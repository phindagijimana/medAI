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

## Getting started for researchers (~3 minutes)

If you have a single note you want to phenotype right now:

1. **Start the service.** Local (uses the small dev server, fine for one user):
   ```bash
   ./medai start -f
   ```
   or on HPC:
   ```bash
   sbatch slurm_job.sh
   ```

2. **Open the research UI in a browser** at `http://localhost:8085/extract/ui` (or replace localhost with the HPC node hostname).

3. **Acknowledge the research-use disclaimer** on first visit.

4. **Wait for Med42 to load.** The status badge in the top-right shows `Loading Med42…` for ~30–60 s on the first request, then flips to `Backend ready`.

5. **Paste a clinical document** into the left panel. The doc type auto-detects on click-out (MRI report / EEG report / progress note / EMU discharge / etc.). Override the suggestion if it's wrong.

6. **Pick an extraction arm**:
   - `M0` — zero-shot (fastest, lowest raw validity)
   - `M1` — few-shot with one Fonferko-Shadrach-adapted example
   - `M2` — few-shot + JSON schema injected into the prompt (highest final validity, ~30 s per module) — **recommended**

7. **Click "Extract phenotype"**. A per-module extraction runs; results appear in the bottom panel.

8. **Review the phenotype**. Every field carries a certainty pill (`definite`, `probable`, `possible`, `negated`, `unknown`, or `not_documented`). Click any field with evidence → the source view scrolls to and highlights the source quote.

9. **Download the results**:
   - `Download JSON` — full phenotype record, Pydantic-schema-conforming
   - `Download CSV` — one row per document, one column per `<module>.<field>.<value|certainty|evidence>` — imports directly into R / Excel / MATLAB.

10. **Iterate.** Clear the form and paste the next note. Nothing is stored server-side beyond the audit trail (`data/run_manifests/<date>/*.json`) unless you also configure the validation database.

**Programmatic API** (curl / Python / REDCap integration):
```bash
curl -X POST http://localhost:8085/extract \
  -H "Content-Type: application/json" \
  -d '{"source_text": "MRI BRAIN 3T. FINDINGS: right hippocampal sclerosis...", "doc_type": "mri_report", "arm": "M2"}'
```
Endpoints:
- `POST /extract` — single document
- `POST /extract/batch` — up to N documents in one call (synchronous)
- `POST /extract/detect_doc_type` — deterministic keyword-based doc-type suggestion
- `GET /extract/health` — Med42 load status + supported doc types
- `GET /extract/registry` — list of all 22 versioned prompt templates
- `GET /extract/registry/<prompt_id>` — one prompt in full for auditing

**Governance reminder.** MedAI-EPI is a **research phenotyping assistant**, not a diagnostic tool. Every extracted value must be reviewed by qualified clinicians. Real patient data requires IRB approval and institutionally-approved secure compute.

---

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
