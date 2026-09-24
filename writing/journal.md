# MedAI-EPI manuscript — journal-tier assessment

**As of**: 2026-09-24. Manuscript state: v0.3 with §Positioning, F-S-gold-direct
scoring (Table 4b-gold), Ethics section, legacy purge. Author list, funding,
and competing-interests placeholders still open. SLURM 103501 running
(max_new_tokens=4096 sensitivity, 60% complete).

## Paper characteristics

- **Type**: methodology paper (Shape A of the two-shape roadmap)
- **Contribution**: schema + prompt registry + repair chain + evaluation
  harness + schema-echo pathology characterization at 8B model scale +
  specialty-at-a-time framing
- **Corpus**: openly-licensed Fonferko-Shadrach synthetic clinic letters
  (n=200), CC-BY 4.0
- **Reference labels**: F-S native clinician-adjudicated gold (in-scope: 8
  fields across ClinicalSeizure + Medication)
- **Baselines evaluated**: B0 rules, B1 BioClinicalBERT (single-head, 94 docs),
  Med42-8B under M0/M1/M2 prompting arms
- **Modules empirically scored**: 2 of 6 (Medication, ClinicalSeizure); the
  other four are framework-ready but out of evaluation scope (documented in
  `docs/FONFERKO_GOLD_SCOPE.md`)
- **Headline numbers**: M1 medication.current_asms F1 = 0.26 [0.18, 0.34]
  against F-S gold; schema-echo pathology on M2 (χ² = 19 vs M0, χ² = 28 vs
  M1); B0 rules F1 = 0.57 on ASM multiset
- **Reproducibility**: `Dockerfile.eval` + `eval/aggregator_cli.py` regenerate
  every table from released run manifests without a GPU
- **Reporting**: TRIPOD-LLM checklist supplied (`docs/TRIPOD_LLM_CHECKLIST.md`)

## Strengths (things reviewers will like)

- Rigorous methodology (bootstrap 95% CIs, paired McNemar's, 12-category
  error taxonomy, evidence precision measured independently of field F1)
- Open-framework posture: open corpus + open-weights model + open code +
  reproducibility container
- TRIPOD-LLM-conformant reporting
- Direct-to-gold scoring (against F-S clinician labels, not our silver labels)
- Novel schema-echo pathology characterization at 8B scale — a
  publishable-in-its-own-right negative result
- Specialty-at-a-time framing turns "narrow scope" from limitation to feature

## Weaknesses (things reviewers will push on)

- Small corpus (n=200)
- Synthetic corpus (no real-EHR artefacts: copy-forward, dictation errors,
  cross-note contradictions)
- One LLM tier evaluated (Med42-8B); no frontier-model spot check
- Two of six modules empirically scored
- Modest headline F1 numbers (F1 = 0.26 for best LLM, F1 = 0.57 for rules)
- No downstream clinical-workflow demonstration (utility demos are
  time-savings ratios, not integrated clinical use)
- B1 baseline is single-head (`epilepsy_type` only)
- No fine-tuning experiments (deliberately paused; documented in §Limitations)

---

## Tier ranking (best fit → aspirational → not-a-fit)

### Primary target: mid-tier methodology journals (best fit × high probability)

**1. JAMIA** — Journal of the American Medical Informatics Association
- IF ~5.4
- **Best fit**. Regularly publishes clinical-NLP methodology papers,
  TRIPOD-LLM-adjacent work, evaluation-framework contributions.
  Fonferko-Shadrach's ExECT lineage lives in this space.
- Paper's reproducibility container + TRIPOD checklist + direct-to-gold
  scoring are exactly what JAMIA reviewers reward.
- Typical timeline: 4–6 months to decision.

**2. Journal of Biomedical Informatics (JBI)**
- IF ~4.5
- Similar profile to JAMIA, slightly more genomics/bioinformatics-flavored
  but publishes clinical NLP steadily.
- Solid backup target if JAMIA misses.

### Aspirational tier — worth trying if co-authors think there is a champion

**3. npj Digital Medicine**
- IF ~15, Nature family
- Publishes open-framework methodology and open-source clinical AI.
- Editorial values align (open corpus + open weights + reproducibility).
- Risk: they push hard on downstream clinical impact and n=200 synthetic
  is on the small side for them. Reject-and-resubmit risk is real.

