#!/bin/bash
#SBATCH --job-name=medai-flat-v2
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --output=logs/medai_flat_v2_%j.out
#SBATCH --error=logs/medai_flat_v2_%j.err
#
# Flat prompt v2 ("unknown" epilepsy type) with constrained decoding, arm L1C, on the held-out
# letters EA0161-EA0200.  Own manifest directory: the v1 runs stay as they are.  Resumable.

set -euo pipefail
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$_SUBMIT_DIR"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME="$_SUBMIT_DIR"
export PYTHONNOUSERSITE=1
unset MEDAI_LORA_ADAPTER_DIR
echo "job=${SLURM_JOB_ID:-local} node=${SLURM_NODELIST:-$(hostname)} start=$(date)"

MEDAI_FLAT_PROMPT_VERSION=v2 MEDAI_ARMS=L1C \
  MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_fs_test_flat_c_v2" \
  venv/bin/python scripts/run_med42_flat_on_fs_test.py
echo "finished=$(date)"
