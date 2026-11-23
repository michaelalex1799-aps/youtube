#!/usr/bin/env python3
"""White Nights production sample renderer.

Renders procedural "living painting" scenes into two formats:
  long  - 1920x1080 YouTube episode opening
  short - 1080x1920 Instagram Reels / TikTok / YouTube Shorts

Each format is written twice: a clean final cut and a "breakdown" cut that
labels A-roll / B-roll and which of the 6 visual designs each shot shows.

Usage: python3 render.py long|short [--vo DIR] [--out DIR] [--still SECONDS]
If --vo DIR has seg_XX.wav files (one per segment) they set the timing and
are mixed in; otherwise timing is estimated from the script word counts.
"""
import argparse
import math
import os
import subprocess
import sys
import wave
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from script import SCRIPTS, DESIGNS

FPS = 30
XF = 12  # crossfade frames between segments
GOLD = (236, 190, 98)
CREAM = (244, 234, 214)

FONT_FILES = {
    "serif": "/usr/share/fonts/truetype/crosextra/Caladea-Regular.ttf",
    "serif_b": "/usr/share/fonts/truetype/crosextra/Caladea-Bold.ttf",
    "serif_i": "/usr/share/fonts/truetype/crosextra/Caladea-Italic.ttf",
    "hand": "/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf",
    "sans_xb": "/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf",
    "sans_b": "/usr/share/fonts/opentype/inter/Inter-Bold.otf",
    "sans_m": "/usr/share/fonts/opentype/inter/Inter-Medium.otf",
}
_fonts = {}


def font(name, size):
    key = (name, int(size))
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT_FILES[name], int(size))
    return _fonts[key]


PAL = {
    "present": dict(top=(5, 9, 28), bot=(46, 70, 124), bld=(13, 19, 40), bld2=(19, 27, 54),
                    win=(255, 196, 112), water=(7, 13, 32), lamp=(255, 186, 96), stone=(24, 30, 52)),
    "memory": dict(top=(58, 30, 14), bot=(214, 146, 78), bld=(78, 46, 28), bld2=(104, 64, 38),
                   win=(255, 220, 150), water=(64, 38, 22), lamp=(255, 214, 150), stone=(92, 60, 40)),
    "dream": dict(top=(20, 8, 50), bot=(164, 92, 176), bld=(40, 20, 72), bld2=(60, 32, 98),
                  win=(255, 226, 250), water=(30, 14, 58), lamp=(255, 206, 244), stone=(52, 30, 84)),
}


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def vgrad(w, h, c1, c2, power=1.0):
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None] ** power
    col = np.array(c1, np.float32) * (1 - t) + np.array(c2, np.float32) * t
    return np.repeat(col[:, None, :], w, axis=1)


