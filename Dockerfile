# Dockerfileï¼ˆFastAPI + Uvicornï¼Œé©??Zeaburï¼?
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ?¥å£?³æœ¬ï¼ˆå¯??Alembicï¼?
RUN chmod +x ./entrypoint.sh

# Zeabur ?ƒæ³¨??PORTï¼Œå?å¿…ç›£?½å?
# https://zeabur.com/docs/en-US/deploy/variables
ENV PORT=8080

CMD ["./entrypoint.sh"]

