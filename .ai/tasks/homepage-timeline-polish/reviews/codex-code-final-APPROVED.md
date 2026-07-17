- **“Loading/error is treated as an empty response, showing misleading zeros.” — Addressed.** `web/src/App.tsx:108` distinguishes unavailable data from a real empty array; `web/src/App.tsx:123` and `:125` display “—” until proposals arrive while `web/src/App.tsx:97` keeps the core app unblocked.

No new issues found. The change conforms to the plan and supplied gate is clean.

APPROVED