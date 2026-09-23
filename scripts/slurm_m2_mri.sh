#!/bin/bash
#SBATCH --job-name=medai-epi-m2
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=00:45:00
#SBATCH --output=logs/medai_epi_m2_%j.out
#SBATCH --error=logs/medai_epi_m2_%j.err
#
# Submit with:  sbatch scripts/slurm_m2_mri.sh
#
# Runs M0/M1/M2 MRI extraction on real Med42-8B and writes manifests to
# data/run_manifests/<date>/. Extends the existing slurm_job.sh convention
# but for a short single-inference sweep, not the full Flask service.

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI M0/M1/M2 MRI Extraction Run"
echo "=================================================="
echo "Job ID: ${SLURM_JOB_ID:-local}"
echo "Node:   ${SLURM_NODELIST:-$(hostname)}"
echo "GPUs:   ${SLURM_JOB_GPUS:-N/A}"
echo "CPUs:   ${SLURM_CPUS_PER_TASK:-N/A}"
echo "Started: $(date)"
echo "=================================================="

# Modules (best-effort, matching slurm_job.sh conventions)
module load python 2>/dev/null || module load python/3.10 2>/dev/null || echo "python module not loadable"
module load gcc    2>/dev/null || module load gcc/11.2   2>/dev/null || echo "gcc module not loadable"
module load cuda   2>/dev/null || module load cuda/12.2  2>/dev/null || echo "cuda module not loadable"

# Environment
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

# NOTE: source .env BEFORE setting APP_HOME — .env contains APP_HOME= (empty
# placeholder) which will overwrite the export otherwise.
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ -f "$_SUBMIT_DIR/.env" ]; then
    echo "Sourcing $_SUBMIT_DIR/.env"
    set -a; . "$_SUBMIT_DIR/.env"; set +a
fi
export APP_HOME="$_SUBMIT_DIR"

# Use venv Python explicitly — plain `python` was resolving to system 3.9 +
# user .local site-packages which have a mismatched pydantic-stack.
PY="$APP_HOME/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv Python not executable at $PY" >&2
    exit 1
fi
echo "Using Python at: $PY"
$PY --version
export PYTHONNOUSERSITE=1

# nvidia-smi for the log
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi | head -20
fi

cd "$APP_HOME"

# ---- Run ----
# Default: synthetic MRI report first (baseline sanity), then one PMC excerpt
echo ""
echo "--- Run 1: synthetic MRI report ---"
$PY scripts/run_m2_mri_real.py

echo ""
echo "--- Run 2: PMC6872800 (MTLE + right HS) MRI excerpt ---"
$PY scripts/run_m2_mri_real.py --pmc PMC6872800

echo ""
echo "Finished: $(date)"
echo "Manifests: data/run_manifests/$(date -u +%Y-%m-%d)/"
