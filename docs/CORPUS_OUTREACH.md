# Corpus outreach tracker

Track requests to authors + registrations for annotated corpora that would fill MedAI-EPI schema fields the Fonferko-Shadrach 2024 corpus doesn't cover (EEG structured fields, MRI structured fields, Engel/ILAE outcomes, drug-resistance labels, semiology→localization pairs).

## Status board

| # | Corpus | Type | Contact | Status | Sent | Response | Next action |
|---|---|---|---|---|---|---|---|
| 1 | Zhang et al. 2025 — 852 public semiology-EZ pairs | data-request | Feng Liu, Stevens IT | pending | ☐ | — | fill placeholders and send |
| 2 | TUH EEG Corpus (Temple University) | registration | Ivan Selesnick / NEDC | pending | ☐ | — | submit registration form + PI signature |
| 3 | Xie 2022 / 2023 seizure-outcome corpora (Penn Epilepsy NLP) | collaboration | Colin Ellis / Kathryn Davis, U Penn | pending | ☐ | — | send collaboration inquiry |
| 4 | Adelson 2026 Engel + ILAE outcome corpus (West Virginia University) | collaboration | P. David Adelson, West Virginia University | pending | ☐ | — | send collaboration inquiry |

**Fill in these blanks before sending:**
- Your name, title, institution, email — search-replace `<YOUR_NAME>`, `<YOUR_TITLE>`, `<YOUR_INSTITUTION>`, `<YOUR_EMAIL>`
- Your PI's name / institutional affiliation — `<PI_NAME>`, `<PI_TITLE>`
- IRB status (if applicable) — `<IRB_STATUS>`
- Timeline of your project — `<TARGET_TIMELINE>`

Log responses under each request block below (date received, terms offered, next step).

---

## 1. Zhang / Liu (Stevens IT) — semiology-EZ 852-pair database

**Paper:** Zhang M et al. (2025). Clinical Value of ChatGPT for Epilepsy Presurgical Decision-Making: Systematic Evaluation of Seizure Semiology Interpretation. *J Med Internet Res* 27:e69173. DOI: 10.2196/69173. PMCID: PMC12107199.
**Data availability quote:** *"The data will be made available upon reasonable request to the corresponding author, FL."*
**What we want:** the 852 public semiology-EZ pairs (already publicly derived from 193 case-report publications, so the raw data provenance is unrestricted; just the compiled table).

### Draft email

> **Subject:** Data-availability request: 852 semiology-EZ pairs from JMIR 2025 (10.2196/69173)
>
> Dear Professor Liu,
>
> I am `<YOUR_NAME>`, `<YOUR_TITLE>` at `<YOUR_INSTITUTION>`, working with `<PI_NAME>` on MedAI-EPI, a research phenotyping project that extracts structured epilepsy phenotypes from heterogeneous clinical documents for downstream research use.
>
> Your recent JMIR paper *Clinical Value of ChatGPT for Epilepsy Presurgical Decision-Making* (10.2196/69173) describes a publicly compiled cohort of 852 semiology-EZ pairs drawn from 193 peer-reviewed case reports. Your data-availability statement notes this dataset is available upon request. I am writing to ask whether it would be possible to receive a copy for our project.
>
> How we would use it:
>
> - As a distant-supervision source for a **`focal_motor_onset` / `focal_nonmotor_onset` / clinical-localization** silver-label pipeline in our schema (v0.2.1).
> - As one benchmark comparison for our Med42-based extraction system alongside the Fonferko-Shadrach 2024 clinic-letter corpus.
> - Not for redistribution — we would keep the file within our IRB-approved secure compute environment and cite your paper (and any derivative work) in all downstream publications.
>
> Any format is fine (CSV, TSV, Excel). If a data-sharing agreement is required by Stevens IT, we would be happy to sign the appropriate DUA.
>
> Thank you for considering this and for making the underlying methodology public in your paper.
>
> Best regards,
> `<YOUR_NAME>`, `<YOUR_TITLE>`
> `<YOUR_INSTITUTION>` — `<YOUR_EMAIL>`

### Response log
- (empty)

---

## 2. TUH EEG Corpus registration (Temple University Neural Engineering Data Consortium)

**Resource:** Temple University Hospital EEG Corpus — TUEG / TUAB / TUSZ / TUEP / TUAR / TUSL sub-corpora. Contains ~30,000+ EEG recordings **plus the free-text neurologist reports** describing IEDs, localizations, seizures captured, ictal onsets, and clinical impressions.
**Access:** https://isip.piconepress.com/projects/nedc/html/tuh_eeg/ — free after registration. Requires institutional email and PI counter-signature. Files distributed via rsync from the NEDC server.
**Why we want it:** the reports are the largest realistic corpus of neurologist-written EEG interpretations available anywhere. Even without our schema's exact field labels, silver-label extraction over the reports (via our B0 EEG rules or via prompt-based M0/M1) would fill an entire arm's worth of data for the EEG module.

