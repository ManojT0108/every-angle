# Every Angle — architecture plan

Status: v5 — **APPROVED** by Sol review loop, round 5 of 5, 2026-07-13 (`reviews/codex-plan-v2-loop.md`). Round 1 history: `reviews/codex-plan.md` (old single-pass tooling). This version is the implementation baseline for M0.

## System overview

Two halves, deliberately decoupled:

1. **Offline pipeline (local, Python, run once per video):** produces all expensive artifacts ahead of demo time — sampled frames, AI-proposed moments, pre-cut event clips. Everything cached on disk; re-runs are incremental.
2. **App (Streamlit, 3 views):** Verify → Search → Reel. Reads only pipeline artifacts + Qdrant. No model calls on the demo hot path except query embedding (local model) and optional commentary generation (small, manifest-grounded).

```
video.mp4 ──▶ [1 ingest] ──▶ audio-cue windows + scene cuts
                 │
                 ▼
          [2 sample] frames @ candidate windows only (cost control)
                 │
                 ▼
          [3 propose] vision-LLM captions frames → proposals.json
                 │
                 ▼        (human, in app)
          [4 Verify view] ─────▶ manifest.json (verified events)
                 │                       │
                 ▼                       ▼
          [5 clip] ffmpeg pre-cuts   [6 index] embed captions → Qdrant
             clips/e-*.mp4                     │
                                               ▼
          [7 Search view] query → local embed → Qdrant → event cards + clip playback
                 │
                 ▼
          [8 Reel view] selected events → ffmpeg concat → reel.mp4 + text commentary
```

## Key design decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Language/stack | Python 3.11 end-to-end; Streamlit UI | User's strength; fastest to Gate 2. UI re-skin is a Gate-3+ luxury, not a dependency. |
| D2 | Vision-LLM | Anthropic Claude (vision) via API; **mock captioner until key arrives** | Pipeline runs end-to-end today with `MockCaptioner` (returns canned captions); real captioner is a drop-in class swap. Key = user blocker, needed before Gate 2. |
| D3 | Candidate windows first, captions second | Audio RMS peaks (crowd roar) + ffmpeg scene cuts gate which frames get captioned | Caption cost scales with candidate windows, not video length. Cap: ≤40 windows/video, ≤4 frames/window. |
| D4 | Embeddings | Local `sentence-transformers` MiniLM (via qdrant-client FastEmbed) | No second API key, no per-query cost, CPU-fast, offline demo safe. |
| D5 | Qdrant | Local Docker for dev; decision point at deploy (Qdrant Cloud free tier vs bundled local) | Smoke-tested today. Collection `moments`, cosine, one named vector. |
| D6 | Clip strategy | Pre-cut each verified event to its own H.264/AAC file at verify time | Avoids Streamlit seeking limits on one big file; reel concat becomes trivial; clips double as search-result previews. |
| D7 | Reel assembly | ffmpeg concat demuxer over pre-cut clips, re-encoded uniform (H.264 yuv420p, AAC, 720p) | Deterministic, no re-encode surprises at demo time; codec verified in browser on deploy target (Gate 2 checklist). |
| D8 | Commentary | Template-first; optional LLM pass constrained to manifest fields + post-check (no tokens not traceable to manifest: names, scores, minutes) | Ideation finding #8: factuality from verified manifest, not guardrails. Template alone is an acceptable MVP. |
| D9 | Deploy | Default: Streamlit Community Cloud + Qdrant Cloud; fallback: local run + prerecorded video | InsForge hello-world (≤1h timebox) may change this — evaluated in Gate-1 smoke test, not assumed. |
| D10 | **Artifact delivery** (r1 finding 1; r3 finding 2) | Precomputed artifacts (`manifest.json`, `clips/`, `thumbs/`, sample proposals+evidence for D11) are zipped into a versioned **release bundle** uploaded to object storage (or attached as a GitHub release asset). Every bundle embeds an immutable `bundle.json`: revision number, exact Qdrant collection name, per-artifact checksums, created_at. The deployed app reads `BUNDLE_URL` + `BUNDLE_SHA256` env vars (documented in `.env.example`), downloads + verifies + unpacks to local cache on boot, and derives its Qdrant collection EXCLUSIVELY from `bundle.json` — never from an external pointer. Qdrant collections are retained while any deployed bundle references them. Local dev reads `data/` directly via `CURRENT_REV`. | Repo stays small, host restarts self-heal, a deployed host can never desync from its bundle. Source video is never deployed — only pre-cut clips. |
| D11 | **Deployed Verify view is a guided demo mode** (r1 open question 2; r2 finding 4) | The bundle ships a small sample of pending proposals WITH their evidence thumbnails so the verify workflow is demonstrable; accept/reject/edit are session-only and cannot publish; Search/Reel always serve the shipped verified revision. The real publish path is local-only. | Keeps the hosted app stateless and honest — no hosted edit can desync from the shipped clips/index. |
| D12 | **Staged publish, atomic promote** (r1 finding 3; r2 finding 1) | One `publish` command/button building the FULL revision N before anything goes live: (1) stage manifest + regenerated clips (changed `(source, t_start, t_end)` hashes) + thumbnails in `staging/`; (2) validate — every event has a playable clip, checksums recorded; (3) build Qdrant collection `moments_rev_N`, verify point count == event count; (4) atomically promote — `CURRENT_REV` pointer file written temp+rename, local app reads collection by that pointer; (5) superseded revisions and their Qdrant collections are deleted only when no deployed bundle references them (same retention rule as D10), and never before the next successful publish. Failure before (4) leaves N−1 fully live. The D10 release bundle is zipped only from a promoted revision (`bundle-revN.zip`, checksummed). | No partial revision is ever observable — locally, in Qdrant, or in the deployed bundle. |
| D13 | **Reproducible runtime** (r1 finding 4; r2 finding 5) | Pinned `requirements.txt`; exact embedding model name + revision pinned, weights pre-fetched into the release bundle (or host cache) at deploy — no registry download on cold start; `docker-compose.yml` for local Qdrant; `packages.txt` (ffmpeg) for Streamlit Cloud; clean-venv smoke test plus a cold-start search check (network to model registries blocked) before Gate 3. | "Works on one machine" and "worked until the host restarted during judging" are the classic killers. |

