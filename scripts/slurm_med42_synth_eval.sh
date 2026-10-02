#!/bin/bash
#SBATCH --job-name=medai-synth-eval
#SBATCH --partition=interactive
#SBATCH --gres=gpu:l40s.24g:1
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/medai_synth_eval_%j.out
#SBATCH --error=logs/medai_synth_eval_%j.err
#
# LLM arms on the US-style synthetic evaluation notes (services/synth_eval.py: 143 notes of 10
# synth-v3-polish validation patients + 20 synth-v3 patients).  Resumable and shardable:
#
#   ARM=FT   sbatch --export=ALL,ARM=FT,MEDAI_SHARD=0/3 scripts/slurm_med42_synth_eval.sh   (and 1/3, 2/3)
#   ARM=flat sbatch --export=ALL,ARM=flat scripts/slurm_med42_synth_eval.sh
#
# Which patients (services/synth_eval.py, MEDAI_SYNTH_SET): SYNTH_SET=eval (default, 30 patients),
# ext (the other 80 synth-v3 patients) or v1v2 (held-out synth-v1 and synth-v2 patients).  Manifest
# directories get the suffix _ext / _v1v2.  Example:
#   SYNTH_SET=ext ARM=FT sbatch --export=ALL,SYNTH_SET=ext,ARM=FT,MEDAI_SHARD=0/4 scripts/slurm_med42_synth_eval.sh
#
# FT   = v3-polish adapter in contract (full phenotype, unconstrained), manifests in
#        data/run_manifests_synth_eval_ft
# flat = base model, arms L0C and L1C (schema-constrained), manifests in
#        data/run_manifests_synth_eval_flat

set -euo pipefail
_SUBMIT_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$_SUBMIT_DIR"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME="$_SUBMIT_DIR"
export PYTHONNOUSERSITE=1
export MEDAI_CORPUS=synth
export MEDAI_SYNTH_SET="${SYNTH_SET:-eval}"
case "$MEDAI_SYNTH_SET" in eval) SFX="";; ext) SFX="_ext";; v1v2) SFX="_v1v2";; polish90) SFX="_polish90";; *) echo "bad SYNTH_SET" >&2; exit 1;; esac
echo "job=${SLURM_JOB_ID:-local} node=${SLURM_NODELIST:-$(hostname)} start=$(date) arm=${ARM:-?} shard=${MEDAI_SHARD:-all}"
nvidia-smi --query-gpu=name,memory.total --format=csv || true

if [ "${ARM:-FT}" = "FT" ]; then
  export MEDAI_MAX_NEW_TOKENS="${MEDAI_MAX_NEW_TOKENS:-4096}"
  export MEDAI_LORA_ADAPTER_DIR="$_SUBMIT_DIR/checkpoints/llama3-med42-8b_lora_epi_v3_polish"
  export MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_synth_eval_ft${SFX}"
  [ -d "$MEDAI_LORA_ADAPTER_DIR" ] || { echo "adapter missing" >&2; exit 1; }
  venv/bin/python scripts/run_med42_ft_on_fs_test.py
else
  unset MEDAI_LORA_ADAPTER_DIR
  export MEDAI_ARMS="${MEDAI_ARMS:-L0C,L1C}"
  export MEDAI_MANIFEST_DIR="$_SUBMIT_DIR/data/run_manifests_synth_eval_flat${SFX}"
  venv/bin/python scripts/run_med42_flat_on_fs_test.py
fi
echo "finished=$(date)"
