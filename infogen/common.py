"""Shared helpers: keys from the environment, paths relative to the run folder (the current directory)."""
import json, os, re, subprocess, sys

ASSETS = os.environ.get("INFOGEN_ASSET_DIR", "assets")     # generated images, cut-outs, music, clips
APP = os.environ.get("INFOGEN_APP") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTION = os.environ.get("INFOGEN_REMOTION") or os.path.join(APP, "remotion")
UA = {"User-Agent": os.environ.get("INFOGEN_USER_AGENT", "infogen/1.0")}
FPS = 30

def key(name):
    """API key by env var name. Never print the return value."""
    v = os.environ.get(name)
    if v: return v
    sys.exit(f"missing {name} (set it in the environment)")

def dur(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]))

def find_asset(name, exts=("png", "jpg", "jpeg", "webp", "mp4")):
    """A file by asset id (looked up in the asset dir, cut-out first) or by path. None if missing."""
    if not name: return None
    if os.path.isfile(name): return name
    for d in (f"{ASSETS}/cutouts", ASSETS):
        for e in exts:
            p = f"{d}/{name}.{e}"
            if os.path.exists(p): return p
    return None

def load(path):
    d = json.load(open(path))
    d.setdefault("slug", os.path.basename(os.getcwd()))
    return d

def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)

def mkdirs(*ds):
    for d in ds: os.makedirs(d, exist_ok=True)

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80] or "video"
