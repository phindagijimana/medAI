#!/bin/bash
#SBATCH --job-name=metacat-train
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=06:00:00
#SBATCH --output=logs/metacat_train_%j.out
#SBATCH --error=logs/metacat_train_%j.err
#
# Train MetaCAT classifiers (Presence, Experiencer, Temporality, Certainty)
# on the silver export from scripts/emit_metacat_silver.py.
#
# Prerequisites (must exist before submit):
#   data/metacat_training/silver.json  — from emit_metacat_silver.py
#
# Submit:
#   sbatch scripts/slurm_train_metacat.sh
#
# Env overrides:
#   EXPORT=data/metacat_training/silver.json  (default)
#   TOKENIZER=emilyalsentzer/Bio_ClinicalBERT (default)
#   TASKS=Presence,Experiencer,Temporality,Certainty (default)
#   EPOCHS=5

set -euo pipefail

echo "=================================================="
echo "MetaCAT training (4 tasks × BERT-family classifier)"
echo "Job ID:  ${SLURM_JOB_ID:-local}"
echo "Node:    ${SLURM_NODELIST:-$(hostname)}"
echo "Started: $(date)"
echo "=================================================="

module load python 2>/dev/null || module load python/3.10 2>/dev/null || true
module load cuda   2>/dev/null || module load cuda/12.2  2>/dev/null || true

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ -f "$_SUBMIT_DIR/.env" ]; then
    set -a; . "$_SUBMIT_DIR/.env"; set +a
fi
export APP_HOME="$_SUBMIT_DIR"
PY="$APP_HOME/venv-medcat/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv-medcat Python not executable at $PY" >&2
    exit 1
fi
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
fi

cd "$APP_HOME"

EXPORT="${EXPORT:-data/metacat_training/silver.json}"
TOKENIZER="${TOKENIZER:-emilyalsentzer/Bio_ClinicalBERT}"
TASKS="${TASKS:-Presence,Experiencer,Temporality,Certainty}"
EPOCHS="${EPOCHS:-5}"
OUT_DIR="checkpoints/metacat"

if [ ! -f "$EXPORT" ]; then
    echo "ERROR: silver export not found at $EXPORT" >&2
    echo "       Run scripts/emit_metacat_silver.py first." >&2
    exit 2
fi

echo ""
echo "--- Training MetaCAT (tokenizer=$TOKENIZER  tasks=$TASKS  epochs=$EPOCHS) ---"
$PY scripts/train_metacat.py \
    --training-export "$EXPORT" \
    --out-dir "$OUT_DIR" \
    --tokenizer-model "$TOKENIZER" \
    --tasks "$TASKS" \
    --epochs "$EPOCHS"

echo ""
echo "Finished: $(date)"
