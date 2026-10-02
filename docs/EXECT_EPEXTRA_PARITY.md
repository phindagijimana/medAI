# ExECT → EpExtra parity table (Paper 1 working draft)

Status: draft. The published ExECT figures are filled in (§3.2, with citations). The port classification in §2
is still provisional until a file-level code review is done; no like-for-like ExECT run exists.
Closes the gap flagged in `docs/CHAIN_OF_THREE_ALIGNMENT.md` (P2.1).

**What EpExtra is.** A Python port of the ExECT-V2 information-extraction approach for epilepsy
letters (Fonferko-Shadrach et al., ExECT v2; repository `swneurosci/ExECT-V2`, commit `c6202de`,
see `docs/EXECT_V2_STUDY.md`). ExECT runs on GATE/JAPE with Groovy serialisers. EpExtra
re-expresses the same semantics on MedCAT (dictionary linking) + spaCy `Matcher` + medspaCy
ConText + Pydantic evidence objects (`rules/jape_to_python.md`). No GATE, JAPE or Groovy is run.
In the arm roster it is **B1′**, the specialist (A) channel of LEO.

## 1. Architecture mapping

| ExECT-V2 (GATE) | EpExtra | Notes |
|---|---|---|
| JAPE phase file | one `BaseFieldRule` subclass in `rules/fields/` | many JAPE files per concept collapse into one class (union of semantics) |
| Gazetteers / `Lookup` (`epilepsy.lst`, `drugs.lst`, custom UMLS lists) | MedCAT CDB (dict linking, `primary_name_only_linker`) built from the same seed lists, then enriched from UMLS atoms | CDB 1,438 → 2,398 rows; curated codes corrected (93 rows) |
| ANNIE tokeniser, sentence splitter, time gazetteers | spaCy / medspaCy | marked SKIP in the inventory |
| Negation / hypothetical handling (JAPE phases) | medspaCy ConText (`rules/context_config*.py`) | |
| MetaCAT-style ML disambiguator (trained on SAIL data) | not used; ConText only | tested a MetaCAT variant: no gain on F-S 40 (0.8064 either way; see `docs/METACAT_EVAL.md`) |
| Groovy serialisers | `EpilepsyPhenotype.model_dump_json()` | |
| Certainty levels 1–5 | Evidence `certainty` + ValidatorVerdict in the chain | |
| UK vocabulary | `rules/uk_to_us_lexicon.py`, `rules/context_config_us.py`, `services/us_note_preprocessing.py` | US adaptation layer: **new**, not in ExECT |

## 2. Inventory coverage

From `docs/EXECT_V2_STUDY.md` (all 272 files classified, none unknown):

| ExECT files | Count | EpExtra treatment |
|---|---:|---|
| JAPE + Groovy, priority P1 (8 pilot fields) | 142 | ported first |
| priority P2 (remaining 16 fields) | 54 | ported second |
| SKIP (orchestrators, helpers, shared, unused, redundant) | 76 | replaced by medspaCy / spaCy / the pipeline entry point |
| **Total** | **272** | |

EpExtra size: 17 rule modules under `rules/fields/`, 5,916 lines (including `__init__`).

### Rule family → EpExtra module (provisional)

Classification: **Direct** = same logic re-expressed; **Modified** = same target, changed
logic (US wording, ConText, new patterns); **Rebuilt** = new implementation, ExECT used only as
a specification. All rows are **provisional**: a file-level code review has not been done, and
until it is, the column should be read as "intended", not as audited fact.

