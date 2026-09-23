#!/bin/bash
#SBATCH --job-name=medai-epi-open-4096
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/medai_epi_open_4096_%j.out
#SBATCH --error=logs/medai_epi_open_4096_%j.err
#
# Sensitivity variant of scripts/slurm_open_benchmark.sh:
#   - max_new_tokens=4096 (up from 1024 baseline)
#   - manifests go to data/run_manifests_maxtok4096/ (separate dir so they
#     don't collide with the baseline run)
#
# Rationale: baseline run (SLURM 89472, max_new_tokens=1024) exhibited a
# schema-echo pathology where M2 responses saturated the 1024-token budget
# reproducing the injected schema and produced no extraction content. This
# rerun tests whether a larger generation budget resolves the pathology
# (token-budget bound) or whether the failure is model-scale bound
# (Med42-8B ceiling).
#
# Submit with:
#   sbatch scripts/slurm_open_benchmark_4096.sh

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI Open Benchmark — max_new_tokens=4096 sensitivity"
echo "=================================================="
echo "Job ID:  ${SLURM_JOB_ID:-local}"
echo "Node:    ${SLURM_NODELIST:-$(hostname)}"
echo "GPUs:    ${SLURM_JOB_GPUS:-N/A}"
echo "CPUs:    ${SLURM_CPUS_PER_TASK:-N/A}"
echo "Started: $(date)"
echo "=================================================="

module load python 2>/dev/null || module load python/3.10 2>/dev/null || echo "python module not loadable"
module load gcc    2>/dev/null || module load gcc/11.2   2>/dev/null || echo "gcc module not loadable"
module load cuda   2>/dev/null || module load cuda/12.2  2>/dev/null || echo "cuda module not loadable"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

# .env is sourced BEFORE setting APP_HOME — .env has an empty APP_HOME= that
# would otherwise override.
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ -f "$_SUBMIT_DIR/.env" ]; then
    echo "Sourcing $_SUBMIT_DIR/.env"
    set -a; . "$_SUBMIT_DIR/.env"; set +a
fi
export APP_HOME="$_SUBMIT_DIR"

# Write manifests to a distinct directory so this run does not collide with
# the baseline 1024-token run.
export MEDAI_MANIFEST_DIR="$APP_HOME/data/run_manifests_maxtok4096"
mkdir -p "$MEDAI_MANIFEST_DIR"
echo "MEDAI_MANIFEST_DIR=$MEDAI_MANIFEST_DIR"

# Use venv Python explicitly + block user-site-packages fallback
PY="$APP_HOME/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv Python not executable at $PY" >&2
    exit 1
fi
echo "Using Python at: $PY"
$PY --version
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi | head -20
fi

cd "$APP_HOME"

# 200 letters × 3 arms × 2 modules = 1200 inferences at max_new_tokens=4096.
# Estimated wall-clock: ~10-12 h.
echo ""
echo "--- Sensitivity sweep: max_new_tokens=4096 ---"
$PY scripts/run_open_benchmark_gpu.py \
    --arms M0,M1,M2 \
    --modules clinical_seizure,medication \
    --prompt-version v1 \
    --max-new-tokens 4096

echo ""
echo "Finished: $(date)"
echo "Manifests: $MEDAI_MANIFEST_DIR/"
echo ""
echo "Aggregate with:"
echo "    MEDAI_MANIFEST_DIR=$MEDAI_MANIFEST_DIR $PY -m eval.aggregator_cli \\"
echo "        --manifests $MEDAI_MANIFEST_DIR \\"
echo "        --gold data/fonferko_shadrach_2024/silver_labels_v0_2_1 \\"
echo "        --out eval/results/open_benchmark_4096_summary.json"
