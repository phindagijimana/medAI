# synth-v3 Master Plan — US-Realistic Epilepsy Clinical Notes

**Status:** design phase, pending user green-light for execution
**Owner:** MedAI-EPI team
**Goal:** Generate a robust synthetic US epilepsy clinical notes corpus that clinician reviewers cannot reliably distinguish from real US EHR notes, while remaining fully controlled (schema-conformant gold + reproducible + safe).

## 1. Vision — what "close to real" actually means

Real US epilepsy clinical documentation has FIVE dimensions our synth-v1/v2 partly capture and partly miss:

| Dimension | What real notes have | Where synth-v3 must excel |
|---|---|---|
| **Structural fidelity** | US EHR section conventions, letter formats for consults, encounter-type-specific templates | 12 distinct templates anchored on real exemplars |
| **Content richness** | Full phenotype narrative with clinical reasoning, temporal progression, multi-provider hand-offs | Longitudinal patient timelines (5-10 notes per patient across a care journey) |
| **Style realism** | Formal register + physician shorthand + copy-forward artifacts + template placeholders | Realistic prose with intentional imperfections |
| **Quirks + noise** | Typos, incomplete sentences, redundant PMH copies, EMR-inserted placeholders, insurance/billing text | Deliberate injection of authentic imperfections |
| **Longitudinal coherence** | Same patient across multiple encounters with consistent phenotype but changing clinical status | Encounter timeline generator with progression logic |

The synth-v3 pipeline addresses all five dimensions simultaneously.

## 2. Design principles

1. **Real-note anchoring, not free-form generation.** Every prompt uses ≥1 real de-identified US EHR note as a structural exemplar.
2. **Auto-annotated by construction.** Semantic plan drives BOTH note content and v0.2.1 gold — no manual annotation.
3. **Multi-template diversity.** 12 distinct US epilepsy note types cover the care spectrum.
4. **Longitudinal patient trajectories.** Notes are grouped into realistic care journeys (5-10 encounters per patient).
5. **Deliberate imperfection injection.** Copy-forward artifacts, template placeholders, physician shorthand, occasional typos — all authentic to real EHRs.
6. **Statistical validation.** Real vs synth profile comparison via published metrics.
7. **Human blind evaluation.** Clinician reviewer distinguishability test as final acceptance gate.
8. **Full traceability.** Every note's manifest records: template, encounter timeline position, generator model, semantic plan reference.
9. **Legal safety.** All exemplars are user-provided deidentified notes, gitignored locally, never redistributed. Attribution to source institution required in paper.

## 3. Template inventory (12 US epilepsy note types)

| ID | Template | Anchor source | Length target | Role in care journey |
|---|---|---|---|---|
| A | Neurology/Neurosurgery new patient consult letter | User's Note 1 (UR Neurosurgery) | 1500-2000 w | Initial encounter |
| B | Neurology telephone/video follow-up | User's Note 2 (UR Neurology tele-FUV) | 800-1200 w | Interim contact |
| C | Neurology in-person routine follow-up | Structural skeleton (hybrid of A + B) | 600-1000 w | Regular follow-up |
| D | EMU admission summary (long-term monitoring) | Standard EMU report format | 1500-2500 w | Presurgical workup |
| E | ED note (first seizure workup) | Standard US ED note format | 400-800 w | Acute presentation |
| F | PRC (Patient Review Conference) summary | Multi-disciplinary review format | 800-1200 w | Surgical decision |
| G | MRI report (brain epilepsy protocol) | Radiology report structure | 200-500 w | Imaging workup |
| H | EEG report (routine or long-term) | Neurophysiology report structure | 300-700 w | EEG workup |
| I | Neuropsychology evaluation summary | Cognitive assessment format | 1000-1500 w | Presurgical baseline |
| J | Post-operative discharge summary | Discharge summary format | 1200-1800 w | Post-surgery |
| K | Nurse triage / phone call note | Brief encounter format | 100-300 w | Between-visit contact |
| L | Inpatient daily progress note | Daily EMU/inpatient format | 200-400 w | During hospitalization |