## Data contracts (single source of truth)

`data/<video_id>/proposals.json` — pipeline output, append-only per run, with run provenance
(r2 finding 2 — so mock output can never masquerade as real):

```json
{"video_id": "match-001",
 "asset": "docs/assets-manifest.md#match-001",
 "runs": [
   {"run_id": "r-002", "created_at": "2026-07-14T08:00:00Z",
    "source_sha256": "…", "detector_config_hash": "…",
    "captioner": {"name": "claude", "model": "claude-…", "prompt_version": "p1"}}],
 "proposals": [
   {"id": "r-002-p-001", "run_id": "r-002", "t_start": 754.0, "t_end": 769.0,
    "type": "goal", "confidence": "high",
    "caption": "Low shot from inside the box beats the keeper at the near post",
    "evidence": {"frames": ["frames/r-002-p-001/*.jpg"], "audio_peak": true, "scene_cut": true}}]}
```

Gate rule: the M1 vertical slice must be fed by a proposal whose run has
`captioner.name != "mock"` — asserted in code, not by eyeballing.

Proposal ids are globally unique across runs — the run id is embedded (`r-002-p-001`), so a
mock-run proposal can never share identity (or decision state) with a real-run proposal
(r3 finding 1). `decisions.json` and `from_proposal` reference only these run-scoped ids.
Evidence paths are run-scoped too (`frames/<proposal-id>/…`, r4 finding 1) — no run can
overwrite another's frames — and the pipeline validates that every proposal's evidence files
live under its own id before writing proposals.json.

`data/<video_id>/decisions.json` — persisted review state (r2 finding 3): maps run-scoped
`proposal_id → {status: pending|accepted|rejected, event_id?}`. Rejected proposals stay
rejected across reloads; nothing returns as unreviewed.

`data/<video_id>/manifest.json` — human-verified, the only factuality source:

```json
{"video_id": "match-001",
 "events": [
   {"id": "e-001", "from_proposal": "r-002-p-001",
    "t_start": 753.5, "t_end": 770.0, "type": "goal",
    "caption": "Low finish at the near post after a counterattack",
    "team": null, "player": null,
    "clip": "clips/e-001.mp4",
    "verified_at": "2026-07-14T09:12:00Z"}]}
```

Rules: `type` ∈ {goal, save, penalty, card, counterattack}. `team`/`player` stay `null` unless the human fills them in — commentary may never invent them. `from_proposal` is `null` for manually added events (r2 finding 3). Verify view MVP (r1 finding 5): accept/reject, edit times/captions, manual add. Merge/split deferred unless real footage proves the need.

Qdrant point = embed(`caption` + `type`), payload = full event object. Collection recreated idempotently from manifest.json on each index run — manifest is truth, Qdrant is a cache.

