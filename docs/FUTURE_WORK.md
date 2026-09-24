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
