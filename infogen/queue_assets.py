"""Queue every generated asset from one file, resumably. Paid jobs are never submitted twice: job ids are kept in
build/queue_state.json and finished files are skipped.

python3 -m infogen queue assets.json [--only images,characters,bgm,ltx]

assets.json:
{ "project_id": "infographics_ep12",
  "images":     [{"id": "city_night", "prompt": "a city skyline at night, every window dark", "aspect": "16:9"}],
  "characters": [{"id": "hero_worried", "prompt": "{hero} looking worried, both hands on his head", "aspect": "9:16"}],
  "bgm":        [{"id": "bgm_long", "prompt": "...", "seconds": 120}],
  "ltx":        [{"id": "ltx_city_night", "image": "city_night", "prompt": "...", "secs": 5}] }
Prompts are wrapped in the series style (style.py): scenes in the illustration style, characters in the character style
on a flat green background, after which they are cut out automatically to <asset dir>/cutouts/<id>.png.
Name recurring people as {cast_id} so every image uses the same description from style.json.
Outputs land in the asset dir as <id>.png | .mp3 | .mp4."""
import json, os, sys, time
from . import cutout, ltx, rp, style as STY
from .common import ASSETS, find_asset, mkdirs
STATE = "build/queue_state.json"

def main(cmd, argv):
    if not argv: sys.exit(__doc__)
    spec = json.load(open(argv[0])); st_ = STY.load()
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else {"images", "characters", "bgm", "ltx"}
    mkdirs(ASSETS, f"{ASSETS}/cutouts", "build")
    st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    save = lambda: json.dump(st, open(STATE, "w"), indent=1)
    pid = spec.get("project_id") or os.path.basename(os.getcwd())
    path = lambda i, ext: f"{ASSETS}/{i}.{ext}"
    failed = []

    def fin(i, res, ext, urlkeys):
        e = st[i]
        if "error" in res: e["error"] = res["error"]; failed.append(i); save(); print("FAIL", i, res["error"], flush=True); return False
        url = next((res[k] for k in urlkeys if isinstance(res.get(k), str) and res[k].startswith("http")), None) \
            or next((v for v in res.values() if isinstance(v, str) and v.startswith("http")), None)
        if not url: e["error"] = "no url in output"; failed.append(i); save(); print("FAIL", i, "no url", flush=True); return False
        rp.download(url, path(i, ext)); e["url"] = url; e["file"] = path(i, ext); e.pop("error", None); save(); print("done", i, flush=True)
        return True

    qwen = lambda kind: (lambda it: ("qwen", {"model": "qwen", "prompt": STY.image_prompt(it["prompt"], st_, kind),
                                               "aspect_ratio": it.get("aspect", "9:16" if kind == "character" else "16:9"), "project_id": pid, "frame_id": it["id"]}))
    s1 = []
    if "images" in only: s1.append(("images", "png", ["image_url"], qwen("scene")))
    if "characters" in only: s1.append(("characters", "png", ["image_url"], qwen("character")))
    if "bgm" in only: s1.append(("bgm", "mp3", ["audio"], lambda it: ("bgm", {"mode": "bgm", "prompt": it["prompt"], "duration_s": it.get("seconds", 50), "steps": 20, "guidance": 7.0, "project_id": pid, "frame_id": it["id"]})))
    # submit everything before waiting on any of it, so cold endpoints warm up in parallel
    jobs1 = []
    for group, ext, urlkeys, build in s1:
        for it in spec.get(group, []):
            i = it["id"]
            if os.path.exists(path(i, ext)) and st.get(i, {}).get("file"): print("skip", i); continue
            if not st.get(i, {}).get("job") or st[i].get("error"):
                ep, inp = build(it); st[i] = {"ep": ep, "job": rp.submit(ep, inp), "group": group}; save(); print("queued", i, flush=True)
            jobs1.append((i, ext, urlkeys, group))
    res1 = rp.wait({i: (st[i]["ep"], st[i]["job"]) for i, _, _, _ in jobs1})
    for i, ext, urlkeys, group in jobs1:
        if fin(i, res1[i], ext, urlkeys) and group == "characters":
            out, kept = cutout.cut(path(i, ext), f"{ASSETS}/cutouts/{i}.png")
            print("cutout", out, f"kept {kept:.0%}", flush=True)
    for it in spec.get("characters", []):   # cut-outs for characters generated in an earlier run
        if os.path.exists(path(it["id"], "png")) and not os.path.exists(f"{ASSETS}/cutouts/{it['id']}.png"):
            cutout.cut(path(it["id"], "png"), f"{ASSETS}/cutouts/{it['id']}.png")

    # stage 2: LTX animations of finished images (ComfyUI Cloud)
    ljobs = {}
    if "ltx" in only:
        for it in spec.get("ltx", []):
            i = it["id"]
            if os.path.exists(path(i, "mp4")) and st.get(i, {}).get("file"): print("skip", i); continue
            if not st.get(i, {}).get("job") or st[i].get("error"):
                img = find_asset(it["image"], ("png", "jpg"))
                if not img: failed.append(i); print("FAIL", i, "image not found:", it["image"]); continue
                prompt = it["prompt"] + ". Flat 2D vector animation, smooth simple motion, the art style does not change, no text."
                st[i] = {"ep": "ltx", "job": ltx.submit(img, prompt, w=it.get("w", 1280), h=it.get("h", 720), secs=it.get("secs", 5), tag=f"{pid}_{i}")}
                save(); print("queued", i, flush=True)
            ljobs[i] = st[i]["job"]
    t0 = time.time(); pending = dict(ljobs)
    while pending and time.time() - t0 < 2400:
        for i, job in list(pending.items()):
            s = ltx.poll(job)
            if s == "done":
                try: ltx.fetch(job, path(i, "mp4")); st[i]["file"] = path(i, "mp4"); st[i].pop("error", None); print("done", i, flush=True)
                except Exception as e: st[i]["error"] = str(e)[:200]; failed.append(i); print("FAIL", i, e, flush=True)
                save(); del pending[i]
            elif s == "failed": st[i]["error"] = "comfy job failed"; failed.append(i); save(); del pending[i]; print("FAIL", i, flush=True)
        if pending: time.sleep(10)
    for i in pending: st[i]["error"] = "timeout"; failed.append(i)
    save()
    print(json.dumps({"failed": failed, "files": sorted(e["file"] for e in st.values() if e.get("file"))}))
    if failed: sys.exit(1)
