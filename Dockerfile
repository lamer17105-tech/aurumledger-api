# Dockerfile（FastAPI + Uvicorn，適用 Zeabur）
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 入口腳本（可選 Alembic）
RUN chmod +x ./entrypoint.sh

# Zeabur 會注入 PORT，務必監聽它
# https://zeabur.com/docs/en-US/deploy/variables
ENV PORT=8080

CMD ["./entrypoint.sh"]
