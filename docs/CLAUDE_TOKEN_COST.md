# Claude token cost: what we found in infogen and how we fixed it

Written 2026-11-01 for other StoryStudio services (moviegen first) that run Claude and have a similar cost problem. It covers what we saw, why it happened, what we changed, what one video costs now, and a checklist for finding the same problems in another service.

Short version: the cost came from **how many turns the agent ran and how much context each turn resent**, not from what it wrote. Output was under 1% of the tokens. Most fixes were cheap: stop polling, load fewer tools, keep output out of the context, use the right cache lifetime, and measure every session.

## 1. What we saw

In October, StoryStudio used about 223.5M Claude tokens (about $159 at list price). Oct 31 alone was 52% of it. On Nov 1 the Anthropic balance reached $0.00, and four infogen jobs failed about 70 s in with `llm_error` (Claude Code exited with code 1 during setup).

| Measure | October | Oct 31 |
|---|---|---|
| Total tokens | 223.5M | ~116M |
| Cache reads | 212.4M (95%) | ~110M |
| Output tokens | 0.61M | ~34K |
| Cache reads : output | ~350 : 1 | ~3,000 : 1 |

Every service used one shared API key, so we couldn't tell which service spent what. This was the first thing we fixed.

**What the pattern means:** when cache reads are 95% of the tokens and output is under 1%, the model isn't doing much writing. It's rereading a large context again and again. Look for an agent loop with many turns, not for long prompts or long answers.

## 2. Why it happened

Infogen makes each video in **one Claude Code agent session** (`claude -p`, stream-json): research, script, visual plan, reviews, assets, build, thumbnails. Every turn resends the entire session so far, which comes from the prompt cache. A turn writes little (one command or one file), but the context it rereads grows past 100K tokens. The turn limit was 500.

The causes, roughly in order of cost:

1. **One session does everything.** Each step is a turn: run a command, read its output, decide what to do next. With 300 turns at about 120K tokens of context, that's about 36M cache-read tokens for one video. Oct 31's ~110M is about three such jobs.
2. **The context only grows.** It holds:
   - the system prompt and tool definitions;
   - the 31 KB producer prompt;
   - the reference docs;
   - every web page fetched during research;
   - every file the agent writes (scripts with 70–90 scenes, plans);
   - every command output and every image it opens.

   All of it stays until the session ends.
3. **Polling while waiting.** The prompt said to check on background work "every minute or so". Every check was a full turn at full context, which added 20–40 extra turns, or 2–5M tokens, per job.
4. **All tool definitions on every turn.** `--allowedTools` only pre-approves tools. Claude Code still sends the definitions of **all** its tools on every turn, unless `--tools` limits which ones are loaded. Our 3D planner sent them all while using none.
5. **Long command output.** A command could put up to 30,000 characters (queue, validate and build logs) into the session, and that text was resent on every later turn.
6. **Cache expiry.** The default prompt cache lasts 5 minutes. When a command runs longer than that, the next turn rewrites the **whole** context to the cache, at 1.25× the input price. In our measured run, 806K of the 988K cache-write tokens came from 5 such full rewrites, each after a command that took more than 5 minutes (asset queueing, frame generation, the render, the thumbnail wait). Compaction and tool-list changes caused none.
7. **Machine-specific system prompt.** Claude Code puts the working directory, environment and git status into the system prompt. Those differ between containers, so two jobs could never share a cached prefix.
8. **Review sessions read everything.** The analyst sessions were told to read every file in full. The research analyst also searched the web for up to 40 turns. A video runs 4–5 of these.
9. **No limit and no meter.** Nothing stopped a runaway job, and nobody could see what a job cost until the balance ran out.

## 3. What we changed

Two commits on `main`: `8028cb8` (deployed Nov 1, 09:47 IST) and `933d0cc` (deployed Nov 1, 13:45 IST).

