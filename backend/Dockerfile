FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    KADR_DATA_DIR=/data \
    KADR_DOWNLOADS_DIR=/downloads

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir -r requirements-runtime.txt \
    && playwright install --with-deps chromium

COPY backend/ ./backend/

RUN mkdir -p /data /downloads

WORKDIR /app/backend

EXPOSE 8765

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"]
