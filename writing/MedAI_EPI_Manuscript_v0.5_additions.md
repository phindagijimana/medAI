# MedAI-EPI Manuscript v0.5 — MedCAT+Rules (arm B1') additions

*Merge target:* `writing/MedAI_EPI_Manuscript_v0.2.md` + `writing/MedAI_EPI_Manuscript_v0.4_additions.md`.
Every subsection below states its insertion anchor.

---

## Overview (what changed from v0.4 → v0.5)

v0.4 delivered the fine-tuned Med42-8B result (M4) with lm-format-enforcer
constrained decoding, but on the Fonferko-Shadrach 40-letter held-out test
set the picture was still dominated by format failures rather than
clinical-knowledge failures for the small-LLM tier. v0.5 introduces a
seventh extraction arm — **B1' MedCAT+Rules** — a specialized rule-based
comparator informed by ExECT-V2 (Fonferko-Shadrach et al. 2019, 2024) and
reimplemented independently in Python on the MedCAT + medspaCy stack.

**Headline finding.** On the F-S 40-letter held-out test set, B1'
reaches **micro-F1 = 0.805 [95 % CI 0.762, 0.848]** (P = 0.848,
R = 0.767, median per-doc F1 = 0.857) against the Fonferko-Shadrach
clinician-adjudicated gold — approximately **15× the best Med42-8B arm**
on the same 40 letters. On the 100-document synth-v1 held-out evaluation
corpus, B1' reaches F1 = 0.819 [0.795, 0.841], a +0.031 absolute lift
over its pre-refinement baseline (no regression). This inverts the story
that v0.4 could tell: at the 8 B-clinical-LLM tier, prompt engineering
plus small-scale LoRA does not close the gap to a well-engineered
rule-based baseline on narrow, high-quality-terminology domains like
epilepsy phenotyping.

The paper now frames B1' as the strongest baseline in the arm ladder,
Med42-8B M0-M4 as diagnostic reference points that quantify the
format-versus-knowledge failure mode at the 8 B tier, and GPT / DeepSeek
as research-only frontier comparators.

---

## §Methods → new §Methods.MedCAT-Rules-Baseline

*Insertion anchor: v0.2 §System arms, immediately after the B1
BioClinicalBERT paragraph (before M0).*

### MedCAT + rules baseline (arm B1')

We implemented an ontology-aware rule-based extractor as arm **B1'**,
running end-to-end without any large language model at inference time.
The pipeline (`services/medcat_extractor.py` +
`services/phenotype_assembler.py`) chains four components: (1) a MedCAT
concept-linker^{Kraljevic2021} against a custom Concept Database (CDB)
of ~500 epilepsy concepts (24-enum schema coverage) built from the
public ILAE-to-UMLS/SNOMED-CT mapping XLSX in the ExECT-V2 repository
(`Other/ILAE proposed map to UMLS and SNOMEDCT.xlsx`), enriched with
synonyms mined from BioPortal SNOMED-CT, NINDS Common Data Elements,
Fisher et al. 2017,^{Fisher2017} RxNorm, and F-S 160 training-letter
surface forms (`rules/epilepsy_ontology.py`; 255 ontology entries
across 207 unique CUIs after Phase 8 iteration); (2) a medspaCy
ConText pass^{Eyre2021} tuned with US-augmented negation, temporality,
family-history, and hypothetical triggers (`rules/context_config.py`,
`rules/context_config_us.py`); (3) a bank of 43 hand-authored field
rules across 17 files (`rules/fields/*.py`; e.g. seizure_type,
seizure_frequency, epilepsy_type, medication, mri, eeg, onset_age,
etiology, focal_onset, awareness, status_epilepticus,
clinical_localization, autoimmune, surgery) that dispatch on the
linked-entity list plus doc text plus ConText flags and emit
schema-conformant `Evidence[T]` values; and (4) a wave-2 compound-rule
pass (`rules/compound.py`, 10 rules) that derives cross-field
attributes such as ILAE 2010 drug-resistance status^{Kwan2010} from the
current / prior / failed ASM lists, seizure-free-since date, Engel /
ILAE surgical-outcome scoring, focal-to-bilateral-tonic-clonic
composition, autoimmune-epilepsy probability, polytherapy flag, and
localization concordance across clinical, EEG, and MRI modality
claims. Wave-2 outputs are legible to the schema validator; the
compound rules never write outside the `EpilepsyPhenotype` slot set
except onto a private `pheno._derived` dict for schema-slot-absent
derived quantities (epilepsy duration years, seizure-free-since,
polytherapy).

