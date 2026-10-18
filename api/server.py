"""infogen API server. One infographic video job at a time; the orchestrator owns the queue.
Same lifecycle as the docgen (documentary) service: see docs/ORCHESTRATOR_INTEGRATION.md. Status comes from <run>/status.json, which the toolkit writes.

Env: INFOGEN_API_TOKEN (required), INFOGEN_CALLBACK_SECRET, INFOGEN_RUNS_DIR (/data/runs), INFOGEN_RUNNER (claude|mock),
     INFOGEN_IMAGE, INFOGEN_ORIGIN_SECRET (CloudFront origin header), INFOGEN_PROMPT (/app/prompts/produce.md), INFOGEN_CLAUDE_FLAGS, INFOGEN_HEARTBEAT_S (60),
     INFOGEN_KEEP_RUNS (3: full run folders kept for the newest finished jobs)"""
import hashlib, hmac, json, os, queue, re, shlex, shutil, signal, subprocess, sys, threading, time, urllib.request, uuid
from typing import Dict, List, Literal, Optional
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError, field_validator

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from infogen import status as S

RUNS = os.environ.get("INFOGEN_RUNS_DIR", "/data/runs")
TOKEN = os.environ.get("INFOGEN_API_TOKEN", "")
SECRET = os.environ.get("INFOGEN_CALLBACK_SECRET", "")
RUNNER = os.environ.get("INFOGEN_RUNNER", "claude")
IMAGE = os.environ.get("INFOGEN_IMAGE", "infogen:dev")
PROMPT = os.environ.get("INFOGEN_PROMPT") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompts", "produce.md")
HEARTBEAT = float(os.environ.get("INFOGEN_HEARTBEAT_S", "60"))
CLAUDE_FLAGS = os.environ.get("INFOGEN_CLAUDE_FLAGS", "--permission-mode acceptEdits --allowedTools Bash Read Write Edit Glob Grep WebSearch WebFetch")
RETRY = [float(x) for x in os.environ.get("INFOGEN_WEBHOOK_RETRY_S", "5,15,60,180,300").split(",")]
TERMINAL = ("succeeded", "failed", "cancelled")
KEEP_RUNS = int(os.environ.get("INFOGEN_KEEP_RUNS", "3"))
BOOT = time.time(); LAST_CALL = [time.time()]
os.makedirs(RUNS, exist_ok=True)

# ---------- request model ----------
FORMATS = Literal["explainer", "what_if", "hour_by_hour", "day_by_day", "versus", "body", "ranking", "true_story", "compilation"]
class Series(BaseModel):
    name: Optional[str] = None; episode: Optional[int] = None
    previous_episode_title: Optional[str] = None; previous_episode_url: Optional[str] = None
    next_episode_title: Optional[str] = None; playlist_url: Optional[str] = None
class Long(BaseModel):
    enabled: bool = True; aspect: Literal["16:9"] = "16:9"
    target_seconds: int = Field(600, ge=120, le=1800); narrator_voice: str = "Puck"
class Shorts(BaseModel):
    count: int = Field(3, ge=0, le=3); aspect: Literal["9:16"] = "9:16"
    angles: List[Literal["hook", "stat", "twist", "myth", "countdown"]] = ["hook", "stat", "twist"]
class Visuals(BaseModel):
    style: Literal["flat_vector", "noir_vector", "paper"] = "flat_vector"
    palette: Dict[str, str] = {}                       # overrides of remotion/src/theme.ts keys, e.g. {"accent": "#FFC93C"}
    cast: Dict[str, str] = {}                          # recurring characters: id -> fixed visual description
    illustrations: int = Field(24, ge=0, le=80)        # generated scene images
    characters: int = Field(6, ge=0, le=20)            # generated character poses (cut out automatically)
    ltx_clips: int = Field(0, ge=0, le=10)             # animated illustrations (ComfyUI LTX), the most expensive item
    charts: bool = True; maps: bool = True
    captions_long: bool = False; captions_shorts: bool = True
class Limits(BaseModel):
    max_runtime_minutes: int = Field(180, ge=30, le=360); max_llm_turns: int = Field(500, ge=20, le=2000)
class Output(BaseModel):
    prefix: Optional[str] = Field(None, max_length=200, pattern=r"^infogen/[A-Za-z0-9_\-./]*$")   # the instance role can only write under infogen/
