# External systems vs E (EpExtra)

**Status (2026-10-07):** B-arm scoring vs E has not been run. Do not dump these into E as extra strings. If scored later, they are **B-arm comparators**, not synonym lists.

Opt-in fusion sidecar (not a B-arm): `--ext-detector` names in `docs/FIELD_SPECIALIST_DETECTORS.md` (including guideline stated-only detectors, §9). Default LEO (flag off) is unchanged. A B-arm is scored against E; a sidecar is a named detector next to E and L that cannot auto-accept or demote an E+L accept.

E is arm B1′: MedCAT + ExECT-style rules filling the phenotype table. A system is a rival of E only when it is scored on the **same notes, same gold, same fields**. LEO’s primary contrast remains E vs L vs fusion (`docs/EVAL_PROTOCOL_LEO.md` §4). Published ExECT figures are the closest epilepsy-letter cousin and are UK, not US.

## Fair test

- Same corpus (v4_ext, F-S, or IRB US notes). Never MIMIC.
- Same gold and field definitions.
- Report only columns the external system can emit. Winning “is this a drug mention?” is not winning ILAE seizure type, DRE, or EEG study type.
- One new B-arm at a time. Do not treat the list below as a full E replacement panel.

## Can compare to E (overlapping fields only)

| System | What to score against E | What not to claim |
|---|---|---|
| **cTAKES** (Savova 2010) | Drugs, problems, negation on *our* notes | Full phenotype table |
| **CLAMP** (Soysal 2018) | Same as cTAKES (check license before install) | Full phenotype table |
| **MetaMap** (Aronson 2010) | UMLS concept hits — closer to MedCAT / O than to E’s rules | The table E fills |
| **i2b2 / n2c2 medication or ADE systems** (Uzuner 2010 and later tracks) | Current / discontinued / dose-style meds | Epilepsy phenotypes; do not use challenge notes as our gold |
| **Published US EEG-report NLP** (Mayo and similar) | EEG findings on EEG text, if a runnable artifact exists | Clinic-note extraction as a whole |
| **CRF / BERT NER / rules+LM** | Whatever that system is trained to fill | Drop-in E: that is a new extractor architecture, then an ablation vs B1′ |

If only one US clinical-NLP baseline is added, score **cTAKES (or CLAMP) on medications + negation** on the same notes and gold as E.

Existing arms that already occupy this slot: B0 regex, B1 BioClinicalBERT scaffold, B1′ = E, then L / GPT / DeepSeek (`docs/medai_target.md`, `docs/EVAL_PROTOCOL_LEO.md`).

## Not models to compare to E

| Resource | Why it is not a rival extractor |
|---|---|
| **Second ConText** | Component inside E. Ablate implementations (`--context-engine sentence\|negex`, default medspaCy; `docs/METACAT_EVAL.md`); do not score it as a phenotype system. |
| **SCORE, EpSO, Orphanet, ICD-10-CM, NINDS CDEs** | Vocabularies / forms. Coding systems for O (or mapping tables), not extractors vs E. Still not loaded as E ontologies. Opt-in post-extract maps: `--export-codes` (`docs/ROLE_PLACEMENTS.md`). |
| **MIMIC notes** | Out. Do not read, display, or score them. A MIMIC-*trained* model run only on *our* notes is a separate license question; it still does not authorize MIMIC as a corpus. |

## Must not go into E as strings

The leftover US cues already in E (ACNS, RxNorm/FDA brands, i2b2/ConText med status, Fisher/Berg aliases, ExECT EEG skip) are documented in `docs/REFERENCES.md`. i2b2/n2c2, cTAKES, CLAMP, MetaMap, SCORE-as-ontology, EpSO, Orphanet, ICD as a retriever, NINDS CDEs as extract fields, a second ConText, and EEG-report *models* stay out of the E gazetteer.

## Rematch note (2026-10-07)

Leftover E strings were rematched on v4_ext (`EVAL_PROTOCOL_LEO.md` §10.30). Headline F1 did not move. Follow-up rematch after LPD sentence-negation and EEG-acronym-not-a-drug: §10.31 (`v4ext_rules_fix` / `v4ext_llm_fix`). CPU: LPD gone from IED cells; spurious IED 4→2; IED side 11/1→12/0. GPU LTM-as-drug still running (job 173225). Optional `--disagree-llm ied-silent` is documented in §10.30 and is not the default.

## If a comparator is run

Record the arm id, notes, gold, field subset, and result file in `docs/EVAL_PROTOCOL_LEO.md` in the same session. Citations: `docs/REFERENCES.md`.
