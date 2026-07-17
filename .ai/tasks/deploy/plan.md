# Plan: deploy the demo to a public URL (R2, Codex-hardened)

Required artifact. Ship ONLY match-001 (CC BY 4.0). Broadcast/source videos never enter the image.

## Bundle — TRACKED, allowlisted, outside data/ (Codex P1#1)
- `data/` is gitignored and Render builds from Git, so create a **tracked** `deploy/bundle/match-001/`
  with ONLY the CC-BY artifacts, at these EXACT paths (Codex R2 P2):
  - `CURRENT_REV`, `windows.json`, `staging/rev-1/manifest.json`, `proposals.json`, `decisions.json`
  - `clips/e-*.mp4` (the 5 event clips — root path, served by `/media` for playback + reel) AND
    `staging/rev-1/clips/e-*.mp4` (reel-assembly copies) AND `clips/proposal-{sha}.mp4` for the
    pending fixture
  - `frames/<run>/<window>/*.jpg` evidence frames referenced by the shown proposals
- **`.dockerignore` deny-by-default** — ignore `*`; un-ignore the frontend **BUILD INPUTS** the node
  stage needs (`web/package.json`, `web/package-lock.json`, `web/src`, `web/public`, `web/index.html`,
  `web/tsconfig*.json`, `web/vite.config.*`, `web/*.config.*`) while still excluding `web/node_modules`
  and `web/dist` (built in-container); plus `deploy/bundle`, `api`, `pipeline`, `requirements.txt`,
  `scripts/seed_qdrant.py`. (Codex R2 P1: `web/dist` is gitignored, so the image must BUILD it.)
- Assert at build time the image contains **no source `*.mp4` under a `source/` dir and no
  `match-002`** (fail the build otherwise).

## Container (Codex P2#3, P2#6)
- Multi-stage `Dockerfile`: node stage builds `web/dist`; python 3.11-slim runtime + `ffmpeg`.
- Set a persistent **`FASTEMBED_CACHE_PATH=/opt/fastembed`** in the RUNTIME image, prewarm the model
  INTO that path at build, and verify a golden embedding with **`local_files_only=True`** (no network)
  so a cold container never fetches lazily / 503s.
- **Immutable baseline + reset-on-start (Codex R3 P2):** bake the bundle at an IMMUTABLE path
  (`/app/baseline/match-001`); the entrypoint **copies it into `$DATA_ROOT` on every startup**,
  overwriting any prior-session mutations. So even a plain restart (not just a fresh container)
  returns to the 5-accepted + 1-pending baseline; `_reconcile_baseline` then syncs Qdrant to it.
- **Docker-native entrypoint**: restore baseline (above), then
  `exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-10000}` (Render injects `$PORT`). NOT
  `scripts/run_app.sh` (it assumes `.venv`/local Docker/curl/node). Render health-check `/api/matches`.

## Qdrant Cloud seed — non-destructive (Codex P2#4)
- `scripts/seed_qdrant.py`: **create-if-missing then upsert-and-verify** match-001's 5 events (canonical
  `event_text`); do NOT delete/recreate a live collection. A destructive rebuild requires explicit
  `--force`; refuse rerun against a populated collection without it. App reads `QDRANT_URL`/`QDRANT_API_KEY`
  from env; startup `_reconcile_baseline` keeps it synced.

## Demo state (Codex P2#5, R2)
- Keep the 5 accepted events (cold Search non-empty). Make **one NAMED proposal PENDING** — the exact
  id, its clip path, and evidence frames are chosen during the coordinator curation step and RECORDED
  in `deploy/bundle/NOTES.md` (kept + rejected ids) before the build; the gate references that name, not
  a "later" TODO. The pending proposal must have `clips/proposal-{sha}.mp4` present.
- **Reset between judging sessions = a restart or Render redeploy** — the entrypoint's baseline-restore
  (above) makes ANY restart return to 5-accepted + 1-pending, so the shared pending proposal a visitor
  may have consumed is restored. (No reliance on writable-layer wiping.)

## Readiness gate — exercise the real flow after a COLD restart (Codex P2#5)
`/api/matches` lists match-001; golden Search returns hits; a clip serves (200 video/mp4); Review lists rows
incl. the named pending one; **pending → edit/accept → the moment appears in Search**; **Build 6-min
highlights succeeds**; then **cold restart → 5 baseline Qdrant points present AND the named proposal pending
again** (reconciliation). No secrets in the image.

## Sequence — what I do vs what the USER must do (Codex P1#2, R2 P2)
1. **Me (now):** the coordinator curation step (record kept/rejected ids + the named pending fixture in
   `deploy/bundle/NOTES.md`); build `deploy/bundle/match-001/`, `.dockerignore`, `Dockerfile`, entrypoint,
   `scripts/seed_qdrant.py`, `render.yaml`. A **provisional** `docker build`/`run` smoke against the
   local Qdrant (labelled provisional — the tracked bundle isn't committed yet). Qdrant Cloud creds are
   in the gitignored `.env.deploy`; Cloud reachable (verified).
2. **USER (required — I cannot):** **approve commit/push** of the deploy files + bundle; create **Render**;
   in Render **import the Blueprint / create the Docker service, connect the repo, enter `QDRANT_URL` +
   `QDRANT_API_KEY`** as secrets.
3. **Me (after approval + commit):** the **authoritative clean-checkout `docker build`** (now the committed
   bundle is present); seed Qdrant Cloud (`seed_qdrant.py`, create-if-missing/upsert-verify); trigger the
   Render deploy; run the readiness checklist on the live URL; hand back the public link.
