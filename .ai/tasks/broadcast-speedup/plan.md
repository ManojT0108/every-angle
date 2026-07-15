# Plan: broadcast profile — fast direct sampling + broadcast caption prompt

## Problem (unchanged, evidence retained)

`pipeline/sample.py` → `pipeline/track.py` ball tracker is the sampling bottleneck. On broadcast
it is ~8× slower/frame and turns a 60-window run into hours. Measured single-window benchmark:

| | BROADCAST w-031 (1920×1080) | AMATEUR w-011 (2048×540 proxy) |
|---|---|---|
| `track()` per frame | 184 ms | 22 ms |
| candidate pixels/frame | median 2211, max 79106 | median 15, max 216 |
| `_blobs()` per frame | median 20 ms, **max 6711 ms** | ~2.4 ms |

Root cause: broadcast camera pans/cuts, so the frame-diff "moving" mask fills the frame and the
O(n²) `_blobs()` clustering explodes. Ball-tracking exists to synthesize a tight crop from a WIDE
fixed camera; a broadcast is already directed, so tracking is unnecessary work there.

## Scope

A single new **`broadcast` profile branch** in sampling + captioning. **The `fixed` (amateur) path
must remain byte-for-byte unchanged** — it is already shipped and APPROVED. Options B
(connected-components), D (proxy), E (parallelism), F (GPU) from the prior draft are **OUT of this
task** (deferred; B specifically risks the approved tracker and yields no broadcast benefit once we
skip tracking). This addresses Codex R1 findings P1(×3) and P2 (`reviews/codex-plan-r1.md`).

## How `profile` reaches each stage

`windows.json` already carries a top-level `"profile"` field (`"fixed"` | `"broadcast"`), written by
ingest. match-002's is `"broadcast"`. Both stages read it from the windows artifact — no new CLI
flags, no new detector work.

## Change 1 — `pipeline/sample.py`: broadcast sampling branch (no ball tracking)

- New constant: `DEFAULT_BROADCAST_FRAMES = 8`.
- New extractor `extract_full(source, t, size, destination)`:
  - **Full frame, aspect-preserving, NO vertical crop** (unlike `extract_wide`, which drops 29% of
    height and would silently cut off players/goal/scoreboard on a 16:9 broadcast — Codex P1 #1).
  - ffmpeg: `-ss {t} -i src -frames:v 1 -vf "scale=1280:-2,format=yuvj420p" -q:v 2`. Width 1280,
    height auto (preserves aspect: 1920×1080 → 1280×720). Input-seek before `-i` (fast), same as the
    other extractors.
- In `extract_frames`, read `profile = str(windows_artifact.get("profile", "fixed"))`. If
  `profile == "broadcast"`, for each window take `DEFAULT_BROADCAST_FRAMES` frames evenly spread over
  `[t_start, min(duration, t_end + AFTERMATH_SECONDS)]`, write them as `frame-{i:03d}.jpg` into
  `run_id/window_id/`, and **do not call `track()`**. Record per-window `{"window_id", "t_start",
  "t_end", "frames", "profile": "broadcast", "ball_tracked": None}`. Print a one-line progress note.
- `profile != "broadcast"` → the existing fixed path runs **exactly as today** (track() + tight/wide),
  untouched. Frame discovery downstream (`_sampled_frames` = `sorted(*.jpg)`; `_copy_evidence` renames
  by order) already handles the `frame-NNN.jpg` names — no propose changes needed for discovery.
- **Top-level `samples.json` contract (Codex R2 P2):** `extract_frames` currently always returns
  `tight_frames_per_window` and `wide_frames_per_window`; for broadcast those keys are false (it would
  claim 5 tight + 3 wide for 8 full frames). Broadcast must instead return
  `"profile": "broadcast", "frames_per_window": DEFAULT_BROADCAST_FRAMES` and **omit** the tight/wide
  counts. The fixed artifact is left **exactly as today** (tight/wide counts, no `profile` key added).
  Add a test asserting the broadcast top-level keys and the absence of tight/wide counts.

## Change 2 — `pipeline/captioner.py`: broadcast prompt + profile propagation

- Keep the current `SYSTEM_PROMPT` as the fixed-camera prompt **verbatim** (do not edit its text).
- Add `SYSTEM_PROMPT_BROADCAST`: same schema/rules, but framed for directed TV footage — frames are
  consecutive samples from a broadcast feed (close-ups, wide shots, replays, camera cuts); you CAN
  often see the ball, the shot, the net, celebrations, and on-screen graphics; still label ordinary
  play as `"none"`; never invent names/scores even if a graphic is partly legible; write
  search-style captions. Keep the exact same `RESULT_SCHEMA` and `PROPOSAL_TYPES`.
- `ClaudeCaptioner.__init__` gains `profile: str = "fixed"`. Store it; in `caption()` pick
  `SYSTEM_PROMPT_BROADCAST` when `profile == "broadcast"` else `SYSTEM_PROMPT`. Set
  `prompt_version` to reflect it (`"p2-broadcast"` vs the current `"p2-strict-none"`) so run metadata
  distinguishes them. The per-call user text is already generic (no tight/wide claim) — leave it.
- `make_captioner(name, *, budget_usd=None, profile="fixed")` forwards `profile` to `ClaudeCaptioner`.
  `MockCaptioner` ignores profile (unchanged).

## Change 3 — `pipeline/propose.py`: pass profile to the captioner

- In `main()`, after loading `windows_artifact`, build:
  `captioner = make_captioner(args.captioner, budget_usd=args.budget_usd,
  profile=str(windows_artifact.get("profile", "fixed")))`.
- No other propose changes (`build_proposals` and evidence flow already work with the new frames).

## Change 4 — tests (acceptance gate, Codex P2)

Add to `tests/`:
- **Broadcast skips tracking:** monkeypatch `pipeline.sample.track` to raise; run `extract_frames`
  on a tiny broadcast-profile windows artifact (monkeypatch/stub `extract_full` to write dummy jpgs
  so no real ffmpeg is needed); assert it completes, calls `extract_full` N times/window, names files
  `frame-001..008.jpg`, and never calls `track`.
- **Fixed path unchanged:** with `profile="fixed"` (or absent), assert `track` IS invoked and
  tight/wide naming is produced (stub the ffmpeg/track calls). Guards against regressing amateur.
- **Prompt selection:** `ClaudeCaptioner(profile="broadcast")` uses `SYSTEM_PROMPT_BROADCAST` and
  `prompt_version=="p2-broadcast"`; default uses `SYSTEM_PROMPT` and `"p2-strict-none"`.
  `make_captioner("claude", profile="broadcast")` propagates it. (No network: assert on the selected
  prompt/attributes, not on an API call.)

## Acceptance

- `ruff` clean; full `pytest` green (existing + new).
- Manual: `sample` on match-002 (broadcast) completes in **minutes**, frames are full-frame 1280×720.
- Then `propose --captioner claude` produces captions that read sanely on directed footage.
- Fixed-path tests prove amateur sampling/captioning is unchanged.

## Out of scope / deferred

Connected-components tracker rewrite (B), proxy transcode (D), window parallelism (E), GPU/hwaccel
(F). Recorded here so they are not silently forgotten; none are needed to hit the runtime target.
