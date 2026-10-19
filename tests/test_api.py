"""End-to-end test of the API contract with the mock runner. Spends nothing. Run: .venv/bin/python tests/test_api.py"""
import hashlib, hmac, http.server, json, os, shutil, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN, SECRET, PORT, HOOK = "test-token", "hook-secret", 18080, 18081
got, bad_sig = [], []
class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers["Content-Length"]))
        sig = "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        (got if hmac.compare_digest(sig, self.headers.get("X-Infogen-Signature", "")) else bad_sig).append(json.loads(raw))
        self.send_response(200); self.end_headers()
    def log_message(self, *a): pass
threading.Thread(target=http.server.HTTPServer(("127.0.0.1", HOOK), H).serve_forever, daemon=True).start()
runs = tempfile.mkdtemp()
env = dict(os.environ, INFOGEN_API_TOKEN=TOKEN, INFOGEN_CALLBACK_SECRET=SECRET, INFOGEN_RUNS_DIR=runs, INFOGEN_RUNNER="mock", INFOGEN_APP=ROOT, INFOGEN_HEARTBEAT_S="1",
           INFOGEN_MOCK_STEP_S="0.3", INFOGEN_ALLOW_HTTP_CALLBACK="1", GEMINI_API_KEY="x", RUNPOD_API_KEY="x", COMFY_API_KEY="x", INFOGEN_ORIGIN_SECRET="cf-secret")
srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.server:app", "--port", str(PORT), "--log-level", "warning"], cwd=ROOT, env=env)
def call(method, path, body=None, token=TOKEN, origin="cf-secret"):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", json.dumps(body).encode() if body is not None else None,
                                 {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "X-Origin-Verify": origin}, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10); return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read() or b"{}")
def wait_state(j, want, t=30):
    t0 = time.time()
    while time.time() - t0 < t:
        s = call("GET", f"/v1/infographics/{j}")[1]
        if s["state"] in want: return s
        time.sleep(0.2)
    raise AssertionError(f"timeout waiting for {want}, last {s['state']} {s['stage']}")
ok = 0
def check(name, cond, info=""):
    global ok
    if not cond: print("FAIL", name, info); srv.terminate(); shutil.rmtree(runs); sys.exit(1)
    ok += 1; print("ok  ", name)
