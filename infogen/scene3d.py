"""3D scenes (bars3d, globe, network3d): the spec check, and the Opus animation planner.
  python3 -m infogen scene3d <scene n> [--model claude-opus-5-5] [--short ID]   have Opus design the camera and timing of one 3D scene
The planner may only set how a scene is shot and when things appear (ALLOWED); it can never change a number, a label or a source.
Env: INFOGEN_ANIM_MODEL (default claude-opus-5-5), INFOGEN_SCENE3D_CMD (a shell command that reads the prompt on stdin and prints the reply; for tests)."""
import json, os, re, subprocess, sys
from .common import APP, load
from .narration import paths

TYPES3D = {"bars3d", "globe", "network3d"}
ITEMS = {"bars3d": "items", "globe": None, "network3d": None}
PRESETS = {"orbit", "push_in", "rise", "still"}
MODEL = os.environ.get("INFOGEN_ANIM_MODEL", "claude-opus-5-5")
# scene-level fields the planner may set, and per-item fields (cue = a word or phrase of the narration, at = seconds)
ALLOWED = {"camera", "focus", "spin"}
ITEM_ALLOWED = {"cue", "at", "color", "highlight"}
LISTS = {"bars3d": ["items"], "globe": ["pins", "arcs"], "network3d": ["nodes", "links"]}

def camera_ok(c):
    if isinstance(c, str): return c in PRESETS
    if not isinstance(c, dict): return False
    return all(k in ("az", "el", "dist") and isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v) for k, v in c.items())

def check(s):
    """Errors in one 3D scene's spec (empty list when fine)."""
    t = s.get("type"); err = []
    if t not in TYPES3D: return err
    if "camera" in s and not camera_ok(s["camera"]): err.append(f"camera must be one of {sorted(PRESETS)} or {{az, el, dist}} with [from, to] numbers")
    if t == "bars3d":
        if not 1 <= len(s.get("items", [])) <= 10: err.append("bars3d wants 1 to 10 items")
        for i in s.get("items", []):
            if not isinstance(i.get("value"), (int, float)): err.append(f"item {i.get('label')!r}: value must be a number")
    if t == "globe":
        if not (s.get("pins") or s.get("arcs") or s.get("highlight")): err.append("globe needs pins, arcs or highlight")
        for k in ("pins",):
            for p in s.get(k, []):
                if not (isinstance(p.get("lon"), (int, float)) and isinstance(p.get("lat"), (int, float)) and -180 <= p["lon"] <= 180 and -90 <= p["lat"] <= 90): err.append(f"pin {p.get('label')!r}: lon -180..180 and lat -90..90 numbers")
        for a in s.get("arcs", []):
            for e in ("from", "to"):
                v = a.get(e)
                if not (isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v)): err.append(f"arc {e} must be [lon, lat]")
        if "focus" in s and not (isinstance(s["focus"], list) and len(s["focus"]) == 2): err.append("focus must be [lon, lat]")
    if t == "network3d":
        ids = [n.get("id") or n.get("label") for n in s.get("nodes", [])]
        if not 2 <= len(ids) <= 14: err.append("network3d wants 2 to 14 nodes")
        if len(set(ids)) != len(ids): err.append("node ids must be unique")
        for l in s.get("links", []):
            if l.get("from") not in ids or l.get("to") not in ids: err.append(f"link {l.get('from')!r} -> {l.get('to')!r} names a node that does not exist")
    return err

def prompt(s, brief):
    doc = open(os.path.join(APP, "prompts", "scene3d.md")).read()
    return doc + "\n\n## This scene\n\nNarration:\n" + (s.get("narration") or "(none)") + "\n\nScene JSON:\n" + json.dumps(brief, indent=1) + "\n"

def ask(text, model):
    cmd = os.environ.get("INFOGEN_SCENE3D_CMD")
    if cmd: return subprocess.run(cmd, shell=True, input=text, capture_output=True, text=True, timeout=900).stdout
    out = subprocess.run(["claude", "-p", text, "--model", model, "--output-format", "json", "--max-turns", "2", "--allowedTools", ""], capture_output=True, text=True, timeout=900)
    try: return json.loads(out.stdout).get("result", "")
    except Exception: return out.stdout

def parse(reply):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", reply, re.S)
    for x in ([m.group(1)] if m else []) + [reply[reply.find("{"):reply.rfind("}") + 1]]:
        try:
            d = json.loads(x)
            if isinstance(d, dict): return d
        except Exception: pass
    return None

def merge(s, plan):
    """The scene with the planner's allowed fields applied. Lists are matched by position and must keep their length."""
    out = json.loads(json.dumps(s)); notes = []
    for k in ALLOWED:
        if k in plan: out[k] = plan[k]
    for lst in LISTS[s["type"]]:
        got = plan.get(lst)
        if got is None: continue
        if not isinstance(got, list) or len(got) != len(out.get(lst, [])): notes.append(f"{lst}: ignored (needs {len(out.get(lst, []))} entries, got {len(got) if isinstance(got, list) else 'none'})"); continue
        for item, g in zip(out[lst], got):
            if isinstance(g, dict):
                for k in ITEM_ALLOWED:
                    if k in g and g[k] is not None: item[k] = g[k]
    return out, notes

def main(cmd, argv):
    if not argv or argv[0].startswith("--"): sys.exit(__doc__)
    sid = argv[argv.index("--short") + 1] if "--short" in argv else None
    model = argv[argv.index("--model") + 1] if "--model" in argv else MODEL
    sp, _, _ = paths(sid); script = load(sp); n = int(argv[0])
    s = next((x for x in script["scenes"] if x.get("n") == n), None)
    if not s: sys.exit(f"no scene {n}")
    if s.get("type") not in TYPES3D: sys.exit(f"scene {n} is {s.get('type')!r}, not one of {sorted(TYPES3D)}")
    brief = {k: v for k, v in s.items() if k not in ("narration",)}
    plan = parse(ask(prompt(s, brief), model))
    if not plan: sys.exit("the planner returned no JSON")
    new, notes = merge(s, plan); err = check(new)
    if err: sys.exit("planner output rejected: " + "; ".join(err))
    s.clear(); s.update(new)
    json.dump(script, open(sp, "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"scene": n, "model": model, "camera": new.get("camera"), "notes": notes}))
