#!/usr/bin/env bash
# Shared helpers for the Codex peer scripts (review.sh, implement.sh).
# Source-only — not executable on its own.
#
# Written fresh for this repo. Concepts (persistent threads, verdict tags,
# per-target state) adapted from the MIT-licensed TRIP-workflow; no code
# copied. Differences by design:
#   - template substitution is LITERAL (a '&' or '\' in values must not be
#     interpreted, unlike naive awk gsub()),
#   - model choice is an explicit function argument, not sniffed from paths,
#   - thread state lives in .ai/codex-state/<phase>/ (gitignored).

set -euo pipefail

CODEX_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$CODEX_LIB_DIR/../.." && pwd)"
PROMPT_DIR="$CODEX_LIB_DIR/prompts"
STATE_ROOT="$REPO_ROOT/.ai/codex-state"

require_deps() {
    local missing=()
    command -v codex >/dev/null 2>&1 || missing+=(codex)
    command -v jq >/dev/null 2>&1 || missing+=(jq)
    if [ "${#missing[@]}" -gt 0 ]; then
        echo "error: missing dependencies: ${missing[*]}" >&2
        exit 127
    fi
}

# Derive a filesystem-safe key from a target (plan path or free-form label).
state_key() {
    local target="$1" abs
    if [ -e "$target" ]; then
        abs="$(cd "$(dirname "$target")" && pwd)/$(basename "$target")"
        printf '%s' "$abs" | sed 's|^/||; s|/|__|g'
    else
        printf '%s' "$target" | sed 's|^/||; s|/|__|g; s|[^A-Za-z0-9._-]|_|g'
    fi
}

# All state paths take: <phase> <target>. Phases: plan, code, implement.
state_dir()   { printf '%s/%s' "$STATE_ROOT" "$1"; }
thread_file() { printf '%s/%s.thread'        "$(state_dir "$1")" "$(state_key "$2")"; }
out_file()    { printf '%s/%s.out.md'        "$(state_dir "$1")" "$(state_key "$2")"; }
events_file() { printf '%s/%s.events.ndjson' "$(state_dir "$1")" "$(state_key "$2")"; }

# Model/effort per phase. CODEX_MODEL / CODEX_EFFORT env vars override.
# All phases run gpt-5.6-sol at xhigh (user decision 2026-07-13): review and
# implementation threads stay separate conversations, but use the same model.
# To try a different implementer without editing this file:
#   CODEX_MODEL=<model> scripts/codex/implement.sh <plan>
phase_model()  { printf '%s' "${CODEX_MODEL:-gpt-5.6-sol}"; }
phase_effort() { printf '%s' "${CODEX_EFFORT:-xhigh}"; }

# render_tpl <tpl-file>
# Substitutes {{TARGET}}, {{EXTRA}}, {{NOTES}} with $TARGET, $EXTRA_PROMPT,
# $IMPLEMENTER_NOTES using literal string replacement via awk index/substr
# (no regex in the replacement path). Values may span multiple lines.
render_tpl() {
    local tpl="$1"
    if [ ! -f "$tpl" ]; then
        echo "error: prompt template not found: $tpl" >&2
        return 1
    fi
    TPL_TARGET="${TARGET-}" TPL_EXTRA="${EXTRA_PROMPT-}" TPL_NOTES="${IMPLEMENTER_NOTES-}" \
    awk '
        function lit(s, ph, val,    out, i) {
            out = ""
            while ((i = index(s, ph)) > 0) {
                out = out substr(s, 1, i - 1) val
                s = substr(s, i + length(ph))
            }
            return out s
        }
        {
            line = $0
            line = lit(line, "{{TARGET}}", ENVIRON["TPL_TARGET"])
            line = lit(line, "{{EXTRA}}",  ENVIRON["TPL_EXTRA"])
            line = lit(line, "{{NOTES}}",  ENVIRON["TPL_NOTES"])
            print line
        }
    ' "$tpl"
}

