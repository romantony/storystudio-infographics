"""The visual plan (infogen/visual_plan.py): checks, and the anchor -> references -> frames requests queue sends, against a
fake RunPod. Spends nothing. Run: .venv/bin/python tests/test_plan.py"""
import base64, io, json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PIL import Image, ImageDraw
from infogen import rp, queue_assets, visual_plan as VP

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

PLAN = {"project_id": "t",
        "characters": [{"id": "pilot", "label": "the pilot", "prompt": "{pilot}, smiling"}, {"id": "kids", "label": "the children", "prompt": "three children", "aspect": "16:9"}],
        "objects": [{"id": "c54", "label": "the transport plane", "prompt": "a C-54 in side view"}],
        "backgrounds": [{"id": "field", "prompt": "an empty 1948 airfield"}],
        "frames": [{"id": "f1", "background": "field", "refs": ["pilot", "kids", "c54"], "prompt": "the pilot waves on the left; the children watch on the right",
                    "add": "the plane flies low in the upper sky"},
                   {"id": "f2", "background": "field", "refs": ["pilot"], "prompt": "the pilot walks to the plane"},
                   {"id": "f3", "prompt": "a close-up of a ration card"}]}

# ---- check ----
err, warn = VP.check(PLAN, {"characters": 6, "objects": 8, "backgrounds": 8, "illustrations": 24})
check("valid plan: no errors", err == [], err)
bad = json.loads(json.dumps(PLAN))
bad["frames"] += [{"id": "pilot", "prompt": "x"},                                                        # duplicate id
                  {"id": "f4", "background": "field", "refs": ["pilot", "nobody", "field"], "prompt": "x"},  # unknown ref, a background as ref, 3 refs without add
                  {"id": "f5", "refs": ["pilot"], "prompt": "x"},                                         # refs without background
                  {"id": "f6", "background": "moon", "prompt": "x"},                                      # unknown background
                  {"id": "f7", "background": "field", "refs": ["pilot", "kids", "c54", "pilot"], "prompt": "x", "add": "y"}]   # 4 refs
err, _ = VP.check(bad, {"illustrations": 5})
for name, needle in [("duplicate id", "used more than once"), ("unknown ref", "'nobody' is not a character"), ("background as ref", "'field' is not a character"),
                     ("third ref needs add", "say how in \"add\""), ("refs need a background", "refs need a background"), ("unknown background", "'moon' is not in backgrounds"),
                     ("at most 3 refs", "at most 3 refs"), ("frame budget", "frames: 8 planned, the request allows 5")]:
    check(f"check catches: {name}", any(needle in e for e in err), err)
check("unused reference is a warning", any("c54" in w for w in VP.check({**PLAN, "frames": PLAN["frames"][1:]})[1]))

sc = lambda imgs: [{"type": "illustration", "image": i} for i in imgs]
check("scene use: fine", VP.check_scenes(PLAN, sc(["f1", "f1", "f2", "f3"])) == [], VP.check_scenes(PLAN, sc(["f1", "f1", "f2", "f3"])))
w = VP.check_scenes(PLAN, sc(["f1", "f2", "f1", "f2", "f2"]))
check("scene use: reuse after other scenes, >2 scenes, unused frame", any("f1: used again" in x for x in w) and any("f2: carries 3" in x for x in w) and any("f3: no illustration" in x for x in w), w)

# ---- run, against a fake RunPod ----
tmp = tempfile.mkdtemp(); os.chdir(tmp)
json.dump({"era": "Berlin, 1948", "cast": {"pilot": "a US transport pilot in a leather jacket"}}, open("style.json", "w"))
json.dump(PLAN, open("plan.json", "w"))
calls = []
def png():
    im = Image.new("RGB", (300, 400), "white"); ImageDraw.Draw(im).rectangle((100, 80, 200, 360), fill=(90, 60, 40), outline="black", width=4)
    b = io.BytesIO(); im.save(b, "PNG"); return b.getvalue()
def submit(ep, inp): calls.append((ep, inp)); return f"job{len(calls)}"
rp.submit = submit
rp.wait = lambda jobs, **kw: {n: {"image_url": f"https://cdn/{jid}.png"} for n, (ep, jid) in jobs.items()}
rp.download = lambda url, path: open(path, "wb").write(png())
q = lambda *only: queue_assets.main("queue", ["plan.json"] + (["--only", ",".join(only)] if only else []))

q("refs")
check("refs: one edit job per reference, nothing else", sorted(i["frame_id"] for _, i in calls) == ["c54", "field", "kids", "pilot"] and all(e == "qedit" for e, _ in calls), calls)
anchor_b64 = base64.b64encode(open(os.path.join(ROOT, "infogen", "anchors", "flat_vector.png"), "rb").read()).decode()
by = {i["frame_id"]: i for _, i in calls}
check("refs: characters and objects drawn from the preset's default anchor (base64) as image 1",
      all(by[i]["image_urls"] == [anchor_b64] for i in ("pilot", "kids", "c54")), [by[i]["image_urls"][:1] == [anchor_b64] for i in ("pilot", "kids", "c54")])
bg_imgs = by["field"]["image_urls"]
bg1 = Image.open(io.BytesIO(base64.b64decode(bg_imgs[0])))
check("refs: a background is drawn on a blank 16:9 canvas, anchor as image 2",
      len(bg_imgs) == 2 and bg_imgs[1] == anchor_b64 and bg1.getextrema() == ((255, 255), (255, 255), (255, 255)) and bg1.size == (1376, 768)
      and by["field"]["prompt"].startswith("Draw on image 1") and "style as image 2" in by["field"]["prompt"], (len(bg_imgs), bg1.size, by["field"]["prompt"][:120]))
