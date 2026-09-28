#!/bin/bash
#SBATCH --job-name=medai-lora-fssplit
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/medai_lora_fssplit_%j.out
#SBATCH --error=logs/medai_lora_fssplit_%j.err
#
# Submit:
#     sbatch scripts/slurm_finetune_med42_fssplit.sh
# Chained after another job (e.g. 151965) to serialize GPU use:
#     sbatch --dependency=afterany:151965 scripts/slurm_finetune_med42_fssplit.sh
#
# Variant of scripts/slurm_finetune_med42.sh that trains on the
# F-S 80/20 held-out split. Adapter output lands at
#     checkpoints/llama3-med42-8b_lora_epi_v3_fssplit/
# The 40 held-out F-S patients (EA0161..EA0200) are NEVER seen at
# training time, so post-hoc evaluation via
# scripts/run_med42_on_fs_test.py is a genuine held-out test.

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI: LoRA fine-tune Med42-8B on synth+fs80"
echo "  (F-S 80/20 patient-level split; 40 pts held out)"
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
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
fi

cd "$APP_HOME"

BASE_MODEL="${BASE_MODEL:-med42}"
CORPUS="${CORPUS:-synth+fs80}"
SUFFIX="${MEDAI_LORA_ADAPTER_SUFFIX:-v3_fssplit}"

echo ""
echo "--- Running LoRA fine-tune (base=$BASE_MODEL corpus=$CORPUS suffix=$SUFFIX) ---"
echo "Adapter will land at checkpoints/llama3-med42-8b_lora_epi_${SUFFIX}/"

export MEDAI_LORA_ADAPTER_SUFFIX="$SUFFIX"
$PY scripts/finetune_lora_epi.py --base-model "$BASE_MODEL" --corpus "$CORPUS" --adapter-suffix "$SUFFIX"

echo ""
echo "Finished: $(date)"