| Cause | Change | Where |
|---|---|---|
| Shared key, usage mixed | Own Anthropic workspace `infogen`, service account `infogen` (Developer role), a key scoped to that workspace in SSM `/infogen/ANTHROPIC_API_KEY` | Console / SSM |
| Polling | `python3 -m infogen wait <files> --pid N --timeout 540` blocks in **one** tool call. It returns when the files exist, when the background process dies, or at the timeout. The prompts say to wait, not to check repeatedly. Bash timeout raised to 10 min (`BASH_DEFAULT_TIMEOUT_MS=600000`). | `infogen/wait.py`, `prompts/produce.md`, `api/server.py` |
| All tool definitions | `--tools` loads only the tools each session uses. The producer gets 8 tools; the 3D planner gets none. | `api/server.py`, `infogen/llm.py` |
| Machine-specific system prompt | `--exclude-dynamic-system-prompt-sections`, so every job sends the same system prompt and shares the cached prefix | `infogen/llm.py` (`COMMON`) |
| Long command output | `BASH_MAX_OUTPUT_LENGTH=15000` | `api/server.py` |
| Reading files whole | A "Keep the session small" section in the prompt: use `tail`/`grep` on logs; never read the usage or queue files; look at images through contact sheets first; chain commands in one turn | `prompts/produce.md` |
| Cache expiry after long commands | **1-hour cache** (`ENABLE_PROMPT_CACHING_1H=1`) for the long producer session only. The short analyst and planner sessions keep the 5-minute cache, because 1-hour writes cost 2× input instead of 1.25×, and a short session gains nothing from them. | `api/server.py`, `infogen/llm.py` (removes the variable for child sessions) |
| No limit | A job stops at **$15** (`INFOGEN_MAX_LLM_USD`) with `llm_budget_exceeded`, `retryable: false`. Each analyst session is capped at **$2** (`--max-budget-usd`), the 3D planner at $2. The turn limit is now 250 (85 were used in the measured run). | `api/server.py`, `infogen/llm.py`, `infogen/analysts.py` |
| Effort | `--effort medium` for the Thumbnail Analyst only. The quality and research reviews keep the default, because they find real problems. | `infogen/analysts.py` |
| No visibility | Every Claude call goes through one wrapper (`llm.run`). A meter keeps a per-step ledger (`producer`, `analyst/qa`, `analyst/research`, `analyst/thumbnail`, `scene3d`) in `llm_usage.json`, and every job status has an `llm` field. | `infogen/llm.py` |
| Wasted retries | A thumbnail retry must change the concept or layout, not just regenerate. Headlines are checked against the sources before images are made: wrong headlines caused most of the extra rounds. | `prompts/produce.md` |
| Failed jobs could not restart | A request whose earlier job failed can start again as a new job | `api/task.py` |

**What we left out:**
- **Message Batches:** an agent loop can't send its turns as a batch.
- **A response cache:** an agent never sends the same request twice.
- **Haiku for reviews:** it trades quality for cost, and we wanted measurements first.

## 4. What a video costs now

This is measured, not estimated. Job `e2e_job_1793495909171_l5uf44pnd_r1` made one 10-minute video plus 3 Shorts on Nov 1, running from 09:48 to 11:14 IST.

| Step | Cost |
|---|---|
| Producer (Sonnet 5.5, plus Haiku for web fetches) | $4.38 |
| Research analyst | $0.75 |
| Thumbnail analyst | $0.74 |
| Quality analyst | $0.57 |
| **Total Claude** | **$6.43** |

For the producer session, the figures were:
- 85 turns and 67 API calls;
- 7.93M cache reads, 988K cache writes and 99.2K output tokens.

The non-Claude cost was about $0.40 on RunPod (119 images and 6 clips). The KIE thumbnail price isn't recorded.

**Expected with the 1-hour cache: about $4.75 per video.** Most of the 806K tokens of full rewrites should disappear. The next completed run should show cache writes well below 0.99M. This isn't measured yet: the three re-runs started at 13:49 IST failed at setup, before any tokens were used. That cause is still under investigation.

## 5. How to measure a Claude Code session correctly

We got our first numbers wrong, so these points are worth knowing before you trust any meter:

