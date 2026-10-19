# infogen

Animated infographic video generator as a service, in the style of narrated motion-graphics explainer channels: a flat
cartoon world, charts that grow on the word, real maps with routes and pins, versus match-ups, timelines, big counters and
a running clock for hour-by-hour stories. Same shape as the docgen (documentary) image: an Ubuntu desktop with Claude Code,
a config-driven toolkit and a small API that an orchestrator drives.

| Path | What |
|---|---|
| `infogen/` | Toolkit. Run from a run folder: `python3 -m infogen <command>`. Each module's docstring is the format reference. |
| `remotion/` | The scene templates (React/Remotion): `illustration`, `bar_chart`, `line_chart`, `donut`, `counter`, `icons`, `versus`, `map`, `timeline`, `list`, `title`, `timecard`, `text`, `clip`, `endcard`, plus the thumbnail. `render.mjs` renders many scenes with one browser. |
| `docs/SCENES.md` | Every template and its fields. |
| `docs/ORCHESTRATOR_INTEGRATION.md` | The API: what differs from docgen, the request payload, cost and render time. |
| `api/server.py` | FastAPI server: one job at a time, status from `status.json`, signed webhooks, checkpoints. |
| `api/mock_runner.py` | Stand-in for the Claude run; walks the stages without spending anything. |
| `prompts/produce.md` | Instructions for the Claude Code run that produces a video. |
| `examples/demo/` | A script that uses every template, with stand-in art (`tests/make_demo_art.py`), buildable offline. |
| `api/task.py`, `docs/ECS_STEP_FUNCTIONS.md`, `deploy/ecs-task-definition.json` | Running on ECS Fargate from a Step Functions state machine: one task per run of the Claude session, job folders on EFS. |
| `Dockerfile`, `deploy/`, `buildspec.yml` | Image, supervisord, compose, systemd units, first-boot setup, `.env` from Parameter Store, dead-man stop, CodeBuild with a render smoke test. |

## How a video is made

1. **Research and script** (Claude): sources first (`research/sources.md`) and what everything on screen looks like (`research/visual_facts.json`, from the topic and synopsis), then `script/script.json`: 70 to 90 scenes for 10 minutes, each one visual beat of 4 to 10 seconds, every reveal tied to a word (`cue`). `validate` checks it.
2. **Art** (`queue`): scene illustrations and character poses from Qwen, wrapped in the series style (`style.json`: preset, palette, era, recurring cast described once). Characters are generated on plain white and cut out automatically. Music from ACE-Step. Optional LTX animations.
3. **Voice** (`tts`, `timings`): Gemini TTS per scene, Whisper word timings.
4. **Motion graphics** (`build`): each scene is rendered by Remotion from data at its exact narration length, cached by content; `--stills` gives a contact sheet to review before the full render.
5. **Mix**: narration, synthesised sound effects (whoosh on cuts, pop on reveals, ding on counters), music ducked under the voice, loudness-normalised; captions optional (on for Shorts).
6. **Package**: thumbnail (text typeset, never misspelled), metadata with chapters and the on-screen sources, upload.

## Local test

```bash
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn pydantic boto3 pillow numpy
.venv/bin/python tests/test_api.py                          # API contract against the mock runner

cd remotion && npm ci && npx remotion bundle src/index.ts --out-dir bundle && cd ..
cd examples/demo && python3 ../../tests/make_demo_art.py && export PYTHONPATH=$(cd ../.. && pwd)
python3 -m infogen cutout analyst_worried && python3 -m infogen validate
python3 -m infogen tts --dry                                  # silent placeholder narration, no API key needed
python3 -m infogen build --stills                             # build/stills_infogen-demo.jpg
python3 -m infogen build --run                                # out/infogen-demo.mp4
```
On a machine without Remotion's own browser, point `INFOGEN_BROWSER` at a Chrome or headless-shell binary.

```bash
docker build -t infogen:local .
docker run --rm -e VNC_PASSWORD=changeme -e INFOGEN_API_TOKEN=t -e INFOGEN_CALLBACK_SECRET=s -e INFOGEN_RUNNER=mock \
  -e GEMINI_API_KEY=x -e RUNPOD_API_KEY=x --shm-size 1g -p 127.0.0.1:6080:6080 -p 127.0.0.1:8080:8080 infogen:local
```

## Not yet verified

- The Docker build itself (arm64 and amd64): the toolkit, templates and API were tested outside Docker.
- A real end-to-end run with `INFOGEN_RUNNER=claude` and paid generations: Qwen's handling of the style wrapper and of the white-background character prompt, and the cut-out quality on real art.
- Render time on the target instance; size it from the first real run.
- Remotion is free for individuals and companies of up to three people; larger companies need a company licence.
