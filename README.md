# Every Angle

**Turn full-match football footage into moments people can trust, search, and edit.**

Every Angle is a human-in-the-loop moment intelligence system for football. It narrows a match
to candidate windows, uses Claude vision to propose what happened, gives an editor the final
decision, and publishes only verified moments to semantic search and deterministic highlight
reels.

Sports World Cup Hackathon 2026 · Track 3: Media, Content & Broadcasting

## Why it is different

Most automated highlight tools hide the boundary between a model guess and a confirmed event.
Every Angle makes that boundary the product:

```text
full match → signal detection → AI proposals → human review → verified manifest
                                                                  │
                                                   semantic search ├─ highlight reel
                                                                  └─ provenance timeline
```

The verified manifest is the only downstream source of truth. Qdrant indexes its captions, the
timeline shows what was proposed, kept, added, or rejected, and FFmpeg cuts reels from its clips.
Raw model output never silently becomes a result. If the footage does not establish a team,
scorer, or scoreline, the interface leaves it unknown.

## Measured result

The fixed-camera detector was evaluated on one 45:05 half from SoccerTrack v2 against the
dataset's event annotations:

| Measure | Result |
|---|---:|
| Annotated goals surfaced for review | **2 / 2 (100%)** |
| Footage queued for review | **11.2 min of 45:05** |
| Detector runtime | **54 s on a laptop CPU** |

The annotations are evaluation data only. They are never an input to detection, captioning,
review, search, or reel assembly.

## Product flow

1. **Detect:** motion density, audio peaks, and scene changes identify candidate windows.
2. **Propose:** Claude vision labels and captions sampled frames, with a hard per-run spend cap.
3. **Review:** an editor plays the evidence, then keeps, rejects, or corrects the proposal. A
   missed moment can be added when the source video is available.
4. **Publish:** accepted events form a revisioned manifest and Qdrant collection. Search and reel
   assembly read that promoted revision only.

The React application exposes the complete judge path in one place: match summary and provenance
timeline, Review, verified-only Search, Quick Highlights, and an ordered Reel workspace.

## Stack

| Layer | Implementation |
|---|---|
| Web | React 19, TypeScript, Vite 8, Tailwind CSS 4 |
| API | FastAPI, Pydantic, Uvicorn |
| Video pipeline | Python, FFmpeg, Pillow |
| AI understanding | Anthropic Claude vision |
| Search | Qdrant + local FastEmbed embeddings |
| Release | Multi-stage Docker image, Render Blueprint, Qdrant Cloud |

## Run the bundled demo locally

Prerequisites: Python 3.11, Node 20, Docker, and FFmpeg.

```bash
docker compose up -d
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
(cd web && npm ci)

mkdir -p data/match-001
cp -R deploy/bundle/match-001/. data/match-001/
QDRANT_URL=http://localhost:6333 ./.venv/bin/python scripts/seed_qdrant.py \
  --bundle data/match-001

./scripts/run_app.sh --dev
```

Open `http://127.0.0.1:5173` for Vite hot reload, or `http://127.0.0.1:8000` for the production
frontend served by FastAPI. The request path does not require an Anthropic key: the demo ships
precomputed, reviewed artifacts and embeds search queries locally.

To process new footage, copy `.env.example` to `.env`, add `ANTHROPIC_API_KEY`, and use the
`pipeline.ingest`, `pipeline.sample`, and `pipeline.propose --captioner claude` commands. The
pipeline is batch-based; it does not claim live broadcast ingest.

## Deploy

[`render.yaml`](render.yaml) defines the reviewed deployment path: one Docker web service backed
by Qdrant Cloud. The container builds the Vite application, preloads the local embedding model,
ships only the redistributable demo bundle, restores that baseline on restart, and serves the UI,
API, and media from one origin.

Import the Blueprint in Render, then provide `QDRANT_URL` and `QDRANT_API_KEY` as secrets. The
Qdrant collection must be seeded once before the first demo:

```bash
QDRANT_URL=https://your-cluster QDRANT_API_KEY=your-key \
  ./.venv/bin/python scripts/seed_qdrant.py
```

After that one-time index seed, the Docker build and `/api/matches` health check are
self-contained; startup reconciles the seeded points with the restored manifest.

## Demo data and licensing

The public bundle contains only one edited SoccerTrack v2 match half. SoccerTrack v2 is licensed
under CC BY 4.0; full source and attribution details are recorded in
[`docs/assets-manifest.md`](docs/assets-manifest.md).

Professional broadcast footage was used locally to test the alternate already-directed input
profile. It is copyrighted and is not present in Git, the deploy image, screenshots, or the demo
video. Every public claim and shot must remain grounded in the CC-BY match.

## Reproducible checks

```bash
./.venv/bin/ruff check .
./.venv/bin/python -m pytest -q

cd web
npm test
npm run build
npm run lint
```

Detector evaluation is reproducible separately; the annotation file is used only by this scoring
command:

```bash
./.venv/bin/python scripts/eval_detector.py \
  data/match-001/windows.json \
  data/match-001/bas/117093_12_class_events.json \
  --half 1 --labels GOAL
```

Implementation plans and independent review verdicts are preserved under [`.ai/tasks`](.ai/tasks).