- **Per-call `usage` lines in stream-json undercount output.** An `assistant` event reports `output_tokens` before the call finishes. Our first meter counted 1,556 output tokens where the real figure was 99,197. Input and cache counts on those lines are correct.
- **The final `result` line is exact.** Its `modelUsage` gives totals per model, **including the Haiku calls Claude Code makes for web fetches**, plus `total_cost_usd`. Use it as the session's figure.
- **The `result` line is cumulative across `--resume`.** A resumed session's result includes its earlier runs (we tested it: 0.00098 → 0.00143). Keep the **latest** result line per session; don't add them up.
- **Between result lines,** estimate output from the text and tool input written (about 4 characters per token), plus the `estimated_tokens_delta` of `system`/`thinking_tokens` events. This is enough for a budget stop.
- **1-hour cache writes** appear as `usage.cache_creation.ephemeral_1h_input_tokens` and are priced at 2× input; 5-minute writes are 1.25×.
- **Check prices against the bill.** Sonnet 5.5 cache reads were charged at $0.10/M, not the $0.20 we had in our price table.
- **To find full cache rewrites,** look for calls with `cache_read_input_tokens == 0` and a large `cache_creation_input_tokens` in the middle of a session, then check what ran just before each one.

`infogen/llm.py` implements all of this (`Meter`, `from_result`, `summary`), and `tests/test_llm.py` tests it against a fake `claude`. It can be copied as it is.

## 6. Checklist for moviegen (or any other service)

Work through these in order. The first three tell you where the money goes; the rest are the usual causes.

1. **Separate the bill.** Give the service its own Anthropic workspace and a workspace-scoped key. Without that you're guessing.
2. **Read the token mix** in the Console for that workspace:
   - Cache reads ≫ output means too many turns over a large context (sections 2.1–2.5).
   - Cache writes higher than about 10% of cache reads means cache expiry or a prefix that keeps changing (2.6, 2.7).
   - High plain input with no cache reads means caching isn't working at all.
   - High output means the model writes too much: check `max_tokens`, effort and thinking.
3. **Measure one job per step.** Log every session's `result` line (or, for direct API calls, every response's `usage`) with a step name. Find the session that dominates before changing anything.
4. **Count turns per job.** Grep the agent prompts for "check every", "poll", "keep checking" or "every minute". Replace polling with one blocking wait command.
5. **Look at the flags.** Is `--tools` set, or only `--allowedTools`? Is `--exclude-dynamic-system-prompt-sections` set? Is there a `--max-budget-usd` or a job-level limit?
6. **Look for long commands.** Anything that runs longer than 5 minutes inside an agent session (renders, generation queues, uploads) causes a full rewrite on the next turn. Either use the 1-hour cache for that session, or run the command outside the session.
7. **Look for big reads.** Logs, JSON state files, base64 images and full web pages read into the context stay there for every later turn. Use `tail`/`grep`, cap output (`BASH_MAX_OUTPUT_LENGTH`), and use contact sheets for images.
8. **Look at sub-sessions.** Review or analyst sessions told to "read everything" with high turn limits. Give each its own budget and only the tools it needs.
9. **Check retries.** A retry that repeats the same request costs the same and fails the same way. Make each retry change something. Make sure a failed job can be restarted without redoing finished stages.
10. **Add a hard stop.** A job limit of about 2× a normal job's measured cost, ending in a non-retryable error, so one runaway loop can't drain the balance again.

If moviegen calls the Claude API directly instead of running Claude Code, items 4–7 become: a stable cached prefix (system prompt and tools first, unchanged between calls); `cache_control` on that prefix; trimming the message history; and Message Batches for anything that doesn't need an immediate answer.

## 7. Related

- `infogen/llm.py`: the wrapper, prices and meter
- `infogen/wait.py`: the blocking wait
- `api/server.py`: producer flags and env, the budget stop
- `prompts/produce.md`: the "Keep the session small" and "Background work" sections
- `docs/ECS_STEP_FUNCTIONS.md`, `docs/ORCHESTRATOR_INTEGRATION.md`: the limits and the `llm` status field
- Analysis docs: [why and what we fixed](https://claude.ai/artifact/B1WGzie8pcw9r8vAtLjdMY), [the measured run and the settings](https://claude.ai/artifact/PKjhPEvxqeEdprWYBNtsaJ)
