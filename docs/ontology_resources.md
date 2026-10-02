# Ontology and terminology resources for LEO

Last updated 2026-10-01. This page explains each resource LEO uses, or could
use, in plain terms: what it is, who runs it, how big it is, what an ID looks
like, what it is good and bad at for epilepsy notes, and exactly how we use it.
`docs/ONTOLOGY_SOURCES.md` is the companion page with pinned releases,
licences, checksums and the full reference list. Bracketed tags like [S10]
point to that page.

## 0. Why LEO needs ontologies at all

LEO is **L**LM + **E**pExtra + **O**ntology. The rule is: *the LLM never
invents a code.* A deterministic retriever
(`services/ontology_candidates.py`) takes a mention such as "cenobamate" or
"mesial temporal sclerosis" and returns a short list of real concepts from
pinned releases. A concept is adopted only if its label or synonym matches the
mention exactly (`min_candidate_score = 0.9`); otherwise the claim keeps our
internal `MEDAI-ENUM` value and goes to review. Every claim records the
release it was coded against, so a result can be reproduced later.

The language model is **Med42-8B** (`m42-health/Llama3-Med42-8B`, the 8B model
of the Med42-v2 suite, built on Llama-3-8B-Instruct and released June 2024)
[M5]. It reads the sentence and decides assertion, experiencer, temporality
and which candidate fits. It does not produce identifiers.

Three kinds of resource are involved, and they are easy to confuse:

| Kind | What it gives us | Examples |
|---|---|---|
| **Terminology / ontology** (machine-readable concept lists with IDs) | The codes and labels we output | HPO, MONDO, EPIO, SNOMED CT, RxNorm |
| **Bridge** (maps between code systems) | Lets us go from one ID to another | UMLS, ATC (inside RxNorm) |
| **Standard / guideline** (a published definition, not a downloadable list) | Tells us what our enum values *mean* | ILAE classifications, NINDS CDEs, ACNS/SCORE EEG terminology |

## 1. The five code systems LEO outputs

Counts below were measured from our pinned files on 2026-10-01.

### 1.1 HPO: Human Phenotype Ontology
* **What it is.** A standard vocabulary of phenotypic abnormalities, the
  things a clinician observes in a patient, arranged as a hierarchy (a
  directed acyclic graph). "Photosensitive myoclonic seizure" sits under
  "Myoclonic seizure", under "Seizure", under "Abnormality of the nervous
  system". [S10]
* **Who runs it.** The Monarch Initiative, with a large clinical community.
  Released on GitHub several times a year.
* **Size and IDs.** 20,482 terms in our release (`2026-09-01`). IDs are
  `HP:` plus seven digits, e.g. `HP:0001250` = Seizure. Each term has a
  label, synonyms, a definition, parents, and sometimes cross-references to
  UMLS or SNOMED.
* **Good at.** Symptoms and signs, including most seizure semiology
  (focal, myoclonic, atonic, tonic-clonic, febrile), EEG and MRI findings
  phrased as abnormalities, and developmental and neurological comorbidities.
  Its annotations power rare-disease diagnosis tools, so HPO IDs are widely
  recognised.
* **Weak at.** Drugs, procedures, documents, and negative or normal findings
  (it describes abnormalities only). Its seizure hierarchy predates the ILAE
  2017 names, so "focal impaired awareness seizure" may only match through
  synonyms.
* **How we use it.** We keep the part of the hierarchy under the seizure,
  epilepsy and nervous-system-abnormality roots: **1,054 terms** in the
  candidate index. A mention that matches an HPO label or synonym exactly is
  coded `HP:…`.

### 1.2 MONDO: Monarch Disease Ontology
* **What it is.** One disease ontology that merges many overlapping disease
  lists (OMIM, Orphanet, DOID, NCIt, ICD and others) so that the same disease
  has one ID. It records which source each equivalence came from. [S11]
* **Who runs it.** Monarch Initiative.
* **Size and IDs.** 63,278 terms. IDs are `MONDO:` plus seven digits, e.g.
  `MONDO:0005027` = epilepsy. The definition of that term comes from NCIt.
