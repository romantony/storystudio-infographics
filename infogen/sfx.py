"""Small sound effects for motion graphics, synthesised with ffmpeg (no licences to track).
python3 -m infogen sfx [--out <dir>]      writes whoosh, pop, tick, ding, thud .wav (skips existing files)

The builder puts a whoosh on every whip cut and a pop on every revealed item (bar, pin, list row, character), quietly
under the narration. A scene can add its own: "sfx": [{"name": "ding", "at": 1.2, "volume": 0.5}] or {"cue": "word"}."""
import os, subprocess, sys

DIR = os.environ.get("INFOGEN_SFX_DIR") or ("/app/sfx" if os.access("/app", os.W_OK) or os.path.isdir("/app/sfx") else "build/sfx")
SOUNDS = {
    "whoosh": "anoisesrc=d=0.5:c=pink:a=0.7:r=48000,highpass=f=350,lowpass=f=4200,volume=1.6,afade=t=in:d=0.2:curve=qsin,afade=t=out:st=0.2:d=0.3:curve=qsin",
    "pop": "aevalsrc='0.7*sin(2*PI*(500+1800*exp(-45*t))*t)*exp(-28*t)':d=0.14:s=48000",
    "tick": "aevalsrc='0.5*sin(2*PI*2600*t)*exp(-140*t)':d=0.05:s=48000",
    "ding": "aevalsrc='0.45*(sin(2*PI*1318*t)+0.45*sin(2*PI*2637*t)+0.2*sin(2*PI*3955*t))*exp(-5*t)':d=1.0:s=48000",
    "thud": "aevalsrc='0.9*sin(2*PI*(48+90*exp(-14*t))*t)*exp(-5*t)':d=0.7:s=48000",
}

def path(name):
    p = f"{DIR}/{name}.wav"
    if not os.path.exists(p): make([name])
    return p

def make(names=None, out=None):
    d = out or DIR; os.makedirs(d, exist_ok=True)
    for n in names or SOUNDS:
        p = f"{d}/{n}.wav"
        if os.path.exists(p): continue
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", SOUNDS[n], "-ac", "2", "-ar", "48000", p], check=True)
    return d

def main(cmd, argv):
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    print(make(out=out))