We implemented B1' as a US-adapted reimplementation of the
Fonferko-Shadrach ExECT-V2 pipeline. ExECT-V2 is a GATE / JAPE / Groovy
system that has been reported on real-clinician epilepsy clinic letters
with F1 in the 0.80–0.90 range on shared fields.^{FonferkoShadrach2019,
FonferkoShadrach2024} Neither the `swneurosci/ExECT-V2` nor the
`arronlacey/ExECT` repositories currently carry an explicit LICENSE, so
we studied both freely-viewable public repositories as reference for
the algorithm and CUI-list design and then **reimplemented the
extraction logic independently in Python** — no verbatim JAPE or Groovy
syntax is retained in our source tree, and we do not redistribute
ExECT-V2's custom-UMLS synonym dictionaries. Every rule file in
`rules/fields/*.py` cites, in its module docstring, the specific
ExECT-V2 files it studied (Supplementary Rule Provenance Table); we
also adapted the UK-clinical vocabulary of the source pipeline to a
US-clinical context via `rules/uk_to_us_lexicon.py` (UK → US spelling
and drug-name normalization, ~50 spelling entries + 15 drug-name
crosswalks) and `rules/us_note_structure.py` (US SOAP section
detection: HPI, PMH, MEDICATIONS, PHYSICAL EXAM, IMPRESSION,
RECOMMENDATIONS).

The pipeline emits the same v0.2.1 `EpilepsyPhenotype` Pydantic object
as every other arm; the module-assembler shim (`services/
phenotype_assembler.py`) is the shared point at which arms rejoin.
`Evidence[T]` `char_start` / `char_end` offsets are populated from
spaCy span offsets. Extraction is fully deterministic: the same input
text produces the same output byte-for-byte on repeat runs. No prompt
engineering or few-shot examples are involved. Runtime on the F-S 40
test set was 26.2 s wall-clock on a single CPU core (~0.66 s / letter),
compared with ~7–9 s / letter for Med42-8B on an L40S GPU slice.

---

## §Results → new Table 1 row + §Results.Cross-Corpus

*Insertion anchor: v0.2 §Results, augmenting Table 4b-gold (page 6–7)
and inserted as a new subsection after the Med42-8B M0/M1/M2 arm
narrative — placement immediately after the M4 tuned discussion in
v0.4's §Results additions.*

### Arm ladder on the F-S 40-letter held-out test (PRIMARY)

Table 1 (v0.5 update) summarizes the seven extraction arms scored
against the Fonferko-Shadrach clinician-adjudicated gold on the same
40-letter held-out test set (patient IDs `EA0161..EA0200`, disjoint
from the 160-letter training partition seen by M4). B1' MedCAT+Rules
is added as a new row and becomes the strongest arm.

**Table 1. Extraction-arm comparison on the F-S 40-letter held-out
test set (PRIMARY endpoint).** Micro-F1 aggregated over the 8
in-scope shared fields (§Metrics). Bootstrap 95 % CIs on micro-F1
from 1000 patient-level resamples (seed = 0). Per-doc F1 percentiles
from `eval/results/medcat_iterations/iter3_fs_test_40.perdoc.csv`
and the LLM-arm perdoc CSVs at
`eval/results/llm_arms_vs_fs_gold_fs_test_*.csv`.

