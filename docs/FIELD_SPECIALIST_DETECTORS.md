# Extra field-specialist detectors (plan)

**Status (2026-10-07):** P0–P2 and no-train Wave 2 / remaining-hole sidecars are
implemented. Default LEO is unchanged (L1C + optional X1C/P1C/F1C, EpExtra, D17
rules-shown, Arm E off). Opt-in `--ext-detector` names below. B1 / trained
Xie/Decker heads and Engel (no catalogue column) are **not** registered.
v4_ext rematch with all 10 names on: `docs/EVAL_PROTOCOL_LEO.md` §10.40 (new
prefixes; not a headline). Sidecar-only never ACCEPT.

This is **not** another Med42 prompt and **not** a gazetteer dump into E.
A literature reader is an opt-in named detector that emits **existing LEO
columns** with a quote. B-arm *scoring vs E* stays in
`docs/E_EXTERNAL_BASELINES.md`. This document is the fusion-sidecar path.

## 1. Guardrails (do not affect LEO)

1. Flag off (`--ext-detector` unset) → bitwise-identical claims, verdicts, and
   five-field F-S / v4_ext headlines. Test this first.
2. Do not load CUIs, brands, or SCORE/EpSO/ICD into `rules/epilepsy_ontology.py`.
3. Do not change D17, `--disagree-llm candidate`, or research extract
   (`accepted` ∧ `specialist+llm`).
4. No majority vote. ExECT has no second reader; published hybrids treat
   disagreement as review.
5. Sidecar **never auto-accepts** and **never demotes** an E+L accept. Auto-accept
   still requires specialist + llm. The sidecar is a third opinion for the
   reviewer and for offline “what if” scoring.
6. One system at a time. Overlapping columns only. Same notes and gold. Never MIMIC.
7. Extra LLM readers (X1C/P1C/F1C) already give every extract field a *second*
   reader when `--ext-reader` is on. Literature systems are a *third* reader on
   those cells, or a cheap CPU second reader for meds when the GPU path is off
   — still without granting accept.

Fusion today (`docs/LEO_ROUTING_RULES.md`): E vs L only; detectors `epextra` /
`llm`. Sidecar adds a named detector (`ctakes`, `b1`, …) and optional
`sidecar_alternative`. It does not replace `alternative` (that stays the
other of E/L).

## 2. Who already reads each cell

X1C/P1C/F1C merge into the `llm` detector; they are not separate fusion parties.
`--no-ext-reader` drops everything except L1C’s five core fields.

| LEO phenotype | Field path | E | L1C | X1C | P1C | F1C | Second reader today |
|---|---|---|---|---|---|---|---|
| epilepsy_type | `clinical_seizure.epilepsy_type` | ✓ | ✓ | | | | E+L1C |
| seizure_type | `clinical_seizure.predominant_seizure_type` | ✓ | ✓ | | | | E+L1C (often clash) |
| age_at_onset | `clinical_seizure.age_at_onset_years` | ✓ | ✓ | | | | E+L1C |
| seizure_frequency | `clinical_seizure.seizure_frequency` | ✓ | ✓ | | | | E+L1C (ExECT-weak) |
| current_asms | `medication.current_asms` | ✓ | ✓ | rescue only | | | E+L1C (maintenance) |
| rescue_medication | `medication.rescue_medication` | ✓ | | via rescue on current path | | | E+X1C |
| acute_administration | `medication.acute_administration` | ✓ | | | | | E only (REVIEW by rule) |
| prior_asms | `medication.prior_asms` | ✓ | | | ✓ | | E+P1C |
| failed_asms | `medication.failed_asms` | ✓ | | | ✓ | | E+P1C (weak) |
| drug_resistance | `medication.drug_resistance_status` | derived ± as-stated | | | | ✓ as-stated | E+F1C |
| awareness | `clinical_seizure.awareness` | ✓ | | | ✓ | | E+P1C |
| other_seizure_types | `clinical_seizure.other_seizure_types` | ✓ | | | ✓ | | E+P1C |
| etiology_category | `clinical_seizure.etiology_category` | ✓ | | | ✓ | | E+P1C |
| etiology_details / specifics | details + specifics | ✓ | | | | ✓ | E+F1C |
| semiology | `clinical_seizure.semiology_text` | ✓ | | | | ✓ | E+F1C |
| focal motor / non-motor | onset fields | ✓ | | ✓ | | | E+X1C |
| eeg study / IED / ictal | `eeg.*` (core) | ✓ | | ✓ | | | E+X1C |
| eeg seizures captured | present + count | ✓ | | | ✓ present | ✓ count | E+P1C/F1C |
| mri normal / findings / lesion | `mri.*` | ✓ | | | ✓ | | E+P1C |
| HS / FCD | bools | ✓ | | | ✓ | | E+P1C (P1C fills blanks) |
| mri_negative / tesla | | ✓ | | | | ✓ | E+F1C |
| surgery_history | `medication.surgery_history` | ✓ | | ✓ | | | E+X1C |
| Engel / ILAE outcome | schema `SurgeryHistoryItem.engel_class` / `ilae_outcome` | not in extract catalogue | | | | | **no LEO column** |
| concordance | `integrated.concordance` | derived | | | | ✓ as-stated | E+F1C |
| status epilepticus / non-drug / localization | | ✓ | | | ✓ | alt loc F1C | E+P1C/F1C |

