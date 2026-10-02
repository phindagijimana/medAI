# LEO routing rules (pipeline `leo-v0.5`)

Authoritative description of how a claim becomes ACCEPT, REVIEW or REJECT in LEO (LLM + EpExtra +
Ontology candidates, Chain-of-Three Prepare → Reason → Verify → Publish). Code is the source of truth:
`services/chain_pipeline.py` (`ChainConfig`, `extract`, `_verify`), `services/chain_llm.py` (`fuse`,
`_freq_agree`, `ground_value`), `services/med_context.py` (acute rule), `schema/claim.py` (`ReasonCode`).
Evidence for each rule is in `docs/EVAL_PROTOCOL_LEO.md` (sections 10.3 to 10.6, deviations D5 to D11).

Terms. **Specialist** = EpExtra (ExECT-derived rules on MedCAT). **LLM** = Med42-8B
(`m42-health/Llama3-Med42-8B`), arms L0C/L1C/L2C (constrained decoding) or H (LoRA adapter).
**Detectors** on a claim = which of `epextra`, `llm` produced it.

## 1. Fusion (per field, before verification)

| situation | result | verdict (after section 2) |
|---|---|---|
| both detectors give the same value | one claim, detectors `[epextra, llm]`, the specialist's evidence span | ACCEPT `accept_specialist_llm_agree` |
| scalar field, different values | claim with the specialist value (or the LLM value if `disagree_primary` names the field), the other value in `alternative` | REVIEW `source_disagreement` |
| only the specialist has it | specialist claim unchanged | ACCEPT `accept_unanimous`, except the drug rule in 3.2 |
| only the LLM has it | the LLM value is located in the note (`ground_value`) | REVIEW `llm_only` if a span is found, REJECT `offsets_unresolved` if not |

Scalar fields: `epilepsy_type`, `predominant_seizure_type`, `age_at_onset_years`, seizure frequency.
List field: `current_asms` (one claim per drug; names compared after brand/salt canonicalisation).

`disagree_primary` (shipped default: none, so the specialist value is shown for every field and the model's value is the claim's `alternative`). A candidate policy, `--disagree-llm candidate` (seizure type → model), helped on synthetic sets (`ext`: seizure type 0.80 → 1.00 but epilepsy type 0.975 → 0.938 if the model were shown there; tied on `v1v2`) but is not validated on real notes, so it is not the default (EVAL_PROTOCOL_LEO D15, D17, 10.13). The policy only picks which value is shown; every disagreement is still REVIEW `source_disagreement`. To collect and score the cases that would decide it per field: `docs/DISAGREEMENT_ADJUDICATION.md`.

### Frequency agreement
Two frequencies agree only if every field both sides state (count_min, count_max, period) matches
**and at least one field is stated by both**. An empty value agrees with nothing. "Seizure-free" with
no counts is read as count 0. Empty values (no counts, no period, not seizure-free) are dropped before
fusion (`drop_empty_frequency`), so a specialist placeholder cannot "agree" with a real LLM value or
replace the LLM's evidence span.

## 2. Verification order (`_verify`)

The first matching rule decides. Hard checks reject; policy checks send to a person.

1. `offsets_unresolved` → REJECT (no span in the note).
2. missing concept id/label → REJECT `invalid_code`.
3. span hash differs from the span text → REJECT `quote_mismatch`.
4. `acute_administration` → REVIEW.
5. `specialist_only_unconfirmed` → REVIEW.
6. `source_disagreement` → REVIEW.
7. LLM is the only detector → REVIEW `llm_only`.
8. assertion uncertain → REVIEW `uncertain_assertion`; hypothetical → `hypothetical_assertion`.
9. family experiencer → REVIEW `family_experiencer`.
10. specialist-only claim linked only to the internal enum code system → REVIEW `specificity_unsupported`.
11. otherwise ACCEPT (`accept_specialist_llm_agree` if the LLM is a detector, else `accept_unanimous`).

A claim is never auto-accepted on the LLM alone. A reviewer can overturn any verdict; the ledger keeps
the original.

## 3. Rules added in leo-v0.4

