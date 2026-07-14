#!/usr/bin/env bash
# Delegate implementation of a plan (or a scoped phase of it) to a Codex
# peer session with WORKSPACE-WRITE sandbox: Codex edits the working tree
# and runs repo checks; it cannot commit, push, or reach the network.
# One persistent thread per target — later phases resume with context.
#
# Usage:
#   scripts/codex/implement.sh <target> ["instructions"] [--dry-run]
#   scripts/codex/implement.sh reset <target>
#   scripts/codex/implement.sh show  <target>
#
# <target> is normally a plan path (.ai/tasks/<task>/plan.md).
# "instructions" narrows scope, e.g. "Implement Phase 1 only".
# The report ends with: IMPLEMENTATION_COMPLETE | IMPLEMENTATION_PARTIAL
# After it returns, the coordinator reviews the FULL diff and fixes issues
# directly — resume only for genuinely new scope (per AGENTS.md).

set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"

usage() {
    sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
    exit 64
}

PHASE=implement
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
        --dry-run) DRY_RUN=true; shift ;;
        -*) echo "error: unknown flag: $1" >&2; usage ;;
        *)
            if [ -n "$EXTRA_PROMPT" ]; then EXTRA_PROMPT="$EXTRA_PROMPT $1"; else EXTRA_PROMPT="$1"; fi
            shift ;;
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
    PROMPT="$(render_tpl "$PROMPT_DIR/implement-continue.tpl")"
else
    MODE=start
    PROMPT="$(render_tpl "$PROMPT_DIR/implement-start.tpl")"
fi

if [ "$DRY_RUN" = true ]; then
    echo "mode: $MODE  phase: $PHASE  sandbox: workspace-write (resume inherits)"
    echo "model/effort: $(phase_model "$PHASE") / $(phase_effort)"
    echo "state: $(state_dir "$PHASE")/$(state_key "$TARGET").*"
    echo "--- prompt ---"
    printf '%s\n' "$PROMPT"
    exit 0
fi

if [ "$MODE" = start ]; then
    codex_start "$PHASE" workspace-write "$TARGET" "$PROMPT"
else
    codex_resume "$PHASE" "$TARGET" "$PROMPT"
fi
