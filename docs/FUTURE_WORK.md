# MedAI-EPI — future work

**Purpose**: capture follow-up study designs that are out of scope for Shape A
(the current manuscript) but that the framework and its released artifacts
naturally enable. This is not a roadmap of things we are working on — it is
a parking lot for defensible, publishable extensions that the paper's own
scope decisions imply.

## Shape B — institutional real-EHR validation

**One-line thesis**: rerun the exact Shape A framework on IRB-approved
institutional clinical documentation and report the extraction performance
degradation caused by real-EHR artefacts (copy-forward propagation, dictation
errors, cross-note contradictions, incomplete sentences, template pollution).

**What Shape A gives Shape B for free**:
- Schema v0.2.1 (versioned, immutable)
- 22 versioned prompts (M0 / M1 / M2 across six modules)
- Three-tier deterministic repair chain
- Evaluation harness with bootstrap CIs, paired McNemar's, 12-category error
  taxonomy
- `Dockerfile.eval` and `eval/aggregator_cli.py` reproducibility container
- TRIPOD-LLM checklist template

**What Shape B has to add**:
- Site-specific IRB / research-ethics-board approval
- De-identification pipeline appropriate to the source EHR system
- Institutionally-approved secure compute (no PHI to external APIs)
- ~20–50 clinician-adjudicated gold documents *at the institution's own
  ontology resolution* — the F-S-gold field set is a starting point; institutional
  needs typically expand it (surgery outcomes at Engel/ILAE resolution,
  imaging findings at Palmini-I/IIa/IIb granularity, etc.)
- Reporting delta vs Shape A on the shared field set

**Target venues**: *Epilepsia*, *JAMIA*, *Neurology Clinical Practice*.
*Epilepsia* becomes the natural home once real-EHR clinical translation is
demonstrated. See `writing/journal.md` for the tier discussion.

**Timeline estimate**: 6–12 months, dominated by IRB, de-identification
review, and clinician annotation time.

## Shape C — linked multi-document synthetic epilepsy corpus

**One-line thesis**: generate 300–500 synthetic epilepsy *patients* — each
represented by a linked set of documents (progress note + EEG report + MRI
report + EMU discharge + presurgical evaluation) generated from a shared
controlled ground truth — and evaluate MedAI-EPI's cross-modality
extraction and the `IntegratedPhenotypeModule` empirically for the first
time.

**Why this is a Shape C paper, not a Shape A add-on**:

The Shape A manuscript deliberately limits empirical evaluation to the two
modules for which Fonferko-Shadrach's clinician-adjudicated gold provides
a reference (`Medication`, `ClinicalSeizure`). The other four modules —
`Mri`, `Eeg`, `ClinicalLocalization`, `IntegratedPhenotype` — are framework-
ready but out of evaluation scope because the F-S corpus does not include
imaging or neurophysiology documents (§Metrics, `docs/FONFERKO_GOLD_SCOPE.md`).
Adding a multi-document synthetic corpus to Shape A would:
1. Explode the scope by 4–8 weeks of corpus generation + validation.
2. Introduce a new methodological question (generator-vs-extractor bias) that
   deserves dedicated treatment, not a §Results paragraph.
3. Delay Shape A submission by 2+ months without materially strengthening
   the paper's *core* claim, which is the framework + schema-echo pathology
   characterization at 8B model scale.

Shape C addresses the multi-document question on its own merits.

**Corpus generation strategy (structured-first)**:

```
                     one synthetic epilepsy patient (structured ground truth)
                                          │
              ┌───────────────────────────┼──────────────────────────┐
              │                           │                          │
       progress note                 EEG report                MRI report
   (multiple styles, one per      (radiologist styles A / B)    (radiologist
    of ~5 neurologist voices)                                    styles A / B)
              │                           │                          │
              ├── EMU admission           │                          │
              ├── EMU discharge           │                          │
              └── presurgical eval        │                          │
                                     surgery-conference note
```

Each document is generated from the same underlying structured phenotype
`Y_i` (a validated `EpilepsyPhenotype` v0.2.1 record). Documents differ in
*voice* and *emphasis* but never in the underlying facts. Prompting styles
are stratified to test linguistic robustness:
- Style A: template-heavy academic radiology / EEG voice
- Style B: narrative-heavy attending-physician voice
- Style C: dictated-then-corrected voice with realistic disfluencies

