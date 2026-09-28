#!/bin/bash
#SBATCH --job-name=medai-fs-test
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --output=logs/medai_fs_test_%j.out
#SBATCH --error=logs/medai_fs_test_%j.err
#
# Runs Med42-8B M0/M1/M2 over the 40 held-out F-S clinician letters
# (EA0161..EA0200, reserved by _fs_pairs_train_test(seed=0)).
#
# One script covers all three configs; select via env vars at submit time:
#
#   BASE (no adapter, no constrained):
#     sbatch --export=ALL scripts/slurm_med42_fs_test.sh
#
#   TUNED_V3 (v3 F-S-split adapter, no constrained):
#     sbatch --export=ALL,MEDAI_LORA_ADAPTER_DIR=$(pwd)/checkpoints/llama3-med42-8b_lora_epi_v3_fssplit \
#            scripts/slurm_med42_fs_test.sh
#
#   TUNED_V3 + CONSTRAINED:
#     sbatch --export=ALL,MEDAI_LORA_ADAPTER_DIR=$(pwd)/checkpoints/llama3-med42-8b_lora_epi_v3_fssplit,MEDAI_CONSTRAINED=1 \
#            scripts/slurm_med42_fs_test.sh
#
# Manifest tree is auto-picked by config:
#   base            → data/run_manifests_fs_test_base/
#   v3              → data/run_manifests_fs_test_tuned_v3/
#   v3+constrained  → data/run_manifests_fs_test_tuned_v3_constr/

set -euo pipefail

# Raise max_new_tokens for tuned runs — the adapter emits the full
# EpilepsyPhenotype JSON (see docs/DATA_QUALITY_AUDIT.md §E "prompt-
# template drift"), and truncation at 1024 breaks smart_repair.
export MEDAI_MAX_NEW_TOKENS="${MEDAI_MAX_NEW_TOKENS:-4096}"

echo "=================================================="
echo "MedAI-EPI: Med42-8B on 40 held-out F-S letters"
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

# ---- Config selection ------------------------------------------------------
# MEDAI_LORA_ADAPTER_DIR is set (or not) by the submitter. Empty string or
# unset → base model. MEDAI_CONSTRAINED=1 activates lm-format-enforcer.
ADAPTER="${MEDAI_LORA_ADAPTER_DIR:-}"
CONSTR="${MEDAI_CONSTRAINED:-}"

# Decide the manifest tree from the config (once, upfront) so scoring
# scripts can find the right run.
if [ -n "$ADAPTER" ] && [ -n "$CONSTR" ]; then
    CFG_TAG="tuned_v3_constr"
elif [ -n "$ADAPTER" ]; then
    CFG_TAG="tuned_v3"
elif [ -n "$CONSTR" ]; then
    CFG_TAG="base_constr"
else
    CFG_TAG="base"
fi
export MEDAI_MANIFEST_DIR="${MEDAI_MANIFEST_DIR:-$APP_HOME/data/run_manifests_fs_test_${CFG_TAG}}"

echo "Config tag        : $CFG_TAG"
echo "Adapter           : ${ADAPTER:-<none, base model>}"
echo "Constrained       : ${CONSTR:-<off>}"
echo "Manifest dir      : $MEDAI_MANIFEST_DIR"
echo "Max new tokens    : $MEDAI_MAX_NEW_TOKENS"

if [ -n "$ADAPTER" ] && [ ! -d "$ADAPTER" ]; then
    echo "ERROR: MEDAI_LORA_ADAPTER_DIR does not exist: $ADAPTER" >&2
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
echo "--- Running Med42-8B on 40 held-out F-S letters ($CFG_TAG) ---"
$PY scripts/run_med42_on_fs_test.py

echo ""
echo "Finished: $(date)"
echo ""
echo "Score with:"
echo "  $PY scripts/score_llm_arms_vs_fs_gold.py \\"
echo "      --manifests-dir $MEDAI_MANIFEST_DIR \\"
echo "      --held-out-only \\"
echo "      --suffix ${CFG_TAG}_fs_test"
