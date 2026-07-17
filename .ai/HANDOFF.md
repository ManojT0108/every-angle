# Current handoff — Claude resumes as orchestrator

Updated **2026-07-16 PM PDT**. This file is the authoritative current state; older task plans and
reviews are historical evidence, not active instructions.

## Immediate objective

Finish the hackathon presentation package and submit before **2026-07-17 10:00 AM PDT**.
The product, repository, cloud index, and live deployment are complete. The only substantial
unfinished artifact is the final demo video.

## Shipped product

- **Live app:** https://every-angle.onrender.com
- **Public repository:** https://github.com/ManojT0108/every-angle
- **Release commits:** `f296cd1` ships the processed broadcast match; `0a4ef92` records the
  completed live deployment.
- Render is configured with `autoDeployTrigger: commit`. The large broadcast release took about
  12 minutes to replace the previous container; do not mistake the old container remaining healthy
  during a rolling build for a failed deploy.
- The live match selector exposes:
  - `match-001`: SoccerTrack v2, CC BY 4.0, revision 1, 5 verified events.
  - `match-002`: authorized user-provided broadcast feed, revision 3, 30 published events.
- The broadcast deploy bundle contains 35 processed clips and 66 Review posters. The 2.9 GB source
  video, extra sampled frames, old staging revisions, and generated local reels are excluded.
- The user explicitly confirmed permission to publicly redistribute `match-002`. The authorization
  and shipped derivative boundary are recorded in `docs/assets-manifest.md`.

## Verified production state

- Qdrant Cloud: `moments_rev_1` = 5 points; `moments_rev_3` = 30 points.
- Live `/api/matches` lists both matches with the expected revisions/event counts.
- Live broadcast query **`trophy lift`** returns the trophy ceremony first.
- A 21 MB broadcast clip, all Review posters, and a generated 60-second two-event reel served 200.
- The frontend bundle contains the **Broadcast feed** selector.
- Source-video capability is false in the deployed container; manual Add Moment remains unavailable
  without a source upload, by design.

## Last quality gate

- Ruff and changed-file formatting: clean.
- Python: **78 passed**.
- Frontend: **18 passed**; Vite production build and Oxlint clean.
- `git diff --check`: clean.
- Production Docker build: passed.
- Production-container smoke against Qdrant Cloud: passed.
- Independent workflow-v2 plan and code reviews: **APPROVED**, durable records in
  `.ai/tasks/live-broadcast-match/reviews/`.
- Embedded browser control was unavailable, so a human visual pass/recording in the real browser is
  still required. API, media, search, and reel behavior were verified directly.

## Demo video — important: not upload-ready

There is **no final screen recording and no uploadable MP4** yet.

Existing materials were prepared before the broadcast match shipped and are now a **single-match
draft**, not the final story:

- `docs/demo-video.md`
- `docs/demo-narration.txt`
- `docs/demo-captions.srt`
- local synthetic narration:
  `/Users/manojt/Documents/Hackathon/every-angle-demo-assets/every-angle-narration.m4a`
  (Reed voice, AAC 48 kHz mono, about 106.5 seconds, normalized near -16 LUFS)

Do not upload that package unchanged. It says to show only `match-001` and explicitly excludes
broadcast footage, which is now obsolete.

### Recommended next task for Claude

Create a small workflow-v2 task such as `.ai/tasks/demo-video-v2/`, then:

1. Rewrite the 105–115 second shot list and narration around the live two-input story:
   hero and four-step workflow → show both source selectors → switch to **Broadcast feed** →
   search **`trophy lift`** and play the first clip → show provenance/Review → Quick Highlights →
   build/play a short reel → final credits.
2. Keep the human-verification distinction explicit. Do not claim live ingest, an official feed,
   or team/scorer certainty beyond what the reviewed artifacts show.
3. Update `docs/demo-narration.txt` and regenerate the synthetic M4A; update the SRT to the new
   audio timings.
4. The agent cannot capture the user's Mac screen with the current browser integration. The user
   must make one silent 1080p screen recording of the live walkthrough and provide its local path.
5. Once that recording exists, combine it with narration and captions using FFmpeg, verify duration,
   audio, captions, and link visibility, then hand back the final MP4 for upload.
6. Final attribution should credit SoccerTrack v2 (CC BY 4.0) and label the second source
   **Broadcast feed · user-provided** without inventing a public license.

## Submission state

Ready:

- Project name: **Every Angle**
- Track: **Media, Content & Broadcasting**
- GitHub repository: https://github.com/ManojT0108/every-angle
- Working demo: https://every-angle.onrender.com
- Project description: `docs/project-description.md`

Not ready / user action:

- Final demo MP4: not recorded.
- Upload the final video and verify it signed out.
- Log into the hackathon portal, paste the repository, live URL, project description, and video URL,
  then submit. Account login and final submission are user-only actions.

## Operational notes

- Render free instances may cold-start; wake the app and exercise Search/Reel before recording.
- A live Review decision mutates only the current container. A redeploy/restart restores both baked
  baselines. The match-001 pending-review fixture is
  `r-20260714T182221Z-v2-p-039` at about 43:11.
- Secrets remain in the gitignored `.env.deploy`; never print or commit them.
- Qdrant collection names are still revision-global rather than match-scoped. Current revisions 1
  and 3 avoid collision; do not republish either match onto the other's revision.
- Worktree should be clean when Claude resumes. Read `AGENTS.md`, this file, and
  `.ai/tasks/live-broadcast-match/plan.md` before starting the video task.

## Collaboration role

Claude is the orchestrator again. Continue the user-approved workflow v2 in `AGENTS.md`: Claude
writes/triages the plan, invokes the separate Codex implement/review threads, performs the
coordinator self-review and release, and keeps this handoff current.
