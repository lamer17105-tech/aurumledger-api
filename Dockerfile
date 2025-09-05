FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run 會提供環境變數 PORT，外部走 443/80，內部容器綁這個 PORT
ENV PORT=8000
EXPOSE 8000
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "${PORT}"]
