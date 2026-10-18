"""Contact sheets, so images and video frames can be checked by eye before they are used or published.
python3 -m infogen sheet --images a.jpg b.png ... --out build/sheet.jpg [--cols 6]
python3 -m infogen sheet --video out/x.mp4 --n 12 --out build/frames.jpg
python3 -m infogen sheet --assets --out build/assets_sheet.jpg          (every generated image and cut-out, labelled)"""
import glob, os, subprocess, sys, tempfile
from PIL import Image, ImageDraw
from .common import ASSETS, dur

def sheet(files, out, cols=6, cell=(320, 200), labels=None):
    rows = (len(files) + cols - 1) // cols; S = Image.new("RGB", (cell[0] * cols, cell[1] * rows)); d = ImageDraw.Draw(S)
    for i, f in enumerate(files):
        im = Image.open(f)
        if im.mode in ("RGBA", "LA"):   # cut-outs on a checkerboard so the transparency shows
            bg = Image.new("RGB", im.size, (200, 200, 200)); dd = ImageDraw.Draw(bg)
            for y in range(0, im.size[1], 40):
                for x in range((y // 40 % 2) * 40, im.size[0], 80): dd.rectangle((x, y, x + 39, y + 39), fill=(150, 150, 150))
            bg.paste(im, (0, 0), im.split()[-1]); im = bg
        im = im.convert("RGB"); im.thumbnail(cell); x, y = (i % cols) * cell[0], (i // cols) * cell[1]; S.paste(im, (x, y))
        if labels: d.rectangle((x, y, x + 8 * len(labels[i]) + 6, y + 14), fill=(0, 0, 0)); d.text((x + 3, y + 1), labels[i], fill=(255, 255, 0))
    S.save(out, quality=88); print(out, len(files), "images")

def main(cmd, argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else "build/sheet.jpg"
    cols = int(argv[argv.index("--cols") + 1]) if "--cols" in argv else 6
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    if "--assets" in argv:
        fs = sorted(glob.glob(f"{ASSETS}/*.png") + glob.glob(f"{ASSETS}/*.jpg") + glob.glob(f"{ASSETS}/cutouts/*.png"))
        sheet(fs, out, cols, labels=[("cut:" if "/cutouts/" in f else "") + os.path.basename(f).rsplit(".", 1)[0][:28] for f in fs])
    elif "--video" in argv:
        v = argv[argv.index("--video") + 1]; n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 12; D = dur(v)
        vert = "--vertical" in argv; tmp = tempfile.mkdtemp(); fs = []
        for i in range(n):
            f = f"{tmp}/{i:03d}.jpg"; t = D * (i + 0.5) / n
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", v, "-frames:v", "1", f], check=True); fs.append(f)
        sheet(fs, out, cols, cell=(270, 480) if vert else (480, 270), labels=[f"{D * (i + 0.5) / n:.0f}s" for i in range(n)])
    else:
        i = argv.index("--images") + 1; fs = [a for a in argv[i:] if not a.startswith("--") and os.path.exists(a)]
        sheet(fs, out, cols, labels=[os.path.basename(f).rsplit(".", 1)[0][:30] for f in fs])