class Callback(BaseModel):
    url: str
    @field_validator("url")
    @classmethod
    def https(cls, v):
        if not (v.startswith("https://") or (os.environ.get("INFOGEN_ALLOW_HTTP_CALLBACK") == "1" and v.startswith("http://"))): raise ValueError("callback.url must be https")
        return v
class Req(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    topic: str = Field(..., min_length=1, max_length=200); synopsis: str = Field(..., min_length=1, max_length=2000)
    format: FORMATS = "explainer"
    series: Series = Series(); long: Long = Long(); shorts: Shorts = Shorts(); visuals: Visuals = Visuals()
    review_mode: Literal["checkpoints", "auto"] = "checkpoints"; model: str = "claude-sonnet-5-5"
    limits: Limits = Limits(); output: Output = Output(); callback: Callback
class Respond(BaseModel):
    checkpoint_id: str; action: Literal["approve", "revise", "abort"]; instructions: str = ""

# ---------- job state on disk ----------
LOCK = threading.RLock()
def jdir(j): return os.path.join(RUNS, j)
def jread(j, name, default=None):
    try: return json.load(open(os.path.join(jdir(j), name)))
    except Exception: return default
def jwrite(j, name, obj):
    p = os.path.join(jdir(j), name); json.dump(obj, open(p + ".tmp", "w"), indent=1); os.replace(p + ".tmp", p)
def index(): return jread("", "index.json", {}) or {}
def current():
    """job id of the job that is running or awaiting input, if any"""
    for rid, j in index().items():
        st = jread(j, "state.json", {})
        if st.get("state") not in TERMINAL: return j
    return None
def public(j):
    """the status object of section 4.4"""
    job = jread(j, "job.json", {}); st = jread(j, "state.json", {}); a = S.read(os.path.join(jdir(j), "status.json"))
    out = {"job_id": j, "request_id": job.get("request_id"), "seq": st.get("seq", 0), "state": st.get("state", "running"),
           "stage": a.get("stage", "setup"), "stages_done": a.get("stages_done", []), "progress": a.get("progress", 0.0), "message": a.get("message", ""),
           "next_steps": a.get("next_steps", []), "awaiting": a.get("awaiting") if st.get("state") == "awaiting_input" else None,
           "warnings": a.get("warnings", []), "outputs": a.get("outputs", []), "costs": a.get("costs", {}),
           "error": st.get("error") or a.get("error"), "created_at": job.get("created_at"), "stage_started_at": a.get("stage_started_at"), "updated_at": st.get("updated_at")}
    if out["state"] == "succeeded": out["progress"] = 1.0
    return out

def prune(skip=None):
    """Free disk when a new job starts. Finished jobs beyond the newest KEEP_RUNS lose their media and working files; the small
    status files stay, so the job can still be queried. A succeeded job is only pruned once all its outputs are uploaded."""
    done = sorted((jread(j, "job.json", {}).get("created_at", ""), j) for j in index().values()
                  if j != skip and jread(j, "state.json", {}).get("state") in TERMINAL)
    for _, j in done[:max(len(done) - KEEP_RUNS, 0)]:
        outs = S.read(os.path.join(jdir(j), "status.json")).get("outputs", [])
        if jread(j, "state.json", {}).get("state") == "succeeded" and not (outs and all(o.get("key") for o in outs)): continue
        for name in os.listdir(jdir(j)):
            p = os.path.join(jdir(j), name)
            if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
            elif not name.endswith((".json", ".jsonl")): os.remove(p)

# ---------- webhooks (section 4.5): signed, at-least-once, retried, never block the job ----------
HOOKS: "queue.Queue" = queue.Queue()
def emit(j, event, bump=True):
    with LOCK:
        st = jread(j, "state.json", {})
        if bump: st["seq"] = st.get("seq", 0) + 1
        st["updated_at"] = S.now(); jwrite(j, "state.json", st)
        body = {"event": event, "job_id": j, "request_id": jread(j, "job.json", {}).get("request_id"), "seq": st["seq"], "sent_at": S.now(), "status": public(j)}
        if event != "job.heartbeat":
            with open(os.path.join(jdir(j), "events.jsonl"), "a") as f: f.write(json.dumps(body) + "\n")
    url = jread(j, "job.json", {}).get("request", {}).get("callback", {}).get("url")
    if url: HOOKS.put((url, body, 0, time.time()))
def hook_worker():
    while True:
        url, body, attempt, due = HOOKS.get()
        if due > time.time(): HOOKS.put((url, body, attempt, due)); HOOKS.task_done(); time.sleep(0.5); continue
        raw = json.dumps(body).encode()
        hdr = {"Content-Type": "application/json", "X-Infogen-Event": body["event"], "X-Infogen-Delivery": str(uuid.uuid4()),
               "X-Infogen-Signature": "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()}
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, raw, hdr), timeout=10); ok = 200 <= r.status < 300
        except Exception: ok = False
        if not ok and body["event"] != "job.heartbeat" and attempt < len(RETRY): HOOKS.put((url, body, attempt + 1, time.time() + RETRY[attempt]))
        HOOKS.task_done()   # api/task.py waits on HOOKS.join() for delivery (retries included) before the ECS task exits
