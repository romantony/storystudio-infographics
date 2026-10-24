# Scene templates

Every scene in `script/script.json` (and `shorts/<id>/script.json`) has a `type` and the fields below. Common fields:

| Field | Meaning |
|---|---|
| `n` | Scene number (unique in the script). |
| `narration` | What the narrator says over this scene. 10 to 25 words is one visual beat. Empty only with `seconds`. |
| `type` | One of the templates below. |
| `seconds`, `hold` | Minimum length; extra seconds after the narration. |
| `cut` | `whip` (default between different scenes), `hard` (default when the same illustration continues), `fade`. |
| `timecard` | Badge in the top-left corner, e.g. `"DAY 2 · 14:00"`. It stays on later illustration, clip and map scenes until another scene sets it again or sets `""`. |
| `ambient` | A looping animated background drawn in code, free and never a frozen frame: `"power_grid"` or `{"motif", "mode", "at", "period", "opacity"}`. Motifs: `power_grid` (pylons, wires with current pulses, house lights), `city_lights`, `network`, `flow`, `radar`, `waves`, `factory` (smoke and gears), `traffic`, `rain` (with lightning), `stocks` (a moving line and bars). `mode`: `flow` (default), `blackout` (lights go out in a cascade from `at` seconds, current stops) or `restore` (lights come back on). It repeats every `period` s (default 8). Behind charts, counters and cards; blended over an illustration or clip. |
| `animated` | Small looping animated props over any scene: `[{"sprite": "turbine" \| "gears" \| "coin" \| "heartbeat" \| "bulb", "x": 0.85, "y": 0.2, "h": 0.22, "at": 0.3, "mode": "on" \| "off" \| "flicker" (bulb), "color"}]`, or a Lottie file the series supplies: `{"lottie": "lottie/name", "x", "y", "h", "loop": true}` (`assets/lottie/name.json`). `x`, `y` are the centre and `h` the height, as fractions of the frame. Free, uncapped. |
| `chapter` | Starts a YouTube chapter here (long video). |
| `source` | Shown small at the bottom; required on data scenes. |
| `verify`, `verify_note` | Fact-check list for the reviewer. |
| `sfx` | Extra effects: `[{"name": "ding" | "pop" | "whoosh" | "tick" | "thud", "at": 1.2 | "cue": "word", "volume": 0.4}]`. |

**Reveals.** Every item marked *revealable* below accepts `"cue": "word or phrase"` (appears when that is spoken, from the Whisper timings) or `"at": seconds`. Without either, items are spread through the first half of the scene. Each reveal gets a quiet pop sound.

**Images.** `image`, `src` and image-like `icon` values are asset ids (`city_night` finds `assets/city_night.png`; cut-outs are found first in `assets/cutouts/`) or paths in the run folder. An `icon` can also be any emoji.

## illustration

The generated cartoon world with a camera move, the cast, and labels. The workhorse: most scenes. `image` is normally a frame id from the visual plan (`plan/visual_plan.json`), with the characters already composed into the picture, so `cast` is left out.

```json
{"type": "illustration", "image": "city_night", "move": "zoom_in",
 "cast": [{"src": "analyst_worried", "x": 0.72, "y": 0.98, "h": 0.66, "flip": false, "cue": "she"}],
 "callouts": [{"text": "3 AM", "x": 0.3, "y": 0.3, "icon": "⏰", "color": "#FF5A5F", "cue": "three"}],
 "tint": "rgba(255,0,0,0.25)"}
```
- `move`: `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`, `still`, or `{"from": [x, y, zoom], "to": [x, y, zoom]}` with x, y the point of the picture (0 to 1) at the centre of the frame. Use from/to to get two or three different shots out of one picture.
- `cast` (revealable, first, optional): cut-out characters laid over the picture, for a figure that is not in the frame itself. `x` centre, `y` feet (0 top, 1 bottom; default 0.98, or 0.6 in Shorts so the captions stay clear), `h` height as a share of the frame, `flip` mirrors. They pop in, bob and breathe.
- `callouts` (revealable, after the cast): label bubbles pointing down at (`x`, `y`).

## bar_chart
```json
{"type": "bar_chart", "title": "...", "kicker": "small line above", "prefix": "$", "unit": "bn", "decimals": 0, "max": 1000,
 "items": [{"label": "USA", "value": 916, "icon": "🇺🇸", "highlight": true, "cue": "America"}], "source": "SIPRI 2024"}
```
Horizontal bars grow and count up. `items` revealable. With any `highlight`, highlighted bars are the accent colour and the rest one neutral colour.

## line_chart
```json
{"type": "line_chart", "title": "...", "prefix": "$", "unit": "bn", "points": [{"x": "2020", "y": 95}, {"x": "2025", "y": 400}],
 "annotate": {"at": 5, "text": "+74% in a year", "cue": "seventy-four"}, "min": 0, "source": "..."}
```
Draws left to right. Beats: the scene's own `cue` starts the drawing, `annotate.cue` pops the label.

## donut
```json
{"type": "donut", "title": "...", "items": [{"label": "Chips", "value": 55, "display": "55%"}], "center": {"value": "$400bn", "label": "in 2025"}, "source": "..."}
```
Segments sweep in, then the legend rows (revealable after the first beat).

