# Agent collaboration workspace

Use one directory per feature or task:

```text
.ai/tasks/<task-name>/
├── brief.md
├── plan.md
├── handoff.md
└── reviews/
    ├── codex-plan.md
    └── codex-implementation.md
```

Create only the files a task needs. Incorporate accepted decisions into the plan, product documentation, or code; review files remain supporting evidence rather than project truth.

Claude is the default coordinator. It invokes Codex without user relaying via:

```bash
scripts/codex-review.sh <task-name> plan
scripts/codex-review.sh <task-name> implementation
```

Each command starts a new read-only, ephemeral Codex reviewer and captures its final response in the task's `reviews/` directory. If a user-directed re-review exists, the helper preserves the earlier review and writes a timestamped file. Run `scripts/codex-review.sh --dry-run <task-name> <phase>` to inspect the prompt and destination without calling Codex; `--dry-run` must be the first argument.

The machine running the helper must have an authenticated Codex CLI. An interactive Claude session may request a one-time shell approval before its first invocation; that approval does not require relaying any review content.