## Repo layout

```
pipeline/        ingest.py sample.py propose.py clip.py index_qdrant.py
                 captioner.py (Captioner ABC: MockCaptioner | ClaudeCaptioner)
app/             streamlit_app.py  views/{verify,search,reel}.py  commentary.py
data/            (gitignored) <video_id>/{source.mp4,frames/,clips/,proposals.json,manifest.json}
docs/            assets-manifest.md  demo-script.md
scripts/         run_pipeline.sh  codex-review.sh
.env.example     ANTHROPIC_API_KEY, QDRANT_URL, QDRANT_API_KEY, BUNDLE_URL, BUNDLE_SHA256
```

## Milestones → gates

- **M0 (tonight, Gate 1): DONE, code review APPROVED** (`reviews/codex-code-m0.md`). Scaffold + ingest/sample/propose on real footage; Qdrant compose service green; asset manifest; portal checklist (`docs/submission-checklist.md`). InsForge parked — absent from the portal's sponsor stack.
- **M1a: motion-density detector (D3 fallback) — DONE, APPROVED** (`reviews/codex-code-m1a.md`). Third cue (`motion_peak`) added alongside audio peaks and scene cuts; cue-count-aware scoring; 18-knob `detector_config()` + `DETECTOR_VERSION` in the provenance hash, guarded by a test. **Measured on real footage: goal recall 2/2 (100%), 40 windows = 11.2 min under review out of 45, 54 s runtime.** Evaluation harness: `scripts/eval_detector.py` (uses BAS ground truth — EVAL ONLY, never pipeline input).
- **M1b (Gate 2, midday Jul 14):** vertical slice with REAL captioner on ≥1 moment: video → proposal → verify → index → search hit → clip plays in browser. Codec test on deploy target. **Fail → pivot decision per ideation plan.**
- **M2 (EOD Jul 14):** full proposal pass on the whole chosen footage; Verify view complete; 8–12 golden queries drafted against actual manifest; per-video API cost measured and logged.
- **M3 (Gate 3, midday Jul 15):** Search + Reel views complete, template commentary, deployed, demo script written. Feature freeze.
- **M4 (Jul 15 PM+, only if green):** layered additions in ideation-plan order; each gets its own task dir.

## Broadcast footage readiness (user supplying a 1h50m directed broadcast, 1 goal)

The pipeline was built and tuned on a FIXED-camera amateur panorama. A directed
broadcast breaks several assumptions — most of them in our favour, one badly against.

| Component | On fixed amateur camera | On directed broadcast | Action |
|---|---|---|---|
| Audio-RMS cue | inert (flat amateur audio) | **strong** — crowd roar + commentator shouting on a goal | keep; it finally earns its place |
| Scene-cut cue | inert (a fixed camera never cuts) | **strong, but noisy** — hundreds of cuts (replays, close-ups, crowd) | keep; the ≤40-window cap and cue-count scoring must stop cuts from flooding candidates |
| Motion-density cue | **the only working cue** | **likely harmful** — the camera pans and zooms, so frame-differencing lights up the WHOLE frame on every pan; every camera move looks like a motion peak | must gate: suppress motion cue when global motion dominates (a pan moves everything; a play moves a region) |
| Ball tracker | needed, works (92–98%) | **will degrade** — it assumes a static background; a panning camera makes everything "moving" | not needed: broadcast frames are already zoomed and legible |
| Tight ball-crops for captioning | **essential** (players ~5px) | **unnecessary** — the director already framed the action | add a framing mode: `ball` (fixed camera) vs `native` (broadcast) |
| Virtual camera | the differentiator | not applicable — a human already directed it | skip for broadcast; it is the grassroots half of the story |
| Replays | none | **a goal is shown 2–3x** → duplicate detections | dedup near-identical events, or treat replays as evidence (a replayed moment IS important) |
| Runtime | 54s for 45 min | ~2.5 min for 110 min (linear) | fine |