# codex_start <phase> <sandbox> <target> <prompt>
# Fresh session: JSONL events captured, thread id persisted, final message
# written to the out file and echoed. Fails (exit 2) if a thread exists.
codex_start() {
    local phase="$1" sandbox="$2" target="$3" prompt="$4"
    local tf of ef
    tf="$(thread_file "$phase" "$target")"
    of="$(out_file "$phase" "$target")"
    ef="$(events_file "$phase" "$target")"

    if [ -f "$tf" ]; then
        echo "error: a '$phase' session already exists for $target" >&2
        echo "       thread id: $(cat "$tf") — use 'resume', or 'reset' to start fresh." >&2
        exit 2
    fi
    mkdir -p "$(state_dir "$phase")"

    codex exec \
        --json \
        --skip-git-repo-check \
        --sandbox "$sandbox" \
        --color never \
        -c model="$(phase_model "$phase")" \
        -c model_reasoning_effort="$(phase_effort)" \
        -o "$of" \
        "$prompt" \
        </dev/null >"$ef" 2>"$ef.stderr" || {
            echo "error: codex exec failed (rc=$?); stderr tail:" >&2
            tail -20 "$ef.stderr" >&2
            exit 1
        }

    local thread_id
    thread_id="$(jq -r 'select(.type == "thread.started") | .thread_id' "$ef" 2>/dev/null | head -1)"
    if [ -z "$thread_id" ] || [ "$thread_id" = "null" ]; then
        echo "error: no thread.started event captured; head of event log:" >&2
        head -10 "$ef" >&2
        exit 1
    fi
    printf '%s\n' "$thread_id" > "$tf"
    report_result "$phase" "$target" started
}

# codex_resume <phase> <target> <prompt>
# Follow-up turn on the persisted thread. Sandbox is inherited from the
# original session (codex exec resume does not accept --sandbox).
codex_resume() {
    local phase="$1" target="$2" prompt="$3"
    local tf of ef
    tf="$(thread_file "$phase" "$target")"
    of="$(out_file "$phase" "$target")"
    ef="$(events_file "$phase" "$target")"

    if [ ! -f "$tf" ]; then
        echo "error: no '$phase' session for $target — run without 'resume' to start one." >&2
        exit 2
    fi

    codex exec resume "$(cat "$tf")" \
        --json \
        --skip-git-repo-check \
        -c model="$(phase_model "$phase")" \
        -c model_reasoning_effort="$(phase_effort)" \
        -o "$of" \
        "$prompt" \
        </dev/null >"$ef" 2>"$ef.stderr" || {
            echo "error: codex exec resume failed (rc=$?); stderr tail:" >&2
            tail -20 "$ef.stderr" >&2
            exit 1
        }
    report_result "$phase" "$target" resumed
}

# report_result <phase> <target> <started|resumed>
report_result() {
    local phase="$1" target="$2" verb="$3" of tag
    of="$(out_file "$phase" "$target")"
    echo "$verb $phase session for $target"
    echo "  thread:       $(cat "$(thread_file "$phase" "$target")")"
    echo "  model/effort: $(phase_model "$phase") / $(phase_effort)"
    echo "  output:       $of"
    echo "---"
    cat "$of"
    printf '\n---\n'
    tag="$(awk 'NF { last = $0 } END { gsub(/^[ \t]+|[ \t\r]+$/, "", last); print last }' "$of")"
    echo "FINAL TAG: $tag"
}

codex_reset() {
    local phase="$1" target="$2" removed=0 f
    for f in "$(thread_file "$phase" "$target")" \
             "$(out_file "$phase" "$target")" \
             "$(events_file "$phase" "$target")" \
             "$(events_file "$phase" "$target").stderr"; do
        if [ -f "$f" ]; then
            rm -- "$f"
            echo "removed $f"
            removed=$((removed + 1))
        fi
    done
    [ "$removed" -gt 0 ] || echo "no $phase state on file for $target"
}

codex_show() {
    local phase="$1" target="$2" of
    of="$(out_file "$phase" "$target")"
    if [ ! -f "$of" ]; then
        echo "error: no $phase output on file for $target" >&2
        exit 1
    fi
    [ -f "$(thread_file "$phase" "$target")" ] && echo "thread: $(cat "$(thread_file "$phase" "$target")")"
    echo "---"
    cat "$of"
}
