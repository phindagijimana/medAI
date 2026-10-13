# Ontology and terminology sources (LEO pipeline)

Last updated 2026-10-01. This page lists every external vocabulary the LEO
pipeline (LLM + EpExtra + Ontology) codes against: which release, where it came
from, the licence, what we use it for, and the reference to cite. Exact files
and SHA-256 checksums are in `data/ontologies/MANIFEST.json`
(`scripts/fetch_ontologies.py` downloads them).

## 1. Pinned releases

| System | Release tag | Source | Licence | Used for |
|---|---|---|---|---|
| SNOMED CT US Edition | `snomed:2026-09-01` | NLM UMLS Terminology Services (UTS), RF2 snapshot | UMLS Metathesaurus Licence + SNOMED CT Affiliate terms; **do not redistribute** | Disorder/finding subset for candidates; checking curated SCTIDs |
| RxNorm | `rxnorm:2026-09-08` | NLM UTS, `RxNorm_full_09082026.zip` | UMLS Metathesaurus Licence; **do not redistribute** | Antiseizure-drug lexicon and ingredient RXCUIs |
| UMLS Metathesaurus (REST) | `current` (2026AA at fetch time) | UTS REST API `https://uts-ws.nlm.nih.gov/rest` | UMLS Metathesaurus Licence | CUI ↔ SCTID resolution; synonym enrichment |
| HPO | `2026-09-01` | `obophenotype/human-phenotype-ontology` GitHub release | Open (HPO licence, attribution) | Seizure phenotype subset |
| MONDO | `2026-09-01` | OBO PURL `mondo.obo` | CC BY 4.0 | Epilepsy disease subset |
| EPIO | `git:dc9f9b1` | `SCAI-BIO/EpilepsyOntology` (`EPIO_merged.owl`) | CC BY 4.0 | Epilepsy concepts not in HPO/MONDO |
| WHO ATC | ATC rows inside RxNorm 2026-09-08 (`SAB=ATC`) | WHO Collaborating Centre for Drug Statistics Methodology | ATC/DDD Index terms of use | Choosing the drugs: N03A Antiepileptics |
| ILAE classification | 2017 operational classification (see 4.1) | Published papers | — | Enum values for seizure and epilepsy type |

Post-extract export maps (opt-in `--export-codes`, not retrieval sources, not E gazetteers): ICD-10-CM G40.x category, Orphanet ORPHA ids for named syndromes, SCORE labels for already-extracted EEG findings, EpSO class labels for ILAE enums. EPIO remains the live EpSO-family retriever. See `docs/ROLE_PLACEMENTS.md` and `services/o_code_maps.py`. SCOPE D3–D5 *retrieval* is still deferred.

Licensed content (SNOMED CT, RxNorm, UMLS) stays under `data/ontologies/`,
which git ignores except `MANIFEST.json`. Files that quote SNOMED descriptions
(e.g. `data/ontologies/curated_code_review.csv`) also stay there. The UMLS API
key is read from `UMLS_APIKEY` in `.env` and is never logged.

Index built by `services/ontology_loaders.py` (`INDEX_FORMAT = 3`): 2,328
terms — HPO 1,054, SNOMED CT 417, EPIO 414, MONDO 392, RxNorm 51.

## 2. How each source is used

### SNOMED CT (RF2)
* **Preferred term.** Labels are the US English preferred term: the synonym
  marked Preferred (`900000000000548007`) in the US English language refset
  (`900000000000509007`). Acceptable synonyms (`900000000000549004`) become
  synonyms. Before 2026-10-01 we used the FSN minus its semantic tag. [S1, S2]
* **Subset.** Only `(disorder)` and `(finding)` concepts below the epilepsy
  and seizure roots are kept (`SNOMED_KEEP_TAGS`).
* **Checking curated codes.** `snomed_lookup()` reports whether each curated
  SCTID exists, whether it is active, its FSN and preferred term, and its
  REPLACED BY / SAME AS association targets
  (`900000000000526001` / `900000000000527005`). We do **not** apply
  REPLACED BY automatically. In this release some targets change the meaning,
  for example "Epileptic automatism" → "Absence seizure".

