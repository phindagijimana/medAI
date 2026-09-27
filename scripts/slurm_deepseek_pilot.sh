#!/bin/bash
#SBATCH --job-name=medai-pilot-deepseek
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --output=logs/medai_pilot_deepseek_%j.out
#SBATCH --error=logs/medai_pilot_deepseek_%j.err
#SBATCH --dependency=afterok:143696
#
# Submit (queued behind the R4c LoRA fine-tune job 143696):
#     sbatch scripts/slurm_deepseek_pilot.sh
#
# Runs DeepSeek-R1-Distill-Llama-8B M0/M1/M2 on the 60 pilot documents.
# Manifests: data/run_manifests_pilot_deepseek/<date>/
#
# Follow-up scoring:
#     python scripts/score_med42_on_pilot.py \
#         --manifests-dir data/run_manifests_pilot_deepseek \
#         --suffix deepseek

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI: DeepSeek-8B M0/M1/M2 on pilot corpus"
echo "=================================================="
echo "Job ID:  ${SLURM_JOB_ID:-local}"
echo "Node:    ${SLURM_NODELIST:-$(hostname)}"
echo "GPUs:    ${SLURM_JOB_GPUS:-N/A}"
echo "Started: $(date)"
echo "=================================================="

module load python 2>/dev/null || module load python/3.10 2>/dev/null || echo "python module not loadable"
module load gcc    2>/dev/null || module load gcc/11.2   2>/dev/null || echo "gcc module not loadable"
module load cuda   2>/dev/null || module load cuda/12.2  2>/dev/null || echo "cuda module not loadable"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ -f "$_SUBMIT_DIR/.env" ]; then
    echo "Sourcing $_SUBMIT_DIR/.env"
    set -a; . "$_SUBMIT_DIR/.env"; set +a
fi
export APP_HOME="$_SUBMIT_DIR"

export MEDAI_MANIFEST_DIR="$APP_HOME/data/run_manifests_pilot_deepseek"

PY="$APP_HOME/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv Python not executable at $PY" >&2
    exit 1
fi
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi | head -20
fi

cd "$APP_HOME"

echo ""
echo "--- Running DeepSeek-8B M0/M1/M2 on 60 pilot documents ---"
$PY scripts/run_deepseek_on_pilot.py

echo ""
echo "Finished: $(date)"
echo "Manifests: $MEDAI_MANIFEST_DIR/$(date -u +%Y-%m-%d)/"
echo ""
echo "Follow-up scoring:"
echo "    $PY scripts/score_med42_on_pilot.py --manifests-dir $MEDAI_MANIFEST_DIR --suffix deepseek"
