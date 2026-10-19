"""The look of a series: palette for the motion graphics, prompt wrappers for generated art, and the recurring cast.

style.json in the run folder (all keys optional; anything missing comes from the preset):
{ "preset": "flat_vector" | "noir_vector" | "paper",
  "palette": {"bg": "#0E2740", "accent": "#FFC93C", ...},          see remotion/src/theme.ts for every key
  "cast": {"narrator_guy": "a young man, short brown hair, orange hoodie, jeans, white sneakers"},
  "era": "Berlin, 1948-49",                                        the time and place every picture must match
  "palette_prompt": "muted 1940s palette of olive green, khaki, slate blue, warm grey and cream",
  "anchor": "assets/anchor.png",                                  style sample every reference is drawn from (path or URL; default infogen/anchors/<preset>.png)
  "logo": "assets/logo.png" }

Prompts in assets.json may name cast members in braces, "{narrator_guy} staring at a falling stock chart": the
description is substituted, so a character looks the same in every image. `era` and `palette_prompt` are added to
every image prompt, so clothing, vehicles and colours stay in period across the whole video.

"style": "auto" (or "palette": "auto") in the request leaves the choice to the run: style.json then has "preset": "auto"
and/or a "choose" block ({"style": true, "palette": true}), and nothing renders until Claude has chosen, after the
research:

python3 -m infogen style --choose --preset paper --palette '{"accent": "#9C3D22", ...}' --why "1948 history: ..."
    checks the choice (a known preset; known colour keys, "#RRGGBB", series a list of 1-12; readable contrast, below)
    and writes it to style.json. Colours fixed by the request ("palette" in style.json) always win over chosen ones.
    --preset only when the style is to be chosen, --palette only when the palette is ('{}' keeps the preset's).

Contrast (WCAG ratios, on the final palette): text on bg, text on ink and ink on panel at least 4.5; ink on accent,
muted on bg and accent on bg at least 3; every series colour on bg at least 2, and no two series colours nearly the same; landHi on land at least 1.5.

python3 -m infogen style            print the resolved style (or, while the choice is open, the presets to choose from)
"""
import json, os, re, sys

# Flat infographic look with grown-up proportions. Explicitly no gradients or lighting: the model adds both by default,
# and they are what made earlier runs look painterly. People are drawn at real proportions (the old wrapper asked for
# "large heads", which gave a chibi look).
BASE_STYLE = ("flat vector infographic illustration, minimalist 2D, clean geometric shapes, bold uniform outlines, "
              "flat colour fills with no gradients, no lighting effects and no texture, simple faces with dot eyes, "
              "realistic adult body proportions with the head about one seventh of body height, children drawn as children, "
              "minimal detail, crisp edges")
NEGATIVE = ("text, letters, words, captions, watermark, logo, signature, photo, photorealistic, 3d render, painterly, glossy, "
            "realistic lighting, soft shading, gradient, chibi, big head, oversized head, blurry, extra limbs, deformed hands")
PRESETS = {
    "flat_vector": {
        "palette": {},
        "image_style": BASE_STYLE + ", wide 16:9 composition with clear separation between subjects",
        # Plain white, not green: these figures also serve as reference images for scene edits (VISUAL_UPGRADE_PLAN.md),
        # and cutout.py removes a plain non-green background by flood fill from the border.
        "character_style": BASE_STYLE + ", one full-body figure, front-facing, standing, centred with space around it, "
                           "isolated on a plain flat pure white background, no ground shadow, no scenery",
        "negative": NEGATIVE,
        "palette_prompt": "a restrained natural palette of muted colours",
    },
    "noir_vector": {
        "palette": {"bg": "#14141C", "bg2": "#2A1E2E", "accent": "#FF4D4D", "accent2": "#FFC93C", "land": "#3A3A4A", "ocean": "#0E0E14", "border": "#0E0E14",
                    "series": ["#FF4D4D", "#FFC93C", "#E0E0E0", "#7FB7FF", "#B388EB", "#FF9F1C"]},
        "image_style": BASE_STYLE + ", wide 16:9 composition, night-time scene",
        "palette_prompt": "a dark palette of deep blues and near-blacks with red accents",
        "character_style": None,
        "negative": None,
    },
    "paper": {
        # ink is light here: it is the background behind text on timecards and badges, and the text on panel labels
        # (it used to equal text and panel, which made both unreadable); the gold is darkened to read on cream
        "palette": {"bg": "#F4EBDD", "bg2": "#FFF8EC", "text": "#1E2A38", "muted": "#6B7A89", "ink": "#FFF8EC", "panel": "#1E2A38", "accent": "#E4572E",
                    "accent2": "#2E86AB", "land": "#D9C7A7", "landHi": "#E4572E", "ocean": "#BFD7EA", "border": "#F4EBDD",
                    "series": ["#E4572E", "#2E86AB", "#76B041", "#B07A00", "#A23B72", "#1E2A38"]},
        "image_style": BASE_STYLE + ", warm paper-cutout look, subtle paper grain texture, wide 16:9 composition",
        "palette_prompt": "a muted warm palette",
        "character_style": None,
        "negative": None,
    },
}

