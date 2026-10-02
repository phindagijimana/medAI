#!/bin/bash
#SBATCH --job-name=medai-flat-l2
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=03:00:00
#SBATCH --output=logs/medai_flat_l2_%j.out
#SBATCH --error=logs/medai_flat_l2_%j.err
#
# Base Med42-8B.  (1) held-out letters EA0161-EA0200, arm L2 (retrieved F-S training letters);
# (2) development letters EA0081-EA0120, arms L1 and L2 (used only to choose the LEO fusion policy;
# held-out letters are never used for that).  Resumable.

set -euo pipefail
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$_SUBMIT_DIR"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME="$_SUBMIT_DIR"
export PYTHONNOUSERSITE=1
unset MEDAI_LORA_ADAPTER_DIR
echo "job=${SLURM_JOB_ID:-local} node=${SLURM_NODELIST:-$(hostname)} start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv || true

MEDAI_ARMS=L2 MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_fs_test_flat" \
  venv/bin/python scripts/run_med42_flat_on_fs_test.py

DEV=$(python3 -c "print(','.join(f'EA{i:04d}' for i in range(81,121)))")
MEDAI_ARMS=L1,L2 MEDAI_PIDS="$DEV" MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_fs_dev_flat" \
  venv/bin/python scripts/run_med42_flat_on_fs_test.py
echo "finished=$(date)"
