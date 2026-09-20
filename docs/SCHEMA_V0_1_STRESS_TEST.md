# Schema v0.1 stress test — PMC case narratives

**Purpose.** Read a diverse sample of published epilepsy case narratives from PMC and check whether the v0.1 phenotype ontology (`schema/`, `docs/SCHEMA_V0_1.md`) can hold what the notes actually contain. Any field that repeatedly appears in real narratives but has no home in the schema is a candidate for v0.2.

**Corpus.** 20 open-access PMC case reports across 7 phenotype themes (MTLE, FLE, FCD, HS-associated, drug-resistant, JME, LGS). Data in `data/pmc_cases/`, provenance in `data/pmc_cases/manifest.json`, fetched via `scripts/fetch_pmc_epilepsy_cases.py`.

**Caveats.**
- PMC case reports are *narratives*, not real EHR notes. They blend history, imaging findings, EEG interpretation, semiology, and outcomes in a single document — real clinical notes will be cleaner-separated per doc type. This inflates apparent "gaps" in modules that in production would live in different source docs.
- Some fetched articles are cohort/imaging studies rather than pure case reports (~5 of 20). They were kept because they still describe individual patients.
- No sign-off implied — this report is one engineer's read of the schema against sample text, meant to seed the epileptologist review.

---

## 1. Coverage that held up

