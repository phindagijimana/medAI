# MedAI-EPI References

Consolidated bibliography of papers, tools, corpora, and standards that inform the MedAI-EPI project. Grouped by role. Entries flagged **[cite]** should be included in the manuscript reference list; **[tool]** entries need only a URL/citation in Methods; **[background]** may be footnoted or omitted depending on space.

---

## 1. Corpora & benchmarks

### Fonferko-Shadrach
- **Fonferko-Shadrach B et al. (2023).** "A dataset of 200 structured epilepsy clinic letters annotated with clinical information." *Scientific Data* 10:459. DOI 10.1038/s41597-023-02351-4. **[cite]**
- Zenodo record: <https://zenodo.org/records/8060906>
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

### Barlow et al. — synthetic epilepsy precedent
- **Barlow S et al. (2026).** BioNLP Workshop paper: "Fine-tuning language models with synthetic epilepsy clinical notes." *(Reference to be resolved to final BioNLP proceedings.)* **[cite]**
- Role: precedent that synthetic data can match or exceed real for epilepsy phenotype extraction.

---

## 2. Ontology, classification & clinical definitions

### ILAE 2017 classification
- **Fisher RS et al. (2017).** "Operational classification of seizure types by the International League Against Epilepsy: Position Paper of the ILAE Commission for Classification and Terminology." *Epilepsia* 58(4):522–530. **[cite]**
- **Scheffer IE et al. (2017).** "ILAE classification of the epilepsies: Position paper of the ILAE Commission for Classification and Terminology." *Epilepsia* 58(4):512–521. **[cite]**
- Role: canonical enum values in `schema/enums.py`; drives the ILAE modernization stage of preprocessing.

### Drug-resistant epilepsy
- **Kwan P, Brodie MJ (2000).** "Early identification of refractory epilepsy." *NEJM* 342(5):314–319. **[cite]**
- **Kwan P et al. (2010).** "Definition of drug resistant epilepsy: consensus proposal by the ad hoc Task Force of the ILAE Commission on Therapeutic Strategies." *Epilepsia* 51(6):1069–1077. **[cite]**
- Role: DRE definition informing synthetic patient sampler distribution and downstream drug-resistance utility demo.

### SNOMED CT / UMLS
- **NLM Unified Medical Language System (UMLS)** — Metathesaurus and semantic types. **[tool]**
- URL: <https://www.nlm.nih.gov/research/umls/>
- Role: CUI seed for MedCAT CDB; Phase 1c/1d enrichment.

### HPO / EPIO
- **Human Phenotype Ontology (HPO).** Köhler S et al. (2021). "The Human Phenotype Ontology in 2021." *Nucleic Acids Research* 49(D1):D1207–D1217. **[cite]**
- **EPIO** — Epilepsy Ontology. Sargsyan A et al. (2020). "EpiOnt: An ontology for epilepsy diseases and treatments." *(Reference to be verified.)* **[cite]**

---

## 3. Extraction methodology (prior art)

### ExECT-V2
- **Fonferko-Shadrach B et al. (2019).** "Using natural language processing to extract structured epilepsy data from unstructured clinic letters: development and validation of the ExECT (extraction of epilepsy clinical text) system." *BMJ Open* 9(4):e023232. **[cite]**
- **ExECT-V2 extension** referenced in Fonferko-Shadrach 2023 companion release.
- Role: rule vocabulary transplanted to Python; MedCAT+Rules pipeline.

### MedCAT
- **Kraljevic Z et al. (2021).** "Multi-domain clinical natural language processing with MedCAT: The Medical Concept Annotation Toolkit." *Artificial Intelligence in Medicine* 117:102083. **[cite]**
- GitHub: <https://github.com/CogStack/MedCAT>
- Role: concept annotation + MetaCAT contextual classification.

### medspaCy ConText
- **Chapman WW et al. (2013).** "Extending the ConText Algorithm to Distinguish Negated, Speculated, and Historical Contexts in Discharge Summaries." *Journal of Biomedical Informatics* 46(5):919–923. **[cite]**
- **Eyre H et al. (2021).** "Launching into Clinical Space with medspaCy: A New Clinical Text Processing Toolkit in Python." *AMIA Symposium.* **[cite]**
- Role: negation, uncertainty, experiencer, temporality classification.

---

## 4. Language models & fine-tuning

### Med42
- **Med42 (M42 Health, 2024).** "Med42: A clinical LLM based on Llama 3." Model card: <https://huggingface.co/m42-health/Llama3-Med42-8B>. **[cite]**
- Role: primary open-weights arm; LoRA fine-tuning target.

### Clinical BERT / BioClinicalBERT
- **Alsentzer E et al. (2019).** "Publicly Available Clinical BERT Embeddings." *NAACL Workshop on Clinical NLP.* **[cite]**
- Role: cited as baseline; B1 BioClinicalBERT scaffold in the repo.

