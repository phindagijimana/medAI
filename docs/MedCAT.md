# MedCAT + Rules Pipeline (arm B1') — Full Build Plan

**Status (2026-10-01):** Phases 0-8 and 1d COMPLETE. Phase 9 manuscript integration in progress. Phases 6d, 6e, 6f PENDING external approvals.
**Owner:** MedAI-EPI team
**Estimated effort:** ~19 working days end-to-end; first F1 measurement at Day 11
**Scope:** all 24 v0.2.1 enums, 6 evaluation corpora
**F1 target on F-S 40 held-out:** 0.72-0.85 — **ACHIEVED at F1=0.8053 [95 % CI 0.762, 0.848] (Phase 8, 2026-09-29)**; 0.60-0.75 on US corpora (secondary; synth-v1 F1=0.8189 [0.795, 0.841])

## Phase completion status (roll-up, 2026-09-29)

| Phase | Description | Status | Landing date |
|---|---|---|---|
| 0 | Setup & study (ExECT-V2 clone, ILAE XLSX, venv) | **DONE** | 2026-09-22 |
| 1a | Extract CUI seed from ExECT dictionaries | **DONE** | 2026-09-23 |
| 1b | Re-derive synonyms from public sources | **DONE** | 2026-09-23 |
| 1c | MedCAT CDB build + UMLS-Small fallback | **DONE** (custom CDB only — the UMLS-Small fallback hook exists in `services/medcat_extractor.py` but no pack is downloaded or passed in production) | 2026-09-24 |
| 1d | UMLS-Full enrichment | **DONE** — via UTS REST API, not a Metathesaurus download: 152 CUIs → +1,055 synonyms, +36 SCTIDs; CDB 1,438 → 2,398 rows. F1 unchanged (0.8064 F-S 40). Commit `60e1c54` | 2026-09-29 |
| 1e | Pinned local ontology releases | **DONE** — HPO, MONDO, EPIO, SNOMED CT US, RxNorm full in `data/ontologies/` (`scripts/fetch_ontologies.py`, `MANIFEST.json`) | 2026-10-01 |
| 2 | Rule translation infrastructure | **DONE** | 2026-09-24 |
| 3a | Field-rule port P1 (8 pilot fields) | **DONE** | 2026-09-25 |
| 3b | Field-rule port P2 (16 extra fields) | **DONE** | 2026-09-26 |
| 4 | US adaptation layer | **DONE** | 2026-09-26 |
| 5 | Compound / relational rules | **DONE** | 2026-09-27 |
| 6a | F-S 40 held-out corpus | **DONE** | already prepared |
| 6b | MTSamples neurology (US silver) | **PENDING** — corpus fetched (78 notes); silver labels not yet generated |
| 6c | Synth-v1 held-out 100 | **DONE** | 2026-09-27 |
| 6d | n2c2 2019 family history | **PENDING** — Harvard DBMI DUA pending |
| 6e | n2c2 2018 medication + ADE | **PENDING** — Harvard DBMI DUA pending |
| 6f | MIMIC-IV epilepsy 500 | **PENDING** — PhysioNet + CITI credentialing pending |
| 7 | Scoring & evaluation (first F1) | **DONE** | 2026-09-28 (F-S F1 baseline = 0.5627) |
| 8 | Error-driven refinement (3 iterations) | **DONE** | 2026-09-29 (F-S F1 final = 0.8053; synth-v1 = 0.8189) |
| 9 | Manuscript v0.5 integration | **IN PROGRESS** | (this document — expected 2026-09-30) |

**Bootstrap-CI reproduction:** `venv-medcat/bin/python scripts/bootstrap_ci_medcat.py --perdoc eval/results/medcat_iterations/iter3_fs_test_40.perdoc.csv --n-boot 1000 --seed 0` yields F1 = 0.8053 [95 % CI 0.7622, 0.8477]; same command with the synth-v1 perdoc CSV yields F1 = 0.8189 [0.7949, 0.8413].

## 1. Goal

Ship a reproducible US-adapted MedCAT + rules pipeline that consumes free-text clinical notes and emits `EpilepsyPhenotype` JSON conforming to v0.2.1 (all 24 enums, 7 module classes). Pipeline is informed by ExECT-V2 (Fonferko-Shadrach 2019/2024) but reimplemented independently in Python; ports rule *logic* rather than copying code.

This is arm **B1'** in the paper's comparison table — a specialized rule-based baseline that sits between B0 (trivial regex) and the frontier LLM comparators (F0 GPT, F1 DeepSeek) and our fine-tuned Med42 (M4 family).

## 2. Non-goals

- Not a deployment-grade clinical tool (research use only, per project charter).
- Not a fork of ExECT-V2 — no verbatim JAPE / Groovy code in our tree.
- Not a MetaCAT re-training exercise for v1 (we use pretrained MIMIC MetaCATs and accept ~10% negation misfires).
- Not a full 30-field extraction on iteration 1; P1 (8 pilot-populated fields) is the minimum viable milestone.

## 3. Primary references

