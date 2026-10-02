# NINDS Epilepsy CDE mapping (MedAI-EPI schema v0.2.1)

Status: first version, 2026-10-01. Decision D2 in `docs/SCOPE_DECISIONS.md` §3.2.

## 1. What this is, and what it is not

A documentation and export table: which MedAI-EPI field corresponds to which element of the NINDS
Epilepsy Common Data Elements (CDEs), so that LEO output can be compared with other epilepsy
networks that collect the CDEs. It changes **nothing** in extraction, retrieval, fusion or scoring.
It is not an ontology source and nothing here is loaded at run time.

## 2. Sources and how much was checked

Access date for everything below: **2026-10-01**. Definitions are paraphrased, not copied.

| Source | What I read | Used for |
|---|---|---|
| [N1] NINDS CDE Epilepsy landing page, <https://www.commondataelements.ninds.nih.gov/epilepsy> | Overview text only. The element lists are loaded by script and were not readable by my fetch tool. | Confirms the module structure and that CDEs are graded Core / Supplemental-Highly Recommended / Supplemental / Exploratory. |
| NINDS "Classification of Seizures" form (PDBP data dictionary, <https://pdbp.ninds.nih.gov/dictionary/publicData/dataStructureAction!lightboxView.ajax?dataStructureName=ClassificationSeizures&publicArea=true>) | Full element list (8 elements, short names). | Seizure-type rows. |
| MDM-Portal copy of the NINDS "Drugs" module (<https://medical-data-models.org/14646>, uploaded 2016-04-25, CC BY-NC 3.0) | Full AED log, AED resistance log and non-AED medication log, with code lists. | Medication rows. |
| MDM-Portal copy of "Classification of Etiology, Seizures and Syndromes by Age of Onset" (<https://medical-data-models.org/43611>) | Partial (the page was truncated). | Etiology and syndrome rows, with lower confidence. |
| Loring DW et al. 2011, *Epilepsia* 52:1186-1191 (PMC3535455) | Abstract-level summary: nine content areas; ILAE-based classification forms are core. | Context. |

The MDM-Portal copies are third-party mirrors from 2016. The CDEs have been revised since (the
overview says they are reviewed periodically), so **every row marked "check" must be confirmed on
the current NINDS site before an export is promised to anyone.** The Epilepsy "Start-up Resource
Listing" on the NINDS page (Core and Supplemental-Highly Recommended elements) was not read; it is
the next thing to open.

Confidence column: **V** = element name read in a source above; **P** = partial or mirror copy only;
**N** = I could not find a matching NINDS element (this is not proof that none exists).

## 3. Mapping

### 3.1 Seizures and epilepsy classification

| MedAI-EPI field (`clinical_seizure.*`) | NINDS element or module | Conf. | Notes |
|---|---|---|---|
| `predominant_seizure_type`, `other_seizure_types[]` | Classification of Seizures: `SeizClassTyp` (type of seizures present, by classification), `SeizGenClassTyp` (generalized subtype), `SeizFocClassTyp` (focal subtype), `SeizUnclassClassTyp` (unclassifiable) | V | The NINDS form records each subtype as present or not (`SeizPresentStatus`); we store one predominant type plus a list. Export: the predominant type sets its subtype element to present; each entry of `other_seizure_types` likewise. A patient with several types needs `SeizMultConfLvlDistinctTyp` (how sure it is that they are distinct types), which we do not extract. |
| `awareness` | The focal-subtype list distinguishes seizures with and without impaired awareness | P | Check the exact permitted values on the current form before mapping `focal_aware` / `focal_impaired_awareness`. |
| `epilepsy_type` (focal / generalized / combined focal and generalized / unknown) | Classification of Etiology, Seizures and Syndromes by Age of Onset (syndrome classification) | P | NINDS classifies **seizures** and **syndromes**; it has no single "epilepsy type" element that I could find. Export `epilepsy_type` only as a derived value (all seizure types focal, all generalized, or both) and label it as derived. |
| `etiology_category` (structural / genetic / infectious / immune / metabolic / unknown) | Same module, etiology item group (genetic or presumed genetic, structural/metabolic, immune, infectious and others, with a confidence code list: No, Possible, Probable, Definite, Unknown, N/A) | P | Our field is a single category; NINDS grades confidence per etiology. Export maps our value to "Definite" only if the note states it plainly; otherwise leave blank. We do not extract a graded confidence. |
| `etiology_specifics` (gene, variant, antibody, tumor, pathogen, metabolic text) | Etiology items and free text | P | Check. |
| `age_at_onset_years` | none found | N | The CDE pages I could reach do not name an onset-age element. The 2023 pediatric EHR CDE set (PMC10508354, a different standard) has "age at onset" under Epilepsy History. Open the NINDS "Epilepsy history" or "Subject characteristics" module to confirm. |
| `seizure_frequency` (`count_min`, `count_max`, `period`, `seizure_free`) | none found | N | Same. The pediatric EHR set records frequency in nine levels, not counts per period; a lossy mapping would be needed in that direction. |
| `status_epilepticus_history` | not examined | N | Check the seizure-history module. |
| `semiology_text`, `focal_motor_onset`, `focal_nonmotor_onset` | not examined | N | Check. |

### 3.2 Medication (`medication.*`)

The NINDS AED log is one line per drug (and per dose change). Our `Medication` holds one drug with a
status. The fit is good for current drugs and weaker for stopped ones.

| MedAI-EPI field | NINDS AED log element | Conf. | Notes |
|---|---|---|---|
| `generic_name` | Name of antiepileptic drug; "generic or brand used" (generic / brand / unknown) | V | We store the generic name and drop the brand; export the flag as "unknown" unless the brand appeared in the quote. |
| `dose_text` | Dose (a number) with unit (code list: g, gr, gtt, mcg, mcL, mg, mL, oz, spray, suppository, tablespoon, teaspoon, other, unknown); dosing schedule times of administration; formulation; route | V | `dose_text` is free text. Splitting it into number, unit, schedule, formulation and route is not done by the extractor; an export needs a parser, or leaves those elements empty. |
| `status` = CURRENT | "Ongoing" (yes/no) with no end date | V | Direct. |
| `status` = PRIOR or FAILED | End date, "ongoing" = no, and reason for discontinuation | V | We rarely have dates. |
| `reason_discontinued` | Reason for discontinuation code list: idiosyncratic side effect, dose-related side effect, chronic side effect, inadequate seizure control, other | V | `FAILED` corresponds to "inadequate seizure control"; `DISCONTINUED_ADVERSE_EFFECT` to the first three; the finer split is not extracted. |
| `status` = PLANNED | none | N | The AED log is retrospective; a planned drug has no row. Exclude from an export. |
| Rescue drugs (`medication.rescue_medication`, leo-v0.5) | Dosing schedule flag "N/A - taken PRN", and "average frequency = times per month" | V | The log has no separate rescue class; a rescue drug is an AED line flagged as taken as needed. This matches how we treat it: documented alongside, not as a daily drug. |
| Acute in-clinic doses (`medication.acute_administration`) | none | N | Not a home-medication log item. Keep out of the export. |
| `drug_resistance_status` | AED resistance log (was the drug appropriate for the syndrome; 3 months of therapy achieved; dose adjusted; seizures continued despite adjustment) | V | The log asks four questions per drug; our field is one patient-level label. Export is not derivable. |
| `non_drug_therapies[]`, `surgery_history[]` | Surgery and pathology, and other-therapy modules | N | Not examined. |
| non-epilepsy medicines | Non-AED medication log (generic name, dose, schedule, dates, ongoing, indication) | V | We do not extract these. |

### 3.3 EEG, MRI, localization

Not examined. The NINDS Electrophysiology and Imaging areas exist (Loring 2011 lists nine content
areas), and SCORE ([N2]) is the EEG reporting standard of record. A mapping would be added when the
EEG and MRI modules of the schema are scored, which they are not yet in any LEO result.

## 4. Counts and limits

* Of the fields LEO scores (epilepsy type, predominant seizure type, age at onset, seizure
  frequency, current ASMs), seizure type and the medication list have a named NINDS counterpart;
  epilepsy type is derivable; seizure frequency and age at onset have **no counterpart that I
  found**. Those two are fields most research networks want, so confirming them is the first
  action item.
* Most mappings are many-to-one or lossy in one direction (our single value to their per-item
  grid, or their four reasons to our two statuses). The export would be one-way from MedAI-EPI to
  CDE; reading CDE data into MedAI-EPI is out of scope.
* No clinician has reviewed this table. It was built from web sources by the engineer.

## 5. Next steps

1. Open the current NINDS site (Start-up Resource Listing, Epilepsy "Seizures and syndromes" and
   "Epilepsy history" modules) and settle every **P** and **N** row; record the page version.
2. Ask the epileptologist whether the seizure-type export rule (predominant type present, others
   present) is acceptable.
3. If an export is wanted: write `scripts/export_ninds_cde.py` against the confirmed table. Do not
   write it before step 1.
