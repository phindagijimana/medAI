# Chain of Three — alignment with current MedAI-EPI codebase

**Source spec:** `Chain_System/chain-of-three-compendium (1).pdf` (v1.0, 2026-09-29)
**Reframed goal (user, 2026-09-30):** *"Get a usable model we can use in an app; papers come as by-products."*

This doc is the honest mapping of what we already have vs what the Chain-of-Three spec requires, ordered by build priority for a deployable app.

## Naming

- **Chain-of-Three** — the external spec (the compendium). We keep that name only when citing it.
- **LEO** — *our* implementation of the chain: **L**LM + **E**pExtra + **O**ntology. The L means "LLM", not a specific checkpoint, so the name survives replacing Med42. The three components corroborate one another; the letter order is not a ranking (the compendium treats the LLM as interpreter, not authority). Recorded in every Claim as `versions.pipeline = "leo-v0.1"`.
- **EpExtra** — our US adaptation of ExECT (Fonferko-Shadrach et al.): ExECT-V2 rules ported onto a MedCAT concept database. Always introduce it as "derived from ExECT" in writing; Paper 1's portability claim depends on that lineage. Detector ID in Claims: `epextra`.
- **Trident** — reserved for the framework (P4.1), if we need to distinguish it from the chain: "specialists built on Trident, each running a LEO chain". Not yet used. "TRIDENT" is already taken by a pathology toolkit, so avoid it in titles.

Code keeps its existing module/class names (`services/chain_pipeline.py`, `ChainPipeline`).

## The Chain-of-Three architecture (implemented as LEO)

```
                    Prepare  →  Reason  →  Verify  →  Publish
                       │          │          │          │
                       ▼          ▼          ▼          ▼
                  section    ┌─────────┐  schema +   ACCEPT →
                  windows    │ 3 comps │  hard +      ledger
                  + hash     └─────────┘  policy     REVIEW →
                              LLM         checks     queue
                              EpExtra                REJECT →
                              Ontology               audit
```

**Three components, each earning its place (L, E, O):**
1. **LLM** (Med42-8B, `m42-health/Llama3-Med42-8B`) — contextual interpretation (assertion, experiencer, temporality, candidate picking). *Not yet called in leo-v0.1; EpExtra currently supplies every span.*
2. **EpExtra** — high-precision specialist signal (ExECT-derived rules over MedCAT)
3. **Ontology** — HPO + MONDO + EPIO + SNOMED CT + RxNorm as candidate space (turns code *generation* into code *selection*)

**Governing principle:** the LLM interprets language but does not invent ontology IDs. A deterministic retriever supplies a small candidate list; the LLM classifies or abstains.

---

## Where we stand — component by component

### 1. EpExtra specialist channel (US adaptation of ExECT)

