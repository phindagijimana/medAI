#!/bin/bash
#SBATCH --job-name=medai-stress-fs
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/medai_stress_%x_%j.out
#SBATCH --error=logs/medai_stress_%x_%j.err
#
# Stress test of the model table on MORE F-S letters: EA0001-EA0160 (the 40 held-out letters EA0161-EA0200
# are the ones in the original table).  None of these models was trained on F-S letters; arm L2 retrieves
# examples from the F-S bank with the letter itself excluded.  Resumable; one job per arm.
#   sbatch --job-name=L0 --export=ALL,WHAT=base,ARM=L0 scripts/slurm_stress_fs.sh     (also L1, L2)
#   sbatch --job-name=H  --export=ALL,WHAT=ft   scripts/slurm_stress_fs.sh              (first adapter, v3_polish)
#   sbatch --job-name=H2 --export=ALL,WHAT=h2   scripts/slurm_stress_fs.sh              (second adapter, constrained)
set -euo pipefail
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$_SUBMIT_DIR"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME="$_SUBMIT_DIR" PYTHONNOUSERSITE=1
export MEDAI_PIDS=$(python3 -c "print(','.join(f'EA{i:04d}' for i in range(1,161)))")
echo "job=${SLURM_JOB_ID:-local} node=${SLURM_NODELIST:-$(hostname)} start=$(date) what=${WHAT:?} arm=${ARM:-}"
nvidia-smi --query-gpu=name,memory.total --format=csv || true
case "$WHAT" in
  base) unset MEDAI_LORA_ADAPTER_DIR
        MEDAI_ARMS="${ARM:?}" MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_fs_stress_base" \
          venv/bin/python scripts/run_med42_flat_on_fs_test.py ;;
  ft)   export MEDAI_MAX_NEW_TOKENS=4096
        MEDAI_LORA_ADAPTER_DIR="$_SUBMIT_DIR/checkpoints/llama3-med42-8b_lora_epi_v3_polish" \
        MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_fs_stress_ft" \
          venv/bin/python scripts/run_med42_ft_on_fs_test.py ;;
  h2)   MEDAI_LORA_ADAPTER_DIR="$_SUBMIT_DIR/checkpoints/llama3-med42-8b_lora_epi_h2" MEDAI_FLAT_ADAPTER_OK=1 MEDAI_ARMS=L0C \
        MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_fs_stress_h2" \
          venv/bin/python scripts/run_med42_flat_on_fs_test.py ;;
  *) echo "bad WHAT" >&2; exit 1 ;;
esac
echo "finished=$(date)"
