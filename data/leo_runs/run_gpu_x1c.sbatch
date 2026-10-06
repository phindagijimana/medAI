#!/bin/bash
#SBATCH --job-name=leo-v4ext-x1c
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=/mnt/nfs/home/urmc-sh.rochester.edu/pndagiji/Documents/med42_service/data/leo_runs/gpu_%x_%j.out
#SBATCH --error=/mnt/nfs/home/urmc-sh.rochester.edu/pndagiji/Documents/med42_service/data/leo_runs/gpu_%x_%j.err
set -euo pipefail
cd /mnt/nfs/home/urmc-sh.rochester.edu/pndagiji/Documents/med42_service
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME=$PWD PYTHONNOUSERSITE=1 OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
module load cuda 2>/dev/null || true
echo "node=$(hostname) job=${SLURM_JOB_ID} start=$(date)"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
exec venv-medcat/bin/python eval/leo_v4ext_run.py --mode gpu --out data/leo_runs/v4ext_llm_x1c