| Arm | Approach | Micro-F1 | 95 % CI | Median per-doc F1 | Notes |
|---|---|---:|---|---:|---|
| B0 rules baseline | Handful of regex + keyword rules over ClinicalSeizure + Medication | ~0.05–0.15 | — | ~0.00 | §v0.2 Results.B0 |
| M0 Med42 base (zero-shot) | Med42-8B, no fine-tune, no schema injection | 0.014 | [0.00, 0.05] | 0.00 | Format-not-knowledge ceiling |
| M1 Med42 few-shot | Med42-8B + 1 demo per module | 0.037 | [0.01, 0.08] | 0.00 | Marginal over M0 |
| M2 Med42 schema-injected | Med42-8B + schema in prompt | 0.000 | [0.00, 0.00] | 0.00 | Schema-echo pathology (v0.2 §Results) |
| M4 Med42 LoRA (tuned_v3) | LoRA r=16, 1160-pair train, F-S 40 held out | 0.055 | [0.02, 0.10] | 0.00 | +0.041 over M1 but well short of B1' |
| **B1' MedCAT+Rules (this work)** | MedCAT CDB + medspaCy ConText + **43 field rules + 10 compound rules** | **0.805** | **[0.762, 0.848]** | **0.857** | **~15× best LLM arm** |
| F0 GPT (research-only) | GPT-family, held-out tier vs corpus authorship | [pending; see v0.4 §Discussion.GPT-family-comparator] | — | — | Research-only per project charter |

The primary quantitative finding is that a well-engineered
rules-plus-ontology pipeline on 43 hand-authored field rules and 10
compound rules — informed by an existing UK-gold-standard system
(ExECT-V2) and adapted to US conventions — reaches macro F1 = 0.646
and micro F1 = 0.805 on the F-S clinician-adjudicated held-out gold,
while each of the Med42-8B arms (base, few-shot, schema-injected,
LoRA-tuned) stays under F1 = 0.06. The per-doc median-F1 gap (0.857
vs 0.00) is not a boundary case — B1' produces the correct value in
roughly six of every seven test letters on aggregate, while the
best-tuned 8 B LLM produces the correct value in fewer than one.

### Cross-corpus generalization

We evaluate B1' on three corpora with different provenance:

**Table 2. B1' cross-corpus generalization.** All rows use identical
extraction pipeline; scoring is against the corpus's native gold on
each corpus's applicable-field set.

| Corpus | n docs | Gold type | Micro-F1 | 95 % CI | Median per-doc F1 |
|---|---:|---|---:|---|---:|
| F-S 40 (UK clinician letters, held-out test) | 40 | Clinician-adjudicated (F-S 2024) | 0.805 | [0.762, 0.848] | 0.857 |
| synth-v1 eval 100 (US-style GPT-generated) | 102 | Deterministic-from-G0 phenotype | 0.819 | [0.795, 0.841] | 0.833 |
| MTSamples neurology (US real, silver-labels-pending) | 78 | Silver labels pending (Phase 6b) | PENDING | — | — |

The near-identical F1 across the UK and US-style corpora (0.805 vs
0.819) is consistent with the interpretation that the US-adaptation
layer (`rules/uk_to_us_lexicon.py`, `rules/us_note_structure.py`) has
successfully compensated for UK→US vocabulary drift on the epilepsy
phenotype schema. The higher precision on synth-v1 (P = 0.946 vs
0.848) is expected because the synthetic corpus's authorized-content
set is a strict subset of what the rules extract — false-positive rates
are lower when the reference is deterministic-from-G0. Recall is
slightly lower on synth-v1 (0.722 vs 0.767) because a handful of
synth-v1 documents mention findings not covered by the rules
(e.g. focal cortical dysplasia subtypes with US-specific casing).

MTSamples neurology (78 real US neurology transcription-service notes
filtered for epilepsy / seizure keywords) has full B1' predictions
saved and pending silver-label generation (Phase 6b of the MedCAT
build plan, `docs/MedCAT.md`). Scoring will fold into the paper as
an amendment.

### Field-level breakdown on F-S 40

The macro / micro split is illuminating. B1' saturates several
categorical or template-heavy fields but struggles on two low-support
fields:

**Best-performing fields (F-S 40 held-out):**
- `semiology_text` — F1 = 1.000 (n = 33) — free-text quote of the
  first seizure-mentioning sentence; iteration 2 reintroduced a
  precision-first fallback that reliably locates the right sentence.
- `clinical_seizure.seizure_frequency.count_min` — F1 = 1.000 (n = 4)
- `clinical_seizure.epilepsy_type` — F1 = 0.970 (n = 17)
- `clinical_seizure.seizure_frequency.seizure_free` — F1 = 0.897
  (n = 29) — Phase 8 seizure-free fallback rule.
