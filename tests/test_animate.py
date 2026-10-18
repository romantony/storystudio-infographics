"""Animation of plan frames (infogen/animate.py): simple-motion checks, the cap, the camera check, conversion, and the
queue stage against a fake RunPod. Spends nothing (needs ffmpeg). Run: .venv/bin/python tests/test_animate.py"""
import json, os, random, shutil, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PIL import Image, ImageDraw
from infogen import animate as AN, build, rp, visual_plan as VP

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

GOOD = {"main": "the silver plane flies slowly from left to right high in the sky, staying small", "secondary": "the pilot on the left waves his raised hand",
        "ambient": "grey clouds drift slowly", "still": "the buildings, the fence and the runway"}

# ---- prompt and simplicity checks ----
p = AN.prompt(GOOD)
check("prompt: slots in guideline order, static camera, style lock last",
      p == "The silver plane flies slowly from left to right high in the sky, staying small. The pilot on the left waves his raised hand. Grey clouds drift slowly. "
           "The buildings, the fence and the runway stay still. Static camera. Flat 2D cartoon animation, consistent line art and colors.", p)
check("prompt: one still thing -> 'stays still'", "The runway stays still." in AN.prompt({**GOOD, "still": "the runway"}))
s = AN.prompt({**GOOD, "camera": "slow pan left"}, simple=True)
check("retry prompt: main motion only, camera forced static", "pilot" not in s and "clouds" not in s and "Static camera." in s and "pan" not in s, s)
check("prompt within the guideline's 40-80 words", 20 <= len(p.split()) <= 80, len(p.split()))
check("a simple block passes", AN.check(GOOD, "f1") == [], AN.check(GOOD, "f1"))
for name, block, needle in [
        ("sequence word", {**GOOD, "main": "the plane lands then taxis to the hangar"}, "sequence"),
        ("too long", {**GOOD, "main": " ".join(["slowly"] * 26)}, "keep it to 25"),
        ("two sentences", {**GOOD, "secondary": "the pilot waves. the girl points."}, "one sentence"),
        ("bad camera", {**GOOD, "camera": "orbit"}, "camera must be one of"),
        ("secs out of range", {**GOOD, "secs": 8}, "3 to 7"),
        ("missing still", {k: v for k, v in GOOD.items() if k != "still"}, "animate.still is required"),
        ("unknown slot", {**GOOD, "dialogue": "hello"}, "not a slot")]:
    check(f"check rejects: {name}", any(needle in e for e in AN.check(block, "f1")), AN.check(block, "f1"))

# ---- cap ----
plan = lambda n, k: {"frames": [{"id": f"f{i}", "prompt": "x", **({"animate": GOOD} if i < k else {})} for i in range(n)]}
check("cap: 20 % of 45 frames = 9", AN.cap(plan(45, 0), None) == 9, AN.cap(plan(45, 0), None))
check("cap: animated_clips is the ceiling", AN.cap(plan(100, 0), {"animated_max_pct": 40, "animated_clips": 18}) == 18)
check("cap: 0 % means no animation", AN.cap(plan(45, 0), {"animated_max_pct": 0}) == 0)
check("cap: an older request's ltx_clips counts as the ceiling", AN.cap(plan(45, 0), {"ltx_clips": 3}) == 3)
err, _ = VP.check(plan(10, 3), {"illustrations": 24})
check("plan check: 3 animated of 10 frames at 20 % is over the cap of 2", any("3 animated, the cap allows 2" in e for e in err), err)
check("plan check: 2 animated of 10 is fine", not any("animated" in e for e in VP.check(plan(10, 2), {"illustrations": 24})[0]))
bad = plan(10, 1); bad["frames"][0]["animate"] = {**GOOD, "main": "the plane lands and then taxis"}
check("plan check includes the simplicity rules", any("sequence" in e for e in VP.check(bad, {"illustrations": 24})[0]))
w = VP.check_scenes(plan(3, 1), [{"type": "clip", "clip": "f0"}, {"type": "clip", "clip": "f1"}, {"type": "illustration", "image": "f2"}])
check("scene check: a clip of a frame with no animate is reported", any("clip 'f1' is a frame with no \"animate\"" in x for x in w) and not any("'f0'" in x for x in w), w)

