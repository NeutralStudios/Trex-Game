"""Generate the 'Frozen Night' texture theme for rossning92/t-rex.

Usage: python3 make_textures.py <repo>/docs
Writes snow.jpg + night-sky.jpg and recolors the model diffuse maps in place.
"""
import sys, os
import numpy as np
from PIL import Image, ImageFilter

DOCS = sys.argv[1]
rng = np.random.default_rng(7)


def periodic_noise(h, w, scale, seed):
    """Tileable fractal noise via filtered FFT (periodic in both axes)."""
    r = np.random.default_rng(seed)
    white = r.standard_normal((h, w))
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    f = np.sqrt(fx ** 2 + fy ** 2)
    f[0, 0] = 1
    amp = 1.0 / (f ** scale)
    amp[0, 0] = 0
    n = np.real(np.fft.ifft2(np.fft.fft2(white) * amp))
    n -= n.min(); n /= n.max()
    return n


def lerp(a, b, t):
    return a + (b - a) * t


def ramp(t, stops):
    """Map t in [0,1] (HxW) through color stops [(pos,(r,g,b)),...] -> HxWx3."""
    pos = np.array([p for p, _ in stops])
    cols = np.array([c for _, c in stops], dtype=np.float64)
    out = np.empty(t.shape + (3,))
    for c in range(3):
        out[..., c] = np.interp(t, pos, cols[:, c])
    return out


def save(arr, path, **kw):
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path, **kw)


# ---------------------------------------------------------------- snow floor
def make_snow():
    N = 1024
    base = periodic_noise(N, N, 1.6, 1)          # soft drifts
    detail = periodic_noise(N, N, 0.9, 2)        # grain
    v = 0.65 * base + 0.35 * detail
    v = (v - v.min()) / (v.max() - v.min())
    col = ramp(v, [(0, (150, 172, 205)), (0.45, (205, 220, 240)),
                   (0.8, (236, 243, 252)), (1, (255, 255, 255))])
    # sparkles
    sp = rng.random((N, N)) > 0.9985
    col[sp] = [255, 255, 255]
    save(col, os.path.join(DOCS, "snow.jpg"), quality=90)


# ---------------------------------------------------------------- night sky
def make_sky():
    W, H = 2880, 1440
    y = np.linspace(0, 1, H)[:, None] * np.ones((1, W))  # 0 top, 0.5 horizon
    x = np.linspace(0, 1, W, endpoint=False)[None, :] * np.ones((H, 1))
    up = np.clip((0.5 - y) / 0.5, 0, 1)                 # 1 at zenith, 0 at horizon

    sky = ramp(up, [(0, (40, 70, 110)), (0.12, (22, 40, 78)),
                    (0.45, (10, 16, 42)), (1, (4, 6, 18))])

    # stars
    stars = np.zeros((H, W))
    k = 5000
    sy = rng.integers(0, H // 2 - 20, k); sx = rng.integers(0, W, k)
    stars[sy, sx] = rng.random(k) ** 3
    stars = np.array(Image.fromarray((stars * 255).astype(np.uint8))
                     .filter(ImageFilter.GaussianBlur(0.8))) / 255.0 * 3
    stars += np.where(rng.random((H, W)) > 0.9993, 1.0, 0) * (y < 0.48)
    sky += stars[..., None] * np.array([230, 240, 255])

    # aurora: wavy curtains, periodic in x so the sphere seam is invisible
    for (cy, amp, freq, phase, color, strength) in [
        (0.30, 0.05, 3, 0.0, (60, 255, 170), 1.0),
        (0.25, 0.04, 5, 1.7, (120, 200, 255), 0.55),
        (0.34, 0.03, 2, 3.1, (170, 110, 255), 0.45),
    ]:
        center = cy + amp * np.sin(2 * np.pi * freq * x + phase) \
                 + 0.015 * np.sin(2 * np.pi * 11 * x + phase * 2)
        d = y - center
        # sharp bottom edge, long fade upward like real aurora
        band = np.where(d > 0, np.exp(-(d / 0.012) ** 2), np.exp(-(d / 0.07) ** 2))
        rays = 0.6 + 0.4 * np.sin(2 * np.pi * 90 * x + 4 * np.sin(2 * np.pi * 7 * x))
        sky += (band * rays * strength)[..., None] * np.array(color) * 0.75

    # distant snowy mountains on horizon (periodic)
    ridge = 0.5 - (0.035 * (0.5 + 0.5 * np.sin(2 * np.pi * 4 * x[0] + 0.5))
                   + 0.02 * np.abs(np.sin(2 * np.pi * 13 * x[0]))
                   + 0.008 * np.sin(2 * np.pi * 41 * x[0]))
    mountain = y > ridge[None, :]
    mshade = ramp(np.clip((y - ridge[None, :]) / 0.04, 0, 1),
                  [(0, (150, 175, 210)), (1, (55, 70, 105))])
    sky = np.where(mountain[..., None], mshade, sky)

    # snowy plain below horizon
    below = y > 0.5
    plain = ramp(np.clip((y - 0.5) / 0.5, 0, 1),
                 [(0, (120, 140, 175)), (0.3, (170, 190, 220)), (1, (210, 225, 245))])
    sky = np.where(below[..., None], plain, sky)
    save(sky, os.path.join(DOCS, "night-sky.jpg"), quality=88)


# ---------------------------------------------------------- model recolors
def load(path):
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float64)


def lum(a):
    return (0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]) / 255.0


def redness(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return np.clip((r - np.maximum(g, b)) / 80.0, 0, 1)


def stretch(l):
    lo, hi = np.percentile(l, 1), np.percentile(l, 99)
    return np.clip((l - lo) / (hi - lo), 0, 1)


def recolor_trex():
    p = os.path.join(DOCS, "models/t-rex/textures/material_0_diffuse.png")
    a = load(p)
    l = stretch(lum(a))
    # icy skin: navy shadows -> glacier blue -> frost white
    skin = ramp(l, [(0, (12, 30, 70)), (0.35, (60, 130, 190)),
                    (0.7, (170, 220, 245)), (1, (245, 252, 255))])
    # former red spikes/belly stripes -> glowing electric cyan
    spikes = ramp(l, [(0, (0, 60, 110)), (0.5, (0, 200, 235)), (1, (190, 255, 255))])
    m = redness(a)[..., None]
    save(lerp(skin, spikes, m), p)


def recolor_ptero():
    p = os.path.join(DOCS, "models/pterodactyl/textures/material_0_diffuse.png")
    a = load(p)
    l = stretch(lum(a))
    body = ramp(l, [(0, (14, 8, 35)), (0.4, (60, 35, 110)),
                    (0.75, (140, 100, 200)), (1, (220, 200, 255))])
    accent = ramp(l, [(0, (60, 0, 50)), (0.5, (230, 60, 190)), (1, (255, 190, 240))])
    m = redness(a)[..., None]
    save(lerp(body, accent, m), p)


def recolor_cactus():
    p = os.path.join(DOCS, "models/cactus/textures/Cactus_1_Material_diffuse.png")
    a = load(p)
    l = stretch(lum(a))
    frost = ramp(l, [(0, (10, 45, 60)), (0.4, (40, 120, 135)),
                     (0.75, (150, 215, 225)), (1, (240, 255, 255))])
    # keep pure-black unused UV space black
    empty = (a.sum(-1) < 15)[..., None]
    save(np.where(empty, a, frost), p)


if __name__ == "__main__":
    make_snow(); make_sky()
    recolor_trex(); recolor_ptero(); recolor_cactus()
    print("done")
