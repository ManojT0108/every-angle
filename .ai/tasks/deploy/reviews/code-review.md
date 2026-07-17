# Deploy — Codex code review (promoted record)

Model: gpt-5.6-sol @ xhigh. Two rounds. Final verdict: **APPROVED**.

## Round 1 — REQUEST_CHANGES (one Major finding)

**Major — `Dockerfile:27`, `api/main.py:399-409`: runtime embedding was not actually
offline.** FastEmbed 0.7.1 can make Hugging Face metadata requests even with a populated
cache. On a Render cold start during an HF outage/rate-limit, the embedder construction
could fail; because `_EMBEDDING_LOAD_ERROR` is cached and never retried, Search would stay
503 until a manual restart. Recommended fix: verify the baked cache with
`local_files_only=True` and use that mode for the deployed runtime constructor.

Everything else passed: bundle allowlist, secret scan, guarded media paths, baseline reset,
manifest-derived search/reels, dependency pins, supplied testing gate.

## Fix applied

- `api/main.py` `_load_embedding_model`: construct
  `TextEmbedding(model_name=..., local_files_only=(FASTEMBED_LOCAL_ONLY == "1"))`. The
  deployed container sets the env, so the model loads strictly from the baked cache with no
  network call; local dev leaves it unset so a first run may still download.
- `Dockerfile`: `ENV ... FASTEMBED_LOCAL_ONLY=1`, and the prewarm now downloads the model
  then re-loads it with `local_files_only=True` — an incomplete baked cache fails the build
  loudly instead of deferring to a runtime download / 503.

## Round 2 — APPROVED

> Prior finding "Runtime embedding is not actually offline." — Addressed. `Dockerfile:21,31-32`
> enables deployed offline mode and verifies the baked cache with `local_files_only=True`;
> `api/main.py:413-415` uses that mode at runtime while preserving local-development
> downloads. No new issues introduced. The supplied gate is green: 75 Python tests and 15
> Vitest tests passed.
