# Task artifacts

Create a short, descriptive directory for each substantial task. Keep its brief, plan, handoff, and agent reviews together.

For Claude-coordinated work, invoke the automatic read-only reviewer at the two stable checkpoints:

```bash
scripts/codex-review.sh <task-name> plan
scripts/codex-review.sh <task-name> implementation
```

The coordinator must triage the resulting review and continue. The user is not the message bus.
