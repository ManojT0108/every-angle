# Plan review loop — build-every-angle plan v2→v5 (workflow v2, Sol thread)

Reviewer: gpt-5.6-sol, effort xhigh, read-only sandbox. Thread `019f5e2a-f87d-7783-9fb3-e8f71aa93408`.
Coordinator: Claude. Scope: `.ai/tasks/build-every-angle/plan.md` (v2 at start, v5 at convergence).
Prior history: round 1 ran under the old single-pass tooling — see `codex-plan.md`.
Full per-version triage tables live in the plan itself; this file is the durable record of the loop.

## Round 2 (thread turn 1, plan v2) — REQUEST_CHANGES, 5 findings

1. **P1** — D12 exposed the new manifest before regenerating clips, rebuilding Qdrant, or
   promoting the D10 bundle; a mid-publish failure leaves revision-N metadata serving
   revision-(N−1) clips. Fix: stage + validate the complete revision, promote atomically,
   retain the previous revision on failure.
2. **P1** — Append-only proposal cache had no source/config/captioner provenance; mock-derived
   records could pass the M1 "real captioner" gate. Fix: per-run provenance + coded non-mock
   assertion.
3. **P2** — Rejected proposals not persisted; `from_proposal` undefined for manual events.
4. **P2** — Hosted Verify claimed workflows (evidence, editing) its bundle contents couldn't
   support.
5. **P2** — MiniLM embedding artifact unpinned; cold-start registry download during judging.

## Round 3 (turn 2, plan v3) — REQUEST_CHANGES

All 5 prior findings confirmed addressed (with line references). 2 new:

1. **P1** — Proposals multi-run but decisions/manifest lineage keyed by bare `proposal_id`;
   mock `p-001` and real `p-001` could share decision state. Fix: run-scoped globally unique ids.
2. **P2** — Deployed revision selection implicit; bundle lacked immutable self-describing
   metadata; `BUNDLE_URL`/checksum env vars undocumented. Fix: `bundle.json` in every bundle,
   app derives collection exclusively from it, retention while referenced.

## Round 4 (turn 3, plan v4) — REQUEST_CHANGES

Round-3 fixes partially complete: manifest example still used unscoped `from_proposal`; D12
retention rule contradicted D10. 1 new:

1. **P1** — Evidence frame paths not run-scoped (`frames/p-001-*.jpg`); a later run could
   overwrite an earlier run's frames and Verify would silently show wrong-run evidence.
   Fix: `frames/<proposal-id>/…` + pipeline validates evidence ownership.

## Round 5 (turn 4, plan v5) — **APPROVED**

All prior findings confirmed addressed (run-scoped ids/decisions/lineage at plan lines 65,
74–83, 90; unified retention rule at lines 47, 49; proposal-scoped evidence dirs + ownership
validation at lines 68, 77–79). "No new actionable issues were introduced."

## Disposition

13 findings total across the loop (5 + 2 + 1 new, plus partials); all accepted, none pushed
back. Plan v5 is the implementation baseline for M0.
