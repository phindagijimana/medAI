# Scope decisions deferred until results

Status: **open**. Nothing here is decided. Each item has a stated trigger, the evidence we
have today, and a proposal. Background and sources: `docs/ontology_resources.md` §3 to §5.
Retrieval evidence: `docs/CONCEPT_GOLD_SET.md`. Protocol: `docs/EVAL_PROTOCOL_LEO.md`.

Honesty note on pre-registration: the retrieval baseline (§2) was seen before these thresholds
were written. The thresholds below are therefore fixed *before the LEO arm results and before the
US set exist*, but they are not blind to the retrieval baseline. Do not change them after the
arm results come in; if they must change, record the change in §6.

## 1. Items and decision rule

| # | Item | Kind | Decide by | Trigger to add |
|---|---|---|---|---|
| D1 | Adopt ILAE 2025 enums (in addition to 2017) | schema change | **before the US annotation guideline is frozen**, otherwise annotators label twice | see §3.1 |
| D2 | Map each schema field to NINDS CDE names | mapping table, not a retriever source | first version written 2026-10-01 (`docs/NINDS_CDE_MAPPING.md`); several rows still to confirm | see §3.2 |
| D3 | Add ICD-10-CM | code system for output / retrieval | after the US pilot notes are read | see §3.3 |
| D4 | Add EpSO | retrieval source | after recall@k re-run | see §3.4 |
| D5 | Add Orphanet ORDO | retrieval source | after recall@k re-run | see §3.4 |
| D6 | Definition of "current ASM": do one-off acute administrations and home rescue drugs count? | scorer and pipeline setting | before the US annotation guideline is frozen | see §3.5 |

General rule for any new **retrieval source** (D3 to D5): add it only if both hold on the
mention→concept gold set (`scripts/eval_concept_retrieval.py`):

1. **Gap:** recall@10 on the affected field is below 0.85 in the lenient view, and
2. **Coverage:** in a manual check of at least 50 sampled top-10 misses for that field, at least
   30% have a correct concept that exists in the candidate source and not in the current sources.

A source that fixes only ranking (the concept is already in the release) is not added; the
fix there is ranking, synonyms or the LLM selector.

## 2. What the data says today

From `docs/CONCEPT_GOLD_SET.md` (1,046 F-S mentions):

- Scorable R@1 0.556, R@5 0.749, R@10 0.764. The R@1 to R@5 gap is 19 points; R@5 to R@10 is 1.5.
  So the loss is mostly ranking, plus a ceiling near 0.76 that does not move with k.
- The ceiling is dominated by brand names, misspellings, long context spans and
  equivalent-but-different codes (valproate, SNOMED generalised-tonic-clonic nodes), not by
  concepts missing from every source. All scored mentions are reachable by construction, so the
  gold concept exists in HPO, SNOMED CT or RxNorm.
- `predominant_seizure_type` is the one weak field (R@10 0.612 < 0.85, so trigger 1 is met).
  Trigger 2 is not shown yet: the sampled misses are 'focal onset', 'epileptic' and
  British-spelling variants of concepts that are already in SNOMED CT and HPO.
- The F-S gold is UK, UMLS-annotated, and has no ICD or Orphanet codes, so it cannot measure
  D3 or D5 at all.

## 3. Item notes

### 3.1 D1: ILAE 2025 enums

