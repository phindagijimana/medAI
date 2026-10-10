#!/bin/bash
#SBATCH --job-name=leo-arme
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=data/leo_runs/gpu_%x_%j.out
#SBATCH --error=data/leo_runs/gpu_%x_%j.err
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME=$PWD PYTHONNOUSERSITE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
module load cuda 2>/dev/null || true
echo "node=$(hostname) job=${SLURM_JOB_ID} start=$(date)"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
exec venv-medcat/bin/python eval/eval_concept_selection.py --mode gpu --offline --out eval/results/concept_selection_gpu_letter_2026-10-06
