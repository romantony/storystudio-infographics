"""The visual plan: every reference the video needs (characters, objects, backgrounds), drawn from one style anchor, and
every illustration frame composed from them. Scenes use a frame by id ("image": "f012"), like any other asset.

plan/visual_plan.json:
{ "project_id": "berlin_airlift",
  "characters":  [{"id": "pilot_us", "label": "the pilot", "prompt": "{pilot_us}, smiling, arms relaxed", "aspect": "3:4"}],
  "objects":     [{"id": "c54", "label": "the transport plane", "prompt": "{c54} in side view, flying level"}],
  "backgrounds": [{"id": "tempelhof", "prompt": "an empty 1948 Tempelhof airfield: apron, runway, a wire fence on the right ..."}],
  "frames":      [{"id": "f012", "background": "tempelhof", "refs": ["pilot_us", "kids_berlin", "c54"],
                   "prompt": "the pilot stands on the left, fully visible at about half the frame height, waving up; the children stand behind the fence on the right ...",
                   "add": "the plane flies low in the upper sky, coming in to land, small against the sky"}] }

- The style anchor is one flat character sheet in the target look: `anchor` in style.json (a path or URL), else the
  preset's default (infogen/anchors/<preset>.png), else "anchor": {"prompt": ...} in the plan (generated, then reviewed).
- References are drawn new from the anchor with qwen-image-edit ("a new picture in exactly the same style as image 1,
  but of ..."), on plain white (characters, objects). Backgrounds are drawn onto a blank canvas with the anchor as image
  2, as an empty set: with the anchor as image 1 its person stays in the picture. Restyling a detailed picture does not
  work; drawing new from the anchor does. Characters and objects are also cut out, for thumbnails.
- A frame is one qwen-image-edit job: image 1 is its background, images 2-3 its first two refs; a third ref is added in
  a second pass, described by `add`. A frame with no background is text-to-image from its prompt and takes no refs.
- `label` is how a prompt names the reference ("the pilot"); default: the id with spaces.
- `animate` on a frame is accepted for the animation stage (not run yet).

python3 -m infogen queue plan/visual_plan.json [--only anchor,refs,frames]
python3 -m infogen validate --plan plan/visual_plan.json      (with the script checks; budget from request.json)"""
import base64, io, json, os, re, sys
from PIL import Image
from . import cutout, rp, style as STY
from .common import ASSETS, APP

GROUPS = ("characters", "objects", "backgrounds")
MAX_IMAGES = 3                    # qwen-image-edit: images per pass
BUDGET = {"characters": ("characters", 6), "objects": ("objects", 8), "backgrounds": ("backgrounds", 8), "frames": ("illustrations", 24)}
ID = re.compile(r"[A-Za-z0-9_]+$")
SAME_STYLE = ("in exactly the same flat vector style as image 1: the same line weight, the same flat colour fills with no shading, "
              "the same simple face style and the same realistic body proportions")

def is_plan(spec): return isinstance(spec, dict) and "frames" in spec

def label(r): return r.get("label") or r["id"].replace("_", " ")

def refs_by_id(plan): return {r["id"]: (g, r) for g in GROUPS for r in plan.get(g, [])}

def check(plan, visuals=None):
    """(errors, warnings) for the plan on its own: shape, ids, refs per frame, budget."""
    err, warn = [], []
    ids = []
    if plan.get("anchor") is not None and not (isinstance(plan["anchor"], dict) and plan["anchor"].get("prompt")):
        err.append('anchor: give {"prompt": "..."} or leave it out (style.json `anchor` or the preset default is used)')
    for g in GROUPS + ("frames",):
        if not isinstance(plan.get(g, []), list): err.append(f"{g}: must be a list"); continue
        for i, x in enumerate(plan.get(g, [])):
            lab = f"{g}[{i}]"
            if not isinstance(x, dict) or not ID.match(str(x.get("id", ""))): err.append(f"{lab}: needs an \"id\" of letters, digits and _"); continue
            ids.append(x["id"])
            if not str(x.get("prompt", "")).strip(): err.append(f"{x['id']}: needs a \"prompt\"")
    for i in {i for i in ids if ids.count(i) > 1}: err.append(f"id {i!r} is used more than once (references and frames share one id space)")
    refs = refs_by_id(plan); bgs = {r["id"] for r in plan.get("backgrounds", [])}
    for f in plan.get("frames", []):
        if not isinstance(f, dict) or "id" not in f: continue
        fid = f["id"]; rs = f.get("refs", [])
        if f.get("background") and f["background"] not in bgs: err.append(f"{fid}: background {f['background']!r} is not in backgrounds")
        if not isinstance(rs, list): err.append(f"{fid}: refs must be a list"); continue
        for r in rs:
            if r not in refs or refs[r][0] == "backgrounds": err.append(f"{fid}: ref {r!r} is not a character or object")
        if len(rs) > MAX_IMAGES: err.append(f"{fid}: at most {MAX_IMAGES} refs (image 1 is the background)")
        if rs and not f.get("background"): err.append(f"{fid}: refs need a background (image 1 is the setting they are placed into)")
        if len(rs) == MAX_IMAGES and not str(f.get("add", "")).strip(): err.append(f"{fid}: a third ref is added in a second pass; say how in \"add\"")
        if "animate" in f and not isinstance(f["animate"], dict): err.append(f"{fid}: animate must be an object")
    for g, (field, default) in BUDGET.items():
        cap = (visuals or {}).get(field, default) if visuals is not None else None
        n = len(plan.get(g, []))
        if cap is not None and n > cap: err.append(f"{g}: {n} planned, the request allows {cap} (visuals.{field})")
    used = {r for f in plan.get("frames", []) if isinstance(f, dict) for r in f.get("refs", [])} | {f.get("background") for f in plan.get("frames", []) if isinstance(f, dict)}
    for r in refs:
        if r not in used: warn.append(f"{r}: no frame uses it (it is still paid for)")
    return err, warn

