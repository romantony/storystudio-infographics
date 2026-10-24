"""3D scene spec check and the Opus planner merge (infogen/scene3d.py). Spends nothing (the planner is mocked).
Run: .venv/bin/python tests/test_scene3d.py"""
import json, os, subprocess, sys, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from infogen import scene3d as S

fails = 0
def check(name, cond, got=None):
    global fails
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  got: {got}"))
    fails += 0 if cond else 1

bars = {"n": 1, "type": "bars3d", "narration": "America spends 916 billion, China 296.", "source": "SIPRI",
        "items": [{"label": "USA", "value": 916}, {"label": "China", "value": 296}]}
check("a good bars3d passes", S.check(bars) == [], S.check(bars))
check("bars3d with a text value is an error", S.check({**bars, "items": [{"label": "A", "value": "lots"}]}) != [])
check("camera preset ok, unknown preset rejected", S.check({**bars, "camera": "push_in"}) == [] and S.check({**bars, "camera": "spin_wildly"}) != [])
check("custom camera needs [from, to] pairs", S.check({**bars, "camera": {"az": [0, 20], "el": [10, 30]}}) == [] and S.check({**bars, "camera": {"az": [0]}}) != [])
check("globe needs something to show", S.check({"type": "globe"}) != [])
check("globe lat out of range", S.check({"type": "globe", "pins": [{"lon": 10, "lat": 120}]}) != [])
check("network link to a missing node", S.check({"type": "network3d", "nodes": [{"id": "a"}, {"id": "b"}], "links": [{"from": "a", "to": "z"}]}) != [])
check("other scene types are not checked", S.check({"type": "bar_chart"}) == [])

# the planner may set camera, cues and colours; it cannot touch values, and a list of the wrong length is ignored
plan = {"camera": "rise", "items": [{"cue": "America", "highlight": True, "value": 1}, {"cue": "China", "label": "Hacked"}], "title": "x"}
out, notes = S.merge(bars, plan)
check("camera and cues applied", out["camera"] == "rise" and out["items"][0]["cue"] == "America" and out["items"][0]["highlight"] is True, out)
check("values, labels and title untouched", out["items"][0]["value"] == 916 and out["items"][1]["label"] == "China" and "title" not in out, out)
out, notes = S.merge(bars, {"items": [{"cue": "x"}]})
check("wrong list length ignored with a note", "cue" not in out["items"][0] and notes, (out, notes))
check("parse reads a fenced reply", S.parse("sure\n```json\n{\"camera\": \"orbit\"}\n```") == {"camera": "orbit"})

# the command end to end, with the model mocked
d = tempfile.mkdtemp(); os.chdir(d); os.makedirs("script"); os.makedirs("audio", exist_ok=True)
from infogen.narration import paths
sp = paths(None)[0]; os.makedirs(os.path.dirname(sp) or ".", exist_ok=True)
json.dump({"slug": "t", "scenes": [bars]}, open(sp, "w"))
reply = os.path.join(d, "reply.txt"); open(reply, "w").write("```json\n" + json.dumps({"camera": {"az": [-10, 10], "el": [15, 30], "dist": [1.2, 0.9]}, "items": [{"cue": "America"}, {"cue": "China"}]}) + "\n```")
r = subprocess.run([sys.executable, "-m", "infogen", "scene3d", "1"], cwd=d, env={**os.environ, "PYTHONPATH": ROOT, "INFOGEN_SCENE3D_CMD": f"cat {reply}"}, capture_output=True, text=True)
got = json.load(open(sp))["scenes"][0]
check("scene3d command writes the plan back", r.returncode == 0 and got["camera"]["el"] == [15, 30] and got["items"][1]["cue"] == "China" and got["items"][1]["value"] == 296, (r.stdout, r.stderr, got))
open(reply, "w").write("```json\n{\"camera\": \"nonsense\"}\n```")
r = subprocess.run([sys.executable, "-m", "infogen", "scene3d", "1"], cwd=d, env={**os.environ, "PYTHONPATH": ROOT, "INFOGEN_SCENE3D_CMD": f"cat {reply}"}, capture_output=True, text=True)
check("a bad plan is rejected and the script is left alone", r.returncode != 0 and json.load(open(sp))["scenes"][0]["camera"]["el"] == [15, 30], (r.stdout, r.stderr))
sys.exit(1 if fails else 0)
