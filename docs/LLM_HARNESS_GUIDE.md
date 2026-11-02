# An LLM harness for StoryStudio services, and when Haiku can do the work

Written 2026-11-02 from moviegen, for infogen, docgen and any other StoryStudio service that calls Claude. It
explains what the harness is, what it saved and what it caught, when Claude Haiku 5.5 can replace Sonnet, and how to
build the same thing in another service. The working code is in this repo (`src/moviegen/harness/`). The detail and
the measurements are in `docs/MODEL_COST_TESTS.md` and `docs/Moviegen LLM Harness — Implementation Spec.md`.

**Short version.** Put every model call behind one function that does five things:
- replays a stored answer for a request it has seen before;
- checks the answer in code;
- repairs only what failed;
- moves up to a stronger model when a cheaper one can't pass the checks;
- prices every call.

With that in place, Haiku 5.5 (1/20 of Sonnet 5.5's price) wrote moviegen's motion prompts and shot lists and passed
the same checks as Sonnet. Sonnet is now a fallback, not the default.

## 1. Why we built it

The first long moviegen plan ("Journey Beyond", 8 × 10-minute episodes) cost **$123.83** in Claude calls over six
runs:

- **About $84 went to runs that failed:** a stage's output cut off at `max_tokens`, the credit running out, a crash on
  an unknown id, a bad API key. Each retry paid again for work that had already succeeded.
- **One stage, `shots`, was 71% of the bill.** It is mostly output tokens: 11–20K per scene at Sonnet's $10/M. This
  is the opposite of infogen's problem, where cache reads dominated. Measure before you optimise.
- **Two of the three automatic fix rounds cost about $15 and fixed nothing.** The findings went 226 → 144 → 202 →
  188. The log said "226 fixed" because it matched findings by their wording, which the reviewer changes every time.
- **Our own price table was wrong in two places.** Sonnet 5.5 cache reads are $0.10/M, not $0.20. Haiku 5.5 charges
  5× on every token of a request whose prompt is over 100K tokens. The Console bill showed it.

A cheaper model alone doesn't fix this. In the first test, Haiku's shot lists were as good as Sonnet's in kind, but
two scenes came out 42% and 46% shorter than their target. Nothing noticed, because nothing checked. The harness is
what makes a cheap model safe to use: code checks every answer, and a stronger model is called only when a check
fails.

## 2. What the harness is

```
stage code ──► call_checked(stage, schema, prompts, checks)
                 │
                 ├─ cache hit? ──────────────────────────────► stored output (+ its violations), no model call
                 │
                 └─ for model in ladder (e.g. Haiku, then Sonnet):
                       call model ── schema-invalid? one schema-repair turn
                       fix-ups (code corrects what it can exactly)
                       validators (code decides: errors block, warnings are recorded)
                       errors? repair: re-ask for only the failing items, splice back, check again (≤ 2 times)
                       passed? ──► cache + return
                    top of ladder and still failing ──► cache + return with violations recorded; the job goes on
               every model call: price it, meter it, log one line
```

The pieces in moviegen (`src/moviegen/harness/`):

| Piece | File | What it does |
| --- | --- | --- |
| Entry point | `run.py` (`Harness.call_checked`) | The loop above. `llm.ClaudeLLM.structured` is a thin shim over it, so stage code didn't change. |
| Record/replay cache | `cache.py` | Key = sha256 of canonical JSON of everything that decides the answer. Stored in the service's own storage (S3). |
| Backends | `models.py` | Claude API / Bedrock, and an OpenAI-compatible endpoint (RunPod) for evaluating open models. |
| Prices | `pricing.py` | One table, priced per call (long-context and batch rates included). |
| Contracts | `validate.py`, `validators/*.py` | `Violation(rule_id, target, severity, message)`, validators, fix-ups. |
| Repair | `repair.py` | Item repair (only the failing items, spliced back by id) or whole-output repair. |
| Vision checks | `vision.py` | Keyframe and clip QC: the model reports findings and code decides pass or fail. |

## 3. Each piece, and what we learned building it

### 3.1 One entry point

Every call goes through one function. Only then can caching, checking, escalation and metering be added once and
apply everywhere. In moviegen the 13 call sites kept calling `llm.structured(...)`; that method now forwards to the
harness. Stages that need checks call `structured_checked(..., checks=...)` and get back a `StageResult` (output,
remaining violations, model used, repairs, escalated).

### 3.2 Record/replay cache

- **Key everything that decides the answer:** stage name, a stage version number, the model (or the whole ladder),
  the system prompt, the shared context, the user text, images *by content hash*, the output schema, and parameters
  such as `max_tokens` and effort. Change one character of any input and the key changes. That is what makes the
  cache safe.
- **Bump the stage version** when a prompt or validator changes meaning in a way the request text doesn't show.
- **Cache failures too.** An output still failing at the top of the ladder is stored with `passed: false` and its
  violations. A rerun then costs nothing and reproduces the same result, instead of paying again for the same
  failure.
- **Give a deliberate second opinion its own key.** A vote ("Independent check 2 of 3") is a different request, so it
  gets its own entry; replaying the first answer would not be a second opinion.
- **Read-only mode** (`MG_LLM_CACHE=read`) turns a miss into an error, so tests and CI can run against a recorded
  cache with no model calls.
- **What it bought:**
  - A second run of an unchanged plan makes 0 model calls and writes byte-identical files.
  - Re-checking 38 keyframes was 38 cache hits.
  - We retuned the keyframe pass/fail rule three times by replaying cached findings, at $0.
- **Watch out:** asking the same question twice now returns the same answer. To force a fresh answer, change an input
  or turn the cache off for that run.

### 3.3 Price every call

- **Price per request, not per total.** Haiku 5.5's long-context rate depends on each request's own prompt size, so
  totals can't be priced correctly afterwards.
- **Check the table against the Console bill.** Ours now reproduces the Nov 1 moviegen bill exactly: Sonnet $39.77
  and Haiku $2.50, from 265 logged calls.
- **Log one line per call**, with stage, model, stop reason, seconds, input, cache write, cache read, output, thinking
  tokens and cost. Log one more per checked stage call, with attempts, repairs, escalated, passed, violations and
  cost. That is enough to answer "which stage costs what" with `grep`.

| Per million tokens (2026-11-02) | Input | Cache write (5 min) | Cache read | Output |
| --- | --- | --- | --- | --- |
| Sonnet 5.5 | $2.00 | $2.50 | $0.10 | $10.00 |
| Haiku 5.5, prompt up to 100K | $0.10 | $0.125 | $0.01 | $0.50 |
| Haiku 5.5, prompt over 100K | $0.50 | $0.625 | $0.05 | $2.50 |

The Batch API halves all of these. Check the pricing page before you rely on these numbers; they change.

### 3.4 Contracts in code: validators and fix-ups

A validator is a pure function, `(output, context) -> [Violation]`. It makes no model calls and does no I/O beyond the
context it is given. A `Violation` has:

- a stable `rule_id`, such as `shots.scene_length`;
- a stable `target`, such as `E01S05` or `E01S05SH07.characters`;
- a severity: `error` blocks the commit, `warning` is recorded;
- a machine-written `message`, which is sent to the model verbatim in a repair turn ("The scene runs 38 s; its target
  is 65 s (allowed 59–71 s). Add about 27 s…").

A fix-up corrects in place what code can correct exactly, before the validators run: snapping a duration to a
supported length, renumbering ids, stepping shot lengths to close a gap of up to 15%. Never ask a model to do
arithmetic or bookkeeping that code can do.

**What we learned:**

- **Measure every rule on real outputs before choosing its severity.** Our first "no readable text" rule flagged 5
  of 840 real shots as errors. All 5 were phrases like "on the word 'pass'", which refer to spoken dialogue. Our first
  "every named character must be in the shot" rule flagged 87 shots, and most were people being looked at or heard
  ("eyes fixed on Orun", "Mira off-screen").
  - After tuning, the error rules raised 0 false alarms on 878 real shots.
  - The noisy rule became a warning: 5 findings, 3 of them real.
  - A noisy error makes the model rewrite good work.
- **Turn existing ad-hoc checks into validators instead of writing new ones.** moviegen already had shot checks and
  motion-prompt checks; the harness gave them rule ids and a repair loop.
- **Let the model fill slots and let code write the final text** wherever the output has fixed parts. moviegen's
  motion prompts are rendered by code from slots the model fills, and the dialogue and character descriptions are
  pasted in by code. They can't drift, so they need no check.
- **Keep warnings out of any automatic fix loop.** Moviegen records harness warnings in the plan's validation list as
  notes. Otherwise 80 "this character has no reference image" warnings would have triggered scene replans that can't
  fix them.

### 3.5 Targeted repair

On errors, send the model:

- the original request;
- its previous output;
- only the failing rule lines;
- the instruction "change only what these problems need".

Two forms:

- **Item repair.** When every error points at items of a list (shots in a scene), ask for only those items, under a
  small schema of their own, and splice them back by id. A fix to one shot doesn't rewrite the other fourteen, which
  is where the output-token money goes.
- **Whole repair.** When the fix can add or remove items (a scene that runs short needs more shots), ask for the
  whole output again.

After a repair, run every validator again: a repair can break something else. Send each repair turn as original
request + current output + current failures, not the growing history, so the second repair costs no more than the
first. Two repairs per model is our default.

### 3.6 The model ladder

`MG_LADDER_<STAGE>=claude-haiku-5-5,claude-sonnet-5-5`: start cheap, and escalate only when the cheap model still
fails its checks after repair. With no ladder set, the stage uses its one model, which is the previous behaviour. An
output still failing at the top is kept with its violations recorded, and the job carries on. A check must never
crash a job; a validator that throws becomes a warning.

### 3.7 Vision checks: findings from the model, the verdict from code

For image and video QC, ask for findings with a `rule_id` from a closed list (`kf.people_count`, `kf.identity`,
`kf.prop_missing`, …), not for a pass/fail verdict and a free-text hint. Code then:

- **Decides pass or fail.** Moviegen fails on any error finding, and always counts wrong head counts, text in the
  image, broken anatomy and corrupt frames as errors, whatever severity the model gave them.
- **Writes the retry hint**, one fixed sentence per rule filled from the plan ("Exactly 2 people in frame: Rian,
  Thessa."). The same failure always changes the next attempt the same way.
- **Votes on failure (optional).** A failed check is checked twice more, and the asset is remade only if most checks
  fail. A Haiku check costs far less than a new image or clip.

Measured on 38 stored keyframes, Haiku's structured check agreed with the earlier verdicts on 35 (92%).

## 4. When Haiku 5.5 can replace Sonnet 5.5

Everything below was measured on moviegen's own work. "With checks" means the harness above was in place.

| Job | Result on Haiku 5.5 | Cost vs Sonnet | Verdict |
| --- | --- | --- | --- |
| Video motion prompts (slot filling, from a keyframe image) | 10/10 passed the worker's prompt checks; 2 needed one repair each | $0.004 vs $0.06 per shot | **Use Haiku** |
| Shot lists (structured planning, 9–14 shots per scene) | First test, no checks: same kinds of mistakes as Sonnet, but 2 of 8 scenes 42–46% short. With checks: 8/8 scenes within ±10% of target, first try | $0.10 vs ~$1.30 per episode | **Haiku, with Sonnet as the fallback** |
| Continuity QA over a long plan | Already Haiku; findings vary a lot between runs (3 vs 19 errors on the same input) | — | Keep Haiku. Vote, and use stable rule ids. |
| Keyframe QA (vision) | 35/38 agreement with stored verdicts | ~$0.001 per check | **Haiku** |
| Narration, music cues, recaps (short structured writing) | Not measured separately | ~1/20 | Likely fine. Test first. |
| Story judgement (screenplay review, story bible, script) | Not tried | — | **Keep Sonnet/Opus** until an eval says otherwise |
| Open models on RunPod as reviewers (GLM-5.3, Qwen3 32B) | Slower and missed more than Haiku; Qwen's 32K context couldn't fit one episode | Not cheaper | **No** |

**How to decide for your own stage:**
1. Copy a real input (the project files the stage reads).
2. Run the stage on Haiku and on Sonnet through your validators.
3. Compare pass rate, repairs needed and cost, and read some outputs side by side.

Moviegen's tests cost under $1 each.

**Haiku 5.5 gotchas we hit, or that the API documents:**

- **The 5× long-context price above 100K prompt tokens.** Our review prompts were 105K tokens, so Haiku billed $2.50
  where we expected $0.50. Keep Haiku prompts under 100K: send only the part of the context the stage needs.
- **Haiku 5.5 rejects some request shapes with a 400:** `budget_tokens` thinking, non-default sampling parameters
  (`temperature`, `top_p`), and assistant prefill. Use adaptive thinking and `output_config.effort`, end the
  messages with a user turn, and use structured outputs.
- **Thinking counts toward `max_tokens`.** A truncated reply (`stop_reason == "max_tokens"`) must be an error, not a
  half-parsed answer.

## 5. How to build it in your service

Do it in this order. Each step is useful on its own.

1. **Separate the bill.** Give the service its own Anthropic workspace and key (moviegen and infogen both have one).
2. **One entry point.** Route every model call through one function. Keep the old interface as a shim, so call sites
   don't change yet.
3. **Price and log every call** with a per-call price table, and check it against the Console bill for one day.
4. **Record/replay cache** in your own storage, keyed on everything that decides the answer. Store the output, raw
   text, model, usage, cost and attempts. Add a read-only mode for tests.
5. **Find the stage that costs the most** (from step 3), and write its contract as validators. Take the rules from
   what has actually gone wrong, run them over real past outputs, and set each severity from what they find.
6. **Repair, then the ladder:** targeted repair first, then a ladder with the cheap model at the bottom. Use the
   stage's current model alone until you have measured the cheap one.
7. **Measure Haiku on that stage** with real inputs (section 4), then set the ladder in production.
8. **Then the rest:** a per-stage ledger, a job budget stop, the Batch API for work nobody waits on. These are
   Phase 5 in the spec, not built yet in moviegen.

### For a direct-API service (docgen, if it calls the Messages API)

Moviegen's code transfers almost as it is:

- `harness/` has no moviegen-specific imports except storage and the schema helper.
- `pricing.py`, `cache.py`, `models.py`, `run.py`, `validate.py` and `repair.py` can be copied.
- Write your own `validators/`.

The pattern that pays most is the moviegen motion prompt: the model fills a small schema of slots, code renders the
final text and checks it. For documents, that might mean the model writes sections into a schema, and code assembles
the document and checks what code can:

- headings present and in order;
- word counts per section;
- every required source cited;
- figures that match the input data;
- no placeholder text.

We don't know docgen's code. Read this as the pattern, not a design.

### For an agent-session service (infogen's Claude Code producer)

A long agent session can't be replayed call by call, but the same ideas apply at the edges:

- **Sub-calls** (analysts, the 3D planner): these are single requests with structured output, so they can use the
  harness as is: cache, validators, ladder, per-call price.
- **The session's outputs:** validate the files the session writes (script, visual plan, render manifest) with
  validators in code, and feed the exact violation lines back. Resume the session with them, or start a short fix
  session. Re-running the whole producer costs far more.
- **The ladder:** run the analyst and review sessions on Haiku with `--max-budget-usd`. Escalate to Sonnet only when
  the code checks on their output fail.
- **Cache at the step level:** key a step's output (for example the research summary) on its inputs, so a retried
  job skips finished steps. Infogen already lets a failed job restart; this makes the restart cheap.
- **Meter from the final `result` line** of each session (its `modelUsage` and `total_cost_usd`), as infogen
  already does.

## 6. Settings (moviegen names; reuse them)

| Setting | Default | Meaning |
| --- | --- | --- |
| `MG_LLM_CACHE` | `readwrite` | `read` = replay only (a miss is an error); `off` = always ask the model |
| `MG_MODEL_<STAGE>` | per stage | The stage's model |
| `MG_LADDER_<STAGE>` | the stage's model only | Models to try in order, e.g. `claude-haiku-5-5,claude-sonnet-5-5` |
| `MG_REPAIR_ATTEMPTS` | `2` | Repair turns per model before escalating |
| `MG_SCENE_LENGTH_TOL` | `0.10` | Example of a contract's tolerance setting (share of target, at least 5 s) |
| `MG_KF_QA_VOTES` / `MG_CLIP_QC_VOTES` | `1` | Votes on a failed vision check (3 = two more checks) |
| `MG_SAFETY_BLOCKLIST` | empty | Terms a provider rejected, which a rewrite must remove |
| `MG_QA_FIX_ROUNDS` | `3` (moviegen production: `1`) | Automatic QA → fix rounds; more than one didn't pay for itself |

Live in moviegen since 2026-11-02 (task definition `moviegen-worker:4`): `MG_LADDER_SHOTS` and
`MG_LADDER_MOTION_PROMPT` set to `claude-haiku-5-5,claude-sonnet-5-5`, and `MG_QA_FIX_ROUNDS=1`.

## 7. What it cost to build and test

| Test | Spend |
| --- | --- |
| Haiku vs Sonnet on one episode's shots, and on 10 motion prompts (first comparison) | ~$0.75 |
| Phase 2 live acceptance: one episode's shots and 10 motion prompts on Haiku with checks | $0.13 |
| Structured keyframe QA on 38 keyframes (and 3 retunings from the cache) | $0.04 |
| RunPod GLM-5.3 and Qwen3 reviewer tests (RunPod's own billing) | ~$0.50 |

The expected saving on one series like Journey Beyond is about $47 on motion prompts alone, plus most of the
`shots` cost once Haiku plans them (about $1.30 → $0.10 per episode on the first draft).

## 8. Open items

- **A per-stage ledger and a job budget stop** (`MG_MAX_LLM_USD`): spec Phase 5, not built.
- **The Batch API** for planning fan-out: Phase 5.
- **Continuity checking in code** (a replay of who holds what, and which device is on or off): spec Phase 3. It
  targets the error kinds both models made: oxygen arithmetic, a beacon switch state, a staff reappearing.
- **Voted QA with stable finding ids, and a stop rule for fix rounds** that compares findings by id, not wording:
  Phase 4.
- **Haiku hasn't been measured on narration, music or recap** in production. The ladder makes trying it low-risk.
