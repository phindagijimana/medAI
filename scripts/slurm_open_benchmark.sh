#!/bin/bash
#SBATCH --job-name=medai-epi-open
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/medai_epi_open_%j.out
#SBATCH --error=logs/medai_epi_open_%j.err
#
# Submit with:
#   sbatch scripts/slurm_open_benchmark.sh
#
# Fills the placeholder Tables 5-8 in paper_doc/MedAI_EPI_Manuscript_v0.1.md.
# Runs Med42-8B M0/M1/M2 across all 200 Fonferko-Shadrach clinic letters
# for clinical_seizure and medication modules. Deterministic decoding.
# Manifests written to data/run_manifests/<date>/ — the same directory the
# eval aggregator reads.
#
# Estimated compute: ~5-10 h wall clock. --time set to 12 h with headroom.

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI Open Benchmark — full Fonferko sweep"
echo "=================================================="
echo "Job ID:  ${SLURM_JOB_ID:-local}"
echo "Node:    ${SLURM_NODELIST:-$(hostname)}"
echo "GPUs:    ${SLURM_JOB_GPUS:-N/A}"
echo "CPUs:    ${SLURM_CPUS_PER_TASK:-N/A}"
echo "Started: $(date)"
echo "=================================================="

# Modules (best-effort, matching slurm_job.sh conventions)
module load python 2>/dev/null || module load python/3.10 2>/dev/null || echo "python module not loadable"
module load gcc    2>/dev/null || module load gcc/11.2   2>/dev/null || echo "gcc module not loadable"
module load cuda   2>/dev/null || module load cuda/12.2  2>/dev/null || echo "cuda module not loadable"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

# NOTE: source .env BEFORE setting APP_HOME — the .env file contains APP_HOME=
# (empty placeholder) which will overwrite the export otherwise.
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ -f "$_SUBMIT_DIR/.env" ]; then
    echo "Sourcing $_SUBMIT_DIR/.env"
    set -a; . "$_SUBMIT_DIR/.env"; set +a
fi
# Now set APP_HOME authoritatively (overriding whatever .env said)
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
# Ensure Python does NOT fall back to user-site-packages for missing deps
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi | head -20
fi

cd "$APP_HOME"

# ---- Run ----
# Full sweep: 200 letters × 3 arms × 2 modules = 1200 inferences.
# Resumable: on rerun, already-completed (doc, arm, module, version) tuples
# are skipped by inspecting existing manifests.

echo ""
echo "--- Full Fonferko sweep: M0/M1/M2 × clinical_seizure + medication ---"
$PY scripts/run_open_benchmark_gpu.py \
    --arms M0,M1,M2 \
    --modules clinical_seizure,medication \
    --prompt-version v1

echo ""
echo "Finished: $(date)"
echo "Manifests: data/run_manifests/$(date -u +%Y-%m-%d)/"
echo ""
echo "Next step to fill manuscript tables 5-8:"
echo "    python -m eval.aggregator_cli \\"
echo "        --manifests data/run_manifests \\"
echo "        --gold data/fonferko_shadrach_2024/silver_labels_v0_2_1 \\"
echo "        --out eval/results/open_benchmark_gpu_summary.json"