Templates A + B anchored on user's real notes. Templates C, D, E, F, G, H, I, J, K, L to be anchored on either (a) additional user-provided real exemplars, or (b) GPT-invented structural skeletons validated against published US EHR conventions.

## 4. Realism techniques

### 4.1 Real-note anchoring

For each template, the generation prompt includes:
- **Full exemplar text** (deidentified real note) as `EXEMPLAR` block
- **Explicit instruction:** "Match the structure, section ordering, formatting conventions, and register of the EXEMPLAR exactly. Adapt clinical content to the SEMANTIC PLAN below."
- **Style directives:** voice (third-person patient, first-person provider), register (formal specialty consult), formatting (ALL CAPS section headers for template B, Title Case for template A, etc.)

### 4.2 Copy-forward artifact injection

Real EHR notes contain redundant information copied from prior visits. Synth-v3 prompt includes:
- For non-first-visit notes: "Include the patient's PMH block verbatim as it appeared in prior notes"
- For medication lists: "Repeat the same medication list unchanged from prior visit if no changes were made"
- For social history: "Copy social history verbatim unless the patient reports a change"

### 4.3 Template placeholder patterns

Instruct GPT to use these US EHR conventions where applicable:
- `"No past medical history on file"` when PMH empty
- `"No current facility-administered medications for this visit"`
- `"No family history on file"`
- `"Twelve systems have been reviewed and pertinent positives noted in HPI. All other systems negative."`
- `"There were no vitals taken for this visit"` / `"No vitals were taken as this was a video visit"`
- `"Allergies: NKDA"` (No Known Drug Allergies) shortcut
- `"Consent was previously obtained from the patient"` for telemedicine visits

### 4.4 Physician shorthand + abbreviations

Prompt for realistic abbreviation density:
- `pt` for patient (in narrative sections)
- `s/p` for status post
- `r/o` for rule out
- `hx of` for history of
- `w/o` for without
- `c/o` for complains of
- `d/c` for discontinue
- `BID/TID/QID/QD/QHS` for medication frequencies
- `EMU` for Epilepsy Monitoring Unit
- `LTM` for long-term monitoring
- `AED` / `ASM` for anti-seizure medications
- `MTS` for mesial temporal sclerosis
- `FCD` for focal cortical dysplasia
- `SPS/CPS` for simple/complex partial seizures (historical, still used)
- `GTC` for generalized tonic-clonic
- `IED` for interictal epileptiform discharges
- `PRC` for Patient Review Conference

### 4.5 Deliberate imperfections

Real notes have quirks synth should include:
- **Occasional sentence fragments** in exam sections ("Alert. Oriented x3. No focal deficits.")
- **Rare typos** (~1-2 per 1000 words, e.g., "seizues" → "seizures")
- **Section-header inconsistency** across notes for same patient
- **Timestamp drift** (some notes reference the wrong date)
- **Section-order variation** (some clinicians put Vitals before PE, some after)
- **Length variance** (rushed follow-up vs thorough new patient)

### 4.6 Longitudinal patient trajectories

Instead of standalone notes, generate note SEQUENCES per patient:

**Phenotype profile → typical trajectory:**

| Profile | Encounter timeline |
|---|---|
| Newly diagnosed | ED note → Neurology new patient → EEG → MRI → Follow-up |
| Drug-responsive | New patient → Follow-up × 3 (increasing intervals) |
| Drug-resistant | New patient → Follow-up → EEG → EMU → Follow-up → PRC → Neuropsych |
| Presurgical evaluation | Follow-up → EMU → PRC → Neuropsych → Neurosurgery consult → Discharge summary post-op |
| Post-surgical | Discharge summary → Follow-up × 4 (Engel outcome documented) |
| Autoimmune epilepsy | ED → EMU → Immunotherapy planning → Follow-up |
| Infantile / pediatric | Multiple pediatric neuro follow-ups + genetic testing report |

Each patient gets 5-10 notes representing their full care journey, with **consistent phenotype but progressive clinical detail**.

