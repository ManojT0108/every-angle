# Plan: auto-detect end-of-match celebrations (taxonomy + tail coverage)

## Why

Product decision (user, 2026-07-14): "Every Angle" must capture everything notable in any
uploaded video — amateur or broadcast — including the winning/trophy celebration. Today the
2022 UCL Final trophy lift is NOT searchable in match-002 for two independent, data-proven
reasons:

1. **No `celebration` type.** The full-time on-pitch celebration IS captioned (windows at
   6192–6295 s say e.g. *"winning team players celebrate… wins the final 1-0"*) but the taxonomy
   is `goal/save/penalty/card/counterattack/none`, so it is labelled `none` and excluded at
   publish.
2. **The trophy podium is never sampled.** The detector keeps only the highest-scoring windows
   (`cap`); the calm podium/medal ceremony (~6480 s) scores far below in-play moments, so the
   final ~333 s (105.4→111 min) gets no window → never captioned.

## Hard constraint (do not violate)

`pipeline/ingest.py` `PROFILES` carries an explicit warning: `pre_roll/post_roll/merge_gap/
density_weight/scoring` are **measured at 2/2 goal recall** and must NOT be tuned. This plan
changes **no** measured scoring parameter and does not re-rank or drop any cue-derived window.
Tail coverage only *appends* windows after the existing selection.

## Change 1 — `pipeline/captioner.py`: add the `celebration` type

- `EVENT_TYPES = ("goal", "save", "penalty", "card", "counterattack", "celebration")`.
  `PROPOSAL_TYPES` and `RESULT_SCHEMA` derive from it (auto-update).
