#!/usr/bin/env sh
set -e
if [ -f "alembic.ini" ]; then
  alembic upgrade head || { echo "Alembic migrate failed"; exit 1; }
fi
exec uvicorn app.web_ui:app --host 0.0.0.0 --port "${PORT}"