threading.Thread(target=hook_worker, daemon=True).start()

# ---------- runner ----------
PROCS = {}
def spawn(j, text, resume=False):
    job = jread(j, "job.json"); req = job["request"]; log = open(os.path.join(jdir(j), "runner.jsonl"), "a")
    env = dict(os.environ, INFOGEN_JOB_ID=j, INFOGEN_REQUEST_ID=req["request_id"], PYTHONPATH=os.environ.get("INFOGEN_APP", "/app") + ":" + os.environ.get("PYTHONPATH", ""))
    if RUNNER == "mock":
        cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mock_runner.py"), "resume" if resume else "start", text]
    else:
        cmd = ["claude", "-p", text, "--model", req["model"], "--output-format", "stream-json", "--verbose", "--max-turns", str(req["limits"]["max_llm_turns"])] + shlex.split(CLAUDE_FLAGS)
        sid = jread(j, "state.json", {}).get("session_id")
        if resume and sid: cmd += ["--resume", sid]
    p = subprocess.Popen(cmd, cwd=jdir(j), stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    PROCS[j] = p
    with LOCK:
        st = jread(j, "state.json", {}); st["state"] = "running"; st["pid"] = p.pid; jwrite(j, "state.json", st)
    return p
def session_id(j):
    try:
        for line in open(os.path.join(jdir(j), "runner.jsonl")):
            if '"session_id"' in line:
                m = re.search(r'"session_id"\s*:\s*"([^"]+)"', line)
                if m: return m.group(1)
    except Exception: pass
def finish(j, state, error=None):
    with LOCK:
        st = jread(j, "state.json", {}); st["state"] = state; st["error"] = error; st["finished_at"] = S.now(); jwrite(j, "state.json", st)
    emit(j, {"succeeded": "job.succeeded", "failed": "job.failed", "cancelled": "job.cancelled"}[state])
def watch(j):
    """Follow status.json for one run of the runner process: turn changes into events, send heartbeats, decide the outcome."""
    p = PROCS[j]; sp = os.path.join(jdir(j), "status.json"); last = S.read(sp); last_beat = time.time()
    deadline = jread(j, "job.json")["deadline"]
    while True:
        rc = p.poll(); a = S.read(sp)
        if a and a != last:
            if a.get("stage") != last.get("stage"):
                if last.get("stage"): emit(j, "stage.completed")
                emit(j, "stage.started")
            elif {k: v for k, v in a.items() if k != "updated_at"} != {k: v for k, v in last.items() if k != "updated_at"}:
                emit(j, "status.updated")
            last = a
        st = jread(j, "state.json", {})
        if st.get("state") == "cancelled": return
        if rc is not None: break
        if time.time() > deadline:
            kill(j); finish(j, "failed", {"code": "timeout", "stage": a.get("stage"), "message": "max_runtime_minutes exceeded", "retryable": True}); return
        if time.time() - last_beat >= HEARTBEAT: emit(j, "job.heartbeat", bump=False); last_beat = time.time()
        time.sleep(1)
    with LOCK:
        st = jread(j, "state.json", {}); sid = session_id(j)
        if sid: st["session_id"] = sid; jwrite(j, "state.json", st)
    a = S.read(sp)
    if a.get("state") == "succeeded": finish(j, "succeeded")
    elif a.get("state") == "awaiting_input" and a.get("awaiting"):
        with LOCK:
            st = jread(j, "state.json", {}); st["state"] = "awaiting_input"; jwrite(j, "state.json", st)
        emit(j, "checkpoint.awaiting_input")
    elif a.get("state") == "failed": finish(j, "failed", a.get("error") or {"code": "generation_failed", "stage": a.get("stage"), "message": a.get("message", ""), "retryable": False})
    else: finish(j, "failed", {"code": "llm_error" if rc else "internal", "stage": a.get("stage"), "message": f"runner exited (code {rc}) without finishing or asking for input", "retryable": True})
def kill(j):
    p = PROCS.get(j)
    if p and p.poll() is None:
        try: os.killpg(p.pid, signal.SIGTERM)
        except Exception: pass
        try: p.wait(10)
        except Exception:
            try: os.killpg(p.pid, signal.SIGKILL)
            except Exception: pass
def start_prompt(req):
    return open(PROMPT).read() + "\n\n## This job\n\nThe request is in `request.json` in the current folder. Read it first.\n"

# ---------- health ----------
APP = os.environ.get("INFOGEN_APP", "/app")
def checks():
    c = {}
    for name, env in (("anthropic", "ANTHROPIC_API_KEY"), ("gemini", "GEMINI_API_KEY"), ("runpod", "RUNPOD_API_KEY"), ("comfy", "COMFY_API_KEY")):
        c[name] = "set" if os.environ.get(env) else "missing"     # presence only; validity shows up when a job uses the key
    c["callback_secret"] = "set" if SECRET else "missing"
    c["templates"] = "ready" if os.path.isfile(os.path.join(os.environ.get("INFOGEN_REMOTION") or os.path.join(APP, "remotion"), "bundle", "index.html")) else "missing"
    c["disk_free_gb"] = round(shutil.disk_usage(RUNS).free / 1e9, 1)
    return c
def ready(c, need_ltx=False):
    ok = all(c[k] == "set" for k in ("gemini", "runpod", "callback_secret")) and c["disk_free_gb"] >= 5 and (c["comfy"] == "set" or not need_ltx)
    if RUNNER != "mock": ok = ok and c["anthropic"] == "set" and c["templates"] == "ready"
    return ok

# ---------- app ----------
app = FastAPI(title="infogen", version="1")
ORIGIN_SECRET = os.environ.get("INFOGEN_ORIGIN_SECRET", "")   # custom header CloudFront adds; proves the call came through the distribution
def auth(authorization: str = Header(default=""), x_origin_verify: str = Header(default="")):
    if ORIGIN_SECRET and not hmac.compare_digest(x_origin_verify, ORIGIN_SECRET): raise HTTPException(403, {"code": "forbidden"})
    if not TOKEN or not hmac.compare_digest(authorization, f"Bearer {TOKEN}"): raise HTTPException(401, {"code": "unauthorized"})
    LAST_CALL[0] = time.time()
@app.exception_handler(HTTPException)
async def http_err(request, exc): return JSONResponse({"error": exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}}, status_code=exc.status_code)
from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def val_err(request, exc):
    e = exc.errors()[0]; return JSONResponse({"error": {"code": "invalid_field", "field": ".".join(str(x) for x in e["loc"] if x != "body"), "message": e["msg"]}}, status_code=400)

