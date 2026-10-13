# MedAI-EPI References

Consolidated bibliography of papers, tools, corpora, and standards that inform the MedAI-EPI project. Grouped by role. Entries flagged **[cite]** should be included in the manuscript reference list; **[tool]** entries need only a URL/citation in Methods; **[background]** may be footnoted or omitted depending on space.

---

## 1. Corpora & benchmarks

### Fonferko-Shadrach
- **Fonferko-Shadrach B, Strafford H, Jones C, et al. (2024).** "Annotation of epilepsy clinic letters for natural language processing." *J Biomed Semantics* 15(1):17. DOI 10.1186/s13326-024-00316-z. **[cite]**
- **Dataset:** Fonferko-Shadrach B, Strafford H, Jones C, et al. "Gold standard annotation of epilepsy clinic letters for the development of information extraction tools." Zenodo, 2023. DOI 10.5281/zenodo.8381079. JSON version: Strafford H, Fonferko-Shadrach B, et al., Zenodo, 2024. DOI 10.5281/zenodo.8356493. **[cite]**
- Corrected 2026-10-08: an earlier entry here cited "Fonferko-Shadrach 2023, *Scientific Data* 10:459" (DOI 10.1038/s41597-023-02351-4) and Zenodo record 8060906. That paper does not exist; the DOI is an unrelated *Sci Data* paper and record 8060906 is an unrelated dataset.
- Role in MedAI-EPI: primary UK evaluation corpus. Note: the 200 letters are *clinician-authored synthetic* (structured to be schema-complete), not real patient records.

### MTSamples
- **MTSamples.com** — public transcribed medical dictations (open access, US). **[tool]**
- URL: <https://mtsamples.com/site/pages/browse.asp?type=42-Neurology>
- 78 neurology notes ingested for MedAI-EPI; 18 kept after epilepsy-relevance filter.

### PMC Open Access
- **PubMed Central Open Access Subset (PMC OAS)** — case reports usable under CC-BY. **[tool]**
- URL: <https://www.ncbi.nlm.nih.gov/pmc/tools/openftlist/>
- Role: schema stress-testing (v0.1 → v0.2 → v0.2.1).

### Synthea (evaluated and discarded)
- **Walonoski J et al. (2018).** "Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health care record." *JAMIA* 25(3):230–238. **[cite, if we discuss the null result]**
- URL: <https://synthetichealth.github.io/synthea/>
- Role: structured EHR list format; discarded as unrepresentative of real US narrative notes (F1 = 0 confirmed).

### Medical LLM exam benchmarks & leaderboards (teaching: `writing/learning_medai.md` Ch. 3–6)
- **Jin D et al. (2021).** MedQA — USMLE-style multiple choice. **[background]**
- **Pal A, Umapathi LK, Sankarasubbu M (2022).** MedMCQA. **[background]**
- **Jin Q et al. (2019).** PubMedQA. **[background]**
- **Hendrycks D et al. (2021).** MMLU. **[background]**
- **Gao L et al.** EleutherAI Language Model Evaluation Harness. **[tool]**
- **Pal A, Minervini P, Motzfeldt AG, Gema AP, Alex B (2024).** Open Medical-LLM Leaderboard. Hugging Face blog + Space. <https://huggingface.co/blog/leaderboard-medicalllm> **[background]**
- Role: how *exam* ranks are produced. Not run in this repo. Distinct from LEO extraction scores.

### Barlow et al. — synthetic epilepsy precedent
- **Barlow S, Gan Y, Davies J, Winston J, Teo J, Richardson M, et al. (2026).** "Using synthetic records to improve automated identification of seizure freedom in clinical text about people with epilepsy." *Proc BioNLP 2026*:20–30. DOI 10.18653/v1/2026.bionlp-1.3. **[cite]**
- Role: precedent that synthetic training data can match real data, for **seizure-freedom status only** (synthetic-trained F1 0.90 ± 0.02 vs authentic 0.87 ± 0.04). Do not generalise to other epilepsy phenotypes.

