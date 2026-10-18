# Visual upgrade plan: grown-up flat-vector characters, reference-built scenes, selective LTX animation

Draft, 2026-10-18. Status: Phase 1 (style.py, infogen 82a526e), the `qwen-image-edit` multi-image worker (Qwen-Edit c47143e, live) and Phase 2 (visual plan: `infogen/visual_plan.py`, `queue` / `validate --plan`, runbook) are done; Phases 3–5 are proposed.

## Test results, 2026-10-18 (Berlin Airlift, about $0.25 in total, mostly cold starts)

| Step | Result |
|---|---|
| Text-to-image with the new Phase 1 wrapper | Period accuracy fixed: 1940s truck, silver four-engine propeller transports, period clothes. Scenes have adult proportions. **But** the images keep shading and texture (graphic-novel look), and **full-body sheets stay chibi** in three prompt variants, including style-first and "eight heads tall". Text prompts alone don't get Qwen to the target look. |
| **Style anchor** (`qwen-image-edit`, image 1 = a flat character sheet in the target style, prompt "draw a new picture in exactly the same style as image 1, but of …") | **Works.** The children and a Berlin mother came out in the anchor's flat style with adult proportions. A C-54 drawn new this way is correct (four radial engines, single fin). **Restyling** a detailed reference (the old C-54 sheet) failed, giving a deformed plane; restyling a background barely changed it. → Generate every reference *new* from the anchor rather than restyling. |
| Composition (background + pilot + children in pass 1, then the C-54 added in pass 2) | Works. All three keep their reference looks, and the output is 16:9 (1376×768). The fixed output size held even with a square or portrait image 1. 53 s for 2 passes. Flaws: a garbled extra figure, the fence layered through a child, and the pilot too large (legs cut off). The review step must catch these; prompts need explicit size and placement. |
| Wan2.2 i2v on the composed frame (480p, 5 s, 4 steps) | The camera stayed put and the characters stayed in frame. The pilot waves, then lowers his arm and turns to watch. The children's arms move, and the plane moves and descends. The flat style holds. **Output is 832×464 at 16 fps** (81 frames): it needs scaling to 1920×1080 and conversion to 30 fps. Generation took 89 s; wall time with a cold start was 274 s. |
| Drift check (correlation of the first vs last frame, lower two-thirds) | 0.785 on the first clip; **0.553 on the guideline-prompt clip, which is also good**: there the plane landed into the lower frame. A whole-region correlation can't tell "the subject moved there" from "the camera moved". The check must compare only the `[STILL ELEMENTS]` regions, using a mask from the background reference (where the background equals the composed frame), or an optical-flow estimate of global camera motion. |
| Same frame and seed, prompt per the Wan2.2 guideline (69 words, slots in order) | **Better motion:** the plane really lands, the children turn their heads to follow it, and the pilot waves and turns. The camera stayed fixed. New issue: "descending toward the runway" brought the plane down large and close behind the pilot, covering the background, and a smoke plume appeared unprompted. Main-motion wording needs scale and position ("high in the background, staying small"). Adopted as the prompt standard (see "Wan2.2 i2v prompt rules"). |

**Phase 2 real run** (`queue plan/visual_plan.json`, 6 references and 3 frames, Berlin): references drawn from the default anchor came out flat with adult proportions, and the C-54 had four engines. **Backgrounds with the anchor as image 1 kept the anchor's pilot** in the empty set, whatever the prompt said. They are now drawn onto a blank canvas (image 1) with the anchor as image 2, which gives a clean empty set. Frames with explicit placement ("fully visible, about half the frame height") came out without the garbled figure, the fence through a child or the cropped legs from the first test. Weakest point: background detail (the bombed-out blocks became a generic skyline).

**Consequence for Phase 2:** the series needs a **style anchor**, one flat character sheet in the target look:
- It is generated once per series, or chosen from a small library, and kept in `style.json` as `anchor`.
- Every character, object and background reference is drawn from it with `qwen-image-edit`, rather than from text with `qwen-image-gen`.
- `qwen-image-gen` stays for the anchor itself and for scenes with no recurring subjects.

## Why

A comparison with The Infographics Show (two of their videos against our Panama Canal and Berlin Airlift runs) found:

| | Theirs | Ours |
|---|---|---|
| Frames with motion | ~99 % | 56–63 % |
| Characters | Flat vector, adult proportions, the same in every scene | Chibi (big heads), painterly lighting, drifting between scenes |
| Period accuracy | — | Berlin 1948 showed C-130s (first flight 1954), a modern jet and modern trucks |
| Image reuse | — | The same picture up to 3 times in 4 minutes |

Manual tests on 2026-10-18 showed a working alternative:
1. A character sheet per role, generated in a flat, adult 1940s style on a white background.
2. A scene composited from those sheets with Qwen Image Edit, with the characters kept exactly as on their sheets.
3. LTX 2.3 image-to-video on that scene for real motion.

Step 3 has one failure to design around: LTX followed the plane and tilted the characters out of frame.

## What the code does today, and why it looks the way it does

| Finding | Where |
|---|---|
| The style wrapper asks for the chibi look: *"simple rounded cartoon people with **large heads** and simple dot eyes", "simple soft cel shading", "smooth **gradient** sky", "vibrant saturated palette"*. The same text is used for scenes and characters. | `infogen/style.py` `BASE_STYLE`, `PRESETS["flat_vector"]` |
| Scenes are text-to-image only. A recurring character is a text description pasted into each prompt (`{cast_id}`), so faces and clothes drift. There is no path for a reference image. | `infogen/queue_assets.py` (`qwen` → `rp.EP["qwen"]` = `qwen-image-gen`) |
| The "hopping": characters are separate green-screen poses, cut out and laid over the scene, which *pop* in on a spring (damping 9), *bob* 6 px and *breathe* 1.2 %. | `remotion/src/templates/Illustration.tsx` (cast layer), `infogen/cutout.py` |
| Our `qwen-image-edit` endpoint runs **Qwen-Image-Edit-2511** (`QwenImageEditPlusPipeline`), which takes several reference images, but the handler only ever passes one: `"image": [image]`. | `~/Qwen-Edit/qwen-image-edit/src/handler.py` `run_pass`, `handler` |
| The LTX workflow's fixed negative prompt is `"pc game, console game, video game, cartoon, childish, ugly"`. The words *cartoon* and *childish* work against a flat-cartoon style. The Gemma prompt rewriter in the graph is switched off (`320:328` = false), so our prompt is used as written. | `infogen/workflows/ltx_i2v.json` node `320:313` |
| The LTX prompt suffix says nothing about the camera, so LTX is free to follow the moving subject. | `queue_assets.py` stage 2: `". Flat 2D vector animation, smooth simple motion, the art style does not change, no text."` |
| LTX is off by default (`ltx_clips` 0). Its only documented use in the runbook is generic. | `api/server.py` `Visuals.ltx_clips`, `prompts/produce.md` |
| The image budget is low for the scene count: 24 illustrations (26 from StoryStudio) for 70–90 scenes, so the runbook encourages reusing one picture for 2–3 scenes. | `api/server.py`, `produce.md` "Assets" |
| The era is checked only by eye ("regenerate images that show ... the wrong era") on a contact sheet. Nothing defines what is right for the period. | `produce.md` "Look at every image" |

## The changes

### Phase 1: the style (prompt-only, cheap, do first)

1. **Rewrite `BASE_STYLE`** around the base prompt that worked in the manual test:
   `flat vector infographic illustration, minimalist 2D, clean geometric shapes, bold uniform outlines, flat colour fills with no gradients and no lighting effects, simple faces with dot eyes, realistic adult body proportions (head about one seventh of body height), children drawn as children, crisp edges`.
   Remove *large heads*, *soft cel shading*, *gradient sky* and *vibrant saturated*.
2. **Add an era palette and wardrobe line** to `style.json`, written by Claude from the research:
   - `"era": "Berlin, 1948–49"`
   - `"palette_prompt": "muted 1940s palette of olive green, khaki, slate blue, warm grey and cream"`

   `image_prompt()` appends both to every prompt. The default stays neutral for modern topics.