**4. Artificial Intelligence in Medicine**
- IF ~7
- Methodology-friendly, more receptive to modest-scale evaluations than npj.
- Reasonable stretch target.

### Specialty option — uncommon but plausible

**5. Epilepsia**
- IF ~5.4, *the* epilepsy journal
- Would strengthen epilepsy-community reach at the cost of longer review
  with reviewers less familiar with LLM methodology.
- Might require reframing to emphasize ILAE alignment more heavily.
- Better fit for the *Shape B follow-up* (institutional-cohort validation)
  than for this Shape A methodology paper.

**6. Neurology Clinical Practice**
- IF ~4
- Implementation-focused specialty journal; LLM-methodology framing might
  feel out-of-scope. Possible but not primary.

### Open-access fallback — fast acceptance, moderate prestige

**7. JMIR AI** (IF ~4) or **JMIR Medical Informatics** (IF ~3)
- Open access, receptive to open-framework methodology
- Typical turnaround: 2–3 months
- Fine as a fallback if JAMIA and JBI both bounce

**8. Frontiers in AI — Medicine and Public Health**
- Similar profile to JMIR family

### Not a fit

- Nature / Science / Cell — too broad, methodology not "discovery"
- NEJM / Lancet / JAMA — no clinical trial
- Nature Medicine / Lancet Digital Health — need real-EHR clinical impact
  demonstration
- ML-only conferences (NeurIPS / ICML) alone — this is medical NLP with
  clinical framing, not core ML methods
- Bioinformatics journals — wrong domain (leans genomics/proteomics)

---

## Recommended submission plan

**Step 1 — submit to JAMIA.** Highest acceptance-probability × fit product.
If accepted → done.

**Step 2 — if rejected**, resubmit to **JBI** first (fast, high fit). Only
take a swing at **npj Digital Medicine** if reviewers' comments explicitly
suggest that "adding real-EHR validation" or "adding a clinical-impact
demonstration" would flip the decision — and only after adding what they
asked for.

**Step 3 — save Epilepsia for the Shape B follow-up.** Once institutional
real-EHR validation is done and the paper has clinician-workflow evidence,
Epilepsia becomes the natural home because Epilepsia reviewers reward
clinical translation.

## Actions that would upgrade the target tier

Three things — each optional, each costs time — would move the primary target
from JAMIA to npj Digital Medicine range:

1. **Institutional real-EHR validation on ≥ 20 letters** — a Shape B preview
   that shows the framework survives real dictation errors, copy-forward
   propagation, and cross-note contradictions. Requires IRB approval and
   secure compute; realistically 3–6 months.
2. **Frontier baseline spot-check** on n≈20 letters — a natural control for
   the schema-echo pathology. Documented cost: ~$50 in API calls, one day
   of work. Currently held in reserve; if a reviewer explicitly asks for it
   in R1, running it during R2 is cheap.
3. **Downstream cohort study** using the extracted phenotypes — genuine
   research use, not just a time-savings ratio. Requires a real research
   question and dataset; realistically 3–6 months.

Without these, **JAMIA is the honest primary target** and the paper is
competitive there today.

## Journal-family formatting notes (for when the target is picked)

- **JAMIA**: ~4000-word main text, structured abstract (Objective / Materials
  and methods / Results / Discussion / Conclusion), Vancouver refs, up to
  6 tables/figures. Cover letter one page.
- **JBI**: ~6000-word main text, unstructured abstract 250 words, Vancouver
  refs, no hard table/figure cap.
- **npj Digital Medicine**: ~3500-word main text, structured abstract,
  Vancouver-numbered refs, up to 5 display items, extensive supplement OK.
- **Epilepsia**: ~4000-word main text, structured abstract, Vancouver refs,
  the "Key Points" bulleted summary is required at the top.

Current manuscript word count (v0.3): approximately 8300 words in the main
text — will need a trim pass for JAMIA/npj/Epilepsia, fine for JBI.

## References

- Paper draft: `writing/MedAI_EPI_Manuscript_v0.2.md` (v0.3 content)
- Positioning argument: manuscript §Positioning
- Evaluation scope: `docs/FONFERKO_GOLD_SCOPE.md`
- TRIPOD-LLM checklist: `docs/TRIPOD_LLM_CHECKLIST.md`
- Reproducibility harness: `Dockerfile.eval`, `eval/aggregator_cli.py`
