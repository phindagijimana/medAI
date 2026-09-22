# MedAI-EPI

**Research phenotyping assistant for epilepsy clinical documentation.**

MedAI-EPI extracts structured, evidence-grounded epilepsy phenotype variables from heterogeneous clinical documents (MRI reports, EEG reports, progress notes, EMU/presurgical/conference/procedure documentation) for research use.

> **⚠️ Research use only.** MedAI-EPI is a research information-extraction tool. It does **not** diagnose, does **not** recommend treatment, and is **not** a clinical decision-support system. All extracted values must be reviewed by qualified medical professionals before any research or clinical use. See paper §21 of the study protocol for governance detail.

## What this project is

A validated text-phenotype layer supporting downstream epilepsy research:
- Structured extraction of ILAE 2017 seizure/epilepsy types, medication timelines, drug-resistance status, imaging findings, and cross-modality synthesis
- Every extracted value carries evidence provenance (source document, date, minimal-sufficient quote, character offsets)
- Modular ontology per document family (MRI-report fields only apply to MRI reports, etc.)
- Runs on locally deployable open-source medical LLMs (currently Llama3-Med42-8B)

**What this project is NOT**: a diagnostic AI, a clinical decision-support tool, an autonomous "expert" system. See paper §21.

## Two parallel tracks

- **App runtime** (existing Flask + SLURM stack): interactive extraction UI + `/extract` REST endpoint for programmatic use.
- **Paper track** (new): schema `schema/`, versioned prompts and extraction pipeline `services/`, evaluation harness `eval/`, silver-labeled corpus at `data/fonferko_shadrach_2024/`. See `docs/SCHEMA_V0_2.md` for the ontology and `paper_doc/` for the full study protocol.

## Quick Start

### Local
```bash
git clone https://github.com/phindagijimana/medai.git
cd medai
./medai start
```
Access at `http://localhost:8085`.

### HPC (SLURM)
```bash
./medai-hpc install
./medai-hpc run gpu    # 'run cpu' for CPU-only
./medai-hpc status
```

### Paper-track eval sweep
```bash
sbatch scripts/slurm_m2_mri.sh                   # first Med42 M0/M1/M2 signal
python3 scripts/smoke_test_all.py                # end-to-end pipeline verification
python3 scripts/fetch_fonferko_shadrach.py       # open annotated corpus
python3 scripts/silver_label_fonferko.py         # convert to silver labels
python3 scripts/analyze_fonferko_schema.py       # schema-mapping report
```

## CLI Commands

### Local (`./medai`)
```bash
./medai install        # pip install -r requirements.txt
./medai start          # Gunicorn in background (production-style)
./medai start -f       # Flask dev server in foreground
./medai start -p 8090  # Port (also SERVICE_PORT)
./medai status         # Check status
./medai logs           # View logs
./medai stop           # Stop service
./medai restart
```

Use `MEDAI_PIP_USER=0` when using a venv so `pip install` does not pass `--user`.

### HPC (medai-hpc)
```bash
./medai-hpc install             # Setup
./medai-hpc run gpu             # Submit GPU job
./medai-hpc run cpu             # Submit CPU job
./medai-hpc status              # Check status
./medai-hpc logs                # View logs
```

## Requirements

**Minimum**:
- Python 3.8+
- 2GB RAM
- Flask, pandas, numpy (auto-installed)

**For AI Model**:
- PyTorch 2.1+
- 16GB+ GPU VRAM (GPU mode) or CPU fallback
- CUDA 11.7+ (GPU mode)

## Documentation

- `docs/SCHEMA_V0_2.md` — the phenotype ontology (v0.2.1), reviewer-facing
- `docs/SCHEMA_V0_1_STRESS_TEST.md` — schema gap analysis against real case narratives
- `docs/FONFERKO_SHADRACH_MAPPING.md` — external corpus mapping
- `docs/DEPLOYMENT.md` — deployment guide (HPC + local)
- `docs/SELF_HOSTING.md` — Gunicorn / env vars / Docker
- `paper_doc/MedAI_Paper1_Heterogeneous_Clinical_Documents_Full_Blueprint.docx` — full study protocol
- `paper_doc/MedAI_Paper1_Literature_Review_Reference_Guide.docx` — related-work map

## Tech Stack

- Backend: Flask, Python 3, Gunicorn
- Schema: Pydantic v2
- Database: SQLite (annotation database); PostgreSQL planned for multi-user annotation
- ML: PyTorch 2.5+, Transformers 4.44+ (loads m42-health/Llama3-Med42-8B)
- Optional: sentence-transformers for retrieval

## Governance and intended use

- All extractions are research-grade phenotype records, not clinical inferences.
- Every value has provenance (document ID + date + verbatim evidence quote).
- "Not documented" / "unknown" are first-class values and are preferred over guessing.
- Deployment against real patient data requires IRB approval, appropriate DUA, and institutionally approved secure compute for PHI.
- MedAI-EPI must not be used for autonomous diagnosis or treatment recommendations.

## License

MIT (code). Fetched external corpora carry their own licenses; see per-artifact `manifest.json`.

## Support

GitHub Issues: https://github.com/phindagijimana/medai/issues
