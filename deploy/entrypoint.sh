#!/bin/sh
set -e
# Restore the IMMUTABLE baked baseline into DATA_ROOT on every start, so any
# restart / redeploy resets both demos to their reviewed release state.
mkdir -p "$DATA_ROOT"
rm -rf "$DATA_ROOT/match-001" "$DATA_ROOT/match-002"
cp -a /app/baseline/match-001 "$DATA_ROOT/match-001"
cp -a /app/baseline/match-002 "$DATA_ROOT/match-002"
echo "baselines restored to $DATA_ROOT/match-001 and $DATA_ROOT/match-002"
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-10000}"
