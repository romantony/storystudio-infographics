"""Simple animation of selected frames, within hard caps: Wan2.2 image-to-video (RunPod, LightX2V 4-step), 5 s clips, by
default; LTX 2.3 (ComfyUI Cloud) for a few hero shots, 10 s clips at 720p.

A frame in the visual plan is animated when it has an "animate" block, written in the slots of the team's Wan2.2 prompt
guideline. Keep it SIMPLE: one main motion, at most one small secondary action, a static camera. Complex animation
(several actors, sequences of actions, fast moves, turning to camera) does not come out as intended.

  "animate": {"main": "the silver plane flies slowly from left to right high in the sky, staying small",   one subject, one action, direction, speed
              "secondary": "the pilot on the left waves his raised hand",                                 optional: ONE small action, by position
              "ambient": "grey clouds drift slowly",                                                       optional, subtle
              "still": "the buildings, the fence and the runway",                                          what must not move
              "camera": "static",                     static (default) | slow push-in | slow pan left | slow pan right
              "engine": "wan"}                        wan (default, 5 s) | ltx (a hero shot, 10 s)
Clip lengths are fixed. A 5 s Wan clip on a longer frame holds its last frame; give a 10 s hero shot a scene (or two
consecutive scenes on its frame) of about 10 s.

The scene that shows it is {"type": "clip", "clip": "<frame id>"}. If the clip is missing (over the cap, not approved,
or rejected by the camera check), build shows the still frame instead.

Only an APPROVED frame is animated: a distorted or off-prompt frame makes a distorted clip. Look at the frame, then
  python3 -m infogen approve f12 f30 ...
records each frame with a fingerprint of its image (build/frame_approvals.json). A frame regenerated after approval has
a different fingerprint and must be approved again.

Caps: Wan, at most min(visuals.animated_clips, floor(visuals.animated_max_pct / 100 * frames)) clips per video, retries
included (request.json; defaults 18 and 20 %); LTX hero shots, at most visuals.ltx_clips (default 0), retries included.
validate --plan rejects a plan over either cap; queue never submits past them.
Each clip is checked for camera movement (phase correlation of its first and last frame): a moving camera gets one
retry with the camera forced static and the secondary/ambient motion dropped, then falls back to the still.
Wan clips come back at 832x480, 16 fps, LTX at 1280x720, 25 fps; both are converted to 1920x1080 at 30 fps as
assets/<frame id>.mp4.

python3 -m infogen queue plan/visual_plan.json --only animate"""
import hashlib, json, math, os, re, subprocess, sys, time
import numpy as np
from . import ltx, rp
from .common import ASSETS, mkdirs

APPROVALS = "build/frame_approvals.json"

def fingerprint(path): return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]

def approved(fid):
    """True when the frame's current image is the one that was approved."""
    a = json.load(open(APPROVALS)) if os.path.exists(APPROVALS) else {}
    p = f"{ASSETS}/{fid}.png"
    return os.path.exists(p) and a.get(fid) == fingerprint(p)

def main(cmd, argv):
    """python3 -m infogen approve <frame id> [...]: the frames have been looked at and may be animated."""
    if not argv: sys.exit("usage: python3 -m infogen approve <frame id> [...]   (after looking at each frame)")
    mkdirs("build"); a = json.load(open(APPROVALS)) if os.path.exists(APPROVALS) else {}
    for fid in argv:
        p = f"{ASSETS}/{fid}.png"
        if not os.path.exists(p): sys.exit(f"no frame image {p}")
        a[fid] = fingerprint(p); print("approved", fid, a[fid])
    json.dump(a, open(APPROVALS, "w"), indent=1)

CAMERAS = {"static": "Static camera.", "slow push-in": "Slow push-in.", "slow pan left": "Slow pan left.", "slow pan right": "Slow pan right."}
STYLE_LOCK = "Flat 2D cartoon animation, consistent line art and colors."
DEFAULTS = {"animated_max_pct": 20, "animated_clips": 18}
ENGINES = ("wan", "ltx")
SECS = {"wan": 5, "ltx": 10}   # fixed clip lengths: a short Wan move, a longer LTX hero shot
SEQUENCE = re.compile(r"\b(then|after(wards)?|before|until|finally|next|meanwhile|while)\b", re.I)
MAX_WORDS = 80
LIMITS = {"main": 25, "secondary": 15, "ambient": 10, "still": 20}
CONCURRENCY = int(os.environ.get("INFOGEN_ANIMATE_CONCURRENCY", "4"))
DRIFT = 0.04          # a whole-picture shift of more than 4 % of the frame between the first and last frame = the camera moved

def sentence(s):
    s = s.strip().rstrip(".")
    return s[:1].upper() + s[1:] + "." if s else ""

