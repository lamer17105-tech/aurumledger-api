FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Âª∫Á??õÊì¨?∞Â?‰∏¶Â?Ë£ùÂ?‰ª∂Ô?‰∏çÂ???root ?ÑÂÖ®??pipÔº?
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:${PATH}"

# Ë§áË£ΩÁ®ãÂ?Á¢?
COPY . .
RUN chmod +x ./entrypoint.sh

# Âª∫Á???root ‰ΩøÁî®?Ö‰∏¶?çÊ??∑Ë?
RUN adduser --disabled-password --gecos '' appuser \
 && chown -R appuser /app
USER appuser

ENV PORT=8080
CMD ["./entrypoint.sh"]
