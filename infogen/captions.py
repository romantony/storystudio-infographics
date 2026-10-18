"""Burned-in captions as an ASS file: the current word highlighted. Long videos: up to 6 words on two lines near the bottom.
Shorts: up to 3 words, large, below the middle of the frame, clear of the motion graphics above and the Shorts interface below."""
FUNC = {"the", "a", "an", "of", "to", "and", "in", "with", "that", "very", "for", "on", "at", "by", "but", "or", "its", "his", "her", "their"}
HI, LO = r"{\c&H3CC9FF&}", r"{\c&HFFFFFF&}"   # BGR: highlighted word in the accent yellow

def _chunks(words, short):
    out, cur = [], []
    for k, (w, a, b) in enumerate(words):
        if cur and (len(cur) == (3 if short else 6) or (short and len(" ".join(x[0] for x in cur + [(w, a, b)])) > 16) or cur[-1][0][-1] in ".,;:?!"
                    or (not short and len(cur) >= 3 and cur[-1][0].lower() not in FUNC and a - cur[-1][2] > 0.35)):
            out.append(cur); cur = []
        cur.append((w, a, b))
    if cur:
        if out and len(cur) == 1 and not short: out[-1] += cur
        else: out.append(cur)
    return out

def ts(x): return f"{int(x // 3600)}:{int(x % 3600 // 60):02d}:{x % 60:05.2f}"

def ass(words, W, H, short, out):
    """words: [(word, abs_start, abs_end)] for the whole video. Writes the ASS file and returns the number of events."""
    ev = []
    chunks = _chunks(words, short)
    for ci, ch in enumerate(chunks):
        cend = ch[-1][2] + 0.15
        if ci + 1 < len(chunks): cend = min(cend, chunks[ci + 1][0][1])
        brk = (len(ch) + 1) // 2 if (not short and len(ch) > 3) else None
        for i, (w, a, b) in enumerate(ch):
            en = ch[i + 1][1] if i + 1 < len(ch) else cend
            if en - a < 0.05: en = a + 0.05
            parts = []
            for j, (wj, _, _) in enumerate(ch):
                if brk is not None and j == brk: parts.append(r"\N")
                parts.append((HI if j == i else LO) + wj)
            ev.append(f"Dialogue: 0,{ts(a)},{ts(en)},Cap,,0,0,0,,{' '.join(parts).replace(' \\N ', '\\N')}")
    size, align, mv = (88, 2, int(H * 0.36)) if short else (64, 2, 60)
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Cap,Montserrat Black,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,{7 if short else 5},2,{align},{70 if short else 160},{70 if short else 160},{mv},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    open(out, "w").write(hdr + "\n".join(ev) + "\n")
    return len(ev)
