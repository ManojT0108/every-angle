# Plan: match summary + explorable timeline + honest search

## Goal

Make the homepage useful for a person exploring a processed match:

1. Replace the operational stat tiles with a Google-style match summary derived from the
   **verified manifest**: grouped verified goal moments, goal times, and scorer/scoring team
   when the processing pipeline could read them and a human confirmed them. If identity is
   unknown, say `Goal · MM:SS`; never infer a player/team from prose or hardcode demo facts.
2. Replace the compressed percentage timeline with a horizontally scrollable, zoomable timeline
   whose verified moments have large, non-overlapping hit targets. Every event with a clip—not
   only goals—must remain playable. Candidate windows and rejected provenance remain visible.
3. Remove the canned search-query chips. Keep Quick Highlights and keep all Review clip playback.

## 1. Structured goal metadata from processing

- Extend `pipeline.captioner.CaptionResult` and the Claude structured-output schema with nullable
  `team` and `player` fields whose semantics are specifically **scoring team** and **scorer**.
- The prompts may populate them only when the sampled sequence directly attributes that team or
  player to the goal (for example an explicit scorer graphic or an unambiguous scoring sequence).
  A visible player, shirt, lower-third, or goalkeeper is not enough. Fixed-camera footage will
  normally return `null`. No caption regex or UI guessing.
- Bump the prompt version because this changes the persisted proposal contract.
- Persist `team`/`player` into `proposals.json`. Show both optional fields in Review and include
  them in the existing inline edit form so a human can confirm, correct, or clear them before/after
  acceptance. Live Accept materialization copies the reviewed fields into the verified event.
  Existing artifacts without the fields remain valid and produce the honest fallback.
- Do not call Claude or reprocess footage in this task. The current deploy bundle remains
  truthful: its two verified goal events have unknown team/player metadata.

## 2. Derived match summary

- Add a small pure frontend summary helper/component over `Timeline.events` and `duration`.
- First cluster overlapping/near-adjacent verified goal moments with the same rolling-end incident
  grouping already used by Quick Highlights. This prevents replay windows for one incident from
  producing repeated rows. Use the earliest moment time; use scorer/team metadata only when the
  incident has one unambiguous non-null value for that field, otherwise suppress it.
- Sort the resulting display incidents chronologically and render one row per incident:
  `Player · Team · MM:SS` when available; otherwise `Team goal · MM:SS`; otherwise
  `Goal · MM:SS`.
- Show `N displayed goal groups` plus footage duration, with a short note that replay-adjacent goal
  moments are grouped for display. Do **not** call the heuristic count a verified score or claim an
  official team-v-team scoreline:
  the current artifact contract has neither human-verified incident IDs nor canonical team IDs,
  so grouping raw labels such as `RMA` and `Real Madrid` would be unsafe. A real scoreline remains
  future work once that match-level metadata exists.
- Replace the four pipeline-stat tiles at the top. Remove the homepage-only proposals query; the
  Review tab continues loading proposals/clips independently.

## 3. Zoomable, scrollable timeline

- Add zoom controls with bounded pixels-per-minute levels and a useful zoomed default.
- Render an overflow-x viewport and a time-scaled inner canvas. Use pixel positions rather than
  percentages so zoom genuinely creates space.
- Lay verified moments across multiple lanes using deterministic greedy interval placement based
  on their visual hitbox, preventing clustered events from covering one another.
- Give every playable event a minimum 24px click target; clicking opens the existing shared modal.
  Clipless events remain inert. Goal and non-goal events use the same interaction contract.
- Render rejected moments and candidate windows on separate lanes, with time-proportional widths;
  adapt tick spacing to zoom. Preserve keyboard access and avoid nested buttons.

## 4. Search cleanup

- Delete the hardcoded `GOLDEN` prompts and their buttons.
- Keep the search field, chronological empty-query browse mode, and Quick Highlights action.

## Tests and gate

- Python: caption schema/prompt-version contract; proposal persistence; Accept preserves structured
  team/player; Review edit can correct/clear both; legacy missing metadata still validates.
- Frontend: summary fallback and confirmed team/scorer detail; replay-adjacent goal moments collapse
  to one display incident; all goal times chronological; no official scoreline or old stat tiles;
  zoom controls/canvas width; clustered playable events occupy distinct lanes and all
  remain buttons; clipless remains inert; canned search strings absent and Quick Highlights kept.
- Run Ruff check/format, full pytest, `npm test`, web build, Oxlint, and `git diff --check`.
- Perform browser QA at desktop and a narrow viewport: scroll/zoom, click a non-goal event, inspect
  summary fallback, confirm Search has no canned suggestions, and confirm Review clips remain.

## Non-goals

- No official match-feed integration, OCR-specific model, canonical team registry, persisted
  incident IDs, caption regex, reprocessing, or manual edits to demo event identities.
- No aesthetic redesign beyond layout required for the requested usability changes.
- No changes to Review clip generation/playback, Quick Highlights selection, or deployment data.