3. **Character sheets on a plain white background**, full body, front-facing, as in the test. `cutout.py` already handles plain non-green backgrounds with a flood fill, and white sheets work better as edit references than green.
4. **Negative prompt additions:** `chibi, big head, gradient, 3D, painterly, glossy, realistic lighting`.
5. **Test:** regenerate 6 Berlin scenes and 3 cast sheets with the new wrapper, then compare contact sheets with the old run.

### Phase 2: plan the references, generate them, then compose every frame from them

The flow, after the script is written:

```
script ──► visual plan ──► references (qwen-image-gen) ──► frames (qwen-image-edit, refs) ──► animate ≤ cap (LTX)
            characters        one image per character,        one composed image per            selected frames only
            objects           object and background           frame / visual beat
            backgrounds
```

1. **Visual plan (`plan/visual_plan.json`, written by Claude after the script and validated before anything is paid for).**
   Planning names every reference the video needs and writes a prompt for each one:
   ```json
   {"characters":  [{"id": "pilot_us",    "prompt": "US Air Force transport pilot, brown leather flight jacket, khaki trousers, garrison cap, aviator sunglasses pushed up"},
                    {"id": "kids_berlin", "prompt": "three postwar Berlin children in patched coats, flat caps and wool stockings"}],
    "objects":     [{"id": "c54",         "prompt": "Douglas C-54 Skymaster, four radial engines, tricycle gear, single tall fin, bare aluminium"},
                    {"id": "coal_sack",   "prompt": "burlap coal sack"}],
    "backgrounds": [{"id": "tempelhof",   "prompt": "1948 Tempelhof airfield, runway, curved terminal, bombed-out apartment blocks behind, overcast"},
                    {"id": "berlin_flat", "prompt": "bare 1948 Berlin flat interior, small table, window, candle"}],
    "frames":      [{"id": "f012", "scenes": [12, 13], "background": "tempelhof", "refs": ["pilot_us", "kids_berlin", "c54"],
                     "prompt": "the pilot stands left by a parked C-54 waving up; the children stand right behind a wire fence, one pointing at the C-54 coming in to land",
                     "animate": {"prompt": "the pilot waves slowly; the girl's pointing arm follows the plane; the plane glides right, descending; propellers spin", "secs": 5}}]}
   ```
   - **Characters, objects and backgrounds** are drawn from the script and `research/visual_facts.md` (Phase 4). Every recurring person, vehicle, aircraft and location gets exactly one reference.
   - **Frames:** one per visual beat. A frame may carry up to 2 consecutive scenes with different crops (Phase 5). It names its background and up to 3 refs, describes the action, and, only when chosen (Phase 3), has an `animate` block.
   - **`validate --plan`** checks the plan before anything is paid for:
     - every id a frame uses exists;
     - each frame has at most 3 refs;
     - every illustration scene in the script is covered by a frame;
     - counts are within the request budget;
     - animated frames are within the cap (Phase 3).
2. **References (`qwen-image-gen`)**, generated first. All use the Phase 1 style wrapper on a plain white background:
   - characters: full body, front-facing, neutral pose;
   - objects: isolated, side or three-quarter view;
   - backgrounds: the empty set with no people, at 16:9.

   The run then makes a contact sheet of all references, and Claude looks at it and regenerates any that are off. Every frame inherits from these, so this is the cheapest place to catch the wrong aircraft or a drifting face.
3. **Frames (`qwen-image-edit`, multi-reference).** Each frame is one edit job:
   - Image 1 is the background reference; images 2–4 are the character and object refs.
   - Fixed preamble: *"Flat vector infographic scene in the same style as the reference images. Use image 1 as the setting. Place <label of ref 2> from image 2 [, <label of ref 3> from image 3 ...], keeping their exact faces, outfits, proportions and colours unchanged."* The frame's action prompt and the era palette follow.
   - **Limit:** the endpoint takes 3 images per pass. A frame with a background and 3 refs runs as two chained passes: the background plus 2 refs first, then the result plus the third ref.
   - A frame with no background reference (a close-up on an object, an abstract scene) is text-to-image from the frame prompt, as today.