### RxNorm and ATC
`scripts/build_asm_lexicon.py` generates `rules/asm_lexicon.py` (51
ingredients). The same table drives MedCAT drug detection, through
`MEDICATION_ONTOLOGY`, and RxNorm coding. [S3]
* **Included:**
  * ingredients under ATC **N03A Antiepileptics**, excluding combination
    products;
  * every drug already curated in `MEDICATION_ONTOLOGY`;
  * `EXTRA_INGREDIENTS` (below).
* **Normalising names.** Precise ingredients (`PIN`) are folded into their
  base ingredient (`IN`) via the `has_form`/`form_of` relations. For example,
  valproic acid (11118) folds into valproate (40254).
* **Brand names.** Only single-ingredient brands (`BN`) of four or more
  characters are kept, minus a short stoplist.
* **Gabapentin and pregabalin** have been ATC **N02BF Gabapentinoids** since
  the 2023 WHO alteration (gabapentin N03AX12→N02BF01, pregabalin
  N03AX16→N02BF02). They stay in the lexicon because they are curated ASMs.
  [S4, S5]
* **`EXTRA_INGREDIENTS`** are drugs with a US FDA seizure indication that
  ATC files outside N03A. Labels are from DailyMed and Drugs@FDA [S6–S8]:

| Ingredient | Role | FDA seizure indication |
|---|---|---|
| diazepam | rescue | Rectal gel and nasal spray: acute repetitive seizures / seizure clusters |
| midazolam | rescue | Nasal spray: seizure clusters. ATC keeps all midazolam forms in N05CD08 [S4] |
| lorazepam | rescue | Injection: status epilepticus |
| clorazepate | adjunct | Adjunctive therapy for partial seizures |
| acetazolamide | adjunct | Centrencephalic epilepsies |
| corticotropin (ACTH) | adjunct | Monotherapy for infantile spasms under 2 years [S7] |
| everolimus | adjunct | Afinitor Disperz: adjunct for TSC-associated partial-onset seizures, 2 years and older [S8] |

### UMLS
* **Resolving CUIs from SCTIDs.**
  `/search/current?inputType=sourceUi&sabs=SNOMEDCT_US`.
* **Synonym enrichment.**
  `/content/current/CUI/{cui}/atoms`, restricted to SNOMEDCT_US, RXNORM, MSH,
  HPO and ICD10CM, run by `scripts/enrich_ontology_from_umls.py` and
  `scripts/apply_umls_enrichment.py`.
* **Enrichment safeguards.** A patch is dropped if none of its synonyms
  shares a word with the entry. An SCTID is added only if it is active,
  shares a word with the entry, is not a `(situation)`, and was not removed
  in `data/curated/curated_code_corrections.csv`. [S9]

### HPO, MONDO, EPIO
OBO and OWL subsets below the epilepsy and seizure roots, used as candidate
terms. [S10–S12]

## 3. Curated code corrections (2026-10-01)

The curated `cui` and `sctid` values in `rules/epilepsy_ontology.py` were
written by hand and never checked against a release.
`services/curated_code_audit.py` checks each one for:
* existence and active status in SNOMED CT;
* duplicate codes within a group;
* word overlap with the SNOMED name;
* word overlap with the UMLS names of the CUI;
* RxNorm provenance matching the ingredient RXCUI.

The first audit found 79 issues. A full review of the codes the audit did
*not* flag found 8 more wrong ones, e.g. `MriFinding.tumor` → "prostate
neoplasm" and `MedicationStatus.current` → "drug treatment stopped".

* **Corrections.** All fixes are in `data/curated/curated_code_corrections.csv`
  (93 rows: 69 SNOMED, 24 CUI, 8 codes removed with no replacement). Each row
  gives the old and new code, the source, and the reason.
  `scripts/apply_curated_code_corrections.py` applies them:
  * it refuses any SCTID that is not active in `snomed:2026-09-01`;
  * it resolves new CUIs through UTS;
  * it adds a "corrected 2026-10-01" note to each entry's
    `source_provenance`.
* **Reviewed exceptions.** `data/curated/curated_code_reviewed.csv` lists four
  flags checked by hand and accepted, each with a reason. Example: Laterality
  `bilateral` = 51440002 "Right and left", which is SNOMED's bilateral
  qualifier.