* **Good at.** Named diseases and syndromes (Dravet syndrome, tuberous
  sclerosis, Rasmussen encephalitis) and mapping between disease coding
  systems.
* **Weak at.** Symptoms, findings, drugs. It says *what disease*, not *what
  was seen in this patient*.
* **How we use it.** The epilepsy and related-syndrome branch: **392 terms**.
  Used for epilepsy type, syndrome and etiology mentions.

### 1.3 EPIO: Epilepsy Ontology
* **What it is.** An ontology built for epilepsy specifically, following the
  ILAE classification and re-using HPO and MONDO classes. It adds epilepsy
  concepts the general ontologies lack: classification terms, assessment
  scales, comorbidity and treatment concepts. It follows OBO Foundry
  practice (BFO upper ontology). [S12]
* **Who runs it.** Fraunhofer SCAI (Bonn) with an international community.
  Pinned to git commit `dc9f9b1`. The same repository calls the ontology
  EPSO in its metadata. It is related to, but maintained separately from,
  the Case Western EpSO (section 4); one author, S. Sahoo, is on both.
* **Size and IDs.** 1,916 classes in the merged file; **414** are native EPIO
  classes that we index (the rest are imported from HPO and MONDO and come
  from those releases instead). Native IDs are local names such as
  `0000500` (connectivity). Terms about animal models and statistical
  methods are excluded.
* **Good at.** Epilepsy-specific wording, such as the ILAE categories, that
  HPO and MONDO express less directly.
* **Weak at.** Small, with sparse synonyms. Several terms are research
  concepts (e.g. "Zung self-rating anxiety scale") that clinic notes rarely
  mention, and IDs are not stable CURIEs like `HP:`.
* **How we use it.** As the third source in the same exact-match lookup,
  after HPO and MONDO.

### 1.4 SNOMED CT (US Edition)
* **What it is.** The largest clinical terminology in the world. It covers
  diagnoses, findings, procedures, body structures, substances and
  qualifiers, each as a *concept* with an ID, plus relationships between
  concepts. It is the standard coded vocabulary in US electronic health
  records. [S1, S2]
* **Who runs it.** SNOMED International; in the US the National Library of
  Medicine issues the US Edition (the International Edition plus US
  content).
* **Size and IDs.** In our `2026-09-01` snapshot: 543,260 concept rows, of
  which 390,812 are active. IDs are plain numbers (`84757009` = Epilepsy).
  Each concept has one **FSN** (fully specified name, ending in a semantic
  tag such as "(disorder)") and several descriptions; the US English
  language refset marks one description as the **preferred term**.
* **Good at.** Almost everything clinical: disorders and findings (including
  normal findings such as "MRI of brain normal"), procedures (EEG,
  lobectomy, VNS implantation), anatomy and substances. It includes the ILAE
  2017 seizure types.
* **Weak at.** It is large and fine-grained, so near-duplicates are common,
  and retired concepts linger. Its "replaced by" pointers can change meaning.
  Concepts for administrative ideas (current vs prior medication status) do
  not exist. It is licensed, not open.
* **How we use it.**
  * **Candidates.** Only active `(disorder)` and `(finding)` concepts under
    the epilepsy and seizure roots: **417 terms**, shown with the US
    preferred term.
  * **Checking our own codes.** Every curated SCTID is checked against the
    release (exists? active? name matches?). That check found 79 problems,
    and a manual review of the rest found 8 more; all are corrected
    (`docs/ONTOLOGY_SOURCES.md` §3).
* **Licence.** UMLS licence. Never committed or redistributed.

### 1.5 RxNorm
* **What it is.** The US standard names for clinical drugs, from the NLM. It
  links brand names, generic names, salts and doses to one identifier
  (RXCUI) and connects to many drug databases. [S3]
* **IDs and structure.** RXCUIs are numbers. Concepts have a *term type*:
  `IN` (ingredient, e.g. lamotrigine 28439), `PIN` (precise ingredient, e.g.
  a salt), `BN` (brand name, e.g. Lamictal), and many dose-form types. In our
  `2026-09-08` release there are 14,689 `IN` and 11,933 `BN` rows.
* **Good at.** Drug identity. It also carries other classifications as
  attributes, notably the WHO ATC class of each ingredient, which lets us
  pick "all antiepileptics" without writing the list by hand.
