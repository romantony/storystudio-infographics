"""The plan of a series (a request with "kind": "series_plan"): every episode's topic, synopsis, format and era, one cast
and look for all of them, and the publish dates. The orchestrator then makes the episodes one at a time, each an ordinary
video request built from its entry.

series/series.json:
{ "name": "Cold War Flashpoints",
  "premise": "Twelve moments when the Cold War nearly turned hot, told as they happened.",
  "cast": {"narrator": "a woman in her 40s, short grey hair, navy blazer, red scarf"},
  "style": "paper", "palette": {"accent": "#9C3D22"}, "style_why": "1940s-60s history: ...",   only when the request's style or palette is "auto"
  "episodes": [{"n": 1, "title": "The Berlin Airlift", "topic": "The Berlin Airlift",
                "synopsis": "How the Western Allies kept 2 million West Berliners alive by air for 15 months ...",
                "format": "true_story", "era": "Berlin, 1948-49"}, ...] }

python3 -m infogen series series/series.json
checks it against request.json (episode count, formats, lengths, unique topics) and fills in, for every episode:
`publish_date` (series_plan.per_week episodes a week, spread over the week, from series_plan.start_date or the next
Monday), `next_title`, `shorts` (the request's angles) and the series `style` and `palette`: the request's, or, when it
says "auto", the plan's choice (one for the whole series, checked like `style --choose`: infogen/style.py). It also writes the overview the reviewer
reads, as series/series.md and series/series.pdf (the link StoryStudio shares). Exit code 1 on errors."""
import datetime as dt, json, os, sys
from . import style as STY

FORMATS = ("explainer", "what_if", "hour_by_hour", "day_by_day", "versus", "body", "ranking", "true_story", "compilation")
ANGLES = ("hook", "stat", "twist", "myth", "countdown")
MIN_SYNOPSIS = 40   # shorter than this, StoryStudio treats a synopsis as missing and writes its own