def prompt(a, simple=False):
    """The Wan prompt in the guideline's slot order. simple=True (the retry): static camera, main motion only."""
    parts = [sentence(a["main"])]
    if not simple:
        if a.get("secondary"): parts.append(sentence(a["secondary"]))
        if a.get("ambient"): parts.append(sentence(a["ambient"]))
    parts.append(sentence(f"{a['still'].strip().rstrip('.')} stay{'s' if not re.search(r'\band\b|,|s$', a['still'].strip()) else ''} still"))
    parts.append(CAMERAS["static"] if simple else CAMERAS[a.get("camera", "static")])
    parts.append(STYLE_LOCK)
    return " ".join(parts)

def check(a, fid):
    """Errors for one animate block: required slots, one camera move, short and simple."""
    err = []
    if not isinstance(a, dict): return [f"{fid}: animate must be an object"]
    for k in a:
        if k == "secs": err.append(f"{fid}: animate.secs: clip lengths are fixed (Wan {SECS['wan']} s, an LTX hero shot {SECS['ltx']} s)")
        elif k not in ("main", "secondary", "ambient", "still", "camera", "engine"): err.append(f"{fid}: animate.{k} is not a slot (main, secondary, ambient, still, camera, engine)")
    for k in ("main", "still"):
        if not str(a.get(k, "")).strip(): err.append(f"{fid}: animate.{k} is required")
    if a.get("camera", "static") not in CAMERAS: err.append(f"{fid}: animate.camera must be one of: {', '.join(CAMERAS)}")
    if a.get("engine", "wan") not in ENGINES: err.append(f"{fid}: animate.engine must be wan or ltx")
    for k, n in LIMITS.items():
        v = str(a.get(k, "") or "")
        if len(v.split()) > n: err.append(f"{fid}: animate.{k} has {len(v.split())} words; keep it to {n} (simple motion comes out, complex motion does not)")
        if SEQUENCE.search(v): err.append(f"{fid}: animate.{k} describes a sequence ({SEQUENCE.search(v).group(0)!r}); animate one action, not several in turn")
        if v.count(".") > 1 or ";" in v: err.append(f"{fid}: animate.{k} must be one sentence")
    if not err and len(prompt(a).split()) > MAX_WORDS: err.append(f"{fid}: the animation prompt is over {MAX_WORDS} words; cut the motion down")
    return err

def engine(f): return f["animate"].get("engine", "wan")

def cap(plan, visuals=None, eng="wan"):
    """How many clips of an engine the request allows for this plan."""
    if eng == "ltx": return int((visuals or {}).get("ltx_clips") or 0)
    v = {**DEFAULTS, **{k: x for k, x in (visuals or {}).items() if k in DEFAULTS and x is not None}}
    return min(int(v["animated_clips"]), math.floor(float(v["animated_max_pct"]) / 100 * len(plan.get("frames", []))))

def drift(video):
    """Whole-picture shift between the first and last frame, as a share of the frame (phase correlation): a camera move
    shifts everything; a subject moving across a still background does not move the correlation peak."""
    def frame(sel):
        raw = subprocess.check_output(["ffmpeg", "-v", "error"] + sel + ["-i", video, "-frames:v", "1", "-vf", "scale=256:144,format=gray", "-f", "rawvideo", "-"])
        return np.frombuffer(raw, np.uint8).reshape(144, 256).astype(float)
    a, b = frame([]), frame(["-sseof", "-0.1"])
    win = np.outer(np.hanning(144), np.hanning(256))
    F = np.fft.fft2((a - a.mean()) * win) * np.conj(np.fft.fft2((b - b.mean()) * win))
    r = np.abs(np.fft.ifft2(F / (np.abs(F) + 1e-9)))
    y, x = np.unravel_index(np.argmax(r), r.shape)
    dy, dx = (y if y < 72 else y - 144) / 144, (x if x < 128 else x - 256) / 256
    return max(abs(dx), abs(dy))