PALETTE_KEYS = ("bg", "bg2", "text", "muted", "ink", "panel", "accent", "accent2", "good", "bad", "land", "landHi", "ocean", "border", "series")
HEX = re.compile(r"#[0-9a-fA-F]{6}$")
DEFAULT_PALETTE = {"bg": "#0E2740", "bg2": "#17507A", "text": "#FFFFFF", "muted": "#A9C1D6", "ink": "#11233A", "panel": "#FFFFFF", "accent": "#FFC93C",
                   "accent2": "#FF5A5F", "good": "#3DDC97", "bad": "#FF5A5F", "land": "#2C6A8C", "landHi": "#FFC93C", "ocean": "#0B1F33", "border": "#0B1F33",
                   "series": ["#FFC93C", "#FF5A5F", "#3DDC97", "#4CC9F0", "#B388EB", "#FF9F1C", "#F15BB5", "#9EF01A"]}   # remotion/src/theme.ts

def palette_errors(p):
    """Errors for a palette override: known keys, "#RRGGBB", series a list of 1 to 12."""
    if not isinstance(p, dict): return ['palette must be an object of colour key -> "#RRGGBB"']
    err = []
    for k, v in p.items():
        if k not in PALETTE_KEYS: err.append(f"palette.{k}: unknown colour (allowed: {', '.join(PALETTE_KEYS)})")
        elif k == "series":
            if not (isinstance(v, list) and 1 <= len(v) <= 12 and all(isinstance(c, str) and HEX.match(c) for c in v)): err.append('palette.series: a list of 1 to 12 colours like "#FFC93C"')
        elif not (isinstance(v, str) and HEX.match(v)): err.append(f'palette.{k}: a colour like "#FFC93C"')
    return err

def luminance(c):
    def ch(x):
        x = int(x, 16) / 255
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[1:3]) + 0.7152 * ch(c[3:5]) + 0.0722 * ch(c[5:7])

def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)

def contrast_errors(p):
    """Readability of a full palette (the preset's, the chosen and the fixed colours merged)."""
    err = []
    # ink is both a background (timecards, badges: text on ink) and a text colour (on panel labels and accent markers)
    for fg, bg, need in (("text", "bg", 4.5), ("text", "ink", 4.5), ("ink", "panel", 4.5), ("ink", "accent", 3), ("muted", "bg", 3), ("accent", "bg", 3), ("landHi", "land", 1.5)):
        r = contrast(p[fg], p[bg])
        if r < need: err.append(f"{fg} on {bg}: contrast {r:.1f}, needs {need}")
    for i, c in enumerate(p["series"]):
        r = contrast(c, p["bg"])
        if r < 2: err.append(f"series[{i}] {c} on bg: contrast {r:.1f}, needs 2")
        for j in range(i):
            d = sum((int(c[k:k + 2], 16) - int(p["series"][j][k:k + 2], 16)) ** 2 for k in (1, 3, 5)) ** 0.5
            if d < 40: err.append(f"series[{i}] {c} is too close to series[{j}] {p['series'][j]}")
    return err

def resolved_palette(preset, chosen, fixed):
    return {**DEFAULT_PALETTE, **PRESETS[preset]["palette"], **(chosen or {}), **(fixed or {})}

