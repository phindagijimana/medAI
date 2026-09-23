#!/bin/bash
#SBATCH --job-name=medai-epi-b1
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=logs/medai_epi_b1_%j.out
#SBATCH --error=logs/medai_epi_b1_%j.err
#
# Submit with:
#   sbatch scripts/slurm_train_b1.sh
#
# Fine-tunes BioClinicalBERT for the epilepsy_type field on Fonferko-Shadrach
# silver labels. Fills manuscript Table 4 (B1 baseline). ~20 min compute,
# ~440 MB HF cache download on first run.

set -eu
# NOTE: intentionally NOT `set -o pipefail`. `nvidia-smi | head -N` can trigger
# SIGPIPE which pipefail treats as script-fatal. We want the pipe to close
# quietly and the script to continue.
set -x   # command tracing to help diagnose future failures

echo "=================================================="
echo "MedAI-EPI B1 BioClinicalBERT training"
echo "=================================================="
echo "Job ID:  ${SLURM_JOB_ID:-local}"
echo "Node:    ${SLURM_NODELIST:-$(hostname)}"
echo "GPUs:    ${SLURM_JOB_GPUS:-N/A}"
echo "Started: $(date)"
echo "=================================================="

module load python 2>/dev/null || module load python/3.10 2>/dev/null || echo "python module not loadable"
module load gcc    2>/dev/null || echo "gcc module not loadable"
module load cuda   2>/dev/null || echo "cuda module not loadable"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ -f "$_SUBMIT_DIR/.env" ]; then
    echo "Sourcing $_SUBMIT_DIR/.env"
    set -a; . "$_SUBMIT_DIR/.env"; set +a
fi
export APP_HOME="$_SUBMIT_DIR"

PY="$APP_HOME/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv Python not executable at $PY" >&2
    exit 1
fi
echo "Using Python at: $PY"
$PY --version
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi | head -12
fi

cd "$APP_HOME"
mkdir -p checkpoints

echo ""
echo "--- B1 training: epilepsy_type head on Fonferko silver labels ---"
$PY scripts/train_b1_epilepsy_type.py \
    --silver data/fonferko_shadrach_2024/silver_labels_v0_2_1 \
    --base emilyalsentzer/Bio_ClinicalBERT \
    --epochs 5 \
    --batch 16 \
    --out checkpoints/b1_epilepsy_type_v1

echo ""
echo "Finished: $(date)"
echo "Checkpoint at: checkpoints/b1_epilepsy_type_v1"
