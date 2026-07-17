# Plan: reel workflow — Quick Highlights + replace/merge + organizer (R2)

Three cohesive Reel/Search UX features, all client-side over the existing `api.reel(id,
ordered_event_ids)` builder (FFmpeg concat of pre-cut clips — deterministic, can't fail live).

## Current state
- Reel selection is `reel: string[]` (event ids) in `App.tsx`; Search adds ids; the Reel tab builds
  via `api.reel(matchId, selected)` (ORDERED list).
- Verified events: `api.timeline(id)` → `Timeline.events: MomentEvent[]`
  (`id, type, t_start, t_end, clip, from_proposal`). Timeline events = the manifest = the
  human-verified truth (same manifest live-Verify makes canonical).

## Verified-pool integrity (Codex R1 P1#1)
Quick Highlights promotes goals deterministically, so the source manifest must be genuinely
verified. **The DEPLOY ships only match-001 rev 1, which IS human-curated (5 decided events).**
match-002 rev 3 was AUTO-accepted (local testing only, never deployed) and contains replay/
disallowed goals — acknowledged, out of the shipped scope. Dedup (below) collapses replays; a
truly disallowed goal must be rejected by a human in the baseline — verify the shipped baseline has
no false goal before deploy. (No new per-event "verified" field this deadline; the manifest already
IS the verified set.)

## A. Quick Highlights — deterministic, client-side
`web/src/lib/highlights.ts` → `pickHighlights(events: MomentEvent[]): string[]`. No LLM, no endpoint.

1. **Split off celebrations FIRST (Codex R1 P1#3).** Partition events into `plays` (non-celebration)
   and `celebrations`. Reserve the **raw latest celebration** (max `t_start`) as the terminal clip —
   do NOT dedup it into an earlier one. Debit its 1 clip and its duration from the caps up front.
2. **Cluster plays into incidents by time (Codex R1 P1#2).** Sort `plays` by `t_start`. Walk with a
   ROLLING incident end: an event joins the current incident if its `t_start ≤ incidentEnd +
   INCIDENT_GAP` (e.g. 12 s), extending `incidentEnd = max(incidentEnd, t_end)`; otherwise it starts
   a new incident. This correctly merges chained replay windows. Per incident, the representative is
   chosen by **(rank, then earliest t_start, then id)** — fully deterministic.
3. **Rank incidents by representative type:** `goal > penalty > save > counterattack > card`
   (all goals equal).
4. **Absolute caps (Codex R1 P1#3):** `MAX_CLIPS = 8`, `MAX_SECONDS = 90`, **already debited** by the
   reserved celebration. Take incidents in rank order, adding one only if it fits BOTH remaining
   budgets; skip (don't stop) a candidate that would exceed the duration budget. Caps hold even for
   a near-empty pool.
5. **Order:** selected play incidents chronologically by `t_start`, then the reserved celebration
   appended last. Return the ordered event ids.
- **"Quick Highlights" button** (Reel tab; also in Search): runs `pickHighlights(timeline.events)`,
  routes the result through the replace/merge flow (B). **Disabled when `timeline.events` is empty.**
- Unit tests (see F): many goal replays → one clip; disallowed handled by curation not code; latest
  celebration is last; ≤8 clips AND ≤90 s absolute; chronological; empty → `[]`.

## B. Replace vs merge (add from Search / Quick Highlights)
When a selection is applied and the reel is **non-empty**, prompt **Replace** (set reel = new) or
**Merge** (append new ids, preserving existing order, de-duplicating). Empty reel → no prompt.

## C. Reel organizer (reorder before build)
Reel tab renders `selected` as an ordered list with **move up / move down** (zero new dep) + remove.
Build sends `selected` in the chosen order.

## D. Selection ↔ timeline consistency (Codex R1 P1#4)
Live-Verify can remove an event whose id is still in `selected`, which would 404 the build. **On
every timeline refresh, reconcile `selected` to keep only ids still present in `timeline.events`;
the organizer and Build both use this reconciled list.** Test: reject an event after selecting it →
it drops from the reel and Build omits it.

## E. Built-reel staleness (Codex R1 P2#5)
When `selected` changes (replace / merge / remove / reorder) after a reel was built, **reset the
build mutation** (clear the shown video/download) so a stale reel is never displayed against a new
order; the user must rebuild.

## F. Frontend test runner (Codex R1 P2#6)
The web app has no test runner. **Add `vitest` (dev dependency) + an `npm test` script** (the
standard Vite choice; documented new dev dep). Wire `pickHighlights` unit tests and a small
reconcile/replace/merge test. `npm test` joins the acceptance gate.

## Acceptance
- `pickHighlights` unit tests pass under `npm test`; web `tsc` build + oxlint clean; Python
  unaffected.
- Local: Quick Highlights → deduped, capped (≤8/≤90 s), chronological reel ending on the
  celebration; add-from-Search offers Replace/Merge; reorder before Build; rejecting a selected
  moment drops it; changing selection after a build clears the stale reel.

## Out of scope
"Why it matters" blurb, unverified auto-mode, real analytics. Covers tasks #11, #12, #13.