@app.get("/v1/health")
def health(_=Depends(auth)):
    c = checks(); cur = current()
    return {"ready": ready(c), "image": IMAGE, "runner": RUNNER, "busy": cur is not None, "current_job_id": cur, "checks": c,
            "uptime_seconds": int(time.time() - BOOT), "idle_seconds": 0 if cur else int(time.time() - LAST_CALL[0])}

@app.post("/v1/infographics")
def create(req: Req, _=Depends(auth)):
    with LOCK:
        idx = index()
        if req.request_id in idx:
            j = idx[req.request_id]; return JSONResponse({"job_id": j, "request_id": req.request_id, "state": public(j)["state"], "status_url": f"/v1/infographics/{j}"}, status_code=200)
        cur = current()
        if cur: raise HTTPException(409, {"code": "busy", "current_job_id": cur})
        c = checks()
        if not ready(c, need_ltx=req.visuals.ltx_clips > 0): raise HTTPException(503, {"code": "not_ready", "checks": c})
        j = "ig_" + uuid.uuid4().hex[:12]; os.makedirs(jdir(j))
        r = req.model_dump(); r["output"]["prefix"] = r["output"]["prefix"] or f"infogen/{req.request_id}/"
        jwrite(j, "request.json", r)
        jwrite(j, "style.json", {"preset": r["visuals"]["style"], "palette": r["visuals"]["palette"], "cast": r["visuals"]["cast"]})   # infogen/style.py reads it
        jwrite(j, "job.json", {"job_id": j, "request_id": req.request_id, "request": r, "created_at": S.now(), "deadline": time.time() + req.limits.max_runtime_minutes * 60})
        jwrite(j, "state.json", {"state": "running", "seq": 0})
        S.update(os.path.join(jdir(j), "status.json"), stage="setup", message="Job accepted.")
        idx[req.request_id] = j; jwrite("", "index.json", idx)
    emit(j, "job.accepted")
    threading.Thread(target=prune, args=(j,), daemon=True).start()
    spawn(j, start_prompt(r)); threading.Thread(target=watch, args=(j,), daemon=True).start()
    return JSONResponse({"job_id": j, "request_id": req.request_id, "state": "running", "status_url": f"/v1/infographics/{j}"}, status_code=202)