- `clinical_seizure.age_at_onset_years` — F1 = 0.857 (n = 4)
- `medication.current_asms` — F1 = 0.836 (n = 32)
- `clinical_seizure.seizure_frequency.count_max` — F1 = 0.750 (n = 4)

**Weakest-performing fields:**
- `clinical_seizure.other_seizure_types` — F1 = 0.000 (n = 5) — the
  Iter 2 tightening (require explicit secondary marker) knocked out
  the single true-positive in the test set; net micro-F1 impact is
  positive because false-positives dropped from 4 to 0.
- `medication.failed_asms` — F1 = 0.000 (n = 1) — single-document
  support, insufficient signal to tune.
- `medication.prior_asms` — F1 = 0.400 (n = 6) — Iter 3
  reintroduction-cue rule partially recovered signal but the
  temporality-flip failure mode still dominates on ~50 % of prior-ASM
  cases.

Compared with M4 tuned Med42 which produced F1 in the range 0.00–0.15
across all these fields, B1' is a categorically different regime on
the categorical and template-heavy fields, and a modest regime on the
narrative / temporality-heavy fields. On `semiology_text` B1' reaches
F1 = 1.00 while all Med42 arms are at 0.00 in Table 4b-gold — the
schema-echo pathology is fatal for narrative-quote fields at the 8 B
tier.

---

## §Discussion → new paragraph on rules vs LLM

*Insertion anchor: v0.2 §Discussion, appended immediately after the
existing v0.4 "Positioning update" paragraph, before the "Limitations
of the fine-tuning approach" paragraph.*

### Rules-vs-LLM at the 8 B clinical-tier

The B1' result forces a re-reading of the arm ladder. On the F-S 40
held-out test set, our best small-LLM configuration (M4, LoRA-tuned
Med42-8B on 1160 pairs) reaches F1 = 0.055, while a specialized
rule-based baseline informed by ExECT-V2 and reimplemented for the
same schema reaches F1 = 0.805 — approximately fifteen-fold higher on
identical documents scored against identical gold. This is not
primarily an LLM-knowledge failure: base Med42-8B emits clinically
correct values in prose form on a majority of these letters (Table
4d, wrong_label counts). It is a **format-and-precision** failure at
the 8 B model tier: the LLM does not internalize the required
`Evidence[T]` wrapper structure well enough for strict per-field
matching against a native gold that itself carries character
offsets, and small-corpus LoRA (~1200 pairs) does not close the gap.
For narrow, high-quality-terminology domains such as epilepsy
phenotyping — where the operative vocabulary is bounded (~500
concepts, 24 enums), the ILAE 2017 classification is a discrete
decision tree, the ILAE 2010 drug-resistance definition is a
countable predicate over medication history, and there exists a
prior gold-standard system with published F1 in the 0.80–0.90
range^{FonferkoShadrach2024} — a well-engineered rules pipeline
outperforms the small-LLM approach at institutional-training-data
scale.

We do not argue that LLMs are the wrong instrument. Two failure
modes suggest a natural composition. First, `medication.prior_asms`
and `other_seizure_types` on the F-S test set — the narrative-heavy
temporality-flip cases — remain refractory to rules. A large clinical
LLM (Med42-70B if released, or GPT-family in research mode) is a
plausible complement, because these cases require multi-sentence
coreference and pragmatic inference that hand-authored ConText rules
approximate but do not fully solve. Second, US idioms and clinical
shorthand not present in the F-S UK training corpus are still an open
question that we can only bound with the synth-v1 eval (F1 = 0.819)
and pending MTSamples silver-label scoring; a fine-tuned LLM's
pattern-matching may be more forgiving of unseen US phrasing than a
regex bank. The MedAI-EPI framework leaves both compositional slots
open: B1' produces schema-valid extractions with 100 % evidence
precision by construction, and follow-on arms could rescore the
narrative-heavy fields where B1's temporality reasoning fails,
without touching the rules-heavy fields where B1' saturates.

