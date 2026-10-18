"""YouTube metadata and credits from meta.json (written by the LLM) plus facts computed here: chapter times from the
timeline, the data sources shown on screen, verify lists from the scripts.
python3 -m infogen metadata meta.json
meta.json:
{ "long": {"title", "alternatives": [], "tags": "a, b", "pinned_comment", "thumbnail_text", "hashtags": "#A #B",
           "description": "paragraphs; may contain {chapters} and {sources}", "disclosure": "what is AI-generated"},
  "shorts": {"a_hook": {"day": 1, "title", "alternatives": [], "cover_text", "tags", "pinned_comment", "description", "hashtags"}} }
Chapters come from the "chapter" field of scenes in script/script.json. Writes out/youtube_metadata.md,
out/youtube_metadata_shorts.md, out/youtube_metadata.json, out/credits.md."""
import json, os, sys
from .common import ASSETS, load, mkdirs
PRODUCED = "Produced @ https://ai-storystudio.com, https://agent.ai-storystudio.com"
def ts(x): x = int(x); return f"{x // 3600}:{x % 3600 // 60:02d}:{x % 60:02d}" if x >= 3600 else f"{x // 60:02d}:{x % 60:02d}"

def sources_of(scenes):
    return list(dict.fromkeys(s["source"].strip() for s in scenes if s.get("source")))

def main(cmd, argv):
    if not argv: sys.exit(__doc__)
    M = json.load(open(argv[0])); mkdirs("out"); script = load("script/script.json"); sc = {s["n"]: s for s in script["scenes"]}
    tl = json.load(open("build/timeline.json"))
    warn = []; L = M["long"]
    # chapters: YouTube needs the first at 00:00, at least three, each at least 10 seconds
    ch = [(e["start"], sc[e["scene"]]["chapter"]) for e in tl if e["scene"] in sc and sc[e["scene"]].get("chapter")]
    keep = []
    for st, t in ch:
        if keep and st - keep[-1][0] < 10: warn.append(f"chapter '{t}' dropped: under 10 s after the previous one"); continue
        keep.append((st, t))
    if keep and keep[0][0] != 0: keep[0] = (0, keep[0][1])
    if len(keep) < 3: warn.append("fewer than 3 chapters: YouTube will not show them")
    chapters = "\n".join(f"{ts(st)} {t}" for st, t in keep)
    srcs = sources_of(script["scenes"]); maps = any(s["type"] == "map" for s in script["scenes"])
    src_txt = "\n".join(f"- {x}" for x in srcs) + ("\n- Map data: Natural Earth (public domain)" if maps else "")
    desc = L["description"]
    desc = desc.replace("{chapters}", "Chapters:\n" + chapters) if "{chapters}" in desc else desc + "\n\nChapters:\n" + chapters
    if src_txt: desc = desc.replace("{sources}", "Sources:\n" + src_txt) if "{sources}" in desc else desc + "\n\nSources:\n" + src_txt
    desc += "\n\n" + L.get("disclosure", "Narration, illustrations and music in this video are AI-generated. Figures are taken from the sources listed.") + "\n\n" + PRODUCED + "\n\n" + L.get("hashtags", "")
    ver = [(n, s["type"], s["verify_note"]) for n, s in sc.items() if s.get("verify")]
    unverified = [n for n, s in sc.items() if s["type"] in ("bar_chart", "line_chart", "donut", "counter", "icons", "versus") and not s.get("source")]
    if unverified: warn.append(f"data scenes without a source: {unverified}")
    for ph in ("[PLAYLIST URL]", "[EPISODE", "TODO"):
        if ph in desc: warn.append(f"placeholder {ph} still in the description")
    if len(L["title"]) > 100: warn.append("long title over 100 characters")
    md = (f"# {L['title']}\n\n**Alternatives:** {'; '.join(L.get('alternatives', []))}\n\n**Category:** Education | **Made for kids:** no | **Altered/synthetic content:** yes"
          f" | **Thumbnail:** `thumb/thumbnail.jpg` ({L.get('thumbnail_text', '')})\n\n**Tags:** {L.get('tags', '')}\n\n**Pinned comment:** {L.get('pinned_comment', '')}\n\n## Description\n\n{desc}\n\n"
          f"## Before publishing: fact-check the `verify` scenes ({len(ver)})\n\n" + "\n".join(f"- Scene {n} ({t}): {v}" for n, t, v in ver) + "\n")
    open("out/youtube_metadata.md", "w").write(md)
    used = sorted({os.path.basename(e["image"]).rsplit(".", 1)[0] for e in tl if e.get("image")})
    lines = ["# Credits\n", "AI-generated illustrations: " + (", ".join(used) or "none"),
             "AI-animated clips: " + (", ".join(sorted(sc[e["scene"]].get("clip", "") for e in tl if e["type"] == "clip" and e["scene"] in sc)) or "none"),
             "Motion graphics: rendered from data by infogen (Remotion)."]
    if maps: lines.append("Map data: Natural Earth, public domain (naturalearthdata.com), via the world-atlas package.")
    if srcs: lines += ["\n## Data sources shown on screen\n"] + [f"- {x}" for x in srcs]
    open("out/credits.md", "w").write("\n".join(lines) + "\n")
    out = {"long": dict(L, description=desc, chapters=[{"start": st, "title": t} for st, t in keep], verify=[v for _, _, v in ver], sources=srcs)}
    smd = ["# YouTube metadata: Shorts (9:16)\n\nCommon: **Category** Education | **Made for kids** no | **Altered/synthetic content** yes | publish one per day after the long video.\n"]
    for sid, v in sorted(M.get("shorts", {}).items(), key=lambda kv: kv[1].get("day", 0)):
        s_ = json.load(open(f"shorts/{sid}/script.json")); vv = [x.get("verify_note") for x in s_["scenes"] if x.get("verify")]
        ss = sources_of(s_["scenes"])
        smd.append(f"## Day {v.get('day', '?')}: {s_.get('title', sid)}\n\n**Title:** {v['title']}\n\n**Alternatives:** {'; '.join(v.get('alternatives', []))}\n\n**Cover text:** {v.get('cover_text', '')}\n\n"
                   f"**Tags:** {v.get('tags', '')}\n\n**Hashtags:** {v.get('hashtags', '')}\n\n**Pinned comment:** {v.get('pinned_comment', '')}\n\n### Description\n\n{v.get('description', '')}\n\n"
                   + (("Sources: " + "; ".join(ss) + "\n\n") if ss else "") + f"{PRODUCED}\n\n{v.get('hashtags', '')}\n\n**Verify before publishing:**\n" + "\n".join(f"- {x}" for x in vv) + "\n")
        if len(v["title"]) > 60: warn.append(f"short {sid}: title over 60 characters")
        out[sid] = dict(v, description=v.get("description", "") + ("\n\nSources: " + "; ".join(ss) if ss else "") + "\n\n" + PRODUCED, verify=vv, video=f"shorts/{sid}/out/{sid}.mp4")
    if M.get("shorts"): open("out/youtube_metadata_shorts.md", "w").write("\n".join(smd))
    out["warnings"] = warn; json.dump(out, open("out/youtube_metadata.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps({"chapters": len(keep), "verify": len(ver), "sources": len(srcs), "warnings": warn}))