| Spec item | Our state |
|---|---|
| Custom epilepsy CDB | ✅ `data/medcat_cdb_epilepsy/` |
| ExECT-V2 rule port | ✅ `rules/` — 24 field rules |
| Negation / temporality / experiencer | ✅ via medspaCy ConText in `rules/context_config.py` |
| MetaCAT-style ML attributes | 🔴 Trained (job 159296), evaluated, **not adopted**: replacing ConText with MetaCAT Presence costs 2.1 micro-F1 points on synth-v1 (silver labels are ConText's own output). ConText stays default; `--metacat` flag available. See `docs/METACAT_EVAL.md` |
| US idiom coverage | ✅ Phase 4 + Phase 8 + `us_note_preprocessing.py` |
| Section-aware rules | 🟡 Preprocessing canonicalises headers; rules mostly not gated on section yet |
| F-S test 40 F1 | **0.8064** — inside 0.75-0.85 target band |
| Portability parity vs original ExECT | ❌ Not documented as a comparison table |

**Verdict:** functionally complete. Missing formal ExECT → EpExtra parity table for Paper 1.

### 2. Ontology / candidate retrieval service

| Spec item | Our state |
|---|---|
| HPO as primary phenotype vocab | 🟡 Exact-match mentions now get HPO / MONDO / EPIO / RxNorm IDs; on a 5-note synth-v3 sample, 49 of 150 claims carry a standard-ontology ID, 87 still `MEDAI-ENUM` (fuzzy matches wait for LLM selection) |
| HPO release pinning | ✅ Releases pinned in `data/ontologies/MANIFEST.json` (HPO, MONDO, EPIO, SNOMED CT US, RxNorm) via `scripts/fetch_ontologies.py`; each Claim records its candidate's release (e.g. `hpo:2026-09-01`) |
| EPIO as optional enrichment | ✅ 414 native EPIO classes are a candidate source (TM_BIN bins and animal/statistical models excluded) |
| RxNorm for meds | ✅ 25 anti-seizure ingredients with brand + salt-form synonyms; medication claims get RxCUIs. Coverage limited to drugs named in `rules/fields/medication.py` |
| Candidate service: top-k retrieval + rank | ✅ `services/ontology_candidates.py` + `services/ontology_loaders.py` — lexical ranking over 2,328 subset terms + curated entries, routed by field; ~3 s load, <15 ms/query. SNOMED labels are US preferred terms; curated codes that fail `services/curated_code_audit.py` are not emitted |
| Definitions + synonyms + parents surfaced | ✅ From HPO / MONDO / EPIO / SNOMED; obsolete terms retained but down-ranked and never auto-adopted |
| Selected candidate validation | ❌ No candidate step to validate |
| Candidate recall@k metric | ❌ Not measured |

**Verdict:** this is the biggest missing piece. It is also the design's most novel claim ("generation → selection"). Building it is the highest-leverage single unlock.

### 3. Med42-8B LLM

| Spec item | Our state |
|---|---|
| Frozen model + version pinning | ✅ Med42-8B via `services/med42_backend.py` |
| Zero-shot arm | ✅ M0 already scored on F-S test 40 |
| Fixed few-shot arm | ✅ M1 already scored |
| Schema-injected prompt | ✅ M2 already scored |
| Dynamic few-shot / RAG | ❌ Not built |
| Fine-tuned arm | 🟢 v3-polish LoRA trained (job 159285, completed); F-S test 40 eval running (job 159294) |
| Constrained decoding | ✅ `services/constrained_decode.py` |
| Independent LLM detection pass | 🟡 Partial via existing `/extract` endpoint |
| Cross-model verifier (DeepSeek) | ✅ `services/deepseek_backend.py` + `evidence_verifier.py` |

**Verdict:** substantially built. Missing dynamic-retrieval few-shot and the *interaction with a candidate service*.

### 4. Pipeline orchestration (Prepare / Reason / Verify / Publish)

| Spec item | Our state |
|---|---|
| Prepare: normalise + section segment + windows + provenance | 🟡 Chunker exists (`services/chunker.py`); section detection via preprocessing; no unified "Prepare" stage |
| Reason: dual-pass (specialist + LLM) → reconcile | 🟡 We run each arm separately; no reconciliation |
| Verify: schema + hard + policy checks + reason codes | ✅ `ChainPipeline._verify` + `ReasonCode` enum |
| Publish: ACCEPT / REVIEW / REJECT + ledger | ✅ `services/ledger.py` routing |
| Append-only evidence ledger | ✅ SQLite, `data/ledger/evidence.sqlite` |
| Review queue | 🟡 API + `/extract/ui/review` built; not yet tested against a running server |
| Claim contract JSON | ✅ `schema/claim.py`; `POST /extract/chain` and `scripts/extract_chain_cli.py` emit it |

**Verdict:** the app layer (Prepare/Verify/Publish) is where most build effort goes. This is what turns extractors into a deployable tool.

### 5. Data / corpus

| Spec item | Our state |
|---|---|
| Clinician-annotated US epilepsy corpus | ❌ We have silver only (MTSamples via gpt-5.6-terra + luna + sol) |
| Patient-level splits | ✅ present for F-S and synth-v3-polish |
| Epileptologist adjudication | ❌ Not arranged |
| Frozen test set | 🟡 F-S 40 held out; needs equivalent US set |
| Annotation guideline | 🟡 v0.2.1 schema doc exists; not a formal annotation guideline |

**Verdict:** the corpus is the biggest external dependency. Papers 1 and 2 both require a real clinician-annotated US corpus. The app can ship on silver + adjudicated pilot.

---

## Build order — deployable app first

Given the user directive, priorities re-order:

### Priority 1 (P1) — App plumbing that a user can invoke end-to-end

**P1.1 — HPO retrieval service** (`services/ontology_candidates.py`)
- Load a pinned HPO release (`data/ontologies/hpo/hp-YYYY-MM-DD.obo`)
- Build a lexical + synonym index over labels + definitions
- Optional TF-IDF or sentence-BERT vector index for paraphrase
- API: `get_candidates(mention: str, section: str) -> list[Candidate]`
- Each candidate carries: `id`, `label`, `definition`, `synonyms`, `parent_ids`, `is_obsolete`, `release_hash`
- Bonus: EPIO + RxNorm indexes with the same interface

**P1.2 — Claim contract dataclass** (`schema/claim.py`)
- Match the spec's JSON exactly (see PDF page 8)
- Wrap existing Evidence[T] output into Claim objects
- Add `validator_verdict`, `reason_codes`, `detectors`, `candidate_rank`, `versions`

**P1.3 — Prepare / Reason / Verify / Publish orchestrator** (`services/chain_pipeline.py`)
- Prepare: consume a note text, section-segment, window, hash — deterministic
- Reason: run specialist (B1' MedCAT+Rules) + LLM detection, retrieve candidates, LLM classifies
- Verify: schema + hard + policy checks; emit reason codes
- Publish: verdict → ledger OR review queue

**P1.4 — Evidence ledger** (`services/ledger.py`)
- SQLite-backed append-only store
- Insert = new row; no updates
- Query APIs for research + audit + review UI

**P1.5 — Review queue + minimal UI**
- Extend the existing `/extract/ui` blueprint with a review tab
- Reviewer sees flagged claims side-by-side with note context + alternatives
- Reviewer verdict: accept-as-is / edit / reject → writes a new ledger row marked `human-adjudicated`

**P1.6 — Deployment**
- `docker-compose.yml` already exists; extend with the ledger DB + review UI
- `/extract` API returns claim JSONs in the spec format
- CLI `medai-epi extract note.txt --output claims.jsonl`

### Priority 2 (P2) — Paper 1 (ExECT portability to US notes, as EpExtra)

**P2.1 — Formal ExECT → EpExtra parity table**
- Which ExECT rules ported directly, which modified, which rebuilt
- Category F1 vs original 200-Welsh-letter figures
- Portability failure taxonomy

**P2.2 — Adjudicated US test set**
- 40-100 clinician-annotated US epilepsy notes
- Requires the epileptologist to actually annotate; blocked on outreach

### Priority 3 (P3) — Paper 2 (Framework: 9-arm ablation)

**P3.1 — Rename our arms to match the spec:**
- Our B0 rules = **Arm A**
- Our B1' MedCAT+Rules = **Arm B**
- Our M0 = **Arm C** (zero-shot)
- Our M1 = **Arm D** (fixed few-shot)
- Our M2 (schema-injected) = subsumed by **Arm F** once ontology grounding is added
- Our M4 v3 = **Arm H** (fine-tuned)
- Our M4+C = folds into F (constrained decoding is a decoder choice, not an arm)
- Our M4+CR = **Arm G** (dynamic few-shot retrieval)
- Our M4+CRV = drop OR keep as an extra `V` arm

We are missing: **Arm E** (fixed few-shot + candidate selection) and **Arm I** (full LEO chain + fine-tuned Med42).

**P3.2 — Run all 9 arms** through the LEO chain's Prepare→Reason→Verify stages on the same test set.

### Priority 4 (P4) — Paper 3 (Second specialty)

**P4.1 — Framework/plug-in split** — refactor so `specialty = "epilepsy"` is a config, not code.
**P4.2 — Second specialty pilot** — e.g. neuromuscular or headache, small annotation study.

---

## What NOT to do (yet)

- **Do not** pretend our Evidence[T] output is HPO-compliant. It is not. Bridge via a mapping table.
- **Do not** run all 9 arms before Arm E and the ontology service exist — the primary comparison is F vs H vs I, and F requires ontology grounding.
- **Do not** submit any paper before a clinician has adjudicated at least a 40-100 US-note test set.
- **Do not** claim "clinical decision support." This is a research extraction tool. Everything ships behind a research-only banner (already in the app disclaimer).

## Concrete near-term deliverables (this week + next)

Status as of 2026-10-01:

1. ~~**Build the candidate retrieval service** (P1.1)~~ — done, backed by pinned HPO / MONDO / EPIO / SNOMED / RxNorm subsets. **Next:** build a gold mention→concept set and measure recall@k; add the LLM selection step for non-exact matches.
2. ~~**Wire the Claim contract** (P1.2)~~ — done.
3. ~~**Prepare/Reason/Verify/Publish orchestrator** (P1.3)~~ — done (EpExtra + Ontology; LLM step not yet called).
4. ~~**Ledger** (P1.4)~~ — done.
5. **Score arm H** — v3-polish LoRA eval running (job 159294).
6. **Draft the ExECT → EpExtra parity table** (P2.1) — a paper-shaped doc, not just a table. ~1 day.
7. **Smoke-test review queue + CLI** (P1.5 / P1.6) end-to-end against a running server.

## Governance decisions to record

Per the spec (page 32), the following decisions should be formally noted:

- [x] Use three-component chain as starting hypothesis — **Adopted**
- [x] Use candidate selection rather than code generation — **Adopted** (P1.1 is the concrete step)
- [ ] Use 3–5 fixed few-shot examples — **Provisional** (need to build the fewshot bank)
- [ ] Keep EpExtra in final deployment — **Open** (measured after 9 arms run)
- [x] Fine-tune Med42 — **Adopted** (v3-polish LoRA, job 159285 completed)
- [x] Name the chain **LEO** (LLM + EpExtra + Ontology); reserve **Trident** for the framework — **Adopted** 2026-10-01
- [ ] Claim a reusable framework — **Conditional on second-specialty pilot**

## Success gate for "usable model in an app"

The app is deployable when:
1. A user can drop a US epilepsy note into `/extract` and get back a JSONL of Claim objects.
2. Each Claim references exact source offsets + a valid HPO ID + an assertion + experiencer + temporality.
3. Uncertain / implicit / medication-derived claims route to a review queue, not to the accepted ledger.
4. The reviewer can accept, edit, or reject in the UI; the ledger tracks the decision.
5. All output is reproducible from a run manifest recording model, ontology, and prompt versions.

**When those five are true, we can ship.** The papers write themselves from the ledger + benchmarks.

## Update log

| Date | Change |
|---|---|
| 2026-09-30 | Initial alignment written after reading Chain-of-Three compendium v1.0. Priorities re-ordered from "F1 on F-S 40" to "deployable app first." |
| 2026-10-01 | Named our implementation **LEO** and the specialist **EpExtra** (ExECT-derived). `pipeline_version` → `leo-v0.1`; detector ID `exect_us` → `epextra`. Status tables refreshed: P1.1–P1.4 built, P1.5/P1.6 built but untested, ontology releases pinned, LoRA v3-polish trained. |
| 2026-10-01 | Candidate service loads pinned ontology subsets (`services/ontology_loaders.py`, 2,302 terms). Pipeline adopts a candidate only on exact label/synonym match (`min_candidate_score = 0.9`) and records the candidate's own release; previously it adopted any top-ranked candidate and stamped the pipeline default release. |
| 2026-10-01 | Loader fixes. (1) Drugs: `rules/asm_lexicon.py` generated from RxNorm (`scripts/build_asm_lexicon.py`: ATC N03A + curated + FDA-indicated rescue/adjunct drugs filed outside N03A, 51 ingredients, 26 new incl. cenobamate, cannabidiol, fenfluramine) feeds both MedCAT detection and RxNorm coding; the medication rule now sets `rxnorm_cui`. (2) SNOMED terms use the US language refset (preferred term, US-acceptable synonyms, disorders/findings only). (3) Curated-code audit (`scripts/audit_curated_codes.py`) found ~120 bad curated codes: fabricated/mistyped SCTIDs, wrong UMLS CUIs, 14 wrong RxNorm codes. Fixed from authoritative sources: all 24 curated drug codes (RxNorm), UMLS enrichment regenerated with relatedness filters (−138 unrelated synonyms, −8 wrong SCTIDs). Remaining 79 issues frozen in `data/curated/curated_code_known_issues.json` for clinician review (worklist with suggested SCTIDs: `data/ontologies/curated_code_review.csv`); the candidate service suppresses them. ILAE-map SNOMED IDs were atom strings, now parsed. B1′ F1 unchanged on F-S 40 (0.8064) and synth-v1 (0.8192) with the rebuilt CDB (`data/medcat_cdb_epilepsy_v2/`, not yet default). |
| 2026-10-01 | Curated codes fixed. 93 corrections (69 SNOMED, 24 CUI, 8 removed) in `data/curated/curated_code_corrections.csv` with source and reason per row, applied by `scripts/apply_curated_code_corrections.py` (new SCTIDs must be active in `snomed:2026-09-01`; CUIs resolved via UTS). Includes 8 wrong codes the audit had missed (e.g. `MriFinding.tumor` → prostate neoplasm). 4 hand-checked false positives in `data/curated/curated_code_reviewed.csv`. `MedicationStatus` moved to `RULES_ONLY_ENUMS` (no SNOMED concepts exist; status is regex-derived). Audit: 79 → 0 issues. Candidate service now dedupes curated codes per group, so a code shared across groups (resection = SurgeryType and DocumentType) links to both. Rebuilt CDB is now the default `data/medcat_cdb_epilepsy/` (old archived as `…_archive_20260930/`); F1 unchanged (0.8064 / 0.8192); FBTC plurals added so "secondary generalised seizures" is not read as generalized. MetaCAT evaluated and not adopted (`docs/METACAT_EVAL.md`). Sources and citations: `docs/ONTOLOGY_SOURCES.md`. LEO smoke (5 synth-v3-polish notes): 77 accept / 68 review / 6 reject; 15 SNOMED claims, all active and tagged `snomed:2026-09-01`. Old vs new CDB on the same notes: lorazepam newly detected (review); focal cortical dysplasia now coded HPO:0032046 / SNOMED 253153000 instead of internal enum only. |
| 2026-10-01 | LEO LLM channel wired (`pipeline_version` → `leo-v0.2`): fusion of EpExtra and Med42-8B output (`services/chain_llm.py`), live / tuned-adapter / manifest-replay reasoners, `--llm-*` CLI flags, `MEDAI_LEO_LLM` env for the route. Audit findings F1–F6 and the frozen evaluation protocol are in `docs/EVAL_PROTOCOL_LEO.md`; the earlier tuned-arm F-S numbers are withdrawn (adapter was scored out of contract). First results on flat base arms (§10.1 of the protocol): LLM alone 0.68–0.70 micro-F1 vs EpExtra 0.655 on seven native-gold fields; LEO with review included is indistinguishable from either; auto-accept trades recall for precision. |
| 2026-10-01 | P2.1 parity table drafted: `docs/EXECT_EPEXTRA_PARITY.md` (ExECT original per-category column still to fill from the paper). P2.2 plan: `docs/US_ANNOTATION_PLAN.md`. Mention→concept gold set and recall@k: `docs/CONCEPT_GOLD_SET.md`. Deferred scope items with triggers: `docs/SCOPE_DECISIONS.md`. Repo hygiene and commit plan: `docs/REPO_HOUSEKEEPING.md`. |
| 2026-10-01 | LEO evaluated on US-style synthetic notes (synth-v3-polish validation + synth-v3 patients), patient level, with the fine-tuned adapter and constrained base arms. Set is saturated (llm 0.99-1.00, specialist 0.95); agreement tiers still separate (agree 0.98 vs disagree 0.03). See `docs/EVAL_PROTOCOL_LEO.md` §10.4. |
| 2026-10-01 | `pipeline_version` → `leo-v0.4`. Acute one-off drug administrations are REVIEW under `medication.acute_administration` (not `current_asms`); specialist-only drugs are REVIEW when the LLM listed other drugs but not this one; empty frequency placeholders no longer count as agreement or replace the LLM's evidence; approximate frequencies (specialist PROBABLE) are read as asserted. Four `ChainConfig` switches; results and caveats in `docs/EVAL_PROTOCOL_LEO.md` 10.6 / D11. |
| 2026-10-01 | `pipeline_version` → `leo-v0.5`. Drug role: as-needed rescue drugs go to `medication.rescue_medication` (reason `rescue_role`, switch `rescue_role_split`); scorers report current ASMs with and without rescue. Cues and sources in `docs/LEO_ROUTING_RULES.md` 3.4; results in `docs/EVAL_PROTOCOL_LEO.md` 10.7 / D12. |
