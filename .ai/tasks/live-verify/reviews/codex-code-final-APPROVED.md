Prior findings:

- “`ensure_reconciled()` is not synchronized” — **addressed** at `api/main.py:746-770`. The app-wide guard and double-checked flag prevent concurrent reconciliation runs and the resulting point-deletion race.
- “Missing collection becomes a permanent generic 503” — **addressed** at `api/main.py:589-600`. Missing collections are skipped during reconciliation, while connectivity exceptions still propagate; request-time `_require_collection` retains the actionable 409.
- “Incremental fixes lacked regression tests” — **addressed** at `tests/test_api.py:400`, `604`, `638`, `699`, and `723`. The five new tests cover ID reservation, retry recovery, missing collections, runtime clip cutting, and the hosted no-source failure.

No new Critical or Major issues found. Commit ordering, manifest filtering, reconciliation, lock coverage, and graceful failure behavior remain consistent with the plan. The supplied gate is clean: ruff, 63 pytest tests, and web build/lint all pass.

APPROVED