check("refs: character prompt draws a new person in the anchor's style, cast and era expanded",
      by["pilot"]["prompt"].startswith("Draw a new picture in exactly the same flat vector style as image 1") and "leather jacket" in by["pilot"]["prompt"]
      and "historically accurate for Berlin, 1948" in by["pilot"]["prompt"] and "Do not include anyone from image 1" in by["pilot"]["prompt"], by["pilot"]["prompt"])
check("refs: object and background prompts", "shows only a C-54" in by["c54"]["prompt"] and "empty setting: an empty 1948 airfield" in by["field"]["prompt"], (by["c54"]["prompt"], by["field"]["prompt"]))
check("refs: aspect per kind, plan override", (by["pilot"]["aspect_ratio"], by["kids"]["aspect_ratio"], by["c54"]["aspect_ratio"], by["field"]["aspect_ratio"]) == ("3:4", "16:9", "16:9", "16:9"))
check("refs: characters and objects cut out, backgrounds not", all(os.path.exists(f"assets/cutouts/{i}.png") for i in ("pilot", "kids", "c54")) and not os.path.exists("assets/cutouts/field.png"))

calls.clear(); q("refs")
check("refs again: nothing resubmitted", calls == [], calls)

calls.clear(); q("frames")
by = {i["frame_id"]: (e, i) for e, i in calls}
check("frames: 3 jobs", sorted(by) == ["f1", "f2", "f3"], sorted(by))
st = json.load(open("build/queue_state.json")); url = lambda i: st[i]["url"]
e, f1 = by["f1"]
check("f1: background then first two refs as image 1-3", e == "qedit" and f1["image_urls"] == [url("field"), url("pilot"), url("kids")], f1.get("image_urls"))
check("f1: third ref added in pass 2 with its own image", len(f1["passes"]) == 2 and f1["passes"][1]["image_urls"] == [url("c54")] and "Add the transport plane from image 2" in f1["passes"][1]["prompt"]
      and "the plane flies low" in f1["passes"][1]["prompt"], f1["passes"])
check("f1: pass 1 names the refs by label and image number", "Place the pilot from image 2; the children from image 3" in f1["passes"][0]["prompt"] and f1["aspect_ratio"] == "16:9", f1["passes"][0]["prompt"])
e, f2 = by["f2"]
check("f2: one ref, one pass", f2["image_urls"] == [url("field"), url("pilot")] and len(f2["passes"]) == 1, f2)
e, f3 = by["f3"]
check("f3: no background -> text-to-image", e == "qwen" and f3["model"] == "qwen" and "close-up of a ration card" in f3["prompt"], (e, f3))

# a frame whose references failed is not submitted
os.remove("assets/kids.png"); st["kids"]["error"] = "boom"; st["kids"].pop("url"); json.dump(st, open("build/queue_state.json", "w"))
os.remove("assets/f1.png"); st["f1"].pop("url"); json.dump(st, open("build/queue_state.json", "w"))
calls.clear()
try: q("frames"); code = 0
except SystemExit as x: code = x.code
check("frames with a missing ref: not submitted, run fails", [i["frame_id"] for _, i in calls] == [] and code == 1, (calls, code))

# generated anchor: no anchor image for the preset -> the plan's anchor prompt; first run stops after it
tmp2 = tempfile.mkdtemp(); os.chdir(tmp2)
json.dump({"preset": "noir_vector", "cast": {"pilot": "a US transport pilot in a leather jacket"}}, open("style.json", "w"))
json.dump({**PLAN, "anchor": {"prompt": "a man in a trench coat"}}, open("plan.json", "w"))
calls.clear(); q()
check("generated anchor: first run makes only the anchor", [(e, i["frame_id"]) for e, i in calls] == [("qwen", "style_anchor")], calls)
calls.clear(); q("refs")
check("generated anchor: refs are drawn from its URL", len(calls) == 4 and all(i["image_urls"][-1] == "https://cdn/job1.png" for _, i in calls), calls)
json.dump(PLAN, open("plan.json", "w")); calls.clear()
try: q("refs"); code = 0
except SystemExit as x: code = str(x.code)
check("no anchor anywhere: clear error", "no style anchor" in str(code), code)

# ---- validate --plan end to end ----
tmp3 = tempfile.mkdtemp(); os.chdir(tmp3); os.makedirs("script"); os.makedirs("plan")
json.dump({"title": "t", "scenes": [{"n": 1, "type": "illustration", "image": "f1", "narration": "The pilot waves at the children by the fence."},
                                    {"n": 2, "type": "illustration", "image": "f2", "narration": "Then he walks back to his plane."}]}, open("script/script.json", "w"))
json.dump(PLAN, open("plan/visual_plan.json", "w"))
json.dump({"visuals": {"illustrations": 24, "characters": 6, "objects": 8, "backgrounds": 8}}, open("request.json", "w"))
env = {**os.environ, "PYTHONPATH": ROOT}
r = subprocess.run([sys.executable, "-m", "infogen", "validate", "--plan", "plan/visual_plan.json"], capture_output=True, text=True, env=env)
out = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
check("validate --plan: frame ids count as planned assets, passes", r.returncode == 0 and out.get("errors") == [], (r.returncode, r.stdout[-600:], r.stderr[-600:]))
check("validate --plan: unused frame reported", any("f3: no illustration scene" in w for w in out.get("warnings", [])), out.get("warnings"))
json.dump({"visuals": {"illustrations": 2}}, open("request.json", "w"))
r = subprocess.run([sys.executable, "-m", "infogen", "validate", "--plan", "plan/visual_plan.json"], capture_output=True, text=True, env=env)
check("validate --plan: over budget fails", r.returncode == 1 and "visuals.illustrations" in r.stdout, r.stdout[-400:])

print("ALL OK" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