### Draft registration email / letter of intent

> **Subject:** TUH EEG Corpus access request — MedAI-EPI research phenotyping (epilepsy NLP)
>
> Dear TUH EEG Corpus team,
>
> I am writing to request access to the Temple University Hospital EEG Corpus for a research NLP study.
>
> **Project name:** MedAI-EPI — Research Phenotyping Assistant for Epilepsy Clinical Documentation
> **Principal investigator:** `<PI_NAME>`, `<PI_TITLE>`, `<YOUR_INSTITUTION>`
> **Requestor:** `<YOUR_NAME>`, `<YOUR_TITLE>`
> **Institutional email:** `<YOUR_EMAIL>`
>
> **Which sub-corpora we would like access to:**
> - Primary: TUEG (main EEG corpus, including report text)
> - Secondary: TUEP (epileptic vs. non-epileptic labels), TUSZ (seizure event annotations)
>
> **Research purpose:** MedAI-EPI develops an evidence-grounded structured phenotype-extraction system for epilepsy clinical documents. The paper's blueprint requires per-doc-type baselines (rules and BERT-family models) plus prompted / adapted medical LLM arms. The TUH EEG report text would be used as:
>
> 1. A silver-labeled training corpus for our B1 clinical-BERT baseline on EEG-report extraction targets (study type, background, IED type/localization/laterality/dominant frequency, ictal onset lobe/laterality, seizures captured count).
> 2. A held-out external-validation slice for our locally deployed Med42 extraction system.
>
> **Governance:**
> - Data will remain on institutionally approved secure compute at `<YOUR_INSTITUTION>`.
> - No content will be redistributed or reproduced in publications beyond illustrative quotes permitted under fair-use / your terms of use.
> - All publications will cite the TUH EEG Corpus per the citation guidance on the NEDC website.
> - IRB status: `<IRB_STATUS>` (attached / to be attached).
>
> Please let me know what additional information or PI attestation is required. I can arrange for `<PI_NAME>` to co-sign whatever documentation is standard for your data-use agreement.
>
> Thank you for making this corpus available to the research community.
>
> Best regards,
> `<YOUR_NAME>`
> `<YOUR_INSTITUTION>` — `<YOUR_EMAIL>`

### Response log
- (empty)

---

## 3. Xie / Ellis (U Penn) — epilepsy NLP corpora

**Papers of interest:**
- Xie K et al. (2022). Extracting seizure frequency from epilepsy clinic notes: a machine reading approach to natural language processing. *JAMIA* 29(5):873-881. doi:10.1093/jamia/ocac018.
- Xie K et al. (2023). Generalization of finetuned transformer language models to new clinical contexts. *JAMIA Open* 6(3):ooad070.
- Xie K et al. (2023). Long-term epilepsy outcome dynamics revealed by natural language processing of clinic notes. *Epilepsia* 64(7):1900-1909.

**Corresponding contacts:** Colin Ellis, MD (Assistant Professor of Neurology, Penn Epilepsy Center); Kathryn Davis, MD MTR (Associate Professor of Neurology, Penn). Kevin Xie has moved on but the annotations live with the Penn Epilepsy Center.

**What we want:** annotated notes labeled for seizure freedom, seizure frequency text, last-seizure date, and drug-resistance status. Referenced explicitly in our paper's literature review as the closest predecessor to our seizure-freedom / drug-resistance extraction.

### Draft email

