1. “Edit commit ordering is unsafe.” — **Addressed** at lines 26–32: Search takes the match lock, failed manifest commits restore the old point, and failed compensation forces Search to 503 pending reconciliation.

2. “Live and batch indexing use different embedding text.” — **Addressed** at lines 21–25 and tested at 60–63 through one canonical `caption + type` representation.

3. “Pending edits and `type=none` lack a coherent state transition.” — **Addressed** at lines 16–20: notable edits reuse Accept materialization; `none` explicitly uses Reject.

4. “Review will redisplay stale AI values after editing.” — **Addressed** at lines 33–36 and 64: accepted manifest values overlay the raw proposal response.

5. “A reserved opening ID breaks selection/reel lookup.” — **Addressed** at lines 3–5, 51–53, and 59: the opening is fully deferred and removed from acceptance.

6. “match-002 cannot seed the public demo.” — **Addressed** at lines 40–43: deployable match-001 retains curated accepted events plus a playable pending proposal.

7. “Browse mode and edited rows can remain stale.” — **Addressed** at lines 37–38, 45–48, and 66–67: edits invalidate all affected queries and Search initializes in browse mode.

8. “A six-minute full re-encode can time out.” — **Addressed** at lines 54–56, 65, and 71–72 through stream-copy concat, playable-output testing, and a re-encode fallback.

No new actionable issues. The A/B/E/F-first split is safe: those changes do not depend on C and preserve the existing Accept/Reject flow. Given the deadline, the prudent sequence is A/B/E/F → deploy and smoke-test → C only if time remains.

APPROVED