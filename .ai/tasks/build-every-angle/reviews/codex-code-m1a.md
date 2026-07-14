# Code review loop — M1a motion-density detector (workflow v2, Sol thread)

Reviewer: gpt-5.6-sol, effort xhigh, read-only sandbox. Thread `019f5f05-e53c-7fa0-af71-8caa46b78a2b`.
Implementer: Sol, workspace-write thread `019f5efa-8f64-75b1-893c-8fca3acee2dc` (first run with
Sol as implementer — Luna dropped per user decision 2026-07-13).
Scope: `pipeline/ingest.py`, `tests/test_ingest.py`, `tests/test_detector_provenance.py`,
`scripts/eval_detector.py` (coordinator-authored). M0 treated as approved baseline.

## Why this work existed

M0's run on real footage exposed the plan's top risk as real: the audio-RMS + scene-cut gate
found **1 candidate window in 45 minutes and missed both goals**. Fixed-camera amateur football
has flat crowd audio and zero scene cuts, so both original cues were inert.

## Round 1 — REQUEST_CHANGES

1. **Major — incomplete detector provenance** (`pipeline/ingest.py`): `detector_config` omitted
   output-affecting audio knobs (`min_gap_seconds`, RMS floor, median multiplier) and carried no
   algorithm version. Two runs with different tuning could therefore share a provenance hash,
   undermining the anti-mock-contamination rule (plan r2 finding 2).

Streaming decode, interval aggregation, process cleanup, adaptive threshold, and cue-aware
ranking all reviewed clean. Confirmed: `pipeline/` has no BAS ground-truth dependency.

## Round 2 — **APPROVED**

Fix accepted: all knobs promoted to named parameters; `DETECTOR_VERSION` added; config extracted
to `detector_config()` (18 knobs); `tests/test_detector_provenance.py` introspects the detector
functions and fails if any tunable escapes the hash. "No new Critical or Major issues found."

## Measured acceptance (coordinator-run, not implementer-reported)

- **Goal recall 2/2 (100%)** on the real 45-min first half — 1412.5s → `w-006`, 2375.1s → `w-033`,
  both via the new `motion_peak` cue. The prior detector found neither.
- 40 windows = **11.2 min of footage under review out of 45** — the "hours to minutes" claim,
  measured.
- 54 s wall-clock for a 45-min match, single streaming ffmpeg decode, laptop CPU.
- Recall across all SHOT/FREE KICK labels is 22% — **accepted, not a defect**: the event
  vocabulary is goal/save/penalty/card/counterattack, and the product is explicitly
  AI-assisted + human-verified (Verify supports manual add).

Ground truth (`data/match-001/bas/*.json`) is used ONLY by `scripts/eval_detector.py`, never by
the pipeline — re-confirmed by the reviewer.