def add_glow(arr, x, y, r, color, strength=1.0, sx=None, sy=None):
    sx = sx or r
    sy = sy or r
    h, w, _ = arr.shape
    x0, x1 = max(0, int(x - 3 * sx)), min(w, int(x + 3 * sx) + 1)
    y0, y1 = max(0, int(y - 3 * sy)), min(h, int(y + 3 * sy) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    g = np.exp(-((xx - x) ** 2) / (2 * sx * sx) - ((yy - y) ** 2) / (2 * sy * sy)) * strength
    arr[y0:y1, x0:x1] += g[..., None] * np.array(color, np.float32)


def mix(c1, c2, t):
    return tuple(int(a * (1 - t) + b * t) for a, b in zip(c1, c2))


def scale(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


# --------------------------------------------------------------------------- figures

def draw_man(d, x, yf, h, col, phase=None, hat=True):
    """The Dreamer: top hat, long coat. phase=None means standing."""
    hr = 0.065 * h
    hx, hy = x, yf - 0.86 * h
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=col)
    if hat:
        d.rectangle([hx - 0.055 * h, hy - hr - 0.13 * h, hx + 0.055 * h, hy - hr * 0.4], fill=col)
        d.rectangle([hx - 0.095 * h, hy - hr * 0.6, hx + 0.095 * h, hy - hr * 0.25], fill=col)
    d.polygon([(x - 0.13 * h, yf - 0.78 * h), (x + 0.13 * h, yf - 0.78 * h),
               (x + 0.17 * h, yf - 0.30 * h), (x - 0.17 * h, yf - 0.30 * h)], fill=col)
    d.ellipse([x - 0.075 * h, yf - 0.82 * h, x + 0.075 * h, yf - 0.74 * h], fill=col)
    s = 0.0 if phase is None else math.sin(phase) * 0.11 * h
    lw = max(2, int(0.055 * h))
    d.line([(x - 0.04 * h, yf - 0.34 * h), (x - 0.04 * h + s, yf)], fill=col, width=lw)
    d.line([(x + 0.04 * h, yf - 0.34 * h), (x + 0.04 * h - s, yf)], fill=col, width=lw)


def draw_woman(d, x, yf, h, col, hat_col, lean=0.06):
    """Nastenka: yellow hat, black mantle, long dress, elbows on the rail."""
    hr = 0.06 * h
    hx, hy = x + lean * h, yf - 0.84 * h
    d.ellipse([hx - hr, hy - hr, hx + hr, hy + hr], fill=col)
    d.ellipse([hx - 0.12 * h, hy - hr * 0.9, hx + 0.12 * h, hy - hr * 0.1], fill=hat_col)
    d.ellipse([hx - 0.065 * h, hy - hr * 1.9, hx + 0.065 * h, hy - hr * 0.4], fill=hat_col)
    d.polygon([(hx - 0.10 * h, yf - 0.76 * h), (hx + 0.10 * h, yf - 0.76 * h),
               (x + 0.16 * h, yf - 0.48 * h), (x - 0.13 * h, yf - 0.48 * h)], fill=col)
    d.polygon([(x - 0.11 * h, yf - 0.50 * h), (x + 0.13 * h, yf - 0.50 * h),
               (x + 0.24 * h, yf), (x - 0.21 * h, yf)], fill=col)
    lw = max(2, int(0.04 * h))
    d.line([(hx + 0.06 * h, yf - 0.72 * h), (x + 0.26 * h, yf - 0.55 * h)], fill=col, width=lw)


# --------------------------------------------------------------------------- canal world

def build_canal(w, h, pal, seed=3, fg=False, woman=False, stars=True, moon=True):
    rng = np.random.default_rng(seed)
    P = PAL[pal]
    u = min(w, h)
    portrait = h > w
    base_y = int(h * (0.50 if fg else (0.53 if portrait else 0.57)))
    emb = int(0.022 * u)
    wy = base_y + emb
    arr = np.zeros((h, w, 3), np.float32)
    arr[:wy] = vgrad(w, wy, P["top"], P["bot"], 1.4)
    if stars:
        n = int(w * h / 5000)
        xs = rng.integers(0, w, n)
        ys = (rng.random(n) ** 1.6 * base_y * 0.9).astype(int)
        br = rng.random(n) ** 3
        for x, y, b in zip(xs, ys, br):
            arr[y, x] = np.maximum(arr[y, x], 120 + 135 * b)
            if b > 0.6:
                add_glow(arr, x, y, 1.6, (200, 210, 255), 0.9)
    moon_pos = None
    if moon:
        mx, my, mr = w * 0.8, h * (0.14 if portrait else 0.16), 0.034 * u
        add_glow(arr, mx, my, mr * 3.0, (150, 170, 230), 0.35)
        yy, xx = np.mgrid[0:h, 0:w]
        m1 = (xx - mx) ** 2 + (yy - my) ** 2 < mr * mr
        m2 = (xx - mx - mr * 0.42) ** 2 + (yy - my + mr * 0.12) ** 2 < (mr * 0.92) ** 2
        arr[m1 & ~m2] = (246, 238, 214)
        moon_pos = (mx, my, mr)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)

    lit = []
    x = -int(0.02 * u)
    land_dome = w * 0.63
    land_spire = w * 0.24
    while x < w:
        bw = int(rng.uniform(0.07, 0.16) * u)
        bh = int(rng.uniform(0.08, 0.17) * u)
        col = P["bld"] if rng.random() < 0.5 else P["bld2"]
        top = base_y - bh
        d.rectangle([x, top, x + bw, base_y], fill=col)
        d.rectangle([x - 2, top, x + bw + 2, top + max(2, int(0.005 * u))], fill=scale(col, 1.35))
        if rng.random() < 0.3:
            d.polygon([(x + bw * 0.25, top), (x + bw * 0.75, top), (x + bw * 0.5, top - bw * 0.18)], fill=col)
        ws, hs = 0.021 * u, 0.026 * u
        cols = max(1, int(bw / ws) - 1)
        rows = max(1, int(bh / hs) - 1)
        for r in range(rows):
            for c in range(cols):
                wx = x + (c + 0.8) * bw / (cols + 0.6)
                wyy = top + (r + 0.9) * hs
                rect = [wx, wyy, wx + 0.008 * u, wyy + 0.012 * u]
                if rng.random() < 0.26:
                    k = rng.uniform(0.55, 1.0)
                    d.rectangle(rect, fill=scale(P["win"], k))
                    lit.append((rect, k))
                else:
                    d.rectangle(rect, fill=scale(col, 0.7))
        x += bw + int(rng.uniform(0, 0.01) * u)
    # landmark dome (St Isaac's-like) and needle spire (Admiralty-like)
    dc = P["bld2"]
    dr = 0.075 * u
    d.rectangle([land_dome - 1.3 * dr, base_y - 0.22 * u, land_dome + 1.3 * dr, base_y], fill=dc)
    d.rectangle([land_dome - 0.75 * dr, base_y - 0.30 * u, land_dome + 0.75 * dr, base_y - 0.22 * u], fill=dc)
    for i in range(7):
        cx = land_dome - 0.65 * dr + i * 1.3 * dr / 6
        d.line([(cx, base_y - 0.295 * u), (cx, base_y - 0.225 * u)], fill=scale(dc, 1.5), width=max(1, int(0.003 * u)))
    d.pieslice([land_dome - 0.75 * dr, base_y - 0.30 * u - 0.75 * dr, land_dome + 0.75 * dr, base_y - 0.30 * u + 0.75 * dr], 180, 360, fill=scale(P["lamp"], 0.55))
    d.rectangle([land_dome - 0.1 * dr, base_y - 0.30 * u - 1.05 * dr, land_dome + 0.1 * dr, base_y - 0.30 * u - 0.7 * dr], fill=scale(P["lamp"], 0.6))
    d.rectangle([land_spire - 0.05 * u, base_y - 0.2 * u, land_spire + 0.05 * u, base_y], fill=P["bld"])
    d.rectangle([land_spire - 0.022 * u, base_y - 0.28 * u, land_spire + 0.022 * u, base_y - 0.2 * u], fill=P["bld"])
    d.polygon([(land_spire - 0.009 * u, base_y - 0.28 * u), (land_spire + 0.009 * u, base_y - 0.28 * u),
               (land_spire, base_y - 0.47 * u)], fill=scale(P["lamp"], 0.7))
    # embankment
    d.rectangle([0, base_y, w, wy], fill=P["stone"])
    d.line([(0, base_y), (w, base_y)], fill=scale(P["stone"], 1.6), width=max(1, int(0.003 * u)))
    lamps = []
    lx = 0.05 * u
    while lx < w:
        d.line([(lx, base_y), (lx, base_y - 0.06 * u)], fill=(8, 10, 20), width=max(1, int(0.003 * u)))
        lamps.append((lx, base_y - 0.064 * u))
        lx += 0.12 * u

    arr = np.asarray(img).astype(np.float32)
    for (lx, ly) in lamps:
        add_glow(arr, lx, ly, 0.005 * u, P["lamp"], 1.4)
        add_glow(arr, lx, ly, 0.03 * u, P["lamp"], 0.28)
    # water + reflection
    L = min(h - wy, base_y)
    refl = arr[base_y - L:base_y][::-1]
    water = vgrad(w, h - wy, scale(P["water"], 1.4), P["water"], 0.7)
    arr[wy:wy + L] = refl * 0.40 + water[:L] * 0.60
    if L < h - wy:
        arr[wy + L:] = water[L:]
    for (lx, ly) in lamps:
        add_glow(arr, lx, wy + (base_y - ly) * 1.4, 0.03 * u, P["lamp"], 0.55, sx=0.006 * u, sy=0.07 * u)
    if moon_pos:
        mx, my, mr = moon_pos
        add_glow(arr, mx, wy + (base_y - my) * 0.55, mr, (220, 220, 230), 0.35, sx=mr * 0.8, sy=mr * 4)

    fgy = None
    if fg:
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(img)
        fgy = int(h * 0.86)
        d.rectangle([0, fgy, w, h], fill=(9, 11, 20))
        if woman:
            draw_woman(d, w * (0.60 if not portrait else 0.55), fgy, 0.36 * u, (6, 7, 14), (214, 168, 60))
        rt = fgy - 0.10 * u
        rc = (6, 7, 13)
        d.rectangle([0, rt, w, rt + 0.012 * u], fill=rc)
        d.rectangle([0, fgy - 0.012 * u, w, fgy], fill=rc)
        step = 0.06 * u
        px = 0
        while px < w:
            d.rectangle([px, rt, px + 0.008 * u, fgy], fill=rc)
            cr = 0.022 * u
            cx, cy = px + step / 2, (rt + fgy) / 2
            d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], outline=rc, width=max(2, int(0.004 * u)))
            px += step
        lpx = w * (0.82 if not portrait else 0.85)
        d.rectangle([lpx - 0.006 * u, fgy - 0.5 * u, lpx + 0.006 * u, fgy], fill=rc)
        d.rectangle([lpx - 0.02 * u, fgy - 0.56 * u, lpx + 0.02 * u, fgy - 0.5 * u], fill=rc)
        arr = np.asarray(img).astype(np.float32)
        add_glow(arr, lpx, fgy - 0.53 * u, 0.012 * u, P["lamp"], 1.6)
        add_glow(arr, lpx, fgy - 0.53 * u, 0.12 * u, P["lamp"], 0.25)
    return dict(arr=np.clip(arr, 0, 255).astype(np.uint8), horizon=wy, lit=lit, fgy=fgy, u=u)


# --------------------------------------------------------------------------- scenes

class Scene:
    fog = 0.0
    horizon = None
    shimmer = True
    haze = None

    def frame(self, t):
        return self.img

    def post(self, arr, t, R):
        pass


class Canal(Scene):
    def __init__(self, R, o):
        self.R, self.o = R, o
        c = build_canal(R.SW, R.SH, o.get("pal", "present"), o.get("seed", 3), fg=o.get("fg", False),
                        woman=o.get("woman", False))
        self.img = Image.fromarray(c["arr"])
        self.horizon = c["horizon"]
        self.fgy = c["fgy"]
        self.lit = c["lit"]
        self.u = c["u"]
        self.fog = o.get("fog", 0.22)
        self.P = PAL[o.get("pal", "present")]
        self.particles = o.get("particles", False)
        if self.fgy:
            self.shimmer_end = self.fgy - 0.1 * self.u

    def frame(self, t):
        im = self.img.copy()
        d = ImageDraw.Draw(im)
        for i, (rect, k) in enumerate(self.lit[:40]):
            if math.sin(t * 0.9 + i * 2.3) < -0.93:
                d.rectangle(rect, fill=scale(self.P["bld"], 0.8))
        wk = self.o.get("walker")
        if wk and self.fgy:
            x = self.R.SW * (wk[0] + wk[1] * t)
            draw_man(d, x, self.fgy + 0.03 * self.u, 0.38 * self.u, (4, 5, 10), phase=t * 5.5)
        return im

    def post(self, arr, t, R):
        if self.particles:
            R.particles(arr, t, self.P["lamp"])


