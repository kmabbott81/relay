#!/usr/bin/env sh
set -e
PORT="${PORT:-8000}"
export RELAY_ENV="${RELAY_ENV:-production}"
exec python -m uvicorn relay_ai.platform.api.mvp:app --host 0.0.0.0 --port "$PORT"
