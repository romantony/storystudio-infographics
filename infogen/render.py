"""Bridge to the Remotion renderer (remotion/render.mjs): renders scene clips and stills, cached by content.
Images are served to the headless browser from the run folder by a small local HTTP server for the length of a render."""
import functools, hashlib, http.server, json, os, socketserver, subprocess, sys, threading
from .common import REMOTION

def bundle_version():
    """Changes whenever the templates are re-bundled, so new templates re-render cached scenes."""
    try:
        st = os.stat(os.path.join(REMOTION, "bundle", "index.html")); return f"{st.st_size}:{int(st.st_mtime)}"
    except OSError: return "none"

def fingerprint(props):
    """Hash of the props, the template bundle, and the size and mtime of every file the props reference."""
    files = [bundle_version()]
    def walk(v):
        if isinstance(v, dict): [walk(x) for x in v.values()]
        elif isinstance(v, list): [walk(x) for x in v]
        elif isinstance(v, str) and os.path.isfile(v): st = os.stat(v); files.append((v, st.st_size, int(st.st_mtime)))
    walk(props)
    return hashlib.sha1(json.dumps([props, files], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:14]

class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*"); super().end_headers()

def serve(root="."):
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=os.path.abspath(root)))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"

def run(jobs, concurrency=None, label="render"):
    """jobs: [{"props", "out", "id"?, "still"?, "frame"?}] with file paths in props relative to the run folder. Skips existing outputs."""
    todo = [j for j in jobs if not (os.path.exists(j["out"]) and os.path.getsize(j["out"]) > 0)]
    if not todo: return 0
    if not os.path.isdir(os.path.join(REMOTION, "bundle")):
        subprocess.run(["npx", "remotion", "bundle", "src/index.ts", "--out-dir", "bundle", "--log=error"], cwd=REMOTION, check=True)
    srv, base = serve(".")
    try:
        spec = {"concurrency": concurrency or int(os.environ.get("INFOGEN_RENDER_CONCURRENCY", "0")) or None,
                "jobs": [dict(j, out=os.path.abspath(j["out"]), props=dict(j["props"], base=base)) for j in todo]}
        os.makedirs("build", exist_ok=True); jf = os.path.abspath(f"build/{label}_jobs.json"); json.dump(spec, open(jf, "w"), ensure_ascii=False)
        print(f"{label}: rendering {len(todo)} of {len(jobs)} (the rest are cached)", flush=True)
        p = subprocess.Popen(["node", os.path.join(REMOTION, "render.mjs"), jf], stdout=subprocess.PIPE, text=True)
        bad = []
        for line in p.stdout:
            try: r = json.loads(line)
            except Exception: print(line.rstrip()); continue
            if r.get("ok"): print(f"  {os.path.relpath(r['out'])}  {r['seconds']:.0f}s", flush=True)
            else: bad.append(r); print("  FAILED", os.path.relpath(r["out"]), r.get("error"), flush=True)
        p.wait()
        if bad or p.returncode: sys.exit(f"{label}: {len(bad) or 'some'} render(s) failed")
    finally:
        srv.shutdown()
    return len(todo)
