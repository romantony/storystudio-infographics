"""The Quality and Research Analysts (infogen/analysts.py): prompts, reports, and the rubrics that improve after every
run, against a stub analyst. Spends nothing. Run: .venv/bin/python tests/test_analysts.py"""
import json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

tmp = tempfile.mkdtemp(); rub = os.path.join(tmp, "rubrics"); run = os.path.join(tmp, "run"); os.makedirs(f"{run}/script"); os.makedirs(f"{run}/research")
os.environ["INFOGEN_RUBRICS_DIR"] = rub
from infogen import analysts as A

# The stub analyst saves the prompt it was given and replies with the JSON in $REPLY (fenced, as a model often does).
stub = os.path.join(tmp, "stub.py")
open(stub, "w").write("import os, sys\nopen(os.environ['PROMPT_OUT'], 'w').write(sys.stdin.read())\nprint('Here is my review:\\n```json\\n' + open(os.environ['REPLY']).read() + '\\n```')\n")
env = {**os.environ, "PYTHONPATH": ROOT, "INFOGEN_ANALYST_CMD": f"{sys.executable} {stub}", "PROMPT_OUT": os.path.join(tmp, "prompt.txt"), "REPLY": os.path.join(tmp, "reply.json")}
def analyst(*args, reply):
    json.dump(reply, open(env["REPLY"], "w"))
    return subprocess.run([sys.executable, "-m", "infogen", "analyst", *args], cwd=run, capture_output=True, text=True, env=env)

json.dump({"request_id": "job-1", "kind": "video", "model": "claude-sonnet-5-5"}, open(f"{run}/request.json", "w"))
json.dump({"scenes": []}, open(f"{run}/script/script.json", "w")); open(f"{run}/research/sources.md", "w").write("# Sources\n")

REPLY = {"summary": "Solid, but the hook is slow.",
         "scores": [{"id": "Q01", "result": "fail", "note": "scene 1 opens on background"}, {"id": "Q02", "result": "pass"}, {"id": "Q03", "result": "na"}],
         "findings": [{"severity": "must_fix", "where": "scene 1", "issue": "slow open", "fix": "open on the blockade"},
                      {"severity": "suggestion", "where": "scene 9", "issue": "x", "fix": "y"}, {"severity": "nonsense", "issue": "dropped"}],
         "new_guidelines": [{"area": "hook", "check": "The narrator names the stakes for ordinary people within the first three scenes.", "why": "Stakes make it personal."},
                            {"area": "hook", "check": "The first 15 seconds open on the most dramatic moment or consequence, then state the question.", "why": "dup"}]}
r = analyst("qa", reply=REPLY)
out = json.loads(r.stdout) if r.returncode == 0 else {}
check("qa: runs and reports counts", r.returncode == 0 and out["findings"] == {"must_fix": 1, "should_fix": 0, "suggestion": 1} and out["criteria_failed"] == 1 and out["rubric"] == "script", (r.stdout[-500:], r.stderr[-500:]))
p = open(env["PROMPT_OUT"]).read()
check("qa: prompt has the role, every active criterion and the files", p.startswith("# Quality Analyst") and "Q12" in p and "- script/script.json" in p and "- research/sources.md" not in p, p[-600:])
R = json.load(open(f"{rub}/script.json"))
by = {c["id"]: c for c in R["criteria"]}
check("rubric: seeded, scores counted (na not counted)", (by["Q01"]["checked"], by["Q01"]["failed"], by["Q01"]["last_failed"], by["Q02"]["checked"], by["Q03"]["checked"]) == (1, 1, "job-1", 1, 0), by["Q01"])
check("rubric: the new guideline added from this job, the near-duplicate not", by.get("Q13", {}).get("source") == "job-1" and "Q14" not in by and out["guidelines_added"] == ["Q13"] and R["version"] == 2, [c["id"] for c in R["criteria"]])
rep = json.load(open(f"{run}/review/qa.json")); md = open(f"{run}/review/qa.md").read()
check("report: json drops unknown severities, md lists findings, failures and guidelines",
      len(rep["findings"]) == 2 and "## must fix (1)" in md and "Q01: scene 1 opens" in md and "names the stakes" in md, md)
hist = [json.loads(l) for l in open(f"{rub}/history.jsonl")]
check("history: one line per recorded review", hist[-1]["job"] == "job-1" and hist[-1]["failed"] == ["Q01"] and hist[-1]["added"] == ["Q13"], hist)

