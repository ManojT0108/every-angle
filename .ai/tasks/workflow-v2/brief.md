# Task: workflow-v2 — adopt TRIP-style Codex collaboration

User decision 2026-07-13: adopt the workflow pattern from the MIT-licensed
[TRIP-workflow](https://github.com/PiLastDigit/TRIP-workflow) (seen on r/ClaudeCode), with the
explicit instruction to **re-implement rather than copy** so no latent bugs are inherited.

## Safety review of the source repo (Claude, 2026-07-13)

Full read of every `.sh` and `.tpl` plus pattern scan of all `.md`: no network calls, no
`curl|bash`, no `eval`, no credential access, no sandbox bypasses, no prompt-injection content.
Verdict: clean. Bugs found and fixed in our re-implementation:

1. `awk gsub()` template substitution interprets `&`/`\` in substituted values → ours uses
   literal `index/substr` replacement.
2. Model selection sniffed from `STATE_DIR` string matching → ours passes phase explicitly.
3. Assumes `git diff HEAD` always works → our prompts handle a repo with no commits yet.

## What was adopted

Persistent per-target Codex threads (`codex exec resume`); verdict tags
(APPROVED/REQUEST_CHANGES/NEEDS_REWORK, IMPLEMENTATION_COMPLETE/PARTIAL); iterative review
loops capped at 5 rounds; implementer notes fed back to the reviewer; testing gate before code
review; "NOT priorities" review guidance; Luna (workspace-write) implements, Sol (read-only)
reviews, Claude coordinates/self-reviews/fixes; single-source review checklist
(`docs/review-checklist.md`).

## What was rejected

- TRIP-3-release auto commit/tag/merge/push → conflicts with this repo's "no commits unless
  the user asks" rule; release ceremony stays user-gated.
- ARCHI.md — redundant with AGENTS.md + `.ai/HANDOFF.md` at this repo's size.
- The `.claude/skills` packaging — our scripts live in `scripts/codex/` and the protocol in
  `AGENTS.md`, consistent with the existing `.ai/` convention.

Implementation: `scripts/codex/{_lib.sh,review.sh,implement.sh,prompts/*.tpl}`,
`docs/review-checklist.md`, AGENTS.md "workflow v2" section. Supersedes `scripts/codex-review.sh`
(removed). First live run: plan re-review of `.ai/tasks/build-every-angle/plan.md`.
