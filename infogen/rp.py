"""RunPod serverless: queue with /run, poll /status. Endpoints can be cold, so always queue and wait.

Text-to-image ("qwen"), image editing ("qedit") and music ("bgm") go to KIE instead (Nano Banana 2.1 and Suno, infogen/kie.py)
when their names are in INFOGEN_KIE_ROUTES (default "qwen,qedit,bgm"; empty = everything on RunPod). The callers don't change:
a KIE job id is "kie:<taskId>" and its status comes back in RunPod's shape, {"status": ..., "output": {"image_url"|"audio": url}}.
Job ids already queued on RunPod keep polling RunPod."""
import json, os, time, urllib.request
from .common import key
EP = {"bgm": os.environ.get("RUNPOD_EP_BGM", "6apg6j7suzuezw"), "mm": os.environ.get("RUNPOD_EP_MMAUDIO", "nzkcsef9t2iv7s"),
      "qwen": os.environ.get("RUNPOD_EP_QWEN", "e165se4r3eo5hp"), "qedit": os.environ.get("RUNPOD_EP_QWEN_EDIT", "oxwx8o879qwtla"),
      "wan": os.environ.get("RUNPOD_EP_WAN", "nd7wloyvj09xwy"),
      "flux": os.environ.get("RUNPOD_EP_FLUX", "rnqxi6c0mlq517"),
      "itk": os.environ.get("RUNPOD_EP_INFINITETALK", "infinitetalk")}
def call(url, body=None):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None,
                                 {"Authorization": f"Bearer {key('RUNPOD_API_KEY')}", "Content-Type": "application/json", "User-Agent": "curl/8.5.0"})
    return json.load(urllib.request.urlopen(req, timeout=120))
KIE_ROUTES = {x.strip() for x in os.environ.get("INFOGEN_KIE_ROUTES", "qwen,qedit,bgm").split(",") if x.strip()}
def routed(ep): return ep in KIE_ROUTES

def kie_submit(ep, inp):
    from . import kie
    if ep == "bgm": return kie.music(inp["prompt"], inp.get("duration_s"), title=str(inp.get("frame_id") or "Background music").replace("_", " "))
    passes = inp.get("passes") or [{"prompt": inp.get("prompt", "")}]
    if len(passes) > 1: raise ValueError("a KIE edit is one pass: build the frame with visual_plan.frame_passes(..., single=True)")
    return kie.submit(passes[0]["prompt"], inp.get("image_urls") or (), aspect=inp.get("aspect_ratio", "16:9"), resolution=kie.IMAGE_RES)

def kie_status(ep, task):
    from . import kie
    st, urls, msg = kie.status(task)
    if st == "success":
        if not urls: return {"status": "FAILED", "error": "KIE returned no result URL"}
        return {"status": "COMPLETED", "output": {"audio": urls[0]} if ep == "bgm" else {"image_url": urls[0]}}
    if st == "fail": return {"status": "FAILED", "error": f"KIE: {msg}"}
    return {"status": "IN_PROGRESS"}

def submit(ep, inp):
    if routed(ep): return "kie:" + kie_submit(ep, inp)
    return call(f"https://api.runpod.ai/v2/{EP.get(ep, ep)}/run", {"input": inp})["id"]
def status(ep, jid):
    if str(jid).startswith("kie:"): return kie_status(ep, jid[4:])
    return call(f"https://api.runpod.ai/v2/{EP.get(ep, ep)}/status/{jid}")
def wait(jobs, every=5, limit=3600, on_done=None):
    """jobs: {name: (ep, id)} -> {name: output}. Failed or timed-out jobs map to {'error': ...}."""
    out, t0 = {}, time.time()
    while len(out) < len(jobs) and time.time() - t0 < limit:
        for n, (ep, jid) in jobs.items():
            if n in out: continue
            try: s = status(ep, jid)
            except Exception as e: s = {"status": "UNKNOWN", "error": str(e)}
            if s["status"] == "COMPLETED": out[n] = s.get("output") or {}
            elif s["status"] in ("FAILED", "CANCELLED", "TIMED_OUT"): out[n] = {"error": str(s.get("error"))[:300]}
            if n in out and on_done: on_done(n, out[n])
        if len(out) < len(jobs): time.sleep(every)
    for n in jobs:
        out.setdefault(n, {"error": "timeout waiting for RunPod"})
    return out
def download(url, path):
    open(path, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8.5.0"}), timeout=300).read())