### 4.7 Multi-provider hand-offs

Real epilepsy care involves multiple providers:
- Attending neurologist
- APP (NP/PA)
- Neurosurgeon
- Neuropsychologist
- EMU fellow
- Emergency physician
- Radiologist
- EEG technologist

For each note, prompt specifies provider persona (name pattern, credentials). Notes about same patient show consistent phenotype but different clinical voices.

### 4.8 Regional/institutional variation

US epilepsy care has regional flavors. Assign each patient a care-setting cluster:
- Academic medical center (heavy on presurgical workup, RNS/DBS mentions)
- Community neurology practice (routine medication management, occasional EMU referrals)
- VA hospital (post-TBI epilepsy, mental health comorbidity, Vets Administration terminology)
- Tertiary pediatric epilepsy center (genetic testing, ketogenic diet, developmental delay)
- Rural / underserved (delayed diagnosis, tele-neurology follow-ups)

Each cluster has characteristic phrasing patterns.

## 5. Multi-modality diversity strategies

### 5.1 Generator model mix
- **gpt-5.6-sol** — 250 notes (consistent with synth-v1/v2 baseline)
- **gpt-5.6-luna** — 250 notes (adds linguistic diversity)
- **gpt-5.6-terra** — NEVER (reserved for held-out evaluation per project memory rule)

### 5.2 Template weights (500 notes)

| Template | N | % | Care journey step |
|---|---|---|---|
| A. New patient consult | 100 | 20% | First encounter for most trajectories |
| B. Telephone FUV | 60 | 12% | Interim between visits |
| C. In-person FUV | 100 | 20% | Routine follow-up |
| D. EMU admission | 40 | 8% | Presurgical workup |
| E. ED note | 40 | 8% | Acute presentations |
| F. PRC summary | 30 | 6% | Surgical evaluation |
| G. MRI report | 40 | 8% | Imaging workup |
| H. EEG report | 40 | 8% | Neurophys workup |
| I. Neuropsych | 15 | 3% | Presurgical baseline |
| J. Discharge summary | 20 | 4% | Post-op |
| K. Triage call | 5 | 1% | Between-visit contact |
| L. Inpatient progress | 10 | 2% | Daily inpatient (EMU/post-op) |
| **Total** | **500** | | |

### 5.3 Phenotype profile distribution

| Profile | % | Notes/patient | Total notes |
|---|---|---|---|
| Newly diagnosed | 15% | 5 | 75 |
| Drug-responsive | 20% | 4 | 80 |
| Drug-resistant | 25% | 6 | 150 |
| Presurgical evaluation | 15% | 8 | 120 |
| Post-surgical | 8% | 5 | 40 |
| Autoimmune | 7% | 5 | 35 |
| Developmental / infantile | 5% | 5 | 25 |
| Status epilepticus history | 5% | 5 | 25 |

~100 patients, ~500 notes total.

### 5.4 Care setting distribution

- Academic medical center: 40%
- Community neurology: 30%
- VA: 15%
- Tertiary EMU: 15%

### 5.5 Note-length variance (per template)

Each template's target length is a distribution, not a fixed value:
- Template A: mean 1750 w, std 300 w
- Template B: mean 1000 w, std 200 w
- etc.

Prompt specifies target with variance: "Aim for approximately 1750 words but natural variation is expected."

## 6. Statistical validation

### 6.1 Profile computation

Compute statistical profile for both real and synth corpora:

**Structural metrics:**
- Section header frequency (which appear, in what order)
- Section length distributions
- Total note length distributions
- Sentence length distributions
- Paragraph count distributions

**Style metrics:**
- Abbreviation density per 1000 words
- Copy-forward artifact frequency
- Typo/fragment rate
- Passive/active voice ratio
- Medical terminology density

**Content metrics:**
- Phenotype field coverage (which v0.2.1 fields populated per note)
- Drug mention format compliance (`generic (BRAND) dose` pattern)
- Deidentification pattern compliance (xxx usage)

### 6.2 Real-vs-synth comparison

