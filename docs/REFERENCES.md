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

## Status legend

- **[cite]** — needs to appear in manuscript reference list
- **[cite — verify]** — needs BibTeX / DOI / venue confirmation before manuscript submission
- **[tool]** — cite in Methods (URL + brief version note is often sufficient)
- **[background]** — footnote-level; include if space allows

## Update discipline

When a new corpus, tool, or paper is used in the pipeline, add it here in the same session — do not defer. If the reference is provisional, flag `[cite — verify]` so the manuscript editor sweeps it before submission.