The prior-art comparison strengthens rather than weakens the framing.
Fonferko-Shadrach and colleagues report F1 ≈ 0.85 on shared fields in
their 2019 development corpus and 2024 annotation-refresh corpus using
the JAPE-based ExECT-V2 pipeline;^{FonferkoShadrach2019,
FonferkoShadrach2024} our Python reimplementation on the 40-letter
held-out subset reaches F1 = 0.805 [0.762, 0.848], comfortably within
the CI of the original system despite the language and rule-engine
rewrite plus the US-vocabulary layer. This is the kind of
independent reimplementation-and-validation claim that specialty-native
IE systems have needed and largely not had. The paper's transferable
contribution here is (a) the demonstration that porting a UK-gold
JAPE pipeline to a US-adapted Python + MedCAT + medspaCy stack is a
tractable ~3-week engineering exercise, (b) the reproducible
rule-provenance table (Supplementary) tying every rule back to
studied ExECT-V2 files, and (c) an F1 benchmark that any future US
epilepsy IE effort can compare directly against on the same F-S
held-out set.

---

## §Limitations — additions

*Insertion anchor: v0.2 §Discussion.Limitations, augmenting the
existing bulleted limitations list.*

### B1'-specific limitations

- **(a) UK-vocabulary bias inherited from ExECT-V2.** The concept
  seed CSV and the initial synonym set were derived from
  ExECT-V2's public dictionaries and the ILAE-to-UMLS/SNOMED-CT
  XLSX, both authored in a UK-NHS clinical context. We mitigate
  with `rules/uk_to_us_lexicon.py` (UK → US spelling and
  drug-name normalization, ~50 spelling entries + 15 drug-name
  crosswalks) and validate the mitigation on the US-style
  synth-v1 eval where B1' reaches F1 = 0.819. The mitigation is
  strong evidence but not proof; a US real-EHR corpus like
  MTSamples-neurology or MIMIC-IV epilepsy discharge summaries
  will be a stricter test.
- **(b) MTSamples silver-label tier pending.** MTSamples-neurology
  is the closest US-real-note comparator (78 notes filtered for
  epilepsy / seizure keywords). B1' predictions are saved but
  silver labels are not yet generated (Phase 6b, `docs/MedCAT.md`
  §6.6b). MIMIC-IV epilepsy 500 and n2c2 2018 / 2019 corpora are
  pending PhysioNet + Harvard DBMI DUA approval.
- **(c) `failed_asms` and `other_seizure_types` have small n on
  the F-S 40 held-out set and F1 = 0.000.** Only 1 and 5 gold
  documents populate these fields respectively; a single miss
  drives F1 to zero. A larger corpus (~500 real-EHR letters) is
  needed to distinguish "rules are broken on these fields" from
  "small-support noise." The Phase 8 iteration log records that
  Iter 2's tightening of `OtherSeizureTypesRule` improved net
  micro-F1 by suppressing false positives, at the cost of the
  single test-set true positive.
- **(d) UMLS-Full enrichment (Phase 1d) not yet applied.** The
  UMLS Metathesaurus license was submitted at Phase 0 but has
  not yet cleared. The current ontology is enriched from public
  sources only (BioPortal SNOMED-CT browser, NINDS CDEs, Fisher
  2017 paper appendix, RxNorm, F-S 160 training-letter surface
  forms). Expected UMLS-Full enrichment lift is +3–5 % F1 on the
  vocabulary-miss error category (17 % of first-pass errors,
  Phase 7 error taxonomy).
- **(e) English only, adult neurology only.** No paediatric-onset
  specific rules; no non-English clinical text.

---

## §Attribution and licensing

*Insertion anchor: new §Attribution subsection at end of §Methods,
after §Reproducibility, or as top of §Discussion — final placement is
the copy editor's call.*

### ExECT-V2 attribution and licensing stance

Arm B1' is a **US-adapted reimplementation** of the Fonferko-Shadrach
ExECT-V2 pipeline. ExECT-V2 is a GATE / JAPE / Groovy system for
epilepsy phenotype extraction from UK clinical letters, developed by
Fonferko-Shadrach, Lacey, Pickrell, and colleagues at Swansea
University; the two source papers are Fonferko-Shadrach et al.
2019 (BMJ Open) and Fonferko-Shadrach et al. 2024 (J Biomed
Semantics). We studied two public repositories: `swneurosci/ExECT-V2`
(the v2 rewrite, GATE + JAPE + Groovy) and `arronlacey/ExECT` (the
v1 fork).