4. **Worker (`~/Qwen-Edit/qwen-image-edit`):**
   - Accept `image_urls` (1–3) alongside `image_url` and pass all of them to the pipeline (`"image": [img1, img2, img3]`).
   - Let a pass in `passes` carry its own `image_urls`; the previous pass's output is image 1.
   - `image_url` with a single image behaves exactly as today.
   - Deploy through the usual GitHub Actions → Docker Hub path.
5. **The queue:** `queue` reads `plan/visual_plan.json` in place of the `images`/`characters` groups of `assets.json`. Stages run in order:
   1. references
   2. contact-sheet review
   3. frames, which need the reference URLs kept in `queue_state.json`
   4. LTX on frames that have `animate`

   Each stage is resumable and never resubmits paid jobs, as today. `assets.json` keeps `bgm`. `build` resolves a scene's image from the frame that covers it.

### Phase 3: animation in place of hopping

1. **`Illustration.tsx`:**
   - Characters are now drawn into the scene image, so the cut-out `cast` layer becomes optional and rarely used.
   - When it is used, the entrance is a short fade-and-rise (no spring), with no bob and no breathe.
   - Callout labels keep their pop, which reads as a graphic rather than a character.
2. **LTX prompt and workflow:**
   - **Workflow negative:** replace with `camera movement, panning, tilting, zoom, characters leaving frame, morphing faces, extra people, 3D, realistic, photographic, text, watermark`. Remove *cartoon* and *childish*.
   - **Suffix:** replace with `Static locked-off camera, no pan, no tilt, no zoom; the whole scene stays in frame for the whole clip. Flat 2D vector animation, simple smooth motion, characters keep their exact faces and outfits, the art style does not change, no text.`
   - **Shape of each LTX prompt:** say *who* moves and *how much* ("the pilot waves his raised hand slowly", "propellers spin as faint discs", "the plane glides from upper left toward the right, staying in the upper half of the frame").
3. **Automatic check** in the queue, after each clip arrives:
   - Compare the clip's first and last frames: a structural similarity of the lower two-thirds, where the characters stand.
   - If they differ beyond a threshold (the camera drifted or a character left), regenerate once with the subject's own motion removed. If it fails again, fall back to the still image with a camera move and record a warning.
4. **Which frames to animate (runbook).** Claude chooses during planning and marks them with `animate` in the visual plan.
   - Only beats that carry the story: the opening hook, the turning point, the climax, and at most one per chapter.
   - Only motion the narration names, such as a wave, a pointing hand, propellers, a vehicle crossing, smoke or rain.
   - Every other frame stays a still with a camera move.
5. **Hard limit on animated frames, so the budget cannot be exceeded.**
   - **Request:** `visuals.animated_max_pct`, the share of the long video's frames that may be animated. Default **20 %**, maximum **40 %** (see "Engines and cost"). An absolute ceiling, `animated_clips` (default 18), replaces `ltx_clips`, which is kept as an alias.

     The allowed number of clips is `min(animated_clips, floor(animated_max_pct × frames))`, worked out from the plan's frame count. For a 10-minute video with about 45 frames at 20 %, that is 9 clips (about $0.19 on Wan2.2). The request sets the cost ceiling; the plan only decides where the clips go.
   - **Enforced in three places**, not only in the runbook:
     1. `validate --plan` rejects a plan with more `animate` frames than the cap.
     2. `queue` submits LTX jobs only up to the cap and logs any frames left over, so a plan edited after validation still can't overspend.
     3. The drift-check retry (item 3) counts against the cap. A retry that would go over the cap falls back to the still image with a warning instead.
   - **Reported:**
     - `status --cost ltx_clips=<n>` records the number actually generated, retries included;
     - a warning gives `<used>/<cap>`;
     - StoryStudio stores the cap per job, so cost can be checked against it.
   - **Shorts:** reuse the long video's clips, cropped to 9:16, and generate no new LTX.

### Phase 4: period accuracy

1. **During research, write `research/visual_facts.md`:** for the place and date, the vehicles, aircraft, uniforms, weapons, buildings and landmarks, each with a one-line visual description and a source. For example: *"C-47 Skytrain: twin radial engines, tail-dragger; C-54 Skymaster: four radial engines, tricycle gear, single tall fin"*.
2. **Turn those into sheets and cast** (Phase 2), so the right equipment comes from a reference rather than from the model's memory.
3. **Image review:** check every asset on the contact sheet against `visual_facts.md`, item by item. Report how many were regenerated for era errors in a warning.