- Add ONE rule to BOTH prompts (`SYSTEM_PROMPT`, `SYSTEM_PROMPT_BROADCAST`), all existing rules
  kept verbatim. **`goal` takes strict precedence (Codex P2 #4):** label `goal` whenever the
  frames show evidence of a specific recent goal — the strike, a replay of it, a changed
  scoreline graphic, the immediate goal celebration, OR players returning for a centre-circle
  restart. Reserve `celebration` **exclusively for match-ending / ceremonial scenes**: full-time
  celebrations, lap of honour, players mobbing at the final whistle, trophy lift, medal
  ceremony — i.e. celebration NOT attributable to a specific in-window goal. When in doubt
  between `goal` and `celebration`, choose `goal`.
- Bump `prompt_version`: fixed → `p3-celebration`, broadcast → `p3-broadcast-celebration`.
  Mock captioner unchanged.

## Change 2 — `pipeline/ingest.py`: additive tail GAP-FILLING

Redesign per Codex P1 #1/#2/#3 and P2 #4 — fill the *actual* uncovered gaps in the trailing
region (no gapless-vs-threshold contradiction), keep cue IDs stable, and handle short videos.

- New module constants (NOT inside `PROFILES`): `TAIL_WINDOW_SECONDS = 30`, `MAX_TAIL_WINDOWS = 6`.
  The trailing region length is derived: `TAIL_REGION = MAX_TAIL_WINDOWS * TAIL_WINDOW_SECONDS`
  (=180 s). No coverage-fraction threshold (removed — it caused the P1 #2 contradiction).
- Add a helper `ensure_tail_coverage(kept_windows, duration)` applied AFTER `windows =
  windows[:cap]` **and** on the no-cues fallback path (single shared code path). Use **six FIXED
  EOF-aligned candidate tiles** (Codex R4 P1 — avoids the fragmentation blow-up of per-gap
  tiling), `W = TAIL_WINDOW_SECONDS`:
  1. For `k = 1 .. MAX_TAIL_WINDOWS`, candidate tile `k` is
     `t_end = duration - (k-1)*W`, `t_start = max(0.0, duration - k*W)`. Discard a tile when
     `t_end <= 0` or `t_end <= t_start` (short-video clamping → no zero-length/duplicate tiles).
  2. `covered` = union of kept-window spans.
  3. Append a tile UNLESS it is **fully** covered by `covered` (`[t_start, t_end] ⊆ covered`). A
     partially-covered or uncovered tile is appended IN FULL, so there is no blind gap; a
     genuinely fully-covered tile (match ends in play) is skipped.
  4. There are only `MAX_TAIL_WINDOWS` fixed tiles, so `tail_count <= MAX_TAIL_WINDOWS` holds
     **regardless of how `covered` fragments the region** — assert this, with a fragmented-coverage
     test (many small kept spans splitting the tail still yields ≤ 6 tail windows).
  5. Tail windows: `score=0.0`, all cue flags `False`, `tail=True` (see Change 4). Never remove,
     re-rank, or re-score kept windows.
- **ID stability (P1 #3):** assign IDs to the measured cue windows FIRST (exactly as today —
  sort cue windows by `t_start` and number them), THEN append tail windows with IDs that CONTINUE
  after the last cue ID (e.g. keep numbering `w-{n:03d}`). Do NOT re-sort cue+tail together before
  ID assignment. This guarantees every cue window's `id` is invariant even when a tail tile's
  `t_start` precedes a late cue window's. (The final list is cue windows in `t_start` order
  followed by tail windows; downstream iterates the list and does not require global `t_start`
  order.)
- **Explicit acceptance geometry (P1 #1):** for match-002 (`duration ≈ 6658.577`, kept windows
  end ≈ 6325), `R = [6478.577, 6658.577]` is entirely uncovered → six 30 s tiles, so ~6480 s
  lands in the first tile. A unit test asserts a tail window covers `t = 6480` for this duration,
  and a short-video test (100 s, no cues) asserts tiles stay within `[0, 100]`, unique, positive
  length.
- Applies to both profiles (regime-agnostic; footage already ending in play has `R` covered, so
  nothing is appended).

## Change 3 — detector provenance (Codex P1 #3)

- Bump `DETECTOR_VERSION` `"d3-percentile"` → `"d4-tail"` so a tail-aware `windows.json` is
  distinguishable from an old one.
- Emit the tail constants that actually determine output in `detector_config`:
  `tail_window_seconds`, `max_tail_windows`, and the derived `tail_region_seconds`
  (`= max_tail_windows * tail_window_seconds`). There is no `tail_covered_fraction` (the design
  uses exact gap-filling, so no threshold exists to record). Do NOT modify `PROFILES`. Test their
  presence.

## Change 4 — `CandidateWindow` dataclass marker + honest non-regression (Codex P2 #6, P2 #5)

- Add `tail: bool = False` to the **`CandidateWindow`** dataclass (the actual class in
  `pipeline/ingest.py`, not `Window`). This adds a `"tail": false` key to every serialized window
  — a deliberate, `DETECTOR_VERSION`-bumped format change, NOT a silent one.
- Redefine the non-regression invariant as a **projection**, not byte-for-byte: for every
  cue-derived window the tuple `(id, t_start, t_end, audio_peak, scene_cut, motion_peak, score)`
  is unchanged by this change. Tests assert that projection (this is the real goal-recall guard),
  and assert tail windows carry `tail=True, score=0.0`, all cue flags `False`.

## Change 5 — taxonomy consistency across API + web (Codex P2 #5)

The auto search/read path already carries `type` as `str` (not blocked), but the manual-event
contract hardcodes the 5 types:
- `api/main.py`: add `"celebration"` to the `EVENT_TYPES` `Literal` (used by the human-event
  request model) so a human can also mark a celebration; keep read/search models as `str`.
- `web/src/lib/api.ts`: add `"celebration"` to the `EventType` union (and any manual-event
  selector) so the client contract and display include it.
- Update/extend the API contract tests to include `celebration`.

## Change 6 — re-run broadcast end-to-end (data, after code APPROVED) — Codex P1 #1

match-002's current `manifest.json`/rev-2 is an **auto-generated draft, not human-verified**, so
regenerate it wholesale (no append/preserve ambiguity):
- Re-ingest match-002 (new windows incl. tail) → sample (broadcast, fast) → propose
  (`--captioner claude`, budget cap) → **rebuild `decisions.json` + `manifest.json` from the new
  run's notable proposals** — notable = **every proposal whose type is not `none`** (all six
  event types: goal/save/penalty/card/counterattack/celebration; do NOT drop penalty or
  counterattack — Codex P1 #3) — with fresh event IDs → cut clips → `publish_revision` as
  **rev 3** (`moments_rev_3`; never reuse rev 1 = match-001). Optionally delete the orphaned
  `moments_rev_2`.
- Verify a "winning celebration / trophy lift" search now returns the ceremony. Because this is a
  fresh nondeterministic captioning run with new IDs, do NOT assert prior captions/IDs/counts are
  "unchanged" (Codex P2 #4); instead assert **no known event class disappears** — goal, save, and
  card coverage from the rev-2 draft is still represented, plus celebration now appears.
- **match-001 (shipped amateur demo, rev 1) is NOT re-run by default** — its footage has no
  ceremony and re-indexing would change the deployed demo. Leave it unless the user asks. (User
  decision; do not auto-run.)

## Acceptance

- ruff clean; full pytest green (existing + new). Cue-derived detector output unchanged under
  the projection above (goal-recall guard). Fixed prompt keeps all prior rules; `goal` precedence
  explicit.
- Manual: match-002 re-run; "winning celebration"/"trophy lift" returns the end-of-match
  ceremony; **no known event class disappears** — goal, save, and card coverage from the rev-2
  draft is still represented (per the fresh-run policy, NOT an exact "unchanged" check), and
  celebration now appears. `DETECTOR_VERSION` and tail constants present in `windows.json`.
