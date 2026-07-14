# Code review checklist

Single source of truth for code-review criteria. Both the Codex review threads
(`scripts/codex/review.sh code`) and any manual review apply these criteria by reference so
the two surfaces cannot drift.

## Checklist

### 1. Functional correctness

- [ ] Logic matches the plan's data contracts (`proposals.json`, `manifest.json` shapes)
- [ ] Error scenarios handled with actionable feedback
- [ ] Edge cases on real inputs validated (empty manifest, zero proposals, missing clip file)

### 2. Manifest-is-truth (project-specific, non-negotiable)

- [ ] Search results, reel, and commentary derive ONLY from the verified manifest
- [ ] Commentary never invents player names, teams, scores, or minutes not in the manifest
- [ ] Dataset ground-truth annotations are never used as pipeline input (eval only)
- [ ] Qdrant collection rebuilds carry the manifest revision; no stale derivatives served

### 3. Reliability of the demo path

- [ ] No model/API calls on the demo hot path except query embedding (local) per plan D4
- [ ] Expensive artifacts cached on disk; re-runs incremental
- [ ] Graceful degradation when Qdrant or artifacts are unavailable (clear message, no crash)

### 4. Code quality

- [ ] DRY / KISS; no unnecessary abstraction for a 4-day project
- [ ] Consistent naming; comments only where the code can't say it
- [ ] No dead code or unused imports

### 5. Security & secrets

- [ ] No credentials or API keys in the tree (env vars via `.env`, documented in `.env.example`)
- [ ] User-supplied query strings handled safely (no shell interpolation into ffmpeg/commands)

### 6. Reproducibility & performance

- [ ] Dependencies pinned; new ones documented (plan D13)
- [ ] No obvious hot-path waste (per-request model loads, unbounded frame extraction)
- [ ] Resource cleanup (ffmpeg temp files, file handles)

## Severity

- **Critical (blocks):** data corruption, secrets exposure, manifest-is-truth violations,
  demo-path crash on the golden path
- **Major (fix now):** incorrect logic, missing error handling, broken build/checks
- **Minor (should fix):** duplication, style inconsistency, missing docs
- **Suggestion:** optimizations, readability, extra coverage

## Approval gate

- No Critical or Major findings open
- Project checks pass (testing-gate summary supplied by coordinator)
- New logic has tests, or an explicit debt note with rationale in the plan/handoff
