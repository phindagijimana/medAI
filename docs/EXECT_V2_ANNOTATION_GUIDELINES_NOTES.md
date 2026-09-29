# ExECT-V2 Annotation Guidelines — Curated Notes

**Source.** Extracted from `ExECT V2 .1 - What and How of annotating_v8.docx`,
Fonferko-Shadrach et al. 2024, J Biomed Semantics (github.com/swneurosci/ExECT-V2,
`Other/`). **Reference-only, not for redistribution.** Definitions and category
lists are reproduced verbatim below to inform our own annotation conventions;
we do not re-publish the source DOCX in this repository (the DOCX itself sits
only in `references/exect_v2/`, which is git-ignored).

**Purpose.** Phase 0.3 of the MedCAT+Rules build plan (`docs/MedCAT.md`).
These are the ExECT-V2 authors' per-field definitions and decision rules; we
mirror them here so that when we build our own annotation SOPs for the F-S 40
held-out re-annotation and MTSamples-neuro silver labels, we know exactly what
convention F-S trained the extractor against.

**Citations.**

- Fonferko-Shadrach B et al. *Extracting epilepsy patient data with ExECT.* BMC
  Med Res Methodol 2019 (v1 pipeline paper).
- Fonferko-Shadrach B et al. *Annotation guidelines for ExECT-V2.* J Biomed
  Semantics 2024 (v2 annotation paper).
- Repository: <https://github.com/swneurosci/ExECT-V2>

---

## 0. General annotation principles (verbatim, F-S 2024)

- All possible UMLS options from the loaded dictionary are shown once a term is
  highlighted; the UMLS list mixes epilepsy, seizure types, AEDs, and
  comorbidities, so annotators must select the correct entity.
- If a concept is not on the UMLS dropdown, search for a similar term (e.g.
  ASD → search "autism").
- Terms in the general UMLS list not exactly on ExECT's list should be flagged
  for future inclusion but only annotated with the UMLS match during
  validation.
- **Certainty** applies to Diagnosis, When-Diagnosed, Onset, Epilepsy Cause,
  Birth History, and Patient History — always to the *concept itself*, not
  its attributes. **Certainty is NOT applied** to Seizure Frequency,
  Prescription, or Investigations.
- **Polarity (Negation)** applies to all concepts *except* Seizure Frequency,
  Investigations, and Prescription. Missing attributes may be ignored.
  Currently only affirmed statements are annotated (exception: Febrile
  Seizures, where negated statements are also captured).
- **Dates** as attributes: DayDate, MonthDate, YearDate (4-digit).

---

## 1. Diagnosis (maps to our `EpilepsyType`, `SeizureType`)

**Definition (verbatim).** "Includes Epilepsy, Epilepsy type and syndromes,
seizure types. No generic 'seizure / absence / myoclonic jerk' should be
included. Past and present tense is accepted, but hypothetical statements are
not."

**Pattern.** *Diagnosis trigger or Person term → Epilepsy Term or Specific
Seizure.*

**Combined phrases.** Seizures in combined phrases such as "partial seizures
with secondary generalisation" are annotated as **two separate concepts**
(partial seizures + secondary generalisation). *Exception*: "focal to
bilaterally convulsive seizure" is one CUI (secondary generalised seizure).
Same for epilepsy compounds: "refractory focal epilepsy" → "refractory
epilepsy" + "focal epilepsy". But "symptomatic focal epilepsy" has its own
CUI and is annotated as one.

**Certainty examples (verbatim).**

- "diagnosed with focal epilepsy" → Certainty = 5.
- "possible complex partial seizures" → Certainty = 3.
- "Should her focal seizures continue…" → Certainty = 5 (we know seizures are
  happening; the hypothetical trigger "should" modifies the future action,
  not the current fact).
- "has not had a generalised tonic clonic seizure for a while" → Certainty = 5,
  Negation = Affirmed (usually does; even though sentence negates the recent
  occurrence, the concept itself is affirmed as historically present).

