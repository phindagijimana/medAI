# Mention → concept gold set and recall@k (Ontology arm)

Status: baseline measured. Harness: `scripts/eval_concept_retrieval.py`.
Outputs: `eval/results/concept_retrieval.{json,md}` (strict) and
`eval/results/concept_retrieval_lenient.{json,md}` (lenient).
Referenced from `docs/EVAL_PROTOCOL_LEO.md` §6 (claim C3, candidate retrieval).

> Licence note. The per-mention tables in the `.md` outputs quote SNOMED CT and RxNorm
> labels. SNOMED CT and RxNorm are UMLS-licensed; these result files must not be committed,
> pushed or redistributed (keep them under the gitignore rules in `docs/ONTOLOGY_SOURCES.md`).
> Only the aggregate numbers in this document may be shared.

## 1. What is measured

The Ontology arm (C of the Chain-of-Three) returns ranked candidate concepts for a text
mention. The claim is that the correct concept is in the top-k. This had never been measured
(limitation "search quality hasn't been measured" in `docs/ontology_resources.md`).

- **Gold.** Clinician-annotated mention→UMLS CUI pairs from the Fang–Sanders/Fonferko-Shadrach
  (F-S) epilepsy-letter corpus (Zenodo 8356494, CC-BY). 1,046 annotated mentions, 62 distinct CUIs,
  entity classes Diagnosis (569), Prescription (294), Investigations (183).
  Fields routed: `epilepsy_type`, `predominant_seizure_type`, `current_asms`.
- **Crosswalk.** CUI → codes in HPO, SNOMED CT US and RxNorm through the UMLS atoms of each CUI
  (UTS cache `.cache/umls_api/<CUI>.json`). A mention is *reachable* when its CUI has at least one
  code in those three sources: 956 of 1,046.
- **Candidates.** Real service call with field routing (the same retrieval the chain uses),
  top-10. HPO / MONDO / EPIO / SNOMED CT / RxNorm release, plus the curated seed.
- **Metrics.** Recall@1/5/10 and MRR@10 over reachable mentions.
- **Views.** `all`; `scorable` (excludes candidates from MONDO and EPIO, because a UMLS CUI
  cannot be crosswalked to them); `release-only`; `seed-only` (the curated seed alone, to test
  retrieval that does not depend on our own dictionaries).
- **Splits.** Seed entries and lexicons were derived from ExECT dictionaries, so independence is
  imperfect. Mentions are split into held-out (letters EA0161–EA0200, the F-S test letters,
  also the primary LEO test set) and train (all other letters). Roughly equal scores on the two
  indicate the result is not an artifact of development on particular letters.

### Match modes

| mode | a candidate counts as a hit when |
|---|---|
| strict (headline) | its (system, code) is a UMLS code of the gold CUI |
| lenient | strict, **or** its label equals a UMLS atom name of the gold CUI (same concept under an equivalent code, e.g. a MONDO "epilepsy" node) |

Strict undercounts: MONDO/EPIO cannot match a CUI. Lenient can overcount if a label is
shared across distinct concepts. Report both; do not pick the better one after the fact.

## 2. Results (1,046 mentions)

| group | n | R@1 strict | R@5 strict | R@10 strict | R@1 lenient | R@5 lenient |
|---|---:|---:|---:|---:|---:|---:|
| ALL | 1046 | 0.344 | 0.744 | 0.764 | 0.561 | 0.768 |
| scorable view | 1046 | 0.556 | 0.749 | 0.764 | 0.556 | 0.749 |
| Diagnosis | 569 | 0.216 | 0.715 | 0.752 | 0.626 | 0.760 |
| Prescription | 294 | 0.752 | 0.759 | 0.759 | 0.752 | 0.759 |
| Investigations | 183 | 0.064 | 0.803 | 0.803 | 0.064 | 0.803 |
| `epilepsy_type` | 308 | 0.049 | 0.850 | 0.876 | 0.824 | 0.929 |
| `predominant_seizure_type` | 260 | 0.405 | 0.565 | 0.612 | 0.405 | 0.574 |
| `current_asms` | 294 | 0.752 | 0.759 | 0.759 | 0.752 | 0.759 |
| held-out split (scorable R@1) | 201 | 0.543 | 0.753 | 0.753 | 0.543 | 0.785 |
| train split (scorable R@1) | 845 | 0.560 | 0.742 | 0.766 | 0.565 | 0.764 |

