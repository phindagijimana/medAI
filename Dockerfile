# Self-hosted med42_service (CPU-friendly base image; customize for CUDA if needed).
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Some dependencies (e.g. scientific stack) need a compiler; trim if you pre-build wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/logs /app/uploads /app/data

ENV SERVICE_HOST=0.0.0.0 \
    SERVICE_PORT=8085

EXPOSE 8085

# Single worker + threads: one model copy (see gunicorn_config.py).
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
