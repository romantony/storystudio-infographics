"""Every Claude call infogen makes, and what it costs. The producer session is started by the API server (api/server.py); the analysts
and the 3D planner call run() below. Nothing else starts a Claude session.

run(): one fresh `claude -p` session, with only the tools it needs loaded (--tools, so the unused tool definitions are not resent on
  every turn), the per-machine part of the system prompt moved out of it (so jobs share the cached prefix), a USD cap of its own
  (--max-budget-usd: a fresh session, so the cap is unambiguous), and its token usage appended to llm_calls.jsonl in the run folder.

Meter: the job's token and USD ledger, kept in llm_usage.json. It reads the producer's stream (runner.jsonl: one usage object per API
  call, deduplicated by message id) and llm_calls.jsonl incrementally, so it can run every second. The server stops a job whose
  estimate passes INFOGEN_MAX_LLM_USD: a runaway loop costs the cap, not the account balance.

USD figures are estimates from the token counts and the list prices below (standard tier); the Console is the bill.

Env: INFOGEN_MAX_LLM_USD (30; 0 = no cap) per job, all sessions together. INFOGEN_ANALYST_MAX_USD (5) and INFOGEN_SCENE3D_MAX_USD (2)
     per session. INFOGEN_CLAUDE_TOOLS: the producer's tools (Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch)."""
import json, os, subprocess, time

USAGE, CALLS = "llm_usage.json", "llm_calls.jsonl"
PRODUCER_TOOLS = os.environ.get("INFOGEN_CLAUDE_TOOLS", "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch")
COMMON = ["--exclude-dynamic-system-prompt-sections"]   # cwd, env and git status go into the first user message instead

# $ per million tokens: input, output, cache read. Cache writes are 1.25x input (5 minutes) and 2x input (1 hour).
PRICES = {"claude-fable-5-1": (10, 50, 0.25), "claude-fable-5": (10, 50, 0.25), "claude-opus-5-5": (4, 20, 0.20), "claude-opus-5": (5, 25, 0.50),
          "claude-opus-4-8": (5, 25, 0.50), "claude-sonnet-5-5": (2, 10, 0.20), "claude-sonnet-5": (2, 10, 0.20), "claude-sonnet-4-6": (3, 15, 0.30),
          "claude-haiku-5-5": (0.10, 0.50, 0.01), "claude-haiku-4-5": (1, 5, 0.10)}

def max_job_usd(): return float(os.environ.get("INFOGEN_MAX_LLM_USD", "30") or 0)

def tokens(u):
    """A Messages API usage object as flat counts."""
    u = u or {}; cw = u.get("cache_creation") or {}
    w1h = cw.get("ephemeral_1h_input_tokens", 0) or 0
    w = u.get("cache_creation_input_tokens", 0) or 0
    return {"input": u.get("input_tokens", 0) or 0, "output": u.get("output_tokens", 0) or 0, "cache_read": u.get("cache_read_input_tokens", 0) or 0,
            "cache_write_5m": max(w - w1h, 0), "cache_write_1h": w1h}

def usd(model, t):
    base = next((p for k, p in PRICES.items() if (model or "").startswith(k)), PRICES["claude-sonnet-5-5"])
    i, o, r = base
    return (t["input"] * i + t["output"] * o + t["cache_read"] * r + t["cache_write_5m"] * i * 1.25 + t["cache_write_1h"] * i * 2) / 1e6

def log_call(step, model, res, cwd="."):
    """Append one finished session (the JSON of `claude -p --output-format json`) to llm_calls.jsonl."""
    t = tokens(res.get("usage"))
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "step": step, "model": model, **t,
           "usd": res["total_cost_usd"] if isinstance(res.get("total_cost_usd"), (int, float)) else round(usd(model, t), 4),
           "turns": res.get("num_turns"), "subtype": res.get("subtype")}
    with open(os.path.join(cwd, CALLS), "a") as f: f.write(json.dumps(rec) + "\n")
    return rec

