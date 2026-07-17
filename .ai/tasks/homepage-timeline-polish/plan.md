# Plan: homepage stats + clickable timeline (R2, Codex-scoped for the deadline)

Codex recommendation adopted: **ship items 1 (stats) + 2 (clickable timeline)**; **defer item 3**
(live duplicate-cascade is a risky multi-store transaction) and instead **curate duplicates out of
the demo data**; **defer item 4** (opening) as future reel/intro metadata (deployable match-001 has
no lineup footage — it starts at 203s midfield; lineups are only in local-only match-002).

## 1. Homepage stat tiles — useful & derived (Codex P2#5)
Replace the current 5 tiles (`App.tsx:104–115`) with four, all derived (App must also fetch the
proposals response, which today it does not):
- [x] **Footage to review — X of Y** (the "hours → minutes" pitch: reviewed vs total).
- [x] **AI proposals** (count of notable proposals from the latest run).
- [x] **Verified clips** (`tl.events.length`).
- [x] **Awaiting review** (notable proposals still `pending`).
Drop candidate-windows / goals-kept / rejected-by-human. Avoid "moments detected" (overstates
duplicates/false positives).

## 2. Clickable match timeline (`Timeline.tsx`) — Codex P2#6
- [x] Pass **`matchId`** into `Timeline` (it currently receives none); resolve a bar's clip via
  **`mediaUrl(matchId, clip)`** (relative `clips/e-….mp4` would 404 otherwise).
- [x] Clicking a bar that maps to an event **with a clip** opens the shared modal player. **Extract a
  controlled shared modal** (from `ClipThumb`) whose trigger is the timeline bar — do NOT nest
  `ClipThumb`'s `<video>`/button inside the existing bar `<button>` (nested-button bug). Bars with
  no clip stay inert. Keyboard-accessible.

## 3. Duplicate / false moments — MANUAL human curation, no auto-dedup (Codex R2 P1×2)
Both auto approaches are unsafe: the live edit-cascade is a distributed transaction, and automatic
time-clustering KEEPS false positives (match-002's ~2830–2875s "goal" is disallowed, score 0–0) and
MISSES delayed replays (the ~6000.8s replay of the real 3980s goal is outside any gap). So this is a
**coordinator human-judgment pass**, recorded, NOT automatic:
- For the **deployed match-001**: manually inspect its accepted events, **reject false incidents and
  semantic duplicates (incl. delayed replays), keep one correct representative per real incident**,
  and record the exact kept/rejected proposal ids in the bundle notes. This cleans **Search / Reel /
  Highlights** (one correct result per incident) — the surfaces judges use.
- For local **match-002**: the user curates it themselves with the now-built Reject / edit-to-`none`
  tools (this is literally the human-verify step).
- **Honest scope (Codex R2 P1#1):** rejecting removes an item from Search/Reel but the Review
  "Judged" list and Timeline still render rejected marks (provenance). A visual Review/Timeline
  *collapse* of duplicates is a **display-only fast-follow**, deferred — not promised here.
- No dedup/cascade code this pass.

## Tests
- [x] Stats render from timeline + proposals data (unit/render); no hardcoded values.
- [x] Timeline bar with a clip opens the modal (clip resolved via `mediaUrl`); no-clip bars inert; no
  nested `<button>`.

## Acceptance
Local: homepage shows the four derived tiles; clicking a timeline bar plays that moment. After
curation, each real incident appears at most once in **Search / Reel / Highlights**, and no false
incident (e.g. a disallowed goal) is searchable; the kept/rejected ids are recorded. (Review's
Judged list may still show rejected items — the visual collapse is deferred.) ruff + pytest +
npm test + web build/oxlint green.

## Deferred (fast-follow, after deploy)
- Item 3 live incident-cascade — if revisited, one canonical event carrying member proposal ids,
  with full snapshot/rollback/reconcile and reader-side locking.
- Item 4 opening/line-ups — per-match reel/intro metadata with a pre-cut clip, not a fake event.