# ---- camera check and conversion, on synthetic clips ----
tmp = tempfile.mkdtemp(); os.chdir(tmp)
random.seed(1)
art = Image.new("RGB", (1300, 480), (220, 215, 190)); d = ImageDraw.Draw(art)
for _ in range(120):   # flat shapes with outlines, like the art
    x, y = random.randrange(1250), random.randrange(430); d.rectangle((x, y, x + random.randrange(20, 90), y + random.randrange(20, 90)), fill=tuple(random.randrange(60, 200) for _ in range(3)), outline="black", width=3)
art.save("art.png"); art.crop((0, 0, 832, 480)).save("still.png")
ff = lambda *a: subprocess.run(["ffmpeg", "-v", "error", "-y", *a], check=True)
ff("-loop", "1", "-i", "still.png", "-f", "lavfi", "-i", "color=white:s=80x50", "-filter_complex", "[0][1]overlay=x='60+t*120':y=60", "-t", "5", "-r", "16", "-pix_fmt", "yuv420p", "subject.mp4")
ff("-loop", "1", "-i", "art.png", "-vf", "crop=832:480:'t*80':0", "-t", "5", "-r", "16", "-pix_fmt", "yuv420p", "pan.mp4")
ds, dp = AN.drift("subject.mp4"), AN.drift("pan.mp4")
check(f"camera check: a subject moving over a still background passes ({ds:.1%})", ds <= AN.DRIFT, ds)
check(f"camera check: a panning picture fails ({dp:.1%})", dp > AN.DRIFT, dp)
AN.finish("subject.mp4", "out.mp4")
info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate:format=duration", "-of", "json", "out.mp4"]))
check("conversion: 1920x1080 at 30 fps, same length", (info["streams"][0]["width"], info["streams"][0]["height"], info["streams"][0]["r_frame_rate"]) == (1920, 1080, "30/1")
      and abs(float(info["format"]["duration"]) - 5) < 0.2, info)

# ---- queue stage against a fake RunPod ----
os.makedirs("assets"); os.makedirs("build")
P = plan(10, 4)            # 4 animated frames, but the cap for 10 frames at 20 % is 2: a plan edited after validation
P["frames"][3]["animate"] = {**GOOD, "camera": "slow pan left"}
state = {f["id"]: {"url": f"https://cdn/{f['id']}.png"} for f in P["frames"]}
save = lambda: json.dump(state, open("build/queue_state.json", "w"))
submits, inflight, peak = [], [0], [0]
def submit(ep, inp):
    submits.append((ep, inp)); inflight[0] += 1; peak[0] = max(peak[0], inflight[0]); return f"j{len(submits)}"
pan_for = set()
def status(ep, jid):
    inflight[0] -= 1; inp = submits[int(jid[1:]) - 1][1]
    return {"status": "COMPLETED", "output": {"video_url": f"https://cdn/{jid}.mp4", "seed": 7, "frame": inp["frame_id"]}}
def download(url, path):
    jid = url.rsplit("/", 1)[1][:-4]; fid = submits[int(jid[1:]) - 1][1]["frame_id"].replace("_anim", "")
    shutil.copy("pan.mp4" if fid in pan_for else "subject.mp4", path)
rp.submit, rp.status, rp.download = submit, status, download
AN.CONCURRENCY = 1
def frames(n):
    for i in range(n): Image.new("RGB", (64, 36), (i, 0, 0)).save(f"assets/f{i}.png")

