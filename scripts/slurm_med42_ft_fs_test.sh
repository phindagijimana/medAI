#!/bin/bash
#SBATCH --job-name=medai-ft-fs
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/medai_ft_fs_%j.out
#SBATCH --error=logs/medai_ft_fs_%j.err
#
# Arm H, in contract: tuned Med42-8B, training prompt, one full-phenotype
# generation per held-out F-S letter.  Resumable: resubmit if it times out.
#
#   sbatch scripts/slurm_med42_ft_fs_test.sh
#   sbatch --export=ALL,MEDAI_LIMIT=2 scripts/slurm_med42_ft_fs_test.sh   # smoke
#
# Score (no GPU):
#   venv-medcat/bin/python scripts/score_leo_vs_fs_gold.py \
#       --llm armH=data/run_manifests_fs_test_ft_v3_polish:FT

set -euo pipefail
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$_SUBMIT_DIR"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME="$_SUBMIT_DIR"
export PYTHONNOUSERSITE=1
export MEDAI_MAX_NEW_TOKENS="${MEDAI_MAX_NEW_TOKENS:-4096}"
export MEDAI_LORA_ADAPTER_DIR="${MEDAI_LORA_ADAPTER_DIR:-$_SUBMIT_DIR/checkpoints/llama3-med42-8b_lora_epi_v3_polish}"
export MEDAI_MANIFEST_DIR="${MEDAI_MANIFEST_DIR:-$_SUBMIT_DIR/data/run_manifests_fs_test_ft_v3_polish}"
[ -d "$MEDAI_LORA_ADAPTER_DIR" ] || { echo "adapter missing: $MEDAI_LORA_ADAPTER_DIR" >&2; exit 1; }
echo "job=${SLURM_JOB_ID:-local} node=${SLURM_NODELIST:-$(hostname)} start=$(date)"
echo "adapter=$MEDAI_LORA_ADAPTER_DIR"; echo "manifests=$MEDAI_MANIFEST_DIR"
nvidia-smi --query-gpu=name,memory.total --format=csv || true
venv/bin/python scripts/run_med42_ft_on_fs_test.py
echo "finished=$(date)"
