### Prior findings

- “No findings.” — Not applicable; the previous review had no open defects.

### New issues

None.

Pass-2 verification:

- Point updates are compensated before releasing the match lock; failed compensation enables reconciliation: `api/main.py:1001`, `api/main.py:1094`, `api/main.py:1178`.
- Search and edit acquire the same match lock once, with no recursive acquisition or deadlock: `api/main.py:1035`, `api/main.py:1151`, `api/main.py:1342`.
- Canonical `caption. type` embedding is shared by live upserts, reconciliation, and batch rebuilds: `pipeline/index_qdrant.py:250`, `api/main.py:583`, `api/main.py:689`, `pipeline/index_qdrant.py:289`.
- Accepted proposal responses overlay manifest caption, type, and clip: `api/main.py:331`, `api/main.py:343`, `api/main.py:373`.
- Frontend edits invalidate proposals, timeline, and Search: `web/src/lib/verify.ts:8`.
- Section D remains an explicitly coordinator-owned data step.
- Gate accepted: Ruff clean, 75 pytest, 12 Vitest, web build and oxlint clean.

APPROVED