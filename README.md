# MedAI-EPI

**Research phenotyping assistant for epilepsy clinical documentation.**

MedAI-EPI extracts structured, evidence-grounded epilepsy phenotype variables
from clinical documents (progress notes, MRI reports, EEG reports, EMU/
presurgical documentation) for research use. Every extracted value carries a
verbatim source quote and a `certainty` label; outputs land as tidy-format CSV
ready for pandas / R / SQL analysis.

> **Research use only.** MedAI-EPI is a research information-extraction tool.
> It does **not** diagnose, does **not** recommend treatment, and is **not**
> clinical decision support. All extracted values must be reviewed by qualified
> clinicians. Deployment against real patient data requires IRB approval and
> institutionally-approved secure compute. See the manuscript §Positioning for
> the specialty-at-a-time framing and §Ethics for scope of intended use.

## Table of contents

1. [What you get](#what-you-get)
2. [Quick start (5 min)](#quick-start-5-min)
3. [Using the app in the browser](#using-the-app-in-the-browser)
4. [API reference](#api-reference)
5. [Long notes and multi-visit Excel input](#long-notes-and-multi-visit-excel-input)
6. [Reproducing the paper's tables](#reproducing-the-papers-tables)
7. [Requirements](#requirements)
8. [Repository layout](#repository-layout)
9. [Citing this work](#citing-this-work)

---

## What you get

- **Structured extraction** into a versioned Pydantic ontology (`schema/`)
  covering six modules: `ClinicalSeizure`, `Medication`, `ClinicalLocalization`,
  `Eeg`, `Mri`, `IntegratedPhenotype`. Aligned with ILAE 2017 seizure and
  epilepsy classifications and ILAE 2010 drug-resistance definition.
- **Evidence-grounded output**: every field carries a `value`, `certainty`
  (definite / probable / possible / negated / unknown / not_documented),
  verbatim `evidence_text`, character offsets, and source-document provenance.
- **Three prompting arms** for Med42-8B (M0 zero-shot / M1 few-shot / M2
  few-shot with schema injected) plus rules (B0) and BioClinicalBERT (B1)
  baselines. All 22 versioned prompts live in `services/prompt_registry.py`.
- **Two-tier repair chain**: strip-code-fence + regex JSON extraction, then
  `smart_repair` wraps bare values in default Evidence metadata and normalizes
  60+ enum synonyms — raising structural validity from ~5 % raw to ~95 %.
- **Long-format CSV output**: one row per extracted field with `value`,
  `evidence_text`, `confidence`, `temporal_status`, `char_start`/`char_end`,
  and provenance columns. Standard tidy-data shape for downstream analysis.
- **Freeform chat**: `/extract/chat` accepts any user question about a note and
  returns a grounded answer with a verbatim quote, appendable to the same CSV.
- **Long-document and per-visit handling**: `services/chunker.py` chunks by
  clinical section / paragraph or by Excel-style visit rows;
  `services/merge.py` unions list fields, keeps latest-visit-wins scalars,
  and flags conflicts across chunks.
- **Reproducibility container**: `Dockerfile.eval` reproduces every table in
  the manuscript from released run manifests without a GPU. `eval/aggregator_cli.py`
  is the entry point.

---

## Quick start (5 min)

### Option A — Docker (recommended for a fresh machine)

```bash
git clone https://github.com/phindagijimana/vecta.git
cd vecta

# CPU-only image (fine for smoke tests, offline components, and remote-GPU dev):
docker build -t medai-epi:cpu .
docker run -p 8085:8085 medai-epi:cpu

# GPU image (needed to run Med42-8B locally on an NVIDIA GPU with ≥16 GB VRAM):
docker build -f Dockerfile.gpu -t medai-epi:gpu .
docker run --gpus all -p 8085:8085 \
    -v $HOME/.cache/huggingface:/root/.cache/huggingface \
    -e HF_TOKEN=$HF_TOKEN \
    medai-epi:gpu
```

Open `http://localhost:8085` → auto-redirects to the research UI at `/extract/ui`.

### Option B — Local Python venv

```bash
git clone https://github.com/phindagijimana/vecta.git
cd vecta
cp .env.example .env    # then edit APP_HOME and (optionally) SECRET_KEY
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app.py           # or: ./medai start -f
```

### Option C — HPC (SLURM)

```bash
./medai-hpc install
./medai-hpc run gpu
./medai-hpc status
```

### Verify the install (offline, no GPU needed)

```bash
python scripts/smoke_e2e_http.py
```

Should print 26 `✓` checks in green. Uses a scripted mock backend, so it
verifies the HTTP surface end-to-end without loading Med42.

---

## Using the app in the browser

1. Open `http://localhost:8085/extract/ui`.
2. Acknowledge the research-use disclaimer.
3. Wait for the status badge to turn `Backend ready` (~30–60 s on first request
   while Med42-8B downloads and loads).
4. Paste a clinical note into the left panel. Doc type auto-detects on blur;
   override the suggestion if needed.
5. Pick a prompting arm:
   - `M0` — zero-shot (fastest, lowest raw validity)
   - `M1` — few-shot with one Fonferko-Shadrach-adapted example
   - `M2` — few-shot + JSON schema injected in the prompt (highest final
     validity but hits the schema-echo pathology on 8B models; see paper
     §Results and §Limitations)
6. Click **Extract phenotype**. Per-module extractions run in sequence; results
   appear in the phenotype tree with certainty pills. Click any field with
   evidence — the source view scrolls to and highlights the exact quote.
7. **Ask follow-up questions** in the Chat panel below the phenotype tree —
   e.g. "was surgery mentioned?", "what was the reason for LTG discontinuation?"
   Answers come with a verbatim quote and a confidence label.
8. **Download CSV** — tidy long format, one row per field, with `evidence_text`
   and `confidence` columns next to each value. Optional toggles let you
   include `not_documented` rows and chat Q&A rows in the same file.

---

## API reference

All endpoints under `/extract/*`. Every response is `Cache-Control: no-store`.

| Endpoint                              | Method | Purpose |
|---------------------------------------|--------|---------|
| `/extract`                            | POST   | Single-document structured extraction; returns full JSON phenotype + per-module manifests |
| `/extract/batch`                      | POST   | Multi-document, synchronous |
| `/extract/csv`                        | POST   | Text OR CSV input → long-format CSV output. Auto-chunks docs > 8000 chars; `?chunk=1` to force |
| `/extract/chat`                       | POST   | One user question about one note → grounded answer + CSV row for `module=user_query` |
| `/extract/ui`                         | GET    | Single-page browser UI |
| `/extract/health`                     | GET    | Backend load status + registered prompts + supported doc types |
| `/extract/registry`                   | GET    | Inventory of all 22 versioned prompts |
| `/extract/registry/<prompt_id>`       | GET    | One prompt in full for auditing |
| `/extract/detect_doc_type`            | POST   | Deterministic keyword-based doc-type suggestion |

**Single-doc example**:

```bash
curl -X POST http://localhost:8085/extract \
  -H "Content-Type: application/json" \
  -d '{
    "source_text": "Dear Dr, on lamotrigine 75mg BID. Focal epilepsy.",
    "doc_type": "progress_note",
    "arm": "M2"
  }'
```

**CSV batch example** (rows-of-notes → tidy CSV):

```bash
curl -X POST http://localhost:8085/extract/csv \
  -H "Content-Type: text/csv" \
  --data-binary @notes.csv \
  -o phenotypes.csv
```

Input CSV columns: `text` (required; `note`, `source_text`, `clinical_note`,
`content` also accepted), plus optional `doc_id`, `patient_id`, `doc_date`,
`visit_date`, `doc_type`, `arm`.

**Chat example**:

```bash
curl -X POST http://localhost:8085/extract/chat \
  -H "Content-Type: application/json" \
  -d '{
    "source_text": "Dear Dr, seizure-free for 6 months on LTG.",
    "question": "Is the patient seizure-free?"
  }'
```

---

## Long notes and multi-visit Excel input

The extractor accepts documents longer than the model's context by chunking
on clinical section headers (HPI / Assessment / EEG / MRI / …) with paragraph-
level overlap, running one call per module per chunk, and merging with
Evidence-aware union rules.

**Free-text long note** — auto-chunks anything over 8000 chars:
```bash
curl -X POST http://localhost:8085/extract/csv -H "Content-Type: application/json" \
  -d '{"source_text": "<a very long clinic letter…>", "doc_type": "progress_note"}'
```

**Excel-per-visit longitudinal input** — one row = one visit. `visit_date` is
used as the temporal-ordering key; list fields (like `current_asms`) collapse
across visits keeping the latest visit's dose text; conflict on scalar fields
is surfaced in a `MergeReport`.

Programmatic API in `services/chunker.py` (`chunk_text`, `chunk_rows`) and
`services/merge.py` (`merge_modules`, `MergeReport`). Smoke tests:
```bash
python scripts/smoke_chunk_merge.py    # 3 scenarios: free-text, longitudinal, conflict
```

---

## Reproducing the paper's tables

Every reported table is regenerated from released run manifests without a GPU.

```bash
docker build -f Dockerfile.eval -t medai-epi:eval .
docker run --rm -v $PWD:/work medai-epi:eval \
    python -m eval.aggregator_cli --manifests /work/data/run_manifests --gold /work/data/fonferko_shadrach_2024
```

Manuscript tables and the scripts that generate them:

| Table | Script |
|---|---|
| 4a — content-validity per (arm, module) | `scripts/score_llm_arms.py` |
| 4b — per-field P/R/F1 vs silver (95% CI) | `scripts/score_llm_arms.py` |
| **4b-gold — per-field P/R/F1 vs F-S native gold** | **`scripts/score_llm_arms_vs_fs_gold.py`** |
| 4c — paired McNemar's across arms | `scripts/mcnemar_arm_comparisons.py` |
| 4d — 12-category error taxonomy | `scripts/error_taxonomy_scan.py` |
| 5 — downstream utility (drug resistance) | `scripts/utility_demo_drug_resistance.py` |
| 6 — downstream utility (seizure freedom) | `scripts/utility_demo_seizure_freedom.py` |

Scope of gold-based scoring is documented in `docs/FONFERKO_GOLD_SCOPE.md`.

---

## Requirements

**Minimum (offline components, HTTP surface, smoke tests, scoring)**:
- Python 3.9+
- ~500 MB disk for repo + deps
- No GPU required

**To run Med42-8B locally**:
- NVIDIA GPU with ≥ 16 GB VRAM (paper ran on an L40S 24 GB slice)
- CUDA 12.x drivers
- PyTorch 2.4+ with CUDA wheels (`pip install torch --index-url https://download.pytorch.org/whl/cu124`)
- Hugging Face token to download Med42-8B weights (~16 GB, one-time)

---

## Repository layout

```
schema/            v0.2.1 Pydantic ontology (6 modules + Evidence[T] wrapper)
services/          extraction pipeline, prompt registry, chunker, merger, tabular
  extract.py       three-tier repair pipeline
  prompt_registry.py 22 versioned prompts (M0/M1/M2 × 6 modules × versions)
  smart_repair.py  Evidence-wrapping + enum normalization repair
  chunker.py       section-aware and Excel-per-visit chunking
  merge.py         Evidence-aware merger with conflict reporting
  tabular.py       phenotype → long-format CSV rows
  router.py        applicability-driven multi-module extractor
routes/            Flask endpoints
  extract.py       /extract, /extract/batch, /extract/csv, /extract/chat, …
  extract_ui.py    /extract/ui (single-page research UI)
data/              silver labels, run manifests, corpora (fetched via scripts/)
scripts/           run scripts, scorers, utility demos, smoke tests
eval/              scoring library + aggregator CLI
docs/              schema, protocol, TRIPOD checklist, F-S mapping and gold scope
writing/           manuscript sources
```

---

## Citing this work

*[BibTeX to be inserted at submission.]*

License: MIT for code; fetched corpora keep their own licenses (Fonferko-
Shadrach is CC-BY 4.0, see `data/fonferko_shadrach_2024/manifest.json`).

Support: GitHub Issues on the release repository.