**Feature set (Diagnosis).** Certainty, Negation, UMLS concept + DiagCategory:
`{Epilepsy | SingleSeizure | MultipleSeizures}`.

---

## 2. Onset (maps to our `clinical_seizure.age_at_onset_years`)

**Definition (verbatim).** "Only specific seizure types or epilepsy should be
annotated. There are clear onset triggers to look out for: began, started,
first occurred, onset was, followed or preceded by age / time since / date or
other point in time."

**Triggers (List 3, verbatim).** started at age/date/time since; occurred;
appeared; manifested; new; began; onset; suffered … first; began to
experience; began to develop; first; suffering; has been symptomatic for x
number of years; suffering from for … time period; history is of … from the
age …; report him having … age / since date; background is … age / time since;
presented with; was noted to have; found to have; describes … from age.

**Non-onset words (verbatim exclusions).** "increased, continue, changed,
returned, are a clear indication of continuation rather than an onset, so
events in that context should not be annotated."

**Points in Time (List 4).** This_Year, Last_Year, Last_Clinic, Drug_Change,
From_Birth, Surgery, Discharge_Date, Last_Christmas, Birthday, Easter, 1960s,
1970s, 1980s, 1990s, 2000s, 2010s.

**Age groups (List 5, verbatim).** Used when age is not numeric:

| Phrase | Lower age | Upper age | Unit |
|---|---|---|---|
| baby | 0 | 12 | Month |
| infant | 0 | 12 | Month |
| neonate / neonatal period | 0 | 28 | Day |
| toddler | 1 | 3 | Year |
| early childhood / early years | 1 | 6 | Year |
| young child | 1 | 6 | Year |
| child / childhood | 2 | 12 | Year |
| primary school | 5 | 11 | Year |
| early adolescent | 10 | 14 | Year |
| adolescent / adolescence | 10 | 19 | Year |
| puberty | 10 | 17 | Year |
| secondary school | 12 | 16 | Year |
| teenager / teens / young | 13 | 19 | Year |
| early teenage / early teens | 13 | 14 | Year |
| mid teenage / mid teens | 15 | 16 | Year |
| GCSE / GCSE's | 15 | 16 | Year |
| late teenage | 17 | 19 | Year |
| A levels / A'levels / GCEs | 17 | 18 | Year |
| middle age | 45 | 65 | Year |
| one / one year | — | 12 | Month |
| year and a half / one and a half | — | 18 | Month |

**Decade patterns (verbatim).** "For decades e.g. fifties, age is annotated
as AgeRange 50–59. Early = 0–3, mid = 4–6, late = 7–9 years added to the
decade base." Example: "early fifties" → 50–53, "mid fifties" → 54–56, "late
fifties" → 57–59.

**Common mistake (verbatim).** "Onset of generic seizures such as absences,
myoclonic jerks, convulsions will be captured by Patient History so they
should not be annotated in Onset."

**Distinction Onset vs When Diagnosed (verbatim example).** "He was diagnosed
with epilepsy in 2017 but he had his first tonic clonic seizure in his teens."
Tonic-clonic seizure is the *onset*; epilepsy diagnosis (2017) is
*WhenDiagnosed*.

---

## 3. When Diagnosed (maps to structured epilepsy diagnosis event, not
currently a distinct schema field — used only as feature for
`clinical_seizure`)

**Definition (verbatim).** "Only specific seizure types, and epilepsy /
epilepsy syndromes should be annotated in phrases that clearly state that the
diagnosis was made. Triggers: Diagnosed / Diagnosis followed or preceded by
age / time since / date."

Feature set identical to Onset.

---

## 4. Patient History (maps to our `comorbidities`, `family_history` when the
subject is a relative — but F-S does not distinguish subject; we do)

**Definition (verbatim).** "Any other significant diagnoses, comorbidities,
accidents, non-specific seizures / seizure-like events, and specific
abnormalities identified on neuroimaging should be annotated here."

