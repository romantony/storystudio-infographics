# Connecting the orchestrator to infogen

infogen runs exactly like the docgen documentary service: one job at a time, the orchestrator owns the queue, status flows
through signed webhooks and `GET` polling, a person approves at two checkpoints. The Production Manager can drive both
services with the same client code; only the names below differ.

| | docgen (documentaries) | infogen (infographic videos) |
|---|---|---|
| Endpoint | `/v1/documentaries` | `/v1/infographics` |
| Job id | `dg_` + 12 hex | `ig_` + 12 hex |
| Webhook headers | `X-Docgen-Event`, `X-Docgen-Delivery`, `X-Docgen-Signature` | `X-Infogen-Event`, `X-Infogen-Delivery`, `X-Infogen-Signature` |
| Env / SSM prefix | `DOCGEN_*`, `/docgen/` | `INFOGEN_*`, `/infogen/` |
| Output prefix | `docgen/<request_id>/` | `infogen/<request_id>/` |
| Health checks | Storyblocks MCP, Gemini, RunPod, Comfy | Gemini, RunPod, templates bundle; Comfy only for jobs with `ltx_clips > 0`. No MCP sign-in. |

Unchanged: auth (`Authorization: Bearer`, `X-Origin-Verify` from CloudFront), `GET /v1/health`, `GET /{id}`, `GET /{id}/events?after_seq=`,
`POST /{id}/respond`, `POST /{id}/cancel`, `GET /{id}/files/<path>`, the status object, stage names (`setup` ... `upload_outputs`),
checkpoint ids (`cp_script`, `cp_final`), output kinds (`long_video`, `short`, `thumbnail`, `metadata`, `shorts_metadata`, `credits`),
webhook retry and sequence rules, the dead-man stop.

## Request

```json
POST /v1/infographics
{
  "request_id": "tis-2026-10-20-ai-bubble",
  "topic": "What if the AI bubble bursts",
  "synopsis": "Day by day from the first big lab missing its revenue target to the recession that follows; what happens to jobs, savings and the tech you use.",
  "format": "day_by_day",
  "series": {"name": "WHAT IF", "episode": 4, "next_episode_title": "What if the internet went down for a week"},
  "long": {"target_seconds": 600, "narrator_voice": "Puck"},
  "shorts": {"count": 3, "angles": ["hook", "stat", "twist"]},
  "visuals": {"style": "flat_vector", "palette": {}, "cast": {"maya": "a woman in her 30s, curly black hair, green bomber jacket, jeans"},
              "illustrations": 80, "characters": 8, "objects": 8, "backgrounds": 8, "ltx_clips": 0,
              "animated_max_pct": 20, "animated_clips": 18, "captions_long": false, "captions_shorts": true},
  "review_mode": "checkpoints",
  "model": "claude-sonnet-5-5",
  "limits": {"max_runtime_minutes": 180},
  "callback": {"url": "https://orchestrator.example.com/hooks/infogen"}
}
```

| Field | Values | Default |
|---|---|---|
| `format` | `explainer`, `what_if`, `hour_by_hour`, `day_by_day`, `versus`, `body`, `ranking`, `true_story`, `compilation` | `explainer` |
| `long.target_seconds` | any whole number from `60` to `1800` (1 to 30 minutes): a target the script is written to, not a cut-off (`validate` warns beyond 15 %) | 600 |
| `kind` | `video` (one video) or `series_plan` (plan a series; see below) | `video` |
| `series.publish_date` | `YYYY-MM-DD`, the episode's planned publish date | — |
| `long.narrator_voice` | a Gemini TTS voice (`Puck` upbeat, `Charon` informative, `Fenrir` excitable, `Orus` firm) | `Puck` |
| `shorts.angles` | `hook`, `stat`, `twist`, `myth`, `countdown` | `hook, stat, twist` |
| `visuals.style` | `flat_vector`, `noir_vector`, `paper`, or `auto`: Claude chooses the style for the topic after the research (`style --choose`) | `flat_vector` |
| `visuals.palette` | overrides for keys of `remotion/src/theme.ts` (`"#RRGGBB"`; `series` a list), or `auto`: Claude chooses the colours. With `style` `auto` and no colours fixed, the palette is chosen as well. Fixed colours always win, and every choice is checked for readable contrast | `{}` |
| `visuals.cast` | recurring characters, id to a fixed visual description; keep it the same across a series | `{}` |
| `visuals.illustrations` | most frames in the visual plan (0 to 240); the plan uses 50 to 80 per 10 minutes, each on screen 8 to 12 s | 80 per 10 minutes of `long.target_seconds` |
| `visuals.characters` / `objects` / `backgrounds` | references the frames are composed from (0 to 20 each) | 8 / 8 / 8 |
| `visuals.animated_max_pct` / `animated_clips` | Wan2.2 animation (5 s clips) cap: share of the frames (0 to 40) and absolute ceiling on attempts (0 to 30) | 20 / 18 |
| `visuals.ltx_clips` | LTX 2.3 hero shots (10 s clips at 720p), attempts included (0 to 10) | 0 |
| `thumbnail.style` | `cinematic_infographic`, `epic_historical`, `superhero_showdown`, `mystery_discovery`, `economic_explainer`, or `auto` (Claude chooses) | `cinematic_infographic` |
| `thumbnail.candidates` | candidates per thumbnail (1 to 4); the Thumbnail Analyst scores them and the best one at 80 or more is used | 3 |
| `thumbnail.text` | the long video's exact headline (up to 32 characters); Claude writes 2 to 5 words when it is missing | — |
| `thumbnail.text_mode` | `overlay`: Nano Banana 2.1 draws the picture and infogen typesets the headline exactly; `model`: the image model draws the text and the analyst checks it | `overlay` |
| `thumbnail.shorts` / `shorts_cover` | a 9:16 thumbnail for every Short / put it into the Short as a 1 s cover frame at the end | `true` / `true` |
| `thumbnail.resolution` | `1K`, `2K`, `4K` (generation size; exported at 1280×720 and 1080×1920, under 2 MB) | `2K` |

