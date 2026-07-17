# Plan: submission finish

## Goal and deadline

Ship a judge-ready Every Angle submission before **2026-07-17 10:00 AM PDT**. The user
authorized the complete finish sequence on 2026-07-16: polish, documentation, release,
deployment, demo-video package, and submission support. Freeze product scope; do not add another
feature.

The demo must communicate one grounded story in under two minutes:

`full match → AI proposals → human review → verified match intelligence → semantic search → reel`

## 1. Demo-readiness visual polish

- [x] Preserve the existing edit-suite identity: night-pitch ink, chalk for human truth, sodium for
  machine proposals, condensed display type, square controls, and visible provenance.
- [x] Make the first viewport explain the product without narration: a concise outcome-led hero,
  the four-step workflow, verified match summary, and an obvious route into Review/Search/Reel.
- [x] Strengthen hierarchy and spacing without adding decorative stock imagery or dashboard clutter.
  Use CSS atmosphere, type, rules, and the existing pitch motif.
- [x] Make match summary rows scan like incident cards and keep every value derived from the verified
  timeline. Continue to avoid an official team score when canonical teams/scorers are unknown.
- [x] Improve timeline presentation without changing its data or interaction contract: clearer zoom
  wording, a scroll affordance, calmer legend, visible scrollbar, and preserved playable event
  targets/provenance lanes.
- [x] Make Search results, Review proposal cards, tabs, buttons, and Reel controls work cleanly at
  narrow widths. No nested controls, hidden actions, or horizontal page overflow.
- [x] Preserve all current behavior: every timeline clip remains playable, Review clips and editing
  remain available, Search has no canned suggestions, Quick Highlights stays, and reel assembly
  remains deterministic.

## 2. Public-facing submission copy

- [x] Rewrite the stale README around the current React/Vite + FastAPI application. Explain the
  differentiator, grounded AI workflow, measured results, current stack, deploy/run path, demo
  data/license boundary, and reproducible checks. Remove retired Streamlit instructions.
- [x] Add `docs/project-description.md`: a portal-ready description mapped naturally to innovation,
  technical implementation, AI usage, usability, impact, and execution without listing rubric
  buzzwords mechanically.
- [x] Add `docs/demo-video.md` containing:
  - a 90–120 second shot list with exact clicks/query and fallback shots;
  - narration written for a neutral synthetic documentary voice;
  - recording/export settings and a final attribution card;
  - a concise upload/submission checklist.
- [x] Keep claims evidence-backed. Do not imply current public match data knows team identities,
  supports live broadcast ingest, or contains copyrighted broadcast footage.

## 3. Share preview and metadata

- [x] Update `web/index.html` with aligned title, description, Open Graph, and Twitter summary-card
  text metadata.
- [ ] Add `og:image`/`twitter:image` only after the public deployment and `/og.png` are verified,
  so link unfurlers receive an absolute URL instead of a guessed host.
- [x] Social card decision: omitted under the safe fallback because the host provides no browser
  preview and there is not yet a verified public URL. Do not ship an unverified image reference.
  The intended card would have used the
  existing night-pitch/chalk/sodium visual language. Include only short, validated text. Save it
  as `web/public/og.png`, build it into `web/dist`, and verify the deployed `/og.png` before adding
  the absolute image metadata. If the generated card cannot be saved and verified cleanly in this
  Vite/FastAPI repository, omit it and its metadata rather than shipping a broken reference.

## 4. Verification and release

- [x] Update focused frontend tests for new public copy and responsive/interaction invariants where
  source-level assertions add value; do not make tests depend on exact decorative classes.
- [x] Run Ruff check/format, full pytest, frontend tests, Vite production build, Oxlint, and
  `git diff --check`.
- [x] Run the independent Codex code-review loop and preserve its final verdict under this task.
- [x] The embedded browser is unavailable. Record the limitation and require a short manual
  desktop/narrow-width dry run before recording; do not replace it with unsupported automation.
- Commit only intended repository work, explicitly exclude unrelated
  `docs/shareable-agent-workflow.md`, push `main`, and verify the GitHub head.
- Preserve the reviewed Docker + Render + Qdrant Cloud deployment topology. Do not migrate this
  FastAPI/Qdrant/FFmpeg app to static hosting during the submission crunch.
- Deploy or trigger the existing Render path if credentials/account access are available; otherwise
  give the user the smallest exact account-only action and continue preparing the recording package.

## Acceptance criteria

- A judge can understand the product and grounded-AI distinction from the first viewport.
- Review → Search → Reel remains a coherent, playable golden path on the bundled CC-BY match.
- README and submission materials match the actual 2026 codebase and contain no stale Streamlit
  language or unsupported claims.
- A complete voiceover script, shot list, recording recipe, credits, and submission checklist exist.
- Full automated gate is green and independent code review is APPROVED.
- Intended work is committed/pushed, and either a live URL is verified or the sole account-side
  deployment blocker is handed to the user precisely.

## Non-goals

- No new AI provider, paid dependency, match reprocessing, official sports-feed integration,
  canonical scoreline work, uploader redesign, or new sponsor integration.
- No broadcast footage in Git, the deploy image, screenshots, or demo video.
- No visual overhaul that obscures provenance or risks the working golden path.