| ExECT family | EpExtra module | Provisional class |
|---|---|---|
| `Seiz*`, `SF*`, seizure frequency | `seizure_frequency.py` (680 lines) | Modified (largest module; US phrasing, period normalisation) |
| `Diag*`, `Diagnosis*` | `epilepsy_type.py`, `seizure_type.py` | Modified |
| `EpiCause*`, `Symptomatic*` | `etiology.py` | Modified |
| `Prescription*`, `Presc*`, `Drug*`, `frequency`, `doses`, `measurement` | `medication.py`, `medication_extra.py`, `rules/asm_lexicon.py` | Modified (drug lexicon rebuilt from RxNorm ATC N03A + curated) |
| `OnsetAge*`, `AgeDiagnosed*`, `DateSince*` | `onset_age.py` | Modified |
| `Investigations*`, `NegatedFinding*` | `eeg.py`, `mri.py` and `_extra` variants | Rebuilt (ExECT investigation scope differs; CT files marked UNUSED) |
| none (no ExECT equivalent) | `autoimmune.py`, `status_epilepticus.py`, `surgery.py`, `awareness.py`, `focal_onset.py`, `clinical_localization.py` | New (schema v0.2 fields beyond ExECT) |
| US layer | `us_note_structure.py`, `uk_to_us_lexicon.py` | New |

## 3. Accuracy comparison

### 3.1 EpExtra on the F-S test set (40 letters, EA0161–EA0200)

Overall micro-F1 **0.8064** (P 0.8444, R 0.7716); macro-F1 0.6473; per-document F1 median
0.857. Source: `eval/results/medcat_iterations/us_fixes_fs_test_40.summary.md`.

Scored on 24 fields against our silver labels, not against the F-S native gold. This is not
comparable to the 7-field native-gold numbers in `docs/EVAL_PROTOCOL_LEO.md` (finding F5).
Specialist on the 7 native-gold fields, 40 held-out letters: micro-F1 0.655 [0.582, 0.723].

### 3.2 What the published ExECT systems achieved

Two publications, **different data**. Do not read them as one benchmark.

| system | data | overall |
|---|---|---|
| ExECT v1 [X1] | 200 **real**, de-identified clinic letters from a Welsh health board; scored against one clinician's review | per item P 91.4, R 81.4, F1 86.1 |
| ExECT v2 [X2] | the **200 synthetic** letters released with the annotation corpus (the same F-S letters we use, EA0001–EA0200), scored against the consensus gold | per item F1 0.87, per letter F1 0.90 |

The F-S letters are therefore synthetic letters written by clinicians, not real notes. Every
result in this repository that uses them says something about synthetic UK clinic letters.

ExECT v1 per category (precision, recall; F1 computed from them) [X1]:

| ExECT v1 category | P | R | F1 | nearest EpExtra field |
|---|---:|---:|---:|---|
| epilepsy diagnosis | 88.1 | 89.0 | 88.5 | (diagnosis presence) |
| epilepsy type | 89.8 | 79.8 | 84.5 | `epilepsy_type` |
| focal seizures | 96.2 | 69.7 | 80.8 | `predominant_seizure_type` |
| generalised seizures | 88.8 | 52.3 | 65.8 | `predominant_seizure_type` |
| seizure frequency | 86.3 | 53.6 | 66.1 | `seizure_frequency.*` |
| medication | 96.1 | 94.0 | 95.0 | `medication.current_asms` |
| CT | 55.6 | 58.8 | 57.1 | no CT module in schema v0.2 |
| MRI | 82.4 | 68.8 | 75.0 | `mri.*` |
| EEG | 81.5 | 75.3 | 78.3 | `eeg.*` |

ExECT v2 per entity, F1 per item / per letter (same letters as F-S gold) [X2]: Prescription
0.87 / 0.87; Diagnosis 0.85 / 0.94; Seizure Frequency 0.66 / 0.68; Investigations 0.95 / 0.95;
Onset 0.96 / 0.95; Epilepsy Cause 0.90 / 0.92; overall 0.87 / 0.90. Human inter-annotator
agreement on the same corpus: overall F1 0.73 (Prescriptions 0.87, Seizure Frequency 0.47).

EpExtra on the F-S 40 test letters, 24-field silver scoring, by field:

