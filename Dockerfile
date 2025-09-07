FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# 建�??�擬?��?並�?裝�?件�?不�???root ?�全??pip�?
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

# 複製程�?�?
COPY . .
RUN chmod +x ./entrypoint.sh

# 建�???root 使用?�並?��??��?
RUN adduser --disabled-password --gecos '' appuser \
 && chown -R appuser /app
USER appuser

ENV PORT=8080
CMD ["./entrypoint.sh"]
