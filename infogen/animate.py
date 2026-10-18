"""Simple animation of selected frames with Wan2.2 image-to-video (RunPod, LightX2V 4-step), within a hard cap.

A frame in the visual plan is animated when it has an "animate" block, written in the slots of the team's Wan2.2 prompt
guideline. Keep it SIMPLE: one main motion, at most one small secondary action, a static camera. Complex animation
(several actors, sequences of actions, fast moves, turning to camera) does not come out as intended.

  "animate": {"main": "the silver plane flies slowly from left to right high in the sky, staying small",   one subject, one action, direction, speed
              "secondary": "the pilot on the left waves his raised hand",                                 optional: ONE small action, by position
              "ambient": "grey clouds drift slowly",                                                       optional, subtle
              "still": "the buildings, the fence and the runway",                                          what must not move
              "camera": "static",                     static (default) | slow push-in | slow pan left | slow pan right
              "secs": 5}                              3-7 whole seconds (default 5)

The scene that shows it is {"type": "clip", "clip": "<frame id>"}. If the clip is missing (over the cap, not approved,
or rejected by the camera check), build shows the still frame instead.

Only an APPROVED frame is animated: a distorted or off-prompt frame makes a distorted clip. Look at the frame, then
  python3 -m infogen approve f12 f30 ...
records each frame with a fingerprint of its image (build/frame_approvals.json). A frame regenerated after approval has
a different fingerprint and must be approved again.

Cap: at most min(visuals.animated_clips, floor(visuals.animated_max_pct / 100 * frames)) clips per video, retries
included (request.json; defaults 18 and 20 %). validate --plan rejects a plan over the cap; queue never submits past it.
Each clip is checked for camera movement (phase correlation of its first and last frame): a moving camera gets one
retry with the camera forced static and the secondary/ambient motion dropped, then falls back to the still.
Clips come back at 832x480, 16 fps; they are converted to 1920x1080 at 30 fps as assets/<frame id>.mp4.

python3 -m infogen queue plan/visual_plan.json --only animate"""
import hashlib, json, math, os, re, subprocess, sys, time
import numpy as np
from . import rp
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
        if k not in ("main", "secondary", "ambient", "still", "camera", "secs"): err.append(f"{fid}: animate.{k} is not a slot (main, secondary, ambient, still, camera, secs)")
    for k in ("main", "still"):
        if not str(a.get(k, "")).strip(): err.append(f"{fid}: animate.{k} is required")
    if a.get("camera", "static") not in CAMERAS: err.append(f"{fid}: animate.camera must be one of: {', '.join(CAMERAS)}")
    if not (isinstance(a.get("secs", 5), int) and 3 <= a.get("secs", 5) <= 7): err.append(f"{fid}: animate.secs must be a whole number from 3 to 7")
    for k, n in LIMITS.items():
        v = str(a.get(k, "") or "")
        if len(v.split()) > n: err.append(f"{fid}: animate.{k} has {len(v.split())} words; keep it to {n} (simple motion comes out, complex motion does not)")
        if SEQUENCE.search(v): err.append(f"{fid}: animate.{k} describes a sequence ({SEQUENCE.search(v).group(0)!r}); animate one action, not several in turn")
        if v.count(".") > 1 or ";" in v: err.append(f"{fid}: animate.{k} must be one sentence")
    if not err and len(prompt(a).split()) > MAX_WORDS: err.append(f"{fid}: the animation prompt is over {MAX_WORDS} words; cut the motion down")
    return err

def cap(plan, visuals=None):
    """How many clips the request allows for this plan."""
    v = {**DEFAULTS, **{k: x for k, x in (visuals or {}).items() if k in DEFAULTS and x is not None}}
    if (visuals or {}).get("animated_clips") is None and (visuals or {}).get("ltx_clips"): v["animated_clips"] = visuals["ltx_clips"]   # older requests
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
    """832x480 at 16 fps -> 1920x1080 at 30 fps (motion-interpolated, cropped to 16:9)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-an", "-vf",
                    "minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:vsbmc=1,scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out], check=True)

def run(plan, state, save, pid, visuals, failed, warnings):
    """Animate the frames that ask for it, up to the cap, CONCURRENCY at a time. Resumable; attempts are counted in
    state["_animate"]["attempts"] across runs, so a re-run cannot spend past the cap."""
    allowed = cap(plan, visuals)
    book = state.setdefault("_animate", {"attempts": 0}); book["cap"] = allowed
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
        if book["attempts"] >= allowed:
            warnings.append(f"{f['id']}: not animated, the cap of {allowed} clips is used up (the still is shown)"); print("CAP", f["id"], flush=True); return
        e = state.setdefault(f["id"] + ".mp4", {})
        inp = {"image": img, "prompt": prompt(f["animate"], simple), "resolution": "480p", "duration_s": int(f["animate"].get("secs", 5)), "sample_steps": 4,
               "project_id": pid, "frame_id": f["id"] + "_anim"}
        e.update(ep="wan", job=rp.submit("wan", inp), simple=simple, prompt=inp["prompt"]); e.pop("error", None)
        book["attempts"] += 1; save(); running[f["id"]] = (f, img, simple); print("queued", f["id"] + ".mp4", "(retry: static, main motion only)" if simple else "", flush=True)

    for f, img, simple in list(queue):   # jobs already queued by an earlier run are picked up, not resubmitted
        e = state.get(f["id"] + ".mp4", {})
        if e.get("job") and not e.get("error") and not e.get("file"): running[f["id"]] = (f, img, e.get("simple", False)); queue.remove((f, img, simple))
    t0 = time.time()
    while (queue or running) and time.time() - t0 < 3600:
        while queue and len(running) < CONCURRENCY:
            submit(*queue.pop(0))
        for fid, (f, img, simple) in list(running.items()):
            e = state[fid + ".mp4"]
            try: s = rp.status("wan", e["job"])
            except Exception: continue
            if s.get("status") in ("IN_QUEUE", "IN_PROGRESS"): continue
            del running[fid]
            out = s.get("output") or {}
            url = out.get("video_url") if isinstance(out, dict) else None
            if s.get("status") != "COMPLETED" or not url:
                e["error"] = str(s.get("error") or out)[:300]; save(); failed.append(fid + ".mp4"); print("FAIL", fid + ".mp4", e["error"], flush=True); continue
            raw = f"build/anim/{fid}_raw.mp4"; rp.download(url, raw); e.update(url=url, seed=out.get("seed"))
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
    used = book["attempts"]; made = sum(1 for f in plan.get("frames", []) if isinstance(f, dict) and f.get("animate") and os.path.exists(f"{ASSETS}/{f['id']}.mp4"))
    warnings.append(f"animation: {made} clips made, {used} of {allowed} allowed attempts used")
    print(f"animation: {made} clips, {used}/{allowed} attempts", flush=True)