| field | n docs | P | R | F1 |
|---|---:|---:|---:|---:|
| `epilepsy_type` | 17 | 1.000 | 0.941 | 0.970 |
| `semiology_text` | 33 | 1.000 | 1.000 | 1.000 |
| `seizure_frequency.count_min` | 4 | 1.000 | 1.000 | 1.000 |
| `seizure_frequency.count_max` | 4 | 0.750 | 0.750 | 0.750 |
| `seizure_frequency.period` | 12 | 0.833 | 0.417 | 0.556 |
| `seizure_frequency.seizure_free` | 29 | 0.897 | 0.897 | 0.897 |
| `predominant_seizure_type` | 21 | 0.579 | 0.524 | 0.550 |
| `other_seizure_types` | 5 | 0.000 | 0.000 | 0.000 |
| `age_at_onset_years` | 4 | 1.000 | 0.750 | 0.857 |
| `etiology_category` | 5 | 0.600 | 0.600 | 0.600 |
| `medication.current_asms` | 32 | 0.807 | 0.868 | 0.836 |
| `medication.prior_asms` | 6 | 0.500 | 0.333 | 0.400 |
| `medication.failed_asms` | 1 | 0.000 | 0.000 | 0.000 |

Small n on several rows (1 to 6 documents): F1 there is anecdotal.

### 3.3 Reading the two together

| area | ExECT v2 (synthetic 200, per item) | EpExtra (F-S 40, silver) | comment |
|---|---:|---:|---|
| medication | 0.87 | 0.836 (current ASMs) | comparable to v2, below v1's 0.95 on real letters; v2's "Prescription" includes dose and frequency, ours is the drug name |
| seizure frequency | 0.66 | 0.556 (period) to 1.0 (count_min) | both weak; frequency is hard for humans too (IAA 0.47) |
| epilepsy type | 0.85 (diagnosis, v2) | 0.970 | different definitions; ours is a closed enum on 17 letters |
| seizure type | n/a | 0.550 | EpExtra's weakest main field; matches the weak retrieval result |

Honest summary: EpExtra is in the range of ExECT on the fields where the definitions line up,
and has not been shown to exceed it. A like-for-like comparison needs ExECT v2 run on the same
40 letters with the same scorer; the GATE pipeline is public (`swneurosci/ExECT-V2`) but has
not been run here.

References for this section (full entries in `docs/REFERENCES.md`):
[X1] Fonferko-Shadrach B, et al. Using natural language processing to extract structured epilepsy
data from unstructured clinic letters: development and validation of the ExECT system. *BMJ Open*
2019;9(4):e023232. https://bmjopen.bmj.com/content/9/4/e023232
[X2] Fonferko-Shadrach B, et al. Annotation of epilepsy clinic letters for natural language
processing. *J Biomed Semantics* 2024. https://link.springer.com/article/10.1186/s13326-024-00316-z
(corpus on Zenodo: 10.5281/zenodo.8381079; JSON annotations 10.5281/zenodo.8356493).

## 4. Portability failure taxonomy (UK letters → US notes)

Observed or documented in this repository; the unmeasured items need the US set
(`docs/US_ANNOTATION_PLAN.md`).

| class | example | status |
|---|---|---|
| Vocabulary | "generalised" vs "generalized", "Keppra" vs "levetiracetam", UK drug names | handled by `uk_to_us_lexicon.py`; brand / misspelling gaps remain in retrieval (`docs/CONCEPT_GOLD_SET.md` §3) |
| Document structure | letters vs templated Epic notes with problem lists, med lists, copy-forward text | preprocessor `us_note_preprocessing.py`; unquantified on real notes |
| Copy-forward / stale text | old medication lists repeated in new notes | **not measured**; risk to `current_asms` precision |
| Negation / experiencer | family history ("mother had seizures") | ConText; silver-labelled only |
| Scorer / label mismatch | silver labels made on raw notes vs preprocessed text | MTSamples F1 0.513 vs F-S 0.806 is partly real, partly silver mismatch (`docs/medai_target.md`) |
| Frequency phrasing | "2 per month", "1-2 a week", "seizure free since 2021" | `seizure_frequency.period` recall 0.417, the weakest numeric field |
| Seizure-type granularity | ILAE 2017 vs older terms; "focal onset", "epileptic" | `predominant_seizure_type` F1 0.550; also weakest retrieval field |

## 5. Claims this table can and cannot support

Can: EpExtra reaches 0.806 micro-F1 on the 24-field silver F-S 40 set with a rule-and-dictionary
design that needs no GPU and no training data. Cannot (yet): that EpExtra matches or exceeds
original ExECT (no like-for-like run), or that it works on US notes (no clinician gold).