---

## 2. Ontology, classification & clinical definitions

### ILAE 2017 classification
- **Fisher RS et al. (2017).** "Operational classification of seizure types by the International League Against Epilepsy: Position Paper of the ILAE Commission for Classification and Terminology." *Epilepsia* 58(4):522–530. **[cite]**
- **Scheffer IE et al. (2017).** "ILAE classification of the epilepsies: Position paper of the ILAE Commission for Classification and Terminology." *Epilepsia* 58(4):512–521. **[cite]**
- Role: canonical enum values in `schema/enums.py`; drives the ILAE modernization stage of preprocessing. Leftover E cues (2026-10-07): synonym strings map to existing enums only — psychomotor / complex-partial → FIA; partial-onset → focal unknown awareness; secondarily generalized seizures → FBTC. Operational rule: onset is the first prominent feature (`thereafter` / `subsequently` / `after that` do not become onset). Extra detector (D20): `--ext-detector first-feature` fires only on “begins with / onset with” plus the ILAE motor/non-motor checklist — not a dump of more aliases into E. Ask/audit RAG (D21): `--ask-template first_feature --ask-rag` (Fisher first-feature vs evolution); not stuffed into extract prompts.
- **Berg AT et al. (2010).** "Revised terminology and concepts for organization of seizures and epilepsies: Report of the ILAE Commission on Classification and Terminology, 2005–2009." *Epilepsia* 51(4):676–685. **[cite]**
- Role: historical names (complex partial, secondarily generalized, psychomotor) that US notes still use; E maps them onto the 2017 enums above. Not a second classification.

### Drug-resistant epilepsy
- **Kwan P, Brodie MJ (2000).** "Early identification of refractory epilepsy." *NEJM* 342(5):314–319. **[cite]**
- **Kwan P et al. (2010).** "Definition of drug resistant epilepsy: consensus proposal by the ad hoc Task Force of the ILAE Commission on Therapeutic Strategies." *Epilepsia* 51(6):1069–1077. **[cite]**
- Role: DRE definition informing synthetic patient sampler distribution and downstream drug-resistance utility demo. Extra detector (D20): `--ext-detector dre` emits `drug_resistant` only from those phrases, never from counting two failed ASMs (that inference stays E). `--ext-detector fail-reason` uses Kwan/NINDS language for why a named ASM stopped. Ask/audit RAG (D21): `--ask-template dre_kwan --ask-rag` retrieves a Kwan paraphrase; not used in L1C.

### ACNS critical-care EEG terms
- **Hirsch LJ, Fong MWK, Leitinger M, et al. (2021).** "American Clinical Neurophysiology Society's Standardized Critical Care EEG Terminology: 2021 version." *J Clin Neurophysiol* 38(1):1–29. DOI 10.1097/WNP.0000000000000806. **[cite]** Supersedes the 2012 version (Hirsch LJ et al., *J Clin Neurophysiol* 2013;30(1):1–27); the project cites 2021 throughout.
- Role in E (2026-10-07): leftover match strings only — `LTM`, `cEEG`, `ICU EEG`, `outpatient EEG` / `routine EEG`; `LPDs` (not only PLEDs), `GPDs`, `BiPDs`. LPDs set `ied_present` as `IedType.OTHER` (no new enum). Not SCORE-as-ontology. Extra detector (D20): `--ext-detector ictal` (captured vs “no ictal onset”); `--ext-detector eeg-done` (performed vs recommended). Not EEG-report NLP (Biswal/Westover 2015; Frontiers 2025) run on clinic letters. Ask/audit RAG (D21): `--ask-template ltm_sense --ask-rag` (LTM is a study, not a drug).
- **Maldonado R, Harabagiu SM (2019).** "Active deep learning for the identification of concepts and relations in electroencephalography reports." *J Biomed Inform.* PMC6922091. **[cite]** — SACAR attribute schema (morphology, frequency band, recurrence, dispersal, polarity, modality) and report-section scope. Source of `rules/eeg_attributes.py` and `rules/eeg_sections.py` (EVAL_PROTOCOL D31). Volume/article number not completed.
- **Maldonado R, Harabagiu SM (2020).** "The language of brain signals: natural language processing of electroencephalography reports." *Proc LREC 2020*. ACL Anthology 2020.lrec-1.276. **[cite]** — TUH EEG-report gold + silver annotations. External test `scripts/score_tuh_eeg_attributes.py` is blocked on Temple access.

