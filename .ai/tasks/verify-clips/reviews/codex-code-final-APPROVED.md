Prior finding:

- “Source-free Keep cannot reuse a proposal clip.” — **Addressed.** [api/main.py:911](/Users/manojt/Documents/Hackathon/sports_worldcup_hackathon/api/main.py:911) resolves the proposal-only clip and [api/main.py:914](/Users/manojt/Documents/Hackathon/sports_worldcup_hackathon/api/main.py:914) promotes it to the event path before source-cut fallback. Regression coverage is at [tests/test_api.py:784](/Users/manojt/Documents/Hackathon/sports_worldcup_hackathon/tests/test_api.py:784); the genuine missing-both-clips case is corrected at [tests/test_api.py:808](/Users/manojt/Documents/Hackathon/sports_worldcup_hackathon/tests/test_api.py:808).

No new Critical or Major issues found in the scoped edits. The supplied gate is green: Ruff, 67 pytest tests, Vitest, web build, and oxlint.

APPROVED