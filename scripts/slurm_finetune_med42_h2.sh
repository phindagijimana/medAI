#!/bin/bash
#SBATCH --job-name=medai-lora-h2
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/medai_lora_h2_%j.out
#SBATCH --error=logs/medai_lora_h2_%j.err
#
# Arm H2: LoRA fine-tune Med42-8B on the flat contract with verbatim evidence spans.
# Data: scripts/emit_flat_training_pairs.py  ->  data/finetune_data/flat_polish_{train,val}.jsonl
# Adapter: checkpoints/llama3-med42-8b_lora_epi_h2/   (patient-level validation split identical to Arm H)
set -euo pipefail
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$_SUBMIT_DIR"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME="$_SUBMIT_DIR" PYTHONNOUSERSITE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
module load cuda 2>/dev/null || true
[ -f data/finetune_data/flat_polish_train.jsonl ] || { echo "run scripts/emit_flat_training_pairs.py first" >&2; exit 2; }
export MEDAI_LORA_ADAPTER_SUFFIX=h2
venv/bin/python scripts/finetune_lora_epi.py --base-model med42 \
    --train-jsonl data/finetune_data/flat_polish_train.jsonl \
    --val-jsonl data/finetune_data/flat_polish_val.jsonl \
    --adapter-suffix h2 --epochs 4 --max-length 3584
echo "finished $(date)"
