#!/usr/bin/env bash
# Med42 Production Deployment on HPC via Slurm + OOD (Patched)
#
# Submit with: sbatch med42_service.slurm

#SBATCH --job-name=med42_service
#SBATCH --output=med42_service_%j.out
#SBATCH --error=med42_service_%j.err
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=168:00:00         # 7 days
#SBATCH --mem=64G
#SBATCH --partition=general
#SBATCH --gres=gpu:1             # remove or change if you want CPU-only

set -euo pipefail

#############################
# CONFIG                    #
#############################
export SERVICE_PORT="${SERVICE_PORT:-8081}"
export SERVICE_HOST="${SERVICE_HOST:-0.0.0.0}"
# Do not set CUDA_VISIBLE_DEVICES to empty — that hides GPUs and forces CPU-only PyTorch.
# With #SBATCH --gres=gpu:1, Slurm usually sets CUDA_VISIBLE_DEVICES to the allocated GPU(s).
export USE_RAG="${USE_RAG:-1}"
export USE_FEW_SHOT="${USE_FEW_SHOT:-1}"
export MAX_CONCURRENT_USERS="${MAX_CONCURRENT_USERS:-10}"

# Source .env from the submission directory so HF_TOKEN, SECRET_KEY, etc. reach
# the gated model download and the pre-gunicorn smoke test. app.py also calls
# load_dotenv() at import — this is the belt-and-suspenders pass.
_ENV_FILE="${SLURM_SUBMIT_DIR:-$HOME/med42_service}/.env"
if [[ -f "$_ENV_FILE" ]]; then
  echo "[*] Sourcing $_ENV_FILE"
  set -a; . "$_ENV_FILE"; set +a
fi

# Correct OOD hostname for your site
export OOD_HOSTNAME="${OOD_HOSTNAME:-ood.urmc-sh.rochester.edu}"

# Paths
export APP_HOME="$HOME/med42_service"
export VENV_DIR="$APP_HOME/venv"
export UPLOAD_DIR="$APP_HOME/uploads"
export SERVICE_LOG_DIR="$APP_HOME/logs"

# Hugging Face & Torch caches
export HF_HOME="$HOME/.cache/huggingface"
export TORCH_HOME="$HOME/.cache/torch"

# Model settings
export MODEL_NAME="${MODEL_NAME:-m42-health/Llama3-Med42-8B}"

#############################
# ENV & DIRS                #
#############################
echo "[*] Creating directories..."
mkdir -p "$APP_HOME" "$VENV_DIR" "$UPLOAD_DIR" "$SERVICE_LOG_DIR"

echo "[*] Virtualenv..."
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
python -V

#############################
# DEPENDENCIES              #
#############################
echo "[*] Installing core deps..."
python -m pip install --upgrade pip
pip install "flask>=3.1" "flask-cors>=6.0" "gunicorn>=22" "pandas>=2.2" "numpy>=1.26"
pip install openpyxl xlrd PyPDF2 python-docx python-multipart
pip install "accelerate>=0.33" "transformers>=4.44" "safetensors>=0.4"

# Detect GPU presence
HAS_GPU=false
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then
  HAS_GPU=true
  echo "[*] GPU detected"
fi

echo "[*] Installing torch (${HAS_GPU:+GPU}${HAS_GPU:-CPU})..."
if $HAS_GPU; then
  # Adjust if your cluster exposes a different CUDA toolkit
  pip install --index-url https://download.pytorch.org/whl/cu118 torch torchvision torchaudio
else
  pip install --index-url https://download.pytorch.org/whl/cpu torch
fi

#############################
# APPLICATION FILES         #
#############################
echo "[*] Using existing app.py file with HTML frontend..."

# Check if app.py exists (should be accessible on shared filesystem)
if [[ -f "$APP_HOME/app.py" ]]; then
    echo "[*] App file exists: $(ls -la $APP_HOME/app.py)"
    echo "[*] UI_HTML template present: $(grep -c 'UI_HTML' $APP_HOME/app.py) lines"
else
    echo "[*] ERROR: app.py not found in $APP_HOME"
    echo "[*] SLURM_SUBMIT_DIR: $SLURM_SUBMIT_DIR"
    exit 1
fi

echo "[*] Using existing gunicorn_config.py..."

#############################
# ACCESS URLS               #
#############################
NODE_SHORT="$(hostname -s 2>/dev/null || echo unknown-node)"
URL_FILE="$SERVICE_LOG_DIR/ACCESS_URLS.txt"
mkdir -p "$SERVICE_LOG_DIR"

{
  echo "========================================="
  echo "Med42 Service Access Information"
  echo "Node:      $NODE_SHORT"
  echo "OOD Host:  $OOD_HOSTNAME"
  echo "Port:      $SERVICE_PORT"
  echo "Started:   $(date)"
  echo "-----------------------------------------"
  echo "Direct:    http://$NODE_SHORT:$SERVICE_PORT/"
  echo "OOD rnode: https://$OOD_HOSTNAME/rnode/$NODE_SHORT/$SERVICE_PORT/"
  echo "Health:    https://$OOD_HOSTNAME/rnode/$NODE_SHORT/$SERVICE_PORT/health"
  echo "========================================="
} | tee "$URL_FILE"

#############################
# START SERVICE             #
#############################
cd "$APP_HOME"
echo "[*] Checking environment..."
echo "[*] Current directory: $(pwd)"
echo "[*] Python path: $(which python)"
echo "[*] GPU available: $(nvidia-smi -L 2>/dev/null | wc -l) GPU(s)"
echo "[*] CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
echo "[*] USE_RAG=$USE_RAG USE_FEW_SHOT=$USE_FEW_SHOT"
echo "[*] HF_TOKEN: $([[ -n "${HF_TOKEN:-}" ]] && echo set || echo MISSING)"
echo "[*] Optional: verify stack with: python3 scripts/test_gpu_rag_fewshot.py"

# Test the app before starting gunicorn
echo "[*] Testing app..."
python -c "
from app import app
print('App import successful')
with app.test_client() as client:
    resp = client.get('/health')
    print('Health check:', resp.status_code)
"

echo "[*] Starting Gunicorn on port $SERVICE_PORT..."
gunicorn -c gunicorn_config.py app:app &
GUNICORN_PID=$!
echo "[*] Gunicorn started with PID: $GUNICORN_PID"

# Give gunicorn time to start
sleep 5

# Check if gunicorn is still running
if kill -0 $GUNICORN_PID 2>/dev/null; then
    echo "[*] Gunicorn is running successfully"
    echo "[*] Service is running. Job will continue for 7 days or until cancelled."
    echo "[*] Monitor with: squeue -u $USER"

    # Keep the job alive by monitoring gunicorn
    while kill -0 $GUNICORN_PID 2>/dev/null; do
        sleep 60
    done
    echo "[*] Gunicorn process ended"
else
    echo "[*] ERROR: Gunicorn failed to start"
    exit 1
fi