def finish(raw, out):
    """A Wan (832x480, 16 fps) or LTX (1280x720, 25 fps) clip -> 1920x1080 at 30 fps (motion-interpolated, cropped to 16:9)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-an", "-vf",
                    "minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:vsbmc=1,scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out], check=True)

def run(plan, state, save, pid, visuals, failed, warnings):
    """Animate the frames that ask for it, up to the cap, CONCURRENCY at a time. Resumable; attempts are counted in
    state["_animate"] across runs, so a re-run cannot spend past the caps."""
    allowed = {e: cap(plan, visuals, e) for e in ENGINES}
    book = state.setdefault("_animate", {"attempts": 0}); book.setdefault("ltx_attempts", 0)
    book["cap"], book["ltx_cap"] = allowed["wan"], allowed["ltx"]
    spent = lambda eng: "attempts" if eng == "wan" else "ltx_attempts"
    todo = [f for f in plan.get("frames", []) if isinstance(f, dict) and f.get("animate")]
    todo = [f for f in todo if not os.path.exists(f"{ASSETS}/{f['id']}.mp4")]
    mkdirs(ASSETS, "build/anim")
    queue = []
    for f in todo:
        img = state.get(f["id"], {}).get("url")
        if not img: failed.append(f["id"] + ".mp4"); print("FAIL", f["id"], "animation: the frame image is not ready", flush=True); continue
        if not approved(f["id"]):   # nothing is spent on a frame nobody has checked
            warnings.append(f"{f['id']}: not animated, the frame is not approved (look at it, then: python3 -m infogen approve {f['id']})")
            print("UNAPPROVED", f["id"], flush=True); continue
        queue.append((f, img, False))
    running = {}

    def submit(f, img, simple):
        eng = engine(f)
        if book[spent(eng)] >= allowed[eng]:
            what = "clips" if eng == "wan" else "LTX hero shots"
            warnings.append(f"{f['id']}: not animated, the cap of {allowed[eng]} {what} is used up (the still is shown)"); print("CAP", f["id"], eng, flush=True); return
        e = state.setdefault(f["id"] + ".mp4", {}); pr = prompt(f["animate"], simple)
        if eng == "wan":
            job = rp.submit("wan", {"image": img, "prompt": pr, "resolution": "480p", "duration_s": SECS["wan"], "sample_steps": 4, "project_id": pid, "frame_id": f["id"] + "_anim"})
        else:
            job = ltx.submit(f"{ASSETS}/{f['id']}.png", pr, w=1280, h=720, secs=SECS["ltx"], tag=f"{pid}_{f['id']}")
        e.update(ep=eng, job=job, simple=simple, prompt=pr); e.pop("error", None)
        book[spent(eng)] += 1; save(); running[f["id"]] = (f, img, simple); print("queued", f["id"] + ".mp4", eng, "(retry: static, main motion only)" if simple else "", flush=True)

    def collect(e, raw):
        """None while the job runs; else an error, or "" with the clip saved to raw."""
        if e.get("ep") == "ltx":
            s = ltx.poll(e["job"])
            if s == "running": return None
            if s == "failed": return "LTX job failed"
            ltx.fetch(e["job"], raw); return ""
        s = rp.status("wan", e["job"])
        if s.get("status") in ("IN_QUEUE", "IN_PROGRESS"): return None
        out = s.get("output") or {}
        url = out.get("video_url") if isinstance(out, dict) else None
        if s.get("status") != "COMPLETED" or not url: return str(s.get("error") or out)[:300]
        rp.download(url, raw); e.update(url=url, seed=out.get("seed")); return ""

    for f, img, simple in list(queue):   # jobs already queued by an earlier run are picked up, not resubmitted
        e = state.get(f["id"] + ".mp4", {})
        if e.get("job") and not e.get("error") and not e.get("file"): running[f["id"]] = (f, img, e.get("simple", False)); queue.remove((f, img, simple))
    t0 = time.time()
    while (queue or running) and time.time() - t0 < 3600:
        while queue and len(running) < CONCURRENCY:
            submit(*queue.pop(0))
        for fid, (f, img, simple) in list(running.items()):
            e = state[fid + ".mp4"]; raw = f"build/anim/{fid}_raw.mp4"
            try: res = collect(e, raw)
            except Exception: continue
            if res is None: continue
            del running[fid]
            if res:
                e["error"] = res; save(); failed.append(fid + ".mp4"); print("FAIL", fid + ".mp4", e["error"], flush=True); continue
            d = drift(raw); e["drift"] = round(d, 3)
            if d > DRIFT:
                e["error"] = f"camera moved ({d:.0%} of the frame)"; save(); print("DRIFT", fid, e["error"], flush=True)
                if not simple: queue.append((f, img, True))
                else: warnings.append(f"{fid}: not animated, the camera moved in both attempts (the still is shown)")
                continue
            finish(raw, f"{ASSETS}/{fid}.mp4"); e.update(file=f"{ASSETS}/{fid}.mp4"); e.pop("error", None); save(); print("done", fid + ".mp4", f"drift {d:.1%}", flush=True)
        if running: time.sleep(10)
    for fid in running: failed.append(fid + ".mp4"); state[fid + ".mp4"]["error"] = "timeout"
    save()
    made = {e: sum(1 for f in plan.get("frames", []) if isinstance(f, dict) and f.get("animate") and engine(f) == e and os.path.exists(f"{ASSETS}/{f['id']}.mp4")) for e in ENGINES}
    line = f"animation: {made['wan']} clips made, {book['attempts']} of {allowed['wan']} allowed attempts used"
    if allowed["ltx"] or book["ltx_attempts"]: line += f"; {made['ltx']} LTX hero shots made, {book['ltx_attempts']} of {allowed['ltx']} allowed attempts used"
    warnings.append(line); print(line, flush=True)
