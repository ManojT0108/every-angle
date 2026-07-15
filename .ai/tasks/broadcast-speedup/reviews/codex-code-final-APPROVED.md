Prior finding:

- “Near-EOF sampling at exactly `duration` can overclaim frames.” — **Addressed** at `pipeline/sample.py:139-140`, clamping to `duration - 0.1`. Regression coverage is at `tests/test_broadcast_profile.py:80`.

No new scoped issues found. Fixed/amateur behavior remains unchanged, checklist requirements are satisfied, and the gate reports ruff clean with 43 tests passing.

APPROVED