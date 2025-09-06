#!/usr/bin/env bash
set -e

# 若有 Alembic，先做遷移（沒有就會略過）
if [ -f "alembic.ini" ]; then
  alembic upgrade head || { echo "Alembic migrate failed"; exit 1; }
fi

# 你的 FastAPI 入口
exec uvicorn app.web_ui:app --host 0.0.0.0 --port "${PORT}"
