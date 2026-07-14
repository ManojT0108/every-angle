#!/usr/bin/env bash
# Run Every Angle. One process, one URL: FastAPI serves the API, the media and
# the built frontend, so there is nothing to desync and nothing extra to keep
# alive. This is also exactly what the deployed container runs.
#
#   scripts/run_app.sh          # build the frontend, then serve on :8000
#   scripts/run_app.sh --dev    # additionally run Vite on :5173 with HMR
#
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PORT="${PORT:-8000}"

if [[ ! -x .venv/bin/python ]]; then
  echo "No .venv — run: python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

# Qdrant powers search; without it the app loads but search returns 503.
if ! curl -sf http://localhost:6333/healthz >/dev/null 2>&1; then
  echo "→ starting Qdrant"
  docker compose up -d >/dev/null
  until curl -sf http://localhost:6333/healthz >/dev/null 2>&1; do sleep 1; done
fi
echo "✓ Qdrant"

echo "→ building frontend"
(cd web && npm run build >/dev/null)
echo "✓ frontend built"

# Load ANTHROPIC_API_KEY etc. if present. Nothing on the request path needs it
# (search embeds locally), but the pipeline modules read it at import.
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [[ "${1:-}" == "--dev" ]]; then
  (cd web && npm run dev -- --port 5173 --strictPort) &
  trap 'kill 0' EXIT
  echo "✓ Vite dev server (HMR)  → http://localhost:5173"
fi

echo
echo "  EVERY ANGLE  →  http://localhost:${PORT}"
echo
exec ./.venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port "${PORT}"