Each has a `ChainConfig` switch (default on). Motivation, numbers and caveats: `EVAL_PROTOCOL_LEO.md` 10.5, 10.6, D11.

### 3.1 Acute administrations (`acute_administration_filter`)
Emergency, EMU and inpatient notes record drugs *given* ("lorazepam 4 mg IV administered at 18:51",
"levetiracetam IV load"). These are events, not the regimen. A drug mention is acute when, in its own
sentence or line and within 80 characters of the mention, one of these holds:

| rule name | cue |
|---|---|
| `load_or_bolus` | load, loading dose, loaded, bolus, stat dose |
| `parenteral_unscheduled` | IV, IM, IO or spelled-out route, and no schedule word (q8h, BID, TID, daily, nightly, maintenance, scheduled ...) |
| `administered_at_time` | administered, given, gave, received, was started, together with a clock time ("at 18:51", "1851 hrs") |

Effect: reason `acute_administration`, field path `medication.acute_administration` (not
`current_asms`), REVIEW. Scorers ignore this path; the reviewer sees the claim.
Deliberately **not** matched: home rescue medication (buccal or intranasal PRN) and scheduled inpatient
IV therapy, which stay current. The rule is narrow because a false match removes a true current drug from
the auto-accepted list. It is plain text pattern matching with no model.

Scope setting to be decided: the F-S gold counts every non-negated prescription, including rescue, as
current; the synthetic gold does not. See `SCOPE_DECISIONS.md` item D6 (scope list; unrelated to deviation D6 of the evaluation protocol).

### 3.2 Specialist-only drugs (`specialist_only_drug_review`)
A drug only the specialist found goes to REVIEW (`specialist_only_unconfirmed`) when the LLM listed at
least one current drug but not this one. If the LLM listed no drugs, its silence is not evidence and the
specialist claim keeps its verdict. Reason: specialist-only precision on F-S letters is 0.25 to 0.31.

### 3.3 Approximate frequencies (`approx_frequency_is_asserted`)
The specialist labels a frequency PROBABLE only when the text says "about / approximately / around /
roughly / ~ N" (`rules/fields/seizure_frequency.py`). That is an imprecise quantity, not an uncertain
assertion, so it is read as asserted. Hedged frequencies ("possibly", hypothetical) keep POSSIBLE and
go to review. A reviewer still sees the word "approximately" in the evidence span.

### 3.4 Drug role: rescue (`rescue_role_split`, leo-v0.5)
Each current-ASM mention gets a role: `maintenance`, `rescue` or `acute` (`services/med_context.drug_role`).
Rescue drugs are as-needed seizure-emergency or acute-cluster drugs. They keep the claim but move to
`medication.rescue_medication` with the informational reason `rescue_role`; the verdict follows the normal
checks (a rescue drug both sources agree on is ACCEPT). The scorers count that path as current ASM or not
by a switch (section 8).

A mention is rescue when a cue belongs to this drug (read after the mention up to the next drug name, and
in at most 30 characters before it that hold no other drug name and no comma or semicolon; a brand and its
generic in parentheses count as one drug):

| rule name | cue |
|---|---|
| `rescue_word` | rescue, abortive, seizure action plan, emergency medication, acute cluster/repetitive ..., seizure cluster(s), for cluster(s) |
| `if_seizure` | "if / for / during / when (a) seizure", "seizure lasting / longer than" (after the drug only) |
| `prn` | PRN, as needed, as required, when needed, if needed (not after titrate, increase, adjust, wean, taper, reduce) |
| `rescue_route_or_product` | intranasal, nasal, buccal, rectal, Diastat, Valtoco, Nayzilam, Buccolam, Epistatus, and no schedule word after the drug |

Order: load/bolus and time-stamped administration are `acute` even if the drug is also ordered as needed;
then rescue cues; then an unscheduled parenteral dose is `acute`. So "lorazepam 2 mg IV PRN seizure lasting
more than 5 minutes" is rescue (a standing order), "levetiracetam 1000 mg IV load PRN" is acute.
Grounding: ExECT keeps rescue drugs as prescriptions with frequency "As Required"; NINDS, the Epilepsy
Foundation and the 2024 expert consensus separate rescue from daily medication (`REFERENCES.md`).
The ExECT default that makes clobazam "As Required" when no frequency is stated is not copied.

