"""Check scripts before anything is generated or rendered.
python3 -m infogen validate [--short <id>] [--assets assets.json] [--plan plan/visual_plan.json] [--target-seconds 600]

Reports: unknown scene types, missing template fields, cues that are not in the narration, data scenes without a
source, long scenes (a visual change every 4 to 10 seconds is the format), pictures used too often, the estimated length
against the target, and image ids that neither exist nor are in assets.json or the visual plan. With --plan, also the
plan itself (ids, references per frame, the budget in request.json), research/visual_facts.json and the facts the
plan cites, and how the scenes use its frames. Exit code 1 on
errors, 0 with warnings."""
import json, os, sys
from collections import Counter
from .build import TYPES, items_of
from .common import find_asset, load
from .narration import WPS, paths
from . import scene3d, timing, visual_plan as VP

REQUIRED = {"illustration": ["image"], "bar_chart": ["items"], "line_chart": ["points"], "donut": ["items"], "counter": ["value"], "icons": ["total", "highlight"],
            "versus": ["a", "b"], "timeline": ["events"], "list": ["items"], "map": [], "title": ["title"], "timecard": ["text"], "text": ["text"], "clip": ["clip"], "bars3d": ["items"], "globe": [], "network3d": ["nodes", "links"]}
FRAME_SECS = (7.5, 12)   # seconds on screen per frame: 50 to 80 frames per 10 minutes
DATA = {"bar_chart", "line_chart", "donut", "counter", "icons", "versus", "bars3d"}

def main(cmd, argv):
    sid = argv[argv.index("--short") + 1] if "--short" in argv else None
    sp, _, _ = paths(sid); script = load(sp); sc = script["scenes"]
    planned = set()
    if "--assets" in argv:
        A = json.load(open(argv[argv.index("--assets") + 1]))
        planned = {x["id"] for g in ("images", "characters", "ltx") for x in A.get(g, [])}
    err, warn = [], []
    if "--plan" in argv:
        P = json.load(open(argv[argv.index("--plan") + 1]))
        visuals = json.load(open("request.json")).get("visuals", {}) if os.path.exists("request.json") else None
        pe, pw = VP.check(P, visuals); fe, fw = VP.check_facts(P, VP.load_facts()); pe += fe; pw += fw; err += [f"plan: {e}" for e in pe]; warn += [f"plan: {w}" for w in pw]
        if not sid:   # Shorts reuse the long video's frames
            se, sw = VP.check_scenes(P, sc); err += [f"plan: {e}" for e in se]; warn += [f"plan: {w}" for w in sw]
        planned |= VP.ids(P)
    seen = Counter()
    words = 0
    for s in sc:
        n = s.get("n"); lab = f"scene {n}"; t = s.get("type")
        if t not in TYPES or t == "endcard": err.append(f"{lab}: type {t!r} (use one of {', '.join(sorted(TYPES - {'endcard'}))})"); continue
        for f in REQUIRED.get(t, []):
            if not s.get(f): err.append(f"{lab}: {t} needs \"{f}\"")
        text = (s.get("narration") or "").strip(); nw = len(text.split()); words += nw
        if not text and not s.get("seconds"): err.append(f"{lab}: no narration and no \"seconds\"")
        est = nw / WPS
        if est > (9 if sid else 14): warn.append(f"{lab}: about {est:.0f} s on one visual; split it (the format changes picture every 4 to 10 s)")
        wl = timing.words(text, None, max(est, 0.1))
        for it in items_of(s):
            if isinstance(it, dict) and it.get("cue") and timing.cue(wl, it["cue"]) is None: err.append(f"{lab}: cue {it['cue']!r} not in its narration")
        err += [f"{lab}: {e}" for e in scene3d.check(s)]
        if t in DATA and not s.get("source"): err.append(f"{lab}: {t} has no \"source\" (every number on screen needs one)")
        if t in DATA and not s.get("verify"): warn.append(f"{lab}: {t} is not marked \"verify\"")
        ids = [s.get("image")] + [c.get("src") or c.get("id") for c in s.get("cast", [])] + [s.get("clip")]
        for i in filter(None, ids):
            if not find_asset(i, ("png", "jpg", "jpeg", "webp", "mp4")) and i not in planned: err.append(f"{lab}: asset {i!r} neither exists nor is in assets.json or the visual plan")
        if t == "illustration": seen[s.get("image")] += 1
    for img, k in seen.items():
        if k > 4: warn.append(f"image {img!r} carries {k} scenes; vary the camera move or add another picture")
    secs = words / WPS
    tgt = int(argv[argv.index("--target-seconds") + 1]) if "--target-seconds" in argv else None
    if tgt and abs(secs - tgt) > tgt * 0.15: warn.append(f"estimated {secs:.0f} s of narration against a target of {tgt} s")
    if "--plan" in argv and not sid and secs:
        nf = len(P.get("frames", [])); per = secs / nf if nf else 0
        if nf and not FRAME_SECS[0] <= per <= FRAME_SECS[1]:
            warn.append(f"plan: {nf} frames for about {secs:.0f} s is one every {per:.1f} s; aim for one every {FRAME_SECS[0]} to {FRAME_SECS[1]} s (50 to 80 per 10 minutes)")
    types = Counter(s.get("type") for s in sc)
    print(json.dumps({"scenes": len(sc), "words": words, "estimated_seconds": round(secs), "types": types, "errors": err, "warnings": warn}, indent=1))
    if err: sys.exit(1)
