# Plan: watchable footage in Verify (per-moment clip playback)

## Why (user, 2026-07-16)

The Verify tab shows only captions (and, for pending items, a few still frames). A human cannot
truly VERIFY an AI call without WATCHING the moment. Add a playable video clip to every Verify row
so the reviewer watches, then Keep/Reject. This is core to the "AI-assisted, human-verified"
differentiator and is currently missing.

## Current state

- `ProposalResponse` has `frames: list[str]` (evidence stills), no clip. `Verify.tsx` `ProposalCard`
  renders `<img>` stills; the settled/"Judged" list is text-only.
- Clips exist only for accepted/published EVENTS (e.g. 35 for match-002), named by event id — not
  per pending proposal.
- The source video IS present locally for match-001 and match-002, so proposal clips can be cut.

## Design

- **`ProposalResponse.clip: str | None`** — a `/media` URL to a clip of the proposal's
  `[t_start, t_end]` window, resolved REUSE-FIRST, **status-independent** (Codex P2 / R2 P1):
  1. If `decisions[pid].event_id` is set AND `clips/{event_id}.mp4` exists →
     `/media/{id}/clips/{event_id}.mp4`, **regardless of current accepted/rejected status**. The
     event clip stays on disk after Undo, so a judged row keeps its video. (For match-002 all 35
     notable proposals have event clips → reused, **zero new clips**.)
  2. Else if `clips/proposal-{sha16(proposal_id)}.mp4` exists → that (the `proposal-` prefix avoids
     collision with `e-*` event clips).
  3. Else → `None` (front-end falls back to evidence stills).
- **How proposal-`{sha16}` clips are produced:** a small reusable step cuts a clip via `cut_event`
  over the window ONLY for notable (`type != none`) proposals that resolve to `None` above — i.e.
  no event clip AND no existing proposal clip. Run locally for match-001/002. Never re-cut footage
  that already exists under either name.
- **Deploy (no source video):** the bundle (task #14) must ship `proposals.json`, `decisions.json`,
  the referenced event clips, the proposal-`{sha16}` clips, and the evidence frames — else
  `/api/matches/{id}/proposals` returns empty and Verify has no rows (Codex P1 #2). Add a
  source-free cold-start test that Verify lists rows and a clip plays.
- **Frontend `Verify.tsx`:**
  - **Exclude `type === "none"` from the Judged/settled list (Codex P1 #1)** — those are dismissed
    ordinary play, not moments to verify; this keeps "every Verify row has a clip" true.
  - Render `<video controls preload="metadata">` with `clip` in each `ProposalCard` AND each
    settled row (both pending and judged are watchable). Keep caption + Keep/Reject/Undo. If `clip`
    is null, fall back to the existing evidence stills.

## Tests

- Clip resolution: accepted proposal reuses its event clip; **a proposal rejected AFTER acceptance
  still reuses that event clip** (status-independent); a notable proposal with only a
  `proposal-{sha16}` clip uses it; `clip == None` only when NEITHER file exists.
- `/media` serves a resolved proposal clip (real HTTP GET).
- Frontend: a proposal with a clip renders a `<video>` with that src; without a clip, the stills
  fallback renders; the Judged list excludes `type == "none"`.

## Acceptance

- Local match-002: every Verify row shows a playable clip of the moment; watch → Keep/Reject works.
  web build + oxlint + vitest clean; ruff + pytest green.

## Scope / deadline

Dovetails with deploy task #14 (bundle must ship per-proposal clips). It's now Jul 16 (submissions
open; deadline tomorrow) — keep this tight, and the deploy is still the required artifact.

## Implementation status

- [x] Resolve proposal clips event-first, status-independently, with proposal-file fallback.
- [x] Add the reusable, source-optional proposal clip cutter and run it for both local matches.
- [x] Render clip video or evidence stills in pending and judged rows; omit judged ordinary play.
- [x] Add backend and frontend coverage and pass the full Python/web validation gate.
