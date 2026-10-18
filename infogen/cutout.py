"""Cut a character out of its plain background, for the cast layer of illustration scenes and for thumbnails.
python3 -m infogen cutout <asset id or path> [...] [--out-dir assets/cutouts] [--tol 60]

Characters are generated on a flat pure-green background (see style.py), which keys cleanly: every pixel close to the key
colour goes, wherever it is. On any other plain background only the region connected to the border is removed, so a
white shirt on a white background survives. Green fringe is suppressed and the edge is feathered by a pixel.
Writes <out-dir>/<id>.png (RGBA, cropped to the character). Look at the result (sheet) before using it."""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from .common import ASSETS, find_asset, mkdirs

def cut(src, out, tol=60):
    im = Image.open(src).convert("RGB"); a = np.asarray(im).astype(np.int16)
    h, w, _ = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    key = np.median(border, axis=0)
    green = key[1] > 150 and key[0] < 140 and key[2] < 140
    dist = np.sqrt(((a - key) ** 2).sum(axis=2))
    if green:
        # chroma key: green dominance, not just distance, so shaded green is caught too
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        bg = (dist < tol * 1.6) | ((g - np.maximum(r, b)) > 70)
    else:
        work = im.copy(); seeds = [(x, y) for x in range(0, w, 32) for y in (0, h - 1)] + [(x, y) for y in range(0, h, 32) for x in (0, w - 1)]
        for s in seeds:
            if dist[s[1], s[0]] < tol and work.getpixel(s) != (1, 2, 3): ImageDraw.floodfill(work, s, (1, 2, 3), thresh=tol)
        bg = np.all(np.asarray(work) == (1, 2, 3), axis=2)
    alpha = Image.fromarray(np.where(bg, 0, 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    rgb = a.copy()
    if green:   # despill: no channel-green brighter than the other two
        mx = np.maximum(rgb[..., 0], rgb[..., 2]); rgb[..., 1] = np.minimum(rgb[..., 1], mx + 10)
    res = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA"); res.putalpha(alpha)
    box = res.getbbox()
    if not box: sys.exit(f"cutout: nothing left of {src} (is the whole image one colour?)")
    m = 8; box = (max(box[0] - m, 0), max(box[1] - m, 0), min(box[2] + m, w), min(box[3] + m, h))
    res = res.crop(box); res.save(out)
    kept = 1 - bg.mean()
    return out, kept

def main(cmd, argv):
    if not argv: sys.exit(__doc__)
    od = argv[argv.index("--out-dir") + 1] if "--out-dir" in argv else f"{ASSETS}/cutouts"
    tol = int(argv[argv.index("--tol") + 1]) if "--tol" in argv else 60
    names = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] not in ("--out-dir", "--tol"))]
    mkdirs(od); bad = 0
    for n in names:
        src = find_asset(n, ("png", "jpg", "jpeg", "webp"))
        if src and src.startswith(f"{ASSETS}/cutouts"): src = f"{ASSETS}/{os.path.basename(src)}"
        if not src or not os.path.exists(src): print("missing", n); bad += 1; continue
        out, kept = cut(src, f"{od}/{os.path.splitext(os.path.basename(src))[0]}.png", tol)
        warn = "  (check it: very little or almost everything was removed)" if kept < 0.05 or kept > 0.9 else ""
        print(out, f"kept {kept:.0%}{warn}")
    if bad: sys.exit(1)
