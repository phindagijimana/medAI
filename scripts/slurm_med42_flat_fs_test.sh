#!/bin/bash
#SBATCH --job-name=medai-flat-fs
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=logs/medai_flat_fs_%j.out
#SBATCH --error=logs/medai_flat_fs_%j.err
#
# Base Med42-8B, flat prompts L0 (zero-shot) and L1 (two examples), 40 held-out letters.
# Resumable. Score (no GPU):
#   venv-medcat/bin/python scripts/score_leo_vs_fs_gold.py \
#       --llm L0=data/run_manifests_fs_test_flat:L0 --llm L1=data/run_manifests_fs_test_flat:L1

set -euo pipefail
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$_SUBMIT_DIR"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME="$_SUBMIT_DIR"
export PYTHONNOUSERSITE=1
unset MEDAI_LORA_ADAPTER_DIR
export MEDAI_MANIFEST_DIR="${MEDAI_MANIFEST_DIR:-$_SUBMIT_DIR/data/run_manifests_fs_test_flat}"
echo "job=${SLURM_JOB_ID:-local} node=${SLURM_NODELIST:-$(hostname)} start=$(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv || true
venv/bin/python scripts/run_med42_flat_on_fs_test.py
echo "finished=$(date)"
