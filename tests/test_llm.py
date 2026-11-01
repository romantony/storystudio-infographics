"""infogen/llm.py (the Claude call wrapper and the job's token ledger) and infogen/wait.py, against a fake `claude`. Spends nothing.
Run: .venv/bin/python tests/test_llm.py"""
import json, os, stat, subprocess, sys, tempfile, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from infogen import llm

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

tmp = tempfile.mkdtemp(); os.chdir(tmp)

# Prices: Sonnet 5.5 is $2 in, $10 out, $0.20 cache read; cache writes 1.25x (5 m) and 2x (1 h) input.
t = llm.tokens({"input_tokens": 1_000_000, "output_tokens": 100_000, "cache_read_input_tokens": 10_000_000,
                "cache_creation_input_tokens": 300_000, "cache_creation": {"ephemeral_1h_input_tokens": 100_000}})
check("usage flattened, 1 h writes split out", t == {"input": 1_000_000, "output": 100_000, "cache_read": 10_000_000, "cache_write_5m": 200_000, "cache_write_1h": 100_000}, t)
check("usd from list prices", abs(llm.usd("claude-sonnet-5-5", t) - (2 + 1 + 2 + 0.5 + 0.4)) < 1e-9, llm.usd("claude-sonnet-5-5", t))
check("unknown model priced as Sonnet", llm.usd("claude-new-thing", t) == llm.usd("claude-sonnet-5-5", t))

# The producer's stream: a call streamed in two lines (same id, output growing), a second call, noise, a half-written line.
def ev(i, out): return json.dumps({"type": "assistant", "message": {"id": f"m{i}", "model": "claude-sonnet-5-5", "usage": {"input_tokens": 100, "output_tokens": out, "cache_read_input_tokens": 1000}}})
open("runner.jsonl", "w").write("\n".join([ev(1, 5), ev(1, 50), json.dumps({"type": "user", "usage": "x"}), ev(2, 20)]) + "\n" + ev(3, 9)[:30])
m = llm.Meter(tmp); tot = m.poll()
check("stream: one call per message id, output taken at its largest, half line left for later", tot["calls"] == 2 and tot["input"] == 200 and tot["output"] == 70 and tot["cache_read"] == 2000, tot)
with open("runner.jsonl", "a") as f: f.write(ev(3, 9)[30:] + "\n")
llm.log_call("analyst/qa", "claude-sonnet-5-5", {"usage": {"input_tokens": 7, "output_tokens": 3}, "total_cost_usd": 0.5, "num_turns": 4})
tot = llm.Meter(tmp).poll()
check("ledger resumes from its saved offsets and folds in the sessions' log", tot["calls"] == 4 and tot["output"] == 82 and tot["by_step"]["analyst/qa"]["usd"] == 0.5
      and tot["by_step"]["producer"]["calls"] == 3, tot)
s = llm.summary(tmp)
check("summary for the status object", s["calls"] == 4 and s["usd_estimate"] >= 0.5 and set(s["by_step"]) == {"producer", "analyst/qa"}, s)

# run(): the flags it passes, the log line, and a stop at the USD cap.
bin_ = os.path.join(tmp, "bin"); os.makedirs(bin_)
fake = os.path.join(bin_, "claude")
open(fake, "w").write("#!" + sys.executable + "\nimport json, os, sys\njson.dump(sys.argv[1:], open(os.environ['ARGS_OUT'], 'w'))\n"
                      "print(json.dumps({'type': 'result', 'subtype': os.environ.get('SUB', 'success'), 'result': 'hello' if os.environ.get('SUB') is None else '',"
                      " 'total_cost_usd': 0.25, 'num_turns': 2, 'usage': {'input_tokens': 10, 'output_tokens': 5}}))\n")
os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
os.environ["PATH"] = bin_ + os.pathsep + os.environ["PATH"]; os.environ["ARGS_OUT"] = os.path.join(tmp, "args.json")
open(llm.CALLS, "w").close()
r = llm.run("prompt", "claude-sonnet-5-5", "analyst/research", tools="Read Glob WebSearch", max_turns=40, max_usd=5)
a = json.load(open(os.environ["ARGS_OUT"]))
check("run: reply text returned", r == "hello", r)
check("run: only the named tools are loaded and allowed, with the USD cap and the shared prefix", a[a.index("--tools") + 1] == "Read,Glob,WebSearch"
      and a[a.index("--allowedTools") + 1:a.index("--allowedTools") + 4] == ["Read", "Glob", "WebSearch"] and a[a.index("--max-budget-usd") + 1] == "5"
      and "--exclude-dynamic-system-prompt-sections" in a, a)
rec = json.loads(open(llm.CALLS).read().splitlines()[-1])
check("run: session logged with its reported cost", rec["step"] == "analyst/research" and rec["usd"] == 0.25 and rec["input"] == 10, rec)
llm.run("p", "claude-opus-5-5", "scene3d", tools="", max_turns=2)
a = json.load(open(os.environ["ARGS_OUT"]))
check("run: no tools means no tool definitions at all", a[a.index("--tools") + 1] == "" and "--allowedTools" not in a and "--max-budget-usd" not in a, a)
os.environ["SUB"] = "error_max_budget_usd"
try: llm.run("p", "claude-sonnet-5-5", "analyst/qa", max_usd=1); check("run: stop at the cap raises", False)
except RuntimeError as e: check("run: stop at the cap raises", "cap" in str(e), e)
del os.environ["SUB"]

# wait: ready, exited (the background job died without writing its file), waiting (timeout).
W = [sys.executable, "-m", "infogen", "wait"]; env = dict(os.environ, PYTHONPATH=ROOT)
bg = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1); open('done.json', 'w').write('{}')"])
t0 = time.time(); p = subprocess.run(W + ["done.json", "--pid", str(bg.pid)], capture_output=True, text=True, env=env)
check("wait: returns when the file appears", p.returncode == 0 and json.loads(p.stdout)["result"] == "ready" and time.time() - t0 < 10, p.stdout + p.stderr)
bg = subprocess.Popen([sys.executable, "-c", "pass"]); bg.wait()
p = subprocess.run(W + ["never.json", "--pid", str(bg.pid)], capture_output=True, text=True, env=env)
check("wait: says so when the process exited without the file", p.returncode == 1 and json.loads(p.stdout)["result"] == "exited", p.stdout + p.stderr)
p = subprocess.run(W + ["never.json", "--timeout", "1"], capture_output=True, text=True, env=env)
check("wait: times out with 'waiting'", p.returncode == 2 and json.loads(p.stdout)["missing"] == ["never.json"], p.stdout + p.stderr)

print("\nALL PASSED" if not fails else f"\n{fails} FAILED"); sys.exit(1 if fails else 0)
