Continue the implementation session for `{{TARGET}}`.

The working tree may have changed since your last turn — the coordinator reviews your work
and fixes issues directly. Run `git status -s` and `git diff HEAD` (or re-read the relevant
files if HEAD does not exist) to resync first. Treat the current tree as authoritative and do
not revert the coordinator's adjustments.

Same rules as before: stay within the stated scope, tick completed plan checkboxes, leave the
project's checks green, no tests unless asked, never commit/tag/push or touch release
ceremony, report needed installs as leftovers.

Same report format (files changed, deviations, leftovers, check status), ending with exactly
one tag on its own line:
IMPLEMENTATION_COMPLETE
IMPLEMENTATION_PARTIAL

## New instructions from the coordinator

{{EXTRA}}
