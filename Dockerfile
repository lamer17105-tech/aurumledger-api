# Dockerfile（FastAPI + Uvicorn，適??Zeabur�?
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ?�口?�本（可??Alembic�?
RUN chmod +x ./entrypoint.sh

# Zeabur ?�注??PORT，�?必監?��?
# https://zeabur.com/docs/en-US/deploy/variables
ENV PORT=8080

CMD ["./entrypoint.sh"]