**Trigger lists used.** List 1 (Diagnosis Triggers), List 3 (Onset Phrases),
List 6 (Medical History: *past medical history, past medical history of, past
history of, used to suffer, background, was under the care, known to suffer,
comorbidities, labelled, on the record as*), List 7 (Opinion: *history
suggests, case of, history is suggestive, history is consistent, impression
is, suggestive, opinion is, description is consistent, does have, point
towards, I think, I am of the opinion, conclusion, likely explanation, would
seem, seems, evidence of*).

**Location conventions.** May appear as "other diagnoses at the top of a
letter", "background history", listed past events, or "concluding
comments/opinion".

**Overlap with Seizure Frequency.** "When a person trigger is present (i.e.
'her seizures') annotate as Patient History; seizure frequency on its own
should be ignored (e.g. 'he had no seizures since', 'his seizure frequency
is')."

**Features.** Age, Time Since, Date, or PointInTime.

**Febrile Seizures special case (verbatim).** "For febrile seizures we want
to extract both, Affirmed and Negated statements. Negated statements are
assigned a Certainty of 1 and are Negated. Febrile seizures may be given with
age, and here we try to use a range if a number of ages are given."

- "No history of febrile convulsions" → Certainty=1, Negation=Negated.
- "She had febrile seizure at the age of 3 and 5" → LowerAge=3, UpperAge=5,
  AgeUnit=Year (when no unit is given, "year" is implied).

---

## 5. Epilepsy Cause (maps to our `EtiologyCategory` + `etiology_details_text`)

**Definition (verbatim).** "Events in the patient's history that are stated
to be a cause of epileptic seizures or epilepsy. Identified by 'Causality
phrases' followed by a specific event, disease, or brain abnormality. UMLS
concepts and CUIs relate to the CAUSE and this must be highlighted by the
annotator, not the Epilepsy Term."

**Causality triggers (List 8, verbatim).** due to, caused by, related to,
subsequent to, result of, secondary to, associated with, left her/him with,
resulting from, resulted in, effect of.

**Exclusion (verbatim).** "Events that may trigger seizures, such as alcohol
intake, drug abuse, or medication should not be annotated here."

**Weak association example.** "Her epilepsy started following a fall she
sustained on holiday last year" — *not* annotated as cause; the fall preceded
onset but is not stated strongly enough.

---

## 6. Birth History (maps to our `birth_history`)

**Definition (verbatim).** "Injuries sustained during or before the time of
birth should be annotated here. These have their own CUIs, so it is important
to highlight a whole phrase while annotating for the UMLS match to appear."

**Normal birth** is annotated; **normal delivery** currently is not (revision
pending).

**Premature birth categories.**

- 37+ → `isTerm_Birth`
- under 37 → `isPreterm_Birth`
- 34–37 → `isLate_Preterm_Birth`
- 32–37 → `isModerate_To_LatePreterm`
- 28–31 → `isVery_Preterm`
- under 28 → `isExtreamelyPreterm`

Conversion note: "Levels of prematurity expressed in the number of weeks from
full term should be converted to gestational age in weeks." Example: "born 8
weeks prematurely" → 32to<37 = Moderate_To_LatePreterm.

---

## 7. Investigations (maps to our `MriModule`, `EegModule`, imaging.performed
booleans)

**Definition (verbatim).** "EEG/CT/MRI followed by an abnormal/normal result.
To find the UMLS match, a test type, and normal/abnormal must be entered in
the search box. For EEG, the type of test needs to be annotated, if stated
(it should not be assumed), otherwise it can be ignored."

**Unknown-result convention.** "When results are stated to be unknown —
annotate with a CUI for the test itself (i.e., EEG, MRI, or CT searching for
CT/MRI/EEG unknown)."

**Skip rule.** "Investigations without any mentions of result should be
ignored."

**Features (verbatim).**

