#!/bin/sh
# Cloud/container entrypoint. Runtime configuration is supplied exclusively by
# environment variables; no local .env or dataset is baked into the image.
set -eu

# This entrypoint is the production container contract. Defaulting APP_ENV here
# makes the Settings validator reject an accidental AUTH_ENABLED=false Railway
# deployment even when the platform variable was omitted.
APP_ENV="${APP_ENV:-production}"
export APP_ENV

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    python -m alembic upgrade head
else
    # Fail before serving traffic when credentials are invalid or a shared
    # database has not received the committed migrations yet.
    python -m alembic current --check-heads
fi

exec uvicorn src.main:app \
    --host "${APP_HOST:-0.0.0.0}" \
    --port "${PORT:-${APP_PORT:-8000}}" \
    --proxy-headers \
    --forwarded-allow-ips="*"
