# Task: build-every-angle

Build the "Every Angle" golden-path MVP defined in `.ai/tasks/ideation/plan.md` (v2, accepted 2026-07-13):

One licensed football match video → offline AI-proposed moments (frame captioning + audio cues) → human verification UI → verified event manifest → Qdrant semantic search → FFmpeg highlight reel + manifest-grounded text commentary.

**Scope of this task:** architecture, repo scaffold, and implementation through Gate 3 (feature freeze midday Jul 15). Layered additions (TTS, second language, Lyzr, Enkrypt) are separate follow-up tasks, only if the golden path stays green.

**Out of scope:** live/streaming ingestion, exhaustive event detection claims, any commentary content not derivable from the verified manifest.

**Gates (from ideation plan):**
- Gate 1 EOD Jul 13: footage locked + asset manifest, Qdrant smoke test, InsForge hello-world (≤1h), portal checklist.
- Gate 2 midday Jul 14: vertical slice (one video → one indexed moment → one search hit → one playable clip) or pivot to C.
- Gate 3 midday Jul 15: feature freeze; polish/reliability/deploy only.

Coordinator: Claude. Reviewer: Codex (plan + implementation checkpoints via `scripts/codex-review.sh`).
