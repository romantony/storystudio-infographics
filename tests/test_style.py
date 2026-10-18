"""The series style (infogen/style.py) and the white-background cut-out (infogen/cutout.py). Spends nothing.
Run: .venv/bin/python tests/test_style.py"""
import json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PIL import Image, ImageDraw
from infogen import cutout, style as S

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

tmp = tempfile.mkdtemp(); os.chdir(tmp)

# defaults: grown-up flat look, no chibi / gradient wording left in what is asked for
st = S.load()
p = S.image_prompt("a pilot waving", st)
check("no chibi wording in the wrapper", "large heads" not in p and "gradient sky" not in p and "cel shading" not in p, p)
check("asks for flat fills and adult proportions", "no gradients" in p and "one seventh of body height" in p, p)
check("negative names chibi and gradient", "chibi" in st["negative"] and "gradient" in st["negative"], st["negative"])
check("default palette line, no era line", st["palette_prompt"] in p and "historically accurate" not in p, p)
c = S.image_prompt("a pilot", st, "character")
check("characters on plain white, not green", "pure white background" in c and "green" not in c.split("Avoid:")[0], c)

# era and palette from style.json reach every prompt
json.dump({"era": "Berlin, 1948-49", "palette_prompt": "muted 1940s palette of olive, khaki and slate blue",
           "cast": {"pilot": "a US transport pilot in a brown leather flight jacket"}}, open("style.json", "w"))
st = S.load()
for kind in ("scene", "character"):
    q = S.image_prompt("{pilot} waving", st, kind)
    check(f"{kind}: era, palette and cast substituted", "historically accurate for Berlin, 1948-49" in q and "muted 1940s palette" in q
          and "brown leather flight jacket" in q and "{pilot}" not in q, q)

# other presets keep their own palette line and inherit the shared negative / character style
json.dump({"preset": "noir_vector"}, open("style.json", "w")); st = S.load()
check("noir: own palette line, shared negative", "near-blacks" in st["palette_prompt"] and st["negative"] == S.NEGATIVE, st)
check("noir: no lighting effects asked for", "rim light" not in st["image_style"], st["image_style"])
json.dump({"preset": "paper", "palette_prompt": "sepia tones"}, open("style.json", "w")); st = S.load()
check("style.json palette_prompt overrides the preset", st["palette_prompt"] == "sepia tones", st["palette_prompt"])

# cut-out on white: the border-connected background goes, a white shirt inside the outline stays
im = Image.new("RGB", (400, 600), "white"); d = ImageDraw.Draw(im)
d.ellipse((160, 60, 240, 140), fill=(240, 200, 170), outline="black", width=5)      # head
d.rectangle((140, 140, 260, 380), fill="white", outline="black", width=5)           # white shirt, outlined
d.rectangle((150, 380, 250, 560), fill=(120, 110, 80), outline="black", width=5)    # trousers
im.save("fig.png")
out, kept = cutout.cut("fig.png", "fig_cut.png")
a = Image.open(out).getchannel("A"); w, h = a.size
check("background removed (corners transparent)", a.getpixel((0, 0)) == 0 and a.getpixel((w - 1, h - 1)) == 0, a.getpixel((0, 0)))
check("white shirt inside the outline kept", a.getpixel((w // 2, int(h * 0.4))) == 255, a.getpixel((w // 2, int(h * 0.4))))
check("figure kept, background gone", 0.2 < kept < 0.5, kept)

print("ALL OK" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