A published extractor may be appended **only** if it can emit one of the paths
above (or a documented subset, e.g. drug generic name + current/prior). Engel
is schema-ready but not a LEO phenotype; Adelson cannot sit in fusion until
that column exists — that would be a new field, not a sidecar.

## 3. Match published extractors to those cells

### Wave 1 — runnable or in-repo; can sit in fusion as a sidecar

| Id | System | Paper | Overlapping LEO cells | Why it can sit in fusion | Catch |
|---|---|---|---|---|---|
| **S1** | cTAKES (prefer) or CLAMP | Savova 2010; Soysal 2018 | `current_asms`, `prior_asms`, rescue vs maintenance if assertion maps; negation on MRI/EEG *mentions* as a check on those bools | Apache cTAKES is the documented US med+negation toolkit; first B-arm in `E_EXTERNAL_BASELINES.md`; CPU, no GPU | Not ILAE types. CLAMP license. Map UMLS drug → RxNorm generic via existing canonicaliser |
| **S2** | i2b2/n2c2 **status layer** on S1 mentions | Uzuner 2010 meds | current / discontinued / dose → `current_asms` vs `prior_asms`; PRN → rescue; one-off → `acute_administration` | This is the failed-ASM and “stopped still current” task. Not a second binary: it is assertion on the same mentions | Do **not** use i2b2 notes as gold. Failed-for-lack-of-effect needs a reason cue; if missing, leave `failed_asms` to E+P1C |
| **S3** | B1 BioClinicalBERT head | Alsentzer 2019; `services/baseline_bert.py` | start with `epilepsy_type` only | Scaffold and checkpoint path already exist. Closed enum, cheap CPU/GPU | Must train on **our** labels (F-S train letters, not EA0161–EA0200). Tiny slice. Quote from token-BIO if trained, else span-less → cannot auto-accept anyway |

**Not Wave 1 as a detector:** ConText / medspaCy (Harkema 2009; Chapman; Eyre 2021).
That is an engine **inside E**. Ablate in `docs/METACAT_EVAL.md`. Do not score
ConText vs LEO F1. Do not add a second ConText as `detectors=["context"]`.

### Wave 2 — literature *tasks* we would train; no public weights

Copy the job, not the network (`docs/CORPUS_OUTREACH.md`). Same sidecar
contract once a model exists.

| Id | Task (paper) | LEO cells | Why later | Blocker now |
|---|---|---|---|---|
| **T1** | Seizure frequency (Xie *JAMIA* 2022/2023; Abeysinghe *npj Digit Med* 2025) | `seizure_frequency` (± `other_seizure_frequencies`) | Highest-value specialist: ExECT frequency is the weak field; L1C already reads it so a dedicated head is a true third reader | **No-train sidecar shipped:** `--ext-detector freq` (current stated rate + seizure-free). Trained Xie/Abeysinghe head still not registered |
| **T2** | Seizure type (Decker *Seizure* 2022) | `predominant_seizure_type`, `other_seizure_types` | E and L1C clash here; candidate policy already shows L | **No-train sidecar shipped:** `--ext-detector stated-type` (explicit ILAE phrases only; no CPS→focal-impaired map). Trained Decker head still not registered |
| **T3** | HS on MRI text (AutoHS-class imaging NLP) | `mri.hippocampal_sclerosis` (± FCD) | P1C already fills HS/FCD blanks; a dedicated HS head matches a published imaging task | **No-train sidecar shipped:** `--ext-detector hs` (mention+NegEx; never `false` if MRI unmentioned). AutoHS-on-pixels and B1 MRI heads still not registered |
| **T4** | DRE as stated (Kwan 2010 definition; no published no-train extractor — Xie 2022/2023 do not extract DRE) | `medication.drug_resistance_status` (as-stated only) | F1C already reads as-stated; compound Kwan inference stays E | **No-train sidecar shipped:** `--ext-detector dre` (explicit Kwan phrases only). Do not gazetteer “refractory” **into E**. Two-failed-drug count stays E |