### RxNorm / FDA ASM brands
- **NLM RxNorm.** Release pinned in `rules/asm_lexicon.py` as `rxnorm:2026-09-08`. **[tool]**
- URL: <https://www.nlm.nih.gov/research/umls/rxnorm/>
- Role: generated ASM lexicon. Leftover US FDA brands (2026-10-07) live in `rules/asm_us_brand_aliases.py` — Depakene, Stavzor, Equetro, Carnexiv, Tegretol XR, Keppra XR, Lamictal XR / ODT — brand → existing generic. Not a new ontology.

### SNOMED CT / UMLS
- **NLM Unified Medical Language System (UMLS)** — Metathesaurus and semantic types. **[tool]**
- URL: <https://www.nlm.nih.gov/research/umls/>
- Role: CUI seed for MedCAT CDB; Phase 1c/1d enrichment.

### HPO / EPIO
- **Human Phenotype Ontology (HPO).** Köhler S et al. (2021). "The Human Phenotype Ontology in 2021." *Nucleic Acids Research* 49(D1):D1207–D1217. **[cite]**
- **EPIO** — Epilepsy Ontology. Sargsyan A, Wegner P, Gebel S, et al. (2023). "The Epilepsy Ontology: a community-based ontology tailored for semantic interoperability and text mining." *Bioinform Adv* 3(1):vbad033. DOI 10.1093/bioadv/vbad033. **[cite]**

---

## 3. Extraction methodology (prior art)

### ExECT-V2
- **Fonferko-Shadrach B et al. (2019).** "Using natural language processing to extract structured epilepsy data from unstructured clinic letters: development and validation of the ExECT (extraction of epilepsy clinical text) system." *BMJ Open* 9(4):e023232. **[cite]**
- **ExECT-V2 extension** referenced in Fonferko-Shadrach 2023 companion release.
- **Cui L, Sahoo SS, Lhatoo SD, Garg G, Rai P, Bozorgi A, Zhang GQ (2014).** "Complex epilepsy phenotype extraction from narrative clinical discharge summaries." *J Biomed Inform* 51:272–279. DOI 10.1016/j.jbi.2014.06.006 (PMC4464795). **[cite]** — PEEP: EpSO-generated patterns + MetaMap on 662 US EMU discharge summaries; F1 0.927 findings, 0.856 finding + location. Source of the electrode-to-location rule (`rules/eeg_electrodes.py`, EVAL_PROTOCOL D27). Not a baseline: structured EMU summaries, one annotator per test summary.
- Role: rule vocabulary transplanted to Python; MedCAT+Rules pipeline.

