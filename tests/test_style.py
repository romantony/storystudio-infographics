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

# ---- "auto": Claude chooses the style and palette, checked ----
import subprocess
ROOTENV = {**os.environ, "PYTHONPATH": ROOT}
run = lambda *a: subprocess.run([sys.executable, "-m", "infogen", "style", *a], capture_output=True, text=True, env=ROOTENV)
check("every preset is readable", all(S.contrast_errors(S.resolved_palette(k, {}, {})) == [] for k in S.PRESETS), {k: S.contrast_errors(S.resolved_palette(k, {}, {})) for k in S.PRESETS})
json.dump({"preset": "auto", "palette": {}, "cast": {}, "choose": {"style": True, "palette": True}}, open("style.json", "w"))
try: S.load(); blocked = False
except SystemExit as e: blocked = "not chosen yet" in str(e)
check("auto: nothing loads (so nothing renders) before the choice", blocked)
r = run(); shown = json.loads(r.stdout) if r.returncode == 0 else {}
check("auto: `style` lists what to choose and the presets", shown.get("to_choose") == ["style", "palette"] and set(shown["presets"]) == set(S.PRESETS), r.stdout[:300])
r = run("--choose", "--preset", "paper", "--palette", json.dumps({"text": "#E0D8C8"}), "--why", "history")
check("auto: unreadable text is refused, naming the pair", r.returncode != 0 and "text on bg: contrast" in r.stderr, r.stderr)
r = run("--choose", "--preset", "comic", "--palette", "{}", "--why", "x")
check("auto: unknown preset refused", r.returncode != 0 and "--preset: one of" in r.stderr, r.stderr)
r = run("--choose", "--preset", "paper", "--palette", json.dumps({"accent": "#9C3D22", "glow": "#FFFFFF"}), "--why", "x")
check("auto: unknown colour key refused", r.returncode != 0 and "palette.glow: unknown colour" in r.stderr, r.stderr)
r = run("--choose", "--preset", "paper", "--palette", json.dumps({"accent": "#9C3D22", "landHi": "#9C3D22", "series": ["#9C3D22", "#3E5C76", "#6B8F3E", "#8A6A14"]}))
check("auto: a reason is required", r.returncode != 0 and "--why" in r.stderr, r.stderr)
r = run("--choose", "--preset", "paper", "--palette", json.dumps({"accent": "#9C3D22", "landHi": "#9C3D22", "series": ["#9C3D22", "#3E5C76", "#6B8F3E", "#8A6A14"]}), "--why", "1948 history: sepia with brick red")
st = S.load() if r.returncode == 0 else {}
check("auto: a good choice is written and loads", r.returncode == 0 and st.get("preset") == "paper" and st["palette"]["accent"] == "#9C3D22" and st["palette"]["bg"] == "#F4EBDD"
      and st["chosen"]["why"].startswith("1948"), (r.stderr, st.get("palette")))
check("auto: choosing twice is refused", run("--choose", "--preset", "paper", "--palette", "{}", "--why", "x").returncode != 0)
json.dump({"preset": "noir_vector", "palette": {"accent": "#FF0000"}, "cast": {}, "choose": {"style": False, "palette": True}}, open("style.json", "w"))
r = run("--choose", "--preset", "paper", "--palette", "{}", "--why", "x")
check("palette auto: the style is the request's, --preset refused", r.returncode != 0 and "choose only the palette" in r.stderr, r.stderr)
r = run("--choose", "--palette", json.dumps({"accent": "#00FF00", "accent2": "#FFD000"}), "--why", "news")
st = S.load() if r.returncode == 0 else {}
check("palette auto: the request's fixed colours win over the chosen ones", r.returncode == 0 and st["preset"] == "noir_vector" and st["palette"]["accent"] == "#FF0000"
      and st["palette"]["accent2"] == "#FFD000", (r.stderr, st.get("palette")))

print("ALL OK" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
