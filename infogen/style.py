"""The look of a series: palette for the motion graphics, prompt wrappers for generated art, and the recurring cast.

style.json in the run folder (all keys optional; anything missing comes from the preset):
{ "preset": "flat_vector" | "noir_vector" | "paper",
  "palette": {"bg": "#0E2740", "accent": "#FFC93C", ...},          see remotion/src/theme.ts for every key
  "cast": {"narrator_guy": "a young man, short brown hair, orange hoodie, jeans, white sneakers"},
  "logo": "assets/logo.png" }

Prompts in assets.json may name cast members in braces, "{narrator_guy} staring at a falling stock chart": the
description is substituted, so a character looks the same in every image.

python3 -m infogen style            print the resolved style
"""
import json, os, re, sys

BASE_STYLE = ("flat 2D vector illustration in the style of a modern animated explainer video, clean geometric shapes, bold flat colours, "
              "simple soft cel shading, smooth gradient sky or background, simple rounded cartoon people with large heads and simple dot eyes, "
              "expressive poses, minimal detail, crisp edges")
PRESETS = {
    "flat_vector": {
        "palette": {},
        "image_style": BASE_STYLE + ", vibrant saturated palette, cinematic wide composition",
        "character_style": BASE_STYLE + ", full body character, centred, standing, three-quarter view, isolated on a plain flat solid pure green #00FF00 background, "
                           "no ground shadow, no scenery, the character contains no green",
        "negative": "text, letters, words, captions, watermark, logo, signature, photo, photorealistic, 3d render, blurry, extra limbs, deformed hands",
    },
    "noir_vector": {
        "palette": {"bg": "#14141C", "bg2": "#2A1E2E", "accent": "#FF4D4D", "accent2": "#FFC93C", "land": "#3A3A4A", "ocean": "#0E0E14", "border": "#0E0E14",
                    "series": ["#FF4D4D", "#FFC93C", "#E0E0E0", "#7FB7FF", "#B388EB", "#FF9F1C"]},
        "image_style": BASE_STYLE + ", dark moody palette, deep blues and blacks with red highlights, dramatic rim light, night-time atmosphere, cinematic",
        "character_style": None,
        "negative": None,
    },
    "paper": {
        "palette": {"bg": "#F4EBDD", "bg2": "#FFF8EC", "text": "#1E2A38", "muted": "#6B7A89", "ink": "#1E2A38", "panel": "#1E2A38", "accent": "#E4572E",
                    "accent2": "#2E86AB", "land": "#D9C7A7", "landHi": "#E4572E", "ocean": "#BFD7EA", "border": "#F4EBDD",
                    "series": ["#E4572E", "#2E86AB", "#76B041", "#F3A712", "#A23B72", "#1E2A38"]},
        "image_style": BASE_STYLE + ", warm paper-cutout look, subtle paper grain texture, muted warm palette",
        "character_style": None,
        "negative": None,
    },
}

def load(path="style.json"):
    s = json.load(open(path)) if os.path.exists(path) else {}
    pre = PRESETS.get(s.get("preset", "flat_vector"), PRESETS["flat_vector"]); base = PRESETS["flat_vector"]
    out = {k: (pre.get(k) if pre.get(k) is not None else base[k]) for k in base}
    out["palette"] = {**pre["palette"], **s.get("palette", {})}
    out["cast"] = s.get("cast", {}); out["logo"] = s.get("logo"); out["preset"] = s.get("preset", "flat_vector")
    for k in ("image_style", "character_style", "negative"):
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
    return f"{body}. {wrap}. Avoid: {st['negative']}."

def main(cmd, argv):
    print(json.dumps(load(), indent=1))
