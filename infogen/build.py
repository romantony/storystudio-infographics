"""Build the long 16:9 video (script/script.json) or a 9:16 Short (shorts/<id>/script.json) from scene descriptions.
python3 -m infogen build [--short <id>] [--stills] [--preview] [--run]

  (no flag)   lay out only: timings, beats and render jobs; prints the scene list and total length
  --stills    one still per scene (at 70 % of its length, or after its last reveal) plus build/stills_<name>.jpg contact sheet: cheap, use it to review
  --preview   the whole video at half size (out/<slug>.preview.mp4)
  --run       the full-size video: out/<slug>.mp4, or shorts/<id>/out/<id>.mp4
Needs narration first (infogen tts; infogen timings for captions and cue-synced reveals). Rendered scenes are cached by
content in build/scenes, so changing one scene re-renders only that scene.

script.json: {"title", "slug", "narrator_voice", "bgm": "<asset id or path>", "captions": false (long) / true (Shorts),
              "series", "next", "endcard": true, "scenes": [...]}
scene: {"n": 1, "narration": "...", "type": "<template>", ...template fields..., "cut": "whip" | "hard" | "fade",
        "seconds": minimum length, "hold": extra seconds, "timecard": "DAY 1 · 03:00" (stays on later scenes until changed or set to ""),
        "chapter": "Chapter title (long video)", "sfx": [{"name": "ding", "at": 1.2 | "cue": "word", "volume": 0.4}],
        "verify": true, "verify_note": "..."}
Every revealable item (bar, list row, pin, route, highlighted country, timeline event, versus row, cast member,
callout) can carry "cue": "word or phrase from the narration" to appear when it is spoken, or "at": seconds.
Templates and their fields: docs/SCENES.md."""
import json, os, re, subprocess, sys, wave
import numpy as np
from . import captions, render, sfx, style as STY, timing
from .common import ASSETS, FPS, dur, find_asset, load, mkdirs
from .narration import paths

TYPES = {"illustration", "bar_chart", "line_chart", "donut", "counter", "icons", "versus", "timeline", "list", "map", "title", "timecard", "text", "endcard", "clip"}
META = {"n", "narration", "voice", "verify", "verify_note", "seconds", "hold", "sfx", "chapter", "notes"}
PRODUCED = ["Produced @ https://ai-storystudio.com · https://agent.ai-storystudio.com"]
SR = 48000

def items_of(s):
    t = s["type"]
    if t == "illustration": return list(s.get("cast", [])) + list(s.get("callouts", []))
    if t in ("bar_chart", "list"): return s.get("items", [])
    if t == "line_chart": return [s, s.get("annotate") or {}]
    if t == "donut": return [s] + list(s.get("items", []))
    if t == "counter": return [s, {"cue": s.get("sub_cue")}]
    if t == "icons": return [s, {"cue": s.get("highlight_cue")}]
    if t == "versus": return [s.get("a", {}), s.get("b", {})] + list(s.get("rows", []))
    if t == "timeline": return s.get("events", [])
    if t == "map": return [h if isinstance(h, dict) else {} for h in s.get("highlight", [])] + list(s.get("pins", [])) + list(s.get("routes", []))
    return []

def default_beats(s, L):
    t = s["type"]; it = items_of(s); n = len(it)
    def spread(k, start, end):
        end = max(start + 0.3, end)
        return [start] if k == 1 else [start + (end - start) * i / (k - 1) for i in range(k)]
    if not n: return []
    if t == "line_chart":
        d = max(1.6, L * 0.45); pts = s.get("points", []); an = (s.get("annotate") or {}).get("at", len(pts) - 1)
        return [0.5, 0.5 + d * (an / max(len(pts) - 1, 1)) + 0.2]
    if t == "donut": return [0.4] + [0.65 + 0.3 * i for i in range(n - 1)]
    if t == "counter": return [0.3, 1.5]
    if t == "icons": return [0.3, 0.9 + 0.02 * int(s.get("total", 20))]
    if t == "versus": return [0.2, 0.5] + spread(n - 2, 0.95, L * 0.6) if n > 2 else [0.2, 0.5]
    span = {"illustration": 0.45, "list": 0.75, "timeline": 0.8, "map": 0.65}.get(t, 0.55)
    return spread(n, 0.4, L * span)

