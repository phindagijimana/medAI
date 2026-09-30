# US Clinical Note Preprocessing Pipeline

**Module:** `services/us_note_preprocessing.py`
**CLI:** `scripts/preprocess_us_notes.py`
**Backwards-compat shim:** `scripts/preprocess_mtsamples.py`

## Motivation

The MedCAT+Rules pipeline (arm B1') was built on the [ExECT-V2](REFERENCES.md#exect) rule vocabulary, which is anchored to UK epilepsy clinician letters (the [Fonferko-Shadrach corpus](REFERENCES.md#fonferko-shadrach)). US clinical notes differ from UK letters in three ways that can cause extraction failures even when the underlying clinical facts are identical:

1. **Section header conventions.** US templated notes use abbreviations (`CC:`, `HX:`, `PMH:`, `MEDS:`, `EXAM:`) where UK letters spell them out (`Chief Complaint:`, `History of Present Illness:`). Section-aware rules that key off canonical labels effectively hide content when the header doesn't match.
2. **Medication brand names.** US notes reach for `Keppra`, `Dilantin`, `Tegretol`, `Depakene` — brand names that are less common in UK narrative. If the concept catalogue is trained only on generic names, ~20 % of AED mentions get missed.
3. **Historical seizure descriptors.** `grand mal`, `petit mal`, `complex partial`, and `psychomotor seizures` are still in wide clinical circulation in the US, but they are not linked in the modern ILAE 2017 concept graph. A rule keyed on `focal impaired awareness` will miss `complex partial` unless someone bridges the two.

**These are format mismatches, not clinical differences.** They should not count against the extractor.

## Pipeline design

Four stages, each individually toggleable:

| Stage | What it does | Example |
|---|---|---|
| **A. Relevance scoring** | Computes an epilepsy-density score per note; filters out non-epilepsy content (default threshold: 3.0) | Stroke-only note → score 0.4 → dropped |
| **B. Section header canonicalization** | Rewrites 30+ known US abbreviations to canonical H&P labels | `CC:` → `Chief Complaint:`; `HX:` → `History of Present Illness:`; `PMH:` → `Past Medical History:` |
| **C. ILAE 2017 modernization** | Appends the modern ILAE 2017 equivalent alongside legacy terms (non-destructive) | `grand mal` → `grand mal (generalized tonic-clonic)` |
| **D. Brand-generic drug annotation** | Appends the generic name in parentheses after first brand mention per note | `Keppra` → `Keppra (levetiracetam)`; `Dilantin` → `Dilantin (phenytoin)` |

The transformations are **idempotent** — running preprocessing twice is a no-op after the first pass (each rule checks for the already-canonicalized form).

Character offsets shift after preprocessing. Downstream evidence-span extraction must run against the preprocessed text (not the raw text); the universal manifest records this via the `note_path` (preprocessed) vs `raw_source_path` (original) distinction.

## Usage

### Corpus-agnostic CLI

```bash
# MTSamples neurology, filter to epilepsy-primary (score >= 3.0)
venv-medcat/bin/python scripts/preprocess_us_notes.py \
    --layout mtsamples \
    --in-dir data/eval_corpora/mtsamples_neuro \
    --out-dir data/eval_corpora/mtsamples_neuro_preprocessed \
    --corpus mtsamples \
    --min-relevance-score 3.0

# Flat directory of *.txt (no filter)
venv-medcat/bin/python scripts/preprocess_us_notes.py \
    --layout flat \
    --in-dir data/inbox/some_us_notes \
    --out-dir data/inbox/some_us_notes_preprocessed \
    --corpus custom_v1 \
    --min-relevance-score 0.0

# Existing universal-manifest corpus (upgrade in place)
venv-medcat/bin/python scripts/preprocess_us_notes.py \
    --layout manifest \
    --in-dir data/eval_corpora/synth_v3 \
    --out-dir data/eval_corpora/synth_v3_preprocessed \
    --corpus synth_v3 \
    --min-relevance-score 0.0
```

### Programmatic use

```python
from services.us_note_preprocessing import preprocess_note

text = open("some_note.txt").read()
processed, stats = preprocess_note(text)
# stats.score, stats.n_section_headers_normalized, ...
```

## Empirical validation on MTSamples

**Setup:** 78 MTSamples neurology notes → 18 kept at score ≥ 3.0. Ran MedCAT+Rules on the 18 preprocessed docs and compared to the same 18 in the unprocessed corpus.

**Result: identical field-level extraction.**

| Field | Preprocessed | Unprocessed | Δ |
|---|---|---|---|
| `medication.current_asms` (list length) | 34 | 34 | +0 |
| `medication.trialed_asms` | 0 | 0 | +0 |
| Every other tracked field | 0 | 0 | +0 |

**Interpretation.** On this pipeline, preprocessing does **not move the needle** — because:

1. The MedCAT CDB already maps `Keppra`, `Dilantin`, `Tegretol` etc. to their concept CUIs directly, so Stage D annotation is redundant.
2. Very few current rules are gated on a specific section label, so Stage B doesn't unlock hidden content on this pipeline.
3. Stage C matters clinically but the current seizure-type rules already recognise `complex partial` via the CDB.

**Why keep the pipeline then?** Because:

- **Downstream arms benefit.** LLM prompts that request section-scoped extraction (e.g., "extract medications from the *Medications:* section only") depend on canonical headers. So does chunking by section.
- **MetaCAT training benefits.** Consistent section labels are one of the features MetaCAT can attend to for negation / experiencer / temporality classification.
- **Reproducibility.** Freezing the canonical form lets us treat "raw MTSamples" and "raw future US corpus" identically after this step.
- **Future rules.** Every section-aware rule we add later gets this for free.
- **Honest evaluation.** When a rule DOES fail, we know it's a semantic gap, not a format one.

**What the pipeline is not.** It is not a fix for a pipeline that fails on real US notes at the *semantic* level (e.g., missing risk factors, missing seizure semiology). Those are separate work items for the rules themselves.

## Adding a new rule

To handle a new US header abbreviation or brand-generic pair:

1. Edit `services/us_note_preprocessing.py`.
2. Add an entry to `_HEADER_MAP`, `_ILAE_LEGACY_TO_MODERN`, or `_BRAND_TO_GENERIC`.
3. Rerun preprocessing (the CLI is idempotent; existing outputs are overwritten).
4. If the change is corpus-specific, note it in the corpus README.

## Extending to a new corpus

If your corpus doesn't fit `mtsamples` / `flat` / `manifest` layouts, add a new loader in `scripts/preprocess_us_notes.py`:

```python
def _iter_mycorpus(in_dir: Path):
    """Yield (visit_id, patient_id, raw_text, source_metadata_dict)."""
    ...

LAYOUTS["mycorpus"] = _iter_mycorpus
```

The loader must yield tuples of `(visit_id, patient_id, raw_text, meta_dict)` where `meta_dict` passes through any fields relevant to the universal manifest schema (visit_date, note_type, care_setting, etc.).

## Related documents

- [Universal Corpus Manifest Schema](CORPUS_MANIFEST_SCHEMA.md)
- [MetaCAT Training Plan](METACAT_TRAINING_PLAN.md)
- [References](REFERENCES.md)
