#!/usr/bin/env sh
set -e
PORT="${PORT:-8000}"
export RELAY_ENV="${RELAY_ENV:-production}"

# Run database migrations if DATABASE_URL is set
if [ -n "$DATABASE_URL" ]; then
    echo "Running Alembic migrations..."
    python -m alembic upgrade head || echo "Migration failed or already up to date"
fi

exec python -m uvicorn relay_ai.platform.api.mvp:app --host 0.0.0.0 --port "$PORT"
