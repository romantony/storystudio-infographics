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
              "illustrations": 26, "characters": 8, "ltx_clips": 0, "captions_long": false, "captions_shorts": true},
  "review_mode": "checkpoints",
  "model": "claude-sonnet-5-5",
  "limits": {"max_runtime_minutes": 180},
  "callback": {"url": "https://orchestrator.example.com/hooks/infogen"}
}
```

| Field | Values | Default |
|---|---|---|
| `format` | `explainer`, `what_if`, `hour_by_hour`, `day_by_day`, `versus`, `body`, `ranking`, `true_story`, `compilation` | `explainer` |
| `long.target_seconds` | 120 to 1800 | 600 |
| `long.narrator_voice` | a Gemini TTS voice (`Puck` upbeat, `Charon` informative, `Fenrir` excitable, `Orus` firm) | `Puck` |
| `shorts.angles` | `hook`, `stat`, `twist`, `myth`, `countdown` | `hook, stat, twist` |
| `visuals.style` | `flat_vector`, `noir_vector`, `paper` | `flat_vector` |
| `visuals.palette` | overrides for keys of `remotion/src/theme.ts` | `{}` |
| `visuals.cast` | recurring characters, id to a fixed visual description; keep it the same across a series | `{}` |
| `visuals.illustrations` / `characters` / `ltx_clips` | generation budget | 24 / 6 / 0 |

The server writes `request.json` and `style.json` (from `visuals.style`, `palette`, `cast`) into the run folder before the Claude run starts.

## Cost and time per 10-minute video (estimates to confirm on the first real runs)

- Paid generations: about 24 to 30 images and 6 to 10 character poses (Qwen on RunPod), 4 music tracks, about 90 TTS calls (one per scene, long and Shorts), one Whisper call per scene. No stock footage.
- Rendering is CPU work in the container: about 0.3 to 0.5 seconds per frame per core-pair on a small machine, so give the instance at least 8 vCPUs (`INFOGEN_RENDER_CONCURRENCY` sets Remotion's parallel tabs; default half the cores). A 10-minute video is 18,000 frames.
