# Brag Plan: laya-router

## What is this app?
An OpenAI-compatible proxy that routes every prompt to a cheap or a frontier model using a local decision model, so you keep frontier quality while paying cheap prices for the 80% of prompts that never needed it.

## The angle
The integration is two lines and the savings are measured, not claimed. A blind-judge backtest (both tiers answer every prompt, judge picks blind) says the cheap tier tied or won on 79% of what the router sent it, cutting the bill 54.9%. The video is a quiet infra film: terminal-first, numbers-first, zero marketing voice.

## Hook (first 2-3 seconds)
A terminal types `pip install laya-router` with keystroke sounds, then a single line settles under it: "your LLM bill, routed." Fast-in, then hold.

## Key moments (the middle)
- The two-line adoption: `client = OpenAI(base_url="http://127.0.0.1:8000/v1", ...)` with "that's the whole integration" as the only caption.
- The centerpiece: a curl request and its response headers arriving one by one: `x-laya-route: cheap`, `x-laya-model: gpt-4o-mini`, `x-laya-confidence: 0.90`. A second request lands `x-laya-route: frontier`. The product deciding, live.
- The measured card: `−54.9% cost · 79% quality-tied · $0 per routing decision`.

## Outro / punchline
Wordmark `laya-router` on warm bone background with the pip command under it. Beat, then out.

## User flow worth showing
Point SDK base_url at the proxy → prompt arrives → the X-Laya-* headers reveal which tier the local model chose → the same client, two different routes. This IS the centerpiece scene (real flow, not a diagram).

## Tone
- Preset: polished
- Creative direction: quiet infra tool film, terminal-first, numbers do the talking
- Interpretation: few scenes, longer holds, soft crossfades, restrained motion; typography carries the energy.

## Format: landscape — 1920x1080
## Duration: 20 seconds

## Visual identity (from the project)
- Background: #F7F6F3 (warm bone)
- Text: #111111
- Accents: pale green #EDF3EC (tag text #346538) for cheap, pale blue #E1F3FE (tag text #1F6C9F) for frontier, pale red #FDEBEC for the cost number
- Display font: Instrument Serif (editorial headline moments)
- Body/terminal font: JetBrains Mono
- Strongest visual element: the terminal response with X-Laya-* headers, and the two-tier split (cheap/frontier pills)

## Share copy (draft)
Cut 54.9% off my LLM bill with a router that runs on my own machine. A blind judge says quality tied. Two lines to adopt: pip install laya-router

## Audio direction
- Role: warm minimal bed, sparse professional accents
- Music: calm instrumental bed (warm, low, slightly optimistic), fade out on the outro card
- Music treatment: fade in over the hook, low posture throughout, gentle swell into the measured card, fade to silence on the wordmark
- Music cue guidance: cues to be detected at composition time (bundled presets if a warm/calm track fits); target a strong cue for the measured-card landing (~15s) and the wordmark (~19s)
- Audio-reactive treatment: none; restraint
- SFX posture: sparse, motion-matched: keystrokes on typed commands, one soft tick per arriving header, one low hit on the measured card
- Audio-coupled moments: typed hook line, header-by-header arrival (one tick each), final card hit
- Restraint rule: no risers, no whoosh stacks, no voice-over energy; audio stays under the visuals

## Storyboard

### Scene 1 — Hook: install — 3s
Warm bone background. Terminal window (faux-OS chrome, three light dots) types `pip install laya-router` character by character. Under it, editorial serif line fades in: "your LLM bill, routed."
Sequential/interaction: yes — typing simulation, one line then the caption
Audio intent: quiet confidence, curiosity
Audio-coupled idea: keystrokes while typing; soft land when the caption settles
Music: warm bed starts, low
Transition mood: soft → Scene 2

### Scene 2 — Reveal: two lines — 4s
Same terminal, new block typed fast (not char-by-char): the OpenAI client with base_url pointed at the proxy. Small mono caption below: `# that's the whole integration`. Hold.
Sequential/interaction: yes — code block slides in, comment pops last
Audio intent: "wait, that's it?"
Audio-coupled idea: one keystroke burst, tiny pop on the comment
Music: bed continues
Transition mood: soft → Scene 3

### Scene 3 — Centerpiece: the router deciding — 8s
Terminal again. A curl POST flies in; the response headers arrive one by one, each with a soft tick and a colored pill: `x-laya-route: cheap` (green pill), `x-laya-model: gpt-4o-mini` (neutral), `x-laya-confidence: 0.90` (neutral). Second request slides in: `x-laya-route: frontier` (blue pill). Both pill rows hold side by side for a beat: the same client, two different decisions.
Sequential/interaction: yes — headers one by one (hold each ~0.5s settled), then the pair holds together
Audio intent: the product working; quiet delight
Audio-coupled idea: one tick per header, small lift when the frontier row lands
Music: bed gently builds
Transition mood: clean → Scene 4

### Scene 4 — Punchline: measured — 5s
Clean card on bone: serif headline "−54.9% cost" with mono sublines "79% quality-tied · $0 per routing decision · blind-judge backtest". Bottom: wordmark `laya-router` + `pip install laya-router` mono line. Hold, fade.
Sequential/interaction: yes — number first, sublines stagger in, wordmark last
Audio intent: proof, then silence
Audio-coupled idea: one low hit on the number; wordmark lands dry
Music: swell into the card, fade out to silence
Transition mood: soft fade to end

**Music mood for this video:** calm / quietly optimistic
**Audio summary:** warm low bed under typed terminal moments, sparse ticks tracking each header arrival, one low hit on the measured card, fade to silence on the wordmark.
