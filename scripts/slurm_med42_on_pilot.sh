#!/bin/bash
#SBATCH --job-name=medai-pilot-med42
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --output=logs/medai_pilot_med42_%j.out
#SBATCH --error=logs/medai_pilot_med42_%j.err
#
# Submit:
#     sbatch scripts/slurm_med42_on_pilot.sh
#
# Runs Med42-8B M0/M1/M2 against the 60 Phase 6D.2 pilot documents
# (data/episynth_pilot/run_001/). 60 × 3 = 180 extractions across 2 modules
# = ~360 inferences. Wall clock ~30-90 min on L40S 24 GB.
#
# Manifests write to data/run_manifests_pilot/<date>/ so they do NOT collide
# with the F-S sweep at data/run_manifests/.
#
# Follow-up scoring:
#     python scripts/score_med42_on_pilot.py

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI: Med42-8B M0/M1/M2 on EpiSynth pilot"
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

# Route manifests to a dedicated dir — do NOT overwrite the F-S sweep.
export MEDAI_MANIFEST_DIR="$APP_HOME/data/run_manifests_pilot"

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
echo "--- Running Med42-8B M0/M1/M2 on 60 pilot documents ---"
$PY scripts/run_med42_on_pilot.py

echo ""
echo "Finished: $(date)"
echo "Manifests: $MEDAI_MANIFEST_DIR/$(date -u +%Y-%m-%d)/"
echo ""
echo "Follow-up scoring:"
echo "    $PY scripts/score_med42_on_pilot.py"
