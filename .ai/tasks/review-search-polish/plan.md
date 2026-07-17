# Plan: Review + Search polish (R2, Codex-hardened)

Rename "Review", compact modal player, caption/type editing, chronological Search browse, 6-min
highlights. The auto-opening/intro is DEFERRED (Codex R1 P1#5 — a fake event id breaks
reconciliation + reel lookup; model it later as reel-request metadata).

## Implementation status
- [x] A. Rename Verify → "Review"
- [x] B. Compact shared clip player
- [x] C. Caption + type editing in Review
- [ ] D. Review-first flow + demo state (deferred to pass 2)
- [x] E. Chronological Search browse
- [x] F. Six-minute Quick Highlights + stream-copy reel

## A. Rename Verify → "Review"
`App.tsx` tab label "Review"; update the component/headings. No behavior change.

## B. Compact clip player (shared)
Extend `ClipThumb` (bits.tsx) with a play-button overlay → click opens a **modal lightbox**
(`<video controls autoPlay>`, Esc/backdrop closes). Use in **Review rows** (replace the big inline
`<video>`) AND **Search rows**.

## C. Caption + type editing in Review — reuse Accept/Reject, made consistent
- **One endpoint, proposal-keyed**, that SHARES the existing materialization paths (Codex P1#3):
  - Edit to a **notable type** → the full **Accept** path with the edited `caption`/`type`
    (materialize/reuse event, promote-or-cut clip, embed, upsert, manifest, decision).
  - Edit to **`none`** → the full **Reject** path (remove event, delete point, persist decision).
    (`none` is NOT "implies acceptance" — it is the honest removal.)
- **Canonical embed text (Codex P1#2):** add `event_text(event) = f"{caption}. {type}"` and use it
  in `_upsert_event`, `_reconcile_baseline`, AND `rebuild_collection_from_manifest`, so live edits,
  reconcile, and batch rebuild produce IDENTICAL vectors (today `_upsert_event` embeds caption only
  while batch embeds caption+type — a latent live-Verify bug this also fixes). A type-only edit thus
  changes the vector.
- **Edit consistency (Codex P1#1):** an edit mutates an ALREADY-visible point, so:
  - `search_events` acquires the **per-match lock** (it currently doesn't), so it can't read a
    half-applied edit.
  - Under the lock, capture the OLD point; order writes so the manifest is the commit; on a failed
    write, **compensate** by restoring the old point; if compensation itself fails, set
    `reconciliation_error` so Search 503s (self-heals via `ensure_reconciled`). Fault-injection
    tests for upsert-fail and manifest-fail.
- **Review response reflects edits (Codex P1#4):** `_proposal_responses` must OVERLAY the accepted
  manifest event's `caption`/`type` (and `clip`) onto the row when a decision maps the proposal to a
  manifest event; keep the raw proposal fields only if needed for provenance. Otherwise Review shows
  stale AI text after a successful edit.
- **Frontend Review row:** an **Edit** control → inline caption textarea + type dropdown →
  Save / Cancel. On save, invalidate `proposals`, `timeline`, AND `search` queries (Codex P2#7).

## D. Review-first flow + demo state (Codex P2#6)
Code already supports pending→accept→search. Demo state lives in **deployable match-001** (NOT the
local-only match-002): leave **3–5 curated accepted events** (so cold Search isn't empty) plus **≥1
playable pending proposal** (so the watch-review-edit-accept flow demos). Coordinator data step.

## E. Search: chronological browse + build actions
- **Initialize the submitted query EMPTY (Codex P2#7)** so Search OPENS in browse mode: no query →
  list ALL verified `events` in `t_start` order (the `events` prop already holds them); show
  timecode, hide cosine score. A typed query → relevance hits (unchanged).
- Keep Add-to-reel, Build reel (selected), Quick Highlights.

## F. Quick Highlights ≈ 6 minutes (no intro this pass)
- `highlights.ts`: `MAX_SECONDS = 360`; drop the hard clip count (duration is the bound) or raise it;
  keep dedup + rank + chronological + celebration last. **No opening clip** (deferred).
- **Reel encode (Codex P2#8):** a 6-min reel must NOT full-`libx264`-re-encode (times out on
  free-tier CPU). Switch `_build_reel` to **stream-copy concat** of the already-normalized clips
  (all `cut_event` output is 1280×720 H.264/AAC); keep a re-encode fallback only if concat fails.

## Tests
- `pickHighlights`: 6-min budget honored; chronological; celebration last. (No opening.)
- Edit endpoint: notable edit re-materializes + re-embeds (canonical text) + rewrites manifest +
  searchable reflects new caption AND type-only change; `type=none` removes from Search; editing a
  pending proposal accepts it; under lock; **fault-injection**: upsert-fail and manifest-fail leave
  Search consistent (old value) or 503, never a split state.
- `_proposal_responses` overlays accepted manifest caption/type/clip.
- Reel: stream-copy concat produces a playable file; 6-min build path.
- Frontend: modal player opens/closes; Review edit saves + invalidates; Search opens in browse
  (chronological) with no query; query mode still relevance.

## Acceptance
Local: Review renamed; compact thumbnails + modal player; edit a mislabeled "goal" → it re-indexes
(or `none` removes it) and Search reflects it; Search opens chronological; a ~6-min highlights reel
builds via stream-copy. ruff + pytest + npm test + web build/oxlint green.

## Scope / deadline
It's Jul 16; deadline Jul 17 ~10:00 PDT; the required **deploy is still unbuilt**. If the edit
consistency work (C) threatens the schedule, ship A/B/E/F first (visible polish, low risk) and land
C next — reviewer, confirm that split is safe. The opening/intro is explicitly deferred.