* **Rules-only enums.** `MedicationStatus` moved to `RULES_ONLY_ENUMS`.
  SNOMED CT has no concepts for current, prior or failed drug status, and
  every curated code for it was wrong. Status was always set by regex rules.
* **Result.** The audit now reports 0 issues
  (`data/curated/curated_code_known_issues.json` is empty).
  `tests/test_curated_codes.py` fails if a correction is reverted, if a
  corrected-away code is emitted, or if a new issue appears.
* **Effect on extraction.** With the rebuilt MedCAT CDB (now the default at
  `data/medcat_cdb_epilepsy/`), EpExtra (B1′) micro-F1 is unchanged: 0.8064
  on F-S test 40 and 0.8192 on synth-v1 eval 100. One prediction changed,
  and it is now correct: EA0182 "fully conscious during the episodes" →
  awareness = aware. The old CDB is archived at
  `data/medcat_cdb_epilepsy_archive_20260930/`.

## 4. References

### 4.1 Classification and definitions
* [C1] Fisher RS, Cross JH, French JA, et al. Operational classification of seizure types by the International League Against Epilepsy: Position Paper of the ILAE Commission for Classification and Terminology. *Epilepsia*. 2017;58(4):522–530. doi:10.1111/epi.13670
* [C2] Scheffer IE, Berkovic S, Capovilla G, et al. ILAE classification of the epilepsies: Position paper of the ILAE Commission for Classification and Terminology. *Epilepsia*. 2017;58(4):512–521. doi:10.1111/epi.13709
* [C3] Beniczky S, Trinka E, Wirrell E, et al. Updated classification of epileptic seizures: Position paper of the International League Against Epilepsy. *Epilepsia*. Published online 23 April 2025. doi:10.1111/epi.18338. It keeps four classes and reduces 63 types to 21, among other changes. *Not yet adopted by our enums*, which follow 2017. https://www.ilae.org/guidelines/definition-and-classification/updated-classification-of-epileptic-seizures-2025
* [C4] Kwan P, Arzimanoglou A, Berg AT, et al. Definition of drug resistant epilepsy: consensus proposal by the ad hoc Task Force of the ILAE Commission on Therapeutic Strategies. *Epilepsia*. 2010;51(6):1069–1077. doi:10.1111/j.1528-1167.2009.02397.x

### 4.2 Terminologies and ontologies
* [S1] SNOMED International. *SNOMED CT Release File Specification*, §5.2.2.1 Language Reference Set. https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/reference-set-release-file-specification/5.2-reference-set-types/5.2.2.1-language-reference-set
* [S2] U.S. National Library of Medicine. *SNOMED CT United States Edition* (release 2026-09-01). https://www.nlm.nih.gov/healthit/snomedct/us_edition.html
* [S3] Nelson SJ, Zeng K, Kilbourne J, Powell T, Moore R. Normalized names for clinical drugs: RxNorm at 6 years. *J Am Med Inform Assoc*. 2011;18(4):441–448. doi:10.1136/amiajnl-2011-000116
* [S4] WHO Collaborating Centre for Drug Statistics Methodology. *ATC/DDD Index* (N02BF Gabapentinoids; N03A Antiepileptics). https://atcddd.fhi.no/atc_ddd_index/?code=N02BF
* [S5] WHO International Working Group for Drug Statistics Methodology. *Executive summary, 51st meeting* (March 2023): new ATC level N02BF; gabapentin, pregabalin and mirogabalin reclassified; oromucosal midazolam kept in N05CD08. https://cdn.who.int/media/docs/default-source/international-nonproprietary-names-(inn)/atc-ddd/51st_atc_ddd_executive_summary.pdf
* [S6] U.S. National Library of Medicine. *DailyMed* (FDA structured product labels for diazepam rectal gel/nasal spray, midazolam nasal spray, lorazepam injection, clorazepate, acetazolamide). https://dailymed.nlm.nih.gov/
* [S7] Acthar Gel (repository corticotropin injection) prescribing information, §1.1 Infantile Spasms. Revised 2/2024. https://www.accessdata.fda.gov/drugsatfda_docs/label/2024/008372s074lbl.pdf
* [S8] Afinitor / Afinitor Disperz (everolimus) prescribing information, §1.6 TSC-Associated Partial-Onset Seizures. https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=2150f73a-179b-4afc-b8ce-67c85cc72f04
* [S9] Bodenreider O. The Unified Medical Language System (UMLS): integrating biomedical terminology. *Nucleic Acids Res*. 2004;32(Database issue):D267–D270. doi:10.1093/nar/gkh061
* [S10] Gargano MA, Matentzoglu N, Coleman B, et al. The Human Phenotype Ontology in 2024: phenotypes around the world. *Nucleic Acids Res*. 2024;52(D1):D1333–D1346. doi:10.1093/nar/gkad1005
* [S11] Vasilevsky NA, Matentzoglu NA, Toro S, et al. Mondo: Unifying diseases for the world, by the world. *medRxiv*. 2022. doi:10.1101/2022.04.13.22273750
* [S12] Sargsyan A, Wegner P, Gebel S, et al. The Epilepsy Ontology: a community-based ontology tailored for semantic interoperability and text mining. *Bioinform Adv*. 2023;3(1):vbad033. doi:10.1093/bioadv/vbad033