For each metric:
- Kolmogorov-Smirnov test for distribution equivalence
- Chi-squared for categorical distributions
- Target: p > 0.05 (fail to reject null of same distribution) on ≥80% of metrics

### 6.3 Deliverable

`docs/SYNTH_V3_REALISM_REPORT.md` — full statistical validation with per-metric results and interpretation.

## 7. Human blind evaluation (Turing-style)

### 7.1 Setup

- **Sample:** 10 synth-v3 notes + 10 real deidentified US epilepsy notes (from user's institution, IRB-appropriate)
- **Task:** Neurologist reviewer classifies each as "real" or "synthetic"
- **Blinded:** Notes shuffled, no metadata, no timestamps

### 7.2 Interpretation

| Reviewer accuracy | Interpretation |
|---|---|
| 90-100% correct | Synth easily distinguishable — needs more realism iteration |
| 70-89% | Some tells remaining — identify + fix systematic differences |
| 55-69% | Approaching indistinguishable — good result |
| 50-54% | **Clinician-indistinguishable** — paper-strong claim |
| < 50% | Reviewer systematically wrong — check for bias |

### 7.3 Iteration

If < 70% accurate, identify what tips reviewer off, iterate prompt, regenerate a batch.

## 8. Legal, ethical, and safety framework

### 8.1 Exemplar handling

- User-provided real deidentified notes stored at `references/real_us_note_templates/` (gitignored)
- **Never committed to git, never redistributed**
- Full attribution in paper: "Structural templates informed by deidentified real US EHR notes from University of Rochester Medicine (used with clinician consent, IRB-approved research use)"
- User confirms IRB approval + institutional consent for template use in research

### 8.2 Deidentification

- All user exemplars must be fully deidentified BEFORE they enter our pipeline
- User to verify: no real patient names, DOBs, MRNs, addresses, phone numbers, physician names beyond `xxx` masking
- Any residual identifiers we detect: flag to user, do not use exemplar

### 8.3 Synthetic patient identifiers

- New patient IDs: P003000-P003099 (100 patients, disjoint from synth-v1/v2 + F-S)
- Names: entirely fabricated using GPT with prompt `"generate a plausible US patient name"` — must be verified against public directories to avoid coincidence
- Institutions: fictional (`Northeast Medical Center`, `Midwest Regional Neurology`) — never real institutions
- Provider names: fabricated

### 8.4 Content constraints

- No real drug pricing / insurance codes (they change)
- No real hospital-specific policies
- No real clinical trial names (unless publicly available reference)
- No content that could be mistaken for actual patient records

## 9. Deliverables

### 9.1 Documentation
- `docs/SYNTH_V3_MASTER_PLAN.md` — this document
- `docs/SYNTH_V3_DESIGN.md` — technical design specification
- `docs/SYNTH_V3_REALISM_REPORT.md` — statistical validation results
- `docs/SYNTH_V3_HUMAN_EVAL.md` — human blind evaluation results
- `references/real_us_note_templates/README.md` — provenance + IRB status

### 9.2 Prompt library
- `prompts/synth_v3_templates/template_A_new_patient_consult.txt`
- `prompts/synth_v3_templates/template_B_telephone_fuv.txt`
- ... (all 12 templates)
- `prompts/synth_v3_templates/README.md` — usage documentation

### 9.3 Generation infrastructure
- `scripts/synth_v3_patient_sampler.py` — creates 100 patients with phenotype profiles
- `scripts/synth_v3_encounter_planner.py` — assigns note-type timeline per patient based on profile
- `scripts/generate_synth_v3_corpus.py` — main generator with template routing
- `scripts/convert_synth_v3_targets.py` — semantic plan → v0.2.1 gold with CUI enrichment
- `scripts/synth_v3_realism_analyzer.py` — statistical profile comparison

### 9.4 Corpus data
- `data/episynth_corpus/v3/` structured as v2:
  - `documents/{PID}/{note_type}/output.txt`
  - `targets/{PID}.json` — patient-level phenotype
  - `gold_v0_2_1/{PID}_{note_type}.json` — per-doc gold
  - `manifest.csv` — all metadata + generator + template + timeline position
  - `run_metadata.json` — model versions, timestamps, total cost, random seed
  - `README.md` — reproducibility instructions

### 9.5 Held-out evaluation subset
- `data/eval_corpora/synth_v3_eval_100/` — patient-disjoint 100-doc held-out
- Ready for `run_medcat_rules_on_corpus.py --corpus synth_v3_eval_100`

## 10. Timeline + cost

| Phase | Duration | Cost | Deliverable |
|---|---|---|---|
| **Phase 1: Design + template extraction** | 4h | $0 | Design docs, template prompts (12) |
| **Phase 2: Additional exemplar collection** | user input | $0 | 3-5 more real note types from user (D, E, F, G, H) |
| **Phase 3: Pipeline scaffolding** | 3h | $0 | Sampler, planner, generator, converter |
| **Phase 4: Smoke test (10 notes)** | 30min | $2 | Validate pipeline end-to-end |
| **Phase 5: Full generation (500 notes)** | 3-4h | $30-50 | data/episynth_corpus/v3/ |
| **Phase 6: Statistical validation** | 1h | $0 | Realism report |
| **Phase 7: Human blind eval (user 30 min)** | user input | $0 | Human eval report |
| **Phase 8: Iteration if needed** | 2h | $10 | Refined prompts, second batch |
| **Phase 9: Score B1' + regression check** | 30min | $0 | synth_v3_eval_100 F1 |
| **Phase 10: Manuscript integration** | 2h | $0 | Updated Table 2 with synth-v3 |
| **TOTAL** | **~16h + user time** | **$45-65** | Full US-realistic corpus |

## 11. Success criteria

### 11.1 Technical
- ✓ 500 notes generated
- ✓ 100% pass Pydantic v0.2.1 validation
- ✓ Patient IDs disjoint from synth-v1, synth-v2, F-S
- ✓ Cost stays under $65
- ✓ All 12 templates represented per allocation
- ✓ Statistical profile validation ≥80% metrics pass K-S test vs real

### 11.2 Realism
- ✓ Human blind evaluation: clinician accuracy ≤69% (approaching indistinguishability)
- ✓ Copy-forward artifacts present in ≥60% of follow-up notes
- ✓ Template placeholder phrases match real note patterns

### 11.3 Extractor performance
- ✓ B1' F1 on synth_v3_eval_100 in range 0.65-0.80 (slightly lower than synth-v2 due to added structural variance, still meaningful)
- ✓ No regression on F-S 40 (must stay ≥ 0.78)
- ✓ No regression on synth-v1/v2 (must stay ≥ 0.78)

### 11.4 Paper impact
- ✓ New Table 2 row: synth-v3 with realism report reference
- ✓ §Methods.SynthGeneration subsection expanded with template-anchored methodology
- ✓ §Limitations acknowledges synthetic vs real gap remaining after v3
- ✓ Reproducibility statement includes all scripts + deidentified exemplar hashes

## 12. Iterative improvement roadmap

Beyond synth-v3, potential future iterations:

- **synth-v4:** Multi-EHR-vendor style calibration (Epic vs Cerner vs Athena) — needs vendor-specific exemplars
- **synth-v5:** Adversarial realism — train a classifier to distinguish synth vs real, use its loss to improve prompts iteratively
- **synth-v6:** Multi-lingual (Spanish for Hispanic US populations)
- **synth-v7:** Longitudinal cohorts (10-year care journeys with multiple providers)

## 13. What we need from user to start

### Required (Phase 1 blockers)
- [ ] Green-light on 12-template, 500-note plan
- [ ] Confirm storage location: `references/real_us_note_templates/` (gitignored)
- [ ] Verify IRB status: is use of your 2 existing notes for research-methodology inspiration approved?

### Highly recommended (Phase 2 additional exemplars)
- [ ] 1 real EMU admission summary (template D)
- [ ] 1 real ED note for first-seizure workup (template E)
- [ ] 1 real MRI report (epilepsy protocol) (template G)
- [ ] 1 real EEG report (template H)
- [ ] 1 real PRC summary or presurgical eval (template F)

Every additional exemplar significantly increases realism for that template.

### Optional (Phase 7 human evaluation)
- [ ] 30 min of your (or a colleague neurologist's) time for blind evaluation
- [ ] 10 real deidentified notes to mix with 10 synth-v3 for blind evaluation

## 14. Phase-by-phase launch checklist

**Phase 1 (design):**
- Write this document ✓
- Write `docs/SYNTH_V3_DESIGN.md` (technical spec)
- Write prompt templates A + B (using your 2 exemplars)
- Write skeleton prompts for C-L (with placeholder for real exemplars)

**Phase 2 (exemplars):**
- User provides additional deidentified notes if available
- Store at `references/real_us_note_templates/`
- Populate remaining template prompts

**Phase 3 (infrastructure):**
- Extend `scripts/synth_patient_sampler.py` for v3 (300 patients)
- Write `scripts/synth_v3_encounter_planner.py`
- Extend `scripts/generate_synth_corpus.py` for template routing

**Phase 4 (smoke test):**
- Generate 10 notes, spot-check by user
- Iterate if quality issues

**Phase 5 (full generation):**
- Launch 500-note batch
- Monitor cost + quality

**Phase 6 (validation):**
- Run statistical profile comparison
- Write realism report

**Phase 7 (human eval):**
- User conducts 20-note blind eval
- Report accuracy

**Phase 8 (iterate if needed):**
- Address any systematic differences flagged by user
- Regenerate affected batch

**Phase 9 (evaluation):**
- Run B1' extractor on synth_v3_eval_100
- Compute F1
- Verify no regression on other corpora

**Phase 10 (integration):**
- Update `docs/MedCAT.md` corpus roll-up
- Update `writing/MedAI_EPI_Manuscript_v0.5_additions.md` with synth-v3 row
- Commit + tag as `synth-v3-v1.0`

## 15. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| GPT ignores template exemplars | Medium | Explicit "match structure exactly" instruction + few-shot format |
| Cost exceeds $65 | Low | Cost cap enforced in generator; abort if projected >$65 |
| Notes fail Pydantic validation | Low | Same validator as synth-v1/v2 (0% failure rate) |
| Clinician can distinguish 100% | Medium | Iterate: identify tells, refine prompts, regenerate |
| Realism report fails K-S tests | Medium | Adjust length/section frequency prompts, regenerate |
| User doesn't have IRB for exemplar use | Low | Use only structural patterns (not verbatim clinical content) |
| Deidentification incomplete on user exemplars | Low | Automated PHI scanner before ingest; user re-verify |

## 16. Bottom line

**synth-v3 is the most defensible synthetic US epilepsy notes corpus achievable without direct real-patient EHR access.** It combines:

- Real-note structural anchoring (from user's deidentified exemplars)
- Multi-template diversity (12 note types covering full care spectrum)
- Longitudinal patient trajectories (5-10 notes per patient)
- Deliberate imperfection injection (copy-forward, shorthand, EMR quirks)
- Statistical validation (K-S tests vs real note profiles)
- Human blind evaluation (Turing-style acceptance gate)
- Full traceability (manifest with template + generator + timeline metadata)
- Legal safety (gitignored exemplars, fictional identifiers, IRB compliance)

**Expected outcome:** clinician-indistinguishable synthetic US epilepsy notes suitable for:
- B1' MedCAT+Rules cross-domain evaluation
- LoRA v4 M4 fine-tuning training pool
- Paper reproducibility demonstration
- Public release under CC-BY (synthetic data has no HIPAA concerns)

**Recommended launch order:**
1. User green-lights this plan
2. User provides 3-5 additional deidentified exemplars (dramatically improves templates C-L)
3. I write technical design doc + template prompts
4. Smoke test 10 notes for user review
5. Full generation
6. Validation + iteration
7. Manuscript integration

Total effort: ~16 hours + user IRB verification + user 30-min human eval + $45-65 OpenAI cost.
