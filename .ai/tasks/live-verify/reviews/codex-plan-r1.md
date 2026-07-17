- **P1 — lines 26–35, 51–54, 69–70:** If Qdrant upsert succeeds but the manifest or decision write fails, Search exposes the event while Timeline/Reel or Verify disagree; atomic file replacement does not make these writes atomic. **Recommended fix:** Make the promoted manifest the visibility commit—filter Search against it, use synchronous Qdrant writes, derive accepted status from the manifest, compensate/reconcile failures, and test every write boundary for accept and reject.

- **P1 — lines 26–31, 40–42:** Clips are written under `staging/rev-N/clips/`, but the web player resolves `clips/x.mp4` as `/media/{video_id}/clips/x.mp4`; the new search hit will return while its preview 404s. **Recommended fix:** Add a revision-aware media endpoint/URL and test an actual HTTP clip fetch after Accept.

- **P1 — lines 26–31, 37–42, 72–78:** The deployed bundle contains no source video, so request-time `cut_event` cannot support Accept or Add Moment; ephemeral container writes could also disappear after restart while Qdrant retains the point. **Recommended fix:** Package pre-cut clips for demo proposals, scope arbitrary Add Moment to source-equipped environments, and define either durable storage with startup reconciliation or a session-scoped overlay reset on boot.

- **P1 — lines 30–38, 46–48:** Live changes update only the promoted manifest, while `publish_revision` still rebuilds from root `manifest.json`; the next batch publish drops accepted events and can resurrect rejected ones. **Recommended fix:** Declare one canonical mutable manifest and make both live edits and future publishing consume it.

- **P2 — lines 23–31, 40–42:** A fresh proposed match has no `CURRENT_REV`, promoted directory, or collection, so its first Accept cannot work without the supposedly removed publish step. **Recommended fix:** Either bootstrap revision 1 on first Accept or explicitly require and enforce a pre-seeded published revision.

- **P2 — lines 34–35, 59–62, 73–74:** After Keep, the proposal moves to the settled list, which has no unaccept/reject control, so the acceptance requirement “Reject removes it” is not exercisable in the UI. **Recommended fix:** Add an Undo/Reject action for accepted settled proposals.

- **P2 — line 54:** Atomic replacement does not prevent lost updates when Accept and Add Moment concurrently read-modify-write the same manifest, which the threaded API can do even with one browser. **Recommended fix:** Add a per-match lock around manifest/decision read-modify-write commits.

REQUEST_CHANGES