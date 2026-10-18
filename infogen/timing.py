"""Word timings for one scene, and cue lookup: the time a phrase is spoken, so a bar, pin or label appears on that word."""
import difflib, json, os, re

norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())

def words(narration, words_json, audio_len):
    """[(word, start, end)] for the script's own words, timed from Whisper when available, else spread evenly."""
    script = (narration or "").split()
    if not script: return []
    wh = json.load(open(words_json))["chunks"] if words_json and os.path.exists(words_json) else None
    if not wh:   # estimate: proportional to word length, which tracks speech better than a flat spread
        tot = sum(len(w) + 2 for w in script); t, out = 0.0, []
        for w in script:
            d = audio_len * (len(w) + 2) / tot; out.append((w, t, t + d)); t += d
        return out
    A = [norm(w) for w in script]; B = [norm(c["text"]) for c in wh]
    times = [None] * len(script)
    for blk in difflib.SequenceMatcher(None, A, B, autojunk=False).get_matching_blocks():
        for k in range(blk.size):
            ts = wh[blk.b + k]["timestamp"]; times[blk.a + k] = (ts[0], ts[1] if ts[1] is not None else ts[0] + 0.3)
    i = 0
    while i < len(times):   # interpolate unmatched words between known neighbours
        if times[i] is None:
            j = i
            while j < len(times) and times[j] is None: j += 1
            lo = times[i - 1][1] if i > 0 else 0.0
            hi = times[j][0] if j < len(times) else (wh[-1]["timestamp"][1] or audio_len)
            step = (hi - lo) / (j - i)
            for k in range(i, j): times[k] = (lo + step * (k - i), lo + step * (k - i + 1))
            i = j
        else: i += 1
    return [(w, a, b) for w, (a, b) in zip(script, times)]

def cue(wl, phrase):
    """Start time of the first occurrence of phrase in the timed words, or None."""
    if not phrase or not wl: return None
    P = [norm(x) for x in str(phrase).split() if norm(x)]; W = [norm(w) for w, _, _ in wl]
    for i in range(len(W) - len(P) + 1):
        if W[i:i + len(P)] == P: return wl[i][1]
    for i, w in enumerate(W):   # fall back to a word that starts with the cue's first word ("bomb" -> "bombers")
        if P and w.startswith(P[0]): return wl[i][1]
    return None