### Xie / Decker / Abeysinghe (tasks, not loaded weights)
- **Xie K et al. (2022).** "Extracting seizure frequency from epilepsy clinic notes: a machine reading approach to natural language processing." *JAMIA* 29(5):873–881. **[cite]**
- **Xie K et al. (2023).** "Generalization of finetuned transformer language models to new clinical contexts." *JAMIA Open* 6(3):ooad070. **[cite]**
- **Decker BM et al. (2022).** "Development of a natural language processing algorithm to extract seizure types and frequencies from the electronic health record." *Seizure* 101:48–51. **[cite]**
- **Abeysinghe R et al. (2025).** "Leveraging pretrained language models for seizure frequency extraction from epilepsy evaluation reports." *npj Digit Med* 8:208. **[cite]**
- Role in extra detector (2026-10-07, D19–D20): the *jobs* (current stated frequency; ILAE seizure type; HS/FCD mention) are covered by `--ext-detector freq` / `stated-type` / `hs` without their weights. The `dre` (DRE as-stated) detector is our own task; neither Xie paper extracts drug-resistant epilepsy (Xie 2023 is about generalising seizure-freedom and frequency extraction to new settings). Not “run Xie’s model.” Trained heads remain blocked (`b1` / `xie` / `decker`). Engel/ILAE class: Wieser HG et al. (2001) ILAE surgery-outcome commission; Adelson PD, Delaney H, D'Haese PF, *Epilepsia* 2026;67(9):4483–4492, doi:10.1002/epi.70341 (West Virginia University) agents — `--ext-detector engel` raises until that column is a LEO phenotype. EVAL 10.34–10.35.

### MedCAT
- **Kraljevic Z et al. (2021).** "Multi-domain clinical natural language processing with MedCAT: The Medical Concept Annotation Toolkit." *Artificial Intelligence in Medicine* 117:102083. **[cite]**
- GitHub: <https://github.com/CogStack/MedCAT>
- Role: concept annotation + MetaCAT contextual classification.

### medspaCy ConText
- **Chapman WW, Bridewell W, Hanbury P, Cooper GF, Buchanan BG (2001).** "A simple algorithm for identifying negated findings and diseases in discharge summaries." *J Biomed Inform* 34(5):301–310. **[cite]**
- Role: NegEx lineage for E's leftover discontinuation / planned-med cues (`d/c'd`, `dc'd`, `will start`). Not a second ConText implementation. Same NegEx pre-negation (sentence before the mention) is used in the opt-in sidecar (`services/ext_detectors/ctakes_meds.py`, D18), as a separate path from E's medspaCy ConText.
- **Harkema H, Dowling JN, Thornblade T, Chapman WW (2009).** "ConText: An algorithm for determining negation, experiencer, and temporal status from clinical reports." *J Biomed Inform* 42(5):839–851. **[cite]**
- **Chapman BE, Lee S, Kang HP, Chapman WW (2011).** "Document-level classification of CT pulmonary angiography reports based on an extension of the ConText algorithm." *J Biomed Inform* 44(5):728–737. DOI 10.1016/j.jbi.2011.03.011. **[cite only if a ConText extension is needed]** Replaces an earlier entry ("Chapman WW et al. 2013, JBI 46(5):919–923") that does not exist.
- **Eyre H et al. (2021).** "Launching into Clinical Space with medspaCy: A New Clinical Text Processing Toolkit in Python." *AMIA Symposium.* **[cite]**
- Role: negation, uncertainty, experiencer, temporality classification. One ConText (medspaCy defaults + US SOAP additions). Leftover i2b2 cues added 2026-10-07; "home meds" stay current outpatient. Ablation inside E (D21): `--context-engine sentence|negex` vs default `medspacy`. Do not score ConText as a phenotype system (`docs/ROLE_PLACEMENTS.md`).

### i2b2 medications
- **Uzuner Ö, Solti I, Cadag E (2010).** "Extracting medication information from clinical text." *JAMIA* 17(5):514–518. **[cite]**
- Role in E (2026-10-07): triggers that mark discontinued or planned, not current — `d/c'd` / `dc'd` → prior; `will start` / `will begin` → planned. Does not load the i2b2 corpus. Optional later comparator: i2b2/n2c2 *systems* vs E on medication/ADE columns only (`docs/E_EXTERNAL_BASELINES.md`). Not a full E rival.
- Role in extra detector (2026-10-07, D18): S2 status layer on sidecar mentions (`services/ext_detectors/ctakes_meds.py`) — current / discontinued / failed / planned-drop / PRN. Same paper, separate code path from E. `--ext-detector ctakes`.