* **Weak at.** Doses and regimens ("75 mg twice daily") are not concepts we
  code; it says nothing about reason, status or timing.
* **How we use it.** `scripts/build_asm_lexicon.py` builds a **51-ingredient
  lexicon** from ATC N03A (Antiepileptics), our curated drugs, and seven
  FDA-indicated extras (diazepam, midazolam, lorazepam, clorazepate,
  acetazolamide, corticotropin, everolimus). It feeds both MedCAT drug
  detection and RxNorm coding. Salts fold into ingredients (valproic acid
  into valproate 40254). Brands count only when they map to a single
  ingredient.
* **Licence.** UMLS licence. Never committed or redistributed.

## 2. Bridges

### 2.1 UMLS Metathesaurus
* **What it is.** NLM's catalogue that links the same concept across more
  than a hundred vocabularies under one **CUI** (e.g. `C0014544` for
  epilepsy). Think of it as a switchboard: SNOMED CT, RxNorm, MeSH, HPO and
  ICD-10-CM entries for the same idea share a CUI. [S9]
* **How we use it.** Through the UTS REST API (no bulk download): to find the
  CUI of a SNOMED code and to pull extra synonyms for a concept. It is also
  the ID that MedCAT uses internally. Two caveats we hit: a CUI is only as
  good as whoever typed it, and about two dozen of our hand-typed CUIs pointed
  at the wrong concept. They are fixed and checked by the audit.
* **Licence.** Free account and agreement with NLM; no redistribution. The
  API key lives in `.env` and is never printed.

### 2.2 WHO ATC (Anatomical Therapeutic Chemical classification)
* **What it is.** A WHO system that groups drugs by organ and use. `N03A` is
  "Antiepileptics". [S4]
* **Why it matters here.** It decides which drugs are "epilepsy drugs". Since
  2023 gabapentin and pregabalin have been in `N02BF` (gabapentinoids), no
  longer in `N03A`, because their main use is neuropathic pain [S5]. We keep
  them in our list because clinicians prescribe them for seizures.
* **How we read it.** From the ATC rows already inside RxNorm, so there is no
  separate download.

## 3. Standards that define our enums but are not code lists

### 3.1 ILAE classifications: do we need them as an "ontology"?
**No separate download is needed, and none exists.** The ILAE publishes
position papers, not a code file. What it defines is the *meaning* of our
enum values:
* the 2017 operational seizure classification [C1] and epilepsy
  classification [C2], which our `SeizureType`, `EpilepsyType`,
  `Awareness` and etiology enums follow;
* the 2025 update [C3] (four classes, 21 seizure types instead of 63,
  "consciousness" instead of "awareness", observable vs non-observable
  instead of motor vs non-motor).

The ILAE terms already reach us through three routes: EPIO is built on the
ILAE classification, SNOMED CT contains the ILAE 2017 seizure types (we
corrected our codes to them), and the Case Western EpSO follows the ILAE too.
**The real open decision is whether to move our enums to ILAE 2025.** Real
clinic letters still use the 2017 and older ("complex partial") words, so we
would need both vocabularies at once. That is a schema change, so it needs a
decision, not a download.

### 3.2 NINDS Common Data Elements (CDEs)
* **What it is.** NIH/NINDS-recommended data elements and case-report-form
  modules for epilepsy research, revised in 2017 to follow the new ILAE
  classification. Each has a name, a definition and permitted values; the
  "Classification of Seizures" module, for instance, defines eight elements
  such as `SeizClassTyp` and `SeizGenClassTyp`. [N1]
* **Is it an ontology?** No. It is a data dictionary. But it matters for
  interoperability: a hospital or study that already collects NINDS CDEs
  can compare fields with ours directly.
* **Recommendation.** Do not load it into the retriever. **Do** map each
  field of our schema to its CDE name (a small table). That costs a day and
  makes the output usable for epilepsy research networks. Some CDE items
  carry UMLS CUIs, which gives a free cross-check of ours; for example the
  CDE form lists C0234533 as "Generalized seizures", which agrees with the
  correction we made to `IedType.spike`.