(The scorable-view row is reproduced from the strict run; in that view lenient adds nothing.)

Reading the table:

1. **The strict `epilepsy_type` R@1 of 0.049 is a measurement artifact.** The top-1 is usually
   the MONDO "epilepsy" node, which the CUI gold cannot credit. Lenient R@1 is 0.824 and the
   scorable view is 0.805. Do not quote 0.049 as retrieval quality.
2. **The real gap is R@1 → R@5.** Scorable R@1 0.556 vs R@5 0.749 (+19 points). Ranking is the
   weak point, not coverage, which is the situation an LLM selector (arm B choosing among
   arm C candidates) is meant to fix.
3. **Ceiling of about 0.76 to 0.80** at R@10 for every class: it does not rise with k. The
   residual is a coverage / mapping problem, not a ranking problem (§3).
4. **Held-out ≈ train** (scorable R@1 0.543 vs 0.560; R@5 0.753 vs 0.748), so the result is not an artifact of tuning on the
   development letters.
5. **`predominant_seizure_type` is the weakest field** (R@10 0.612).
6. **Seed-only R@10 is 0.100**, so most hits come from the released ontologies, not from the
   curated seed that was derived from ExECT.

## 3. Miss taxonomy (reachable mentions with no top-10 hit)

| class | examples | cause | fix type |
|---|---|---|---|
| Brand names | Keppra, Tegretol, Lamictal | gold CUI is the brand (RxNorm BN); candidate is the ingredient (levetiracetam, carbamazepine, lamotrigine). The ingredient is the *clinically correct* answer. | scoring convention (compare at ingredient level) and a brand→ingredient synonym table |
| Misspellings | "Kepra", "zobisamide" | no fuzzy matching | fuzzy / edit-distance lexicon, or let the LLM normalise |
| Context spans | "Current antiepileptic medication: sodium valproate 600 mg bd" | gold span includes dose and prefix words | mention trimming before retrieval (the chain's specialist already gives the drug span) |
| Equivalent code, different concept node | sodium valproate: gold RxNorm 9919 (valproic acid) vs returned 40254 (valproate) | RxNorm treats the acid and the salt as different ingredients | ingredient-level equivalence table |
| Equivalent SNOMED node | "generalised tonic clonic seizure": gold SNOMED 1217136003, returned 1217209006 | two near-synonymous SNOMED concepts | accept as a synonym group, or exclude from strict scoring |
| British spelling | "generalised" vs "generalized" | normalisation | spelling variants in the lexicon |
| Abbreviations | "JME" | gold SNOMED 6204001; candidate is MONDO juvenile myoclonic epilepsy | credited under lenient; not strict |
| Underspecified mentions | "epileptic", "focal onset", "epilepsy" mapped to a specific CUI | gold is more specific than the text supports | irreducible; report as ceiling |
| Investigations | "CT head", "MRI scan", "EEG ... no epileptiform" | no investigations ontology in the release; R@1 0.064 | out of scope for the phenotype claims; see SCOPE_DECISIONS |

None of these is evidence that a new ontology is needed. The brand/ingredient and misspelling
classes are fixable with a small lexicon; they are recorded here rather than silently patched,
so that any future change is measured against this baseline.

## 4. Caveats

- Gold CUIs come from UMLS annotation by the F-S team; annotation conventions (brand-level CUI
  for brand mentions, specific CUI for vague text) differ from what a clinician would accept as
  correct. The strict score therefore understates real retrieval quality on medication.
- 62 distinct CUIs: a narrow vocabulary. Rare syndromes and drugs outside it are untested.
- UK letters (F-S), not US notes. US-specific wording is covered only once the US annotation
  set exists (`docs/US_ANNOTATION_PLAN.md`).
- The crosswalk relies on UMLS atoms; a CUI with no HPO/SNOMED/RxNorm atom is unreachable and
  excluded (90 mentions).

## 5. Reproduction

```bash
venv-medcat/bin/python scripts/eval_concept_retrieval.py --offline --match strict
venv-medcat/bin/python scripts/eval_concept_retrieval.py --offline --match lenient
```

`--offline` uses the cached UMLS atoms (no API call, no key needed). Without it the script
reads `UMLS_APIKEY` from `.env`; the key is never printed.

## 6. Decisions this feeds

See `docs/SCOPE_DECISIONS.md`: thresholds for adding ICD-10-CM, EpSO or ORDO are stated
against these numbers. Current reading: the gap is ranking and mapping convention, not missing
source ontologies.