**Evaluation loop**:

For each generated document `X_ij` (patient *i*, document family *j*),
run MedAI-EPI extraction and score against the source `Y_i`:
`P(Ŷ = Y | doc_family, generator_style, arm)`. This lets Shape C ask
*which document families are hardest*, *which generator styles trip which
arms*, and *whether the `IntegratedPhenotypeModule`'s cross-modality
consistency check catches multi-doc contradictions we deliberately seed*.

**The generator-vs-extractor circularity risk**:

The main reviewer objection to Shape C will be: "You tested an LLM
extractor on notes generated by another LLM; both are trained on similar
corpora; performance is inflated by shared statistical regularities." This
is a legitimate critique of *any* fully-synthetic pipeline and must be
addressed by design:
1. Generate the corpus using at least two independent generator families
   (e.g. one open-weight, one frontier API) with disjoint training-data
   sources where possible.
2. Include a clinician-authored control subset (n ≈ 20) written by neurology
   staff from the same ground-truth records, and report extraction delta
   between LLM-generated and clinician-written documents for the same
   underlying `Y_i`.
3. Cross-validate with the Shape A F-S-gold numbers on the shared field
   set — if MedAI-EPI's Shape C numbers on `Medication` closely track its
   Shape A numbers, the generator is not adversely inflating results.

**What Shape C gives Shape A**:

Nothing directly — Shape C is downstream of Shape A. But once Shape C
exists, it provides a controlled substrate for future *methods* papers
(e.g., LoRA fine-tuning at Shape D) that would be infeasible on institutional
data alone.

**Target venues**: *npj Digital Medicine* (open-source corpus + methodology
angle), *Nature Communications* (if the corpus is large enough and used
downstream by other groups), *Epilepsia* (specialty framing).

**Timeline estimate**: 3–6 months. Corpus generation is fast; generator
validation and clinician control-subset are the long poles.

## Shape D — parameter-efficient fine-tuning (LoRA / QLoRA)

**One-line thesis**: with a large enough gold-labeled corpus (institutional
via Shape B, or synthetic-with-ground-truth via Shape C), does LoRA or
QLoRA fine-tuning of Med42-8B close the gap to frontier LLMs on the
`ClinicalSeizure` module — the one refractory to M0 / M1 / M2 in Shape A?

**Prerequisites**: Shape B or Shape C first — Shape A's 200-letter silver
corpus is too small to expect meaningful fine-tuning gain (§Discussion 4th
limitation).

**Timeline**: 2–4 months once prerequisites exist.

## Priorities

The Shape A manuscript deliberately does not commit to Shape B / C / D
priorities — that is a decision for co-authors and PI review. But: any of
the three shapes is a defensible follow-up publication, and none of them
undermines Shape A's contribution.

For the manuscript's §Discussion, the current phrasing ("future work" and
"institutional-cohort validation studies") is sufficient. This document is
the extended internal version.

## LEO open items (2026-10-01, after leo-v0.4)

Not started. Order is by value for the LEO paper.

1. ~~Validate leo-v0.4 on an unused set.~~ Done on `ext` and `v1v2` (EVAL_PROTOCOL_LEO 10.13); Arm H2 synthetic runs still to score. Original note: Run the LLM arms on the synth-v2 / synth-v1 notes already on disk (no new generation) and score with `scripts/score_leo_vs_synth_gold.py`. The four v0.4 changes were designed on the notes they were first scored on.
2. **Current-ASM convention (SCOPE_DECISIONS D6).** Built in leo-v0.5 (rescue path, two views). Remaining: a clinician picks the headline view; check the rescue cues on US notes (the rule has fired on 1 F-S drug so far); add a role split to the `llm` system for a like-for-like comparison.
3. **Per-field disagreement policy.** Checked on unused synthetic sets (D15) but not adopted: the default stays "rules' value everywhere" (D17) until adjudicated disagreements from real notes exist. Tooling and decision rule: `DISAGREEMENT_ADJUDICATION.md` (`bin/leo disagreements`).
4. **Hard-slice scoring** from existing gold: patients whose notes carry prior, denied, hedged or hypothetical ASM or seizure statements (polish gold has counts per slice).
5. **Learned auto-accept calibrator** on v1/v2 outputs, compared with the rule-based routing, so the rules are not tuned on test data.
6. ~~Arm H2~~ Trained and scored on the F-S letters (0.743 alone, 10.13); synthetic runs queued.
7. **Environment H9:** one environment with Flask and MedCAT (`REPO_HOUSEKEEPING.md`).
8. **Human-blocked:** ILAE 2025 decision (D1), US clinician annotation (`US_ANNOTATION_PLAN.md`), ExECT parity column (`EXECT_EPEXTRA_PARITY.md`).

