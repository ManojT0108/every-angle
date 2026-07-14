# Agent orchestration brief

## Goal

Let the user give a task once to the active coordinator while Claude and Codex exchange plans and review findings without the user copying messages between interactive windows.

## Constraints

- Claude is the default coordinator for this hackathon; Codex is review-only by default.
- Reviewers must be technically prevented from editing product files.
- Reviews happen automatically at stable plan and implementation checkpoints.
- No recursive agent calls, background debate loops, commits, pushes, or external actions.
- Review artifacts must remain visible in the repository.

## Acceptance criteria

- Shared instructions define roles, checkpoints, triage, and failure behavior.
- A reusable helper launches a fresh Codex review in a read-only sandbox and saves the final response under the task directory.
- The helper supports a no-cost dry run, validates its inputs, rejects empty implementation checkpoints, and preserves earlier reviews.
- The setup passes shell syntax checks and receives one independent read-only peer review.
