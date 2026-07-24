# Vednix AI — backend image
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# install deps first (layer caching: requirements change less often than code)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data dir (SQLite + uploads) — mount a volume at /app/data to persist
ENV VEDNIX_HOST=0.0.0.0 \
    VEDNIX_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