### Wave 3 — do not append

| System | Why not a LEO sidecar |
|---|---|
| ExECT v2 | Already **is** E |
| SCORE / EpSO / ICD / Orphanet / NINDS CDEs | Vocabularies for O or mapping, not extractors. Opt-in `--export-codes` after extract (`docs/ROLE_PLACEMENTS.md`). Still not E gazetteers |
| MetaMap | Closer to MedCAT / O than to a field reader |
| Mayo EEG-report NLP | Only if the document *is* an EEG report; clinic notes stay X1C |
| Adelson 2026 Engel/ILAE agents | Schema has `engel_class` / `ilae_outcome`; **not** in the extract catalogue. New column, then a reader — not a voter on `surgery_history` |
| Penn / West Virginia University / closed institutional weights | Outreach only; cannot sit in fusion this week |
| 70B / CoT / self-consistency | Another L, not a field specialist. Not shipped (`docs/ROLE_PLACEMENTS.md` §4) |
| Second ConText | Inside E. Ablate with `--context-engine`; do not score as a phenotype system |

## 4. How a sidecar sits in fusion (without changing LEO)

Contract for every Wave 1/2 system:

```
note → { field_path: { value: <schema enum or drug dict>, quote: <verbatim> } }
detector name: "ctakes" | "freq" | "stated-type" | "hs" | "b1" | ...
```

Map through `schema/enums.py` and `rules.fields.medication.canonicalize_drug_name`.
Drop values whose quote is not in the note (same `ground_value` as L).

Per overlapping cell, after E vs L has already run:

| E vs L | Sidecar | Default LEO (unchanged) | Extra (flag on) |
|---|---|---|---|
| agree | agrees | ACCEPT `specialist+llm` | append detector name; no verdict change |
| agree | disagrees | ACCEPT | keep ACCEPT; store sidecar value as `sidecar_alternative` |
| disagree | agrees with shown (E) | REVIEW, E shown | REVIEW; note sidecar sided with E |
| disagree | agrees with L | REVIEW, E shown (D17) | REVIEW; note sidecar sided with L |
| disagree | third value | REVIEW | REVIEW; sidecar as `sidecar_alternative` |
| specialist only | any | existing specialist-only rules | still no accept from sidecar alone |
| llm only | any | REVIEW `llm_only` | unchanged |

Offline (not default): score a **hypothetical** voter
`agree(E, sidecar)` vs `agree(E, L)` on the overlapping subset. That is a
table in EVAL, not a runtime policy.

CLI: `--ext-detector NAME` (repeatable). Independent of `--ext-reader`. Off with H2
unless passed, same spirit as extra LLM readers.

## 5. Phased work (when we implement)

**P0 — contract, LEO frozen** — done (`services/ext_detectors/`, `ChainPipelineConfig.ext_detectors`, tests in `tests/test_ext_detectors.py`).

**P1 — S1 cTAKES-style dictionary NER** — done as Python lookup of the RxNorm ASM lexicon + Chapman NegEx. Not the Java UIMA binary (set aside unless `CTAKES_HOME` is added later). `--ext-detector ctakes`.

**P2 — S2 i2b2 status on S1 mentions** — done in the same detector: current / discontinued / failed / planned-drop / PRN→rescue / one-off→acute. Dose on the span.

**P3 — S3 B1 `epilepsy_type`**

- Train on F-S letters **outside** the held-out 40 (EA0161–EA0200).
- Emit enum + optional BIO quote. Sidecar on `clinical_seizure.epilepsy_type` only.
- Do not extend B1 to all fields in the same drop.

