# Plan: live Verify — accept a proposal → instantly searchable (R2, Codex-hardened)

## Goal (user)

In Verify, a human reviews AI proposals (caption + evidence) and on **Accept** the moment is
**immediately searchable and reel-able** — no separate publish step. Reject/undo removes it. This
is the human-in-the-loop working live. User accepts that the deployed demo has NO source video.

## Why it doesn't work today

Search reads a frozen published snapshot (`moments_rev_N`, clips from `staging/rev-N/`). Verify
only writes a draft (`decisions.json`; `add_human_event` appends to a manifest and cuts no clip).
Only the heavy destructive `publish_revision` indexes. So Accept never reaches search.

## Design (addresses Codex R1 P1×4 + P2×3)

### Single canonical manifest = source of truth AND visibility commit (R1 P1#1, P1#4)
- The **promoted** `staging/rev-{CURRENT_REV}/manifest.json` is the ONE canonical mutable manifest.
  Live Accept/reject mutate it; a future `publish_revision` must consume THIS manifest (not a stale
  root copy) so batch publish can't drop accepted / resurrect rejected events.
- **Search is filtered against the manifest AT QUERY TIME (R2 P2):** `search_events` passes a
  Qdrant payload filter restricting hits to `payload.id ∈ {event ids in the current manifest}`, so
  `limit` applies to VALID results (post-filtering after `limit` could return too few / zero when
  orphan points occupy the top-K). An orphaned Qdrant point (upsert succeeded, manifest write
  didn't) is thus never returned — the manifest write is the atomic commit point.
- `accepted` status in Verify is derived from the manifest, not a separate decisions file.

### Pre-cut clips — no runtime source video (R1 P1#3)
- The deployed bundle ships **pre-cut clips for every acceptable proposal** in match-001 (CC-BY)
  at the **root** clips path `data/{video_id}/clips/`. Accept does NOT run `cut_event` at request
  time — the clip already exists at the served path. Removes the source-video dependency.
- **Ephemeral filesystem — session-reset semantics (R2 P1#3):** the hosted container's filesystem
  is ephemeral, so live manifest edits are lost on restart (rare mid-judging). We ACCEPT this: the
  demo always restores the pre-verified baseline. On startup, **two-way reconcile Qdrant to the
  baseline manifest (R3 P1):** UPSERT a point for every baseline event AND DELETE any point not in
  the baseline. One-way (delete-only) is wrong — if a session rejected a BASELINE event its point
  was deleted, and after restart the manifest restores that event, so its point must be re-added or
  Timeline/Reel would show an event Search can't find. Two-way sync makes Qdrant exactly match the
  reset baseline. (No durable storage this deadline; documented, tested cold both directions.)
- **Add-Moment** (arbitrary new timestamp) needs the source video, so it is **local-only** (hidden
  in the hosted demo via an API capability flag). When shown, it uses the SAME write-through commit
  path as Accept (R2 new-P1) — cut the clip at runtime (source present locally), upsert, append to
  the canonical manifest under the lock — so a locally-added moment reaches Search/Timeline/Reel.
  It never writes the old root-manifest-only path.

### Clip serving (R1 P1#2, corrected)
- `/media` is `GuardedStaticFiles(directory=DATA_ROOT)`; the frontend `mediaUrl(id, "clips/x.mp4")`
  resolves to `/media/{id}/clips/x.mp4` = `data/{id}/clips/x.mp4` (match ROOT — NOT `staging/`).
  So accepted/pre-cut clips must live at the root clips path (they do, per above). Reel assembly's
  `_safe_published_clip` reads the same clips; confirm it resolves the root path (adjust if it
  still points at `staging/rev-N/`). A test does a real HTTP GET of an accepted clip via `/media`.

### Accept / reject endpoints (idempotent, locked)
- `POST /api/matches/{id}/proposals/{pid}/accept`, under a **per-match lock** (R1 P2#7):
  1. Build the event (stable `event_id` from `pid`; idempotent).
  2. Embed caption (`_query_vector`) and **synchronously** `upsert` one point
     (`_point_id(video_id, event_id)`, payload = event) into `collection_name(CURRENT_REV)`.
  3. Append the event to the canonical manifest atomically (temp+replace). **This is the commit.**
  4. Record the decision.
  The pre-cut clip must already exist at the served path; assert it (R1 P1#2).
- `POST …/{pid}/reject` (also for undo of an accepted one): remove the event from the manifest
  first (instantly invisible via the search filter), then delete the point; record the decision.
- Require a **pre-seeded published revision** (match-001 has rev 1). A never-published match has no
  collection → Accept returns a clear error rather than silently failing (R1 P2#5). (Bootstrapping
  rev 1 on first Accept is out of scope for the deadline.)

## Frontend (`Verify.tsx`)
- `decide` for `"accepted"` → the accept endpoint; `"rejected"` → the reject endpoint. On success
  invalidate `["search",…]`, `["timeline",…]`, `["proposals",…]` so search reflects it instantly.
- **Undo/Reject on settled ACCEPTED proposals (R1 P2#6):** the "Judged" list gets a reject/undo
  control for accepted items (today it is display-only).
- `AddMoment`: shown only when the API reports a source video is available (local); hidden in the
  hosted demo.

## Tests
- Accept upserts a searchable point AND writes the manifest event; the served clip path exists;
  search returns it; timeline/reel see it.
- Reject/undo removes the event (search no longer returns it) and deletes the point.
- Idempotent re-accept: no duplicate event/point.
- **Commit-point / orphan:** a point whose event is absent from the manifest is filtered out of
  search (simulate upsert-then-manifest-failure).
- Concurrency: two interleaved manifest writes under the lock don't lose an update.
- Accept on a match with no published revision returns a clear error.
- Query-time filter: with orphan points ranked above valid ones, search still returns the full
  requested count of valid (in-manifest) hits.
- Cold-restart reconciliation (both directions): a live point whose event is absent from the
  baseline is deleted on startup; AND a baseline event whose point was deleted during the session
  (reject/undo of a baseline event) is re-upserted on startup → searchable again.
- Local Add-Moment write-through: an added moment appears in Search/Timeline (source-present env).

## Acceptance
- Local: Verify → Accept a pending proposal → Search returns it, clip plays; Undo removes it.
  ruff + pytest green; web build + lint clean.

## Priority note (coordinator)
Backbone feature; must land before deploy (the deploy bundle depends on pre-cut clips + the
manifest-as-truth model). Keep tight.