### Li 2021 — MIMIC clinical BERT variants
- **Li Y et al. (2021).** "A comparative study of pretrained language models for automated essay scoring with adversarial examples." *(Verify — user referenced "Li 2021" for prior epilepsy phenotyping.)* **[cite — verify]**
- Role: prior-art citation in Related Work.

### Goldenholz 2025 — seizure freedom
- **Goldenholz DM et al. (2025).** *(Verify — user referenced for seizure-freedom identification demo.)* **[cite — verify]**
- Role: motivates the utility demo #2 (seizure freedom identification from extracted phenotype).

### DeepSeek / open baselines
- **DeepSeek AI (2024).** "DeepSeek-V2: A strong, economical, and efficient mixture-of-experts language model." Technical report. **[background]**
- Role: alternative open backbone for the multi-model backend.

---

## 5. Reporting standards

### TRIPOD-LLM
- **Cabitza F et al. (2024).** "TRIPOD-LLM: Reporting Guideline for Studies Using Large Language Models in Healthcare." *(To be finalized when published.)* **[cite]**
- Role: manuscript checklist compliance.

### TRIPOD-AI (predecessor)
- **Collins GS et al. (2024).** "TRIPOD+AI statement: updated guidance for reporting clinical prediction models that use regression or machine learning methods." *BMJ* 385:e078378. **[cite]**
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
- **Loring DW et al. (2011).** "Common data elements in epilepsy research: development and implementation of the NINDS Epilepsy CDE Project." *Epilepsia* 52:1186-91. DOI 10.1111/j.1528-1167.2011.03018.x. NINDS CDE site: <https://www.commondataelements.ninds.nih.gov/epilepsy>. The CDEs keep an antiepileptic-drug log (name, formulation, schedule, dose, start and end dates, ongoing status, reason for discontinuation) separate from a non-AED medication log. **[cite — verify]** (field list read from the MDM-Portal copy <https://medical-data-models.org/14646>, not from the NINDS CRF itself).
- **Inclusion and exclusion criteria for epilepsy clinical trials: recommendations from the April 30, 2011 NINDS workshop.** PMC4028380. Intermittent rescue benzodiazepines should be documented and are generally not an exclusion. **[cite — verify]**
- **ILAE Nomenclature Task Force (position paper; year to confirm).** "Which terms should be used to describe medications used in the treatment of seizure disorders? An ILAE position paper." *Epilepsia*. DOI 10.1111/epi.17877. Recommends "antiseizure medications". **[cite — verify authors and year]**
- **Pina-Garza JE et al. (2024).** "Outpatient management of prolonged seizures and seizure clusters to prevent progression to a higher-level emergency: consensus recommendations of an expert working group." Proposes "REST medication" (prolonged seizure) and "acute cluster treatment" for what was called rescue treatment, and defines a seizure cluster as an increase over the patient's usual pattern. **[cite — verify]** (read from the working group's PDF <https://epi-care.eu/wp-content/uploads/2024/09/Pina-Garza-etal_2024_Experts-Consensus_Outpatient-management-of-prolonged-seizures-and-seizure-clusters-1.pdf>; confirm journal and DOI).
- **Epilepsy Foundation, Seizure rescue therapies.** <https://www.epilepsy.com/treatment/seizure-rescue-therapies>. Rescue therapy is used as needed and does not replace daily seizure medication. **[background]**
- **ILAE (2025).** "Updated classification of epileptic seizures: position paper of the ILAE." <https://www.ilae.org/guidelines/definition-and-classification/updated-classification-of-epileptic-seizures-2025>. Four classes, 21 seizure types, "consciousness" replaces "awareness" as a classifier (relevant to SCOPE_DECISIONS D1). **[cite]**

## Status legend

- **[cite]** — needs to appear in manuscript reference list
- **[cite — verify]** — needs BibTeX / DOI / venue confirmation before manuscript submission
- **[tool]** — cite in Methods (URL + brief version note is often sufficient)
- **[background]** — footnote-level; include if space allows

- **Fonferko-Shadrach B et al. (2024).** "Annotation of epilepsy clinic letters for natural language processing." *J Biomed Semantics*. https://link.springer.com/article/10.1186/s13326-024-00316-z. The 200 **synthetic** letters, annotations and guidelines are on Zenodo (10.5281/zenodo.8381079; JSON annotations 10.5281/zenodo.8356493). ExECT v2 validation: per-item F1 0.87, per-letter 0.90; seizure frequency 0.66 / 0.68; human inter-annotator F1 0.73. Used in `docs/EXECT_EPEXTRA_PARITY.md` §3. Figures read from the search-result abstract and table text on 2026-10-01; re-check against the paper before submission.

## Update discipline

When a new corpus, tool, or paper is used in the pipeline, add it here in the same session — do not defer. If the reference is provisional, flag `[cite — verify]` so the manuscript editor sweeps it before submission.
