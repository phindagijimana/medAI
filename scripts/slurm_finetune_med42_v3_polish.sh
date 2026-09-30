#!/bin/bash
#SBATCH --job-name=medai-lora-v3polish
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=08:00:00
#SBATCH --output=logs/medai_lora_v3polish_%j.out
#SBATCH --error=logs/medai_lora_v3polish_%j.err
#
# LoRA fine-tune Med42-8B on the polished synth-v3 corpus.
#
# Prerequisites (must exist before submit):
#   data/eval_corpora/synth_v3_polish/manifest.csv       (~493 rows)
#   data/eval_corpora/synth_v3_polish/documents/*.txt    (per-visit notes)
#   data/episynth_corpus/v3_polish/targets/{P#####}/target_phenotype.json
#
#   To regenerate the target JSONs:
#     venv-medcat/bin/python scripts/convert_synth_corpus_targets.py --corpus-version v3_polish
#
# Submit:
#   sbatch scripts/slurm_finetune_med42_v3_polish.sh
#
# Env overrides:
#   CORPUS=synth-v3-polish (default) | synth-v3-polish+fs80
#   BASE_MODEL=med42 (default) | deepseek
#   SUFFIX=v3_polish (default) — appears in the adapter output dir name
#
# Adapter output:
#   checkpoints/llama3-med42-8b_lora_epi_${SUFFIX}/

set -euo pipefail

echo "=================================================="
echo "MedAI-EPI: LoRA fine-tune Med42-8B on synth-v3-polish"
echo "=================================================="
echo "Job ID:  ${SLURM_JOB_ID:-local}"
echo "Node:    ${SLURM_NODELIST:-$(hostname)}"
echo "Started: $(date)"
echo "=================================================="

module load python 2>/dev/null || module load python/3.10 2>/dev/null || echo "python module not loadable"
module load cuda   2>/dev/null || module load cuda/12.2  2>/dev/null || echo "cuda module not loadable"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
if [ -f "$_SUBMIT_DIR/.env" ]; then
    set -a; . "$_SUBMIT_DIR/.env"; set +a
fi
export APP_HOME="$_SUBMIT_DIR"
PY="$APP_HOME/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "ERROR: venv Python not executable at $PY" >&2; exit 1
fi
export PYTHONNOUSERSITE=1

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true
fi

cd "$APP_HOME"

BASE_MODEL="${BASE_MODEL:-med42}"
CORPUS="${CORPUS:-synth-v3-polish}"
SUFFIX="${MEDAI_LORA_ADAPTER_SUFFIX:-v3_polish}"

# Prerequisite check — fail fast if the corpus isn't ready.
if [ ! -f "data/eval_corpora/synth_v3_polish/manifest.csv" ]; then
    echo "ERROR: synth-v3 polish corpus not found." >&2
    echo "       Expected data/eval_corpora/synth_v3_polish/manifest.csv" >&2
    exit 2
fi
N_TARGETS=$(ls data/episynth_corpus/v3_polish/targets/ 2>/dev/null | wc -l)
if [ "$N_TARGETS" -lt 50 ]; then
    echo "ERROR: too few per-patient targets ($N_TARGETS). Run:" >&2
    echo "       $PY scripts/convert_synth_corpus_targets.py --corpus-version v3_polish" >&2
    exit 3
fi
N_ROWS=$(wc -l < data/eval_corpora/synth_v3_polish/manifest.csv)
echo "[prereq] Corpus manifest rows: $N_ROWS   patient targets: $N_TARGETS"

echo ""
echo "--- Running LoRA fine-tune (base=$BASE_MODEL corpus=$CORPUS suffix=$SUFFIX) ---"
echo "Adapter will land at checkpoints/llama3-med42-8b_lora_epi_${SUFFIX}/"

export MEDAI_LORA_ADAPTER_SUFFIX="$SUFFIX"
$PY scripts/finetune_lora_epi.py \
    --base-model "$BASE_MODEL" \
    --corpus "$CORPUS" \
    --adapter-suffix "$SUFFIX"

echo ""
echo "Finished: $(date)"
