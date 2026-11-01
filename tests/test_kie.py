"""infogen/rp.py routing text-to-image, image editing and music to KIE (Nano Banana 2.1, Suno), against a fake KIE API.
Spends nothing. Run: .venv/bin/python tests/test_kie.py"""
import json, os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["KIE_API_KEY"] = "x"
from infogen import kie, rp

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

os.chdir(tempfile.mkdtemp())
sent, records = [], {}
def fake_call(path, body=None, tries=4):
    if body is not None:
        sent.append(body); return {"taskId": f"t{len(sent)}"}
    tid = path.split("taskId=")[1]; return records[tid]
kie.call = fake_call; kie.pace = lambda: None

check("default routes: images, edits and music go to KIE; Wan and transcription stay on RunPod",
      rp.routed("qwen") and rp.routed("qedit") and rp.routed("bgm") and not rp.routed("wan") and not rp.routed("flux"))

j = rp.submit("qwen", {"model": "qwen", "prompt": "a city at night", "aspect_ratio": "9:16", "frame_id": "city"})
check("text-to-image: Nano Banana 2.1 task, KIE job id", j == "kie:t1" and sent[-1]["model"] == "nano-banana-2-1"
      and sent[-1]["input"]["aspect_ratio"] == "9:16" and sent[-1]["input"]["resolution"] == kie.IMAGE_RES and "image_input" not in sent[-1]["input"], sent[-1])
rp.submit("qedit", {"image_urls": ["https://cdn/a.png", "https://cdn/b.png"], "passes": [{"prompt": "place them"}], "aspect_ratio": "16:9"})
check("edit: one pass, reference URLs as image_input", sent[-1]["input"]["image_input"] == ["https://cdn/a.png", "https://cdn/b.png"] and sent[-1]["input"]["prompt"] == "place them", sent[-1])
try: rp.submit("qedit", {"image_urls": [], "passes": [{"prompt": "a"}, {"prompt": "b"}]}); check("edit: two passes refused", False)
except ValueError: check("edit: two passes refused", True)
rp.submit("bgm", {"mode": "bgm", "prompt": "calm documentary piano", "duration_s": 120, "frame_id": "bgm_long"})
m = sent[-1]
check("music: instrumental Suno track in custom mode, style, title and length", m["model"] == "ai-music-api/generate" and m["input"]["instrumental"] is True
      and m["input"]["custom_mode"] is True and m["input"]["style"] == "calm documentary piano" and m["input"]["duration"] == 120
      and m["input"]["title"] == "bgm long" and m["input"]["model"] == kie.MUSIC_MODEL, m)

records["t1"] = {"state": "generating"}
check("status: running", rp.status("qwen", "kie:t1") == {"status": "IN_PROGRESS"})
records["t1"] = {"state": "success", "model": "nano-banana-2-1", "creditsConsumed": 12, "resultJson": json.dumps({"resultUrls": ["https://kie/out.png"]})}
check("status: image done in RunPod's shape", rp.status("qwen", "kie:t1") == {"status": "COMPLETED", "output": {"image_url": "https://kie/out.png"}})
records["t4"] = {"state": "success", "model": "ai-music-api/generate", "creditsConsumed": 10,
                 "response": {"data": [{"id": "a", "audio_url": "https://kie/a.mp3", "duration": 120}, {"id": "b", "audio_url": "https://kie/b.mp3"}]}}
check("status: music done, first track as audio", rp.status("bgm", "kie:t4") == {"status": "COMPLETED", "output": {"audio": "https://kie/a.mp3"}})
records["t2"] = {"state": "fail", "failMsg": "content policy"}
s = rp.status("qedit", "kie:t2")
check("status: failure carries KIE's message", s["status"] == "FAILED" and "content policy" in s["error"], s)
costs = [json.loads(l) for l in open(kie.COSTS)]
check("credits of every finished task recorded once, in USD too", [(c["task"], c["usd"]) for c in costs] == [("t1", 0.06), ("t4", 0.05), ("t2", None)], costs)
rp.status("qwen", "kie:t1")
check("a task polled again is not recorded twice", len(open(kie.COSTS).read().splitlines()) == 3)
check("public URLs pass through unchanged", kie.public_url("https://cdn/x.png") == "https://cdn/x.png")
os.environ.pop("INFOGEN_OUTPUT_BUCKET", None)
try: kie.public_url("aGVsbG8="); check("base64 without a bucket is an error, not a silent drop", False)
except RuntimeError: check("base64 without a bucket is an error, not a silent drop", True)

rp.KIE_ROUTES.clear()
rp.call = lambda url, body=None: {"id": "rp1"} if body else {"status": "COMPLETED", "output": {"image_url": "https://rp/x.png"}}
check("routes empty: back on RunPod", rp.submit("qwen", {"prompt": "p"}) == "rp1")
check("a job queued on RunPod before the switch keeps polling RunPod", rp.status("qwen", "rp1")["output"]["image_url"] == "https://rp/x.png")

print("\nALL PASSED" if not fails else f"\n{fails} FAILED"); sys.exit(1 if fails else 0)