**The headline risk is the motion cue inverting**: on a moving camera it goes from our best
signal to our worst. Audio + scene cuts should carry the broadcast case, which is the mirror
image of the amateur case — a nice demonstration that the three-cue design is the right one,
but only if we actually gate the motion cue rather than trusting it blindly.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| No API key yet | MockCaptioner path keeps everything unblocked; key needed by Jul 14 morning (user). |
| Footage licensing unclear | Gate-1 asset manifest with license evidence per source; primary + one backup source; avoid CC-ND; check music/commentary layers separately. |
| Vision-LLM misses events | Verify view supports manual add — demo narrative is "AI-assisted, human-verified", so recall gaps are a workflow feature, not a lie. Golden queries written against the verified manifest, not hopes. |
| Cost blowup | D3 caps; measure on first real run (M2); one video only. |
| Amateur footage lacks crowd-audio peaks (SoccerTrack v2 primary asset) | D3 falls back to scene-cut/motion-density gating; validate on first ingest (M0). Dataset ships event annotations — used as **evaluation ground truth only**, never as pipeline input, or the "AI-proposed" story is fake. |
| Browser codec/deploy surprises | D7 uniform re-encode; codec test at Gate 2, deploy dry-run Jul 15, prerecorded fallback Jul 16. |
| Streamlit video jank | Pre-cut clips (D6); no seeking of the big source file in-app. |

## Verification plan (per milestone)

M0: `pytest` unit tests for window detection + manifest round-trip; run pipeline on real footage with mock captioner; curl Qdrant search returns the seeded moment. M1: scripted end-to-end run documented in task handoff with timings. M2+: golden-query pass/fail table checked into `docs/demo-script.md`; implementation Codex review at M3.

## Review triage

Round 1 (2026-07-13, old single-pass tooling, `reviews/codex-plan.md`, 5 findings):

| # | Sev | Finding (short) | Disposition |
|---|---|---|---|
| 1 | H | No artifact delivery strategy for deploy | **Accepted** — D10 release bundle + D11 hosted verify demo mode |
| 2 | M | M0 omits InsForge + portal deliverables | **Accepted** — added to M0 acceptance |
| 3 | M | Manifest edits leave clips/Qdrant stale | **Accepted** — D12 staged publish |
| 4 | M | No reproducible runtime/deps | **Accepted** — D13 pinned deps, compose, packages.txt |
| 5 | L | Verify UI scope aggressive | **Accepted** — MVP = accept/reject/edit/add; merge/split deferred |

Round 2 (2026-07-13, Sol thread `019f5e2a`, workflow v2, 5 findings):

| # | Sev | Finding (short) | Disposition |
|---|---|---|---|
| 1 | P1 | D12 promotes manifest before clips/Qdrant/bundle — not atomic | **Accepted** — D12 rewritten: stage full revision, validate, atomic `CURRENT_REV` promote, keep N−1 |
| 2 | P1 | Proposal cache lacks provenance; mock data could pass the M1 "real captioner" gate | **Accepted** — run provenance in proposals.json + coded gate assert |
| 3 | P2 | Rejected proposals not persisted; `from_proposal` undefined for manual events | **Accepted** — decisions.json + nullable from_proposal |
| 4 | P2 | Hosted Verify claims workflows the bundle can't support | **Accepted** — D11 guided demo mode with sample evidence, session-only edits |
| 5 | P2 | Embedding model artifact unpinned — cold-start download during judging | **Accepted** — D13: pin model+revision, pre-fetch weights, cold-start check |

Round 3 (2026-07-13, same Sol thread, resume; prior 5 confirmed addressed, 2 new):

| # | Sev | Finding (short) | Disposition |
|---|---|---|---|
| 1 | P1 | Proposal ids collide across runs — mock/real could share decision state | **Accepted** — run-scoped globally-unique ids (`r-002-p-001`) everywhere |
| 2 | P2 | Deployed revision selection implicit; bundle lacks own metadata; env vars undocumented | **Accepted** — immutable `bundle.json` in every bundle, app derives collection from it only, `BUNDLE_URL`/`BUNDLE_SHA256` in `.env.example`, referenced collections retained |

Round 4 (2026-07-13, same Sol thread; r3 fixes partially complete, 1 new):

| # | Sev | Finding (short) | Disposition |
|---|---|---|---|
| 1 | P1 | Evidence frame paths not run-scoped — later run overwrites earlier run's frames | **Accepted** — `frames/<proposal-id>/…` + pipeline validates evidence belongs to its run |
| 2 | — | Manifest example still used unscoped `from_proposal`; D12 retention contradicted D10 | **Accepted** — example fixed; single retention rule: delete only when no deployed bundle references it |

## Open questions

1. USER: Anthropic API key (preferred) — needed before Gate 2. OpenAI acceptable fallback (captioner class swap).
2. USER: OK to spend ~$5–15 API budget on captioning runs?
3. Deploy target final call after InsForge smoke test (D9) — decision due Gate 3, not before.
4. Object-storage home for the release bundle (D10): GitHub release asset vs sponsor storage — decide with 3.