### 3.3 EEG terminology: SCORE and ACNS
* **SCORE** (Standardized Computer-based Organized Reporting of EEG, second
  version) is the IFCN's controlled vocabulary for reporting EEG, covering
  background, epileptiform discharges, seizures and critical-care patterns.
  [N2]
* **ACNS Standardized Critical Care EEG Terminology 2021** defines patterns
  such as electrographic seizure and BIRDs. [N3]
* Neither is a code file; both are free documents. Our `EegBackground` and
  `IedType` values should be reviewed against them. Note that
  `IedType.spike` has no SNOMED, HPO or UMLS concept, which is another reason
  to align to SCORE wording.

## 4. Other credible resources we could add

None is needed to use LEO today. Adding a source before we can *measure*
retrieval quality (recall@k on a gold mention-to-concept set) would be
guesswork, so these are ordered by expected payoff, not queued for work.

| Resource | What it adds | Licence / access (verified) | Fit | Effort |
|---|---|---|---|---|
| **ICD-10-CM** (CMS/NCHS, G40.x epilepsy, R56.9 unspecified convulsions) | The billing codes that appear in US notes and problem lists. Epilepsy codes encode intractable vs not and status epilepticus. | Free download from CMS | **High** for US notes; code mention to code is near-exact | Low |
| **EpSO**, Epilepsy and Seizure Ontology (Case Western; Sahoo et al.) | Seizure semiology, EEG, medication, neuropathology; follows ILAE including 2025 revisions | OWL v3.1 (May 2025) on NCBO BioPortal; check licence terms on the BioPortal page before use [E1] | **Medium-high**: closest to our semiology and EEG fields; overlaps EPIO | Medium |
| **Orphanet ORDO** | Rare epilepsy syndromes and gene links, with alignments to ICD-10/11, OMIM, UMLS, MONDO | CC BY 4.0, downloadable (July 2026 release) [E2] | **Medium**: much already reaches us through MONDO | Low |
| **NINDS CDE mapping** | Field-level interoperability, not terms | Public website [N1] | **High** as a mapping table | Low |
| **ICD-11** (WHO) | Newer WHO classification; epilepsy chapter follows ILAE | WHO API; licence terms not checked in this session | Low for US notes (ICD-10-CM is billed) | Medium |

Not evaluated in this session, so not recommended without checking:
MeSH, NCI Thesaurus, LOINC (note and study-type codes), OMOP/OHDSI Athena
vocabularies, ClinGen epilepsy gene curation.

Not suitable: DrugBank (licence restrictions on reuse) and any
proprietary clinical terminology; RxNorm already covers drug identity.

## 5. How each resource maps to a schema field

| Schema field group | Primary code system | Fallback |
|---|---|---|
| Seizure type, awareness | SNOMED CT (ILAE 2017 concepts), HPO | `MEDAI-ENUM` |
| Epilepsy type and syndrome | SNOMED CT, MONDO, EPIO | `MEDAI-ENUM` |
| Etiology (tumour, cortical dysplasia, hippocampal sclerosis, autoimmune) | SNOMED CT, MONDO | HPO |
| MRI and EEG findings | SNOMED CT, HPO | `MEDAI-ENUM` |
| Medications | RxNorm | none; unmatched drug stays uncoded and goes to review |
| Surgery, neurostimulation, diet | SNOMED CT (procedures, regimes) | `MEDAI-ENUM` |
| Medication status, certainty, temporality, drug resistance, Engel and ILAE outcome | none (derived by rules) | `MEDAI-ENUM` |
| Document type | SNOMED CT (procedure codes for EEG and MRI) | `MEDAI-ENUM` |

## 6. Honest limits

* Retrieval is **lexical**: it finds exact and near-exact wording. A
  paraphrase ("jerking of the left arm") needs the LLM selection step, which
  is not wired in yet.
* **Search quality has not been measured.** There is no gold set of
  mention-to-concept pairs, so we cannot say how often the right concept is
  in the top *k*.
* Only 49 of 150 claims on a 5-note sample carry a standard ontology ID; the
  rest remain internal values pending the LLM step.
* SNOMED CT and RxNorm may not leave this machine; anything that quotes them
  stays under `data/ontologies/` (git-ignored).