def open_choice(s): return s.get("preset") == "auto" or any((s.get("choose") or {}).values())

def load(path="style.json"):
    s = json.load(open(path)) if os.path.exists(path) else {}
    if open_choice(s): sys.exit('the style is "auto" and not chosen yet: after the research, run python3 -m infogen style --choose (python3 -m infogen style --help)')
    pre = PRESETS.get(s.get("preset", "flat_vector"), PRESETS["flat_vector"]); base = PRESETS["flat_vector"]
    out = {k: (pre.get(k) if pre.get(k) is not None else base[k]) for k in base}
    out["palette"] = {**pre["palette"], **s.get("chosen_palette", {}), **s.get("palette", {})}   # the request's colours win over chosen ones
    out["chosen"] = s.get("chosen")
    out["cast"] = s.get("cast", {}); out["logo"] = s.get("logo"); out["preset"] = s.get("preset", "flat_vector")
    out["era"] = s.get("era"); out["anchor"] = s.get("anchor")
    for k in ("image_style", "character_style", "negative", "palette_prompt"):
        if s.get(k): out[k] = s[k]
    return out

def expand(prompt, st):
    """Replace {cast_id} with that cast member's description."""
    def sub(m):
        k = m.group(1)
        if k not in st["cast"]: sys.exit(f"prompt names {{{k}}} but style.json has no cast member {k!r}")
        return st["cast"][k]
    return re.sub(r"\{([A-Za-z0-9_]+)\}", sub, prompt)

def image_prompt(prompt, st, kind="scene"):
    body = expand(prompt, st)
    wrap = st["character_style"] if kind == "character" else st["image_style"]
    era = f", everything historically accurate for {st['era']}" if st.get("era") else ""
    return f"{body}. {wrap}, {st['palette_prompt']}{era}. Avoid: {st['negative']}."

def choose(argv, path="style.json"):
    s = json.load(open(path)) if os.path.exists(path) else {}
    want = s.get("choose") or {}
    if not open_choice(s): sys.exit("nothing to choose: the request set the style and the palette")
    arg = lambda k: argv[argv.index(k) + 1] if k in argv else None
    preset, raw, why = arg("--preset"), arg("--palette"), (arg("--why") or "").strip()
    err, chosen = [], {}
    if want.get("style"):
        if preset not in PRESETS: err.append(f"--preset: one of {', '.join(PRESETS)}")
    elif preset: err.append("--preset: the request set the style; choose only the palette")
    if want.get("palette"):
        if raw is None: err.append("--palette: give the chosen colours as JSON ('{}' keeps the preset's)")
        else:
            try: chosen = json.loads(raw)
            except Exception: err.append("--palette: not valid JSON"); chosen = {}
            err += palette_errors(chosen)
    elif raw: err.append("--palette: the request set the palette; choose only the style")
    if not why: err.append("--why: one sentence on why this suits the topic")
    final = preset if want.get("style") else s.get("preset", "flat_vector")
    if not err: err += contrast_errors(resolved_palette(final, chosen, s.get("palette")))
    if err: sys.exit("style not chosen:\n" + "\n".join(f"- {e}" for e in err))
    s["preset"] = final; s["chosen_palette"] = chosen
    s["chosen"] = {"style": final if want.get("style") else None, "palette": chosen if want.get("palette") else None, "why": why}
    s.pop("choose", None)
    json.dump(s, open(path, "w"), indent=1)
    print(json.dumps({"preset": final, "palette": resolved_palette(final, chosen, s.get("palette")), "why": why}, indent=1))

def main(cmd, argv):
    if "--choose" in argv: return choose(argv)
    if "--help" in argv: sys.exit(__doc__)
    s = json.load(open("style.json")) if os.path.exists("style.json") else {}
    if open_choice(s):
        print(json.dumps({"to_choose": [k for k, v in (s.get("choose") or {}).items() if v], "fixed_palette": s.get("palette", {}),
                          "presets": {k: {"palette": resolved_palette(k, {}, s.get("palette")), "pictures": v["image_style"].replace(BASE_STYLE, "<flat vector base>")}
                                      for k, v in PRESETS.items()}}, indent=1)); return
    print(json.dumps(load(), indent=1))