### US clinical NLP toolkits (comparators, not E loads)
- **Savova GK et al. (2010).** "Mayo clinical Text Analysis and Knowledge Extraction System (cTAKES): architecture, component evaluation and applications." *JAMIA* 17(5):507–513. **[cite]**
- **Soysal E et al. (2018).** "CLAMP — a toolkit for efficiently building customized clinical NLP pipelines." *JAMIA* 25(3):331–336. **[cite]**
- **Aronson AR, Lang FM (2010).** "An overview of MetaMap: historical perspective and recent advances." *JAMIA* 17(3):229–236. **[cite]**
- Role: optional B-arms vs E on overlapping fields (drugs, problems, UMLS hits, negation). Do not add as E synonym lists. Preferred first comparator if one is run: cTAKES or CLAMP on medications + negation. MetaMap is closer to MedCAT / O than to E’s rules. Policy: `docs/E_EXTERNAL_BASELINES.md`.
- Role in extra detector (2026-10-07, D18): Savova dictionary+negation *method* is implemented as `--ext-detector ctakes` (Python lexicon + NegEx, not the Java UIMA binary). CLAMP not installed. Fusion sidecar: `docs/FIELD_SPECIALIST_DETECTORS.md`, EVAL 10.33. Default LEO frozen.

---

## 4. Language models & fine-tuning

### Med42
- **Christophe C, Kanithi PK, Raha T, Khan S, Pimentel MAF (2024).** "Med42-v2: A Suite of Clinical LLMs." arXiv:2408.06142. **[cite]**
- Model cards: <https://huggingface.co/m42-health/Llama3-Med42-8B>, <https://huggingface.co/m42-health/Llama3-Med42-70B>. Eval recipes: <https://github.com/m42health/med42>.
- Role: primary open-weights arm (8B); LoRA target. Published 0-shot MCQA and Clinical Elo are copied into `writing/learning_medai.md` Chapter 6; this repo does not re-run that harness. 70B is not deployed here (not the default reader: memory, L40S 24GB, status errors still need rules; D21). Chain-of-thought and self-consistency are not used on the extract path (greedy `seed 0`, `do_sample=False`).

### Clinical BERT / BioClinicalBERT
- **Alsentzer E et al. (2019).** "Publicly Available Clinical BERT Embeddings." *NAACL Workshop on Clinical NLP.* **[cite]**
- Role: cited as baseline; B1 BioClinicalBERT scaffold in the repo. **Not** registered as `--ext-detector` (needs new training on our labels; EVAL D18–D19).

### Li 2021 — MIMIC clinical BERT variants
- **Do not cite.** The title previously listed here is an essay-scoring paper unrelated to epilepsy or MIMIC, and no matching epilepsy-phenotyping "Li 2021" was found (2026-10-08 check). Resolve the intended paper before using this slot.

### Goldenholz 2025 — seizure freedom
- The 2025 Goldenholz paper found is Goldenholz DM, Goldenholz SR, Habib S, Westover MB. "Inductive reasoning with large language models: a simulated randomized controlled trial for epilepsy." *Epilepsy Res* 211:107532. DOI 10.1016/j.eplepsyres.2025.107532. It simulates a trial; it does not identify seizure freedom from notes. **Do not cite it for seizure freedom.**
- For seizure-freedom extraction cite Xie K et al., *Epilepsia* 2023;64(7):1900–1909 (PMID 37114472) and Ojemann WKS et al., *J Healthc Inform Res* 2025;9(3):380–400, doi:10.1007/s41666-025-00198-5 (see `writing/further_LEO.md`).
- Role: motivates the utility demo #2 (seizure freedom identification from extracted phenotype).

### DeepSeek / open baselines
- **DeepSeek AI (2024).** "DeepSeek-V2: A strong, economical, and efficient mixture-of-experts language model." Technical report. **[background]**
- Role: alternative open backbone for the multi-model backend.

---

## 5. Reporting standards