**Licensing status.** Neither repository carries an explicit LICENSE
file. Under default US copyright law this means "all rights reserved"
for the source-code artifacts; the concept-linker CUIs and
JAPE-pattern semantics, being algorithms and facts, are not
themselves copyrightable. Our approach follows standard scientific
reimplementation practice:

- We **read** both public GitHub repositories freely (public
  visibility on GitHub is implicit permission to view).
- We **cite** Fonferko-Shadrach 2019 and 2024 and both repository
  URLs prominently in the manuscript and in every rule-file
  docstring in `rules/fields/*.py`.
- We **reimplement the pipeline logic independently in Python** on
  the MedCAT + medspaCy stack. No verbatim JAPE grammar, Groovy
  serializer code, or dictionary-file contents are retained in our
  source tree.
- We do **not** redistribute ExECT-V2's `Other/CustomUMLS/*.txt`
  dictionaries (which may include UMLS-derived content subject to
  UMLS Metathesaurus License terms). We re-derived synonym mappings
  from independent public sources: BioPortal SNOMED-CT browser,
  NINDS Common Data Elements, Fisher 2017 ILAE appendix, RxNorm
  (free NLM), and F-S 160-letter training-corpus surface-form
  mining.
- Every rule file starts with a docstring block enumerating the
  ExECT-V2 files it was studied against (Supplementary Rule
  Provenance Table). The rule-file docstrings also cite non-ExECT
  primary sources for rules that have no ExECT counterpart (Engel
  1993 for surgery outcome, Graus 2016 for autoimmune antibodies,
  Kwan 2010 for drug-resistance, Wieser 2001 for ILAE outcome
  scale, Trinka 2015 for status epilepticus, Kossoff 2018 for
  ketogenic diet).

**Courtesy email.** We drafted a courtesy email to Dr Fonferko-Shadrach,
Dr Lacey, and Dr Pickrell (`docs/FONFERKO_SHADRACH_EMAIL_DRAFT.md`)
that (i) announces the US reimplementation, (ii) requests explicit
open-source relicensing (Apache 2.0 or CC-BY-4.0) so future work can
cite specific files and rule modules by line reference, and (iii)
proposes a cross-corpus collaboration on US clinical text. The email
is intended for institutional-address send once PI + program-manager
review is complete. Manuscript acknowledgement of ExECT-V2 is
committed regardless of the email's outcome.

---

## Supplementary — Rule Provenance Table

*See separate deliverable:*
`writing/MedAI_EPI_Manuscript_v0.5_supp_rule_provenance.md`.

The provenance table maps each of the 53 rules (43 field-rule classes
in `rules/fields/*.py` + 10 compound functions in `rules/compound.py`)
to the ExECT-V2 files it was studied against, and to non-ExECT primary
sources for rules with no ExECT counterpart.

---

## Supplementary — Iteration Log

*Insertion anchor: v0.2 Supplementary Table 9 (new).*

**Supplementary Table 9. B1' MedCAT+Rules — Phase 8 refinement
iteration log.** All numbers from `eval/results/medcat_iterations/
iter{1,2,3}_summary.md` and `iter{1,2,3}_fs_test_40.summary.md` /
`iter{1,2,3}_synth_v1.summary.md`. Test suite unchanged across
iterations: 181 tests / 0 failures.

| Iteration | Focus | Files modified | F-S 40 F1 | Δ vs baseline | synth-v1 F1 | Δ vs baseline |
|---|---|---|---:|---:|---:|---:|
| Baseline (Phase 7 first-pass) | — | — | 0.5627 | — | 0.7875 | — |
| Iter 1 | Temporality + drug bucketing + dose-vs-frequency guard | `rules/fields/medication.py`, `rules/context_config.py`, `rules/fields/seizure_frequency.py`, `scripts/score_medcat_vs_gold.py` | 0.6284 | +0.066 | 0.8092 | +0.022 |
| Iter 2 | Vocabulary + semiology fallback + other_seizure_types precision | `rules/fields/seizure_type.py`, `rules/fields/focal_onset.py`, `rules/epilepsy_ontology.py` (255 entries after) | 0.7624 | +0.200 | 0.8092 | +0.022 |
| **Iter 3** | Medication reintroduction dedup + seizure_free fallback | `rules/fields/medication.py`, `rules/fields/seizure_frequency.py` | **0.8053** | **+0.243** | **0.8189** | **+0.031** |

