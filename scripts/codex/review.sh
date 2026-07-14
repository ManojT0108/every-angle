#!/usr/bin/env bash
# Iterative Codex peer review of a plan or an implementation, with a
# persistent thread per target so follow-up rounds keep full context.
#
# Usage:
#   scripts/codex/review.sh <plan|code> <target> [--notes "..."] [--extra "..."] [--dry-run]
#   scripts/codex/review.sh <plan|code> reset <target>
#   scripts/codex/review.sh <plan|code> show  <target>
#
# <target> is normally a plan path (.ai/tasks/<task>/plan.md); a free-form
# label is accepted for unplanned work. First call starts a session; later
# calls resume it (incremental re-review). Reviews run in a READ-ONLY
# sandbox. The review ends with a verdict tag on its own line:
#   APPROVED | REQUEST_CHANGES | NEEDS_REWORK
# Loop policy (caps, escalation) lives in AGENTS.md, not here.

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

usage() {
    sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
    exit 64
}

PHASE="${1:-}"; shift || true
case "$PHASE" in plan|code) ;; *) usage ;; esac

ACTION=auto
case "${1:-}" in
    reset|show) ACTION="$1"; shift ;;
esac

TARGET="${1:-}"; shift || true
[ -n "$TARGET" ] || usage

EXTRA_PROMPT=""
IMPLEMENTER_NOTES=""
DRY_RUN=false
while [ $# -gt 0 ]; do
    case "$1" in
        --notes)   IMPLEMENTER_NOTES="$2"; shift 2 ;;
        --notes=*) IMPLEMENTER_NOTES="${1#*=}"; shift ;;
        --extra)   EXTRA_PROMPT="$2"; shift 2 ;;
        --extra=*) EXTRA_PROMPT="${1#*=}"; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        *) echo "error: unknown argument: $1" >&2; usage ;;
    esac
done
export TARGET EXTRA_PROMPT IMPLEMENTER_NOTES

case "$ACTION" in
    reset) codex_reset "$PHASE" "$TARGET"; exit 0 ;;
    show)  codex_show  "$PHASE" "$TARGET"; exit 0 ;;
esac

require_deps

if [ -f "$(thread_file "$PHASE" "$TARGET")" ]; then
    MODE=resume
    PROMPT="$(render_tpl "$PROMPT_DIR/$PHASE-resume.tpl")"
else
    MODE=start
    PROMPT="$(render_tpl "$PROMPT_DIR/$PHASE-start.tpl")"
fi

if [ "$DRY_RUN" = true ]; then
    echo "mode: $MODE  phase: $PHASE  sandbox: read-only"
    echo "model/effort: $(phase_model "$PHASE") / $(phase_effort)"
    echo "state: $(state_dir "$PHASE")/$(state_key "$TARGET").*"
    echo "--- prompt ---"
    printf '%s\n' "$PROMPT"
    exit 0
fi

if [ "$MODE" = start ]; then
    codex_start "$PHASE" read-only "$TARGET" "$PROMPT"
else
    codex_resume "$PHASE" "$TARGET" "$PROMPT"
fi
