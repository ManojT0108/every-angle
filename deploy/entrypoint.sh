#!/bin/sh
set -e
# Restore the IMMUTABLE baked baseline into DATA_ROOT on every start, so any
# restart / redeploy resets the demo to 5 accepted + 1 pending (session reset).
mkdir -p "$DATA_ROOT"
rm -rf "$DATA_ROOT/match-001"
cp -a /app/baseline/match-001 "$DATA_ROOT/match-001"
echo "baseline restored to $DATA_ROOT/match-001"
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-10000}"