**P4 — Wave 2 no-train sidecars** — done (`freq`, `stated-type`, `hs`). Trained T1–T3 heads remain after labels (F-S train letters; never EA0161–EA0200; never v4_ext if E was edited from it).

**P4b — remaining holes, guideline language only** — done (`fail-reason`, `rescue-if`, `ictal`, `eeg-done`, `dre`, `first-feature`). High precision when the note *states* the fact; not a published clinic-letter F1. Sidecar silence cannot un-accept E (D18). Engel not registered. `acute_administration` stays on `ctakes` (Uzuner one-off); no extra LLM field added.

**P5 — never in this track**

- ExECT v2, SCORE-as-reader, ontologies into E, Adelson without a catalogue
  column, EEG-report models on clinic letters, MIMIC, majority vote.

## 6. What “success” is (and is not)

This track supports **field specialists** for review and for a fair B-arm.
It is not an accuracy claim against Med42 and must not be titled as one.

Useful if: reviewers see a third med/type/frequency/HS opinion with a quote;
CPU cTAKES runs without quadrupling GPU time; offline tables show where
sidecar would have sided with gold on E–L disagreements.

Not useful if: default F1 moves; E’s lexicon grows; three-way vote auto-accepts;
Engel/SCORE/ICD appear as if they were phenotype readers.

## 7. Shipped map (2026-10-07) — traceability

Protocol: **D18–D20** and **§10.33–10.35** in `docs/EVAL_PROTOCOL_LEO.md`. D17 not flipped.

| Kind | Path |
|---|---|
| Contract / this plan | `docs/FIELD_SPECIALIST_DETECTORS.md` |
| B-arm policy (distinct; still unscored) | `docs/E_EXTERNAL_BASELINES.md` |
| Fusion + `sidecar_only` | `docs/LEO_ROUTING_RULES.md` |
| Operator | `docs/LEO_USER_GUIDE.md` (`--ext-detector`, `*_sidecar`) |
| Citations | `docs/REFERENCES.md` (Savova, Uzuner, Chapman; Xie/Decker = tasks; Kwan, NINDS CDE, Pina-Garza, Fisher 2017, ACNS Hirsch; Alsentzer/Adelson = not registered) |
| Registry | `services/ext_detectors/__init__.py` (`KNOWN_EXT_DETECTORS`, `parse_ext_detectors`) |
| S1+S2 | `services/ext_detectors/ctakes_meds.py` |
| T1 no-train | `services/ext_detectors/freq.py` (`--ext-detector freq`) |
| T2 no-train | `services/ext_detectors/stated_type.py` (`--ext-detector stated-type`) |
| T3 no-train | `services/ext_detectors/hs.py` (`--ext-detector hs`) |
| Shared NegEx window | `services/ext_detectors/span.py` |
| Guideline remaining holes | `services/ext_detectors/guideline.py` (`fail-reason`, `rescue-if`, `ictal`, `eeg-done`, `dre`, `first-feature`) |
| Attach without changing verdicts | `services/ext_detectors/attach.py` |
| Pipeline | `ChainPipelineConfig.ext_detectors`, `services/chain_pipeline.py` |
| Runtime / CLI / env | `LeoRuntime.ext_detectors`, `--ext-detector`, `MEDAI_LEO_EXT_DETECTOR` |
| Claim + table | `Claim.sidecar_alternative`, `ReasonCode.SIDECAR_ONLY`, `*_sidecar` in `leo_tabular` |
| Tests | `tests/test_ext_detectors.py` |

Flags: off unless `--ext-detector NAME` or `MEDAI_LEO_EXT_DETECTOR` (comma list). Known: `ctakes`, `freq`, `stated-type`, `hs`, `fail-reason`, `rescue-if`, `ictal`, `eeg-done`, `dre`, `first-feature`. Independent of `--ext-reader`. `--ext-detector b1` / `xie` / `decker` still raise (need training); `engel` raises (not a catalogue column).

## 9. Remaining field weaknesses — literature (2026-10-07)

There are **no published, no-train extractors with good clinic-letter accuracy** for most leftover holes. ILAE / ACNS / NINDS / JAMIA give either (a) a stated-phrase list (high precision, not a measured F1) or (b) a trained model / EEG-report system we cannot download. Do not dump the phrases into E.

