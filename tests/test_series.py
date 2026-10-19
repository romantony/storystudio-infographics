"""The series plan (infogen/series.py): checks against the request, publish dates, links, the overview. Spends nothing.
Run: .venv/bin/python tests/test_series.py"""
import datetime as dt, json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from infogen import series as SE

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

REQ = {"series_plan": {"episodes": 4, "per_week": 3, "start_date": "2026-11-02"}, "shorts": {"count": 3, "angles": ["hook", "stat", "twist"]},
       "visuals": {"style": "paper", "cast": {"guide": "a woman in a navy blazer"}}}
ep = lambda n, **k: {"n": n, "title": f"Title {n}", "topic": f"Topic {n}", "format": ["true_story", "versus", "what_if", "explainer"][n % 4], "era": "Berlin, 1948",
                     "synopsis": f"Episode {n}: the angle, the question it answers and the beats to cover, in order.", **k}
PLAN = {"name": "Flashpoints", "premise": "Moments the Cold War nearly turned hot.", "cast": {"guide": "a woman in a navy blazer"}, "episodes": [ep(i) for i in range(1, 5)]}

check("valid plan: no errors", SE.check(PLAN, REQ) == ([], []), SE.check(PLAN, REQ))
check("dates: 3 a week from Monday = Mon, Wed, Fri", SE.dates(6, 3, dt.date(2026, 11, 2)) == ["2026-11-02", "2026-11-04", "2026-11-06", "2026-11-09", "2026-11-11", "2026-11-13"])
check("dates: 1 a week is weekly, 7 a week daily", SE.dates(2, 1, dt.date(2026, 11, 2)) == ["2026-11-02", "2026-11-09"] and SE.dates(3, 7, dt.date(2026, 11, 2))[-1] == "2026-11-04")
check("no start date: the next Monday", SE.next_monday(dt.date(2026, 10, 21)) == dt.date(2026, 10, 26))
bad = json.loads(json.dumps(PLAN))
bad["episodes"][1].update(n=5, synopsis="short", format="podcast", topic="topic 1"); bad["episodes"].pop(); bad["cast"] = {"guide": "someone else"}
err, _ = SE.check(bad, REQ)
for name, needle in [("episode count", "3 episodes, the request asks for 4"), ("order", '"n" must be 2'), ("short synopsis", "synopsis must be 40"),
                     ("unknown format", "format must be one of"), ("duplicate topic", "same topic as episode 1"), ("request cast changed", "keep the request's description")]:
    check(f"check catches: {name}", any(needle in e for e in err), err)
check("check: formats limited by the request", any("format must be one of versus" in e for e in SE.check(PLAN, {**REQ, "series_plan": {**REQ["series_plan"], "formats": ["versus"]}})[0]))
same = {**PLAN, "episodes": [ep(i, format="explainer") for i in range(1, 7)]}
check("check: one format across 6 episodes is a warning", any("only 1 format" in w for w in SE.check(same, {**REQ, "series_plan": {"episodes": 6}})[1]))

AUTO = {**REQ, "visuals": {"style": "auto", "palette": "auto", "cast": REQ["visuals"]["cast"]}}
err, _ = SE.check(PLAN, AUTO)
check("auto: the plan must choose style, palette and say why", any('choose "style"' in e for e in err) and any('choose "palette"' in e for e in err) and any("style_why" in e for e in err), err)
picked = {**PLAN, "style": "paper", "palette": {"accent": "#9C3D22", "landHi": "#9C3D22"}, "style_why": "1940s-60s history"}
check("auto: a readable choice passes", SE.check(picked, AUTO) == ([], []), SE.check(picked, AUTO))
check("auto: an unreadable one is refused", any("text on bg" in e for e in SE.check({**picked, "palette": {"text": "#EEE8DD"}}, AUTO)[0]))
check("not auto: the plan may not change the request's style", any('"style": the request sets paper' in e for e in SE.check({**PLAN, "style": "noir_vector"}, REQ)[0]))
filled = SE.fill(json.loads(json.dumps(picked)), {**AUTO, "visuals": {"style": "auto", "palette": {"accent2": "#123456"}, "cast": {}}})
check("fill: the chosen style kept, the request's fixed colours merged in and winning", filled["style"] == "paper" and filled["palette"] == {"accent": "#9C3D22", "landHi": "#9C3D22", "accent2": "#123456"}, filled.get("palette"))

tmp = tempfile.mkdtemp(); os.chdir(tmp); os.makedirs("series")
json.dump(REQ, open("request.json", "w")); json.dump(PLAN, open("series/series.json", "w"))
r = subprocess.run([sys.executable, "-m", "infogen", "series", "series/series.json"], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": ROOT})
P = json.load(open("series/series.json"))
check("command: fills dates, next titles, Shorts and style", r.returncode == 0 and [e["publish_date"] for e in P["episodes"]] == ["2026-11-02", "2026-11-04", "2026-11-06", "2026-11-09"]
      and [e["next_title"] for e in P["episodes"]] == ["Title 2", "Title 3", "Title 4", None] and P["episodes"][0]["shorts"] == ["hook", "stat", "twist"]
      and P["style"] == "paper" and P["episodes_per_week"] == 3, (r.stdout[-400:], r.stderr[-400:]))
md = open("series/series.md").read()
check("command: the overview as a PDF too", open("series/series.pdf", "rb").read(5) == b"%PDF-" and os.path.getsize("series/series.pdf") > 2000)
check("command: overview with the schedule and every synopsis", "| 1 | 2026-11-02 | Title 1 | versus | Berlin, 1948 |" in md and "## 4. Title 4" in md and "navy blazer" in md, md[:400])
json.dump(bad, open("series/series.json", "w"))
r = subprocess.run([sys.executable, "-m", "infogen", "series", "series/series.json"], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": ROOT})
check("command: errors exit 1 and leave the file alone", r.returncode == 1 and "publish_date" not in open("series/series.json").read(), r.stdout[-300:])

print("ALL OK" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