The server writes `request.json` and `style.json` (from `visuals.style`, `palette`, `cast`) into the run folder before the Claude run starts.

## A series: plan once, then one video at a time

A request with `"kind": "series_plan"` makes no video. It plans a whole series with `prompts/plan_series.md`:
- `topic` is the theme and `synopsis` the brief;
- `series.name` is the name, or Claude names it;
- `long`, `shorts` and `visuals` are what every episode will be made with.

```json
{"request_id": "ss-series-cold-war", "kind": "series_plan", "topic": "Cold War flashpoints",
 "synopsis": "Twelve moments when the Cold War nearly turned hot, told as they happened, for a general audience.",
 "series": {"name": "Flashpoints"}, "long": {"target_seconds": 600}, "shorts": {"count": 3},
 "series_plan": {"episodes": 12, "per_week": 3, "start_date": "2026-11-02"},
 "review_mode": "checkpoints", "callback": {"url": "https://orchestrator.example.com/hooks/infogen"}}
```

| Field | Values | Default |
|---|---|---|
| `series_plan.episodes` | 2 to 30 | 12 |
| `series_plan.per_week` | 1 to 7, spread over the week (3: Mon, Wed, Fri) | 3 |
| `series_plan.start_date` | first publish date, `YYYY-MM-DD` | the next Monday |
| `series_plan.formats` | the formats episodes may use | all |

With `review_mode` `checkpoints`, the job stops at `cp_series`. StoryStudio sends `auto` until it has an approval screen. Its outputs are:
- `series_plan`: `series/series.json` (format: `infogen/series.py`);
- `series_plan_pdf`: `series/series.pdf`, the overview to share;
- `series_overview`;
- `series_research`;
- `qa_report` and `research_report`.

Each episode is then an ordinary video request, made one at a time:
- `topic`, `synopsis` and `format` from its entry;
- `series.name`, `series.episode` = `n`, `series.next_episode_title` = `next_title`, `series.publish_date`;
- `shorts.angles` from its `shorts`;
- the plan's `cast` as `visuals.cast`, and the same `long`, `shorts` and `visuals` as the plan request;
- usually `review_mode` `auto`.

## Quality and Research Analysts

Every video and every series plan is reviewed before anything is paid for, by two analysts (`infogen/analysts.py`):
- the **Research Analyst**: sources, claims, visual facts and era;
- the **Quality Analyst**: script, Shorts and visual plan, or the series as a series.

Each runs as its own Claude session with read-only tools, scores the work against a rubric (`rubrics/`), and writes a report with must-fix, should-fix and suggested findings. The producer fixes the findings, and a verify pass confirms the fixes. The reports are outputs, `qa_report` and `research_report`.

The rubrics improve after every run:
- each recorded review counts every criterion's passes and failures;
- each new guideline an analyst proposes becomes a criterion;
- criteria that keep passing are retired once there are more than 40.

The live rubrics are kept on the runs volume (`<INFOGEN_RUNS_DIR>/_rubrics`, with a `history.jsonl`) and shared by every job. The producer reads them before writing (`rubric show`), so each run starts from what the earlier runs learned.

StoryStudio does this in `backend/convex/e2e/infographicSeries.ts`. Each episode's completion starts the next. A failed episode is recorded and the series carries on, while one cancelled by its reviewer stops the series.

## Cost and time per 10-minute video (estimates to confirm on the first real runs)

- Paid generations: 50 to 80 frames (Qwen Image Edit, about 15 s each on an A40), up to 24 references (about 8 s each), up to 16 Wan2.2 clips of 5 s at the default cap (20 % of 80 frames), any LTX hero shots of 10 s (Qwen and Wan on RunPod), 4 music tracks, about 90 TTS calls (one per scene, long and Shorts), one Whisper call per scene. No stock footage.
- Rendering is CPU work in the container: about 0.3 to 0.5 seconds per frame per core-pair on a small machine, so give the instance at least 8 vCPUs (`INFOGEN_RENDER_CONCURRENCY` sets Remotion's parallel tabs; default half the cores). A 10-minute video is 18,000 frames.