> **Subject:** Collaboration inquiry — Penn epilepsy-NLP annotated corpora for MedAI-EPI cross-institutional evaluation
>
> Dear Dr. Ellis and Dr. Davis,
>
> I am `<YOUR_NAME>`, `<YOUR_TITLE>` at `<YOUR_INSTITUTION>`. Along with `<PI_NAME>`, I am building **MedAI-EPI**, an evidence-grounded structured-phenotype extraction system for epilepsy clinical documentation, designed as a research phenotyping layer to support downstream retrospective epilepsy research at our institution.
>
> Your group's series of publications on epilepsy NLP has directly shaped our study design:
>
> - *Xie et al. 2022 (JAMIA)* seizure-frequency extraction — informing our `SeizureFrequency` schema module and our per-field annotation strategy.
> - *Xie et al. 2023 (JAMIA Open)* generalization across contexts — motivating our document-type stratification design.
> - *Xie et al. 2023 (Epilepsia)* longitudinal outcome dynamics — used as our motivating downstream use case.
>
> I am writing to explore two possibilities:
>
> 1. **Cross-institutional validation.** Would you be open to us evaluating our extraction pipeline (Med42-8B based, evidence-grounded) on your annotated corpus as an external validation slice? Any output would remain governed by the receiving-side DUA, and Penn would be co-authored on the resulting publication.
> 2. **Access to the annotated notes** (or a subset — e.g., a de-identified benchmark split) for use as silver / training material during the pilot phase of our institutional annotation. We would sign whatever DUA Penn requires.
>
> If neither is currently possible, I would be grateful for any advice you can offer on annotator training, adjudication protocol, and drug-resistance label operationalization from your experience.
>
> Timeline: `<TARGET_TIMELINE>`.
>
> Thank you for considering this — happy to hop on a call if it's easier.
>
> Best regards,
> `<YOUR_NAME>`, `<YOUR_TITLE>`
> `<YOUR_INSTITUTION>` — `<YOUR_EMAIL>`

### Response log
- (empty)

---

## 4. Adelson (West Virginia University) — Engel / ILAE outcome corpus

**Paper:** Adelson PD, Delaney H, D'Haese PF. (2026). Bridging the outcome documentation gap in epilepsy surgery: validating large language model agents for automated Engel and ILAE scoring from clinical notes. *Epilepsia* 2026;67(9):4483–4492. doi:10.1002/epi.70341.
**Corresponding contact:** P. David Adelson, MD, West Virginia University (affiliation per PubMed, checked 2026-10-08; confirm the current title and corresponding author on the paper before sending).
**What we want:** their post-operative follow-up notes labeled with Engel and ILAE outcome classes. Would strengthen MedAI-EPI's `SurgeryHistoryItem.engel_class` / `.ilae_outcome` fields dramatically since our own institution likely has small surgical volume compared with theirs.

### Draft email

> **Subject:** Collaboration inquiry — Engel/ILAE outcome extraction (MedAI-EPI cross-site validation)
>
> Dear Dr. Adelson,
>
> I am `<YOUR_NAME>`, `<YOUR_TITLE>` at `<YOUR_INSTITUTION>`, working with `<PI_NAME>` on **MedAI-EPI**, a research phenotyping system for structured extraction of epilepsy phenotypes from heterogeneous clinical documents.
>
> Your recent Epilepsia paper *Bridging the outcome documentation gap in epilepsy surgery: validating large language model agents for automated Engel and ILAE scoring* is directly upstream of one part of our schema. Our `SurgeryHistoryItem` module already includes structured slots for `engel_class` (IA–IVC) and `ilae_outcome` (1–6) with per-field evidence-span grounding, but our institutional cohort has modest surgical volume, which limits our ability to evaluate those specific fields with statistical power.
>
> I am writing to explore whether your team at West Virginia University might be open to a collaborative arrangement:
>
> 1. **Cross-institutional validation** — running our locally deployed extraction system (Med42-8B, deterministic decoding, evidence-grounded) on a subset of your post-operative follow-up notes as a validation slice for the Engel/ILAE fields. Outputs would remain governed by your institution's DUA; your team would be co-authors on any resulting publication.
> 2. **Sharing of prompt / annotation methodology** — even without shared data, we would benefit greatly from your team's operational experience on Engel/ILAE label validation.
>
> Your paper's LLM-agent approach and our schema-constrained baseline are methodologically complementary (agent orchestration vs. per-field validate-and-repair). A joint benchmark on Engel/ILAE extraction, if feasible, could inform the field beyond either study individually.
>
> Happy to send our schema documentation and validation harness ahead of any conversation.
>
> Best regards,
> `<YOUR_NAME>`, `<YOUR_TITLE>`
> `<YOUR_INSTITUTION>` — `<YOUR_EMAIL>`

### Response log
- (empty)

---

## Follow-up cadence recommendation

- Send all four in a single afternoon so responses correlate in time.
- Re-ping after **2 weeks** if no response; second re-ping at **4 weeks**.
- Log all responses in the tracker table above.
- If any group offers data under a DUA, forward the DUA to `<PI_NAME>` and `<YOUR_INSTITUTION>`'s office of research contracts to negotiate terms before signing.

## What we do while we wait

None of the four outreach responses gate our engineering work. In parallel, keep executing:
- Submit `sbatch scripts/slurm_m2_mri.sh` for the first real Med42 signal.
- Advance IRB / institutional cohort work.
- Iterate schema v0.2.1 with the epileptologist.
- Draft manuscript methods section.
- B0 EEG + medication rules are already in place; extend to clinical_seizure if time permits.