### 4.3 Methods and tools
* [M1] Fonferko-Shadrach B, Lacey AS, Roberts A, et al. Using natural language processing to extract structured epilepsy data from unstructured clinic letters: development and validation of the ExECT (extraction of epilepsy clinical text) system. *BMJ Open*. 2019;9(4):e023232. doi:10.1136/bmjopen-2018-023232
* [M2] Kraljevic Z, Searle T, Shek A, et al. Multi-domain clinical natural language processing with MedCAT: the Medical Concept Annotation Toolkit. *Artif Intell Med*. 2021;117:102083. doi:10.1016/j.artmed.2021.102083
* [M3] Harkema H, Dowling JN, Thornblade T, Chapman WW. ConText: an algorithm for determining negation, experiencer, and temporal status from clinical reports. *J Biomed Inform*. 2009;42(5):839–851. doi:10.1016/j.jbi.2009.05.002
* [M4] Eyre H, Chapman AB, Peterson KS, et al. Launching into clinical space with medspaCy: a new clinical text processing toolkit in Python. *AMIA Annu Symp Proc*. 2021;2021:438–447.

* [M5] Christophe C, Kanithi PK, Raha T, Khan S, Pimentel MAF. Med42-v2: A Suite of Clinical LLMs. arXiv:2408.06142. 2024. Model used by LEO: `m42-health/Llama3-Med42-8B` (Llama-3-8B-Instruct base, June 2024). https://huggingface.co/m42-health/Llama3-Med42-8B

### 4.4 Standards and candidate resources (see `docs/ontology_resources.md`)
* [N1] NINDS Common Data Elements: Epilepsy (CRF modules incl. Classification of Seizures; revised 2017 for the ILAE classification). https://www.commondataelements.ninds.nih.gov/epilepsy
* [N2] Beniczky S, Aurlien H, Brøgger JC, et al. Standardized computer-based organized reporting of EEG: SCORE – Second version. *Clin Neurophysiol*. 2017;128(11):2334–2346. PMID 28838815. https://pubmed.ncbi.nlm.nih.gov/28838815/
* [N3] Hirsch LJ, Fong MWK, Leitinger M, et al. American Clinical Neurophysiology Society's Standardized Critical Care EEG Terminology: 2021 version. *J Clin Neurophysiol*. 2021;38(1):1–29.
* [E1] Sahoo SS, Lhatoo SD, Gupta DK, et al. Epilepsy and seizure ontology: towards an epilepsy informatics infrastructure for clinical research and patient care. *J Am Med Inform Assoc*. 2014;21(1):82–89. PMID 23686934. EpSO v3.1 (May 2025): https://bioportal.bioontology.org/ontologies/EPSO
* [E2] Orphanet Rare Disease Ontology (ORDO) and Orphadata Science files, CC BY 4.0. https://sciences.orphadata.com/ordo/

Citations were checked against PubMed, publisher pages, ILAE, WHOCC and FDA/DailyMed on 2026-10-01.