- `MRI_Performed`: {Yes | No | Notknown}; `MRI_Results`: {Normal | Abnormal | Unknown}
- `CT_Performed`, `CT_Results`: same domain.
- `EEG_Performed`, `EEG_Results`: same domain.
- `EEG_Type`: {SleepDeprived | VideoTelemetry | Standard | Ambulatory |
  Prolonged}.

**EEG-result phrase table (List 9, ~55 entries).** Abnormal indicators
include: *abnormal, abnormalities, bilateral discharges, burst suppression,
dysrhythmic, epileptic, epileptiform, epileptogenic, focal discharge, focal
ictal rhythms, focal slowing, focus, generalised discharges, generalised
slowing, hypsarrhythmia, irregular, left/right side slowing, localised
discharge(s), localised repetitive discharges, low amplitude/voltage fast
activity, multifocal discharges, non-specific interictal changes,
paroxysmal fast activity, photoparoxysmal response, photosensitive,
photosensitivity, polyspike, polyspike-and-wave, sharp, slow spike and wave,
slow spike-wave discharges, slow wave, spike, spike and wave, spike-wave,
spike-wave discharges, spikes, temporal intermittent rhythmic delta activity,
temporal slowing, unstable*. Normal indicators: *both normal, clear, did not
capture any events, epileptic activity was not seen, failed to alter, no
changes, no significant findings, non-epileptic, normal, unremarkable*.
Unknown: *not available, not have the results*.

**MRI/CT-result phrase table (verbatim highlights).** Abnormal indicators:
*abnormal, abnormal signal, atrophy, atrophic changes, AVM, brain asymmetry,
astrocytoma, cavernoma, cerebral artery occlusion, cerebral oedema,
cerebral ischaemia, cortical dysplasia, CVA, degeneration, degenerative
brain disorder, DNET, encephalomalacia, glioma, gliosis, haemangioma,
haemorrhage, heterotopic grey matter, high intensity signal, lesion(s),
malformation(s), mass effect, non-specific lesion, sclerosis, signal
abnormality, signal intensity, tumour/tumor, white matter changes,
white-matter hyperintensities*. Normal indicators: *both normal, clear, no
significant findings, normal, unremarkable*.

---

## 8. Prescription (maps to our `MedicationModule.current_asms`)

**Definition (verbatim).** "We are only annotating **current** prescriptions
for antiepileptic drugs (AED) as: Drug name, Dose (quantity), Dose Unit
(mg/g), and Frequency."

**Rules (verbatim).**

- Drugs without a dose should not be annotated, **except for rescue
  medications** such as midazolam or diazepam (frequency = "As required").
- If frequency is NOT stated, use "once a day", or "As Required" for
  Clobazam and rescue drugs.
- UMLS list uses generic **and** brand names — match precisely (do not
  substitute).
- Extract AM/PM when mentioned.

**AED list (List 10, verbatim generic → brand).**

| Generic | Brand |
|---|---|
| Acetazolamide | — |
| Carbamazepine | Tegretol, Tegretol PR, Tegretol Retard |
| Clobazam | Frisium, Perizam |
| Clonazepam | — |
| Eslicarbazepine Acetate | Zebinix |
| Ethosuximide | Zarontin |
| Gabapentin | Neurontin |
| Lacosamide | Vimpat |
| Lamotrigine | Lamictal |
| Levetiracetam | Keppra, Desitrend |
| Nitrazepam | — |
| Oxcarbazepine | Trileptal |
| Perampanel | Fycompa |
| Phenobarbital | — |
| Phenytoin | Epanutin |
| Piracetam | — |
| Pregabalin | — |
| Primidone | — |
| Retigabine | — |
| Rufinamide | Inovelon |
| Sodium Valproate | Epilim, Epilim Chrono, Episenta; may be given as Valproic Acid |
| Stiripentol | — |
| Tiagabine | Gabitril |
| Topiramate | Topamax |
| Vigabatrin | Sabril |
| Zonisamide | Zonegran |

Note this is a UK-centric brand list; our Phase 4 US-adaptation layer must
add US-only brands (Keppra XR, Trokendi XR, Briviact, etc.) and drug-name
crosswalks (phenobarbitone→phenobarbital).