# approval gate: nothing is spent on a frame nobody has checked
frames(10); failed, warns = [], []
AN.run(P, state, save, "t", {"animated_max_pct": 20}, failed, warns)
check("gate: unapproved frames are not animated, nothing spent", submits == [] and sum("not approved" in w for w in warns) == 4, (submits, warns))
try: AN.main("approve", ["f99"]); code = 0
except SystemExit as x: code = str(x.code)
check("approve: refuses a frame with no image", "no frame image" in code, code)
AN.main("approve", [f"f{i}" for i in range(10)])
Image.new("RGB", (64, 36), (9, 9, 9)).save("assets/f1.png")   # f1 regenerated after approval
check("gate: a frame regenerated after approval is no longer approved", AN.approved("f0") and not AN.approved("f1"))
AN.main("approve", ["f1"])
failed, warns = [], []
AN.run(P, state, save, "t", {"animated_max_pct": 20}, failed, warns)
check("queue: never past the cap (2 of 4 animated frames submitted)", len(submits) == 2 and all(e == "wan" for e, _ in submits), [i["frame_id"] for _, i in submits])
check("queue: the rest reported as over the cap", sum("cap of 2 clips is used up" in w for w in warns) == 2, warns)
check("queue: concurrency limit respected", peak[0] <= 1, peak[0])
check("queue: clips land as assets/<frame>.mp4 at 1080p", os.path.exists("assets/f0.mp4") and os.path.exists("assets/f1.mp4") and not os.path.exists("assets/f2.mp4"))
i0 = submits[0][1]
check("queue: Wan request per the endpoint (480p, whole seconds, 4 steps, frame image)",
      (i0["resolution"], i0["duration_s"], i0["sample_steps"], i0["image"]) == ("480p", 5, 4, "https://cdn/f0.png") and i0["prompt"] == AN.prompt(GOOD), i0)
check("queue: attempts and cap recorded", state["_animate"] == {"attempts": 2, "cap": 2}, state["_animate"])

before = len(submits); AN.run(P, state, save, "t", {"animated_max_pct": 20}, [], [])
check("re-run: nothing resubmitted, still capped", len(submits) == before, len(submits) - before)

# camera moved -> one retry with the simple prompt -> then the still
shutil.rmtree("assets"); os.makedirs("assets"); frames(10); AN.main("approve", [f"f{i}" for i in range(10)])
state = {f["id"]: {"url": f"https://cdn/{f['id']}.png"} for f in P["frames"]}; submits.clear(); pan_for.clear(); pan_for.add("f0")
warns = []
AN.run(plan(10, 1), state, save, "t", {"animated_max_pct": 30}, [], warns)
check("drift: retried once with the simple prompt", len(submits) == 2 and "Grey clouds" not in submits[1][1]["prompt"] and "Static camera." in submits[1][1]["prompt"], [i["prompt"] for _, i in submits])
check("drift twice: no clip, reported, attempts counted", not os.path.exists("assets/f0.mp4") and any("camera moved in both attempts" in w for w in warns) and state["_animate"]["attempts"] == 2, (warns, state["_animate"]))

# ---- frames to be animated are composed for it ----
refs = {"pilot": ("characters", {"id": "pilot"})}
st0 = {"palette_prompt": "muted colours", "cast": {}}
fa = VP.frame_passes({"id": "f", "background": "bg", "refs": ["pilot"], "prompt": "the pilot waves", "animate": GOOD}, refs, st0)[0]["prompt"]
fs = VP.frame_passes({"id": "f", "background": "bg", "refs": ["pilot"], "prompt": "the pilot waves"}, refs, st0)[0]["prompt"]
check("frame prompt: animated frames ask for large, separated figures and space ahead", "Composed for animation" in fa and "open space in the direction" in fa and "Composed for animation" not in fs, fa)

# ---- build falls back to the still when the clip is missing ----
Image.new("RGB", (1376, 768), "white").save("assets/f0.png")
st = {"palette": {}, "logo": None}
p = build.scene_props({"n": 3, "type": "clip", "clip": "f0", "narration": "x"}, 1920, 1080, 5.0, [], "whip", st, "scene 3")
check("build: clip with no video shows the still frame", p["type"] == "illustration" and p["image"].endswith("assets/f0.png"), p)
shutil.copy("out.mp4", "assets/f0.mp4")
p = build.scene_props({"n": 3, "type": "clip", "clip": "f0", "narration": "x"}, 1920, 1080, 5.0, [], "whip", st, "scene 3")
check("build: clip with a video stays a clip", p["type"] == "clip" and p["src"].endswith("assets/f0.mp4") and abs(p["clip_seconds"] - 5) < 0.2, p)

print("ALL OK" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
