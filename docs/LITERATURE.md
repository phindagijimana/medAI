# Literature

Papers and standards LEO cites. Full lab bibliography with leftover-rule notes: `docs/REFERENCES.md` in the repo. Nothing here is a claim we ran the other group’s weights.

## How to read a citation here

| We take | We do not |
|---|---|
| Concordant vs discordant split [Khan; Alwakeel] | A third-model critique or ensemble that hides the clash |
| Quote must appear in the note [Gero; Windisch; VeriFact] | “Quote present ⇒ value true”; `--quote-entail` stays off |
| ExECT / MedCAT / ConText as E’s lineage | Loading cTAKES, CLAMP, or Xie/Decker checkpoints into E |
| ILAE 2017 enums and Kwan 2010 DRE language | ILAE 2025 as the shipped classification (scoped, not default) |
| Ontology codes after extract [HPO; EPIO; EpSO; SCORE] | ICD/Orphanet/SCORE as extra trigger strings in E |

## Dual-reader and grounding

- **Khan MA, et al. (2025).** Collaborative LLMs for living systematic reviews. *JAMIA* 32(4):638–647. [doi:10.1093/jamia/ocae325](https://doi.org/10.1093/jamia/ocae325). Concordant 0.94 vs discordant 0.41–0.50. We take the split, not the cross-critique.
- **Alwakeel M, et al. (2025).** LLMs for PE registry abstraction. AMAI 2025, LNCS 16206:206–215. [doi:10.1007/978-3-032-09569-5_21](https://doi.org/10.1007/978-3-032-09569-5_21). Source of the term **concordant PPV**.
- **Courvoisier DS, et al. (2026).** Multimodel abstract classification. *Res Synth Methods* 17(2):365–377. [doi:10.1017/rsm.2025.10054](https://doi.org/10.1017/rsm.2025.10054). We stay 2-of-2 readers.
- **Wittlinger S, et al. (2026).** Multi-LLM disagreement as a detector of human annotation errors. *medRxiv* [Preprint]. [doi:10.64898/2026.05.04.26352392](https://doi.org/10.64898/2026.05.04.26352392). We use disagreement to list extract misses, not to rewrite gold.
- **Mahbub M, et al. (2026).** Multi-stage validation framework. arXiv:2604.06028 [Preprint]. Rules + LLM + judge. Closest system analogue; we do not add a judge LLM.
- **Schmidt L, et al. (2026).** Automating clinical phenotyping. *Commun Med* 6:77. [doi:10.1038/s43856-025-01337-0](https://doi.org/10.1038/s43856-025-01337-0).
- **Wang B, et al. (2026).** SDoH rules vs LLM, late-fusion ensemble. *JMIR Med Inform* 14:e89534. [doi:10.2196/89534](https://doi.org/10.2196/89534). They resolve clash; D17 leaves it visible.
- **Oh IY, et al. (2025).** AD phenotype extraction. *npj Dement* 1:37. [doi:10.1038/s44400-025-00043-x](https://doi.org/10.1038/s44400-025-00043-x).
- **Gero Z, et al. (2023).** Self-verification for clinical IE. ICML IMLH; arXiv:2306.00024. We require a quote; no self-verify loop.
- **Windisch P, et al. (2026).** Verbatim evidence requirements. *medRxiv* [Preprint]. [doi:10.64898/2026.03.03.26346690](https://doi.org/10.64898/2026.03.03.26346690). Quotes can be present and still unsupported.
- **Swaminathan A, et al. (2023).** Selective prediction for unstructured clinical data. *JAMIA* 31(1):188–197. [doi:10.1093/jamia/ocad182](https://doi.org/10.1093/jamia/ocad182). Abstention / review share; we do not claim cost savings.
- **Chung P, Swaminathan A, et al. (2026).** VeriFact. *NEJM AI* 3(1). [doi:10.1056/AIdbp2500418](https://doi.org/10.1056/AIdbp2500418). Whether a statement is supported by the record — same job as `--quote-entail` (default off).

## Epilepsy letters, ExECT, and MedCAT

- **Fonferko-Shadrach B, et al. (2019).** ExECT. *BMJ Open* 9(4):e023232. Rule vocabulary transplanted into EpExtra.
- **Fonferko-Shadrach B, et al. (2024).** Annotation of epilepsy clinic letters for NLP. *J Biomed Semantics* 15(1):17. [doi:10.1186/s13326-024-00316-z](https://doi.org/10.1186/s13326-024-00316-z). Primary gold; 200 **synthetic** clinician-authored letters (Zenodo [10.5281/zenodo.8381079](https://doi.org/10.5281/zenodo.8381079), JSON [10.5281/zenodo.8356493](https://doi.org/10.5281/zenodo.8356493)).
- **Cui L, et al. (2014).** PEEP / complex epilepsy phenotype extraction. *J Biomed Inform* 51:272–279. [doi:10.1016/j.jbi.2014.06.006](https://doi.org/10.1016/j.jbi.2014.06.006). Electrode-to-location rule; not a LEO baseline (EMU summaries).
- **Kraljevic Z, et al. (2021).** MedCAT. *Artif Intell Med* 117:102083. Concept annotation inside E.

## ILAE, DRE, and medications

- **Fisher RS, et al. (2017).** Operational classification of seizure types. *Epilepsia* 58(4):522–530.
- **Scheffer IE, et al. (2017).** ILAE classification of the epilepsies. *Epilepsia* 58(4):512–521.
- **Berg AT, et al. (2010).** Revised terminology 2005–2009. *Epilepsia* 51(4):676–685. Historical names E still maps.
- **Beniczky S, et al. (2025).** Updated classification of epileptic seizures. *Epilepsia* 66(6):1804–1823. [doi:10.1111/epi.18338](https://doi.org/10.1111/epi.18338). Scoped; shipped enums stay 2017.
- **Kwan P, Brodie MJ (2000).** Early identification of refractory epilepsy. *NEJM* 342(5):314–319.
- **Kwan P, et al. (2010).** Definition of drug resistant epilepsy. *Epilepsia* 51(6):1069–1077.
- **Perucca E, et al. (2024).** Terms for medications in seizure disorders (ASM). *Epilepsia* 65(3):533–541. [doi:10.1111/epi.17877](https://doi.org/10.1111/epi.17877).
- **Loring DW, et al. (2011).** NINDS epilepsy common data elements. *Epilepsia* 52:1186–1191. [doi:10.1111/j.1528-1167.2011.03018.x](https://doi.org/10.1111/j.1528-1167.2011.03018.x).
- **Fertig E, et al. (2014).** Inclusion/exclusion for epilepsy trials. *Epilepsy Res* 108(5):825–832. [doi:10.1016/j.eplepsyres.2014.02.011](https://doi.org/10.1016/j.eplepsyres.2014.02.011). Rescue benzodiazepines.
- **Pina-Garza JE, et al. (2024).** Outpatient management of prolonged seizures and clusters. *Epileptic Disord* 26(4):484–497. [doi:10.1002/epd2.20243](https://doi.org/10.1002/epd2.20243).

## Frequency, seizure type, and EEG (jobs, not loaded weights)

- **Xie K, et al. (2022).** Extracting seizure frequency from clinic notes. *JAMIA* 29(5):873–881.
- **Xie K, et al. (2023).** Generalization of finetuned transformers. *JAMIA Open* 6(3):ooad070. Also Xie et al., *Epilepsia* 2023;64(7):1900–1909 (seizure freedom).
- **Decker BM, et al. (2022).** NLP for seizure types and frequencies. *Seizure* 101:48–51.
- **Abeysinghe R, et al. (2025).** Pretrained LMs for seizure frequency. *npj Digit Med* 8:208.
- **Barlow S, et al. (2026).** Synthetic records for seizure-freedom identification. *Proc BioNLP 2026*:20–30. [doi:10.18653/v1/2026.bionlp-1.3](https://doi.org/10.18653/v1/2026.bionlp-1.3). Seizure-freedom only; do not generalise to all phenotypes.
- **Hirsch LJ, et al. (2021).** ACNS critical-care EEG terminology. *J Clin Neurophysiol* 38(1):1–29. [doi:10.1097/WNP.0000000000000806](https://doi.org/10.1097/WNP.0000000000000806).
- **Maldonado R, Harabagiu SM (2019).** Active deep learning on EEG reports. *J Biomed Inform.* PMC6922091.
- **Maldonado R, Harabagiu SM (2020).** NLP of EEG reports. *LREC 2020*. ACL Anthology 2020.lrec-1.276.
- **Beniczky S, et al. (2017).** SCORE – second version. *Clin Neurophysiol* 128(11):2334–2346. Export labels only, not E gazetteers.

## Ontologies and codes

- **Köhler S, et al. (2021).** Human Phenotype Ontology in 2021. *Nucleic Acids Res* 49(D1):D1207–D1217.
- **Sargsyan A, et al. (2023).** The Epilepsy Ontology (EPIO). *Bioinform Adv* 3(1):vbad033. [doi:10.1093/bioadv/vbad033](https://doi.org/10.1093/bioadv/vbad033).
- **Sahoo SS, et al. (2014).** Epilepsy and seizure ontology (EpSO). *JAMIA* 21(1):82–89.
- **NLM RxNorm.** <https://www.nlm.nih.gov/research/umls/rxnorm/>
- **NLM UMLS.** <https://www.nlm.nih.gov/research/umls/>
- ICD-10-CM G40.x (CMS/NCHS) and Orphanet/ORDO: post-extract export only.

## Clinical NLP methods inside or next to E

- **Chapman WW, et al. (2001).** NegEx. *J Biomed Inform* 34(5):301–310.
- **Harkema H, et al. (2009).** ConText. *J Biomed Inform* 42(5):839–851.
- **Eyre H, et al. (2021).** medspaCy. *AMIA Symp.*
- **Uzuner Ö, Solti I, Cadag E (2010).** i2b2 medications. *JAMIA* 17(5):514–518.
- **Savova GK, et al. (2010).** cTAKES. *JAMIA* 17(5):507–513. Method cited; Java UIMA not loaded. Opt-in `--ext-detector ctakes` is a Python lexicon + NegEx sidecar.
- **Soysal E, et al. (2018).** CLAMP. *JAMIA* 25(3):331–336. Comparator, not loaded.
- **Aronson AR, Lang FM (2010).** MetaMap. *JAMIA* 17(3):229–236. Closer to O than to E.

## Language model

- **Christophe C, Kanithi PK, Raha T, Khan S, Pimentel MAF (2024).** Med42-v2: A Suite of Clinical LLMs. arXiv:2408.06142. Shipped reader: [Llama3-Med42-8B](https://huggingface.co/m42-health/Llama3-Med42-8B).
- **Alsentzer E, et al. (2019).** Publicly available clinical BERT embeddings. *NAACL Clinical NLP.* Cited; not a shipped `--ext-detector`.

## Reporting

- **Gallifant J, et al. (2025).** TRIPOD-LLM. *Nat Med* 31(1):60–69. [doi:10.1038/s41591-024-03425-5](https://doi.org/10.1038/s41591-024-03425-5).
- **Collins GS, et al. (2024).** TRIPOD+AI. *BMJ* 385:e078378. [doi:10.1136/bmj-2023-078378](https://doi.org/10.1136/bmj-2023-078378).

## Also used (tools / background)

- Walonoski et al. (2018), Synthea — evaluated and discarded for narrative notes.
- OpenAI models — synthetic generation / silver labels only; never the clinical extractor.
- HIPAA Safe Harbor de-identification guidance (HHS, 2012).
- PyTorch; Hugging Face transformers / PEFT; Pydantic; Flask.

Reasoning that uses these papers: [Theory and Science](THEORY.md).
