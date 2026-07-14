#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 VIDEO.mp4 [VIDEO_ID]" >&2
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIDEO_PATH="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
if [[ ! -f "$VIDEO_PATH" ]]; then
  echo "input does not exist: $VIDEO_PATH" >&2
  exit 2
fi

VIDEO_ID="${2:-$(basename "$VIDEO_PATH" .mp4)}"
DATA_ROOT="${DATA_ROOT:-$ROOT_DIR/data}"
VIDEO_DIR="$DATA_ROOT/$VIDEO_ID"
RUN_ID="${RUN_ID:-$(python3 -c 'from datetime import datetime, timezone; import uuid; print("r-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])')}"
WINDOWS_PATH="$VIDEO_DIR/windows.json"

mkdir -p "$VIDEO_DIR"
cd "$ROOT_DIR"

python3 -m pipeline.ingest \
  --input "$VIDEO_PATH" \
  --video-id "$VIDEO_ID" \
  --output "$WINDOWS_PATH"

python3 -m pipeline.sample \
  --input "$VIDEO_PATH" \
  --windows "$WINDOWS_PATH" \
  --output-dir "$VIDEO_DIR/frames" \
  --run-id "$RUN_ID"

python3 -m pipeline.propose \
  --windows "$WINDOWS_PATH" \
  --source "$VIDEO_PATH" \
  --output-dir "$VIDEO_DIR" \
  --frames-dir "$VIDEO_DIR/frames" \
  --captioner mock \
  --run-id "$RUN_ID"

echo "M0 pipeline complete: $VIDEO_DIR/proposals.json"