def check_scenes(plan, scenes):
    """Warnings for how the script uses the frames: unused frames, a frame carrying more than 2 scenes, a frame used again
    after other scenes came between (one picture = one visual beat, at most two consecutive scenes with different crops)."""
    warn = []; fids = [f["id"] for f in plan.get("frames", []) if isinstance(f, dict) and "id" in f]
    order = [s.get("image") for s in scenes if s.get("type") == "illustration"]
    for fid in fids:
        pos = [i for i, x in enumerate(order) if x == fid]
        if not pos: warn.append(f"{fid}: no illustration scene uses this frame"); continue
        if len(pos) > 2: warn.append(f"{fid}: carries {len(pos)} scenes; at most 2")
        if pos[-1] - pos[0] + 1 != len(pos): warn.append(f"{fid}: used again after other scenes; plan a new frame")
    return warn

def ids(plan): return {x["id"] for g in GROUPS + ("frames",) for x in plan.get(g, []) if isinstance(x, dict) and "id" in x}

# ---------- generation ----------

def anchor_source(plan, st):
    """(image for the edit endpoint: URL or base64, or None) and the asset id to generate it as when it must be generated."""
    a = st.get("anchor")
    if not a:
        d = os.path.join(APP, "infogen", "anchors", f"{st['preset']}.png")
        a = d if os.path.exists(d) else None
    if a and str(a).startswith(("http://", "https://")): return a, None
    if a and os.path.exists(a): return base64.b64encode(open(a, "rb").read()).decode(), None
    if a: sys.exit(f"style.json anchor {a!r} is neither a URL nor a file")
    if not plan.get("anchor"): sys.exit("no style anchor: set `anchor` in style.json, or add \"anchor\": {\"prompt\": ...} to the plan")
    return None, "style_anchor"

def ref_prompt(group, r, st):
    body = STY.expand(r["prompt"], st)
    era = f" Everything historically accurate for {st['era']}." if st.get("era") else ""
    tail = f" {st['palette_prompt'][0].upper() + st['palette_prompt'][1:]}.{era} No text, no letters, no logos."
    if group == "characters":
        return (f"Draw a new picture {SAME_STYLE}, but of different people: {body}. Full body, front-facing, standing, centred with space around, "
                f"plain white background, no scenery. Do not include anyone from image 1.{tail}")
    if group == "objects":
        return (f"Draw a new picture {SAME_STYLE}. Do not include the person from image 1. The picture shows only {body}, "
                f"plain white background, no people, no scenery.{tail}")
    # A background is drawn onto a blank canvas (image 1) with the anchor as image 2: with the anchor as image 1 the model
    # keeps the anchor's person in the picture, whatever the prompt says.
    return (f"Draw on image 1 a new picture {SAME_STYLE.replace('image 1', 'image 2')}. Image 2 is only a style sample: do not draw the person "
            f"from image 2 or any people. The picture shows only the empty setting: {body}. A wide empty set with room for figures.{tail}")

def blank(aspect):
    """A white canvas of the aspect, as base64: image 1 of a background reference."""
    w, h = (float(x) for x in aspect.split(":")); ratio = w / h; W = (1024 * 1024 * ratio) ** 0.5   # ~1 MP, rounded like the edit worker
    b = io.BytesIO(); Image.new("RGB", (round(W / 32) * 32, round(W / ratio / 32) * 32), "white").save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()

