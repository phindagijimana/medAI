#!/bin/bash
#SBATCH --job-name=medai-flat-c
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --output=logs/medai_flat_c_%j.out
#SBATCH --error=logs/medai_flat_c_%j.err
#
# Base Med42-8B with schema-constrained decoding (lm-format-enforcer): arms L1C and L2C on the
# held-out letters EA0161-EA0200 and on the development letters EA0081-EA0120.  Resumable.

set -euo pipefail
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$_SUBMIT_DIR"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME="$_SUBMIT_DIR"
export PYTHONNOUSERSITE=1
unset MEDAI_LORA_ADAPTER_DIR
echo "job=${SLURM_JOB_ID:-local} node=${SLURM_NODELIST:-$(hostname)} start=$(date)"

MEDAI_ARMS=L2C,L1C MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_fs_test_flat_c" \
  venv/bin/python scripts/run_med42_flat_on_fs_test.py

DEV=$(python3 -c "print(','.join(f'EA{i:04d}' for i in range(81,121)))")
MEDAI_ARMS=L2C,L1C MEDAI_PIDS="$DEV" MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_fs_dev_flat_c" \
  venv/bin/python scripts/run_med42_flat_on_fs_test.py
echo "finished=$(date)"