### TRIPOD-LLM
- **Gallifant J, Afshar M, Ameen S, et al. (2025).** "The TRIPOD-LLM reporting guideline for studies using large language models." *Nat Med* 31(1):60–69. DOI 10.1038/s41591-024-03425-5. **[cite]**
- Role: manuscript checklist compliance.

### TRIPOD-AI (predecessor)
- **Collins GS et al. (2024).** "TRIPOD+AI statement: updated guidance for reporting clinical prediction models that use regression or machine learning methods." *BMJ* 385:e078378. DOI 10.1136/bmj-2023-078378. Correction: *BMJ* 2024;385:q902. **[cite]**
- Role: backup reporting frame.

---

## 6. Synthetic data & privacy

### HIPAA Safe Harbor
- **US Department of Health and Human Services.** "Guidance Regarding Methods for De-identification of Protected Health Information in Accordance with the Health Insurance Portability and Accountability Act (HIPAA) Privacy Rule." Nov 2012. **[tool/regulation]**
- URL: <https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/de-identification/>
- Role: informed deidentification of the two real US EHR exemplars in `references/real_us_note_templates/`.

---

## 7. Tools & software (Methods only)

- **OpenAI Responses API** — GPT-5.6 tiers (`gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.6-terra`). Used for synthetic generation and silver labelling only. Never deployed as a clinical extractor. **[tool]**
- **PyTorch** — Paszke A et al. 2019 NeurIPS. **[tool]**
- **transformers / PEFT** — Wolf T et al. 2020 EMNLP-Demo; Mangrulkar S et al. 2022 (PEFT). **[tool]**
- **Pydantic** — Colvin S et al. 2020. **[tool]**
- **Flask + Gunicorn** — service infrastructure. **[tool]**

---

### Medication roles: current, maintenance, rescue (added 2026-10-01, used for SCOPE_DECISIONS D6)
- **Loring DW et al. (2011).** "Common data elements in epilepsy research: development and implementation of the NINDS Epilepsy CDE Project." *Epilepsia* 52:1186-91. DOI 10.1111/j.1528-1167.2011.03018.x. NINDS CDE site: <https://www.commondataelements.ninds.nih.gov/epilepsy>. The CDEs keep an antiepileptic-drug log (name, formulation, schedule, dose, start and end dates, ongoing status, reason for discontinuation) separate from a non-AED medication log. **[cite — verify]** (field list read from the MDM-Portal copy <https://medical-data-models.org/14646>, not from the NINDS CRF itself). Extra detector (D20): `--ext-detector fail-reason` uses the CDE *reason-for-discontinuation* distinction (efficacy vs ADE vs wean). CDEs are not loaded as an E ontology (Wave 3).
- **Fertig E, Fureman BE, Bergey GK, et al. (2014).** "Inclusion and exclusion criteria for epilepsy clinical trials: recommendations from the April 30, 2011 NINDS workshop." *Epilepsy Res* 108(5):825–832. DOI 10.1016/j.eplepsyres.2014.02.011 (PMC4028380 not cross-checked). Intermittent rescue benzodiazepines should be documented and are generally not an exclusion. **[cite — verify]**
- **Perucca E, French JA, Aljandeel G, et al. (2024).** "Which terms should be used to describe medications used in the treatment of seizure disorders? An ILAE position paper." *Epilepsia* 65(3):533–541. DOI 10.1111/epi.17877. Recommends "antiseizure medications". **[cite]**
- **Pina-Garza JE, Chez M, Cloyd J, et al. (2024).** "Outpatient management of prolonged seizures and seizure clusters to prevent progression to a higher-level emergency: consensus recommendations of an expert working group." *Epileptic Disord* 26(4):484–497. DOI 10.1002/epd2.20243. Proposes "REST medication" (prolonged seizure) and "acute cluster treatment" for what was called rescue treatment, and defines a seizure cluster as an increase over the patient's usual pattern. **[cite — verify]** (read from the working group's PDF <https://epi-care.eu/wp-content/uploads/2024/09/Pina-Garza-etal_2024_Experts-Consensus_Outpatient-management-of-prolonged-seizures-and-seizure-clusters-1.pdf>; confirm journal and DOI). Extra detector (D20): `--ext-detector rescue-if` keeps home PRN and drops instructional if-clauses / inpatient PRN.
- **Epilepsy Foundation, Seizure rescue therapies.** <https://www.epilepsy.com/treatment/seizure-rescue-therapies>. Rescue therapy is used as needed and does not replace daily seizure medication. **[background]**
- **Beniczky S, Trinka E, Wirrell E, et al. (2025).** "Updated classification of epileptic seizures: position paper of the International League Against Epilepsy." *Epilepsia* 66(6):1804–1823. DOI 10.1111/epi.18338. <https://www.ilae.org/guidelines/definition-and-classification/updated-classification-of-epileptic-seizures-2025>. Four classes, 21 seizure types, "consciousness" replaces "awareness" as a classifier (relevant to SCOPE_DECISIONS D1). **[cite]**

