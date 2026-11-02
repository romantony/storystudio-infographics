"""infogen/harness.py: cache replay, checks, targeted repair, ladder, read-only mode, and the analyst/3D wiring. Spends nothing.
Run: python tests/test_harness.py"""
import os, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp(); os.chdir(tmp); os.environ["INFOGEN_LLM_CACHE_DIR"] = os.path.join(tmp, "cache")
from infogen import harness as H, llm
fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}")); fails += 0 if cond else 1

calls = []
def fake(replies, usd=0.5):
    it = iter(replies)
    def ask(text, model):
        calls.append((model, text)); llm.LAST[0] = {"usd": usd}; return next(it)
    return ask
def need_ok(reply): return [] if "OK" in reply else [H.Violation("t.ok", "reply", "must contain OK")]

r = H.call_checked("s", "q", "m1", [need_ok], ask=fake(["bad", "OK done"]))
check("one failed check is repaired once", r.passed and r.repairs == 1 and len(calls) == 2 and abs(r.usd - 1.0) < 1e-9, (r, calls))
check("repair turn carries the original, the reply and the rule line", "q" in calls[1][1] and "bad" in calls[1][1] and "[t.ok] reply: must contain OK" in calls[1][1])
n = len(calls); r2 = H.call_checked("s", "q", "m1", [need_ok], ask=fake([]))
check("same request replays with no model call", r2.cached and r2.reply == "OK done" and len(calls) == n and r2.usd == 0, r2)
n = len(calls); H.call_checked("s", "q", "m1", [need_ok], extra={"f": "changed"}, ask=fake(["OK"]))
check("a changed input changes the key", len(calls) == n + 1)

calls.clear(); r = H.call_checked("f", "q", "m1", [need_ok], ask=fake(["bad"] * 5))
check("still failing after 2 repairs: kept with violations, job goes on", not r.passed and r.repairs == 2 and len(calls) == 3, r)
n = len(calls); r = H.call_checked("f", "q", "m1", [need_ok], ask=fake([]))
check("a failure is cached too", r.cached and not r.passed and len(calls) == n)

calls.clear(); r = H.call_checked("l", "q", ["haiku", "sonnet"], [need_ok], repairs=0, ask=fake(["bad", "OK"]))
check("ladder escalates when the cheap model fails", r.passed and r.escalated and r.model == "sonnet" and [c[0] for c in calls] == ["haiku", "sonnet"], (r, calls))

def boom(reply): raise ValueError("x")
r = H.call_checked("c", "q", "m1", [boom], ask=fake(["whatever"]))
check("a crashing check is a warning, not a crash", r.passed and r.violations[0].severity == "warning", r)

os.environ["INFOGEN_LLM_CACHE"] = "read"
try: H.call_checked("new", "q", "m1", [], ask=fake([])); ok = False
except RuntimeError: ok = True
check("read-only mode: a miss is an error", ok)
os.environ["INFOGEN_LLM_CACHE"] = "off"; n = len(calls); H.call_checked("s", "q", "m1", [need_ok], ask=fake(["OK"]))
check("cache off always asks", len(calls) == n + 1)

# analyst checks
from infogen import analysts as A
rub = {"criteria": [{"id": "Q01", "status": "active"}, {"id": "Q02", "status": "active"}, {"id": "Q09", "status": "retired"}]}
chk = A.review_checks(rub)[0]
good = '{"summary":"s","scores":[{"id":"Q01","result":"pass"},{"id":"Q02","result":"na"}],"findings":[{"severity":"must_fix","where":"scene 1","issue":"i","fix":"f"}]}'
check("complete report passes", chk(good) == [])
rules = {v.rule_id for v in chk('{"summary":"","scores":[{"id":"Q01","result":"ok"}],"findings":[{"severity":"must_fix","where":"x","issue":"i"},{"severity":"nonsense"}]}')}
check("incomplete report fails the right rules", rules == {"review.summary", "review.scores_missing", "review.score_value", "review.finding_field", "review.severity"}, rules)
check("non-JSON reply fails", chk("sorry")[0].rule_id == "review.json")
print("\nALL CHECKS PASSED" if not fails else f"\n{fails} FAILED"); sys.exit(1 if fails else 0)
