"""
Gunicorn configuration for med42_service.

Use a single worker for the LLM (each worker loads its own model copy).
Override via environment variables.
"""
import os

_bind_host = os.environ.get("SERVICE_HOST", "0.0.0.0")
_bind_port = os.environ.get("SERVICE_PORT", "8085")
bind = os.environ.get("GUNICORN_BIND", f"{_bind_host}:{_bind_port}")

# One worker = one model in memory. Increase only if you run multiple model processes intentionally.
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"
worker_connections = int(os.environ.get("GUNICORN_WORKER_CONNECTIONS", "1000"))

# Long timeouts for large-model inference (especially CPU).
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "600"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "120"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))

max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "0"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "50"))

preload_app = os.environ.get("GUNICORN_PRELOAD_APP", "").lower() in ("1", "true", "yes")

accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info").lower()
capture_output = True

# Limit request line / header sizes (bytes)
limit_request_line = int(os.environ.get("GUNICORN_LIMIT_REQUEST_LINE", "8190"))
limit_request_fields = int(os.environ.get("GUNICORN_LIMIT_REQUEST_FIELDS", "100"))
limit_request_field_size = int(os.environ.get("GUNICORN_LIMIT_REQUEST_FIELD_SIZE", "8190"))
