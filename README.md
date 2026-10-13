# MedAI-EPI / LEO

**Research phenotyping for epilepsy notes.** LEO (runtime `leo-v0.9`; headline extras still the frozen D17 L1C files) fills a table from a note: value, quote, which reader said it, whether a person should look.

> **Research use only.** Does not diagnose or recommend treatment. Real notes need IRB and approved compute. Tested on **synthetic notes only**.

Operator: [`docs/LEO_USER_GUIDE.md`](docs/LEO_USER_GUIDE.md). Hosting: [`docs/LEO_HOSTING.md`](docs/LEO_HOSTING.md). Design: [`docs/IMPLEMENTATION.md`](docs/IMPLEMENTATION.md). How to quote numbers: [`docs/INTERPRETING_RESULTS.md`](docs/INTERPRETING_RESULTS.md).

HTML docs: [medai.readthedocs.io](https://medai.readthedocs.io) (Read the Docs, same host as [QSIPrep](https://qsiprep.readthedocs.io)). Preview: `pip install -r docs_site/requirements.txt && mkdocs serve`.

## Crucial commands

```bash
# install / check
bin/leo install --check-only
bin/leo check                    # CPU, specialist only
bin/leo check --slurm            # Med42 on a GPU node

# extract
bin/leo phenotypes
bin/leo evidence
bin/leo batch notes.xlsx         # Slurm GPU → notes_leo.xlsx
bin/leo batch notes.xlsx --cpu   # rules only; every cell needs_review
bin/leo batch notes.xlsx --local
bin/leo run "seizure types for the first 100 subjects" --input notes.xlsx

# web
bin/leo user add NAME            # turns login on
bin/leo start                    # then: bin/leo status
# open /leo/ui  (SSH tunnel from status)

# validator (same store as the download)
bin/leo review notes_leo.csv
bin/leo review notes_leo.reviewed.csv --summarize
bin/leo merge notes_leo.csv notes_leo.reviewed.csv

# learning later (does not change extract; LoRA paused)
bin/leo learn notes_leo.reviewed.csv
bin/leo learn --archive
bin/leo learn FILE.reviewed.csv --loop a --emit-policy policy.json
# apply only after ≥100 scored cases/field, as a new leo-v0.x:
bin/leo batch notes.xlsx --disagree-llm policy:policy.json

bin/leo rollup notes_leo.csv --patient-col patient_id
bin/leo stop
```

Default extract is GPU (Med42-8B + EpExtra). `--cpu` has no second reader. Output is next to the input (`*_leo.csv|xlsx`, `.claims.csv`, `.provenance.json`) and contains note text.

## What you get

- **Table, not a chat.** One row per note. Core fields: epilepsy type, seizure type, onset age, frequency, current ASMs (ILAE 2017 / Kwan 2010).
- **Two readers.** Rules (EpExtra) + model (Med42-8B, constrained, greedy). Agree → accept. Disagree → review; rules shown (D17); model kept as `alternative`.
- **Validator.** Accept / Correct / Deny / Add missed, why-tag, which-reader, 10% accepted audit. Merge writes `_final` for this job only.
- **Learning is a command**, not a click. `leo learn` scores routing and thresholds. Few-shot and LoRA are paused.

Research extract = `accepted` **and** `specialist+llm`. LEO does not beat the model on F1; it adds an audit trail. `bin/leo evidence`.

## Requirements

- Python 3.11, `venv-medcat`, Slurm GPU for real extraction (L40S 24 GB in this lab).
- UMLS key in `.env` (never printed). Ontologies are not in git.
- Hugging Face access to Med42-8B for GPU runs.

## Docs

| File | Use |
|---|---|
| `docs/index.md` | Public HTML landing (Read the Docs) |
| `docs/LEO_USER_GUIDE.md` | Run the tool |
| `docs/LEO_HOSTING.md` | Workstation vs Slurm (`--gres`, `--cpu`, `--local`) |
| `docs/IMPLEMENTATION.md` | A–Z design, decisions, strengths, weaknesses |
| `docs/WEAKNESSES.md` | Each hole, what accounts for it, what to improve next |
| `docs/INTERPRETING_RESULTS.md` | Concordant PPV; research extract ≠ reviewed |
| `docs/ACTIVE_LEARNING_PLAN.md` | `leo learn` |
| `docs/EVAL_PROTOCOL_LEO.md` | Frozen protocol (D1–D33) |
| `docs/LEO_ROUTING_RULES.md` | ACCEPT / REVIEW / REJECT |

The older Med42-only paper UI (`/extract/ui`, arms M0/M1/M2) is a separate URL, not linked from LEO. Day-to-day use is `bin/leo` and `/leo/ui`.

## What git does not contain (do not add)

`.env` / `.env.save` (UMLS, HF, Flask secrets). `model_cache/`, `venv-medcat/`, `data/ontologies/` except `MANIFEST.json`. `data/leo_jobs/`, `data/leo_training/`, `logs/leo_jobs/`, `*_leo.csv`. `data/restricted/` (MIMIC). Job output contains note text.

Fonferko-Shadrach letters in-tree are **synthetic, CC-BY**. They are not real-patient notes.

Paper drafts (`writing/`, `paper_doc/`, TRIPOD / reviewer packet) stay on disk and are gitignored. Run-manifest trees stay on disk and are gitignored (they embed local cache paths). Git history may still contain older lab paths until a history rewrite, which is not done here. Do not commit real notes.

License: MIT for code; corpora keep their own licenses.
