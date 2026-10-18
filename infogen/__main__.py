import importlib, sys
CMDS = {"status": "status", "style": "style", "queue": "queue_assets", "cutout": "cutout", "tts": "narration", "timings": "narration",
        "build": "build", "thumb": "thumb", "metadata": "metadata", "sheet": "sheet", "sfx": "sfx", "upload": "upload", "validate": "validate"}
if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
    sys.exit("usage: python3 -m infogen <" + "|".join(CMDS) + "> [args]   (run from the run folder)")
cmd = sys.argv[1]
importlib.import_module(f"infogen.{CMDS[cmd]}").main(cmd, sys.argv[2:])
