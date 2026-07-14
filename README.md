# Every Angle

**Turn raw football footage into searchable, edited content — from a camera on a pole to a live pro feed.**

Sports World Cup Hackathon 2026 · Track 3: Media, Content & Broadcasting

---

## The problem

A 45-minute match is 45 minutes of footage a human has to sit through to find the goals. Content
teams do this by hand, every match, every week. Grassroots clubs mostly don't bother — they film
the game and the footage dies on an SD card.

## What Every Angle does

A pipeline that proposes moments with AI, has a human verify them, and turns the verified events
into a searchable index and a highlight reel.

```
match video ──▶ detect candidate moments ──▶ AI-proposed events ──▶ HUMAN VERIFIES
                (audio + scene cuts + motion)   (vision model)              │
                                                                            ▼
                                                              verified event manifest
                                                                     │         │
                                              semantic search ◀──────┘         └──▶ highlight reel
                                                   (Qdrant)                          (deterministic cut)
```

**The manifest is the only source of truth.** Search results, reels, and commentary derive
exclusively from human-verified events — so the system cannot invent a goal, a name, or a score.
AI proposes; a human decides; everything downstream is grounded in that decision.

## Measured results

On a real 45-minute match (SoccerTrack v2, CC BY 4.0), evaluated against the dataset's
ground-truth event annotations:

| Metric | Result |
|---|---|
| Goal recall | **2 / 2 (100%)** |
| Footage a human must review | **11.2 min instead of 45** |
| Detector runtime | 54 s on a laptop CPU |
| Ball tracked (virtual camera) | 92–98% of frames |

Reproduce it yourself: `python scripts/eval_detector.py data/<video>/windows.json <events>.json --labels GOAL`

> Ground-truth annotations are used **only** to score the detector. They are never an input to it —
> otherwise "AI-proposed moments" would be a lie.

## Two inputs, two buyers

- **Grassroots — one fixed camera, no director.** We generate the camera work *and* the highlights.
  A virtual broadcast camera tracks the ball and crops a moving 16:9 window out of the wide shot,
  so a club with a camera on a pole gets broadcast-style clips. (See `scripts/ball_track.py`.)
- **Professional — an already-directed broadcast.** The camera work exists, so we go straight to
  moment detection, semantic search, and commentary — collapsing an editor's afternoon into minutes.

## Stack

- **Qdrant** — semantic search over verified moments (local embeddings, no per-query API cost)
- **Anthropic Claude** — vision captioning of candidate moments
- **FFmpeg** — detection signals, clip cutting, virtual camera
- **Streamlit** — Verify → Search → Reel

## Run it

```bash
docker compose up -d                        # Qdrant
python -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env                        # add ANTHROPIC_API_KEY
./scripts/run_pipeline.sh path/to/match.mp4 match-001
./.venv/bin/streamlit run app/streamlit_app.py
```

Requires `ffmpeg` on PATH (see `packages.txt`).

## Footage & licensing

All shipped footage is **SoccerTrack v2**, CC BY 4.0 — see `docs/assets-manifest.md` for source,
license, and attribution. Every asset used is recorded there before use. No broadcast footage is
redistributed in this repository or the deployed demo.

## How this was built

Plans and code were cross-reviewed by a second model before landing: Claude coordinates and
implements, GPT-5.6 reviews in read-only sandboxes, and every review round is recorded under
`.ai/tasks/<task>/reviews/`. The protocol lives in `AGENTS.md`. Nothing merged without a review
verdict of `APPROVED`.