## counter
```json
{"type": "counter", "kicker": "...", "value": "$7 trillion", "label": "...", "icon": "💸", "sub": "...", "sub_cue": "Japan", "source": "..."}
```
One big number counting up (text around the digits is kept), with a ding when it lands.

## icons
```json
{"type": "icons", "title": "...", "total": 20, "highlight": 3, "icon": "🧍", "label": "3 in 20", "highlight_cue": "three", "source": "..."}
```
A grid of icons; the first `highlight` light up. Good for "1 in 5" statements.

## versus
```json
{"type": "versus", "title": "...", "a": {"name": "Navy SEAL", "image": "seal_cutout" | "icon": "🪖", "color": "#4CC9F0"}, "b": {...},
 "rows": [{"label": "Training (weeks)", "a": 78, "b": 62, "unit": "", "better": "high" | "low" | "none", "cue": "training"}], "source": "..."}
```
Beats: a, b, then each row. The better value of each row lights up; text values are allowed (no bar race then).

## map
```json
{"type": "map", "title": "...", "focus": {"countries": ["Poland", "Lithuania"]} | {"bbox": [[13, 50], [30, 58]]} | "world",
 "highlight": ["Poland", {"country": "Russia", "color": "#FF5A5F", "label": "KALININGRAD", "at": [21, 54.7], "cue": "Russia"}],
 "pins": [{"lon": 23.0, "lat": 54.0, "label": "Suwałki Gap", "icon": "⚠️", "cue": "gap"}],
 "routes": [{"from": [20.5, 54.7], "to": [27.5, 53.9], "icon": "🚚", "dashed": true, "color": "#FF5A5F", "cue": "supply"}]}
```
Real country shapes (Natural Earth 1:50m). Default framing: the highlighted countries' main landmass plus the pins and routes. Beats: highlights, pins, routes. Country names: Natural Earth short names; common aliases work (USA, UK, DRC, South Korea, UAE...). For a highlighted country `label` overrides the name, `""` hides it, and `at` moves it.

## timeline
```json
{"type": "timeline", "title": "...", "events": [{"date": "7:30 AM", "label": "New hire logs in", "icon": "💻", "cue": "logged"}]}
```
Events appear along a line; it scrolls after four. Vertical in Shorts.

## list
```json
{"type": "list", "title": "...", "numbered": true, "countdown": false, "items": [{"text": "Hiring freezes", "icon": "🧊", "cue": "freezes"}]}
```

## title, timecard, text (stingers)
```json
{"type": "title", "kicker": "PART 2", "title": "The Collapse", "sub": "...", "icon": "💥", "image": "city_night"}
{"type": "timecard", "kicker": "DAY 1", "text": "HOUR 3", "sub": "09:45 AM · Washington"}
{"type": "text", "text": "A house divided against itself cannot stand.", "quote": true, "attribution": "Abraham Lincoln, 1858", "icon": "📜"}
```
Short (2 to 4 seconds), with a thud. Use `quote` only for real, sourced quotations.

## clip
```json
{"type": "clip", "clip": "ltx_city_night"}
```
A video (an LTX animation from `assets.json`) filling the frame; holds its last frame if the narration is longer.

## endcard
Added automatically at the end (5 s long, 2.5 s Shorts) from the script's `series` and `next`. Set `"endcard": false` in the script to leave it out.

## bars3d, globe, network3d (3D scenes)
Three.js scenes, rendered in software (no GPU), with the same palette and heading as the flat charts. Use them sparingly, for the one or two moments in a video that should feel like a reveal; the planner `python3 -m infogen scene3d <n>` (Opus, `INFOGEN_ANIM_MODEL`, default `claude-opus-5-5`) designs the camera and the cues of a scene and cannot change any data. A 6 s scene takes roughly 30 to 50 s to render on 8 cores.
```json
{"type": "bars3d", "title": "...", "kicker": "...", "prefix": "$", "unit": "bn", "max": 1000, "camera": "rise",
 "items": [{"label": "USA", "value": 916, "highlight": true, "cue": "America"}], "source": "SIPRI 2024"}

{"type": "globe", "title": "...", "focus": [10, 30], "spin": 50, "camera": "push_in", "highlight": ["Egypt", {"country": "Panama", "color": "#FF5A5F"}],
 "pins": [{"lon": 32.5, "lat": 30, "label": "Suez", "cue": "Suez"}], "arcs": [{"from": [-79.5, 9], "to": [32.5, 30], "cue": "ships"}]}

{"type": "network3d", "title": "...", "camera": "orbit",
 "nodes": [{"id": "a", "label": "Plant", "size": 1, "cue": "plant"}, {"id": "b", "label": "City"}], "links": [{"from": "a", "to": "b", "cue": "power"}]}
```
- `camera`: `"orbit"` (default), `"push_in"`, `"rise"`, `"still"`, or `{"az": [from, to], "el": [from, to], "dist": [from, to]}` (degrees round the subject, degrees above the horizon, distance multiplier).
- `bars3d`: 1 to 10 `items` (revealable), like `bar_chart`; needs a `source`.
- `globe`: country shapes as the Earth's skin (`highlight` colours countries, names as in `map`), `pins` then `arcs` revealable. `focus` is the point it faces mid-scene, `spin` the degrees it turns.
- `network3d`: 2 to 14 `nodes` (`size` 0 to 1), `links` between node `id`s; nodes then links revealable. The layout is computed, the same every time.
