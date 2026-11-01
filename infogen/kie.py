"""KIE (api.kie.ai): images with Nano Banana 2.1 (text-to-image and editing with reference images) and music with Suno.
Create a task, poll it, download the result. Key: KIE_API_KEY.
Reference images must be public URLs (up to 10); base64 images are uploaded to the output bucket first (public_url).
Env: KIE_BASE (https://api.kie.ai), KIE_MODEL (nano-banana-2-1), KIE_IMAGE_RESOLUTION (2K) for frames and references,
     KIE_MUSIC_MODEL (V6). Every finished task's credits are appended to build/kie_costs.jsonl (1 credit = $0.005)."""
import base64, hashlib, json, os, time, urllib.error, urllib.parse, urllib.request
from .common import key

BASE = os.environ.get("KIE_BASE", "https://api.kie.ai").rstrip("/")
MODEL = os.environ.get("KIE_MODEL", "nano-banana-2-1")
ASPECTS = ("1:1", "2:3", "3:2", "1:4", "4:1", "3:4", "4:3", "4:5", "5:4", "1:8", "8:1", "9:16", "16:9", "21:9", "auto")
RETRY = (429, 500, 502, 503, 504)
MUSIC_MODEL = os.environ.get("KIE_MUSIC_MODEL", "V6")
IMAGE_RES = os.environ.get("KIE_IMAGE_RESOLUTION", "2K")
COSTS = "build/kie_costs.jsonl"
USD_PER_CREDIT = 0.005

def available(): return bool(os.environ.get("KIE_API_KEY"))

def call(path, body=None, tries=4):
    for n in range(tries):
        req = urllib.request.Request(BASE + path, json.dumps(body).encode() if body is not None else None,
                                     {"Authorization": f"Bearer {key('KIE_API_KEY')}", "Content-Type": "application/json", "User-Agent": "infogen/1.0"})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code in RETRY and n < tries - 1: time.sleep(5 * (n + 1)); continue
            raise RuntimeError(f"KIE {path}: HTTP {e.code} {e.read()[:300]!r}")
        if r.get("code") in RETRY and n < tries - 1: time.sleep(5 * (n + 1)); continue
        if r.get("code") != 200: raise RuntimeError(f"KIE {path}: {r.get('code')} {r.get('msg')}")
        return r["data"]
    raise RuntimeError(f"KIE {path}: no answer")

_last = [0.0]
def pace():
    """KIE allows 20 new tasks per 10 s per account: keep new tasks at least 0.6 s apart."""
    d = 0.6 - (time.time() - _last[0])
    if d > 0: time.sleep(d)
    _last[0] = time.time()

def submit(prompt, image_urls=(), aspect="16:9", resolution="2K", fmt="png"):
    """A new image task; returns its taskId."""
    pace()
    if aspect not in ASPECTS: raise ValueError(f"aspect {aspect!r} is not one of {ASPECTS}")
    inp = {"prompt": prompt[:20000], "aspect_ratio": aspect, "resolution": resolution, "output_format": fmt}
    if image_urls: inp["image_input"] = [public_url(u) for u in list(image_urls)[:10]]
    return call("/api/v1/jobs/createTask", {"model": MODEL, "input": inp})["taskId"]

def music(style, seconds=None, title="Background music"):
    """A new instrumental Suno track (custom mode: the style prompt, a title, an optional length of 10-360 s); returns its taskId."""
    inp = {"custom_mode": True, "instrumental": True, "model": MUSIC_MODEL, "title": title[:80], "style": style[:1000]}
    if seconds: inp["duration"] = int(min(max(seconds, 10), 360))
    pace()
    return call("/api/v1/jobs/createTask", {"model": "ai-music-api/generate", "input": inp})["taskId"]

def result_urls(d):
    """Output URLs of a finished task: resultUrls for images, the tracks' audio_url for music."""
    r = d.get("response") or json.loads(d.get("resultJson") or "{}") or {}
    urls = list(r.get("resultUrls") or [])
    for t in r.get("data") or []:
        if isinstance(t, dict) and (t.get("audio_url") or t.get("audioUrl")): urls.append(t.get("audio_url") or t.get("audioUrl"))
    return urls

def status(task):
    """('waiting' | 'success' | 'fail', result URLs, failure message). Records the credits of a finished task."""
    d = call("/api/v1/jobs/recordInfo?" + urllib.parse.urlencode({"taskId": task}))
    st = d.get("state")
    if st in ("success", "fail"): log_cost(task, d)
    return st, (result_urls(d) if st == "success" else []), d.get("failMsg") or d.get("failCode")

_logged = set()
def log_cost(task, d):
    if task in _logged: return
    _logged.add(task)
    try:
        os.makedirs(os.path.dirname(COSTS), exist_ok=True)
        c = d.get("creditsConsumed")
        with open(COSTS, "a") as f: f.write(json.dumps({"task": task, "model": d.get("model"), "state": d.get("state"), "credits": c,
                                                       "usd": round(c * USD_PER_CREDIT, 4) if isinstance(c, (int, float)) else None}) + "\n")
    except Exception: pass

def public_url(img):
    """A URL KIE can fetch: URLs pass through; base64 (or a local file) is uploaded once to the output bucket, named by its hash."""
    s = str(img)
    if s.startswith(("http://", "https://")): return s
    raw = open(s, "rb").read() if len(s) < 1024 and os.path.exists(s) else base64.b64decode(s.split(",", 1)[-1])
    bucket, base = os.environ.get("INFOGEN_OUTPUT_BUCKET"), (os.environ.get("INFOGEN_OUTPUT_BASE_URL") or "").rstrip("/")
    if not (bucket and base): raise RuntimeError("a base64 reference image needs INFOGEN_OUTPUT_BUCKET and INFOGEN_OUTPUT_BASE_URL to reach KIE")
    k = f"infogen/kie-inputs/{hashlib.sha256(raw).hexdigest()[:24]}.png"
    import boto3
    boto3.client("s3", endpoint_url=os.environ.get("INFOGEN_S3_ENDPOINT") or None).put_object(Bucket=bucket, Key=k, Body=raw, ContentType="image/png")
    return f"{base}/{k}"

def wait(tasks, every=5, limit=900):
    """{name: taskId} -> {name: {"url": ...} | {"error": ...}}."""
    out, t0 = {}, time.time()
    while len(out) < len(tasks) and time.time() - t0 < limit:
        for n, t in tasks.items():
            if n in out: continue
            try: st, urls, msg = status(t)
            except Exception as e: st, urls, msg = "waiting", [], str(e)
            if st == "success": out[n] = {"url": urls[0]} if urls else {"error": "no result URL"}
            elif st == "fail": out[n] = {"error": str(msg)[:300]}
        if len(out) < len(tasks): time.sleep(every)
    for n in tasks: out.setdefault(n, {"error": "timeout waiting for KIE"})
    return out

def download(url, path):
    open(path, "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "infogen/1.0"}), timeout=300).read())