| Field / concept                     | Verdict | Notes |
| ----------------------------------- | ------- | ----- |
| `age_at_onset_years` (float)        | Good    | Case with 13-month-old onset would use 1.08; acceptable. Consider a raw-text quote in evidence. |
| `SeizureFrequency.raw_text` free-form | Good  | "6–8 seizures per month", "several times a day", "seizure-free for 3 years" — flexible enough. |
| `Medication` list with `MedicationStatus` | Good  | Handles polytherapy of 8+ ASMs including doses ("levetiracetam 1000 mg twice daily") via `dose_text`. |
| `DrugResistanceStatus` enum          | Good    | Case narratives use the ILAE definition explicitly. |
| `Laterality`, `LobarLocalization`    | Good    | Every localization statement fit — including "predominantly left frontal", "bilateral", "right mesial temporal". |
| `EegBackground`                      | Good    | Diffuse slowing, focal slowing, asymmetric, burst suppression all appeared. |
| `MriFinding` (mostly)                | Partial | HS, FCD, encephalomalacia all present. **Gaps below.** |
| `Certainty` values                   | Good    | "definite", "probable", "possible", "negated" all fit ("no clear lateralization" → NEGATED with value=None). |
| Evidence wrapper                     | Good    | Evidence spans are clearly extractable from prose in most fields. |
| Applicability mask                   | Not tested directly (case reports don't cleanly map to doc types), but the mask design remains sound for real EHR ingestion. |

---

## 2. Missing fields — add in v0.2 (ranked by frequency of gap)

### 2.1 Etiology (highest priority)

Appears in ~15/20 cases and has no home in the schema. ILAE etiology categories: **structural**, **genetic**, **infectious**, **immune**, **metabolic**, **unknown**.

Examples encountered:
- ARGHAP35 gene mutation (LGS) → *genetic*
- Anti-SOX1 antibody, paraneoplastic (SCLC) → *immune*
- Post-traumatic (bike fall at 15) → *structural*
- Neurocysticercosis-related → *infectious*
- Post-stroke → *structural*
- Malformation of cortical development / MOGHE → *structural*

**Proposal:** Add `etiology_category` (enum) + `etiology_details_text` (Evidence[str]) to `ClinicalSeizureModule`. Optionally a small `EtiologySpecifics` object with fields for `causative_gene`, `causative_variant`, `associated_tumor`, `causative_antibody` — but these can also live in free text if we want to defer.

### 2.2 Focal seizure motor subtype

The `SeizureType` enum handles focal aware / focal impaired-awareness / FBTC, but not the motor phenomenology that clinicians and ILAE 2017 both use: **automatisms, hyperkinetic, tonic, clonic, myoclonic, atonic, epileptic spasms (focal)**. Cases had:
- "focal hyperkinetic seizures with mild impairment of awareness" (MOGHE)
- "focal myoclonic seizures in his right arm" (post-infarct DRE)
- "focal impaired awareness with cognitive changes and behavioural arrest" (MTLE)

**Proposal:** Add `focal_motor_onset` and `focal_nonmotor_onset` enums per ILAE 2017, applied when `predominant_seizure_type` is a focal type. Or a single `focal_subtype` composite. Reviewer preference needed.

### 2.3 Surgical outcome (Engel / ILAE)

`SurgeryHistoryItem.outcome_text` is free text. Every surgery case reported outcome as "seizure-free for X months/years" or a specific ILAE/Engel class.

**Proposal:** Add `engel_class` (I / II / III / IV, with A/B/C subclasses) and `ilae_outcome` (1–6) enums to `SurgeryHistoryItem`. Keep `outcome_text` alongside for the raw quote.

### 2.4 Neuropathology from resected specimen

MOGHE, FCD Type IIa/IIb, Palmini classification, granule cell dispersion — these are diagnostic conclusions from *pathology reports*, not MRI reports. Our schema has no path/histology module and `MriFinding.other_lesion` swallows too much detail.

**Proposal:** Either (a) extend `MriFinding` with `MOGHE`, `fcd_palmini_type_i`, `fcd_palmini_type_iia`, `fcd_palmini_type_iib`, or (b) add a new `NeuropathologyModule` for `procedure_resection` / autopsy reports. (a) is cheaper for v0.2; (b) is cleaner long-term. Recommend starting with (a) plus a `pathology_notes_text` Evidence[str] field on `SurgeryHistoryItem`.

### 2.5 Seizure duration (per event)

Cases distinguish duration from frequency: "seizures lasting for 2 to 3 minutes each", "variable duration from 16 to 30 seconds". Currently no field.

**Proposal:** Add `duration_seconds_min` / `duration_seconds_max` (optional int) or a `duration_text` (raw quote) to `SeizureFrequency`. Raw text is safer for v0.1→v0.2.

### 2.6 MRI field strength

Multiple cases hinged on 1.5 T missing what 3 T revealed. Not decisive for extraction, but worth capturing.

**Proposal:** Add `field_strength_tesla` (float or enum {1.5, 3, 7}) to `MriModule`.

### 2.7 Non-drug / dietary / immunotherapy

Ketogenic diet, IVIG, plasmapheresis, steroids appear as treatments. `MedicationModule` currently only takes pharmaceutical `Medication` items.

**Proposal:** Add `non_drug_therapies` list to `MedicationModule` (or rename it `TreatmentModule`) with a small `NonDrugTherapy` object: `therapy_type` (enum: `ketogenic_diet`, `modified_atkins`, `ivig`, `plasmapheresis`, `steroids`, `other`), `status`, `response_text`.

### 2.8 Neurostimulation programming detail

VNS/RNS/DBS cases include device model, lead type, and programming parameters (mA, Hz, μs, on/off duty). Currently only device *type* is in `SurgeryType`.

**Proposal:** Add optional structured fields to `SurgeryHistoryItem` when `surgery_type` is a neurostimulation subtype: `device_model_text`, `stimulation_parameters_text` (Evidence[str]). Full parsing to numeric fields is a v0.3+ concern.

### 2.9 Ictal EEG frequency band

"medium-amplitude spike- and slow-wave complex (4–5 Hz)" — the Hz value carries diagnostic weight (e.g., 3 Hz generalized spike-wave for absence). Currently unrepresented.

**Proposal:** Add optional `dominant_frequency_hz` (float) to `IedFinding`. Keep it optional.

### 2.10 Structured "unknown" surgery

Post-infarct DRE case: "underwent epilepsy surgery at another hospital when he was 34 years old, though the specific type of surgery performed remains unclear." No `UNKNOWN` in `SurgeryType`.

**Proposal:** Add `SurgeryType.UNKNOWN`.

---

## 3. Design decisions worth reconsidering

### 3.1 Predominant vs. multiple seizure types with per-type frequency

Schema has `predominant_seizure_type` + `other_seizure_types` list. But cases like the LGS one say "6–7 tonic seizures **and** numerous atonic seizures **and** myoclonia daily" — three coexisting types, each with its own frequency. There is no way to tie a `SeizureFrequency` to a specific seizure type.

**Options:**
- (a) Keep current, note frequency as global; accept lossy encoding.
- (b) Replace flat lists with a `list[SeizureTypeWithFrequency]` object.
- (c) Add `frequency` field inside each `Evidence[SeizureType]` entry.

I'd argue (b) is cleanest but changes downstream code more than (a) or (c).

### 3.2 Convenience booleans on `MriModule`

`hippocampal_sclerosis` and `focal_cortical_dysplasia` bools duplicate information already in `findings`. If annotators fill both, they can disagree. Two options:
- (a) Drop the bools; require querying `findings` for the presence of HS/FCD.
- (b) Keep as convenience and add a validator that enforces consistency.

Reviewer preference — I lean (a) for tighter semantics.

### 3.3 Multiple imaging studies within one case

The paraneoplastic case had two MRIs (day 0 normal, day 8 bilateral hippocampal FLAIR hyperintensity). Under our schema each MRI is a separate `EpilepsyPhenotype` record — the day-0-vs-day-8 comparison happens at patient-level aggregation. This is fine, but the ontology doc (`SCHEMA_V0_1.md`) should say so explicitly so annotators don't try to squeeze two studies into one record.

**Proposal:** Add a paragraph to `docs/SCHEMA_V0_1.md` §2 clarifying the per-document unit rule and pointing at patient-level aggregation as a separate step.

---

## 4. Out of scope observations (flag for reviewer, don't necessarily add)

These appeared in real narratives but arguably belong in *other* studies rather than the Paper-1 phenotype schema:

- **CSF findings** (cells, protein, glucose, autoantibody panels). Relevant for autoimmune epilepsy workup. Small module possible; adds annotation burden.
- **Development / psychomotor status** ("severe psychomotor retardation", "regained developmental milestones"). Common in pediatric epileptic encephalopathies. Likely a separate cognitive-outcomes study.
- **Ictal complications** (seizure-related trauma, cerebral hemorrhage, SUDEP). Real and prognostically important, but arguably not phenotype extraction.
- **Quality of life / functional status** (wheelchair-bound, nursing home). Out of scope for phenotype.
- **Neurometabolic / neurogenetic testing panels** (what was ordered and results). Overlaps with etiology (§2.1) — could be part of that.

Recommendation: cover **autoimmune epilepsy** via etiology.immune + `causative_antibody` free text; leave CSF, development, and QoL for future papers.

---

## 5. Corpus-level notes

- **Diversity is adequate** for the eight themes queried; the schema was exercised on TLE, FLE, FCD, HS-associated, drug-resistant polytherapy, JME, LGS, paraneoplastic LE, and post-stroke DRE.
- **Under-represented in this corpus**: pure MRI reports, pure EEG reports, and pediatric-specific presentations. PMC case reports blend all doc types together. For eventual real evaluation, the actual institutional corpus (once IRB-approved) will exercise `MriModule` and `EegModule` in isolation as intended.
- **Not tested here**: applicability mask enforcement in production (the case reports aren't tagged by doc type), evidence-span offset stability, and negation/uncertainty language patterns at scale. These need pilot annotation to surface.

---

## 6. Recommended v0.2 change list

Ranked. Cheap changes at the top; larger structural changes at the bottom.

1. Add `SurgeryType.UNKNOWN`. *One line.*
2. Add MRI field strength to `MriModule`. *One field.*
3. Add ictal `dominant_frequency_hz` to `IedFinding`. *One field.*
4. Add `duration_seconds_min/max` to `SeizureFrequency`. *Two fields.*
5. Add Engel + ILAE outcome enums to `SurgeryHistoryItem`. *Two enums.*
6. Extend `MriFinding` with `moghe`, `fcd_palmini_iia`, `fcd_palmini_iib`. *Enum additions.*
7. Add `pathology_notes_text` Evidence[str] to `SurgeryHistoryItem`. *One field.*
8. Add `non_drug_therapies` list + `NonDrugTherapy` object to `MedicationModule`. *New value object.*
9. Add device/stimulation-parameter text fields on `SurgeryHistoryItem`. *Two fields.*
10. Add `etiology_category` + `etiology_details_text` (+ optional specifics) to `ClinicalSeizureModule`. *Requires reviewer discussion.*
11. Extend `SeizureType` with focal motor/non-motor subtypes per ILAE 2017. *Enum expansion — reviewer discussion.*
12. **Structural:** decide predominant-vs-multiple seizure representation (§3.1) and convenience-boolean policy (§3.2).

Items 1–9 are non-controversial and can be applied immediately if the reviewer concurs. Items 10–12 need epileptologist input.

---

**Next steps.** Combine this report with `docs/SCHEMA_V0_1.md` when sending to the epileptologist. The 8 open questions at the bottom of the schema doc plus this gap list form the v0.2 agenda.
