# Ideation & strategy plan

Status: v2 — ACCEPTED 2026-07-13. User decisions: **build A "Every Angle" (narrowed golden path), football/soccer demo, C is the pivot fallback at Gate 2.**

## Context

- Solo participant + two AI coding agents (Claude Code, Codex). Strong Python/ML background; Node 23 available.
- Time budget: ~3.5 effective build days (now → Jul 17, 10:00 AM PDT).
- Official judging criteria unpublished. **Working assumptions (v2, per review):** main prize — demo quality & reliability 25%, technical execution 25%, innovation 20%, usefulness/impact 20%, sponsor fit 10%. Separate scorecard for the InsForge prize track. Revisit when official criteria drop.

## Strategy principles

1. **Demo-first, reliability-first.** A complete, polished, working demo beats an ambitious partial one. "Credible end-to-end demo by Jul 15" is a pass/fail gate, not a score input.
2. **Differentiate on technical bar** — video understanding + multimodal retrieval stands out vs. the expected flood of chatbots — but positioned honestly: **AI-assisted highlight production** (human verifies AI-proposed moments), not exhaustive event detection.
3. **Two deep sponsor integrations beat four shallow ones.** Qdrant is genuinely central. InsForge added early only if hello-world deploys fast (its prize track makes it worth one timeboxed hour). Lyzr and Enkrypt are strictly timeboxed optional layers.
4. **Position for a buyer.** Media/club content teams: "highlight assembly from hours to minutes." Judges must see who pays and why.

## Candidate ideas (summary — details unchanged from v1, see git history once committed)

- **A. "Every Angle"** — match footage → AI-proposed moments → human-verified event manifest → Qdrant semantic search → one-click highlight reel + AI commentary. Track 3. ⭐ Recommended, aggressively narrowed (below).
- **C. "ScoutGPT"** — multi-agent scouting copilot over open data (StatsBomb), player-similarity via Qdrant, comparison visuals. Track 4. **Designated pivot target** if A fails its gate.
- **B. "FormCoach"** — single-motion form-similarity analysis (pose embeddings). Track 1. Credible only framed as similarity, not biomechanics/injury advice.
- D (fan companion), E (re-voicing): dropped — D is undemoable/crowded, E folds into A as its commentary layer.

Codex's independent ranking matches: A (narrowed) > C > B.

## MVP definition (v2 — the golden path)

**Core (must work end-to-end, deployed, before anything else is added):**
1. ONE curated, clearly-licensed match video, one sport, 3–5 supported event types
2. Offline/precomputed processing (frame sampling + vision-LLM captioning + audio cues) → **AI-proposed moments**
3. Human verification step → **verified event manifest** (also the factuality source for commentary — no unsupported names/scores ever)
4. Qdrant index over verified moment captions → semantic search UI with 8–12 golden queries that demonstrably work
5. Deterministic FFmpeg reel assembly from selected moments → playable in browser (codec tested on deploy target)
6. **Text** commentary/captions generated only from manifest metadata

**Layered additions, in order, each only after golden path stays green:** TTS (English) → second language → Lyzr agent orchestration (timebox 2h) → Enkrypt guardrails framed as safety layer (timebox 2h) → short user-uploaded clips → social captions.

## Gates & cut lines

- **Gate 1 (TODAY, EOD Jul 13):** licensed asset locked + sponsor smoke tests (Qdrant collection created; InsForge hello-world ≤1h or dropped) + portal inspected.
- **Gate 2 (midday Jul 14): vertical slice** — one video → one indexed moment → one search hit → one playable clip. **Fail → simplify detection or pivot to C immediately.**
- **Gate 3 (midday Jul 15): feature freeze.** Only polish, reliability, deploy after this.

## Schedule (v2)

- **Jul 13 (rest of day):** user decision; submission portal inspection + artifact checklist; licensed footage acquired + asset manifest; Qdrant/InsForge smoke tests; architecture task plan.
- **Jul 14:** vertical slice by midday (Gate 2); then detection quality iteration + golden queries; FFmpeg/codec test on deployment target.
- **Jul 15:** UI, reel builder, text commentary; deploy; feature freeze midday (Gate 3); layered additions only if green.
- **Jul 16:** reliability testing, demo video recorded, submission copy, **dry-run submission on portal (afternoon)**; pre-render showcase reel as demo fallback.
- **Jul 17:** contingency only; **submit by 8:30 AM** (90-min buffer).

## Cost & deployment constraints

Precompute and cache all model outputs; cap footage duration/resolution; measure per-video API cost on first run; keep a local + prerecorded demo fallback; test upload limits/timeouts/ephemeral-disk behavior on the host before relying on it.

## Asset licensing workflow

`docs/assets-manifest.md`: source URL, creator, license + version, attribution text, download date, derivatives allowed. Avoid CC-ND. Prefer one clearly reusable source over several uncertain ones. Watch for separately-protected music/commentary/broadcast graphics.

## Review triage (Codex review 2026-07-13, 11 findings)

| # | Sev | Finding (short) | Disposition |
|---|---|---|---|
| 1 | H | MVP = several risky systems | **Accepted** — golden-path MVP redefined above |
| 2 | H | Additive scoring hides delivery risk | **Accepted** — pass/fail completion gate added |
| 3 | H | Detector can't support promised search semantics | **Accepted** — verified event manifest + "AI-assisted" positioning |
| 4 | H | Cut lines too late | **Accepted** — Gate 2 midday Jul 14, freeze midday Jul 15 |
| 5 | M | Sponsor integration too broad | **Accepted** — Qdrant central, InsForge 1h test, Lyzr/Enkrypt timeboxed |
| 6 | M | Licensing needs provenance workflow | **Accepted** — asset manifest |
| 7 | H | No cost/latency/deployment constraints | **Accepted** — constraints section added |
| 8 | M | Guardrails ≠ factuality | **Accepted** — commentary only from verified manifest |
| 9 | H | Submission logistics deferred too long | **Accepted** — portal today, dry run Jul 16, submit 8:30 AM |
| 10 | M | Schedule slips Jul 14→15 | **Accepted** — v2 cadence per review |
| 11 | M | Judging weights misweighted | **Accepted** — v2 weights + separate InsForge scorecard |

## Open questions

1. ~~USER DECISION: project~~ → **A (narrowed), C as Gate-2 fallback** (2026-07-13)
2. ~~USER DECISION: sport~~ → **football/soccer** (2026-07-13). Event types: goals, saves, penalties, cards, counterattacks.
3. ~~Official judging criteria~~ → published 2026-07-13 (portal Evaluation tab): 7 unweighted dimensions — see `docs/submission-checklist.md` for the list and criteria→plan mapping. Weights still unknown; v2 working weights stand.
4. ~~Exact submission artifacts~~ → confirmed 2026-07-13: repo + working demo URL + description (+ optional video). Deployed app is REQUIRED. See `docs/submission-checklist.md`.