### LEO in the app (added 2026-10-01; see `LEO_USER_GUIDE.md`)

1. ~~First live GPU run~~ Done 2026-10-02 (EVAL_PROTOCOL_LEO 10.12).
2. **Long notes.** Chunking now measured on joined synthetic documents (10.12; model 0.991, rules lose accuracy on joined text). Still open: hand-check long real notes.
3. **Patient-level roll-up.** Built as an option (`bin/leo rollup`, D16); per-note rows stay the default. Open: conflict flags between notes, and a clinician's rule for "latest" per field.
4. **Unscored phenotypes**: detailed EEG findings, semiology, focal onset features and surgery have no reference yet (the plans and the F-S gold do not hold them); annotate or generate for the ones the clinic needs first. Prior/failed/rescue drugs, etiology details and coarse EEG are now scored for the rules (EVAL_PROTOCOL 10.16). Rule gaps that scoring found: a drug stopped for lack of effect is usually labelled as a side-effect stop (4 of 23 right); a stopped drug is sometimes listed as current; a suggested rescue drug is read as one the patient has; EEG results are missed in 43% of letters that have one. The extended synthetic set (EVAL_PROTOCOL 10.17) adds: EEG study type read from a recommendation or a device mention (13 of 37 right), "no ictal onset captured" read as an onset, 10 of 27 interictal-discharge patterns missed, and inpatient PRN orders / hypothetical rescue instructions listed as rescue drugs. Fix these on a new batch of patients (the 37 are exposed), and settle whether a hypothetical rescue instruction counts. The model's performance on all of these is untested; real-note references need annotation (open-access case reports, or MIMIC-IV once the data are in).
5. **Real notes. Deferred beyond the MVP (2026-10-02, `DEFERRED_BEYOND_MVP.md`).** After IRB and secure compute: run a small set, review by hand, record under `EVAL_PROTOCOL_LEO.md`. Until then no result here says anything about real notes.
6. **Learning from review. Deferred beyond the MVP (2026-10-02, `DEFERRED_BEYOND_MVP.md`, which also covers reviewers adding missed values).** Step 1 is built (in-app review, `reviewed.csv`, merge; see the guide). Next, in order: (a) per-field accepted / corrected / wrong rates from reviewer decisions, as real-note evidence once real notes are approved; (b) let reviewers add values LEO missed, so recall can be measured; (c) recalibrate the auto-accept rules from decisions and test on notes the rules never saw; (d) retrain an adapter on corrected values and quotes (IRB and secure compute). Each outcome ships as a new pipeline version with a re-run evaluation, never as a live change.
9. **Epic / EHR connection** (design only, nothing built; `LEO_EPIC_INTEGRATION.md`). Stage A: warehouse export to a file and `bin/leo run` on secure compute. Stage B: read-only FHIR pull. Stage C (in-chart) not recommended before real-note accuracy and a regulatory answer. Needs IRB and data approval, login, audit log and per-user jobs first.
8. **Usefulness analyses** (planned, not run): error capture (which of the model's errors LEO flags), workload and post-review accuracy; then reviewer time on real notes. Definitions and caveats: `INTERPRETING_RESULTS.md` section 5.
7. **Environment H9** is done: `venv-medcat` holds MedCAT, torch, peft, lm-format-enforcer and Flask.

- `chain_llm.ground_value`: accept hyphenated words between the count and "per" and "once monthly" (see EVAL_PROTOCOL_LEO 10.8). Re-score Arm H after the change and label it a new pipeline version.
- NINDS CDE mapping (`docs/NINDS_CDE_MAPPING.md`): settle the partial and missing rows on the live NINDS site; no export script before that.