### Role placements — RAG, O codes, ConText ablation (2026-10-07, D21)
- **Beniczky S et al. (2017).** "Standardized computer-based organized reporting of EEG: SCORE – Second version." *Clin Neurophysiol* 128(11):2334–2346. **[cite]** — SCORE labels attached after EEG findings are extracted (`--export-codes`). Not a gazetteer in E.
- **Sahoo SS et al. (2014).** "Epilepsy and seizure ontology: towards an epilepsy informatics infrastructure." *JAMIA* 21(1):82–89. **[cite]** — EpSO class labels on ILAE enums after extract. EPIO remains the O retriever. Not extra trigger strings in `rules/fields/`.
- **ICD-10-CM G40.x** (CMS/NCHS). Category-level cohort/billing export only. ILAE DRE is not mapped to ICD “intractable.” Retrieval still deferred (SCOPE D3).
- **Orphanet / ORDO.** Rare-syndrome ids when the extracted etiology already names a disease. Not a seizure-type filler. Retrieval still deferred (SCOPE D5).
- Contract: `docs/ROLE_PLACEMENTS.md`. Tests: `tests/test_role_placements.py`.

## 8. Dual-reader, hybrid, and grounding papers (manuscript [17]–[29])

These are **[cite]** in `writing/MedAI_EPI_Manuscript_LEO.md`. Role: precedents, not LEO mechanisms we invented. Full matrix: `writing/LEO_LITERATURE_MAP.md`. What we take vs refuse: `writing/contributions.md` §8.