## 4. Reason codes

| code | verdict | meaning |
|---|---|---|
| `schema_invalid`, `offsets_unresolved`, `quote_mismatch`, `invalid_code`, `label_code_mismatch`, `obsolete_code` | REJECT | structure, evidence span or code check failed |
| `uncertain_assertion`, `hypothetical_assertion`, `family_experiencer` | REVIEW | assertion or experiencer needs a person |
| `specificity_unsupported`, `medication_derived`, `low_confidence`, `multi_candidate_tie` | REVIEW | weak code source or ambiguous concept |
| `source_disagreement` | REVIEW | specialist and LLM chose different scalar values |
| `llm_only` | REVIEW | only the LLM proposed it |
| `specialist_only_unconfirmed` | REVIEW | drug only the specialist found, LLM listed other drugs |
| `acute_administration` | REVIEW | one-off dose, not the regimen |
| `rescue_role` | (any) | informational: as-needed rescue drug, claim sits at `medication.rescue_medication` |
| `accept_unanimous`, `accept_specialist_llm_agree` | ACCEPT | passed all checks |

## 5. Run statistics
`ExtractionStats` counts: `n_llm_agree`, `n_llm_disagree`, `n_specialist_only`, `n_llm_only`,
`n_llm_unsupported`, `n_empty_frequency_dropped`, `n_specialist_only_unconfirmed`, `n_acute_rerouted`, `n_rescue_routed`.
The F-S scorer writes the last three to its JSON (`sources.<arm>.safety.counts`).

## 6. Known limits
- The acute rule and the PROBABLE-means-approximate reading were designed after looking at the test
  notes they are scored on; confirm on an unused set before reporting them as validated.
- Claim precision on longitudinal synthetic notes is understated: the gold is the patient's final
  frequency, an earlier note can state another one.
- The specialist's placeholder fields (`drug_resistance_status = undefined`, `concordance = not_assessed`)
  still appear and are rejected as `offsets_unresolved` (audit finding F1).
- EpExtra was developed on the synthetic corpora, which favours the specialist there.
- Published ExECT figures for context (Fonferko-Shadrach et al. 2019, real Welsh letters): F1 about 0.86
  overall, seizure frequency about 0.66. Sources in `REFERENCES.md`.

## 7. Tests
`tests/test_leo_rescue.py` (role rules, own-drug cue, brand/generic pairs, path, switch, acute over rescue), `tests/test_leo_v04.py` (acute cases incl. home rescue and scheduled IV, empty/approximate frequency,
specialist-only on/off, switches), `tests/test_chain_llm.py` (fusion). Full suite: 275 passed;
`scripts/smoke_chain_http.py`: all checks passed after the v0.4 changes.

## 8. Scoring views for "current ASM"
Both scorers take a switch and record the view in their JSON (`rescue_as_current`) and Markdown header.

| scorer | default view | flag to flip |
|---|---|---|
| `scripts/score_leo_vs_fs_gold.py` (F-S gold, ExECT guideline counts rescue) | maintenance + rescue | `--maintenance-only` |
| `scripts/score_leo_vs_synth_gold.py` (synthetic gold, maintenance regimen) | maintenance only | `--rescue-as-current` |

Acute administrations never count. The `llm` system (Med42 alone, no routing) lists every drug it names in
`current_asms`, so it is scored as it is; it has no role split. Each F-S run lists the drugs moved by a role
rule with the gold's verdict (`routed_drugs` in the JSON).

## 9. Table layer: no second reader (added with the LEO app)

Routing above is unchanged. When no LLM contributed to a note (rules-only mode, or a model call failed for that note), `services/leo_tabular.py` reports every value as `needs_review` with the reason `no_second_reader`, and the claims table shows `review` instead of `accept`. Reason: claims made by the specialist alone were right 25% of the time on the F-S held-out letters and 86% on the synthetic US-style notes (`docs/EVAL_PROTOCOL_LEO.md` 10.9), so "accepted" would overstate what was checked. `--accepted-only` therefore returns an empty table in that mode.
