# Hyperframes Composition Brief: laya-router

## Objective
Create a short launch-style brag video for laya-router.

## Output
- Composition directory: `brag-output/composition/`
- Rendered video: `brag-output/brag.mp4`
- Format: landscape — 1920x1080
- Duration: 20 seconds

## Source Material
- Project root: `C:\Code Main\laya-router`
- Primary files read: README.md (quickstart, curl session, measured backtest tables), examples/quickstart.py, src/laya_router/server.py (X-Laya-* headers)
- Product name: laya-router
- Tagline / strongest claim: −54.9% LLM cost with quality tied, measured by a blind judge; routing decisions run locally and cost $0
- Key UI or visual moment to recreate: a terminal window where response headers arrive one by one (x-laya-route: cheap / frontier) with tier-colored pills
- Copy that must appear verbatim:
  - `pip install laya-router`
  - `client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="sk-...")`
  - `x-laya-route: cheap`
  - `x-laya-route: frontier`
  - `x-laya-model: gpt-4o-mini`
  - `x-laya-confidence: 0.90`
  - `−54.9% cost`
  - `79% quality-tied · $0 per routing decision`

## Creative Direction
- Tone preset: polished
- Creative direction: quiet infra tool film, terminal-first, numbers do the talking
- Interpretation: few scenes, longer holds, soft crossfades, restrained motion; typography carries the energy. Warm monochrome editorial palette; color only as pale tier pills (green = cheap, blue = frontier, red = the cost number).
- Angle: the integration is two lines and the savings are measured, not claimed; a blind-judge backtest says the cheap tier tied or won on 79% of routed prompts while cutting the bill 54.9%.
- Hook: terminal types `pip install laya-router`, then the serif line "your LLM bill, routed." settles under it.
- Outro / punchline: measured card (−54.9% cost, 79% quality-tied, $0 per decision) into the `laya-router` wordmark.
- Avoid:
  - Generic SaaS language
  - Abstract filler visuals
  - Unrelated visual redesign
  - Emojis, neon, gradients, AI-purple

## Visual Identity
- Background: #F7F6F3 (warm bone)
- Text: #111111 (never pure black backgrounds)
- Accent: pale green #EDF3EC / #346538 (cheap), pale blue #E1F3FE / #1F6C9F (frontier), pale red #FDEBEC / #9F2F2D (cost number)
- Display font: Instrument Serif (editorial headline moments; fallback Newsreader)
- Body/terminal font: JetBrains Mono (fallback SF Mono)
- Visual references from the project: faux-OS terminal window with three light dots (1px #EAEAEA borders), X-Laya-* header rows, tier pills (9999px radius, tiny uppercase tracking), mono numbers

## Storyboard
Use the storyboard in `brag-output/brag-plan.md` as the creative contract.

Scene summary:
1. Hook: install — 3s — typed `pip install laya-router` + serif caption "your LLM bill, routed."
2. Reveal: two lines — 4s — the two-line OpenAI client adoption + `# that's the whole integration`
3. Centerpiece: the router deciding — 8s — curl request; headers arrive one by one with pills; second request routes frontier; both rows hold
4. Punchline: measured — 5s — serif "−54.9% cost" + mono sublines + wordmark + pip line

## Audio
- Audio role: warm bed, sparse professional accents
- Audio arc: quiet bed under typed moments, sparse ticks tracking header arrivals, one low hit on the measured card, fade to silence on the wordmark
- Music: `happy-beats-business-moves-vol-10-by-ende-dot-app.mp3` (copied to `brag-output/composition/assets/music/`)
- Music treatment: low volume posture throughout, gentle swell into scene 4, fade out under the wordmark
- Music cue guidance: bundled preset at `brag-output/composition/assets/music/happy-beats-business-moves-vol-10-by-ende-dot-app.music-cues.json` (109.96 BPM); lock the scene-4 card landing to a strong cue if one falls near ~15s; header arrivals may tick to the beat grid but never outrun readability (hold each header ≥0.5s settled)
- Audio-reactive treatment: subtle at most (terminal glow/breathing); skip entirely if extraction is unavailable — restraint fits this tone
- Audio-coupled moments:
  - Scene 1 typed line — keystrokes
  - Scene 3 header arrivals — one soft tick each
  - Scene 4 measured card — one low hit; wordmark lands dry
- SFX selection guidance: keyboard ticks for typing, interface ticks for header arrivals, one impact for the card; sparse, motion-matched
- SFX analysis guidance: `assets/sfx/sfx-analysis.md` at the /brag skill dir; prefer low high-frequency-risk files for repeated ticks
- Exact SFX choice: Hyperframes chooses filenames, timestamps, density, volume
- Audio files: copy the chosen music and SFX into `brag-output/composition/assets/`

## Hyperframes Instructions
Load the composition-building Hyperframes domain skills (`hyperframes-core`, `hyperframes-animation`, `hyperframes-creative`, `hyperframes-keyframes`, `hyperframes-cli`) and build in `brag-output/composition/`. /brag is its own workflow: do not enter the hyperframes entry-point interview and do not route into its generic promo workflow.

Requirements:
- Show the terminal/flow recreations described above (real product copy, verbatim).
- Keep all text readable in the final render (hold floors per brag plan).
- Keep the video within 15-25 seconds (target 20).
- Include the music/SFX layer as described.
- Run `hyperframes check` before render — the single gate.
