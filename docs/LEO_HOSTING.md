# Hosting LEO (workstation or HPC)

Researchers can run LEO themselves. Synthetic notes only unless they have IRB + approved compute. Not a device.

## What they need

| | Rules only (CPU) | Model + rules (GPU) |
|---|---|---|
| Python | `venv-medcat` (`bin/leo install`) | same |
| CDB | `data/medcat_cdb_epilepsy/cdb` | same |
| Weights | not used | `model_cache/models--m42-health--Llama3-Med42-8B` |
| UMLS | `.env` (`UMLS_API_KEY`) for MedCAT | same |
| Hardware | ~16 CPU / 48G | 1× 24G GPU (L40S here), 8 CPU / 64G |
| Research extract | **empty** — one reader, every cell `needs_review` | `accepted` ∧ `specialist+llm` |

`bin/leo install --check-only` then `bin/leo check`. GPU path: `bin/leo check --gpu` on a GPU node, or `bin/leo check --slurm` from a login node.

## Workstation

```bash
bin/leo check                              # rules only, this machine
bin/leo batch notes.csv --local --mode cpu # EpExtra; all cells needs_review
bin/leo batch notes.csv --local --mode gpu # Med42 + EpExtra if CUDA is visible
```

`--local --mode auto` uses the GPU when `torch.cuda.is_available()`, else CPU, and says so. Dual-reader extract **needs a GPU**. Manifest replay is for scoring, not a user substitute for Med42.

## Example Slurm site

Login node has no GPU. Default `leo batch` / `leo start` submits a job. Override `--partition` / `--gres` for your cluster.

| Flag | Job | Partition default | Resources |
|---|---|---|---|
| (none) | GPU, both readers | `interactive` (batch/run), `general` (server) | `--gres=gpu:l40s.24g:1`, 8 CPU, 64G |
| `--cpu` | CPU, rules only | same | 16 CPU, 48G, no GRES |
| `--local` | this node | — | no sbatch |

```bash
bin/leo check --slurm --wait
bin/leo batch notes.csv --cpu --partition interactive --hours 2
bin/leo batch notes.csv --partition interactive --hours 4 --gres gpu:l40s.24g:1
```

Override site names: `--partition`, `--hours`, `--gres`, `--cpus`, `--mem`, or `MEDAI_LEO_GRES`. Secrets stay in `.env` (sourced on the node; never written into the sbatch script).

## Another cluster

Keep `--local` on an interactive GPU allocation, **or** set `--gres` / `MEDAI_LEO_GRES` to that site’s name (`gpu:a100:1`, `gpu:1`, …). Change `--partition` to theirs. Weights and CDB must be on a filesystem the compute node can read.

## Ready?

Yes for a researcher who can: create `venv-medcat`, place Med42 weights, keep UMLS in `.env`, and either sit on a GPU workstation or submit Slurm with the right GRES. CPU-only is ready today and is **not** a research extract. Confirm with `bin/leo check` and, on GPU, `bin/leo check --gpu` / `--slurm`.