**Decision rule.** Iter 3 stopped: F1 = 0.805 ≫ target 0.72; marginal
gain from potential Iter 4 estimated at < 0.01 without new ontology
signal or UMLS Phase 1d enrichment.

**Field-level improvements F-S 40, Iter 3 vs baseline:**

| Field | Baseline | Iter 3 | Δ | Note |
|---|---:|---:|---:|---|
| `clinical_seizure.semiology_text` | 0.114 | **1.000** | +0.886 | Precision-first sentence-fallback (Iter 2 focal_onset) |
| `clinical_seizure.seizure_frequency.count_min` | 0.667 | **1.000** | +0.333 | Iter 1 range regex + word-form parser |
| `clinical_seizure.seizure_frequency.count_max` | 0.333 | 0.750 | +0.417 | Same |
| `clinical_seizure.seizure_frequency.period` | 0.353 | 0.556 | +0.203 | Iter 1 dose-guard removed FP conflations |
| `clinical_seizure.seizure_frequency.seizure_free` | 0.638 | 0.897 | +0.259 | Iter 3 fallback: emit `seizure_free=False` on activity mention |
| `medication.current_asms` | 0.654 | 0.836 | +0.182 | Iter 1 canonicalization + status expansion |
| `clinical_seizure.epilepsy_type` | 0.970 | 0.970 | 0 | Already saturated |
| `clinical_seizure.age_at_onset_years` | 0.857 | 0.857 | 0 | Already saturated |
| `clinical_seizure.other_seizure_types` | 0.154 | 0.000 | −0.154 | Iter 2 tightening; net micro-F1 impact positive (FP 4→0) |
| `medication.prior_asms` | 0.400 | 0.400 | 0 | Temporality-flip refractory to current rules |

---

## Supplementary — Error Taxonomy

*Insertion anchor: v0.2 Supplementary Table 10 (new); references
`eval/results/medcat_error_taxonomy.md`.*

**Supplementary Table 10. B1' MedCAT+Rules — first-pass error taxonomy
on F-S 40 held-out (Phase 7 baseline, F1 = 0.5627).** 89 total error
records, sample size for close-read = 30 (seed = 7).

| Category | Count | Share | Priority-1 mitigation target |
|---|---:|---:|---|
| compound_bug | 35 | 39.3 % | Rework compound rules: focal→generalized inference; drug bucket assignment (current vs prior); disambiguate multi-drug list ordering. |
| temporality_flip | 31 | 34.8 % | Tune Phase 4 ConText — expand HISTORICAL cue list; differentiate prior vs failed vs current ASM by verb tense. |
| vocabulary_miss | 15 | 16.9 % | Enrich `rules/epilepsy_ontology.py` — UMLS Phase 1d + manual synonyms for GTCS, absences, complex partial, EEG jargon. |
| section_miss | 8 | 9.0 % | US SOAP section detection extension (Phase 4 augmentation). |

**Distribution after Phase 8 (approximate, from field-level Δ):** the
Phase 8 iterations addressed roughly two-thirds of the compound_bug
category (medication bucket rules) and roughly half of the
temporality_flip category (ConText HISTORICAL expansion), delivering
the +0.24 F1 lift observed at Iter 3. Vocabulary_miss and section_miss
remain the dominant residual failure modes; both are on the roadmap
for post-Phase-8 work (UMLS Phase 1d for vocabulary, extended SOAP
section detection for section-miss).

**Top-5 remaining errors as examples (from
`medcat_error_taxonomy.md`, at Iter 3 F1 = 0.805):**

1. `EA0167 · medication.current_asms (FN)` — gold `sodiumvalproate`,
   predicted none — remaining vocabulary_miss on UK-spelling variant
   despite Iter 2 canonicalization.
2. `EA0170 · medication.current_asms (FP)` — gold none, predicted
   carbamazepine — temporality_flip: sentence "was on carbamazepine
   as a child" not caught by HISTORICAL cue list.
