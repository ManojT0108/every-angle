# Agent orchestration plan

## Accepted design

1. Persist the coordinator-reviewer protocol in `AGENTS.md`, which Claude imports through `CLAUDE.md`.
2. Keep Claude as the default coordinator and Codex as a fresh headless reviewer.
3. Use `scripts/codex-review.sh <task> <phase>` at the plan and implementation checkpoints.
4. Enforce review-only behavior with `codex exec --sandbox read-only --ephemeral` and an explicit no-modification prompt.
5. Save the final reviewer response under `.ai/tasks/<task>/reviews/`; preserve existing outputs on a user-directed re-review.
6. Have the coordinator triage findings, update durable project truth, and report one consolidated result to the user.
7. Stop and report a concise blocker if the reviewer CLI is unavailable or unauthenticated; never make the user relay the review.

## Verification

- `codex exec --help` confirms `--sandbox read-only`, `--ephemeral`, `--cd`, and `--output-last-message` in Codex CLI 0.144.3.
- `bash -n scripts/codex-review.sh` passes.
- Dry runs for both phases resolve the correct repository, prompt, and review path without invoking Codex.
- A headless Claude session reviewed the implementation with only `Read`, `Glob`, and `Grep` tools and returned "Approve with minor changes."