- Proposal: keep 2017 as the stored value, add a one-way **2017 → 2025 view** in the output
  layer instead of changing the stored enum. Real letters use 2017 and older words ("complex
  partial"), so the extraction vocabulary cannot drop them.
- Trigger: adopt as stored values only if (a) the US annotators or the epileptologist say the
  target users expect 2025 terms, and (b) the 2017→2025 mapping is lossless for at least 90% of
  our `SeizureType` values (many-to-one merges lose information; count them).
- Cost: schema version bump, rescoring every arm. Do not do it after arm results are frozen.
- Citation to verify before use: the ILAE 2025 seizure classification update [C3] in
  `docs/ONTOLOGY_SOURCES.md`.

### 3.2 D2: NINDS CDE mapping

- A table: schema field → CDE element name and permitted values, with "no equivalent" rows.
  It is documentation and an export format; it touches neither the retriever nor the model.
- Proposal: do it, because the cost is low and it is the only item that makes the output
  comparable with other epilepsy research networks. Counts as a *need* even without a recall gap.
  It is independent of results; the only reason to wait is that the schema may change under D1.
- Source [N1] in `docs/ONTOLOGY_SOURCES.md`. Each CDE row's definition must be paraphrased, not
  copied, and the access date recorded.
- Status (2026-10-01): first version in `docs/NINDS_CDE_MAPPING.md`. Seizure-type and medication rows
  are backed by element lists read from the NINDS form and a 2016 mirror; seizure frequency and
  age at onset had no NINDS element found; several rows are partial. Confirm against the live site
  before promising an export.

### 3.3 D3: ICD-10-CM

- Why it might be needed rather than nice: US notes and problem lists contain ICD-10-CM codes
  (G40.x), and cohort definitions in US health systems use them. Two uses are different:
  (i) **reading** a code written in a note (near-exact string match, no ontology search), and
  (ii) **emitting** a code for a diagnosis claim (a mapping from SNOMED CT/HPO concept).
- Evidence today: none. F-S is UK. This item cannot be settled from existing results.
- Trigger: the US pilot notes (first 10 of `docs/US_ANNOTATION_PLAN.md`) show ICD-10-CM codes in at
  least 20% of notes, or the deployment requirement lists billing-code output.
- Licensing: the CMS/NCHS release is a public download (confirm the exact terms on the
  release page when it is fetched; record in `data/ontologies/MANIFEST.json`).
- Proposal if triggered: load as a *lookup/crosswalk* for G40.x and R56.x only, not as a
  general retrieval source.

### 3.4 D4/D5: EpSO and ORDO

- EpSO: closest in content to our seizure and EEG vocabulary, but we already take ILAE terms from
  EPIO, SNOMED CT and HPO. Licence terms on BioPortal must be checked before download.
  Trigger per §1 only; the current seizure-type misses do not require it.
- ORDO: rare syndromes and gene links. Much reaches us via MONDO already. Relevant only if the
  scope extends to rare-syndrome/genotype phenotyping. CC BY 4.0 per the Orphadata page [E2].
- Proposal: do not add either now. Re-run recall@k after the cheap fixes in §4 and apply the
  §1 rule.

### 3.5 D6: what counts as a current ASM

The two gold sets disagree. The F-S gold counts every non-negated prescription, rescue forms
included, as current. The synthetic gold lists maintenance ASMs only and leaves out acute or rescue
doses (audit, `EVAL_PROTOCOL_LEO.md` 10.5: 9 of 11 wrong specialist-only drug claims were acute or
rescue doses). `leo-v0.4` handles the clear case, a one-off dose given during the encounter, by moving
it to `medication.acute_administration` for review (`docs/LEO_ROUTING_RULES.md` 3.1). Home rescue
(buccal or intranasal PRN) is still counted as current, as in the F-S gold. The acute rule found 0
cases in the 40 held-out F-S letters.

Literature (2026-10-01; web search summaries, primary documents not all opened; list in `REFERENCES.md`): NINDS Epilepsy CDEs separate the antiepileptic-drug log from other medications and ask for ongoing status per drug; the NINDS trial-criteria workshop says intermittent rescue benzodiazepines should be documented but not used to exclude participants; the ILAE and the Epilepsy Foundation describe rescue treatment as as-needed and not a replacement for daily medication; a 2024 expert consensus (Pina-Garza et al.) proposes replacing "rescue" with "REST medication" and "acute cluster treatment". The ExECT guideline annotates "current prescribed ASMs" with dose, unit and frequency, with no separate rescue category found in the sources read. So the literature supports recording rescue separately from maintenance, and none of it makes one-off acute doses part of the regimen; it does not settle whether a research "current ASM" list should include rescue.

ExECT in detail (local guideline notes `EXECT_V2_ANNOTATION_GUIDELINES_NOTES.md` section 8 and the V2 rule files): it annotates only *current* prescriptions. Rescue drugs are not a separate entity; they are prescriptions whose Frequency is "As Required" (also the default for clobazam). A dose is required for annotation, except for rescue drugs such as midazolam or diazepam. The rule files have an IV-route word list, but `routes.jape` is marked "no longer in pipeline", so the route is not used to include or exclude anything. ExECT has no rule for one-off administered doses: its input is outpatient clinic letters, where they are rare. So the F-S gold, built to that guideline, counts rescue as current, and acute-dose handling is a gap that US ED/EMU notes expose.

Open: the annotation guideline for US notes must say which convention applies and whether rescue is a
separate field. Until then both conventions are reported (current ASMs with and without rescue). Built in `leo-v0.5`: rescue drugs have their own field path (`medication.rescue_medication`) and both scorers take a switch (`docs/LEO_ROUTING_RULES.md` 3.4 and 8). Results: synthetic gold favours the maintenance-only view (specialist precision 0.968 vs 0.884 with rescue counted), the F-S gold counts rescue, as ExECT does; the rescue rule moved 1 of the F-S gold drugs. Recommended headline for US research output: maintenance only, with rescue reported alongside. A clinician must confirm.

**Decision (2026-10-02), subject to clinician confirmation.** Keep both fields and never merge them: `current_asms` is the maintenance regimen (the headline) and `medication.rescue_medication` is a separate field shown beside it. The F-S scorer keeps counting rescue as current because its gold follows ExECT, where rescue is a prescription with "As Required" frequency; the synthetic scorer does not, because its gold lists maintenance drugs only. Both views are reported (`--rescue-as-current`), so the two gold sets are no longer in conflict, they answer two stated questions. The reasons: ExECT annotates rescue as current but has no separate category, so a separate field loses nothing it records; the literature (NINDS, ILAE, Epilepsy Foundation, Pina-Garza 2024) separates rescue from daily medication; and no source says a research "current ASM" list must include it. What a clinician still has to decide is whether a rescue-only drug (a patient with no daily ASM) should count as "on an ASM" for a given study; LEO does not decide that.

## 4. Cheap fixes to try first (not new sources)

These address the actual miss classes and do not add dependencies:

1. Brand→ingredient synonyms for the ASM lexicon (Keppra, Tegretol, Lamictal, Depakote, ...).
2. British/American spelling variants in the candidate service.
3. Fuzzy match for misspelt drug names ("Kepra", "zobisamide"), with a hard distance cap.
4. Ingredient-level equivalence in the retrieval scorer (so valproate/valproic acid match).
5. Trim context spans (dose, prefix words) before retrieval.

Each is measured against the baseline in `docs/CONCEPT_GOLD_SET.md`, with the change recorded.

## 5. Ordering

D1 first (blocks US annotation), D2 any time after D1, D3 after the US pilot, D4/D5 after the
§4 fixes and one re-run of the retrieval eval.

## 6. Change log

| date | change |
|---|---|
| 2026-10-01 | Document created. All items open. |
| 2026-10-01 | Added D6 (definition of current ASM; acute vs rescue) after the leo-v0.4 error diagnostic. |
| 2026-10-01 | D6: rescue role and two scoring views built (leo-v0.5); headline view still to be confirmed by a clinician. |
| 2026-10-02 | Deferred beyond the MVP by the project lead: reviewers adding missed values, learning from review decisions, real clinical notes (IRB and secure compute). See `DEFERRED_BEYOND_MVP.md`. |