def dates(n, per_week, start):
    """n publish dates, per_week a week, spread evenly over each week from start (3 a week from a Monday: Mon, Wed, Fri)."""
    return [(start + dt.timedelta(days=7 * (i // per_week) + (i % per_week) * 7 // per_week)).isoformat() for i in range(n)]

def next_monday(today=None):
    today = today or dt.date.today()
    return today + dt.timedelta(days=7 - today.weekday())

def check(plan, req):
    """(errors, warnings) for the plan against the request."""
    err, warn = [], []
    sp = req.get("series_plan") or {}; want = sp.get("episodes", 12); formats = sp.get("formats") or FORMATS
    for k in ("name", "premise"):
        if not str(plan.get(k, "")).strip(): err.append(f'needs a "{k}"')
    cast = plan.get("cast", {})
    if not isinstance(cast, dict) or not all(isinstance(v, str) and v.strip() for v in cast.values()): err.append('"cast" must be an object of id -> visual description')
    else:
        for k, v in ((req.get("visuals") or {}).get("cast") or {}).items():
            if cast.get(k) != v: err.append(f"cast {k!r}: keep the request's description unchanged")
    v = req.get("visuals") or {}; fixed = v.get("palette") if isinstance(v.get("palette"), dict) else {}
    pick_style, pick_palette = v.get("style") == "auto", v.get("palette") == "auto" or (v.get("style") == "auto" and not fixed)
    if pick_style and plan.get("style") not in STY.PRESETS: err.append(f'the request\'s style is "auto": choose "style" for the series, one of {", ".join(STY.PRESETS)}')
    if not pick_style and plan.get("style") not in (None, v.get("style", "flat_vector")): err.append(f'"style": the request sets {v.get("style", "flat_vector")}')
    if pick_palette:
        if not isinstance(plan.get("palette"), dict): err.append('the request\'s palette is "auto": choose "palette" for the series (an object; {} keeps the style\'s)')
        else: err += STY.palette_errors(plan["palette"])
    elif plan.get("palette") not in (None, fixed): err.append('"palette": the request sets the colours')
    if (pick_style or pick_palette) and not str(plan.get("style_why", "")).strip(): err.append('"style_why": one sentence on why the style and palette suit the series')
    if not err and plan.get("style", v.get("style", "flat_vector")) in STY.PRESETS:
        err += STY.contrast_errors(STY.resolved_palette(plan.get("style", v.get("style", "flat_vector")), plan.get("palette") if pick_palette else {}, fixed))
    eps = plan.get("episodes")
    if not isinstance(eps, list): return err + ['"episodes" must be a list'], warn
    if len(eps) != want: err.append(f"{len(eps)} episodes, the request asks for {want} (series_plan.episodes)")
    seen = {"title": {}, "topic": {}}
    for i, e in enumerate(eps):
        lab = f"episode {i + 1}"
        if not isinstance(e, dict): err.append(f"{lab}: must be an object"); continue
        if e.get("n") != i + 1: err.append(f"{lab}: \"n\" must be {i + 1} (episodes in publishing order)")
        for k, hi in (("title", 100), ("topic", 200), ("era", 200)):
            v = str(e.get(k, "")).strip()
            if not v: err.append(f'{lab}: needs a "{k}"')
            elif len(v) > hi: err.append(f"{lab}: {k} is over {hi} characters")
        syn = str(e.get("synopsis", "")).strip()
        if not MIN_SYNOPSIS <= len(syn) <= 2000: err.append(f"{lab}: synopsis must be {MIN_SYNOPSIS} to 2000 characters (the angle and the beats to cover)")
        if e.get("format") not in formats: err.append(f"{lab}: format must be one of {', '.join(formats)}")
        for k in ("title", "topic"):
            v = str(e.get(k, "")).strip().lower()
            if v and v in seen[k]: err.append(f"{lab}: same {k} as episode {seen[k][v]}")
            seen[k].setdefault(v, i + 1)
        for a in e.get("shorts") or []:
            if a not in ANGLES: err.append(f"{lab}: Short angle {a!r} is not one of {', '.join(ANGLES)}")
    fs = {e.get("format") for e in eps if isinstance(e, dict)}
    if len(eps) >= 6 and len(fs) < 3: warn.append(f"only {len(fs)} format(s) across {len(eps)} episodes; vary them so the series doesn't feel repetitive")
    return err, warn

def fill(plan, req, today=None):
    """Publish dates, next titles, Short angles and the style, in place."""
    sp = req.get("series_plan") or {}
    start = dt.date.fromisoformat(sp["start_date"]) if sp.get("start_date") else next_monday(today)
    eps = plan["episodes"]; shorts = req.get("shorts") or {}
    angles = list(shorts.get("angles") or ANGLES[:3])[:shorts.get("count", 3)]
    v = req.get("visuals") or {}; fixed = v.get("palette") if isinstance(v.get("palette"), dict) else {}
    if v.get("style", "flat_vector") != "auto": plan["style"] = v.get("style", "flat_vector")
    plan["palette"] = {**(plan.get("palette") or {}), **fixed}   # the colours every episode is made with; the request's win
    plan["episodes_per_week"] = sp.get("per_week", 3)
    for e, d, nxt in zip(eps, dates(len(eps), sp.get("per_week", 3), start), eps[1:] + [None]):
        e["publish_date"] = d
        e["next_title"] = nxt["title"] if nxt else None
        e["shorts"] = (e.get("shorts") or angles)[:shorts.get("count", 3)]
    return plan

def overview(plan):
    lines = [f"# {plan['name']}", "", plan["premise"], "", f"{len(plan['episodes'])} episodes, {plan['episodes_per_week']} a week, style {plan['style']}."
             + (f" {plan['style_why']}" if plan.get("style_why") else ""), ""]
    if plan.get("palette"): lines += ["Palette: " + ", ".join(f"{k} {v if isinstance(v, str) else ' '.join(v)}" for k, v in plan["palette"].items()), ""]
    if plan.get("cast"): lines += ["Cast:", *[f"- **{k}**: {v}" for k, v in plan["cast"].items()], ""]
    lines += ["| # | Publish | Title | Format | Era |", "|---|---|---|---|---|"]
    lines += [f"| {e['n']} | {e['publish_date']} | {e['title']} | {e['format']} | {e['era']} |" for e in plan["episodes"]]
    for e in plan["episodes"]:
        lines += ["", f"## {e['n']}. {e['title']}", "", f"*{e['topic']}*, {e['format']}, {e['era']}. Shorts: {', '.join(e['shorts']) or 'none'}.", "", e["synopsis"]]
    return "\n".join(lines) + "\n"

FONT = os.environ.get("INFOGEN_PDF_FONT_DIR", "/usr/share/fonts/truetype/dejavu")

def pdf(plan, path):
    """The overview as a PDF: the schedule table, then one section per episode."""
    from fpdf import FPDF
    p = FPDF(format="A4"); p.set_auto_page_break(True, 15); p.set_margins(15, 15, 15)
    p.add_font("D", "", f"{FONT}/DejaVuSans.ttf"); p.add_font("D", "B", f"{FONT}/DejaVuSans-Bold.ttf")
    p.set_title(plan["name"]); p.add_page()
    line = lambda w, h, text: p.multi_cell(w, h, text, new_x="LMARGIN", new_y="NEXT")
    p.set_font("D", "B", 20); line(0, 10, plan["name"]); p.ln(2)
    p.set_font("D", "", 11); line(0, 6, plan["premise"]); p.ln(2)
    p.set_font("D", "", 9); line(0, 5, f"{len(plan['episodes'])} episodes, {plan['episodes_per_week']} a week, style {plan['style']}."
                                     + (f" {plan['style_why']}" if plan.get("style_why") else "")); p.ln(1)
    pal = STY.resolved_palette(plan["style"], plan.get("palette"), {}); x0 = p.get_x(); y = p.get_y()
    for i, c in enumerate([pal[k] for k in ("bg", "text", "accent", "accent2", "land", "landHi", "ocean")] + pal["series"][:6]):
        p.set_fill_color(*(int(c[k:k + 2], 16) for k in (1, 3, 5))); p.set_draw_color(160, 160, 160); p.rect(x0 + i * 8, y, 7, 7, style="DF")
    p.set_y(y + 10)
    if plan.get("cast"):
        p.set_font("D", "B", 10); p.cell(0, 6, "Cast", new_x="LMARGIN", new_y="NEXT"); p.set_font("D", "", 9)
        for k, v in plan["cast"].items(): line(0, 5, f"{k}: {v}")
        p.ln(2)
    p.set_font("D", "", 8)
    with p.table(col_widths=(6, 18, 70, 20, 36), text_align="LEFT", line_height=4.5) as t:
        for row in [("#", "Publish", "Title", "Format", "Era")] + [(str(e["n"]), e["publish_date"], e["title"], e["format"], e["era"]) for e in plan["episodes"]]:
            r = t.row()
            for c in row: r.cell(c)
    for e in plan["episodes"]:
        p.ln(4); p.set_font("D", "B", 12); line(0, 7, f"{e['n']}. {e['title']}")
        p.set_font("D", "", 8); line(0, 5, f"{e['publish_date']} · {e['format']} · {e['era']} · Shorts: {', '.join(e['shorts']) or 'none'}")
        p.set_font("D", "", 10); line(0, 5.5, f"Topic: {e['topic']}"); p.ln(1); line(0, 5.5, e["synopsis"])
    p.output(path)

def main(cmd, argv):
    if not argv: sys.exit(__doc__)
    path = argv[0]; plan = json.load(open(path))
    req = json.load(open("request.json")) if os.path.exists("request.json") else {}
    err, warn = check(plan, req)
    if not err:
        fill(plan, req); json.dump(plan, open(path, "w"), indent=1, ensure_ascii=False)
        d = os.path.dirname(path) or "."; open(os.path.join(d, "series.md"), "w").write(overview(plan))
        pdf(plan, os.path.join(d, "series.pdf"))
    print(json.dumps({"episodes": len(plan.get("episodes") or []), "errors": err, "warnings": warn,
                      "dates": [e.get("publish_date") for e in plan.get("episodes") or [] if isinstance(e, dict)]}, indent=1))
    if err: sys.exit(1)
