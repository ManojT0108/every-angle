# Website plan — Every Angle

Status: v1 draft, 2026-07-15. Visual mockup (real data): see `docs/design-mockup.md` for the URL.
Awaiting user sign-off, then Codex plan review.

## Decision: Streamlit is retired (user, 2026-07-15)

Judging scores "presentation quality" and a **working demo URL is a hard submission requirement**.
Streamlit cannot be made to look like a product. Replaced with a real web app.

## Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | **React 19 + Vite + TypeScript** | Real component model; instant HMR; one `npm run build` to static assets |
| Styling | **Tailwind v4** with our own tokens | Fast, and the palette below keeps it off the generic-AI-look shelf |
| Data | **TanStack Query** | Caching, loading/error states for free — no hand-rolled fetch spaghetti |
| Video | native `<video>` | Clips are pre-encoded H.264/AAC; nothing else needed |
| Backend | **FastAPI + uvicorn** | Already a Python repo; reuses the pipeline modules directly |
| Deploy | one container: FastAPI serves `/api`, `/media`, and the built SPA | One process, one URL, nothing to desync |

**No SSR, no framework magic.** The app is read-mostly — clips, captions and manifest are all
precomputed — so the backend is thin and the frontend is a static bundle.

## Ownership while building (concurrent agents)

Per AGENTS.md, concurrent implementation requires **clearly separated file ownership**:

- **Codex (Sol) owns `api/`** — FastAPI, the endpoints below, tests. Well-specified, no visual
  judgement needed.
- **Claude owns `web/`** — React app, design system, all UI. Needs eyes on rendered output.
- Neither touches `pipeline/`, which is frozen and reviewed.

## Design direction

**Subject world:** an edit suite, not a dashboard. Chalk lines on grass, sodium floodlights,
timecode, the tally light. The palette is drawn from that, not from a dark-mode template.

**The palette encodes our differentiator — provenance.**

| Token | Value (dark) | Meaning |
|---|---|---|
| Ink | `#0A100E` → `#1B2721` | night pitch; a blue-green ink, not pure black |
| **Sodium** | `#FFA23A` | **machine-proposed, awaiting judgement** |
| **Chalk** | `#F2F5EF` | **human-verified truth** (pitch markings are chalk) |
| Turf | `#4FA36B` | affirmative actions |
| Tally | `#FF4D3D` | destructive only |

A viewer can see, at a glance, what the AI *claimed* versus what a human *stood behind*. Honesty
as a design system — and it is the thing no chatbot submission will have.

**Type:** condensed grotesk for display (scoreboard energy), system sans for body, monospace with
`tabular-nums` for every timecode and score. Sport is numbers; the numbers should line up.

**Layout: timeline-first.** The signature element is a full-width match timeline —
candidate windows as ticks *below* the line, human-verified events *above* it, rejected proposals
struck through. It is not decoration: it shows where the machine looked and what the human kept,
which is the entire product argument in one graphic.

## Screens

1. **Verify** — the proposal queue. Each card shows the frames the model *actually saw* (tight
   ball-tracked crops, then wide aftermath), its caption, type and confidence, and Keep / Reject /
   Edit. Plus **Add moment** — how the goal the AI missed got into the manifest.
2. **Search** — the hero. Semantic query over *verified captions only*, Qdrant cosine scores
   shown honestly, results play inline.
3. **Reel** — selected moments as a strip, ordered, total runtime, one deterministic FFmpeg build.

Above all three: five figures — **11:12 of 45:06 to review**, 40 candidates, 2/2 goals, 54s
detector, $1.15 vision cost.

## API surface (thin by design)

```
GET  /api/matches                     -> [{video_id, duration, revision}]
GET  /api/matches/{id}/timeline       -> {windows[], events[], rejected[]}
GET  /api/matches/{id}/proposals      -> pending proposals + evidence frame URLs
POST /api/matches/{id}/decisions      -> accept / reject / edit / add   (writes decisions.json)
GET  /api/matches/{id}/search?q=      -> Qdrant query over the PUBLISHED revision
POST /api/matches/{id}/reel           -> build reel from selected event ids
GET  /media/...                       -> clips, thumbnails (static)
```

**Hot-path rule preserved (plan D4):** the only model call on the demo path is the local
embedding of the search query. No vision calls, no LLM calls. The demo cannot fail on a network
blip.

## Deploy

Single container: FastAPI + static + the published revision bundle. Qdrant Cloud free tier (or
bundled). Cold-start check before Gate 3: the app must serve search with model registries
unreachable (plan D13).

## Scope discipline

**In:** the three views, the timeline, search, reel playback, provenance chips.
**Out (v1):** drag-to-reorder, auth, uploads, multi-user, analytics.