try:
    for _ in range(50):
        try:
            if call("GET", "/v1/health")[0] == 200: break
        except Exception: time.sleep(0.2)
    c, h = call("GET", "/v1/health"); check("health ready", c == 200 and h["ready"] and not h["busy"], h)
    check("401 bad token", call("GET", "/v1/health", token="nope")[0] == 401)
    check("403 without CloudFront origin header", call("GET", "/v1/health", origin="")[0] == 403)
    base = {"topic": "Test topic", "synopsis": "A test.", "callback": {"url": f"http://127.0.0.1:{HOOK}/hook"}}
    c, b = call("POST", "/v1/infographics", dict(base, request_id="r1", long={"target_seconds": 5}))
    check("400 validation names the field", c == 400 and b["error"]["field"] == "long.target_seconds", b)
    c, b = call("POST", "/v1/infographics", {"topic": "x"}); check("400 missing required", c == 400, b)
    c, b = call("POST", "/v1/infographics", dict(base, request_id="r0", format="podcast")); check("400 unknown format", c == 400 and b["error"]["field"] == "format", b)
    c, b = call("POST", "/v1/infographics", dict(base, request_id="r1", format="hour_by_hour", visuals={"style": "noir_vector", "cast": {"hero": "a man in a red cap"}})); check("202 accepted", c == 202 and b["job_id"].startswith("ig_"), b); j = b["job_id"]
    st_ = json.load(open(os.path.join(runs, j, "style.json"))); check("style.json written from the request", st_["preset"] == "noir_vector" and st_["cast"] == {"hero": "a man in a red cap"}, st_)
    vis = json.load(open(os.path.join(runs, j, "request.json")))["visuals"]
    check("visual budget defaults: 80 frames for 10 minutes, 8 characters, 8 objects, 8 backgrounds",
          (vis["illustrations"], vis["characters"], vis["objects"], vis["backgrounds"], vis["animated_max_pct"], vis["animated_clips"]) == (80, 8, 8, 8, 20, 18), vis)
    scale = subprocess.run([sys.executable, "-c", "from api.server import Req; mk = lambda **k: Req(request_id='x', topic='t', synopsis='s', callback={'url': 'https://h'}, **k).visuals.illustrations; "
                            "print(mk(long={'target_seconds': 300}), mk(long={'target_seconds': 900}), mk(visuals={'illustrations': 12}))"], capture_output=True, text=True, cwd=ROOT, env=env)
    check("frame budget scales with length (5 min 40, 15 min 120), an explicit value is kept", scale.stdout.split() == ["40", "120", "12"], scale.stdout + scale.stderr[-300:])
    c, b2 = call("POST", "/v1/infographics", dict(base, request_id="r1")); check("200 idempotent replay", c == 200 and b2["job_id"] == j, b2)
    c, b3 = call("POST", "/v1/infographics", dict(base, request_id="r2")); check("409 busy", c == 409 and b3["error"]["current_job_id"] == j, b3)
    s = wait_state(j, ["awaiting_input"]); check("checkpoint cp_script", s["awaiting"]["checkpoint_id"] == "cp_script" and s["stage"] == "script", s)
    check("409 wrong checkpoint", call("POST", f"/v1/infographics/{j}/respond", {"checkpoint_id": "cp_final", "action": "approve"})[0] == 409)
    call("POST", f"/v1/infographics/{j}/respond", {"checkpoint_id": "cp_script", "action": "revise", "instructions": "shorter"})
    time.sleep(0.5); s = wait_state(j, ["awaiting_input"]); check("revise raises cp_script again", s["awaiting"]["checkpoint_id"] == "cp_script" and "revised" in s["awaiting"]["question"], s)
    call("POST", f"/v1/infographics/{j}/respond", {"checkpoint_id": "cp_script", "action": "approve"})
    time.sleep(0.5); s = wait_state(j, ["awaiting_input"]); check("checkpoint cp_final", s["awaiting"]["checkpoint_id"] == "cp_final" and s["stage"] == "metadata", s)
    call("POST", f"/v1/infographics/{j}/respond", {"checkpoint_id": "cp_final", "action": "approve"})
    s = wait_state(j, ["succeeded", "failed"]); check("succeeded", s["state"] == "succeeded" and s["progress"] == 1.0 and s["stage"] == "done" and s["outputs"][0]["kind"] == "long_video", s)
    check("stages_done complete", set(s["stages_done"]) >= {"setup", "script", "assets_queued", "assets_ready", "narration", "timings", "build_long", "build_shorts", "metadata", "upload_outputs"}, s["stages_done"])
    time.sleep(1.5)
    mine = [e for e in got if e["job_id"] == j]; ev = [e for e in mine if e["event"] != "job.heartbeat"]; seqs = [e["seq"] for e in ev]
    check("webhooks signed", len(mine) > 10 and not bad_sig, (len(mine), len(bad_sig)))
    check("webhook seq strictly increasing from 1", sorted(seqs) == list(range(1, len(seqs) + 1)), seqs)
    kinds = [e["event"] for e in sorted(ev, key=lambda e: e["seq"])]
    check("event order", kinds[0] == "job.accepted" and kinds[-1] == "job.succeeded" and kinds.count("checkpoint.awaiting_input") == 3 and "stage.started" in kinds, kinds)
    check("heartbeats sent", any(e["event"] == "job.heartbeat" for e in mine))
    c, e = call("GET", f"/v1/infographics/{j}/events?after_seq=5"); check("events endpoint", c == 200 and e["events"][0]["seq"] == 6 and len(e["events"]) == len(seqs) - 5, len(e["events"]))
    r = urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/v1/infographics/{j}/files/out/mock.mp4", headers={"Authorization": f"Bearer {TOKEN}", "X-Origin-Verify": "cf-secret"})); check("file download", len(r.read()) == 1000)
    check("no path traversal", call("GET", f"/v1/infographics/{j}/files/..%2Findex.json")[0] == 404 and call("GET", f"/v1/infographics/{j}/files/../index.json")[0] in (404, 400))
    c, b = call("POST", "/v1/infographics", dict(base, request_id="r2", review_mode="auto")); check("second job after first ends", c == 202, b)
    s = wait_state(b["job_id"], ["succeeded", "failed"]); check("auto mode runs without checkpoints", s["state"] == "succeeded" and not any(x["event"] == "checkpoint.awaiting_input" for x in got if x["job_id"] == b["job_id"]), s)
    c, b = call("POST", "/v1/infographics", dict(base, request_id="r3", topic="FAIL please")); s = wait_state(b["job_id"], ["succeeded", "failed"])
    check("failure reported with error code", s["state"] == "failed" and s["error"]["code"] == "generation_failed", s)
    c, b = call("POST", "/v1/infographics", dict(base, request_id="r4", review_mode="auto")); time.sleep(0.6)
    c, s = call("POST", f"/v1/infographics/{b['job_id']}/cancel"); check("cancel", s["state"] == "cancelled", s)
    time.sleep(1.0); check("cancelled job stays cancelled and frees the slot", call("GET", f"/v1/infographics/{b['job_id']}")[1]["state"] == "cancelled" and not call("GET", "/v1/health")[1]["busy"])
    check("health reports idle_seconds", "idle_seconds" in call("GET", "/v1/health")[1])
    c, b = call("POST", "/v1/infographics", dict(base, request_id="st1", visuals={"style": "auto", "palette": {"accent": "#FF0000"}}, review_mode="auto"))
    st1 = None
    if c == 202: st1 = json.load(open(os.path.join(runs, b["job_id"], "style.json"))); wait_state(b["job_id"], ["succeeded", "failed"])
    check("style auto: the style is left to choose, the fixed colour kept, the palette not chosen", c == 202 and st1["preset"] == "auto"
          and st1["choose"] == {"style": True, "palette": False} and st1["palette"] == {"accent": "#FF0000"}, (c, b, st1))
    th = json.load(open(os.path.join(runs, j, "request.json")))["thumbnail"]
    check("thumbnail defaults: cinematic infographic, 3 candidates, exact overlay, Shorts and cover frames", th == {"style": "cinematic_infographic", "candidates": 3, "text": None,
          "text_mode": "overlay", "shorts": True, "shorts_cover": True, "resolution": "2K"}, th)
    c, b = call("POST", "/v1/infographics", dict(base, request_id="th1", thumbnail={"style": "neon", "candidates": 9, "text": "x" * 40}))
    check("thumbnail: unknown style, too many candidates, too long a headline are 400", c == 400, b)
    c, b = call("POST", "/v1/infographics", dict(base, request_id="st2", visuals={"palette": {"glow": "#FFFFFF"}}))
    check("palette: an unknown colour is a 400", c == 400 and "glow" in json.dumps(b), b)
    for secs, want in ((300, 202), (900, 202), (450, 400), (1800, 400)):
        c, b = call("POST", "/v1/infographics", dict(base, request_id=f"d{secs}", long={"target_seconds": secs}, review_mode="auto"))
        check(f"duration {secs} s: {want}", c == want and (want == 400 or b["job_id"]), b)
        if c == 202: wait_state(b["job_id"], ["succeeded", "failed"])
    c, b = call("POST", "/v1/infographics", dict(base, request_id="s1", kind="series_plan", topic="Cold War flashpoints", series={"name": "Flashpoints"},
                                                 series_plan={"episodes": 12, "per_week": 3, "start_date": "2026-11-02"}))
    check("series plan accepted", c == 202, b); sj = b["job_id"]
    s = wait_state(sj, ["awaiting_input"]); check("series plan: cp_series checkpoint", s["awaiting"]["checkpoint_id"] == "cp_series", s)
    plan = json.load(open(os.path.join(runs, sj, "series", "series.json")))
    check("series plan: 12 episodes Mon/Wed/Fri from the start date, linked", len(plan["episodes"]) == 12 and [e["publish_date"] for e in plan["episodes"][:4]] == ["2026-11-02", "2026-11-04", "2026-11-06", "2026-11-09"]
          and plan["episodes"][0]["next_title"] == "Episode 2" and plan["episodes"][-1]["next_title"] is None, plan["episodes"][:2])
    rb = subprocess.run([sys.executable, "-c", "from api.server import start_prompt as p; print(p({'kind': 'series_plan'}).startswith('# Plan a series'), p({'kind': 'video'}).startswith('# Produce'))"],
                        capture_output=True, text=True, cwd=ROOT, env=env)
    check("series plan: runs the series runbook, a video the production one", rb.stdout.split() == ["True", "True"], rb.stdout + rb.stderr[-300:])
    call("POST", f"/v1/infographics/{sj}/respond", {"checkpoint_id": "cp_series", "action": "approve"})
    s = wait_state(sj, ["succeeded", "failed"]); check("series plan: succeeds with the plan as output", s["state"] == "succeeded" and [o["kind"] for o in s["outputs"]] == ["series_plan", "series_plan_pdf", "series_overview"], s)
    print(f"\nALL {ok} CHECKS PASSED")
finally:
    srv.terminate(); shutil.rmtree(runs, ignore_errors=True)
