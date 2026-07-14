# Sports World Cup Hackathon

## Shared project context

- This repository is the shared workspace for the Sports World Cup hackathon project.
- The official brief, schedule, tracks, and sponsor stack live in `docs/hackathon-brief.md`. Submission deadline: **July 17, 2026, 10:00 AM PDT**.
- Judging criteria are not yet published. Working assumptions are recorded in the active task plan; do not invent official criteria. Once known, use them to prioritize product and engineering decisions.

## Before starting work

1. Read the project `README.md`, `.ai/HANDOFF.md`, and the relevant task directory under `.ai/tasks/`.
2. Inspect `git status` and the current diff before editing.
3. Treat unexpected uncommitted changes as another agent's work. Preserve them and do not revert or overwrite them.
4. State material assumptions when requirements are incomplete.

## Claude-Codex collaboration (workflow v2, user-approved 2026-07-13)

Concepts adapted (re-implemented, not copied) from the MIT-licensed TRIP-workflow
(github.com/PiLastDigit/TRIP-workflow). The user gives the goal to Claude (coordinator) and
never relays messages between agents. Codex participates as headless peer threads via
`scripts/codex/`: **all phases run gpt-5.6-sol at xhigh** (user decision 2026-07-13) — review
threads in a read-only sandbox, implementation threads in a workspace-write sandbox. No
reduced-effort smoke runs. Threads persist per target, so follow-up rounds keep full context;
state lives in `.ai/codex-state/` (gitignored, disposable).

**Context model — what carries and what does not:**

- A Codex thread is server-side conversation state keyed by a thread id (saved under
  `.ai/codex-state/<phase>/<target>.thread`). `resume` replays that thread's full history, so
  round N sees rounds 1..N−1 — findings, the code it read, and the coordinator's `--notes`.
- **Threads do not share context with each other.** The plan-review, code-review, and
  implement threads are three separate conversations, even on the same model and target.
- **Codex never sees Claude's conversation with the user.** Its entire world is: the repo
  files it reads, the prompt template, and the `--extra` / `--notes` Claude passes in.
- Therefore **the repo is the shared memory**: `AGENTS.md`, `.ai/HANDOFF.md`, the task
  `plan.md`, and `.ai/tasks/<task>/reviews/` carry cross-thread and cross-session truth. Every
  prompt template starts by telling Codex to read them. Keep them current — a stale handoff is
  a stale peer.
- Because implementer and reviewer are now the same model, keep them in **separate threads**
  (the scripts enforce this) and keep Claude's own read of the full diff between them — that
  independent pass is what remains of the two-model check.

Cycle per task (artifacts in `.ai/tasks/<task-name>/`):

1. **Plan.** Claude writes `plan.md`, then runs
   `scripts/codex/review.sh plan .ai/tasks/<task>/plan.md` automatically (no user prompt
   needed). Triage: fix legitimate findings in the plan; push back on wrong ones via
   `--notes`. Resume the same command until the verdict tag is `APPROVED`. Cap: 5 rounds.
   `NEEDS_REWORK`, a stalled loop, or an unresolved design disagreement → escalate to user.
2. **Implement.** `scripts/codex/implement.sh <plan-path> ["Phase N only"]` delegates the
   build to Luna. While a Luna turn runs, Claude does not edit the tree (single-writer rule).
   Tag `IMPLEMENTATION_PARTIAL` → resume with instructions or finish small leftovers directly.
3. **Self-review.** Claude reads the FULL diff against the plan and conventions, fixes
   problems directly — no fix ping-pong with Luna. Resume the implement thread only for
   genuinely new scope. Verify ticked plan checkboxes match the actual diff.
4. **Testing gate.** Project checks and affected tests must pass before code review; failures
   block the loop. Summarize as e.g. `checks: clean | tests: N passed (M new)`.
5. **Code review.** `scripts/codex/review.sh code <plan-path> --extra "<gate summary>"`,
   automatically after the gate. Same triage/notes/resume loop until `APPROVED`, cap 5 rounds.
   Criteria live in `docs/review-checklist.md` (single source of truth).
6. **Promote.** After convergence, copy the final review from `.ai/codex-state/` to
   `.ai/tasks/<task>/reviews/` (the durable record). State files are disposable.
7. **Release.** Commits, tags, merges, and pushes happen only when the user asks — the
   repo rule below is unchanged by this workflow.

Guardrails:

- Reviewer threads never modify files; implementer threads never commit, push, or access the
  network. Neither invokes another agent — no recursive chains.
- Reviews identify scope and include severity, file/line, a concrete failure scenario, and a
  recommended fix.
- Claude triages all findings and gives the user one consolidated update per checkpoint.
- If the codex CLI is unavailable, unauthenticated, or failing, report that single blocker;
  never fall back to manual message relaying.
- Interactive Claude and Codex windows share no conversation state: files, Git state, and the
  persisted thread outputs are the communication channel.
- Use separate Git worktrees or clearly separated file ownership if agents ever implement
  concurrently.
- Update `.ai/HANDOFF.md` when pausing or transferring active work.

## Engineering working agreements

- Prefer the smallest coherent, testable increment that advances the hackathon submission.
- Keep plans and documentation synchronized with accepted decisions, but do not treat review files as permanent project truth.
- Never expose credentials or commit secrets. Use `.env.example` for documented environment variables.
- Document new dependencies and external services. Ask before adopting paid services, creating external resources, or using sensitive credentials.
- Run relevant checks after changes and report anything that could not be verified.
- Do not commit, push, or perform destructive Git operations unless the user requests them.