### Can be a no-train sidecar (guideline language) — shipped in `guideline.py`

| Field | Source | Sidecar | Honest accuracy |
|---|---|---|---|
| Failed ASM *reason* | NINDS Epilepsy CDEs; Kwan 2010 | `fail-reason` | Precision when the reason is written. ~20% of notes omit it. Will not fix 4/27 if E guessed without a reason sentence |
| Rescue vs instruction | Pina-Garza 2024; Epilepsy Foundation; NINDS trial-criteria workshop | `rescue-if` | No published F1. Skips if-clause / inpatient PRN. Silence cannot demote E’s false rescue |
| Ictal onset false + | ACNS Hirsch 2021 (*J Clin Neurophysiol* 38(1):1–29) | `ictal` | Emit lobe only if captured; `seizures_captured=false` on “no ictal onset”. Not a new ACNS gazetteer in E |
| EEG study type done vs recommended | ACNS + ExECT skip *as a sidecar* | `eeg-done` | Helps CPU. X1C already 36/37 on GPU. No paper F1 on letters |
| DRE as-stated | Kwan 2010 (our task; not from Xie) | `dre` | Explicit phrases only. Misses inferred DRE (E’s two-drug count + F1C) |
| Focal first feature | Fisher 2017 instruction manual | `first-feature` | Only with “begins with / onset with”. Letters often mix whole-seizure semiology (X1C 7/12) |
| `acute_administration` | Uzuner 2010 one-off | already `ctakes` | No extra LLM field added (would change the X1C/P1C contract) |
| Engel / ILAE class | Wieser 2001; Adelson 2026 | **not registered** | High precision if written, after that column exists. `--ext-detector engel` raises |

### “Good accuracy” papers that are the wrong tool or document

| Field | Paper | Why not a no-train letter reader |
|---|---|---|
| IED / seizures on EEG | Biswal & Westover *EMBC* 2015; Frontiers *Neurol* 2025 keyword NLP (88–97% on reports) | **EEG reports**, not clinic letters. Gate on an EEG section if reused |
| Frequency counts | Xie *JAMIA* 2022 (F1 >0.80); Decker *Seizure* 2022 (0.82 in-house, **0.40** external) | Need their labels/rules. `freq` is the no-train ceiling |
| Failed-drug events | Liu et al. *JAMIA* (DDC+reason AUC 0.75) | Trained on UMass notes; no public weights |
| Surgery candidacy | Wissel et al. Cincinnati Children's, *Epilepsia* 2019, doi:10.1111/epi.16398 (prospective AUC 0.79) | Referral score, not “had VNS vs offered VNS” |
| Engel | Adelson 2026 (West Virginia University) agents, *Epilepsia* 67(9):4483–4492 | LLM on their notes; no LEO column |
| Semiology → EZ | Zhang *JMIR* 2025 | Case reports + ChatGPT, not letters |
| Age at onset | Tao S, Abeysinghe R, et al., *AMIA Jt Summits Transl Sci Proc* 2023:515–524, PMID 37350927 (rules, first-seizure onset F1 0.697, EMU summaries) | Wrong note type; we already have E+L1C |
| MRI extra findings | ILAE/Blumcke catalogues; AutoHS | Pixels or more E gazetteer. Extra-lesion P 0.50 is partly gold incomplete |
| IFCN IED criteria (Kural et al.) | Waveforms, not note text | |

NINDS CDEs remain vocabularies for O (Wave 3) except the **discontinuation-reason phrases** used by `fail-reason`. SCORE/EpSO/ICD stay out of E; `--export-codes` maps them after extract.

## 8. Pointers

- Fusion: `docs/LEO_ROUTING_RULES.md`, `services/chain_llm.py` `fuse`
- Extra LLM readers: `services/{flat,ext,pheno,full}_extract.py`
- B-arm vs E: `docs/E_EXTERNAL_BASELINES.md`
- Citations: `docs/REFERENCES.md` (Savova, Soysal, Uzuner, Alsentzer, Harkema)
- Closed corpora: `docs/CORPUS_OUTREACH.md`
- Default policy: EVAL D17; extra detector: D18–D20 / 10.33–10.35; role placements D21 / 10.36 (`docs/ROLE_PLACEMENTS.md`); do not flip D17