def frame_passes(f, refs, st):
    rs = [refs[r][1] for r in f.get("refs", [])]
    era = f" Everything historically accurate for {st['era']}." if st.get("era") else ""
    look = f" Same flat vector style, flat colours, bold outlines, no gradients, {st['palette_prompt']}.{era} No text, no letters."
    placed = "; ".join(f"{label(r)} from image {i + 2}" for i, r in enumerate(rs[:2]))
    p1 = ("Flat vector infographic scene in the same style as the reference images. Use image 1 as the setting and keep it. "
          + (f"Place {placed}, keeping their exact faces, outfits, proportions and colours unchanged. " if placed else "")
          + f"{STY.expand(f['prompt'], st)}. Every figure is fully inside the frame at a natural size for the setting, no extra people.{look}")
    passes = [{"prompt": p1}]
    if len(rs) == MAX_IMAGES:
        passes.append({"prompt": f"Keep image 1 exactly as it is, including everyone in it. Add {label(rs[2])} from image 2, keeping its exact shape and colours: "
                                 f"{STY.expand(f['add'], st)}.{look}"})
    return passes

def run(plan, st, state, save, pid, only, failed):
    """Queue the anchor (if generated), then references, then frames; each stage waits for the one before. Resumable:
    a finished file is skipped, a queued job is not resubmitted."""
    path = lambda i: f"{ASSETS}/{i}.png"
    refs = refs_by_id(plan)

    def stage(jobs):
        """jobs: {id: (endpoint, input)} -> submit what is not done or queued, wait, download. Returns {id: url} of finished ones."""
        pending = {}
        for i, (ep, inp) in jobs.items():
            if os.path.exists(path(i)) and state.get(i, {}).get("url"): print("skip", i); continue
            if not state.get(i, {}).get("job") or state[i].get("error"):
                state[i] = {"ep": ep, "job": rp.submit(ep, inp), "group": "plan"}; save(); print("queued", i, flush=True)
            pending[i] = (state[i]["ep"], state[i]["job"])
        for i, res in rp.wait(pending).items():
            url = res.get("image_url") if isinstance(res, dict) else None
            if not url: state[i]["error"] = str(res.get("error") if isinstance(res, dict) else res)[:300]; failed.append(i); save(); print("FAIL", i, state[i]["error"], flush=True); continue
            rp.download(url, path(i)); state[i].update(url=url, file=path(i)); state[i].pop("error", None); save(); print("done", i, flush=True)
        return {i: state[i]["url"] for i in jobs if state.get(i, {}).get("url")}

    base = {"project_id": pid}
    anchor, gen_id = anchor_source(plan, st)
    if gen_id:
        anchor = state.get(gen_id, {}).get("url")
        if not anchor:
            # Every reference inherits the anchor's look, so a freshly generated one is looked at before anything is drawn from it.
            if "anchor" not in only: sys.exit("the style anchor is not generated yet: run queue with --only anchor first")
            got = stage({gen_id: ("qwen", {"model": "qwen", "prompt": STY.image_prompt(plan["anchor"]["prompt"], st, "character"), "aspect_ratio": "3:4", **base, "frame_id": gen_id})})
            if got.get(gen_id): print(f"style anchor ready: look at {path(gen_id)}, then queue again for the references", flush=True)
            return

    if "refs" in only:
        jobs = {}
        for g in GROUPS:
            for r in plan.get(g, []):
                ar = r.get("aspect", "3:4" if g == "characters" else "16:9")
                jobs[r["id"]] = ("qedit", {"image_urls": [blank(ar), anchor] if g == "backgrounds" else [anchor], "prompt": ref_prompt(g, r, st),
                                           "aspect_ratio": ar, **base, "frame_id": r["id"]})
        stage(jobs)
        for g in ("characters", "objects"):
            for r in plan.get(g, []):
                if os.path.exists(path(r["id"])) and not os.path.exists(f"{ASSETS}/cutouts/{r['id']}.png"):
                    out, kept = cutout.cut(path(r["id"]), f"{ASSETS}/cutouts/{r['id']}.png"); print("cutout", out, f"kept {kept:.0%}", flush=True)

    if "frames" in only:
        url = lambda i: state.get(i, {}).get("url")
        jobs = {}
        for f in plan.get("frames", []):
            need = ([f["background"]] if f.get("background") else []) + f.get("refs", [])
            missing = [i for i in need if not url(i)]
            if missing: failed.append(f["id"]); print("FAIL", f["id"], "references not ready:", ", ".join(missing), flush=True); continue
            if not f.get("background"):
                jobs[f["id"]] = ("qwen", {"model": "qwen", "prompt": STY.image_prompt(f["prompt"], st), "aspect_ratio": f.get("aspect", "16:9"), **base, "frame_id": f["id"]})
                continue
            passes = frame_passes(f, refs, st)
            if len(passes) > 1: passes[1]["image_urls"] = [url(f["refs"][2])]
            jobs[f["id"]] = ("qedit", {"image_urls": [url(i) for i in need[:MAX_IMAGES]], "passes": passes, "aspect_ratio": f.get("aspect", "16:9"), **base, "frame_id": f["id"]})
        stage(jobs)