def need(j):
    if not re.fullmatch(r"ig_[0-9a-f]{12}", j) or not os.path.isdir(jdir(j)): raise HTTPException(404, {"code": "not_found"})
@app.get("/v1/infographics")
def list_jobs(_=Depends(auth)): return {"jobs": [public(j) for j in index().values()]}
@app.get("/v1/infographics/{j}")
def get_job(j: str, _=Depends(auth)): need(j); return public(j)
@app.get("/v1/infographics/{j}/events")
def events(j: str, after_seq: int = 0, _=Depends(auth)):
    need(j); out = []
    try:
        for line in open(os.path.join(jdir(j), "events.jsonl")):
            e = json.loads(line)
            if e["seq"] > after_seq: out.append(e)
    except FileNotFoundError: pass
    return {"events": out}
@app.post("/v1/infographics/{j}/respond")
def respond(j: str, r: Respond, _=Depends(auth)):
    need(j)
    with LOCK:
        st = jread(j, "state.json", {}); a = S.read(os.path.join(jdir(j), "status.json"))
        if st.get("state") != "awaiting_input": raise HTTPException(409, {"code": "not_awaiting_input", "state": st.get("state")})
        cp = (a.get("awaiting") or {}).get("checkpoint_id")
        if r.checkpoint_id != cp: raise HTTPException(409, {"code": "wrong_checkpoint", "expected": cp})
        if r.action == "abort":
            st["state"] = "cancelled"; jwrite(j, "state.json", st)
    if r.action == "abort": finish(j, "cancelled"); return public(j)
    jwrite(j, f"response_{cp}.json", r.model_dump())
    S.update(os.path.join(jdir(j), "status.json"), state="running", message=f"Checkpoint {cp}: {r.action}.")
    text = (f"The reviewer answered checkpoint {cp}: {r.action.upper()}." + (f" Their instructions: {r.instructions}" if r.instructions else "") +
            " The answer is also in response_" + cp + ".json. " + ("Continue with the next stage." if r.action == "approve" else "Apply the changes, then raise the same checkpoint again."))
    spawn(j, text, resume=True); threading.Thread(target=watch, args=(j,), daemon=True).start()
    emit(j, "status.updated"); return public(j)
@app.post("/v1/infographics/{j}/cancel")
def cancel(j: str, _=Depends(auth)):
    need(j)
    with LOCK:
        st = jread(j, "state.json", {})
        if st.get("state") in TERMINAL: return public(j)
        st["state"] = "cancelled"; jwrite(j, "state.json", st)
    kill(j); finish(j, "cancelled"); return public(j)
@app.get("/v1/infographics/{j}/files/{path:path}")
def files(j: str, path: str, _=Depends(auth)):
    need(j); base = os.path.realpath(jdir(j)); p = os.path.realpath(os.path.join(base, path))
    if not p.startswith(base + os.sep) or not os.path.isfile(p): raise HTTPException(404, {"code": "not_found"})
    return FileResponse(p)

@app.on_event("startup")
def recover():
    """After a restart (the instance was stopped, or the server crashed): a job that was 'running' has lost its process."""
    for rid, j in index().items():
        st = jread(j, "state.json", {})
        if st.get("state") == "running":
            finish(j, "failed", {"code": "internal", "stage": S.read(os.path.join(jdir(j), "status.json")).get("stage"), "message": "server restarted while the job was running", "retryable": True})