- **Khan MA, et al. (2025).** Collaborative LLMs for living systematic reviews. *JAMIA* 32(4):638–647. doi:10.1093/jamia/ocae325. **[cite]** Closest C2 precedent (concordant 0.94 vs discordant 0.41–0.50). Two LLMs; discordant → cross-critique. We take the split; we do **not** add a third-model critique or resolve clashes.
- **Alwakeel M, et al. (2025).** LLMs for PE registry abstraction. AMAI 2025, LNCS 16206:206–215. doi:10.1007/978-3-032-09569-5_21. **[cite]** Source of the field term **concordant PPV** (precision among cells where both readers agree). Their concordant PPV ≥0.90; discordant share <4%. LEO C2 is the same quantity (0.835 on F-S agree claims; research extract 0.866). Our review share is 0.56 (heterogeneous readers). Do not treat that gap as a failed gate.
- **Courvoisier DS, et al. (2026).** Multimodel abstract classification. *Res Synth Methods* 17(2):365–377. doi:10.1017/rsm.2025.10054. **[cite]** k-of-n withhold; >95% accuracy on ≥85% of abstracts. Do **not** say “exceeded a human gold standard” as our paraphrase of the title. We stay 2-of-2; we do not add 5–7 LLMs.
- **Wittlinger S, et al. (2026).** Multi-LLM disagreement as a detector of human annotation errors. *medRxiv* [Preprint]. doi:10.64898/2026.05.04.26352392. **[cite]** Four LLMs (not five). Disagreement to hunt **gold** errors. Not run on F-S; the 11 research-extract misses (82−71) are the place.
- **Mahbub M, et al. (2026).** Multi-stage validation framework. arXiv:2604.06028 [Preprint]. **[cite]** Rules + LLM + judge LLM + selective review. Closest *system* analogue. We do **not** add a judge LLM.
- **Schmidt L, et al. (2026).** Automating clinical phenotyping. *Commun Med* 6:77. doi:10.1038/s43856-025-01337-0. **[cite]** Rules vs GPT-4 in Crohn’s. Two tables give different F1 bands; do not quote a single F1 without the evaluation level.
- **Wang B, et al. (2026).** SDoH rules vs LLM, late-fusion ensemble. *JMIR Med Inform* 14:e89534. doi:10.2196/89534. **[cite]** Resolves clash by ensemble. We keep clash visible (D17).
- **Oh IY, et al. (2025).** AD phenotype extraction. *npj Dement* 1:37. doi:10.1038/s44400-025-00043-x. **[cite]** Rules median precision 0.97; GPT-4 F1 0.98. Do not swap those numbers.
- **Gero Z, et al. (2023).** Self-verification for clinical IE. ICML IMLH workshop; arXiv:2306.00024. **[cite]** Provenance span + self-check. We require a quote; we do not add a self-verify generation loop.
- **Windisch P, et al. (2026).** Verbatim evidence requirements. *medRxiv* [Preprint]. doi:10.64898/2026.03.03.26346690. **[cite]** 83–91% quotes valid, only 48–79% semantically supported. Precedent for C4 caveat and `--quote-entail` (default off).
- **Swaminathan A, et al. (2023).** Selective prediction for unstructured clinical data. *JAMIA* 31(1):188–197. doi:10.1093/jamia/ocad182. **[cite]** Abstention 0–97% (depression), 5–43% (GBM/colorectal); cost −58% to +9%. We report accept/review share (0.41/0.56). We do **not** claim cost. The “57–95% less manual abstraction” figure is **not** in this paper.
- **Chung P, Swaminathan A, et al. (2026).** VeriFact. *NEJM AI* 3(1). doi:10.1056/AIdbp2500418. **[cite]** 93.2% agreement with clinicians on whether a generated statement is supported by the EHR. Same job as `--quote-entail`. Scored on F-S L1C (EVAL 10.49); default stays off.

---

## Status legend

- **[cite]** — needs to appear in manuscript reference list
- **[cite — verify]** — needs BibTeX / DOI / venue confirmation before manuscript submission
- **[tool]** — cite in Methods (URL + brief version note is often sufficient)
- **[background]** — footnote-level; include if space allows

- **Fonferko-Shadrach B et al. (2024).** "Annotation of epilepsy clinic letters for natural language processing." *J Biomed Semantics*. https://link.springer.com/article/10.1186/s13326-024-00316-z. The 200 **synthetic** letters, annotations and guidelines are on Zenodo (10.5281/zenodo.8381079; JSON annotations 10.5281/zenodo.8356493). ExECT v2 validation: per-item F1 0.87, per-letter 0.90; seizure frequency 0.66 / 0.68; human inter-annotator F1 0.73. Used in `docs/EXECT_EPEXTRA_PARITY.md` §3. Figures read from the search-result abstract and table text on 2026-10-01; re-check against the paper before submission. Leftover E skip cues (2026-10-07): `pending`, `not yet obtained/performed`, `to be scheduled/arranged` — skip hypothetical or unavailable EEG studies. Already had consider / may / not available.

## Update discipline

When a new corpus, tool, or paper is used in the pipeline, add it here in the same session — do not defer. If the reference is provisional, flag `[cite — verify]` so the manuscript editor sweeps it before submission.
