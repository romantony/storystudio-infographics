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

python3 -m infogen style            print the resolved style
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
        "palette": {"bg": "#F4EBDD", "bg2": "#FFF8EC", "text": "#1E2A38", "muted": "#6B7A89", "ink": "#1E2A38", "panel": "#1E2A38", "accent": "#E4572E",
                    "accent2": "#2E86AB", "land": "#D9C7A7", "landHi": "#E4572E", "ocean": "#BFD7EA", "border": "#F4EBDD",
                    "series": ["#E4572E", "#2E86AB", "#76B041", "#F3A712", "#A23B72", "#1E2A38"]},
        "image_style": BASE_STYLE + ", warm paper-cutout look, subtle paper grain texture, wide 16:9 composition",
        "palette_prompt": "a muted warm palette",
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

def main(cmd, argv):
    print(json.dumps(load(), indent=1))
