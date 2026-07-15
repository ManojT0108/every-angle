Findings, ordered by severity:

- **P1 — lines 36–38:** Option A does not define a valid direct-frame extractor. The only reusable no-ball path, `extract_wide()`, removes the bottom 29% of a 16:9 broadcast frame; goals, players, and graphics can therefore be silently cropped out. **Fix:** Specify a broadcast-only full-frame, aspect-preserving resize with exact sampling times/order/naming; do not reuse the fixed-camera vertical crop.

- **P1 — lines 36–40, 55–59:** Captioning still assumes fixed wide-angle footage and explicitly tells Claude that the first frames are ball-tracked tight crops and the later frames are wide aftermath shots. Option A would supply directed close-ups, replays, and camera cuts under false instructions, while `profile` currently is not passed to `Captioner.caption()`. **Fix:** Propagate the profile/sampling strategy into proposal generation and select a broadcast-specific prompt while preserving the fixed prompt and behavior unchanged.

- **P1 — lines 41–43, 55–57:** B is not a low-risk companion to A. Standard connected components does not preserve the current radius-3 greedy grouping semantics, its blob thresholds are calibrated for that behavior, and neither proposed library is installed; changing it could regress the approved amateur tracker while adding no broadcast benefit after A skips tracking. **Fix:** Remove B from this deadline task and defer it to a separately benchmarked tracker-hardening change with amateur regression coverage.

- **P2 — lines 34–59:** The plan has no acceptance gate for the new branch. A fast run could select the wrong profile, change frame order/count, emit misleading metadata, or regress fixed sampling without detection. **Fix:** Add tests proving broadcast never calls `track()` and emits the specified full-frame sequence, fixed footage retains its current path/artifact behavior, plus a recorded full 60-window runtime and visual spot-check.

Deadline ranking by leverage per risk:

1. **A, with the corrections above** — overwhelmingly the right product and performance decision.
2. **C, broadcast-scoped only** — an emergency fallback if any broadcast tracking remains.
3. **B** — worthwhile post-deadline engineering, not part of this slice.
4. **E** — unnecessary once A reaches minutes; parallelism adds contention and failure surface.
5. **D** — proxy lifecycle and coordinate remapping complexity without fixing camera-motion candidates.
6. **F** — spend no time on GPU/hardware decode. It does not address the measured CPU-side quadratic hotspot, and after A the remaining extraction should already meet the target.

REQUEST_CHANGES