- Fonferko-Shadrach et al. 2019, BMC Med Res Methodol — ExECT v1 pipeline paper
- Fonferko-Shadrach et al. 2024, J Biomed Semantics — ExECT-V2 annotation paper
- ExECT-V2 repo: [github.com/swneurosci/ExECT-V2](https://github.com/swneurosci/ExECT-V2)
- Kraljevic et al. 2021 — MedCAT foundation paper
- Eyre et al. 2021 — medspaCy US-tuned ConText
- ILAE 2017 classification (Fisher et al.) + ILAE 2025 update
- ILAE 2010 drug-resistance definition (Kwan et al.)
- NINDS Common Data Elements for Epilepsy
- Engel 1993 + Wieser 2001 — surgery outcome scales
- Graus 2016 — autoimmune encephalitis criteria (for CausativeAntibody enum)

## 4. Timeline summary

| Day | Phase | Landmark |
|---|---|---|
| 0 | 0 setup | UMLS + PhysioNet + Harvard DBMI registrations submitted (parallel) |
| 1 | 0 finish | ExECT-V2 cloned locally, ILAE XLSX extracted, env installed |
| 1 | 1a extract | ExECT CUI seed extracted → `references/exect_v2_cui_seed.csv` |
| 1-2 | 1b synonyms | Public-source synonym enrichment → `rules/epilepsy_ontology.py` populated |
| 3 | 1c CDB | Custom CDB + UMLS-Small fallback linker wired |
| X | 1d UMLS enrich | +3-5% F1 whenever license clears |
| 3-4 | 2 infra | JAPE→Python translator, medspaCy config, `medcat_extractor.py` runs on one letter |
| 4-9 | 3 field port | ~200 rules ported, P1 fields first (Days 4-6), P2 fields next (Days 7-8) |
| 9-10 | 4 US adapt | UK→US lexicon, SOAP section detection, US context triggers |
| 10-11 | 5 compound | Compound-field Python functions |
| 0-14 | 6 corpora | Six-corpus prep runs in parallel (corpora ready as DUAs land) |
| 11-12 | 7 score | First F1 across all available corpora |
| 12-14 | 8 refine | 3 iteration passes |
| 14-17 | 9 write-up | Manuscript v0.5 additions with B1' row + cross-corpus table |
| 17-19 | buffer | Two-day slack for MIMIC + n2c2 corpora landing late |

Critical path: MIMIC-IV DUA (~2 weeks). Non-blocking — the plan produces F1 numbers on the four corpora that don't require DUA (F-S, MTSamples, Synth-v1, MTSamples-silver) at Day 11 regardless. MIMIC and n2c2 fold in as amendment as DUAs land.

## 5. Registration checklist

All three registrations initiated in parallel because they are the longest lead times.

- [x] **UMLS Metathesaurus License** — [uts.nlm.nih.gov](https://uts.nlm.nih.gov) — **approved**; API key in `.env` as `UMLS_APIKEY`. **Did NOT block Phase 1** — see Phase 1a below (reference-only path using ExECT's public UMLS-derived dictionaries + BioPortal SNOMED browser + published ILAE codes). UMLS enrichment folds in at Phase 1d whenever license clears.
- [ ] **PhysioNet Credentialing + CITI course** — [physionet.org](https://physionet.org) — CITI ~4 h, credentialing 1-2 weeks. Blocks Phase 6f (MIMIC-IV) only.
- [ ] **Harvard DBMI Portal** — [portal.dbmi.hms.harvard.edu](https://portal.dbmi.hms.harvard.edu) — DUA per challenge, ~1-2 weeks. Blocks Phase 6d + 6e (n2c2 2018/2019) only.

**Nothing on the critical path is blocked by any pending registration.** Corpora 6a (F-S), 6b (MTSamples), 6c (Synth-v1) alone deliver a 3-corpus F1 measurement at Day 11. DUA-gated corpora fold in as they land.

## 6. Phased build plan

### Phase 0 — Setup & study (Days 0-1)

**Deliverables:**
- `references/exect_v2/` — local clone, `.gitignored` (study only, never re-committed)
- `references/exect_v2_ilae_map.csv` — CSV export of `Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx`
- `docs/EXECT_V2_STUDY.md` — inventory of ~30 JAPE files + ~24 Groovy scripts, tagged with which of our schema fields they map to
- `venv-medcat/` — isolated Python 3.10 with `medcat[all]`, `medspacy`, `spacy`, `pandas`, `openpyxl`, `rxnorm-tools`

**Actions:**
1. Clone ExECT-V2 to `references/exect_v2/` (local, not committed)
2. Add `references/` to `.gitignore`
3. Extract annotation-guidelines DOCX text → `docs/EXECT_V2_ANNOTATION_GUIDELINES_NOTES.md`
4. Export ILAE XLSX to CSV via openpyxl script (one-off)
5. `python -m venv venv-medcat && source venv-medcat/bin/activate && pip install medcat[all] medspacy spacy pandas openpyxl`
6. Smoke-test: `python -c "from medcat.cat import CAT; from medspacy.context import ConTextComponent; print('ok')"`

**Acceptance:**
- Import smoke test passes.
- `docs/EXECT_V2_STUDY.md` maps every JAPE+Groovy file to one of our schema fields (or `UNUSED` if not applicable).

### Phase 1 — Ontology & concept database (Days 1-3, + Day X for UMLS enrichment)

**Design principle:** UMLS license is submitted but not required for MVP. Phase 1 splits into three sub-phases (1a, 1b, 1c) that produce a fully working ontology WITHOUT the UMLS license, plus one enrichment sub-phase (1d) that runs whenever the license clears.

**Deliverables (end-state):**
- `rules/epilepsy_ontology.py` — Python module with 24 mapping tables, one per enum
- `data/medcat_cdb_epilepsy/` — MedCAT CDB filtered to ~3-5k SNOMED-CT concepts (US Edition)
- `scripts/build_medcat_cdb_epilepsy.py` — reproducible CDB builder
- `scripts/enrich_ontology_from_umls.py` — one-shot UMLS-Full enrichment (runs at Phase 1d)
- `tests/test_epilepsy_ontology.py` — verifies every enum value has ≥1 CUI or `RULES_ONLY` flag

**All 24 enums to map (categorized by data source):**

| Category | Enums | Primary source (Phase 1a-c, no UMLS) |
|---|---|---|
| Typology (5) | SeizureType, EpilepsyType, EtiologyCategory, DocumentType, TemporalStatus | ExECT `ILAE proposed map to UMLS and SNOMEDCT.xlsx` (published data) + ILAE 2017 paper appendix |
| Localization (4) | Awareness, Laterality, LobarLocalization, LocalizationSource | ILAE XLSX + BioPortal SNOMED anatomy browser |
| Semiology (2) | FocalMotorOnset, FocalNonmotorOnset | ILAE 2017 semiology hierarchy (Fisher et al. paper) |
| EEG (3) | EegStudyType, EegBackground, IedType | ExECT `EEG_results.lst` (public GitHub) + ACNS guideline docs |
| Imaging (1) | MriFinding | ExECT `ct_mri_results.lst` (public GitHub) |
| Treatment / outcome (7) | MedicationStatus, DrugResistanceStatus, SurgeryType, EngelClass, IlaeOutcome, NonDrugTherapyType, CausativeAntibody | RxNorm (free NLM download, no UMLS license needed) + Engel 1993 paper + Graus 2016 paper |
| Meta (2) | Certainty, ConcordanceStatus | Rules-only (derived, not linked) |

Enums with `RULES_ONLY` values: Certainty, ConcordanceStatus, TemporalStatus, DrugResistanceStatus, Engel/IlaeOutcome (all derived from Python logic on linked concepts, not linked directly).

**Sourcing pass for ExECT-uncovered enums:**
- Engel / ILAE outcome scales → hand-map from Engel 1993 + Wieser 2001 papers (~10 codes, all public)
- CausativeAntibody → NMDA-R, LGI1, CASPR2, GAD65, GABA-B, AMPA-R, glycine-R, DPPX (~10 antibodies with CUIs from Graus 2016 paper, all public)
- NonDrugTherapyType → VNS, RNS, DBS, ketogenic diet, MAD, corpus callosotomy, hemispherectomy (~8 codes, hand-mapped from SNOMED browser)

#### Phase 1a — Extract concept structure from ExECT (Day 1, no UMLS needed)

Read ExECT's public GitHub files as **reference for what CUIs to include**, not as verbatim import. The concept-selection work in these files is exactly what we need; we re-verify each CUI from public sources.

**Actions:**
- Parse `Other/CustomUMLS/custom_umls.txt` — extract the ~500 unique CUIs used
- Parse `epilepsy.txt`, `seizure.txt`, `seizureSlang.txt`, `anticonvultants.txt`, `drugs.txt`, `comorbidities.txt` for per-category CUIs
- Output: `references/exect_v2_cui_seed.csv` — one row per (CUI, category, ExECT-file-source)

**Legal framing:** the CUI *list itself* mirrors the ILAE XLSX (which is published, un-restricted). Redistribution of ExECT's synonym mappings is the gray-area part; we do NOT redistribute those — we re-derive synonyms in Phase 1b.

**Deliverable:** `references/exect_v2_cui_seed.csv` — ~500 rows.

#### Phase 1b — Re-derive synonyms from public sources (Days 1-2, no UMLS needed)

For each CUI in the seed CSV, pull synonyms from public sources:

**Sources (all free, no UMLS license required):**
- **BioPortal SNOMED-CT browser** — [browser.ihtsdotools.org](https://browser.ihtsdotools.org) — programmatic lookup for each SCTID → preferred term + all synonyms
- **NINDS Common Data Elements** — [commondataelements.ninds.nih.gov](https://commondataelements.ninds.nih.gov) — canonical US clinical research phrasing per enum value
- **ILAE 2017 Fisher et al.** paper appendix — SNOMED codes for classification terms
- **Wikidata SNOMED-CT mappings** — public factual data with cross-references
- **RxNorm** — [rxnav.nlm.nih.gov](https://rxnav.nlm.nih.gov) — free NLM drug vocabulary, no UMLS needed
- **F-S 160 train corpus data mining** — for every gold value, grep the note for surface forms → add to synonyms

**Deliverable:** `rules/epilepsy_ontology.py` populated with 240+ `(enum, value) → {sctid, cui, label, synonyms[]}` triples, each synonym sourced from a public reference documented inline.

**Effort:** ~1.5 days.

#### Phase 1c — MedCAT CDB build + public UMLS-Small fallback (Day 3, no UMLS needed)

- Build custom CDB from `rules/epilepsy_ontology.py` mappings (~500 concepts curated)
- Download MedCAT's **public pretrained UMLS-Small CDB** (CogStack distributes it under permissive terms, no NLM license required) as a fallback linker for concepts we did not hand-map
- Wire two-tier linker in `services/medcat_extractor.py`: try custom CDB first, fall back to UMLS-Small for unmatched spans

**Deliverable:** working CDB at `data/medcat_cdb_epilepsy/`; pipeline runs end-to-end.

#### Phase 1d — UMLS-Full enrichment (whenever license clears, +1 day)

When UMLS license is approved (uts.nlm.nih.gov ticket clears), run one-shot enrichment:

**Actions:**
- Download UMLS Metathesaurus full release
- Run `scripts/enrich_ontology_from_umls.py`: for each of our ~500 CUIs, pull all UMLS-Full synonyms + related concepts
- Merge into `rules/epilepsy_ontology.py` (versioned diff — before/after)
- Rebuild CDB
- Re-run scorer; measure F1 delta

**Expected effect:** +3-5% F1 on all corpora (mostly on rare-synonym cases).

**Non-critical path:** if UMLS never clears, we ship at Phase 1c quality. Expected F1 range 0.68-0.82 on F-S 40 without UMLS; 0.72-0.85 with UMLS-Full.

**Outcome (2026-09-29, commit `60e1c54`):** run through the UTS REST API rather than a Metathesaurus download (`.cache/umls_api/`, sources SNOMEDCT_US, RXNORM, MSH, HPO, ICD10CM). +1,055 synonyms and +36 SCTIDs applied via `rules/epilepsy_ontology_umls_overrides.py`; CDB 1,438 → 2,398 rows. The predicted +3-5 % F1 did **not** materialise: F-S 40 stayed at 0.8064 and synth-v1 at 0.8236, because the remaining errors are compound-rule, temporality and annotation-convention errors rather than vocabulary gaps. Expected pay-off is on real US notes. Full local releases (Phase 1e) are now pinned in `data/ontologies/`; the enrichers read from there.

**Correction (2026-10-01):** auditing the curated codes against the pinned releases (`scripts/audit_curated_codes.py`) showed that 20 curated UMLS CUIs point at unrelated concepts. Examples: `aware` → "Structure of cerebral vein", `progress_note` → "Virgin", `neurocysticercosis` → "Benign neonatal epilepsies". The enrichment had copied those concepts' names in as synonyms, so MedCAT was detecting "benign neonatal convulsions" as neurocysticercosis. `apply_umls_enrichment.py` now drops patches whose synonyms share no word with the entry and only fills SCTIDs whose SNOMED name relates to the entry. Regenerating removed 138 synonyms and 8 SCTIDs; the CDB rebuilt to `data/medcat_cdb_epilepsy_v2/` has 2,319 rows. F-S 40 and synth-v1 predictions are byte-identical to the old CDB. The wrong CUIs themselves, and 59 bad curated SCTIDs, still need fixing in `rules/epilepsy_ontology.py`; see `data/curated/curated_code_known_issues.json`. `anti_nmdar` and `procedure_seeg` share CUI C4517211, so MedCAT cannot tell them apart.

**Fixed (2026-10-01, later):** all curated codes corrected from the pinned releases. The corrections are in `data/curated/curated_code_corrections.csv` (93 rows, each with source and reason) and are applied by `scripts/apply_curated_code_corrections.py`. The audit now reports 0 issues. `anti_nmdar` is now C2919931 and `procedure_seeg` C5396675. The rebuilt CDB is now the default `data/medcat_cdb_epilepsy/` (2,406 rows); the previous one is archived at `data/medcat_cdb_epilepsy_archive_20260930/`. F-S 40 is 0.8064 and synth-v1 0.8192. That is the same as the 2026-10-01 baseline before these changes; the 0.8236 recorded above was measured on an earlier revision. Sources and citations are in `docs/ONTOLOGY_SOURCES.md`.

**MetaCAT (2026-10-01):** the job-159296 models were evaluated end to end and are not adopted (`docs/METACAT_EVAL.md`). This also fixed `services/metacat_backend.py`, which had never applied a prediction because of MedCAT 2.9 API drift, and recovered the label maps that MedCAT 2.9 fails to save.

**Acceptance (Phase 1 overall):**
- CDB builds without warnings.
- 240+ `(enum, value) → {sctid, cui, label, synonyms}` triples in `epilepsy_ontology.py`.
- `pytest tests/test_epilepsy_ontology.py` passes: every enum value has ≥1 CUI or explicit `RULES_ONLY` flag.
- Every synonym has a public-source citation in the docstring (BioPortal, NINDS, ILAE paper, RxNorm, or F-S train-corpus mined).

### Phase 2 — Rule translation infrastructure (Days 3-4)

**Deliverables:**
- `rules/jape_to_python.md` — one-page cheatsheet mapping JAPE constructs to spaCy Matcher / Python
- `rules/base_rule.py` — abstract base class: input `List[MedCATEntity]` + doc + ConText attrs, output `Evidence[T]`
- `rules/context_config.py` — medspaCy ConText config, US-tuned, incorporating ExECT-V2 UK triggers as fallback set
- `services/medcat_extractor.py` — end-to-end pipeline wrapper

**JAPE → Python translation table:**

| JAPE | Python/spaCy |
|---|---|
| `Rule: X ({Token.string == "foo"}):match --> :match.Y = ...` | `Matcher.add("X", [[{"LOWER": "foo"}]])` + callback |
| `Lookup.majorType == "epilepsy"` | Filter on `medcat_ent.type_ids ∈ {epilepsy CUIs}` |
| `MacroName` (JAPE macros) | Python helper function |
| `Split` / `SplitSentence` | `spacy.doc.sents` |
| ConText features (Negation, Historical, Hypothetical, Experiencer) | medspaCy `Doc._.context` |
| Groovy serializer | Python `Evidence[T]` construction |

**Pipeline architecture (`services/medcat_extractor.py`):**
1. Text → medspaCy sentence segmentation + SOAP section detection
2. Section-aware concept linking via MedCAT CDB
3. medspaCy ConText pass (negation / temporality / hypothetical / experiencer)
4. Field-specific rule dispatch (one rule module per schema field)
5. Compound-rule pass (multi-entity composition)
6. Evidence[T] wrapping with `char_start`/`char_end` from spaCy spans
7. Module assembly → `EpilepsyPhenotype` return

**Acceptance:**
- Pipeline runs end-to-end on one F-S train letter without crashing.
- Produces valid (possibly empty) `EpilepsyPhenotype` that passes Pydantic validation.

### Phase 3 — Field-by-field rule port (Days 4-9)

**Total scope:** ~200 rules across 16 files in `rules/fields/`.

#### Priority 1 (Days 4-6) — 8 pilot-populated fields

| Field | ExECT-V2 source | Est. rules | Hours |
|---|---|---|---|
| `clinical_seizure.type` (SeizureType) | `jape/seizurechange.jape` + Groovy | ~25 | 6 |
| `clinical_seizure.frequency` (SeizureFrequency) | `jape/seizure-frequency*.jape` (4 files, 82 KB total) | ~35 | 8 |
| `clinical_seizure.onset_age` | `jape/times.jape`, `Groovy/Onset.groovy`, `Groovy/WhenDiagnosed.groovy` | ~10 | 3 |
| `epilepsy.type` (EpilepsyType) | `Groovy/Diagnosis.groovy` + ILAE XLSX decision tree | ~8 | 2 |
| `epilepsy.etiology` (EtiologyCategory) | `Groovy/EpilepsyCause.groovy` | ~15 | 4 |
| `medication.name` + `dose` + `frequency` | `jape/prescription*.jape` (7 files) + `Groovy/Prescription*.groovy` | ~30 | 6 |
| `mri.findings` (MriFinding) | `jape/investigations.jape`, `Groovy/Investigations.groovy`, `ct_mri_results.lst` | ~15 | 4 |
| `eeg.findings` (EegBackground + IedType) | `jape/investigations.jape`, `Groovy/Investigations.groovy`, `EEG_results.lst` | ~12 | 3 |

Subtotal: ~150 rules, ~36 hours

#### Priority 2 (Days 7-8) — remaining 16 schema fields

| Field | Source | Est. rules | Hours |
|---|---|---|---|
| `family_history` | `Groovy/PatientHistory.groovy` + medspaCy Family triggers | ~8 | 2 |
| `birth_history` | `Groovy/BirthHistory.groovy` | ~5 | 1 |
| `comorbidities` | `Other/CustomUMLS/comorbidities.txt` (53 KB dictionary) → CDB whitelist + concept linker | ~10 | 3 |
| `imaging.performed` (bool) | Investigations JAPE | ~3 | 1 |
| `eeg.performed` (bool) | Investigations JAPE | ~3 | 1 |
| `clinical_localization.*` (LobarLocalization, Laterality) | ILAE XLSX + SNOMED anatomy hierarchy | ~15 | 4 |
| `medication.status` (MedicationStatus) | Prescription JAPE + tense.jape | ~5 | 1 |
| Surgery history fields (SurgeryType, EngelClass, IlaeOutcome) | No ExECT source — write from scratch using Engel 1993 vocab | ~10 | 3 |
| Non-drug therapy (VNS, RNS, DBS, ketogenic) | No ExECT source — device / diet vocab | ~5 | 2 |
| Autoimmune antibody (CausativeAntibody) | No ExECT source — Graus 2016 panel | ~5 | 2 |

Subtotal: ~70 rules, ~20 hours

**Provenance convention:** every rule file starts with a docstring block like:
```python
"""
seizure_type.py — SeizureType enum extraction.

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- jape/seizurechange.jape L23-L89 → focal-to-bilateral-TC detection
- Groovy/MarkupSeizureFrequency.groovy → sentence-scope handling
- Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx → CUI mappings

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.
Cite: Fonferko-Shadrach et al. 2019 BMC Med Res Methodol; 2024 J Biomed Semantics.
"""
```

**Acceptance:**
- Each field rule has a `pytest` test using 5 F-S 160 *train* letters (not test) — passes with ≥80% precision on training subset.
- `rules/registry.py` dispatches doc entities to relevant field rules.

### Phase 4 — US adaptation layer (Days 9-10)

**Deliverables:**
- `rules/uk_to_us_lexicon.py` — spelling + drug-name normalization pass
- `rules/us_note_structure.py` — SOAP section detector
- `rules/context_config_us.py` — merged UK+US ConText triggers

**UK → US spelling table (~50 entries):**
paediatric→pediatric, oesophageal→esophageal, haemorrhage→hemorrhage, foetal→fetal, oedema→edema, anaesthesia→anesthesia, tumour→tumor, behaviour→behavior, orthopaedic→orthopedic, etc.

**UK → US drug names (RxNorm crosswalk, ~15 entries):**
phenobarbitone→phenobarbital, adrenaline→epinephrine (edge), sodium valproate→valproic acid (formulation), etc. Most AEDs share names (levetiracetam, lamotrigine, carbamazepine).

**SOAP section triggers:**
`SUBJECTIVE:`, `OBJECTIVE:`, `ASSESSMENT:`, `PLAN:`, `HPI:`, `PMH:`, `PSH:`, `HISTORY OF PRESENT ILLNESS:`, `PAST MEDICAL HISTORY:`, `MEDICATIONS:`, `REVIEW OF SYSTEMS:`, `PHYSICAL EXAM:`, `IMPRESSION:`, `RECOMMENDATIONS:`.

**US ConText triggers (added to ExECT-V2 UK set):**
`s/p`, `r/o`, `hx of`, `denies`, `w/o`, `-ve`, `no evidence of`, `no signs of`, `pt reports no`, `unremarkable`, `WNL`.

**Acceptance:**
- Pipeline runs on 5 F-S letters, 5 MTSamples notes, 5 synth-v1 notes — 15/15 produce non-empty extractions on at least one field.

### Phase 5 — Compound / relational rules (Days 10-11)

**Deliverables:** `rules/compound.py` with ~10 functions.

| Compound field | Logic sketch | Source of truth |
|---|---|---|
| `epilepsy.drug_resistance` (DrugResistanceStatus) | Count of AEDs tried at adequate dose+duration + current breakthrough seizures | ILAE 2010 Kwan definition |
| `epilepsy.duration_years` | current_year - onset_year | Arithmetic |
| `medication[i].currently_taking` | Past-tense trigger + AED → False; else True | medspaCy Temporality |
| `epilepsy.classification_full` | Combine seizure.type + onset + awareness → ILAE 2017 leaf | ILAE XLSX tree |
| `clinical_seizure.free_since_date` | AED + latest seizure date + current visit date | Composed entities |
| `focal_to_bilateral_tc` special case | Focal-onset + GTC within N sentences, both non-negated | `jape/seizurechange.jape` logic |
| `clinical_localization.concordance` (ConcordanceStatus) | Compare EEG-localization vs MRI-localization vs semiology | Multi-source rule |
| `surgery_outcome_class` (Engel / ILAE mapping) | Post-op seizure frequency + duration → Engel/ILAE code | Engel 1993 |
| `autoimmune_epilepsy_probable` | Antibody positive + subacute onset + AED-refractory | Graus 2016 |
| `polytherapy_flag` | Count of concurrent AEDs ≥ 2 | Count |

**Acceptance:** each function has ≥3 pytest cases (positive, negative, ambiguous).

### Phase 6 — Corpus preparation (parallel, Days 0-14)

Six corpora. Each yields `data/eval_corpora/<name>/` + `data/eval_corpora/<name>_gold.json`.

#### 6a. F-S 40 held-out (UK real gold) — Day 0

**Status:** already prepared.
**Action:** none.

#### 6b. MTSamples neurology (US silver gold) — Days 3-5

**Deliverables:**
- `scripts/fetch_mtsamples_neuro.py` — scrapes mtsamples.com neurology section (rate-limited, attribution)
- `data/eval_corpora/mtsamples_neuro/` — ~100 notes filtered for epilepsy/seizure keywords
- `data/eval_corpora/mtsamples_neuro_gold_silver.json` — GPT-5.6-terra silver labels (research-only OpenAI use)
- Human-review ~10 notes → `data/eval_corpora/mtsamples_neuro_gold_human10.json`

**Acceptance:** 100 notes; silver-vs-human agreement ≥85% on populated fields.

#### 6c. Synth-v1 held-out 100 (our synthetic corpus) — Days 2-3

**Deliverables:**
- `data/eval_corpora/synth_v1_eval_100/` — 100-pair subset disjoint from LoRA training patients
- `data/eval_corpora/synth_v1_eval_100_gold.json` — already available via semantic-plan-to-Evidence converter

**Acceptance:** patient-ID disjoint from `data/synth_v1_train_patients.txt`.

#### 6d. n2c2 2019 Family History (US real gold, family_history field) — Days 5-9

**Prerequisite:** Harvard DBMI DUA (Day 0 kickoff, ~1-2 wk).

**Deliverables:**
- `scripts/fetch_n2c2_2019.py` — pulls corpus after DUA approval
- `data/eval_corpora/n2c2_2019_family_hx/` — 216 notes
- Note: gold is for family-history annotations only, not our full schema — so this is a *field-level* validation for `family_history`

**Acceptance:** DUA landed; corpus filtered; scorer runs on `family_history` field only.

#### 6e. n2c2 2018 Medication + ADE (US real gold, medication module) — Days 5-9

**Prerequisite:** Harvard DBMI DUA (same portal).

**Deliverables:**
- `scripts/fetch_n2c2_2018.py`
- `data/eval_corpora/n2c2_2018_medication/` — 505 discharge summaries
- Gold is medication + ADE — *field-level* validation for `medication.*`

**Acceptance:** scorer runs on medication fields only.

#### 6f. MIMIC-IV epilepsy 500 (US real narrative notes, DIY gold on 40) — Days 0-17

**Prerequisite:** PhysioNet + CITI (Day 0 kickoff, ~2 wk).

**Deliverables:**
- `scripts/mimic_iv_extract_epilepsy_subset.py` — filter discharge summaries with ICD-10 G40.* or epilepsy/seizure in text
- `data/eval_corpora/mimic_iv_epilepsy_500/` — 500 de-identified discharge summaries
- `data/eval_corpora/mimic_iv_gold_40.json` — 40 human-annotated notes (~40 clinician-hours)
- `data/eval_corpora/mimic_iv_silver_460.json` — GPT-5.6-terra silver labels on remaining 460

**Two-tier evaluation for the paper:**
- Primary: 40 human-gold notes → F1 headline
- Secondary: 460 silver-gold, LLM-vs-rules agreement as proxy

**Acceptance:** DUA approved, 500 notes filtered, 40 human-annotated, inter-annotator κ reported.

### Phase 7 — Scoring & evaluation (Days 11-12)

**Deliverables:**
- `scripts/run_medcat_rules_on_corpus.py` — corpus-agnostic runner (`--corpus {fs_test|mtsamples|synth_v1|n2c2_2018|n2c2_2019|mimic_iv}`)
- `scripts/score_medcat_vs_gold.py` — wraps existing `score_llm_arms_vs_fs_gold.py` and `score_med42_on_pilot.py` for arm B1'
- `eval/results/medcat_rules_all_corpora.csv` — per-arm × per-corpus × per-field F1
- `eval/results/medcat_error_taxonomy.md` — first-pass error categorization

**Acceptance:**
- 6-corpus × per-field F1 exists (corpora that haven't landed marked `PENDING`)
- MedCAT+rules F1 ≥ 0.55 on F-S 40 (below indicates port failure)
- **Target: 0.72-0.85 on F-S 40 held-out (primary), 0.60-0.75 on US corpora (secondary)**
- Pre-UMLS-enrichment floor (Phase 1c only): 0.68-0.82 on F-S 40
- Post-UMLS-enrichment ceiling (Phase 1d): 0.72-0.85 on F-S 40

### Phase 8 — Error-driven refinement (Days 12-14)

**Iterative loop, ≤ 3 iterations or plateau:**
1. Rank errors by field × frequency
2. Sample 20 misses per field
3. Categorize: `{vocabulary_miss, negation_flip, temporality_flip, compound_bug, ambiguous_gold, us_idiom_miss}`
4. Add 5-10 rules per iteration
5. Rerun scorer
6. Stop when marginal F1 gain < 0.01 OR F1 ≥ 0.75 on F-S 40 reached

**Target:** at least one iteration reaches F1 ≥ 0.72 on F-S 40 (headline number). With UMLS enrichment (Phase 1d) applied, aim for 0.75-0.85. If UMLS still pending at Day 14, ship at 0.68-0.80 and re-run scorer once license lands.

**Deliverables:** `eval/results/medcat_iterations/iter_{1,2,3}.csv`, final `eval/results/medcat_rules_final.csv`.

### Phase 9 — Manuscript integration (Days 14-17)

**Deliverables:**
- `writing/MedAI_EPI_Manuscript_v0.5_additions.md`
- New table row: B1' MedCAT+rules across 6 corpora
- New section: `§Methods.MedCAT-Rules-Baseline` (1 paragraph)
- New section: `§Results.Cross-Corpus` — with error taxonomy
- Attribution paragraph: explicit citation of Fonferko-Shadrach 2019 + 2024 + ExECT-V2 repo
- Supplementary: rule-provenance table mapping our ~220 rules → ExECT-V2 files

**Acceptance:** manuscript v0.5 ready for internal review.

## 7. File layout

```
med42_service/
├── references/                             # git-ignored
│   ├── exect_v2/                           # local clone, study only
│   ├── exect_v2_ilae_map.csv               # CSV of the XLSX (public data)
│   └── exect_v2_cui_seed.csv               # Phase 1a — CUI list extracted from ExECT
├── data/
│   ├── eval_corpora/
│   │   ├── fs_test_40/                     # existing
│   │   ├── mtsamples_neuro/                # new — Phase 6b
│   │   ├── synth_v1_eval_100/              # new — Phase 6c
│   │   ├── n2c2_2018_medication/           # new — Phase 6e
│   │   ├── n2c2_2019_family_hx/            # new — Phase 6d
│   │   └── mimic_iv_epilepsy_500/          # new — Phase 6f
│   └── medcat_cdb_epilepsy/                # new — Phase 1
├── rules/                                   # new tree
│   ├── epilepsy_ontology.py                # 24-enum CUI/SCTID map
│   ├── base_rule.py
│   ├── context_config.py
│   ├── context_config_us.py
│   ├── uk_to_us_lexicon.py
│   ├── us_note_structure.py
│   ├── compound.py
│   ├── registry.py
│   ├── jape_to_python.md
│   └── fields/
│       ├── seizure_type.py
│       ├── seizure_frequency.py
│       ├── onset_age.py
│       ├── epilepsy_type.py
│       ├── etiology.py
│       ├── medication.py
│       ├── mri.py
│       ├── eeg.py
│       ├── family_history.py
│       ├── birth_history.py
│       ├── comorbidities.py
│       ├── clinical_localization.py
│       ├── surgery_history.py
│       ├── non_drug_therapy.py
│       ├── autoimmune.py
│       └── imaging_eeg_performed.py
├── services/
│   └── medcat_extractor.py                 # new
├── scripts/
│   ├── build_medcat_cdb_epilepsy.py        # new
│   ├── enrich_ontology_from_umls.py        # new — Phase 1d, runs when UMLS clears
│   ├── fetch_mtsamples_neuro.py            # new
│   ├── fetch_n2c2_2018.py                  # new
│   ├── fetch_n2c2_2019.py                  # new
│   ├── mimic_iv_extract_epilepsy_subset.py # new
│   ├── run_medcat_rules_on_corpus.py       # new
│   └── score_medcat_vs_gold.py             # new
├── tests/
│   ├── test_epilepsy_ontology.py           # new
│   └── test_rules_fields/                  # per-field tests
├── docs/
│   ├── MedCAT.md                           # this file
│   ├── EXECT_V2_STUDY.md                   # new
│   ├── EXECT_V2_ANNOTATION_GUIDELINES_NOTES.md  # new
│   └── US_CORPUS_STRATEGY.md               # new
├── eval/results/
│   ├── medcat_rules_all_corpora.csv        # new
│   ├── medcat_error_taxonomy.md            # new
│   └── medcat_iterations/                  # new
└── writing/
    └── MedAI_EPI_Manuscript_v0.5_additions.md
```

## 8. Attribution and licensing

**ExECT-V2 licensing note:** neither `swneurosci/ExECT-V2` nor `arronlacey/ExECT` carries an explicit LICENSE. Under default US copyright law this means "all rights reserved." Our approach:

- **Read** the repo freely (public GitHub is implicit permission to view).
- **Cite** Fonferko-Shadrach 2019 + 2024 + repo URLs prominently in the paper.
- **Reimplement logic** in Python — algorithms and facts are not copyrightable, so this is standard scientific practice.
- **Do not include** verbatim JAPE / Groovy / dictionary files in our repo.
- **Do not redistribute** their custom UMLS dictionaries (may include UMLS-derived content subject to UMLS terms) — re-derive equivalents through our own UMLS license.
- **Courtesy email** to Fonferko-Shadrach group confirming intent + optionally requesting explicit CC-BY / Apache-2.0 relicensing.

**Draft courtesy email** (send Day 0):

> Subject: US reimplementation of ExECT-V2 for research comparison
>
> Hi Dr Fonferko-Shadrach and Dr Lacey,
>
> We're building a US-side implementation of an epilepsy phenotype extractor at the University of Rochester Medical Center. Our project (MedAI-EPI) is a research comparison of rule-based vs LLM approaches for structured extraction from clinical notes. We plan to include ExECT-V2 as a specialized rule-based comparator by reimplementing your pipeline's logic in Python (MedCAT + medspaCy), citing your work.
>
> We've studied the swneurosci/ExECT-V2 and arronlacey/ExECT repositories. Two questions:
>
> 1. Would you be willing to add an explicit open-source license (e.g. CC-BY or Apache-2.0) so we can properly attribute? Without one, we are limited to reimplementing logic rather than porting code.
> 2. If a US collaboration on cross-corpus validation would interest you, we'd welcome the conversation.
>
> Happy to share our writeup and code as we go.
>
> Best,
> [team]

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| UMLS approval delayed | Low | +3-5% F1 delta only, NOT a blocker | Phase 1a-c uses public sources; Phase 1d enrichment runs when license clears |
| MIMIC DUA delayed > 3 weeks | Medium | Delays 6f only | Paper ships 5-corpus, MIMIC as addendum |
| n2c2 DUAs delayed | Medium | Delays 6d/6e | Same — five other corpora carry the paper |
| ExECT authors object to reimplementation | Very low | Legal | We reimplement logic, cite prominently; email documents good-faith intent |
| MedCAT concept-linker misses US idioms | Medium | F1 hit | Layer medspaCy Matcher rules for surface forms MedCAT misses |
| Rules underperform LLM significantly (F1 < 0.4 F-S) | Low-medium | Weakens paper claim | Iterate Phase 8; if still low, report as-is (paper honesty > paper cleanliness) |
| MTSamples ToS ambiguity | Low | Legal | Rate-limit + attribution; research use only, no redistribution |
| DIY MIMIC gold annotation inter-annotator drift | Medium | Confidence bands wide | Report κ; silver-label 460 with GPT + human-review disagreements |
| Scope creep — all 30 fields | Medium | Timeline slip | P1 (8 fields) is MVP; P2 only if buffer allows |
| 24-enum sourcing surprise (Engel/antibody/RNS) | Low-medium | +1-2 days | Hand-source from primary references |
| Note-type gaps (no video-EEG, no genetics reports) | Certain | Limits claims | Flag as limitations in §Discussion |

## 10. Acceptance criteria (roll-up)

**Phase 0 — DONE (2026-09-22):** ExECT-V2 cloned; env installed; import smoke passes. UMLS registration submitted (still awaiting approval); PhysioNet + Harvard DBMI initiated.
**Phase 1a — DONE (2026-09-23):** ExECT CUI seed CSV built at `references/exect_v2_cui_seed.csv`.
**Phase 1b — DONE (2026-09-23):** `rules/epilepsy_ontology.py` populated with 255 entries across 207 unique CUIs (target was 240+); every synonym cites a public source. Iter 2 (Phase 8) added misspelling variants mined from F-S 40 train.
**Phase 1c — DONE (2026-09-24):** CDB built at `data/medcat_cdb_epilepsy/`; UMLS-Small fallback wired; `pytest tests/test_epilepsy_ontology.py` passes (7 tests).
**Phase 1d — PENDING:** UMLS Metathesaurus License submitted but not yet cleared. Expected +3-5% F1 lift when it lands (`scripts/enrich_ontology_from_umls.py` written, dry-run tested).
**Phase 2 — DONE (2026-09-24):** `services/medcat_extractor.py` produces valid Pydantic-passing output on F-S train letters.
**Phase 3 (a+b) — DONE (2026-09-25/26):** 43 field-rule classes across 17 files in `rules/fields/`. Each has passing pytest on F-S train subset. Total tests: 181 pass / 0 fail.
**Phase 4 — DONE (2026-09-26):** US-adaptation layer active (`rules/uk_to_us_lexicon.py`, `rules/us_note_structure.py`, `rules/context_config_us.py`). Verified 15/15 notes across 3 corpora produce non-empty extractions.
**Phase 5 — DONE (2026-09-27):** 10 compound functions in `rules/compound.py`; each has ≥3 pytest cases.
**Phase 6 — PARTIAL:**
  - 6a F-S 40: DONE
  - 6b MTSamples neurology: PENDING (78 notes fetched; silver labels not yet generated)
  - 6c Synth-v1 100: DONE
  - 6d n2c2 2019: PENDING (Harvard DBMI DUA pending)
  - 6e n2c2 2018: PENDING (Harvard DBMI DUA pending)
  - 6f MIMIC-IV: PENDING (PhysioNet + CITI credentialing pending)
**Phase 7 — DONE (2026-09-28):** First F1 numbers landed; F-S F1 baseline = 0.5627 (≥ 0.50 floor). Error taxonomy generated at `eval/results/medcat_error_taxonomy.md`.
**Phase 8 — DONE (2026-09-29):** 3 refinement iterations completed; F-S F1 = 0.8053 (target 0.72 exceeded by +0.085; synth-v1 no-regression at 0.8189). All 181 tests still pass. Iteration summaries at `eval/results/medcat_iterations/iter{1,2,3}_summary.md`.
**Phase 9 — IN PROGRESS:** Manuscript v0.5 additions at `writing/MedAI_EPI_Manuscript_v0.5_additions.md`; Table 1 patch at `writing/MedAI_EPI_Manuscript_v0.5_table1_patch.md`; supplementary rule-provenance table at `writing/MedAI_EPI_Manuscript_v0.5_supp_rule_provenance.md`.

## 11. Next actions (in order, Day 0)

**No registration blocks Phase 0 or Phase 1a-c.** UMLS is submitted and will fold in at Phase 1d as enrichment.

1. Agent: clone ExECT-V2 to `references/exect_v2/` (add to `.gitignore`); export ILAE XLSX to CSV.
2. Agent: set up `venv-medcat/` env with `medcat[all] medspacy spacy pandas openpyxl`.
3. Agent: draft courtesy email to Fonferko-Shadrach group; user sends.
4. Agent: Phase 1a — parse ExECT dictionaries, extract ~500 CUIs to `references/exect_v2_cui_seed.csv`.
5. Agent: Phase 1b — populate `rules/epilepsy_ontology.py` by cross-verifying each CUI against BioPortal SNOMED browser + NINDS CDEs + ILAE paper appendix + F-S train mining.
6. Agent: Phase 1c — build custom CDB + wire MedCAT UMLS-Small pretrained as fallback.
7. Awaits: UMLS license clears (parallel) → Phase 1d enrichment (+2 hours work, +3-5% F1).
8. Awaits: PhysioNet + Harvard DBMI approvals (parallel) → Phase 6d/6e/6f corpora fold in.

**Non-blocking parallel tracks:**
- Phase 3 field porting (Days 4-9) proceeds independently of UMLS status.
- Phase 6b (MTSamples) and 6c (Synth-v1) proceed independently of any DUA.

## 12. Limitations & known gold-label edge cases

- **`medication.failed_asms` on F-S 40 (n=1, EA0179)**: the F-S silver label
  places sodium valproate under `failed_asms`, but the corresponding note text
  reads "was on sodium valproate" without an explicit failure marker
  ("failed", "did not respond", "seizures continued despite"). Our
  `FailedAsmsRule` (rules/fields/medication.py) intentionally requires
  explicit failure language and therefore places this instance under
  `prior_asms`. We treat this as a gold-label edge case (F-S annotation
  conflates "prior" with "failed" when the drug is discontinued after
  seizure recurrence), not a pipeline defect. Batch A retained the strict
  rule to avoid over-labelling every prior ASM as "failed"; the single
  EA0179 case caps failed_asms F1 at 0.00 for F-S 40 but does not affect
  the overall F1 by more than ~0.001.

- **`clinical_seizure.other_seizure_types` gate relaxation (Batch A D5)**:
  Phase 8 required an explicit `_SECONDARY_MARKERS` regex hit in the same
  sentence. Batch A relaxed this so that whenever 2+ distinct ILAE
  categories survive subsumption suppression, the non-predominant
  candidates fire as "other" entries. This is expected to trade a small
  number of new false positives for coverage on F-S EA0190 / EA0194 where
  the note lists multiple distinct seizure types in narrative form without
  a "also / additionally" marker.

- **HPO / EPIO cross-mappings (Batch A D2 / D3)**: 3 new Comorbidity keys
  (`developmental_delay`, `autism`, `cognitive_impairment`) were added to
  `COMORBIDITY_ONTOLOGY`. These are supplementary-only (not part of the
  Comorbidity enum in `schema/enums.py`) — the CDB build treats them as
  named concepts under `T-Comorbidity` but downstream rules still map to
  the existing enum keys.

- **UMLS-Full enrichment (D1)**: pending — `UMLS_APIKEY` env var was not
  set at Batch A execution time. Script `scripts/enrich_ontology_from_umls.py`
  is idempotent and cache-backed; re-run when the key is available.
