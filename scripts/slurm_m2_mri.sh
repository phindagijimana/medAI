#!/bin/bash
#SBATCH --job-name=medai-epi-m2
#SBATCH --partition=general
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
export APP_HOME="${SLURM_SUBMIT_DIR:-$(pwd)}"

# .env for HF_TOKEN (Med42 weights are gated) — same pattern as slurm_job.sh
if [ -f "$APP_HOME/.env" ]; then
    echo "Sourcing $APP_HOME/.env"
    set -a; . "$APP_HOME/.env"; set +a
fi
if [ -z "${HF_TOKEN:-}" ]; then
    echo "WARNING: HF_TOKEN not set — Med42 download may fail" >&2
fi

# Activate venv if present
if [ -f "$APP_HOME/venv/bin/activate" ]; then
    echo "Activating venv"
    # shellcheck disable=SC1091
    . "$APP_HOME/venv/bin/activate"
fi

# nvidia-smi for the log
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi | head -20
fi

cd "$APP_HOME"

# ---- Run ----
# Default: synthetic MRI report first (baseline sanity), then one PMC excerpt
echo ""
echo "--- Run 1: synthetic MRI report ---"
python scripts/run_m2_mri_real.py

echo ""
echo "--- Run 2: PMC6872800 (MTLE + right HS) MRI excerpt ---"
python scripts/run_m2_mri_real.py --pmc PMC6872800

echo ""
echo "Finished: $(date)"
echo "Manifests: data/run_manifests/$(date -u +%Y-%m-%d)/"