def run(text, model, step, tools="", max_turns=40, max_usd=None, timeout=1800):
    """The reply text of one fresh session. `tools`: space- or comma-separated built-in tool names, "" for none.
    Raises RuntimeError when the session stopped at its USD cap or its turn limit without replying."""
    names = [x for x in tools.replace(",", " ").split() if x]
    cmd = ["claude", "-p", text, "--model", model, "--output-format", "json", "--max-turns", str(max_turns), "--tools", ",".join(names), *COMMON]
    if names: cmd += ["--allowedTools", *names]
    if max_usd: cmd += ["--max-budget-usd", str(max_usd)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try: res = json.loads(out.stdout)
    except Exception: return out.stdout
    if not isinstance(res, dict): return out.stdout
    try: log_call(step, model, res)
    except Exception: pass                                  # the ledger must never fail the work
    sub = res.get("subtype") or ""
    if sub == "error_max_budget_usd": raise RuntimeError(f"{step}: stopped at its ${max_usd} cap before replying")
    if sub == "error_max_turns" and not res.get("result"): raise RuntimeError(f"{step}: stopped at {max_turns} turns before replying")
    return res.get("result", "")

def empty():
    return {"usd": 0.0, "input": 0, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0, "calls": 0, "by_step": {}}

def add(tot, step, t, cost, calls=1):
    for k in ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h"): tot[k] += t[k]
    tot["usd"] = round(tot["usd"] + cost, 4); tot["calls"] += calls
    s = tot["by_step"].setdefault(step, {"usd": 0.0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "calls": 0})
    s["usd"] = round(s["usd"] + cost, 4); s["input"] += t["input"]; s["output"] += t["output"]; s["cache_read"] += t["cache_read"]
    s["cache_write"] += t["cache_write_5m"] + t["cache_write_1h"]; s["calls"] += calls

class Meter:
    """The job's ledger. poll() folds in what was appended to runner.jsonl and llm_calls.jsonl since the last poll and saves it."""
    def __init__(self, run_dir):
        self.dir = run_dir; self.path = os.path.join(run_dir, USAGE)
        try: st = json.load(open(self.path))
        except Exception: st = {}
        self.tot = st.get("total") or empty(); self.off = st.get("offsets") or {}
        self.seen = {}                                      # message id -> counts already added (a message is streamed in several lines)
    def lines(self, name):
        p = os.path.join(self.dir, name)
        try:
            with open(p, "rb") as f:
                f.seek(self.off.get(name, 0)); data = f.read()
        except FileNotFoundError: return []
        end = data.rfind(b"\n") + 1                         # a half-written last line waits for the next poll
        self.off[name] = self.off.get(name, 0) + end
        return data[:end].decode("utf-8", "replace").splitlines()
    def poll(self):
        before = (self.tot["usd"], self.tot["calls"], self.tot["output"])
        for line in self.lines("runner.jsonl"):
            if '"usage"' not in line: continue
            try: ev = json.loads(line)
            except ValueError: continue
            m = ev.get("message") if ev.get("type") == "assistant" else None
            if not isinstance(m, dict) or not m.get("usage"): continue
            t = tokens(m["usage"]); prev = self.seen.get(m.get("id"))
            if prev:                                        # the same call again: add only what grew (the output count)
                d = {k: max(t[k] - prev[k], 0) for k in t}
                if any(d.values()): add(self.tot, "producer", d, usd(m.get("model"), d), calls=0); self.seen[m["id"]] = {k: max(t[k], prev[k]) for k in t}
            else:
                add(self.tot, "producer", t, usd(m.get("model"), t)); self.seen[m.get("id")] = t
        for line in self.lines(CALLS):
            try: r = json.loads(line)
            except ValueError: continue
            add(self.tot, r.get("step", "other"), {k: r.get(k, 0) or 0 for k in ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")}, r.get("usd", 0) or 0)
        if (self.tot["usd"], self.tot["calls"], self.tot["output"]) != before or not os.path.exists(self.path):
            tmp = self.path + ".tmp"; json.dump({"total": self.tot, "offsets": self.off}, open(tmp, "w"), indent=1); os.replace(tmp, self.path)
        return self.tot

def summary(run_dir):
    """The ledger as saved, for the status object: totals, and per step."""
    try: t = json.load(open(os.path.join(run_dir, USAGE)))["total"]
    except Exception: return None
    return {"usd_estimate": round(t["usd"], 2), "calls": t["calls"], "input": t["input"], "output": t["output"], "cache_read": t["cache_read"],
            "cache_write": t["cache_write_5m"] + t["cache_write_1h"], "by_step": t["by_step"]}
