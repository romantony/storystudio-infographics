"""The harness for infogen's single-shot Claude calls (the analysts, the 3D planner): every call goes through call_checked(), which
  1. replays a stored answer for a request it has seen before (a restarted job, a re-run review) instead of paying again;
  2. checks the answer in code (checks=[fn(reply) -> [Violation]]; errors block, warnings are recorded);
  3. repairs only what failed: a fresh short session gets the original request, its previous reply and the failing rule lines;
  4. prices every call (llm.run writes llm_calls.jsonl; the cost of this stage call is returned and logged to harness.jsonl).
Design: docs/LLM_HARNESS_GUIDE.md. Sonnet 5.5 is the model; a `ladder` of several models is supported but off unless a caller sets one.
The producer session is not replayable call by call; its outputs are checked by `python3 -m infogen validate` instead.

Cache: key = sha256 of canonical JSON of everything that decides the answer (step, stage `version`, ladder, text, tools, effort, caller's
`extra` such as the hash of the files the prompt only names). Stored in INFOGEN_LLM_CACHE_DIR (default <INFOGEN_RUNS_DIR>/_llmcache, on the
shared volume). A result still failing at the top of the ladder is cached too (passed: false) so a rerun does not pay for the same failure.
Env: INFOGEN_LLM_CACHE = readwrite (default) | read (a miss is an error; tests) | off.   INFOGEN_REPAIR_ATTEMPTS (2) per model.
Bump `version` when a prompt or check changes meaning in a way the request text does not show."""
import hashlib, json, os, time
from dataclasses import dataclass, field, asdict
from . import llm

@dataclass
class Violation:
    rule_id: str; target: str; message: str; severity: str = "error"   # error blocks and is repaired; warning is recorded only
    def line(self): return f"[{self.rule_id}] {self.target}: {self.message}"

@dataclass
class Result:
    reply: str; violations: list = field(default_factory=list); model: str = ""; repairs: int = 0; escalated: bool = False
    cached: bool = False; usd: float = 0.0; attempts: int = 0
    @property
    def errors(self): return [v for v in self.violations if v.severity == "error"]
    @property
    def passed(self): return not self.errors

def cache_dir():
    return os.environ.get("INFOGEN_LLM_CACHE_DIR") or os.path.join(os.environ.get("INFOGEN_RUNS_DIR", "/data/runs"), "_llmcache")

def cache_mode(): return os.environ.get("INFOGEN_LLM_CACHE", "readwrite")

def file_hash(paths):
    """Content hash of the files a prompt only names, so changed files change the cache key."""
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(p.encode())
        try: h.update(open(p, "rb").read())
        except OSError: h.update(b"<missing>")
    return h.hexdigest()

def key(step, version, ladder, text, tools, effort, extra):
    blob = json.dumps({"step": step, "version": version, "ladder": list(ladder), "text": text, "tools": tools, "effort": effort, "extra": extra},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()

def _path(k): return os.path.join(cache_dir(), k[:2], k + ".json")

def _load(k):
    try: d = json.load(open(_path(k)))
    except Exception: return None
    return Result(d["reply"], [Violation(**v) for v in d.get("violations", [])], d.get("model", ""), d.get("repairs", 0), d.get("escalated", False), True, 0.0, 0)

def _store(k, r):
    if cache_mode() != "readwrite": return
    try:
        p = _path(k); os.makedirs(os.path.dirname(p), exist_ok=True)
        json.dump({"reply": r.reply, "violations": [asdict(v) for v in r.violations], "model": r.model, "repairs": r.repairs, "escalated": r.escalated,
                   "passed": r.passed, "usd": r.usd, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, open(p + ".tmp", "w")); os.replace(p + ".tmp", p)
    except Exception: pass                                   # the cache must never fail the work

def _log(rec):
    try:
        with open("harness.jsonl", "a") as f: f.write(json.dumps(rec) + "\n")
    except Exception: pass

def _run_checks(checks, reply):
    out = []
    for fn in checks:
        try: out += fn(reply) or []
        except Exception as e: out.append(Violation("harness.check_crashed", getattr(fn, "__name__", "check"), f"{type(e).__name__}: {e}", "warning"))   # a check never crashes a job
    return out

def repair_text(text, reply, errors):
    return (text + "\n\n## Your previous reply\n\n" + reply + "\n\n## Problems found by the checker\n\n" + "\n".join("- " + v.line() for v in errors)
            + "\n\nReply again with the complete corrected answer in the same format. Change only what these problems need; keep everything else exactly as it was.")

def call_checked(step, text, models, checks=(), tools="", max_turns=40, max_usd=None, timeout=1800, effort=None, version=1, extra=None, repairs=None, ask=None):
    """Result for one stage call. `models`: a model id or a ladder (cheapest first). `ask(text, model)` replaces llm.run (tests, *_CMD overrides)."""
    ladder = [models] if isinstance(models, str) else list(models)
    k = key(step, version, ladder, text, tools, effort, extra)
    if cache_mode() != "off":
        hit = _load(k)
        if hit: _log({"step": step, "cached": True, "passed": hit.passed, "model": hit.model}); return hit
        if cache_mode() == "read": raise RuntimeError(f"{step}: no recorded answer for this request (INFOGEN_LLM_CACHE=read)")
    n_repairs = int(os.environ.get("INFOGEN_REPAIR_ATTEMPTS", "2")) if repairs is None else repairs
    usd = 0.0; attempts = 0; res = None
    def one(prompt, model):
        nonlocal usd, attempts
        attempts += 1; llm.LAST[0] = None
        reply = ask(prompt, model) if ask else llm.run(prompt, model, step, tools=tools, max_turns=max_turns, max_usd=max_usd, timeout=timeout, effort=effort)
        if llm.LAST[0]: usd += llm.LAST[0].get("usd") or 0
        return reply
    for i, model in enumerate(ladder):
        reply = one(text, model); v = _run_checks(checks, reply); fixed = 0
        while any(x.severity == "error" for x in v) and fixed < n_repairs:
            # each repair turn is original request + current reply + current failures, not a growing history
            reply = one(repair_text(text, reply, [x for x in v if x.severity == "error"]), model); fixed += 1; v = _run_checks(checks, reply)
        res = Result(reply, v, model, fixed, i > 0)
        if res.passed: break
    res.usd = round(usd, 4); res.attempts = attempts
    _store(k, res)
    _log({"step": step, "cached": False, "model": res.model, "attempts": attempts, "repairs": res.repairs, "escalated": res.escalated, "passed": res.passed,
          "violations": [v.line() for v in res.violations], "usd": res.usd})
    return res