def resolve(v, what, exts=("png", "jpg", "jpeg", "webp")):
    p = find_asset(v, exts)
    if not p: sys.exit(f"{what}: asset not found: {v!r} (looked in {ASSETS}/cutouts and {ASSETS})")
    return p

def resolve_icons(o):
    """An icon that names an asset ("icon": "rocket_icon") becomes its path; emoji stay as they are."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "icon" and isinstance(v, str) and re.fullmatch(r"[A-Za-z0-9_\-./]+", v) and find_asset(v): o[k] = find_asset(v)
            else: resolve_icons(v)
    elif isinstance(o, list):
        for x in o: resolve_icons(x)

def scene_props(s, W, H, L, beats, cut, st, label):
    p = {k: v for k, v in json.loads(json.dumps(s)).items() if k not in META}
    t = p["type"]
    if t == "clip" and not find_asset(p.get("clip") or p.get("src"), ("mp4", "webm", "mov")) and find_asset(p.get("clip"), ("png", "jpg", "jpeg", "webp")):
        # an animated frame whose clip was not made (over the cap, or the camera moved): show the still frame instead
        print(f"{label}: no clip {p['clip']!r}, showing the still frame", flush=True)
        p = {"type": "illustration", "image": p["clip"], "move": p.get("move", "zoom_in"), **{k: p[k] for k in ("timecard", "ambient") if p.get(k)}}; t = "illustration"
    if t not in TYPES: sys.exit(f"{label}: unknown type {t!r} (use one of {', '.join(sorted(TYPES))})")
    if p.get("image"): p["image"] = resolve(p["image"], label)
    elif t == "illustration": sys.exit(f"{label}: an illustration needs \"image\"")
    for c in p.get("cast", []): c["src"] = resolve(c.get("src") or c.get("id"), f"{label} cast")
    for side in ("a", "b"):
        if isinstance(p.get(side), dict) and p[side].get("image") and find_asset(p[side]["image"]): p[side]["image"] = find_asset(p[side]["image"])
    if t == "clip":
        p["src"] = resolve(p.get("clip") or p.get("src"), label, ("mp4", "webm", "mov")); p["clip_seconds"] = round(dur(p["src"]), 3)
    for a in p.get("animated", []):
        if a.get("lottie"): a["lottie"] = resolve(a["lottie"], f"{label} animated", ("json",))
    resolve_icons(p)
    p.update(width=W, height=H, fps=FPS, seconds=round(L, 4), beats=[round(b, 3) for b in beats], cut=cut, palette=st["palette"])
    if st.get("logo") and os.path.exists(st["logo"]): p["logo"] = st["logo"]
    return p

def write_wav(path, x):
    x = np.clip(x, -1, 1); w = wave.open(path, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((x * 32767).astype("<i2").tobytes()); w.close()

def read_wav(path):
    w = wave.open(path); n = w.getnframes(); ch = w.getnchannels(); d = np.frombuffer(w.readframes(n), "<i2").astype(np.float32) / 32767
    d = d.reshape(-1, ch); w.close()
    return d if ch == 2 else np.repeat(d, 2, axis=1)

def main(cmd, argv):
    sid = argv[argv.index("--short") + 1] if "--short" in argv else None
    short = bool(sid); preview = "--preview" in argv; stills = "--stills" in argv; go = "--run" in argv or preview
    sp, ad, wd = paths(sid); script = load(sp); st = STY.load()
    W, H = (1080, 1920) if short else (1920, 1080)
    if preview: W, H = W // 2, H // 2
    name = sid or script["slug"]; B = f"shorts/{sid}/build" if short else "build"; OUT = f"shorts/{sid}/out" if short else "out"
    mkdirs(B, OUT, "build/scenes", f"{B}/aud")
    pad = 0.2 if short else 0.45
    scenes = [dict(s) for s in script["scenes"]]
    if script.get("endcard", True):
        scenes.append({"n": 9999, "type": "endcard", "seconds": 2.5 if short else 5, "series": script.get("series", ""), "next": script.get("next"), "lines": PRODUCED})
    tl, jobs, words_all, events, warn = [], [], [], [], []
    t0, prev, timecard, est = 0.0, None, None, 0
    for s in scenes:
        n = s["n"]; label = f"{'short ' + sid if short else 'long'} scene {n}"; text = (s.get("narration") or "").strip()
        a = f"{ad}/s{n}.wav" if text else None
        if a and not os.path.exists(a): sys.exit(f"{label}: no narration audio {a} (run: python3 -m infogen tts{' --short ' + sid if short else ''})")
        alen = dur(a) if a else 0.0
        L = max(alen + pad if a else 0, float(s.get("seconds", 0)), 1.6) + float(s.get("hold", 0))
        frames = int(round(L * FPS)); L = frames / FPS
        wj = f"{wd}/s{n}.json"
        if text and not os.path.exists(wj): est += 1
        wl = timing.words(text, wj, alen)
        # beats: explicit "at", else the cue word, else the default spread
        bs = default_beats(s, L)
        for i, it in enumerate(items_of(s)):
            if not isinstance(it, dict): continue
            if it.get("at") is not None and it is not s: bs[i] = float(it["at"])
            elif it.get("cue"):
                c = timing.cue(wl, it["cue"])
                if c is None: warn.append(f"{label}: cue {it['cue']!r} is not in the narration")
                else: bs[i] = max(0.15, c - 0.12)
        # cuts: a continuing camera on the same picture is a hard cut, anything else whips in
        cut = s.get("cut") or ("fade" if prev is None else "hard" if (prev.get("type") == "illustration" and prev.get("image") == s.get("image") and s["type"] == "illustration") else "whip")
        if "timecard" in s: timecard = s["timecard"] or None
        s2 = dict(s)
        if timecard and s["type"] in ("illustration", "clip", "map") and "timecard" not in s: s2["timecard"] = timecard
        props = scene_props(s2, W, H, L, bs, cut, st, label)
        out = f"build/scenes/{W}x{H}_{s['type']}_{render.fingerprint(props)}.mp4"
        jobs.append({"props": props, "out": out, "still": False})
        tl.append(dict(scene=n, start=round(t0, 3), end=round(t0 + L, 3), frames=frames, type=s["type"], image=props.get("image"), chapter=s.get("chapter"), audio=a, video=out))
        words_all += [(w, t0 + x, t0 + y) for w, x, y in wl]
        # sound effects
        if cut == "whip": events.append(("whoosh", t0, 0.32))
        if s["type"] in ("title", "timecard"): events.append(("thud", t0 + 0.05, 0.5))
        if s["type"] not in ("line_chart", "title", "timecard", "text"):
            for b in bs: events.append(("pop", t0 + b, 0.22))
        if s["type"] == "counter": events.append(("ding", t0 + bs[0] + min(1.8, L * 0.4), 0.3))
        if s["type"] == "endcard": events += [("pop", t0 + 0.1 + 0.15 * i, 0.3) for i in range(3)]
        for e in s.get("sfx", []):
            at = e.get("at") if e.get("at") is not None else timing.cue(wl, e.get("cue"))
            if at is None: warn.append(f"{label}: sfx {e.get('name')} has no time"); continue
            events.append((e["name"], t0 + float(at), float(e.get("volume", 0.4))))
        t0 += L; prev = s
    total = t0
    if est: warn.append(f"{est} scene(s) without word timings: cues and captions are estimated (run: python3 -m infogen timings{' --short ' + sid if short else ''})")
    json.dump(tl, open(f"{B}/timeline.json", "w"), indent=1)
    print(f"{name}: {len(tl)} scenes, {total:.1f} s ({total / 60:.1f} min), {W}x{H}")
    print("  " + " ".join(f"{e['scene']}:{e['type']}:{e['end'] - e['start']:.1f}" for e in tl))
    for w in warn: print("WARNING", w)
    nwarn = len(warn)

    if stills:
        sj = [{"props": j["props"], "out": f"{B}/stills/s{e['scene']}_{os.path.basename(j['out'])[:-4]}.jpg", "still": True, "frame": min(e["frames"] - 1, int(max(e["frames"] * 0.7, (max(j["props"]["beats"] or [0]) + 1.3) * FPS)))} for j, e in zip(jobs, tl)]
        mkdirs(f"{B}/stills"); render.run(sj, label="stills")
        from .sheet import sheet
        sheet([j["out"] for j in sj], f"build/stills_{name}.jpg", cols=4 if not short else 6, cell=(480, 270) if not short else (216, 384), labels=[f"{e['scene']} {e['type']}" for e in tl])
    if not go: return

    render.run(jobs, label="scenes")
    open(f"{B}/list.txt", "w").write("".join(f"file '{os.path.abspath(j['out'])}'\n" for j in jobs))
    sh = lambda *c: subprocess.run(list(c), check=True)
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{B}/list.txt", "-c", "copy", f"{B}/base.mp4")
    # narration track: each scene's audio padded to exactly its frame length
    alist = []
    for e in tl:
        p = f"{B}/aud/s{e['scene']}.wav"; L = e["frames"] / FPS
        if e["audio"]: sh("ffmpeg", "-y", "-loglevel", "error", "-i", e["audio"], "-af", f"aresample={SR},apad=whole_dur={L:.4f},atrim=0:{L:.4f}", "-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", p)
        else: sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-t", f"{L:.4f}", "-c:a", "pcm_s16le", p)
        alist.append(f"file '{os.path.abspath(p)}'\n")
    open(f"{B}/alist.txt", "w").write("".join(alist))
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{B}/alist.txt", "-c", "copy", f"{B}/narration.wav")
    # effects track, mixed in numpy
    fx = np.zeros((int(total * SR) + SR, 2), np.float32); cache = {}
    for nm, at, vol in events:
        if nm not in sfx.SOUNDS: warn.append(f"unknown sfx {nm}"); continue
        x = cache.setdefault(nm, read_wav(sfx.path(nm))); i = max(0, int(at * SR)); j = min(len(fx), i + len(x))
        fx[i:j] += x[:j - i] * vol
    write_wav(f"{B}/sfx.wav", fx[:int(total * SR)])
    # music under it all, ducked by the narration
    bgm = script.get("bgm") or (f"{ASSETS}/bgm_{sid}.mp3" if short else f"{ASSETS}/bgm_long.mp3")
    bgm = find_asset(bgm, ("mp3", "wav", "m4a")) if bgm else None
    lufs = -13 if short else -14
    tail = f"loudnorm=I={lufs}:TP=-1.5:LRA=11,aresample={SR},alimiter=limit=0.89:level=disabled[a]"
    if bgm:
        fc = (f"[2:a]aresample={SR},volume={0.2 if short else 0.16},afade=t=in:d=1.5,afade=t=out:st={max(total - 3, 0):.2f}:d=3,atrim=0:{total:.3f}[bg];"
              f"[0:a]asplit=2[vo][sc];[bg][sc]sidechaincompress=threshold=0.03:ratio=6:attack=20:release=500[duck];[vo][1:a][duck]amix=inputs=3:duration=first:normalize=0," + tail)
        ins = ["-i", f"{B}/narration.wav", "-i", f"{B}/sfx.wav", "-stream_loop", "-1", "-i", bgm]
    else:
        warn.append("no music: " + (f"{script.get('bgm')} not found" if script.get("bgm") else f"{ASSETS}/bgm_{'long' if not short else sid}.mp3 missing"))
        fc = "[0:a][1:a]amix=inputs=2:duration=first:normalize=0," + tail
        ins = ["-i", f"{B}/narration.wav", "-i", f"{B}/sfx.wav"]
    sh("ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", fc, "-map", "[a]", "-c:a", "aac", "-b:a", "192k", f"{B}/mix.m4a")
    video = f"{B}/base.mp4"
    if script.get("captions", short) and words_all:
        nev = captions.ass(words_all, W, H, short, f"{B}/caps.ass")
        sh("ffmpeg", "-y", "-loglevel", "error", "-i", video, "-vf", f"ass={B}/caps.ass", "-c:v", "libx264", "-crf", "19", "-preset", "veryfast", "-pix_fmt", "yuv420p", f"{B}/captioned.mp4")
        video = f"{B}/captioned.mp4"; print("caption events:", nev)
    final = f"{OUT}/{name}{'.preview' if preview else ''}.mp4"
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", f"{B}/mix.m4a", "-map", "0:v", "-map", "1:a", "-c", "copy", "-shortest", "-movflags", "+faststart", final)
    print(final, round(dur(final), 1), "s")
    for w in warn[nwarn:]: print("WARNING", w)
