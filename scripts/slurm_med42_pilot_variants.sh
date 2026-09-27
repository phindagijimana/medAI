#!/bin/bash
#SBATCH --job-name=medai-pilot-variants
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/medai_pilot_variants_%j.out
#SBATCH --error=logs/medai_pilot_variants_%j.err
#SBATCH --dependency=afterok:143696
#
# Submit (queued behind the R4c LoRA fine-tune job 143696):
#     sbatch scripts/slurm_med42_pilot_variants.sh
#
# Runs three Med42 variant sweeps sequentially on the 60-doc pilot:
#     (a) base_constr   base Med42 + schema-constrained decoding
#     (b) tuned         Med42 + LoRA adapter, unconstrained
#     (c) tuned_constr  Med42 + LoRA adapter + schema-constrained decoding
#
# Each variant reloads the model (needed because LoRA state differs) and writes
# manifests to data/run_manifests_pilot_<variant>/.
#
# Follow-up scoring (after this SLURM job finishes):
#     python scripts/score_med42_on_pilot.py --manifests-dir data/run_manifests_pilot_base_constr --suffix base_constr
#     python scripts/score_med42_on_pilot.py --manifests-dir data/run_manifests_pilot_tuned        --suffix tuned
#     python scripts/score_med42_on_pilot.py --manifests-dir data/run_manifests_pilot_tuned_constr --suffix tuned_constr

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI: Med42 pilot variant sweep (R4e-i)"
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

# Adapter dir written by the R4c fine-tune (SLURM 143696).
export MEDAI_ADAPTER_DIR="${MEDAI_ADAPTER_DIR:-$APP_HOME/checkpoints/llama3-med42-8b_lora_epi}"

# All three variants (comma-separated). Override to run a subset.
export MEDAI_PILOT_VARIANTS="${MEDAI_PILOT_VARIANTS:-base_constr,tuned,tuned_constr}"

PY="$APP_HOME/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv Python not executable at $PY" >&2
    exit 1
fi
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi | head -20
fi

cd "$APP_HOME"

echo ""
echo "--- Running Med42 pilot variant sweep ---"
echo "Adapter:  $MEDAI_ADAPTER_DIR"
echo "Variants: $MEDAI_PILOT_VARIANTS"
$PY scripts/run_med42_on_pilot_variants.py

echo ""
echo "Finished: $(date)"
echo ""
echo "Follow-up scoring:"
for v in ${MEDAI_PILOT_VARIANTS//,/ }; do
    echo "    $PY scripts/score_med42_on_pilot.py --manifests-dir data/run_manifests_pilot_${v} --suffix ${v}"
done