class Street(Scene):
    """A row of close house facades. Windows light up as the Dreamer passes."""

    def __init__(self, R, o):
        self.R, self.o = R, o
        W, H = R.SW, R.SH
        u = min(W, H)
        self.u = u
        P = PAL["present"]
        rng = np.random.default_rng(o.get("seed", 11))
        portrait = H > W
        g = int(H * 0.80)
        self.g = g
        arr = vgrad(W, g, P["top"], P["bot"], 1.2)
        full = np.zeros((H, W, 3), np.float32)
        full[:g] = arr
        n = int(W * H / 9000)
        for x, y in zip(rng.integers(0, W, n), rng.integers(0, int(H * 0.25), n)):
            full[y, x] = 200
        add_glow(full, W * 0.85, H * 0.08, 0.03 * u, (230, 230, 245), 1.4)
        add_glow(full, W * 0.85, H * 0.08, 0.12 * u, (120, 140, 210), 0.3)
        img = Image.fromarray(np.clip(full, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(img)
        pastels = [(178, 150, 118), (140, 158, 176), (190, 140, 142), (138, 156, 128), (164, 140, 178), (176, 166, 128)]
        x = -int(0.03 * W)
        self.windows = []
        i = 0
        while x < W:
            hw = int(rng.uniform(0.38, 0.5) * W) if portrait else int(rng.uniform(0.17, 0.24) * W)
            hh = int(rng.uniform(0.48, 0.62) * H) if not portrait else int(rng.uniform(0.38, 0.5) * H)
            base = mix(scale(pastels[i % len(pastels)], 0.30), (14, 22, 48), 0.35)
            top = g - hh
            d.rectangle([x, top, x + hw, g], fill=base)
            d.rectangle([x - 4, top, x + hw + 4, top + 0.018 * u], fill=scale(base, 1.45))
            d.line([(x, top), (x, g)], fill=scale(base, 0.6), width=3)
            cols = 3
            rows = 4 if not portrait else 5
            ww = hw / (cols * 2 + 1)
            wh = (hh - 0.18 * u) / (rows * 1.7)
            for r in range(rows):
                for c in range(cols):
                    wx = x + ww * (1 + 2 * c)
                    wyy = top + 0.05 * u + r * wh * 1.7
                    rect = [wx, wyy, wx + ww, wyy + wh]
                    d.rectangle([wx - 4, wyy - 4, wx + ww + 4, wyy + wh + 4], fill=scale(base, 1.3))
                    d.rectangle(rect, fill=(16, 22, 42))
                    d.line([(wx + ww / 2, wyy), (wx + ww / 2, wyy + wh)], fill=scale(base, 1.1), width=3)
                    self.windows.append((rect, rng.random()))
            dx = x + hw / 2
            d.rectangle([dx - 0.03 * u, g - 0.12 * u, dx + 0.03 * u, g], fill=scale(base, 0.5))
            x += hw
            i += 1
        d.rectangle([0, g, W, g + 0.03 * H], fill=(30, 34, 52))
        d.rectangle([0, g + 0.03 * H, W, H], fill=(14, 16, 28))
        for _ in range(int(W * 0.3)):
            cx, cy = rng.integers(0, W), rng.integers(int(g + 0.035 * H), H)
            r = rng.uniform(0.006, 0.014) * u
            d.ellipse([cx - r, cy - r * 0.5, cx + r, cy + r * 0.5], fill=(20 + rng.integers(0, 12),) * 3)
        self.img = img
        self.fog = o.get("fog", 0.12)
        self.shimmer = False

    def frame(self, t):
        im = self.img.copy()
        d = ImageDraw.Draw(im)
        W = self.R.SW
        wk = self.o.get("walker", (0.1, 0.03))
        xw = W * (wk[0] + wk[1] * t)
        light = self.o.get("lightup", True)
        win = PAL["present"]["win"]
        for rect, rnd in self.windows:
            cx = (rect[0] + rect[2]) / 2
            if light:
                b = min(1.0, max(0.0, (xw + 0.32 * W - cx) / (0.05 * W)))
            else:
                b = 1.0 if rnd < 0.3 else 0.0
            if b <= 0:
                continue
            col = mix((16, 22, 42), scale(win, 0.75 + 0.25 * rnd), b)
            d.rectangle(rect, fill=col)
            if rnd < 0.45 and b > 0.7:
                ww = rect[2] - rect[0]
                hx, hy = (rect[0] + rect[2]) / 2 + (rnd - 0.2) * ww * 0.6, rect[1] + (rect[3] - rect[1]) * 0.45
                r = ww * 0.16
                sc = mix(col, (40, 26, 18), 0.8)
                d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=sc)
                d.ellipse([hx - r * 2.2, hy + r * 0.9, hx + r * 2.2, rect[3] + r * 2], fill=sc)
                d.rectangle([rect[0], rect[3] - 3, rect[2], rect[3]], fill=(16, 22, 42))
        draw_man(d, xw, self.g + 0.05 * self.R.SH, 0.30 * self.R.SH if self.R.portrait else 0.42 * self.R.SH,
                 (4, 5, 10), phase=t * 5.5)
        return im


class PinkHouse(Scene):
    """Memory (amber): the little pink house being painted yellow."""

    def __init__(self, R, o):
        self.R, self.o = R, o
        W, H = R.SW, R.SH
        u = min(W, H)
        P = PAL["memory"]
        portrait = H > W
        g = int(H * 0.80)
        self.g = g
        self.bbox = None
        imgs = []
        for body in [(214, 132, 140), (232, 200, 58)]:
            full = np.zeros((H, W, 3), np.float32)
            full[:g] = vgrad(W, g, P["top"], P["bot"], 1.1)
            add_glow(full, W * 0.5, g * 0.85, 0.5 * u, (255, 200, 120), 0.25)
            img = Image.fromarray(np.clip(full, 0, 255).astype(np.uint8))
            d = ImageDraw.Draw(img)
            ug = (88, 64, 50)
            if portrait:
                hx0, hx1 = W * 0.16, W * 0.84
                top = g - H * 0.36
            else:
                hx0, hx1 = W * 0.36, W * 0.64
                top = g - H * 0.46
            d.rectangle([0, g - H * 0.66, hx0, g], fill=ug)
            d.rectangle([hx1, g - H * 0.70, W, g], fill=scale(ug, 0.9))
            for (a, b) in [(0, hx0), (hx1, W)]:
                for r in range(7):
                    for c in range(4):
                        wx = a + (b - a) * (0.12 + c * 0.22)
                        wyy = g - H * 0.62 + r * H * 0.08
                        if wyy < g - H * 0.08:
                            d.rectangle([wx, wyy, wx + (b - a) * 0.09, wyy + H * 0.045], fill=(60, 40, 30))
            hw = hx1 - hx0
            d.rectangle([hx0, top, hx1, g], fill=body)
            d.polygon([(hx0 - hw * 0.03, top), (hx1 + hw * 0.03, top), ((hx0 + hx1) / 2, top - hw * 0.22)],
                      fill=scale(body, 1.08))
            d.polygon([(hx0 + hw * 0.08, top - 4), (hx1 - hw * 0.08, top - 4), ((hx0 + hx1) / 2, top - hw * 0.17)],
                      fill=scale(body, 0.85))
            d.rectangle([hx0 - hw * 0.03, top, hx1 + hw * 0.03, top + hw * 0.035], fill=(245, 232, 212))
            for k in range(4):
                cx = hx0 + hw * (0.12 + k * 0.253)
                d.rectangle([cx - hw * 0.025, top + hw * 0.06, cx + hw * 0.025, g - hw * 0.05], fill=(240, 226, 206))
            for k in range(3):
                cx = hx0 + hw * (0.245 + k * 0.253)
                for r in range(2):
                    wyy = top + hw * (0.12 + r * 0.33)
                    d.rectangle([cx - hw * 0.07, wyy, cx + hw * 0.07, wyy + hw * 0.2], fill=(240, 226, 206))
                    d.rectangle([cx - hw * 0.055, wyy + hw * 0.015, cx + hw * 0.055, wyy + hw * 0.185], fill=(255, 214, 140))
                    d.line([(cx, wyy), (cx, wyy + hw * 0.2)], fill=(240, 226, 206), width=4)
            d.rectangle([(hx0 + hx1) / 2 - hw * 0.07, g - hw * 0.26, (hx0 + hx1) / 2 + hw * 0.07, g], fill=(120, 70, 50))
            d.rectangle([0, g, W, H], fill=(70, 46, 32))
            d.rectangle([0, g, W, g + 0.02 * H], fill=(120, 86, 60))
            self.bbox = (int(hx0 - hw * 0.04), int(top - hw * 0.23), int(hx1 + hw * 0.04), int(g))
            imgs.append(np.asarray(img))
        self.pink, self.yellow = imgs
        self.fog = 0.0
        self.shimmer = False
        self.haze = (255, 190, 120)

    def frame(self, t):
        t0, t1 = self.o.get("paint", (99, 100))
        p = ease((t - t0) / (t1 - t0))
        if p <= 0:
            return Image.fromarray(self.pink)
        if p >= 1:
            return Image.fromarray(self.yellow)
        x0, y0, x1, y1 = self.bbox
        arr = self.pink.copy()
        level = y1 - p * (y1 - y0)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        m = yy > level + 8 * np.sin(xx * 0.04)
        sub = arr[y0:y1, x0:x1]
        sub[m] = self.yellow[y0:y1, x0:x1][m]
        return Image.fromarray(arr)


class Room(Scene):
    """Thought scene: dark room, window onto the night canal, candle on the sill."""

    def __init__(self, R, o):
        self.R, self.o = R, o
        W, H = R.SW, R.SH
        u = min(W, H)
        self.u = u
        arr = vgrad(W, H, (12, 14, 28), (4, 5, 10), 1.0)
        if R.portrait:
            wx0, wx1, wy0, wy1 = W * 0.14, W * 0.86, H * 0.10, H * 0.52
        else:
            wx0, wx1, wy0, wy1 = W * 0.50, W * 0.86, H * 0.10, H * 0.74
        self.win = (wx0, wx1, wy0, wy1)
        vw, vh = int(wx1 - wx0), int(wy1 - wy0)
        view = build_canal(vw, vh, "present", seed=5, stars=True, moon=True)["arr"]
        arr[int(wy0):int(wy0) + vh, int(wx0):int(wx0) + vw] = view
        add_glow(arr, (wx0 + wx1) / 2, wy1, 0.45 * u, (70, 90, 150), 0.22)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(img)
        fr = (22, 16, 14)
        bw = 0.016 * u
        d.rectangle([wx0 - bw, wy0 - bw, wx1 + bw, wy0], fill=fr)
        d.rectangle([wx0 - bw, wy0, wx0, wy1], fill=fr)
        d.rectangle([wx1, wy0, wx1 + bw, wy1], fill=fr)
        d.rectangle([(wx0 + wx1) / 2 - bw / 2, wy0, (wx0 + wx1) / 2 + bw / 2, wy1], fill=fr)
        d.rectangle([wx0, (wy0 + wy1) * 0.45 - bw / 2, wx1, (wy0 + wy1) * 0.45 + bw / 2], fill=fr)
        cw = (wx1 - wx0) * 0.16
        for side in (0, 1):
            x0 = wx0 - cw * 0.6 if side == 0 else wx1 - cw * 0.4
            d.polygon([(x0, wy0 - bw * 2), (x0 + cw, wy0 - bw * 2), (x0 + cw * (0.7 if side == 0 else 0.3), wy1 + bw * 3),
                       (x0, wy1 + bw * 3)], fill=(14, 18, 36))
            for k in range(4):
                fx = x0 + cw * (0.15 + 0.22 * k)
                d.line([(fx, wy0), (fx, wy1)], fill=(9, 11, 24), width=max(2, int(0.004 * u)))
        d.rectangle([0, wy1, W, wy1 + 0.04 * u], fill=(26, 20, 18))
        d.rectangle([0, wy1 + 0.04 * u, W, H], fill=(8, 7, 9))
        mx = (wx0 + wx1) / 2
        draw_man_back(d, mx - (wx1 - wx0) * 0.12, wy1 + 0.04 * u, 0.42 * u)
        self.candle = (wx1 - (wx1 - wx0) * 0.12, wy1)
        cx, cy = self.candle
        d.rectangle([cx - 0.008 * u, cy - 0.05 * u, cx + 0.008 * u, cy], fill=(226, 214, 190))
        self.img = img
        self.fog = 0.0
        self.shimmer = False

    def frame(self, t):
        return self.img

    def post(self, arr, t, R):
        cx, cy = self.candle
        ox, oy = R.to_out(cx, cy - 0.06 * self.u)
        k = R.zoom
        fl = 0.85 + 0.15 * math.sin(t * 13) * math.sin(t * 7.3)
        add_glow(arr, ox, oy, 0.006 * self.u * k, (255, 200, 120), 2.2 * fl, sy=0.012 * self.u * k)
        add_glow(arr, ox, oy, 0.12 * self.u * k, (255, 170, 90), 0.22 * fl)


def draw_man_back(d, x, ybase, h):
    col = (3, 3, 6)
    d.ellipse([x - 0.085 * h, ybase - 0.66 * h, x + 0.085 * h, ybase - 0.45 * h], fill=col)
    d.rectangle([x - 0.05 * h, ybase - 0.48 * h, x + 0.05 * h, ybase - 0.36 * h], fill=col)
    d.rounded_rectangle([x - 0.30 * h, ybase - 0.38 * h, x + 0.30 * h, ybase + 0.1 * h], radius=0.12 * h, fill=col)
    d.polygon([(x - 0.30 * h, ybase - 0.26 * h), (x + 0.30 * h, ybase - 0.26 * h), (x + 0.36 * h, ybase + 0.1 * h), (x - 0.36 * h, ybase + 0.1 * h)], fill=col)


class Desk(Scene):
    """A-roll set: the narrator's desk for storytelling breaks."""

    def __init__(self, R, o):
        self.R = R
        W, H = R.SW, R.SH
        u = min(W, H)
        self.u = u
        rng = np.random.default_rng(7)
        arr = vgrad(W, H, (30, 21, 15), (12, 8, 6), 1.0)
        img = Image.fromarray(arr.astype(np.uint8))
        d = ImageDraw.Draw(img)
        top = int(H * 0.62)
        sh = 0.11 * u
        y = int(H * 0.04)
        while y < top - sh * 0.5:
            x = 0
            while x < W:
                bw = rng.uniform(0.012, 0.03) * u
                bh = rng.uniform(0.6, 0.92) * sh
                c = [(70, 30, 26), (40, 52, 40), (80, 62, 36), (36, 40, 62), (90, 76, 58), (52, 34, 46)][rng.integers(0, 6)]
                d.rectangle([x, y + sh - bh, x + bw, y + sh], fill=scale(c, 0.55))
                d.line([(x + bw * 0.2, y + sh - bh * 0.8), (x + bw * 0.8, y + sh - bh * 0.8)], fill=scale(c, 0.9), width=2)
                x += bw + 1
            d.rectangle([0, y + sh, W, y + sh + 0.012 * u], fill=(36, 24, 16))
            y += int(sh + 0.012 * u)
        d.polygon([(0, top), (W, top), (W, H), (0, H)], fill=(52, 32, 20))
        d.line([(0, top), (W, top)], fill=(90, 60, 38), width=3)
        bx, by = W * 0.5, top + (H - top) * 0.42
        pw, ph = 0.24 * u, 0.17 * u
        d.polygon([(bx - pw, by - ph * 0.5), (bx - 0.01 * u, by - ph * 0.42), (bx - 0.01 * u, by + ph * 0.55), (bx - pw * 1.05, by + ph * 0.5)], fill=(226, 212, 178))
        d.polygon([(bx + pw, by - ph * 0.5), (bx + 0.01 * u, by - ph * 0.42), (bx + 0.01 * u, by + ph * 0.55), (bx + pw * 1.05, by + ph * 0.5)], fill=(232, 218, 184))
        for side in (-1, 1):
            for k in range(9):
                ly = by - ph * 0.35 + k * ph * 0.095
                x0 = bx + side * 0.03 * u
                x1 = bx + side * (pw * 0.9)
                d.line([(x0, ly), (x1, ly)], fill=(150, 138, 116), width=2)
        lx = W * (0.80 if not R.portrait else 0.78)
        d.rectangle([lx - 0.006 * u, top - 0.25 * u, lx + 0.006 * u, top], fill=(120, 92, 46))
        d.ellipse([lx - 0.05 * u, top - 0.02 * u, lx + 0.05 * u, top + 0.012 * u], fill=(110, 84, 40))
        d.polygon([(lx - 0.09 * u, top - 0.22 * u), (lx + 0.09 * u, top - 0.22 * u), (lx + 0.05 * u, top - 0.29 * u),
                   (lx - 0.05 * u, top - 0.29 * u)], fill=(26, 62, 42))
        cx = W * 0.2
        d.rectangle([cx - 0.035 * u, top + 0.02 * u, cx + 0.035 * u, top + 0.1 * u], fill=(200, 190, 176))
        d.arc([cx + 0.02 * u, top + 0.035 * u, cx + 0.06 * u, top + 0.08 * u], 270, 90, fill=(200, 190, 176), width=4)
        arr = np.asarray(img).astype(np.float32)
        add_glow(arr, lx, top - 0.2 * u, 0.25 * u, (255, 180, 100), 0.35)
        add_glow(arr, lx, top - 0.21 * u, 0.04 * u, (255, 220, 160), 0.9, sy=0.012 * u)
        add_glow(arr, bx, by, 0.3 * u, (255, 190, 110), 0.18)
        self.img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        self.fog = 0.0
        self.shimmer = False


SCENES = {"canal": Canal, "street": Street, "pink": PinkHouse, "room": Room, "desk": Desk}


# --------------------------------------------------------------------------- renderer

class Renderer:
    def __init__(self, fmt, segs):
        self.fmt = fmt
        self.portrait = fmt == "short"
        self.W, self.H = (1080, 1920) if self.portrait else (1920, 1080)
        self.SW, self.SH = int(self.W * 1.25), int(self.H * 1.25)
        self.k = self.W / (1080 if self.portrait else 1920)
        self.segs = segs
        self.cache = {}
        rng = np.random.default_rng(1)
        fn = rng.random((self.H // 220 + 3, (2 * self.W) // 320 + 3)).astype(np.float32)
        fog = np.asarray(Image.fromarray((fn * 255).astype(np.uint8)).resize((self.W * 2, self.H), Image.BICUBIC)
                         .filter(ImageFilter.GaussianBlur(40 * self.k))).astype(np.float32) / 255
        yy = np.linspace(0, 1, self.H, dtype=np.float32)[:, None]
        band = 0.62 if not self.portrait else 0.55
        fog = np.clip((fog - 0.3) / 0.5, 0, 1)
        self.fogtex = fog * fog * (3 - 2 * fog) * (0.25 + 0.75 * np.exp(-((yy - band) ** 2) / 0.02))
        yy, xx = np.mgrid[0:self.H, 0:self.W].astype(np.float32)
        r = np.sqrt(((xx - self.W / 2) / (self.W / 2)) ** 2 + ((yy - self.H / 2) / (self.H / 2)) ** 2)
        self.vig = (1 - 0.42 * np.clip(r - 0.45, 0, 1) ** 1.4)[..., None]
        self.grain = [rng.normal(0, 4.5, (self.H, self.W)).astype(np.float32)[..., None] for _ in range(6)]
        canvas = rng.random((self.H // 3 + 1, self.W // 3 + 1)).astype(np.float32)
        canvas = np.asarray(Image.fromarray((canvas * 255).astype(np.uint8)).resize((self.W, self.H), Image.BICUBIC)).astype(np.float32) / 255
        self.canvas = (0.96 + 0.08 * canvas)[..., None]
        self.parts = [(rng.random() * self.W, rng.random() * self.H, 4 + rng.random() * 22, 8 + rng.random() * 30, rng.random() * 6.28) for _ in range(70)]

    def scene(self, name, o):
        key = (name, tuple(sorted((k, str(v)) for k, v in o.items())))
        if key not in self.cache:
            self.cache[key] = SCENES[name](self, o)
        return self.cache[key]

    def to_out(self, x, y):
        x0, y0, cw, ch = self.crop
        return (x - x0) * self.W / cw, (y - y0) * self.H / ch

    def particles(self, arr, t, col):
        for (x, y, r, sp, ph) in self.parts:
            yy = (y - t * sp * self.k) % self.H
            xx = x + math.sin(t * 0.6 + ph) * 20 * self.k
            a = 0.35 + 0.35 * math.sin(t * 1.3 + ph)
            add_glow(arr, xx, yy, r * self.k, col, a)

    def render_seg(self, seg, t):
        sc = self.scene(seg["scene"], seg.get("opts", {}))
        img = sc.frame(t)
        cx0, cy0, s0, cx1, cy1, s1 = seg.get("cam", (0.5, 0.5, 1.2, 0.5, 0.5, 1.05))
        p = ease(t / max(seg["dur"], 0.1)) if seg.get("ease", True) else min(1, t / seg["dur"])
        p = 0.15 * p + 0.85 * (t / max(seg["dur"], 0.1)) if not seg.get("ease", True) else p
        cx = cx0 + (cx1 - cx0) * p
        cy = cy0 + (cy1 - cy0) * p
        s = s0 + (s1 - s0) * p
        punch = seg.get("punch")
        if punch:
            for pt in punch:
                if t >= pt:
                    s *= 1 - 0.12 * math.exp(-(t - pt) * 3.0)
        cw, ch = self.W * s, self.H * s
        x0 = min(max(cx * self.SW - cw / 2, 0), self.SW - cw)
        y0 = min(max(cy * self.SH - ch / 2, 0), self.SH - ch)
        self.crop = (x0, y0, cw, ch)
        self.zoom = self.W / cw
        out = img.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
        arr = np.asarray(out).astype(np.float32)
        if sc.horizon and sc.shimmer:
            hy = int(self.to_out(0, sc.horizon)[1]) + 2
            he = self.H
            if getattr(sc, "fgy", None):
                he = int(self.to_out(0, sc.fgy - 0.1 * sc.u)[1])
            if 0 < hy < he:
                rows = np.arange(hy, he)
                depth = (rows - hy) / max(1, self.H - hy)
                shift = np.round((1.5 + 9 * depth) * self.k * np.sin(rows * 0.09 / self.k + t * 2.2)).astype(int)
                idx = (np.arange(self.W)[None, :] + shift[:, None]) % self.W
                arr[hy:he] = arr[hy:he][np.arange(len(rows))[:, None], idx]
        if sc.fog:
            off = int(t * 22 * self.k) % self.W
            f = self.fogtex[:, off:off + self.W][..., None] * sc.fog
            arr = arr * (1 - f) + np.array((150, 165, 210), np.float32) * f
        sc.post(arr, t, self)
        if sc.haze:
            arr = arr * 0.86 + np.array(sc.haze, np.float32) * 0.10
        return arr

    def frame(self, fi):
        segs = self.segs
        i = 0
        while i + 1 < len(segs) and fi >= segs[i + 1]["f0"]:
            i += 1
        seg = segs[i]
        lf = fi - seg["f0"]
        t = lf / FPS
        arr = self.render_seg(seg, t)
        if i > 0 and lf < XF and not seg.get("cut"):
            prev = segs[i - 1]
            a = ease(lf / XF)
            arr = self.render_seg(prev, prev["dur"] + t) * (1 - a) + arr * a
        if seg.get("fade_in") and t < seg["fade_in"]:
            arr *= ease(t / seg["fade_in"])
        if seg.get("fade_out"):
            rem = seg["dur"] - t
            if rem < seg["fade_out"]:
                arr *= ease(rem / seg["fade_out"])
        arr = arr * self.canvas * self.vig + self.grain[fi % 6]
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        clean = self.overlay(img, seg, t)
        annot = self.annotate(clean.copy(), seg, t, i)
        return clean, annot

    # ---------------------------------------------------------------- overlays
    def overlay(self, img, seg, t):
        d = ImageDraw.Draw(img, "RGBA")
        k = self.k
        kind = seg.get("overlay")
        if kind == "title":
            self.title_card(img, d, seg, t)
        elif kind == "endcard":
            self.end_card(img, d, seg, t)
        if seg.get("ui", True):
            self.moon_ui(d, seg, t)
        if seg.get("hook"):
            self.hook_box(d, seg["hook"], t, seg)
        if seg.get("lower"):
            self.lower_third(d, seg["lower"], t)
        cap = seg.get("cap", "line")
        if cap == "hand":
            self.handwriting(img, d, seg, t)
        elif cap in ("line", "gold"):
            self.captions_long(d, seg, t, gold=(cap == "gold"))
        elif cap == "words":
            self.captions_short(d, seg, t)
        if seg.get("stamp") and t > seg["stamp"][0]:
            a = ease((t - seg["stamp"][0]) / 0.5)
            f = font("serif_i", 44 * k)
            txt = seg["stamp"][1]
            tw = d.textlength(txt, font=f)
            y = self.H * (0.30 if self.portrait else 0.16)
            d.text(((self.W - tw) / 2, y), txt, font=f, fill=GOLD + (int(255 * a),))
        return img

    def moon_ui(self, d, seg, t):
        k = self.k
        night = seg.get("night", 1)
        r = 22 * k
        if self.portrait:
            cx, cy = self.W - 70 * k, 150 * k
        else:
            cx, cy = self.W - 70 * k, 64 * k
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GOLD + (210,), width=max(2, int(2 * k)))
        frac = night / 4
        d.chord([cx - r + 4 * k, cy - r + 4 * k, cx + r - 4 * k, cy + r - 4 * k], 90 - 180 * frac, 90 + 180 * frac, fill=GOLD + (200,))
        f = font("sans_m", 19 * k)
        label = f"NIGHT {night} OF 4"
        tw = d.textlength(label, font=f)
        d.text((cx - r - 14 * k - tw, cy - 12 * k), label, font=f, fill=(240, 232, 214, 200))
        if self.portrait:
            f2 = font("sans_b", 22 * k)
            d.text((60 * k, cy - 13 * k), "WHITE NIGHTS · EP 1", font=f2, fill=(240, 232, 214, 220))

    def chunks(self, text, maxw):
        words = text.split()
        out, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= maxw or w.endswith((".", ",", "!", "?", ";", ":", "—", "…", "”")) and len(cur) >= max(3, maxw // 2):
                out.append(cur)
                cur = []
        if cur:
            out.append(cur)
        return out

    def timed(self, seg, maxw):
        ch = self.chunks(seg["vo"], maxw)
        lead = seg.get("lead", 0.35)
        span = seg.get("vo_len") or seg["dur"] - lead - 0.6
        total = sum(sum(len(w) + 2 for w in c) for c in ch)
        res, tt = [], lead
        for c in ch:
            dt = span * sum(len(w) + 2 for w in c) / total
            res.append((tt, tt + dt, c))
            tt += dt
        return res

    def wrap(self, d, words, f, maxw):
        lines, cur = [], ""
        for w in words:
            test = (cur + " " + w).strip()
            if d.textlength(test, font=f) > maxw and cur:
                lines.append(cur)
                cur = w
            else:
                cur = test
        if cur:
            lines.append(cur)
        return lines

    def captions_long(self, d, seg, t, gold=False):
        if not seg.get("vo"):
            return
        k = self.k
        for (a, b, words) in self.timed(seg, 12 if not self.portrait else 7):
            if a <= t < b + 0.15:
                alpha = min(1, (t - a) / 0.2, (b + 0.15 - t) / 0.15)
                f = font("serif_i" if gold else "serif", (54 if gold else 46) * k * (1.25 if self.portrait else 1))
                lines = self.wrap(d, words, f, self.W * (0.72 if not self.portrait else 0.84))
                lh = f.size * 1.25
                y = self.H * (0.80 if not self.portrait else 0.70) - lh * len(lines) / 2
                bw = max(d.textlength(ln, font=f) for ln in lines)
                d.rounded_rectangle([(self.W - bw) / 2 - 28 * k, y - 14 * k, (self.W + bw) / 2 + 28 * k, y + lh * len(lines) + 8 * k],
                                    radius=16 * k, fill=(6, 8, 18, int(120 * alpha)))
                for ln in lines:
                    tw = d.textlength(ln, font=f)
                    x = (self.W - tw) / 2
                    col = GOLD if gold else (250, 246, 238)
                    d.text((x + 2 * k, y + 2 * k), ln, font=f, fill=(0, 0, 0, int(170 * alpha)))
                    d.text((x, y), ln, font=f, fill=col + (int(255 * alpha),))
                    y += lh
                if gold:
                    a2 = int(200 * alpha)
                    yq = self.H * (0.80 if not self.portrait else 0.70) - lh * len(lines) / 2 - 20 * k
                    d.line([(self.W / 2 - 60 * k, yq), (self.W / 2 + 60 * k, yq)], fill=GOLD + (a2,), width=max(1, int(2 * k)))
                break

    def captions_short(self, d, seg, t):
        if not seg.get("vo"):
            return
        k = self.k
        allw = seg["vo"].split()
        lead = seg.get("lead", 0.3)
        span = seg.get("vo_len") or seg["dur"] - lead - 0.6
        weights = [len(w) + 3 for w in allw]
        tot = sum(weights)
        starts, acc = [], lead
        for wgt in weights:
            starts.append(acc)
            acc += span * wgt / tot
        cur = max([i for i, s in enumerate(starts) if s <= t] or [-1])
        if cur < 0 or t > acc + 0.3:
            return
        g0 = (cur // 3) * 3
        grp = allw[g0:g0 + 3]
        f = font("sans_xb", 84 * k)
        lines = self.wrap(d, grp, f, self.W * 0.86)
        lh = f.size * 1.18
        y = self.H * 0.64 - lh * len(lines) / 2
        wi = g0
        pop = 1.0
        for ln in lines:
            ws = ln.split()
            tw = d.textlength(ln, font=f)
            x = (self.W - tw) / 2
            for w in ws:
                col = GOLD if wi == cur else (255, 255, 255)
                if seg.get("gold_words") and w.strip(".,!?\"'“”").lower() in seg["gold_words"]:
                    col = GOLD
                d.text((x, y), w, font=f, fill=col, stroke_width=int(7 * k), stroke_fill=(0, 0, 0))
                x += d.textlength(w + " ", font=f)
                wi += 1
            y += lh

    def handwriting(self, img, d, seg, t):
        k = self.k
        f = font("hand", (58 if not self.portrait else 64) * k)
        if self.portrait:
            box = (self.W * 0.10, self.H * 0.60, self.W * 0.90)
        else:
            box = (self.W * 0.06, self.H * 0.26, self.W * 0.44)
        lines = self.wrap(d, seg["vo"].split(), f, box[2] - box[0])
        lead = seg.get("lead", 0.35)
        span = seg.get("vo_len") or seg["dur"] - lead - 0.8
        total = sum(len(l) for l in lines)
        y = box[1]
        lh = f.size * 1.3
        done = 0
        for ln in lines:
            ls = lead + span * done / total
            le = lead + span * (done + len(ln)) / total
            done += len(ln)
            if t > ls:
                p = min(1, (t - ls) / max(0.01, le - ls))
                tw = d.textlength(ln, font=f)
                layer = Image.new("L", img.size, 0)
                ImageDraw.Draw(layer).text((box[0], y), ln, font=f, fill=255)
                cut = int(box[0] + tw * p)
                layer.paste(0, (cut, 0, img.size[0], img.size[1])) if p < 1 else None
                img.paste(Image.new("RGB", img.size, CREAM), (0, 0), layer)
                if p < 1:
                    px, py = cut, y + f.size * 0.7
                    d.ellipse([px - 3 * k, py - 3 * k, px + 3 * k, py + 3 * k], fill=GOLD + (230,))
            y += lh

    def hook_box(self, d, hook, t, seg):
        k = self.k
        a = min(1, t / 0.25)
        f = font("sans_xb", 58 * k)
        lines = self.wrap(d, hook.split(), f, self.W * 0.80)
        lh = f.size * 1.22
        y = self.H * 0.17
        for ln in lines:
            tw = d.textlength(ln, font=f)
            x = (self.W - tw) / 2
            d.rounded_rectangle([x - 22 * k, y - 10 * k, x + tw + 22 * k, y + lh - 2 * k], radius=14 * k, fill=(255, 255, 255, int(245 * a)))
            d.text((x, y), ln, font=f, fill=(12, 12, 16, int(255 * a)))
            y += lh

    def lower_third(self, d, txt, t):
        k = self.k
        a = ease(t / 0.6)
        x = 80 * k if not self.portrait else 60 * k
        y = self.H * (0.12 if not self.portrait else 0.22)
        f1 = font("sans_b", 22 * k)
        f2 = font("serif_i", 40 * k)
        d.rectangle([x, y, x + 6 * k, y + 86 * k], fill=GOLD + (int(255 * a),))
        d.text((x + 24 * k, y + 2 * k), txt[0], font=f1, fill=GOLD + (int(255 * a),))
        d.text((x + 24 * k, y + 34 * k), txt[1], font=f2, fill=(250, 244, 232, int(255 * a)))

    def title_card(self, img, d, seg, t):
        k = self.k
        a = ease((t - 0.3) / 0.9)
        d.rectangle([0, 0, self.W, self.H], fill=(4, 6, 16, int(120 * a)))
        cy = self.H * (0.42 if self.portrait else 0.44)
        f1 = font("serif_b", (120 if not self.portrait else 110) * k)
        f2 = font("serif_i", 40 * k)
        f3 = font("sans_m", 22 * k)
        t1 = "WHITE NIGHTS"
        tw = d.textlength(t1, font=f1)
        d.text(((self.W - tw) / 2, cy - f1.size), t1, font=f1, fill=GOLD + (int(255 * a),))
        a2 = ease((t - 1.0) / 0.8)
        d.line([(self.W / 2 - 160 * k, cy + 30 * k), (self.W / 2 + 160 * k, cy + 30 * k)], fill=GOLD + (int(200 * a2),), width=max(1, int(2 * k)))
        t2 = seg.get("subtitle", "")
        lines = self.wrap(d, t2.split(), f2, self.W * 0.8)
        y = cy + 50 * k
        for ln in lines:
            tw = d.textlength(ln, font=f2)
            d.text(((self.W - tw) / 2, y), ln, font=f2, fill=(246, 238, 222, int(255 * a2)))
            y += f2.size * 1.3
        t3 = "FYODOR DOSTOEVSKY · 1848"
        tw = d.textlength(t3, font=f3)
        d.text(((self.W - tw) / 2, y + 20 * k), t3, font=f3, fill=(220, 210, 190, int(220 * a2)))

    def end_card(self, img, d, seg, t):
        k = self.k
        a = ease(t / 0.7)
        d.rectangle([0, 0, self.W, self.H], fill=(4, 6, 16, int(150 * a)))
        f1 = font("serif_i", (52 if not self.portrait else 60) * k)
        q = seg.get("question", "")
        lines = self.wrap(d, q.split(), f1, self.W * 0.8)
        y = self.H * (0.22 if not self.portrait else 0.24)
        for ln in lines:
            tw = d.textlength(ln, font=f1)
            d.text(((self.W - tw) / 2, y), ln, font=f1, fill=GOLD + (int(255 * a),))
            y += f1.size * 1.3
        a2 = ease((t - 1.0) / 0.7)
        if self.portrait:
            bw, bh = self.W * 0.78, self.H * 0.16
            bx, by = (self.W - bw) / 2, self.H * 0.44
        else:
            bw, bh = self.W * 0.34, self.H * 0.30
            bx, by = self.W * 0.14, self.H * 0.50
        d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=18 * k, fill=(20, 26, 52, int(230 * a2)), outline=GOLD + (int(255 * a2),), width=max(2, int(3 * k)))
        f2 = font("sans_b", 22 * k)
        f3 = font("serif_b", 46 * k)
        d.text((bx + 28 * k, by + 24 * k), seg.get("next_label", "NEXT EPISODE"), font=f2, fill=GOLD + (int(255 * a2),))
        for j, ln in enumerate(self.wrap(d, seg.get("next", "").split(), f3, bw - 56 * k)):
            d.text((bx + 28 * k, by + 64 * k + j * 54 * k), ln, font=f3, fill=(250, 244, 232, int(255 * a2)))
        f4 = font("sans_xb", 30 * k)
        if self.portrait:
            sx, sy = self.W / 2 - 170 * k, self.H * 0.64
        else:
            sx, sy = self.W * 0.62, self.H * 0.60
        a3 = ease((t - 1.6) / 0.6)
        d.rounded_rectangle([sx, sy, sx + 340 * k, sy + 84 * k], radius=42 * k, fill=(196, 40, 40, int(255 * a3)))
        lab = seg.get("button", "SUBSCRIBE")
        tw = d.textlength(lab, font=f4)
        d.text((sx + 170 * k - tw / 2, sy + 22 * k), lab, font=f4, fill=(255, 255, 255, int(255 * a3)))

    def annotate(self, img, seg, t, i):
        d = ImageDraw.Draw(img, "RGBA")
        k = self.k
        f1 = font("sans_xb", 24 * k)
        f2 = font("sans_m", 21 * k)
        roll = seg.get("roll", "B")
        col = (214, 70, 70) if roll.startswith("A") else (40, 160, 150)
        x, y = 28 * k, (self.H * 0.80 if self.portrait else 26 * k)
        lines = [DESIGNS[n] for n in seg.get("designs", [])]
        w = max([d.textlength(roll, font=f1)] + [d.textlength(l, font=f2) for l in lines]) + 40 * k
        h = 46 * k + 32 * k * len(lines)
        d.rounded_rectangle([x, y, x + w, y + h], radius=10 * k, fill=(0, 0, 0, 175))
        d.rectangle([x, y, x + 8 * k, y + h], fill=col + (255,))
        d.text((x + 22 * k, y + 10 * k), roll, font=f1, fill=col + (255,))
        for j, l in enumerate(lines):
            d.text((x + 22 * k, y + 46 * k + j * 32 * k), l, font=f2, fill=(240, 240, 240, 255))
        f3 = font("sans_m", 18 * k)
        tc = f"SHOT {i + 1:02d} · {seg['scene'].upper()}"
        tw = d.textlength(tc, font=f3)
        d.text((self.W - tw - 28 * k, self.H - 44 * k), tc, font=f3, fill=(255, 255, 255, 180))
        return img


# --------------------------------------------------------------------------- audio

SR = 44100


def wav_len(path):
    with wave.open(path) as w:
        return w.getnframes() / w.getframerate()


def read_wav(path):
    with wave.open(path) as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype=np.int16 if sw == 2 else np.int32).astype(np.float32)
    a /= 32768.0 if sw == 2 else 2147483648.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    if sr != SR:
        a = np.interp(np.arange(0, len(a) * SR / sr) * sr / SR, np.arange(len(a)), a).astype(np.float32)
    return a


def piano(freq, dur, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.minimum(1, t / 0.006) * np.exp(-t / (0.9 + 200 / freq))
    s = np.zeros(n, np.float32)
    for h, amp in enumerate([1.0, 0.45, 0.22, 0.12, 0.06], start=1):
        f = freq * h * (1 + 0.0004 * h * h)
        s += amp * np.sin(2 * np.pi * f * t) * np.exp(-t * h * 0.6)
    return (s * env * vel).astype(np.float32)


def nfreq(name):
    notes = {"C": -9, "D": -7, "E": -5, "F": -4, "G": -2, "A": 0, "B": 2}
    n = notes[name[0]]
    rest = name[1:]
    if rest.startswith("#"):
        n += 1
        rest = rest[1:]
    if rest.startswith("b"):
        n -= 1
        rest = rest[1:]
    return 440.0 * 2 ** ((n + (int(rest) - 4) * 12) / 12)


def make_music(total, segs, fmt, vo_dir):
    n = int((total + 3) * SR)
    mus = np.zeros(n, np.float32)
    rng = np.random.default_rng(4)
    chords = [("A2", ["A3", "C4", "E4", "A4", "C5"]), ("F2", ["F3", "A3", "C4", "F4", "A4"]),
              ("C3", ["C4", "E4", "G4", "C5", "E5"]), ("G2", ["G3", "B3", "D4", "G4", "B4"])]
    bar = 4.0 if fmt == "long" else 3.0
    step = 0.5 if fmt == "long" else 0.375
    t = 0.0
    ci = 0
    while t < total:
        bass, tones = chords[ci % 4]
        pos = int(t * SR)
        nb = piano(nfreq(bass), 4.0, 0.55)
        mus[pos:pos + len(nb)] += nb[: n - pos]
        for k in range(int(bar / step)):
            if rng.random() < (0.55 if fmt == "long" else 0.7):
                tt = t + k * step
                p = int(tt * SR)
                nt = piano(nfreq(tones[rng.integers(0, len(tones))]), 2.5, rng.uniform(0.18, 0.32))
                mus[p:p + len(nt)] += nt[: n - p]
        pad_t = np.arange(int(bar * SR)) / SR
        pad = sum(np.sin(2 * np.pi * nfreq(x) * pad_t * (1 + 0.002 * np.sin(pad_t * 3))) for x in tones[:3]) * 0.03
        pad *= np.minimum(1, pad_t / 1.0) * np.minimum(1, (bar - pad_t) / 1.0)
        mus[pos:pos + len(pad)] += pad[: n - pos].astype(np.float32)
        t += bar
        ci += 1
    for s in segs:
        if s.get("sting"):
            p = int(s["t0"] * SR)
            for nm in ["A1", "E2", "A2"]:
                x = piano(nfreq(nm), 5.0, 0.6)
                mus[p:p + len(x)] += x[: n - p]
    ir_t = np.arange(int(2.4 * SR)) / SR
    ir = rng.normal(0, 1, len(ir_t)).astype(np.float32) * np.exp(-ir_t / 0.55)
    ir[0] = 6.0
    m = 1 << int(np.ceil(np.log2(n + len(ir))))
    wet = np.fft.irfft(np.fft.rfft(mus, m) * np.fft.rfft(ir, m), m)[:n]
    mus = mus * 0.6 + wet / np.max(np.abs(wet) + 1e-9) * np.max(np.abs(mus)) * 0.55
    noise = np.cumsum(rng.normal(0, 1, n)).astype(np.float32)
    noise -= np.convolve(noise, np.ones(4000) / 4000, mode="same")
    noise /= np.max(np.abs(noise)) + 1e-9
    mus = mus / (np.max(np.abs(mus)) + 1e-9) * 0.5 + noise * 0.035

    vo = np.zeros(n, np.float32)
    has_vo = False
    for i, s in enumerate(segs):
        path = os.path.join(vo_dir, f"seg_{i:02d}.wav") if vo_dir else None
        if path and os.path.exists(path):
            a = read_wav(path)
            p = int((s["t0"] + s.get("lead", 0.35)) * SR)
            vo[p:p + len(a)] += a[: n - p]
            has_vo = True
    if has_vo:
        vo = vo / (np.max(np.abs(vo)) + 1e-9) * 0.89
        env = np.convolve((np.abs(vo) > 0.02).astype(np.float32), np.ones(SR // 2) / (SR // 2), mode="same")
        duck = 1 - 0.55 * np.clip(env * 3, 0, 1)
        mix_ = vo + mus * 0.32 * duck
    else:
        mix_ = mus * 0.9
    fade = int(2.0 * SR)
    end = int(total * SR)
    mix_ = mix_[:end]
    mix_[-fade:] *= np.linspace(1, 0, fade)
    mix_ = np.clip(mix_, -0.98, 0.98)
    st = np.stack([mix_, np.concatenate([np.zeros(300, np.float32), mix_[:-300]])], axis=1)
    return (st * 32767).astype(np.int16), has_vo


# --------------------------------------------------------------------------- main

def plan(fmt, vo_dir):
    segs = [dict(s) for s in SCRIPTS[fmt]]
    t0 = 0.0
    for i, s in enumerate(segs):
        words = len(s.get("vo", "").split())
        est = words / (2.55 if fmt == "long" else 2.8) + s.get("lead", 0.35) + 0.7
        path = os.path.join(vo_dir, f"seg_{i:02d}.wav") if vo_dir else None
        if path and os.path.exists(path):
            s["vo_len"] = wav_len(path)
            est = s["vo_len"] + s.get("lead", 0.35) + s.get("tail", 0.7)
        s["dur"] = max(s.get("min", 0), est)
        lead = s.get("lead", 0.35)
        span = s.get("vo_len") or s["dur"] - lead - 0.6
        if "paint_frac" in s:
            s["opts"] = dict(s.get("opts", {}), paint=tuple(round(lead + f * span, 2) for f in s["paint_frac"]))
        if "punch_frac" in s:
            s["punch"] = [lead + f * span for f in s["punch_frac"]]
        s["t0"] = t0
        s["f0"] = int(round(t0 * FPS))
        t0 += s["dur"]
    return segs, t0


def worker(args):
    fmt, segs, a, b, outdir, idx = args
    R = Renderer(fmt, segs)
    W, H = R.W, R.H
    procs = []
    for kind in ("clean", "annot"):
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
               os.path.join(outdir, f"part_{kind}_{idx:02d}.mp4")]
        procs.append(subprocess.Popen(cmd, stdin=subprocess.PIPE))
    for fi in range(a, b):
        c, an = R.frame(fi)
        procs[0].stdin.write(c.tobytes())
        procs[1].stdin.write(an.tobytes())
    for p in procs:
        p.stdin.close()
        p.wait()
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fmt", choices=["long", "short"])
    ap.add_argument("--vo", default=None)
    ap.add_argument("--out", default="renders")
    ap.add_argument("--still", type=float, nargs="*")
    ap.add_argument("--jobs", type=int, default=4)
    args = ap.parse_args()
    segs, total = plan(args.fmt, args.vo)
    os.makedirs(args.out, exist_ok=True)
    if args.still is not None:
        R = Renderer(args.fmt, segs)
        for s in args.still:
            c, an = R.frame(int(s * FPS))
            an.save(os.path.join(args.out, f"still_{args.fmt}_{s:05.1f}.jpg"), quality=88)
        return
    nframes = int(round(total * FPS))
    print(f"{args.fmt}: {len(segs)} shots, {total:.1f}s, {nframes} frames", flush=True)
    tmp = os.path.join(args.out, f"tmp_{args.fmt}")
    os.makedirs(tmp, exist_ok=True)
    bounds = np.linspace(0, nframes, args.jobs + 1).astype(int)
    jobs = [(args.fmt, segs, bounds[i], bounds[i + 1], tmp, i) for i in range(args.jobs)]
    with Pool(args.jobs) as pool:
        for idx in pool.imap_unordered(worker, jobs):
            print(f"  part {idx} done", flush=True)
    audio, has_vo = make_music(total, segs, args.fmt, args.vo)
    apath = os.path.join(tmp, "audio.wav")
    with wave.open(apath, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(audio.tobytes())
    names = {"long": "white_nights_ep1_youtube_long", "short": "white_nights_ep1_reel_short"}
    for kind, suffix in (("clean", ""), ("annot", "_breakdown")):
        lst = os.path.join(tmp, f"{kind}.txt")
        with open(lst, "w") as f:
            for i in range(args.jobs):
                f.write(f"file 'part_{kind}_{i:02d}.mp4'\n")
        out = os.path.join(args.out, names[args.fmt] + suffix + ".mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-i", apath,
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out], check=True)
        print("wrote", out, "(voice-over mixed)" if has_vo else "(music only, no voice-over yet)", flush=True)


if __name__ == "__main__":
    main()
