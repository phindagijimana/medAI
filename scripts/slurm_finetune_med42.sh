#!/bin/bash
#SBATCH --job-name=medai-lora
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/medai_lora_%j.out
#SBATCH --error=logs/medai_lora_%j.err
#
# Submit:  sbatch [--export=ALL,BASE_MODEL=deepseek,CORPUS=both] \
#              scripts/slurm_finetune_med42.sh
#
# LoRA fine-tune Med42-8B (or DeepSeek-R1-Distill-Llama-8B) on MedAI-EPI
# (prompt, target_phenotype) pairs. Adapter lands in
# checkpoints/{model_slug}_lora_epi/.
#
# Env knobs (both optional, both default shown):
#   BASE_MODEL=med42            # or deepseek, or any HF id
#   CORPUS=pilot                # or synth-v1, or both

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI: LoRA fine-tune Med42-8B on pilot pairs"
echo "=================================================="
echo "Job ID:  ${SLURM_JOB_ID:-local}"
echo "Node:    ${SLURM_NODELIST:-$(hostname)}"
echo "Started: $(date)"
echo "=================================================="

module load python 2>/dev/null || module load python/3.10 2>/dev/null || echo "python module not loadable"
module load cuda   2>/dev/null || module load cuda/12.2  2>/dev/null || echo "cuda module not loadable"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ -f "$_SUBMIT_DIR/.env" ]; then
    set -a; . "$_SUBMIT_DIR/.env"; set +a
fi
export APP_HOME="$_SUBMIT_DIR"
PY="$APP_HOME/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv Python not executable at $PY" >&2; exit 1
fi
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    # `| head` under pipefail can trip SIGPIPE; use --query for a clean exit.
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
fi

cd "$APP_HOME"
BASE_MODEL="${BASE_MODEL:-med42}"
CORPUS="${CORPUS:-pilot}"
echo ""
echo "--- Running LoRA fine-tune (base=$BASE_MODEL corpus=$CORPUS) ---"
$PY scripts/finetune_lora_epi.py --base-model "$BASE_MODEL" --corpus "$CORPUS"

echo ""
echo "Finished: $(date)"
