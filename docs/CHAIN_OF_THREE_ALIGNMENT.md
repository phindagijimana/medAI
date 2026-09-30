# Chain of Three — alignment with current MedAI-EPI codebase

**Source spec:** `Chain_System/chain-of-three-compendium (1).pdf` (v1.0, 2026-09-29)
**Reframed goal (user, 2026-09-30):** *"Get a usable model we can use in an app; papers come as by-products."*

This doc is the honest mapping of what we already have vs what the Chain-of-Three spec requires, ordered by build priority for a deployable app.

## The Chain-of-Three architecture

```
                    Prepare  →  Reason  →  Verify  →  Publish
                       │          │          │          │
                       ▼          ▼          ▼          ▼
                  section    ┌─────────┐  schema +   ACCEPT →
                  windows    │ 3 comps │  hard +      ledger
                  + hash     └─────────┘  policy     REVIEW →
                              ExECT-US    checks     queue
                              Ontology               REJECT →
                              LLM                    audit
```

**Three components, each earning its place:**
1. **ExECT-US** — high-precision specialist signal (rules over MedCAT)
2. **Ontology** — HPO + EPIO + RxNorm as candidate space (turns code *generation* into code *selection*)
3. **Med42-class LLM** — contextual interpretation (assertion, experiencer, temporality, candidate picking)

**Governing principle:** the LLM interprets language but does not invent ontology IDs. A deterministic retriever supplies a small candidate list; the LLM classifies or abstains.

---

## Where we stand — component by component

### 1. ExECT-US specialist channel

| Spec item | Our state |
|---|---|
| Custom epilepsy CDB | ✅ `data/medcat_cdb_epilepsy/` |
| ExECT-V2 rule port | ✅ `rules/` — 24 field rules |
| Negation / temporality / experiencer | ✅ via medspaCy ConText in `rules/context_config.py` |
| MetaCAT-style ML attributes | 🟡 Training tooling committed; job 159286 queued |
| US idiom coverage | ✅ Phase 4 + Phase 8 + `us_note_preprocessing.py` |
| Section-aware rules | 🟡 Preprocessing canonicalises headers; rules mostly not gated on section yet |
| F-S test 40 F1 | **0.8064** — inside 0.75-0.85 target band |
| Portability parity vs original ExECT | ❌ Not documented as a comparison table |

**Verdict:** functionally complete. Missing formal parity table for the ExECT-US paper.

### 2. Ontology / candidate retrieval service

| Spec item | Our state |
|---|---|
| HPO as primary phenotype vocab | ❌ We output v0.2.1 Evidence[T] enums, not HPO IDs |
| HPO release pinning | ❌ Not present |
| EPIO as optional enrichment | ❌ Referenced in ontology work but not wired |
| RxNorm for meds | 🟡 `rules/fields/medication.py` canonicalises names but doesn't emit RxNorm IDs |
| Candidate service: top-k retrieval + rank | ❌ Not built |
| Definitions + synonyms + parents surfaced | ❌ Not built |
| Selected candidate validation | ❌ No candidate step to validate |
| Candidate recall@k metric | ❌ Not measured |

**Verdict:** this is the biggest missing piece. It is also the design's most novel claim ("generation → selection"). Building it is the highest-leverage single unlock.

### 3. Med42-class LLM

| Spec item | Our state |
|---|---|
| Frozen model + version pinning | ✅ Med42-8B via `services/med42_backend.py` |
| Zero-shot arm | ✅ M0 already scored on F-S test 40 |
| Fixed few-shot arm | ✅ M1 already scored |
| Schema-injected prompt | ✅ M2 already scored |
| Dynamic few-shot / RAG | ❌ Not built |
| Fine-tuned arm | 🟢 **M4 v3 LoRA running now (job 159285)** |
| Constrained decoding | ✅ `services/constrained_decode.py` |
| Independent LLM detection pass | 🟡 Partial via existing `/extract` endpoint |
| Cross-model verifier (DeepSeek) | ✅ `services/deepseek_backend.py` + `evidence_verifier.py` |

**Verdict:** substantially built. Missing dynamic-retrieval few-shot and the *interaction with a candidate service*.

### 4. Pipeline orchestration (Prepare / Reason / Verify / Publish)

| Spec item | Our state |
|---|---|
| Prepare: normalise + section segment + windows + provenance | 🟡 Chunker exists (`services/chunker.py`); section detection via preprocessing; no unified "Prepare" stage |
| Reason: dual-pass (specialist + LLM) → reconcile | 🟡 We run each arm separately; no reconciliation |
| Verify: schema + hard + policy checks + reason codes | 🟡 Pydantic validation exists; no policy layer or reason-code enum |
| Publish: ACCEPT / REVIEW / REJECT + ledger | ❌ No routing decision, no ledger |
| Append-only evidence ledger | ❌ Not built |
| Review queue | ❌ Not built |
| Claim contract JSON | 🟡 Our `Evidence[T]` wrapper covers ~80 % of the fields |

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

### Priority 2 (P2) — Paper 1 (ExECT-US portability)

**P2.1 — Formal ExECT-US parity table**
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

We are missing: **Arm E** (fixed few-shot + candidate selection) and **Arm I** (full chain + fine-tuned Med42).

**P3.2 — Run all 9 arms** through the Prepare→Reason→Verify pipeline on the same test set.

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

While the M4 v3 LoRA (job 159285) and MetaCAT training (job 159286) run, in wall-clock order:

1. **Build the HPO retrieval service** (P1.1). ~1-2 days engineering. Highest single-item leverage.
2. **Wire the Claim contract** (P1.2). ~½ day.
3. **Sketch the Prepare/Reason/Verify/Publish orchestrator** (P1.3) — start with a skeleton that stitches existing components. ~1 day.
4. **Ledger** (P1.4) — SQLite, minimal. ~½ day.
5. **Score M4 v3 when it lands** — arm H numbers.
6. **Draft the ExECT-US parity table** (P2.1) — a paper-shaped doc, not just a table. ~1 day.

None of this is blocked. The MetaCAT + LoRA training will keep running in the background.

## Governance decisions to record

Per the spec (page 32), the following decisions should be formally noted:

- [x] Use three-component chain as starting hypothesis — **Adopted**
- [x] Use candidate selection rather than code generation — **Adopted** (P1.1 is the concrete step)
- [ ] Use 3–5 fixed few-shot examples — **Provisional** (need to build the fewshot bank)
- [ ] Keep ExECT-US in final deployment — **Open** (measured after 9 arms run)
- [x] Fine-tune Med42 — **Adopted** (job 159285 running)
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
