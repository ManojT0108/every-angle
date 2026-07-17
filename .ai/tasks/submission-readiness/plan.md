# Plan: submission readiness for "Every Angle" (deadline Jul 17 10:00 AM PDT)

## State (2026-07-15, ~2 days to deadline)

- Full pipeline shipped + Codex-reviewed: ingest → sample → propose (Claude vision) → publish
  (staged Qdrant + promote) → search → reel. Two footage regimes (amateur fixed-camera / broadcast).
  Web app (React+Vite) + FastAPI (`api/main.py`). All committed, branch pushed.
- **match-001** (SoccerTrack, CC BY 4.0) published rev 1 → `moments_rev_1`, 5 events. SHIPPABLE.
- **match-002** (real broadcast) is LOCAL ONLY (copyright) — works locally, but excluded from any
  public artifact. Not part of the deployed demo. (User decision 2026-07-15: don't productize a
  shippable-broadcast path; it's a hackathon.)

## Requirements vs status (docs/submission-checklist.md)

| Artifact | Status |
|---|---|
| Project name / track / GitHub repo | ✅ done (public repo pushed) |
| **Working Demo URL (deployed app)** | ❌ **REQUIRED, NOT STARTED — top gap** |
| Project description | ❌ draft not written |
| Demo video (optional) | ❌ recommended as live-demo fallback |
| Registration + Submit (portal) | ❌ USER-only; registration deadline ~tonight |

## Priorities (ranked for the deadline)

**P0 — Deploy the demo (required; nothing else counts without it).** Approach, hardened with the
Codex review's four demo-day landmines:
- One container: FastAPI serves the built `web/dist` + match-001 clips + evidence frames; `ffmpeg`
  installed. Add a `Dockerfile` + pinned deps. **Ship ONLY match-001 (CC BY);** broadcast never
  enters the image.
- **(Codex P1a) `data/` is gitignored → a git build deploys EMPTY and `/api/matches` returns [].**
  Copy a minimal CC-BY deploy bundle into the image: `CURRENT_REV`, `windows.json`,
  `staging/rev-1/manifest.json`, **`proposals.json`, `decisions.json`** (else Verify is empty), the
  accepted-event clips, the **proposal-`{sha16}` clips** for any pending/notable proposals, the
  evidence frames, and **at least one PENDING proposal** so the live-accept + watch-and-verify demo
  works (see `.ai/tasks/verify-clips/`).
- **(Codex P1b) FastEmbed model + startup swallows load errors → URL looks healthy but every search
  503s.** Bake AND prewarm the embedding model at image BUILD time, not first request.
- **(Codex P1b) Qdrant seeding:** seed Qdrant Cloud collection ONCE, out-of-band (not the destructive
  `rebuild_collection_from_manifest` at web startup — that deletes the live collection on every
  restart). App reads `QDRANT_URL`/`QDRANT_API_KEY` from env.
- **(Codex P2) Reel re-encode (`libx264 medium`) can time out on throttled free-tier CPU.** Use
  stream-copy concat of the already-normalized clips, or prebuild the scripted fallback reel.
- **Verify is now LIVE, not hidden (superseded).** The read-only/hide direction is obsolete: the
  live-Verify feature (`.ai/tasks/live-verify/`, APPROVED) makes Accept/Reject write through to the
  live index, and verify-clips makes each moment watchable — so a judge accepting a moment DOES see
  it in Search. Ship Verify fully functional; the ephemeral container resets to the verified
  baseline on restart (documented session-reset semantics).
- Host on a free tier (Railway/Render/Fly) → public HTTPS URL. No secrets in the image; CORS correct.
- **Acceptance = readiness gated on real behavior after a COLD restart:** a golden search returns
  results (proves embed model + Qdrant), a clip plays, a reel builds, AND Verify lists rows with a
  playable clip — not just an HTTP 200.

**P1 — Project description + README for judges.** Problem → pipeline → measured results
("45 min → 11 min under review, 2/2 goal recall") → two-buyer story. Map to the 7 criteria.

**P2 — Demo video (2–3 min).** Screen-record the golden path on the deployed URL. This is the
reliability fallback if the live demo breaks during judging.

**P3 — Reliability pass on the deployed golden path.** Verify → Search → Reel must be
self-explanatory; seed 3–5 "golden queries" for onboarding; handle empty/error states.

## Explicitly NOT doing (scope guard)
- Virtual-broadcast-camera / shippable-broadcast productization (user decision — not for a
  hackathon).
- InsForge track (sponsor prize unconfirmed).
- Re-indexing match-001 with the new celebration taxonomy (its footage has no ceremony).

## User actions (blocking — surface immediately, not my tasks)
- **Register on the portal NOW** — deadline "Jul 15 9:30 PM"; timezone unconfirmed (possibly IST,
  which would be ~9 AM PDT today = already passed). Confirm the timezone and register.
- Submissions open Jul 16 10:00 AM IST; submit by our 8:30 AM PDT Jul 17 target.
- Approve any hosting account / spend if the free tier is insufficient.

## Schedule
- Jul 15 PM: P0 deploy (get a live URL today — it's the long pole).
- Jul 16: P1 description, P2 video, dry run once submissions open.
- Jul 17 by 08:30 PDT: submit.

## Questions for the reviewer
Is deploy correctly the P0, and is the single-container + Qdrant-Cloud approach the lowest-risk
path to a live URL in the time left? What's the highest-risk part of the deploy for demo-day
reliability (clips serving? reel ffmpeg? Qdrant seeding?), and what would you cut or simplify to
de-risk hitting the deadline?