**Feature set.**

- `DrugName`: verbatim generic list above.
- `DrugDose`: numeric.
- `DoseUnit`: mg | g.
- `Frequency`: 1 | 2 | 3 | 4 | As Required (od / bd / tds / qds / prn).
  Default = 1 unless drug is midazolam or clobazam (→ As Required).

---

## 9. Seizure Frequency (maps to our `clinical_seizure.seizure_frequency`)

**Definition (verbatim).** "Seizures, specific seizures, absences, and
myoclonic jerks are to be annotated. Events, episodes, or other slang terms
should not."

"Seizure frequency relates to the current seizure experience described as a
number of seizures or seizure frequency change (increase, decrease, same,
etc.) during a defined time period or since a specific point in time."

**`TimeSince_or_TimeOfEvent` usage rule.** Only used when a date or point in
time is explicitly stated in the text. Values: `Since` | `During`.

**Canonical examples (verbatim).**

- "He had 5 seizures in May, but none since." →
  1. Seizure: NumberOfSeizures=5, MonthDate=5, TimeSince_or_TimeOfEvent=During
  2. Seizure: NumberOfSeizures=0, MonthDate=May,
     TimeSince_or_TimeOfEvent=Since
- "Seizure free for the last 2 months" → NumberOfSeizures=0,
  TimePeriod=Month, NumberOfTimePeriods=2.
- "His last generalised seizure was 5 years ago" → NumberOfSeizures=0,
  TimePeriod=Year, NumberOfTimePeriods=5, TimeSince_or_TimeOfEvent = *(unused
  — this is a duration, not a date/point-in-time).*
- "Since starting Lamotrigine his seizure frequency has improved" →
  FrequencyChange=Decreased, TimeSince_or_TimeOfEvent=Since,
  PointInTime=DrugChange.
- "Her last seizure was in September 2012" → NumberOfSeizures=0, MonthDate=9,
  YearDate=2012, TimeSince_or_TimeOfEvent=Since. *("in" would imply During,
  but "last … in <past date>" is treated as Since.)*

**Mnemonic (verbatim).** "No seizure since = 0 seizures Since; Last seizure
in <time period> = 0 seizures Since <time period>."

**Full feature set.** TimePeriod {Day|Week|Month|Year};
NumberOfTimePeriods; LowerNumberOfTimePeriods/Upper (range);
FrequencyChange {Same|Infrequent|Increased|Frequent|Decreased};
NumberOfSeizures; Lower/Upper (range); AgeUnit; Age; AgeLower/Upper;
DayDate; MonthDate; YearDate; TimeSince_or_TimeOfEvent; PointInTime.

**Word-number convention (List 11).** *single / once* → 1; *a couple / a
few / a number / multiple* → 2; *none* → 0.

