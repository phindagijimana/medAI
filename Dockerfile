# MedAI-EPI — research phenotyping assistant (Flask service, CPU-friendly image).
#
# This image builds the /extract Flask surface. It runs the extraction pipeline
# and its offline components (schema validation, smart_repair, chunker, merger,
# tabular flatten, /extract/csv, /extract/chat, /extract/ui). Med42-8B inference
# requires a GPU — use `Dockerfile.gpu` for that. This CPU image is fine for:
#   - unit / smoke tests (scripts/smoke_e2e_http.py runs against a mock backend)
#   - scoring reproducibility (Dockerfile.eval is the leaner target for that)
#   - development against a remote GPU inference server
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/logs /app/uploads /app/data/run_manifests

ENV SERVICE_HOST=0.0.0.0 \
    SERVICE_PORT=8085

EXPOSE 8085

# Single worker + threads: one model copy (see gunicorn_config.py).
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