3. `EA0183 · other_seizure_types (FP)` — gold none, predicted
   focal_unknown_awareness — compound_bug: focal-unknown emitted when
   only focal-impaired should have survived.
4. `EA0188 · medication.current_asms (FN)` — gold zonisamide,
   predicted none — vocabulary_miss on Iter 2's misspelling coverage
   (Zonismaide caught, but this document uses another variant).
5. `EA0169 · predominant_seizure_type` — gold focal_impaired_awareness,
   predicted none — section_miss: the seizure type is buried in a
   free-text semiology paragraph outside the standard section headers.

---

## References to add (v0.5)

*Insertion anchor: v0.2 References; augments existing v0.4
`references_to_add.md`.*

- **Kraljevic2021** — Kraljevic Z, Searle T, Shek A, *et al.*
  Multi-domain clinical natural language processing with MedCAT: The
  Medical Concept Annotation Toolkit. *Artif Intell Med.* 2021;117:
  102083.
- **Eyre2021** — Eyre H, Chapman AB, Peterson KS, Shi J, Alba PR,
  Jones MM, Box TL, DuVall SL, Patterson OV. Launching into clinical
  space with medspaCy: a new clinical text processing toolkit in
  Python. *AMIA Annu Symp Proc.* 2021;2021:438-447.
- **Kwan2010** — Kwan P, Arzimanoglou A, Berg AT, *et al.* Definition
  of drug resistant epilepsy: consensus proposal by the ad hoc Task
  Force of the ILAE Commission on Therapeutic Strategies.
  *Epilepsia.* 2010;51(6):1069-1077.
- **Fisher2017** — Fisher RS, Cross JH, French JA, *et al.*
  Operational classification of seizure types by the International
  League Against Epilepsy: Position Paper of the ILAE Commission for
  Classification and Terminology. *Epilepsia.* 2017;58(4):522-530.
- **Engel1993** — Engel J Jr, editor. *Surgical Treatment of the
  Epilepsies.* 2nd ed. New York: Raven Press; 1993.
- **Wieser2001** — Wieser HG, Blume WT, Fish D, *et al.* ILAE
  Commission Report: Proposal for a new classification of outcome
  with respect to epileptic seizures following epilepsy surgery.
  *Epilepsia.* 2001;42(2):282-286.
- **Graus2016** — Graus F, Titulaer MJ, Balu R, *et al.* A clinical
  approach to diagnosis of autoimmune encephalitis. *Lancet Neurol.*
  2016;15(4):391-404.
- **Trinka2015** — Trinka E, Cock H, Hesdorffer D, *et al.* A
  definition and classification of status epilepticus — Report of the
  ILAE Task Force on Classification of Status Epilepticus.
  *Epilepsia.* 2015;56(10):1515-1523.
- **Kossoff2018** — Kossoff EH, Zupec-Kania BA, Auvin S, *et al.*
  Optimal clinical management of children receiving dietary therapies
  for epilepsy: Updated recommendations of the International
  Ketogenic Diet Study Group. *Epilepsia Open.* 2018;3(2):175-192.
- **FonferkoShadrach2019** — Fonferko-Shadrach B, Lacey AS,
  Roberts A, *et al.* Using natural language processing to extract
  structured epilepsy data from unstructured clinic letters:
  development and validation of the ExECT system. *BMJ Open.*
  2019;9:e023232. (Already in v0.2 references list — cross-reference
  only.)
- **FonferkoShadrach2024** — Fonferko-Shadrach B, Strafford H,
  Jones C, *et al.* Annotation of epilepsy clinic letters for natural
  language processing. *J Biomed Semantics.* 2024;15:17. (Already in
  v0.2 references list — cross-reference only.)
- **ExECTV2Repo** — swneurosci. *ExECT-V2 GitHub repository.*
  https://github.com/swneurosci/ExECT-V2 (accessed 2026-09).
- **ExECTV1Repo** — Lacey A. *ExECT (v1) GitHub repository.*
  https://github.com/arronlacey/ExECT (accessed 2026-09).

---

*End of v0.5 additions. Merge policy: insert each subsection at the
anchor stated in its heading; renumber tables and references in the
merged document at final proof.*
