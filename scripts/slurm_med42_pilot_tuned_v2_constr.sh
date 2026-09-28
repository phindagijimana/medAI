#!/bin/bash
#SBATCH --job-name=medai-pilot-tunedv2-constr
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=05:00:00
#SBATCH --output=logs/medai_pilot_tunedv2_constr_%j.out
#SBATCH --error=logs/medai_pilot_tunedv2_constr_%j.err
#
# Submit (queues behind the plain v2 pilot extraction):
#     sbatch --dependency=afterany:<v2_jobid> scripts/slurm_med42_pilot_tuned_v2_constr.sh
#
# Runs the LoRA-v2 adapter + LMFE schema-constrained decoding over the
# 60 pilot documents. Manifests write to
# data/run_manifests_pilot_tuned_v2_constr/ so they do NOT collide with
# the unconstrained v2 run at data/run_manifests_pilot_tuned_v2/.
#
# Wall clock is 5h (vs 4h for unconstrained) because LMFE adds ~10-20 %
# overhead per generation step and the tuned model emits ~3500-char
# outputs.

set -euo pipefail

# Env knobs — both must be set for this variant:
export MEDAI_MAX_NEW_TOKENS=4096
export MEDAI_CONSTRAINED=1

echo "=================================================="
echo "MedAI-EPI: Med42-8B + LoRA v2 + CONSTRAINED on pilot"
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

export MEDAI_LORA_ADAPTER_DIR="${MEDAI_LORA_ADAPTER_DIR:-$APP_HOME/checkpoints/llama3-med42-8b_lora_epi_v2}"
export MEDAI_MANIFEST_DIR="${MEDAI_MANIFEST_DIR:-$APP_HOME/data/run_manifests_pilot_tuned_v2_constr}"

if [ ! -d "$MEDAI_LORA_ADAPTER_DIR" ]; then
    echo "ERROR: adapter dir does not exist: $MEDAI_LORA_ADAPTER_DIR" >&2
    exit 1
fi

PY="$APP_HOME/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv Python not executable at $PY" >&2
    exit 1
fi
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
fi

cd "$APP_HOME"

echo ""
echo "--- Med42-8B + LoRA v2 + LMFE-constrained on 60 pilot documents ---"
echo "Adapter:      $MEDAI_LORA_ADAPTER_DIR"
echo "Manifests:    $MEDAI_MANIFEST_DIR"
echo "Constrained:  $MEDAI_CONSTRAINED"
echo "Max new tok:  $MEDAI_MAX_NEW_TOKENS"
$PY scripts/run_med42_on_pilot.py

echo ""
echo "Finished: $(date)"
echo ""
echo "Score with:"
echo "  $PY scripts/score_med42_on_pilot.py --manifests-dir $MEDAI_MANIFEST_DIR --suffix tuned_v2_constr"