r = analyst("qa", "--verify", reply={**REPLY, "new_guidelines": [{"area": "x", "check": "A completely different rule about map framing and label sizes.", "why": "y"}]})
R2 = json.load(open(f"{rub}/script.json"))
check("verify: writes qa_verify, records nothing", r.returncode == 0 and os.path.exists(f"{run}/review/qa_verify.md") and R2["version"] == 2 and len(R2["criteria"]) == 13, r.stderr[-300:])
check("verify: the prompt carries the first pass's findings", "second pass" in open(env["PROMPT_OUT"]).read())

r = analyst("research", reply={"summary": "ok", "scores": [{"id": "R01", "result": "pass"}], "findings": [], "new_guidelines": []})
check("research: the research rubric, with the sources among the files", r.returncode == 0 and json.loads(r.stdout)["rubric"] == "research" and "- research/sources.md" in open(env["PROMPT_OUT"]).read(), r.stdout[-300:])

json.dump({"request_id": "series-1", "kind": "series_plan"}, open(f"{run}/request.json", "w")); os.makedirs(f"{run}/series"); json.dump({}, open(f"{run}/series/series.json", "w"))
r = analyst("qa", reply={"summary": "ok", "scores": [], "findings": [], "new_guidelines": []})
check("series plan: both analysts use the series rubric", r.returncode == 0 and json.loads(r.stdout)["rubric"] == "series" and "P01" in open(env["PROMPT_OUT"]).read(), r.stdout[-300:])

json.dump({"request_id": "job-2", "kind": "video"}, open(f"{run}/request.json", "w"))
open(env["REPLY"], "w").write("I could not finish.")
bad = subprocess.run([sys.executable, "-m", "infogen", "analyst", "qa"], cwd=run, capture_output=True, text=True, env={**env, "INFOGEN_ANALYST_CMD": "echo 'no json here'"})
check("a reply with no JSON fails clearly", bad.returncode != 0 and "not a JSON report" in bad.stderr, bad.stderr[-300:])

# parallel jobs: no lost update
procs = []
for i in range(4):
    rep_i = os.path.join(tmp, f"reply{i}.json")
    json.dump({"summary": "", "scores": [{"id": "Q02", "result": "fail"}], "findings": [],
               "new_guidelines": [{"area": "t", "check": f"Rule number {i}: {' '.join(['alpha', 'beta', 'gamma', 'delta'][:i + 1])} distinct wording {i * 1000}", "why": ""}]}, open(rep_i, "w"))
    procs.append(subprocess.Popen([sys.executable, "-m", "infogen", "analyst", "qa"], cwd=run, env={**env, "REPLY": rep_i, "PROMPT_OUT": rep_i + ".p"}, stdout=subprocess.DEVNULL))
for pr in procs: pr.wait()
R3 = json.load(open(f"{rub}/script.json")); by = {c["id"]: c for c in R3["criteria"]}
check("parallel: all 4 reviews counted, all 4 guidelines kept", by["Q02"]["failed"] == 4 and len(R3["criteria"]) == 17 and R3["version"] == 6, (by["Q02"], len(R3["criteria"]), R3["version"]))

# retirement: over MAX_ACTIVE, the most-checked never-failed criteria go first
A.MAX_ACTIVE = 15
for c in R3["criteria"]: c["checked"], c["failed"] = (20, 0) if c["id"] in ("Q04", "Q05", "Q06") else (c["checked"], c["failed"] or 1)
R3["criteria"][4]["checked"] = 30   # Q05 checked most
json.dump(R3, open(f"{rub}/script.json", "w"))
A.record("script", {"scores": [], "new_guidelines": []}, "job-3")
st = {c["id"]: c["status"] for c in json.load(open(f"{rub}/script.json"))["criteria"]}
check("retire: 17 active over a cap of 15 retires Q05 then Q04/Q06's first", [k for k, v in st.items() if v == "retired"] in (["Q04", "Q05"], ["Q05", "Q04"]) and sum(v == "active" for v in st.values()) == 15, st)

r = subprocess.run([sys.executable, "-m", "infogen", "rubric", "show", "script"], cwd=run, capture_output=True, text=True, env=env)
check("rubric show: active criteria with their record", "Q01 [hook]" in r.stdout and "(failed 1 of 1)" in r.stdout and "Q05" not in r.stdout, r.stdout[:400])

print("ALL OK" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