### Phase 5: budget

1. **Frames:** about 40–45 per 10 minutes (each covering 1–2 consecutive scenes), up from 24–26. Each is one edit job, about 15 s on an A40, or 2 jobs with a fourth ref.
2. **References:** budgeted separately: characters (default 8), objects (default 8), backgrounds (default 8). Each is one `qwen-image-gen` job, about 8 s.
3. **Reuse:** a frame may carry at most 2 *consecutive* scenes (with different crops). A picture is never used again once other scenes have come between.
4. **Request fields:**
   - `illustrations` becomes the frame budget;
   - `characters` stays;
   - `objects` and `backgrounds` are new;
   - `animated_max_pct` is new (Phase 3);
   - `ltx_clips` stays as the absolute ceiling.
5. **StoryStudio:** add the new fields to `lib/infographic.ts` (strict validation, the same as the existing ones) and `e2e/infographic.ts`, and update the MCP guide §6.7 and both MCP server schemas.

## Engines and cost

The RunPod endpoints already deployed (infogen's `rp.py` knows `qwen`; `qedit` and `wan` are to be added):

| Engine | Endpoint | Time per job (warm) | Rate | Cost per job |
|---|---|---|---|---|
| Qwen image gen | `e165se4r3eo5hp` (`{"model": "qwen", "prompt", "aspect_ratio"}`) | ~15 s | A40 $0.44/h | ~$0.002 |
| Qwen image edit | `oxwx8o879qwtla` (`image_url`, or `image_urls` after the worker change) | ~15 s per pass | A40 $0.44/h | ~$0.002 |
| Wan2.2 I2V-A14B, 4-step Lightning | `nd7wloyvj09xwy` (`{"image", "prompt", "resolution": "480p", "duration_s": 3–7, "sample_steps": 4, "seed"}`) | ~90 s per 5 s clip | A6000 Ada $0.84/h | ~$0.021 |
| LTX 2.3 (ComfyUI Cloud) | `infogen/ltx.py` | — | — | $0.05–0.08 per 5 s |

- **Cold starts:** about 2.5–3.5 min per Qwen worker spin-up, roughly $0.02. Submitting everything before waiting on anything, as `queue` already does, warms workers in parallel.
- **Wan limits:**
  - `duration_s` must be a whole number from 3 to 7; anything else is rejected.
  - Run at **480p**: 720p runs out of GPU memory.
  - Leave the seed out (or send -1) for a random one; store the seed used so a retry can change it.

**Per 10-minute video** (about 24 references and about 45 frames, some built in two passes): **images ≈ $0.15**. Animation adds:

| `animated_max_pct` | Clips (of ~45 frames) | Wan2.2 | LTX | Wan GPU time, one at a time |
|---|---|---|---|---|
| 10 % | 4 | $0.08 | $0.20–0.32 | 6 min |
| 20 % (proposed default) | 9 | $0.19 | $0.45–0.72 | 14 min |
| 40 % (proposed maximum) | 18 | $0.38 | $0.90–1.44 | 27 min |

At these prices the cap mainly limits **wall-clock time**: the infogen task costs about $0.64/h while it waits. Money is secondary. Clips are therefore submitted in parallel.

The Wan2.2 endpoint has **6 serverless workers**. A per-run limit, `INFOGEN_ANIMATE_CONCURRENCY`, decides how many clips are in flight; the default is 4, so one run can't take every worker if other pipelines share the endpoint.

| Clips | 4 in flight | 6 in flight |
|---|---|---|
| 9 (20 % default) | 3 rounds, ~4.5 min | 2 rounds, ~3 min |
| 18 (40 % maximum) | 5 rounds, ~7.5 min | 3 rounds, ~4.5 min |

These times exclude the model load on each newly started worker.

**Animation engine:**
- **Default: Wan2.2.** It is about 3× cheaper than LTX. LTX's extra, generated audio, isn't used, because Remotion plays clips muted.
- **Optional: LTX** per frame with `"engine": "ltx"`, at 720p, for hero shots. LTX clips count against the same cap.
- **Resolution:** Wan's 480p clips are scaled to 1080p in Remotion. Flat colours survive the scaling, but outlines soften slightly; check this in the Phase 3 proof.
- **Clip length:** `duration_s` = the frame's narration length rounded up, between 3 and 7 s. A frame that runs longer holds its last frame, as the `clip` scene already does.
- **Shared rules for both engines:** the locked-camera prompt suffix, the negative prompt and the drift check from Phase 3.

### Wan2.2 i2v prompt rules (LightX2V 4-step; from the team's guideline)

Every clip prompt has these slots, in this order, in about 40–80 words:

```
[MAIN MOTION]      one subject, one action verb, a direction and a speed:   "A silver four-engine propeller plane flies slowly from left to right across the sky, descending toward the runway, propellers spinning."
[SECONDARY MOTION] characters named by POSITION, 1–2 small actions each:    "The pilot on the left smiles and waves his raised hand side to side. The three children behind the fence turn their heads to follow the plane."
[AMBIENT MOTION]   optional, subtle:                                         "Grey clouds drift slowly."
[STILL ELEMENTS]   what must not move, to stop background warping:           "The ruined buildings and runway stay still."
[CAMERA]           exactly one move:                                          "Static camera." (or slow push-in / slow pan left / slow pan right)
[STYLE LOCK]       always last, the same wording in every clip:               "Flat 2D cartoon animation, consistent line art and colors."
```

- Use strong, visible verbs (flies, waves, turns, walks, falls), not vague ones (lively, dynamic).
- Don't describe what the image already shows (clothes, colours, faces).
- Use **no negative prompt** (CFG 1). Fix problems by rewording the positive prompt ("… stays still") or by having fewer moving parts.
- Keep the seed fixed while iterating on a prompt. Store the seed per clip.
- Our endpoint runs 4 steps at 480p (832×480). 720p runs out of memory on it, even though the guideline lists 1280×720 for finals.

`queue` builds the prompt from these slots: the visual plan's `animate` block gives `main`, `secondary`, `ambient`, `still` and `camera`, and the style lock is fixed per series. The prompt is checked for length (40–80 words) and for having exactly one camera move. The LTX path keeps its own wording.

## Order of work and size

| Phase | Repos | Effort | Proof |
|---|---|---|---|
| 1 Style | infogen | small: prompt text + `style.json` keys | before/after contact sheets for 6 Berlin scenes |
| 2 References | Qwen-Edit worker, infogen | medium: worker input change + new queue stage + runbook | a 3-ref scene matching the manual test |
| 3 Animation | infogen (workflow JSON, queue, Remotion, runbook) | medium | 3 clips in which the characters stay in frame; the drift check catches the old failing clip |
| 4 Period | infogen runbook | small | Berlin rerun shows only C-47/C-54 |
| 5 Budget | infogen, StoryStudio defaults + MCP doc | small | — |

**End-to-end check:** rerun the Berlin Airlift topic in `auto` mode, then repeat the comparison measurements (share of frames moving, contact sheets, image reuse count). The target is over 75 % moving frames without the cast layer, and no anachronisms.

## Decisions needed

1. **Animation defaults** (costs settled 2026-10-18, see "Engines and cost"):
   - Wan2.2 as the default engine, with LTX per frame;
   - `animated_max_pct` defaults to 20 % (maximum 40 %);
   - `ltx_clips` becomes an absolute `animated_clips` ceiling (default 18);
   - at most 4 animation jobs in flight per run (`INFOGEN_ANIMATE_CONCURRENCY`; the Wan endpoint has 6 workers; use 6 if infogen is its only user).
2. **Remove the cut-out cast layer entirely, or keep it optional?** Keeping it optional is proposed: it's still useful for thumbnails and for a narrator figure that recurs.
3. **Change the existing `flat_vector` preset, or add a new one** (for example `infographic`) and make it the default? Changing it in place is proposed: no published series depends on the old look.
4. **The worker change to `qwen-image-edit`:** it's shared with StoryStudio's other image-edit uses. The change is additive (`image_urls` is new; `image_url` behaves the same), but it is a production redeploy.
