"""Thumbnail, 1280x720: an illustration, an optional cut-out character large on one side, 1 to 3 lines of huge outlined text.
The text is typeset by the Remotion template, not drawn by an image model, so it is spelled exactly as given.
python3 -m infogen thumb --image <asset id> --lines "WHAT IF" "AI BUBBLE" "BURSTS?" [--cast <cut-out id>] [--side right|left]
                         [--badge "DAY BY DAY"] [--out thumb/thumbnail.jpg]
Make two or three variants (different --out) and look at them small: the text must read at phone size."""
import os, sys
from . import render, style as STY
from .common import find_asset, mkdirs

def main(cmd, argv):
    if "--lines" not in argv: sys.exit(__doc__)
    g = lambda k, d=None: argv[argv.index(k) + 1] if k in argv else d
    i = argv.index("--lines") + 1; lines = []
    while i < len(argv) and not argv[i].startswith("--"): lines.append(argv[i]); i += 1
    img = find_asset(g("--image"), ("png", "jpg")) if g("--image") else None
    if g("--image") and not img: sys.exit(f"image not found: {g('--image')}")
    props = {"type": "thumb", "width": 1280, "height": 720, "fps": 30, "seconds": 1, "lines": lines, "image": img, "palette": STY.load()["palette"]}
    if g("--cast"):
        c = find_asset(g("--cast"), ("png",))
        if not c: sys.exit(f"cut-out not found: {g('--cast')}")
        props["cast"] = {"src": c, "side": g("--side", "right")}
    if g("--badge"): props["badge"] = g("--badge")
    out = g("--out", "thumb/thumbnail.jpg"); mkdirs(os.path.dirname(out) or ".")
    if os.path.exists(out): os.remove(out)
    render.run([{"id": "Thumb", "props": props, "out": out, "still": True, "frame": 0}], label="thumb")
    print(out)