**Common mistakes (verbatim).** "Annotating past seizure control, change, or
individual seizure event without a statement of frequency (e.g. 'placed on
Tegretol which controlled her seizures very well'; 'seizures recurred in July
2013')."

---

## 10. Certainty (Probability) Levels (List 2)

| Level | Anchor phrases (subset) |
|---|---|
| 1 (ruled out) | ruled out |
| 2 (unlikely / doubt) | doubt, improbable, not convincingly, remote, unclear, unsure, ??, doubtful, not convinced, not likely, remote possibility, unlikely, unusual |
| 3 (possible) | considered, describes himself, ?, could be, further clarification, investigate her along the lines, markers, might, possible, possibility, potentially, potential, to be sure, to see if, uncertain, further investigation, to see whether, to be confirmed, to know whether |
| 4 (probable) | not conclusive, suspicious, suspect, suggestive, sound like, supports, suspected, suspicion, I think, is in keeping with, point more towards, probable, compatible with, impression is, likely, point towards, probably, supportive of, treated as |
| 5 (definite) | consistent with, is conclusive, are dealing with, certain, definite, in keeping with |

**Mapping to our `Certainty` enum.**

- ExECT Level 5 → `Certainty.DEFINITE`
- ExECT Level 4 → `Certainty.PROBABLE`
- ExECT Level 3 → `Certainty.POSSIBLE`
- ExECT Level 2 → `Certainty.POSSIBLE` (we do not distinguish "unlikely" —
  Phase 8 refinement may split)
- ExECT Level 1 → `Certainty.NEGATED` (when concept is stated ruled-out) or
  `Certainty.UNKNOWN` (when the sentence just says "not conclusive"
  hypothetically)

---

## 11. Cross-mapping to our v0.2.1 schema

| ExECT field | ExECT features → our schema fields |
|---|---|
| Diagnosis | `EpilepsyType`, `SeizureType`, `Certainty`, negation → `TemporalStatus.HISTORICAL` when past tense |
| Onset | `clinical_seizure.age_at_onset_years.value` (compute from AgeLower/Upper or from AgeGroup lookup) |
| When Diagnosed | not a distinct field; store as an Evidence attached to Epilepsy diagnosis if we later add it |
| Patient History | `comorbidities`, `family_history` (only when subject is relative) |
| Epilepsy Cause | `EtiologyCategory` + `etiology_details_text` + `etiology_specifics.*_text` |
| Birth History | `birth_history` (prematurity buckets → free-text field) |
| Investigations MRI | `MriModule.findings[]`, `overall_normal`, MRI performed boolean |
| Investigations CT | not currently in schema — treat as `EegModule`-analog if we add CT support, else drop |
| Investigations EEG | `EegModule.background`, `ied_findings`, `EegStudyType`, `EegBackground` |
| Prescription | `MedicationModule.current_asms[]` (Medication.generic_name / dose_text / status = CURRENT) |
| Seizure Frequency | `clinical_seizure.seizure_frequency` (SeizureFrequency: count_min/max, period, seizure_free, raw_text, applies_to_type) |
| Certainty (levels 1–5) | `Certainty` enum (5→DEFINITE, 4→PROBABLE, 3→POSSIBLE, 1/2→NEGATED/POSSIBLE per context) |

Fields **NOT covered** by ExECT-V2 that we must source elsewhere: `Awareness`,
`LobarLocalization`, `Laterality`, `LocalizationSource`, `FocalMotorOnset`,
`FocalNonmotorOnset`, `IedType` sub-types, `SurgeryType`, `EngelClass`,
`IlaeOutcome`, `NonDrugTherapyType`, `CausativeAntibody`, `DrugResistanceStatus`
(derived), `ConcordanceStatus` (derived). These are Phase 3 P2 work — see
`docs/MedCAT.md` §Phase 3 P2 table.

---

## 12. UK → US idiom drift (annotation-guideline-driven)

Terms in the guidelines that must be flagged for US-adaptation (Phase 4):

- **Spellings.** oedema, haemorrhage, ischaemia, tumour, generalised,
  localised, paediatric, foetal — normalize to US equivalents in
  `rules/uk_to_us_lexicon.py`.
- **Drug brands** (List 10). Most UK brands (Tegretol, Zarontin, Keppra) also
  ship in the US; but Epilim, Epanutin, Zebinix, Zonegran, Fycompa, Vimpat,
  Inovelon, Sabril, Frisium, Perizam, Desitrend, Trileptal have varying US
  availability. US-only additions to add: Keppra XR, Trokendi XR, Qudexy XR,
  Briviact, Xcopri, Fintepla, Diacomit.
- **Certainty phrases.** UK style leans on "in keeping with" (Level 5). US
  clinicians more often write "consistent with" (also Level 5), "concerning
  for" (~Level 3–4, must be added), "worrisome for" (~Level 3–4). Add these
  to `rules/context_config_us.py`.
- **Time phrases.** ExECT PointInTime uses "GCSE" and "A-levels" (UK school
  milestones) — remove these from the US lexicon; retain generic
  "early_teens" / "late_teens".

---

*End of curated notes.*
