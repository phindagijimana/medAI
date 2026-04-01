# Self-hosting med42_service

## CLI (recommended)

From the repository root:

```bash
chmod +x vecta vecta-hpc    # once
./vecta install              # pip install -r requirements.txt (uses --user unless venv / VECTA_PIP_USER=0)
./vecta start                # Gunicorn in background (writes vecta_ai.pid)
./vecta start -f             # Flask dev server only (foreground)
./vecta stop | ./vecta status | ./vecta logs
```

HPC (SLURM): `./vecta-hpc install` then `./vecta-hpc run gpu` or `run cpu`.

## Manual install

1. Python 3.10+ recommended (3.11 matches Docker).
2. Create a virtual environment and install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set at least **`SECRET_KEY`** (long random string). For gated Hugging Face models, set **`HF_TOKEN`**.

4. Run with the **development** server (local testing only):

   ```bash
   python app.py
   ```

   Or: `python app.py --host 127.0.0.1 --port 8085`

5. Run with **Gunicorn** (production-style), or use **`./vecta start`** which does this for you:

   ```bash
   export SERVICE_PORT=8085
   gunicorn -c gunicorn_config.py app:app
   ```

   Keep **`GUNICORN_WORKERS=1`** unless you intend to run multiple model processes (each worker loads a full model).

## Configuration

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` / `FLASK_SECRET_KEY` | Stable session signing; set in production |
| `CORS_ORIGINS` | Comma-separated allowed origins; empty = permissive (dev) |
| `MODEL_NAME` | Hugging Face model id |
| `HF_TOKEN` | Hugging Face token if required |
| `SERVICE_HOST`, `SERVICE_PORT` | Listen address and port |
| `GUNICORN_TIMEOUT` | Default 600s for slow inference |
| `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT` | Log rotation |

See `.env.example` for more.

## Docker

```bash
cp .env.example .env
# edit .env — set SECRET_KEY, optional HF_TOKEN
docker compose build
docker compose up -d
```

The image installs dependencies from `requirements.txt` (including PyTorch) and is large. For **GPU** hosts, replace the base image with a CUDA-enabled image and install the matching PyTorch CUDA build from [pytorch.org](https://pytorch.org/get-started/locally/).

## Reverse proxy

Put nginx, Caddy, or Traefik in front for TLS, client body size, and long read timeouts that match `GUNICORN_TIMEOUT`.

## SLURM

`scripts/med42_service.slurm` expects `gunicorn_config.py` in the app directory (included in this repo).
