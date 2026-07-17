1. “Published events may not be human-verified.” — **Addressed** by lines 13–20: deployed scope is limited to curated match-001, match-002 is explicitly excluded, and baseline goal validation is required before deployment.

2. “Incident grouping is undefined and chained replays may split.” — **Addressed** by lines 28–34: time-based grouping, rolling incident end, and deterministic representative ordering are explicit.

3. “Celebration reservation can select the wrong clip or exceed caps.” — **Addressed** by lines 25–40 and 43–44: celebrations are partitioned first, the raw latest is reserved, its budgets are debited up front, and caps remain absolute.

4. “Rejected events can leave stale IDs that make Build return 404.” — **Addressed** by lines 54–58: selection is reconciled after timeline refresh, both organizer and Build use it, and reject-after-selection is tested.

5. “Editing selection can leave a stale built video/download.” — **Addressed** by lines 60–63 and 75: selection changes reset the build mutation and require rebuilding.

6. “Frontend tests have no executable runner or gate.” — **Addressed** by lines 65–72: Vitest, an `npm test` script, required tests, and acceptance-gate execution are specified.

No new actionable issues introduced.

APPROVED