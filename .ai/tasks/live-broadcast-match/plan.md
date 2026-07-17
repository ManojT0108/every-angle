# Plan: add the processed broadcast match to the live demo

## Goal

Expose the already-processed local `match-002` broadcast dataset beside `match-001` on the
Render demo. Preserve its current published revision 3, 30-event verified manifest, detector
timeline, proposal decisions, semantic-search payloads, and playable clips. Do not ship the
2.9 GB source video or regenerate any AI output.

The user explicitly replaced the previous local-only release boundary on 2026-07-16, asked for
this exact processed match on the public demo, and confirmed they have permission to publicly
redistribute `match-002`.

## Bundle and runtime

- [x] Extend `scripts/build_deploy_bundle.py` to build `deploy/bundle/match-002` from the current
  local artifacts using an allowlist:
  - `CURRENT_REV`, `windows.json`, `proposals.json`, `decisions.json`;
  - `staging/rev-3/manifest.json`;
  - every existing root `clips/e-*.mp4` needed by accepted or rejected notable proposals;
  - the first evidence frame for each latest-run proposal, which is the only frame used as the
    Review poster.
- [x] Do not copy source footage, samples, reels, old staging revisions, or all eight evidence frames.
- [x] Keep the existing match-001 pending-review fixture and baseline unchanged.
- [x] Bake both match directories into the Docker baseline and restore both on every container start.
- [x] Keep the build-time source-video guard, but remove the obsolete match-002 prohibition.

## Cloud search

- [x] Make `scripts/seed_qdrant.py` resolve the manifest path from `CURRENT_REV` instead of hardcoding
  `staging/rev-1`; retain its non-destructive create/upsert/verify behavior.
- [x] Seed `match-002` as `moments_rev_3` using the existing Qdrant Cloud credentials and verify at
  least the 30 manifest events are present. Do not modify `moments_rev_1`.

## Product surface and truthful copy

- [x] Add match-002 metadata to the existing automatic multi-match selector as `Broadcast feed` /
  `user-provided`; do not hardcode teams, score, or event facts in the UI.
- [x] Update `docs/assets-manifest.md` to record the user's redistribution authorization and the exact
  derived artifacts being shipped before copying those artifacts into the tracked bundle.
- [x] Update deployment comments and README text that currently state match-002 can never ship, while
  preserving the SoccerTrack attribution.
- [x] Keep all data-driven behavior unchanged: selecting match-002 loads its revision-3 summary,
  timeline, Review decisions, search results, clips, and reel flow.

## Verification and release

- [x] Test the bundle builder with an isolated temporary fixture so the allowlist and revision-derived
  manifest path are guarded without copying real media in the test.
- [x] Run Ruff, pytest, frontend tests, frontend build/lint, `git diff --check`, and a Docker build.
- [x] Run the independent code-review loop and preserve its final verdict.
- [x] Commit and push the release to `main` (authorized by the user's request to update the live demo),
  then trigger/observe Render's deployment and live-smoke both match IDs, match-002 search, one
  broadcast clip, and reel assembly.

## Acceptance

- [x] `/api/matches` lists both `match-001` and `match-002`.
- [x] Match-002 reports revision 3 and 30 published events.
- [x] A match-002 semantic query returns a relevant verified hit from `moments_rev_3`.
- [x] At least one match-002 clip serves as `video/mp4`, and a two-event reel builds and serves.
- [x] No source video or credential is tracked or present in the Docker baseline.
