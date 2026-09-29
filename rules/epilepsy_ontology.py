"""
Epilepsy ontology — 24 enum → CUI / SCTID / label / synonyms mappings for
the MedAI-EPI MedCAT + Rules pipeline (arm B1').

Coverage
--------
All 24 v0.2.1 enums (schema/enums.py). 20 are ``CONCEPT_LINKED`` (SNOMED/UMLS
concept anchor + surface forms). 6 are ``RULES_ONLY`` (derived by rules from
other extracted concepts / linguistic hedges and therefore have no primary
CUI anchor): ``Certainty``, ``ConcordanceStatus``, ``TemporalStatus``,
``DrugResistanceStatus``, ``EngelClass``, ``IlaeOutcome``. Rules-only enums
still ship value-level entries (label + synonym trigger phrases) so the
downstream rule dispatcher has a place to hang trigger strings.

Sources cited in ``source_provenance``
--------------------------------------
- ``F-S train EAxxxx`` — surface form mined from the Fonferko-Shadrach 2024
  gold corpus (letters EA0001–EA0160 only; EA0161–EA0200 are held-out test
  and were NOT read). CC-BY 4.0. See ``data/fs_corpus/targets/*/target_phenotype.json``.
- ``domain-knowledge:standard-neurology-vocab`` — standard clinical
  vocabulary used in US neurology/epileptology practice (ILAE 2017 Fisher
  et al., ACNS EEG terminology, NINDS CDE canonical phrasings).
- ``ILAE 2017`` — Fisher R S et al. 2017 (Epilepsia 58:522-30 and 58:531-42):
  operational classification of seizures and epilepsies.
- ``ILAE 2010`` — Kwan P et al. 2010 (Epilepsia 51:1069-77): drug-resistant
  epilepsy definition.
- ``Engel 1993`` — Engel J Jr et al. 1993, Surgical Treatment of the
  Epilepsies 2nd ed: post-op outcome classification IA–IVC.
- ``Wieser 2001`` — Wieser H G et al. 2001 (Epilepsia 42:282-6): ILAE
  post-op outcome classes 1–6.
- ``Graus 2016`` — Graus F et al. 2016 (Lancet Neurol 15:391-404): clinical
  approach to autoimmune encephalitis (antibody panel).
- ``ExECT-V2 seed`` — CUI concept anchor derived from
  ``references/exect_v2_cui_seed.csv`` (Phase 1a). Only the CUI itself is
  reused; ExECT verbatim surface strings are NOT redistributed here.
- ``RxNorm`` — U.S. National Library of Medicine drug vocabulary (public).
- ``NINDS CDE`` — NIH National Institute of Neurological Disorders and Stroke
  Common Data Elements for Epilepsy.
- ``SNOMED-CT US Edition`` — SCTID sourced from ExECT seed or hand-mapped
  from published ILAE/BioPortal cross-references.

Built by ``scripts/build_epilepsy_ontology.py`` on 2026-09-29 (Phase 1b).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConceptEntry:
    """One (enum, value) → clinical concept mapping.

    - ``cui``: UMLS CUI (Concept Unique Identifier), None if no direct
      concept anchor exists (rules-only compound derivations).
    - ``sctid``: SNOMED-CT identifier where confidently known. None means
      "pending Phase 1d UMLS-Full enrichment".
    - ``label``: canonical human-readable label (ILAE / NINDS / SNOMED
      preferred term; NOT copied verbatim from ExECT-V2).
    - ``synonyms``: surface forms the MedCAT+Rules matcher should recognize
      in free text. Each synonym MUST be sourced in
      ``source_provenance``.
    - ``source_provenance``: list of provenance strings (see module
      docstring for enumerated sources).
    """
    cui: Optional[str]
    sctid: Optional[str]
    label: str
    synonyms: list[str] = field(default_factory=list)
    source_provenance: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rules-only enums — no primary concept anchor.
# ---------------------------------------------------------------------------
RULES_ONLY_ENUMS: dict[str, str] = {
    "Certainty": (
        "Derived from linguistic hedges (medspaCy ConText NEG/HYP/UNC) plus "
        "MetaCAT concept-confidence probability. Not directly linked."
    ),
    "ConcordanceStatus": (
        "Derived from cross-source comparison of EEG-localization vs "
        "MRI-localization vs semiology (§5 integrated phenotype)."
    ),
    "TemporalStatus": (
        "Derived from ConText temporality + verb tense analysis. Trigger "
        "phrases are per-value but no CUI anchor."
    ),
    "DrugResistanceStatus": (
        "Derived by compound rule per ILAE 2010 (Kwan et al.): failure of "
        "two tolerated, appropriately chosen, adequately dosed ASM "
        "schedules to achieve seizure freedom."
    ),
    "EngelClass": (
        "Derived from post-operative seizure frequency using Engel 1993 "
        "classification (IA–IVC). No single CUI anchors each subclass."
    ),
    "IlaeOutcome": (
        "Derived from post-operative seizure days/year using Wieser 2001 "
        "classification (classes 1–6)."
    ),
}


# ---------------------------------------------------------------------------
# 1. DocumentType (12 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
DOCUMENT_TYPE_ONTOLOGY: dict[str, ConceptEntry] = {
    "mri_report": ConceptEntry(
        cui="C0412675", sctid="241615005",
        label="MRI report",
        synonyms=[
            "MRI report", "MRI brain report", "MR imaging report",
            "magnetic resonance imaging report", "MR brain", "brain MRI",
        ],
        source_provenance=["ExECT-V2 seed C0412675", "domain-knowledge:standard-neurology-vocab"],
    ),
    "eeg_report": ConceptEntry(
        cui="C0013819", sctid="164727004",
        label="EEG report",
        synonyms=[
            "EEG report", "electroencephalogram report", "EEG study",
            "EEG interpretation", "routine EEG", "video EEG report",
        ],
        source_provenance=["ExECT-V2 seed C0013819", "domain-knowledge:standard-neurology-vocab"],
    ),
    "progress_note": ConceptEntry(
        cui="C0555061", sctid="371531000",
        label="Progress note",
        synonyms=[
            "progress note", "clinic note", "follow-up note",
            "follow up visit", "clinic letter", "outpatient note",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "F-S train EA0001"],
    ),
    "initial_consult": ConceptEntry(
        cui="C0009818", sctid="11429006",
        label="Initial consultation",
        synonyms=[
            "initial consultation", "new patient consultation",
            "new patient evaluation", "initial visit", "first visit",
            "new referral", "new consult",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "presurgical_evaluation": ConceptEntry(
        cui="C0679828", sctid=None,
        label="Presurgical epilepsy evaluation",
        synonyms=[
            "pre-surgical evaluation", "presurgical work-up",
            "epilepsy surgery evaluation", "surgical candidacy evaluation",
            "phase 1 workup", "phase I evaluation",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "emu_admission": ConceptEntry(
        cui=None, sctid=None,
        label="Epilepsy Monitoring Unit admission",
        synonyms=[
            "EMU admission", "epilepsy monitoring unit admission",
            "admission to EMU", "video EEG admission", "vEEG admission",
            "long-term video EEG admission",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "emu_discharge": ConceptEntry(
        cui=None, sctid=None,
        label="Epilepsy Monitoring Unit discharge summary",
        synonyms=[
            "EMU discharge summary", "epilepsy monitoring unit discharge",
            "vEEG discharge summary", "LTM discharge summary",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "surgery_conference": ConceptEntry(
        cui=None, sctid=None,
        label="Epilepsy surgery conference note",
        synonyms=[
            "epilepsy surgery conference", "surgical conference note",
            "patient management conference", "PMC note",
            "multidisciplinary surgical review",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "procedure_seeg": ConceptEntry(
        cui="C4517211", sctid=None,
        label="Stereo-EEG procedure note",
        synonyms=[
            "sEEG procedure note", "stereo-EEG placement",
            "stereotactic EEG procedure", "intracranial monitoring procedure",
            "depth electrode placement",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "procedure_resection": ConceptEntry(
        cui="C0195028", sctid="107963003",
        label="Epilepsy resective surgery",
        synonyms=[
            "temporal lobectomy", "anterior temporal lobectomy",
            "amygdalohippocampectomy", "focal cortical resection",
            "epilepsy surgery", "lesionectomy",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "ILAE 2017"],
    ),
    "procedure_neurostim": ConceptEntry(
        cui=None, sctid="257538000",
        label="Neurostimulator procedure note",
        synonyms=[
            "VNS implantation", "vagus nerve stimulator placement",
            "RNS implantation", "responsive neurostimulation placement",
            "DBS implantation", "deep brain stimulator placement",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "other": ConceptEntry(
        cui=None, sctid=None,
        label="Other document type",
        synonyms=["other document", "unspecified note type"],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 2. Certainty (RULES_ONLY) — hedge triggers only.
# ---------------------------------------------------------------------------
CERTAINTY_ONTOLOGY: dict[str, ConceptEntry] = {
    "definite": ConceptEntry(
        cui=None, sctid=None,
        label="Definite (asserted)",
        synonyms=["confirmed", "diagnosed with", "has", "definite", "definitively"],
        source_provenance=["RULES_ONLY: Certainty", "domain-knowledge:standard-neurology-vocab"],
    ),
    "probable": ConceptEntry(
        cui=None, sctid=None,
        label="Probable",
        synonyms=["probable", "probably", "likely", "consistent with", "most likely"],
        source_provenance=["RULES_ONLY: Certainty", "domain-knowledge:standard-neurology-vocab"],
    ),
    "possible": ConceptEntry(
        cui=None, sctid=None,
        label="Possible",
        synonyms=["possible", "possibly", "may have", "could be", "suspicion of",
                  "concerning for", "cannot exclude"],
        source_provenance=["RULES_ONLY: Certainty", "domain-knowledge:standard-neurology-vocab"],
    ),
    "negated": ConceptEntry(
        cui=None, sctid=None,
        label="Negated",
        synonyms=["no", "not", "denies", "no evidence of", "without", "ruled out",
                  "negative for", "no history of"],
        source_provenance=["RULES_ONLY: Certainty", "domain-knowledge:standard-neurology-vocab"],
    ),
    "unknown": ConceptEntry(
        cui=None, sctid=None,
        label="Unknown (explicit)",
        synonyms=["unknown", "unclear", "uncertain", "not clear", "unable to determine"],
        source_provenance=["RULES_ONLY: Certainty", "domain-knowledge:standard-neurology-vocab"],
    ),
    "not_documented": ConceptEntry(
        cui=None, sctid=None,
        label="Not documented",
        synonyms=[],  # implicit — absence of mention
        source_provenance=["RULES_ONLY: Certainty"],
    ),
}


# ---------------------------------------------------------------------------
# 3. TemporalStatus (RULES_ONLY) — temporality trigger phrases.
# ---------------------------------------------------------------------------
TEMPORAL_STATUS_ONTOLOGY: dict[str, ConceptEntry] = {
    "current": ConceptEntry(
        cui=None, sctid=None,
        label="Current",
        synonyms=["currently", "current", "presently", "at present", "ongoing", "now"],
        source_provenance=["RULES_ONLY: TemporalStatus", "domain-knowledge:standard-neurology-vocab"],
    ),
    "historical": ConceptEntry(
        cui=None, sctid=None,
        label="Historical",
        synonyms=["history of", "hx of", "h/o", "past", "previously", "prior",
                  "in the past", "formerly", "years ago"],
        source_provenance=["RULES_ONLY: TemporalStatus", "domain-knowledge:standard-neurology-vocab"],
    ),
    "planned": ConceptEntry(
        cui=None, sctid=None,
        label="Planned",
        synonyms=["plan to", "planned", "to be started", "will start", "scheduled for",
                  "to consider", "we will initiate"],
        source_provenance=["RULES_ONLY: TemporalStatus", "domain-knowledge:standard-neurology-vocab"],
    ),
    "hypothetical": ConceptEntry(
        cui=None, sctid=None,
        label="Hypothetical",
        synonyms=["if", "should", "in case of", "would consider", "may consider",
                  "in the event of"],
        source_provenance=["RULES_ONLY: TemporalStatus", "domain-knowledge:standard-neurology-vocab"],
    ),
    "unspecified": ConceptEntry(
        cui=None, sctid=None,
        label="Unspecified",
        synonyms=[],
        source_provenance=["RULES_ONLY: TemporalStatus"],
    ),
}


# ---------------------------------------------------------------------------
# 4. EpilepsyType (4 values, CONCEPT_LINKED, ILAE 2017)
# ---------------------------------------------------------------------------
EPILEPSY_TYPE_ONTOLOGY: dict[str, ConceptEntry] = {
    "focal": ConceptEntry(
        cui="C0014547", sctid="230381004",
        label="Focal epilepsy (ILAE 2017)",
        synonyms=[
            "focal epilepsy", "partial epilepsy", "localization-related epilepsy",
            "localization related epilepsy", "focal onset epilepsy",
            "symptomatic structural focal epilepsy", "temporal lobe epilepsy",
            "frontal lobe epilepsy", "extratemporal epilepsy",
        ],
        source_provenance=[
            "ExECT-V2 seed C0014547", "ILAE 2017",
            "F-S train EA0001 'symptomatic, structural right temporal lobe epilepsy'",
            "F-S train EA0002 'focal epilepsy'",
        ],
    ),
    "generalized": ConceptEntry(
        cui="C0014548", sctid="19598007",
        label="Generalized epilepsy (ILAE 2017)",
        synonyms=[
            "generalized epilepsy", "generalised epilepsy",
            "genetic generalised epilepsy", "genetic generalized epilepsy",
            "idiopathic generalized epilepsy", "IGE",
            "primary generalized epilepsy", "GGE",
            # Batch A D2 — EPIO 2024 (CUI C0014548)
            "idiopathic generalised epilepsy",
        ],
        source_provenance=[
            "ExECT-V2 seed C0014548", "ILAE 2017",
            "F-S train (generalised epilepsy, genetic generalised epilepsy)",
            "EPIO 2024",
        ],
    ),
    "combined_focal_generalized": ConceptEntry(
        cui=None, sctid=None,
        label="Combined focal and generalized epilepsy (ILAE 2017)",
        synonyms=[
            "combined focal and generalized epilepsy",
            "combined generalized and focal epilepsy",
            "focal and generalized epilepsy",
        ],
        source_provenance=["ILAE 2017", "domain-knowledge:standard-neurology-vocab"],
    ),
    "unknown": ConceptEntry(
        cui="C0472355", sctid=None,
        label="Epilepsy of unknown onset type (ILAE 2017)",
        synonyms=[
            "epilepsy of unknown type", "unclassified epilepsy",
            "epilepsy undetermined whether focal or generalised",
            "unclassified epileptic syndrome",
        ],
        source_provenance=["ExECT-V2 seed C0472355", "ILAE 2017"],
    ),
}


# ---------------------------------------------------------------------------
# 5. SeizureType (16 values, CONCEPT_LINKED, ILAE 2017 basic types)
# ---------------------------------------------------------------------------
SEIZURE_TYPE_ONTOLOGY: dict[str, ConceptEntry] = {
    "focal_aware": ConceptEntry(
        cui="C0234974", sctid="117891000119100",
        label="Focal aware seizure (ILAE 2017; formerly simple partial)",
        synonyms=[
            "focal aware seizure", "focal seizure with retained awareness",
            "aware focal seizure", "simple partial seizure", "SPS",
            "focal onset aware seizure", "aura",
            # Batch A D2 — EPIO 2024 (CUI C0234974)
            "focal aware seizures",
            "focal seizure without impairment of awareness",
            "focal seizure without impairment of consciousness or awareness",
            "focal seizures without impairment of consciousness or awareness",
            "partial seizure with retained awareness",
            "partial seizure without impairment of awareness",
            "simple partial seizures",
        ],
        source_provenance=[
            "ExECT-V2 seed C0234974", "ILAE 2017",
            "domain-knowledge:standard-neurology-vocab",
            "EPIO 2024",
        ],
    ),
    "focal_impaired_awareness": ConceptEntry(
        cui="C0149958", sctid="230456007",
        label="Focal impaired awareness seizure (ILAE 2017; formerly complex partial)",
        synonyms=[
            "focal impaired awareness seizure", "focal seizure with impaired awareness",
            "focal seizure with loss of awareness", "focal seizures with altered awareness",
            "complex partial seizure", "CPS", "dyscognitive seizure",
            "focal seizure with dyscognitive features",
            # Batch A D3 — HPO 2024 (HP:0002384, HP:0007359)
            "focal dyscognitive seizure", "dyscognitive seizures",
            "complex focal seizures", "complex partial seizures",
            "focal impaired awareness seizures",
            "focal seizures with impairment of consciousness or awareness",
            "localised dyscognitive seizure", "localized dyscognitive seizure",
            "localised seizure with impaired awareness",
            "localized seizure with impaired awareness",
            "localised seizure with loss of awareness",
            "localized seizure with loss of awareness",
            "partial dyscognitive seizure",
            "partial seizure with impairment of awareness",
            "partial seizure with loss of awareness",
        ],
        source_provenance=[
            "ExECT-V2 seed C0149958", "ILAE 2017",
            "F-S train EA0001 'focal seizures with loss of awareness'",
            "F-S train (focal seizures with altered awareness)",
            "HPO 2024",
        ],
    ),
    "focal_unknown_awareness": ConceptEntry(
        cui="C0751495", sctid="29753000",
        label="Focal seizure, awareness unknown (ILAE 2017)",
        synonyms=[
            "focal seizure", "focal seizures", "partial seizure",
            "focal-onset seizure", "focal onset seizure",
            "focal seizure of unknown awareness",
            # Batch A D2 — EPIO 2024 (CUI C0751495)
            "focal-onset seizures", "partial seizures",
            "seizure affecting one half of brain",
        ],
        source_provenance=[
            "ExECT-V2 seed C0751495", "ILAE 2017",
            "F-S train (focal seizures, focal seizure)",
            "EPIO 2024",
        ],
    ),
    "focal_to_bilateral_tonic_clonic": ConceptEntry(
        cui="C0877017", sctid=None,
        label="Focal to bilateral tonic-clonic seizure (ILAE 2017; formerly secondarily generalized)",
        synonyms=[
            "focal to bilateral tonic-clonic seizure", "focal to bilateral TCS",
            "focal to bilateral convulsive seizure",
            "secondarily generalized seizure", "secondarily generalised seizure",
            "secondary generalized tonic clonic seizure",
            "secondary generalised seizure", "secondary generalisation",
            "focal seizure with secondary generalisation",
        ],
        source_provenance=[
            "ExECT-V2 seed C0877017", "ILAE 2017",
            "F-S train (secondary generalised seizures, secondarily generalised seizures)",
            "F-S train (focal seizures with secondary generalisation)",
        ],
    ),
    "generalized_tonic_clonic": ConceptEntry(
        cui="C0014549", sctid="86181006",
        label="Generalized tonic-clonic seizure (ILAE 2017)",
        synonyms=[
            "generalized tonic-clonic seizure", "generalised tonic-clonic seizure",
            "generalised tonic clonic seizure", "generalized tonic clonic seizure",
            "GTC", "GTCS", "grand mal seizure", "grand mal convulsion",
            "tonic-clonic seizure", "convulsive seizure", "bilateral tonic-clonic seizure",
            # Batch A D3 — HPO 2024 (HP:0002197 Generalized-onset seizure)
            "generalized-onset seizure", "generalised-onset seizure",
            "generalized onset seizure", "generalised onset seizure",
            "generalized-onset seizures", "generalized seizures",
            "generalised seizures", "primary generalized seizure",
            "primary generalised seizure",
        ],
        source_provenance=[
            "ExECT-V2 seed C0014549", "ExECT-V2 seed C0494475 (grand mal)",
            "ILAE 2017",
            "F-S train (Generalised tonic clonic seizure, generalised tonic clonic seizures)",
            "HPO 2024",
        ],
    ),
    "generalized_tonic": ConceptEntry(
        cui="C0086241", sctid="51887003",
        label="Generalized tonic seizure (ILAE 2017)",
        synonyms=[
            "generalized tonic seizure", "generalised tonic seizure",
            "tonic seizure", "tonic epilepsy",
        ],
        source_provenance=["ExECT-V2 seed C0086241", "ExECT-V2 seed C0270844", "ILAE 2017"],
    ),
    "generalized_clonic": ConceptEntry(
        cui="C0234535", sctid="6208003",
        label="Generalized clonic seizure (ILAE 2017)",
        synonyms=[
            "generalized clonic seizure", "generalised clonic seizure",
            "clonic seizure", "clonic epileptic seizure",
        ],
        source_provenance=["ExECT-V2 seed C0234535", "ILAE 2017"],
    ),
    "generalized_myoclonic": ConceptEntry(
        cui="C4317123", sctid="37356005",
        label="Generalized myoclonic seizure (ILAE 2017)",
        synonyms=[
            "generalized myoclonic seizure", "generalised myoclonic seizure",
            "myoclonic seizure", "myoclonic jerk", "myoclonic jerks",
            "myoclonus", "bilateral myoclonic jerks",
        ],
        source_provenance=[
            "ExECT-V2 seed C4317123", "ILAE 2017",
            "F-S train (myoclonic jerks, myoclonus)",
        ],
    ),
    "generalized_absence_typical": ConceptEntry(
        cui="C0014553", sctid="79631006",
        label="Typical absence seizure (ILAE 2017)",
        synonyms=[
            "typical absence seizure", "absence seizure", "absence",
            "petit mal seizure", "petit mal", "staring spell",
            "3 Hz spike-wave absence",
            # Batch A D3 — HPO 2024 (HP:0002121)
            "generalized non-motor (absence) seizure",
            "generalised non-motor (absence) seizure",
            "generalised non-motor seizure",
            "petit mal seizures", "absence seizures",
            "brief seizures with staring spells",
        ],
        source_provenance=[
            "ExECT-V2 seed C0014553", "ILAE 2017",
            "F-S train (absences, absence like seizures)",
            "HPO 2024",
        ],
    ),
    "generalized_absence_atypical": ConceptEntry(
        cui="C0595948", sctid="23374007",
        label="Atypical absence seizure (ILAE 2017)",
        synonyms=[
            "atypical absence seizure", "atypical absence",
            "absence with atypical features", "slow spike-wave absence",
            # Batch A D3 — HPO 2024 (HP:0007270)
            "atypical absence seizures", "atypical petit mal seizures",
        ],
        source_provenance=[
            "ExECT-V2 seed C0595948", "ILAE 2017", "HPO 2024",
        ],
    ),
    "generalized_atonic": ConceptEntry(
        cui="C0270846", sctid="42365007",
        label="Atonic seizure (ILAE 2017)",
        synonyms=[
            "atonic seizure", "drop attack", "drop seizure", "astatic seizure",
            "akinetic seizure",
            # Batch A D3 — HPO 2024 (HP:0010819)
            "atonic seizures", "astatic seizures", "drop attacks",
            "drop seizures", "hypotonic seizure", "hypotonic seizures",
            "sudden loss of muscle tone",
        ],
        source_provenance=[
            "ExECT-V2 seed C0270846", "ILAE 2017", "HPO 2024",
        ],
    ),
    "generalized_epileptic_spasms": ConceptEntry(
        cui="C1527366", sctid="28055006",
        label="Epileptic spasms (ILAE 2017)",
        synonyms=[
            "epileptic spasms", "infantile spasms", "salaam spasms",
            "salaam attack", "West syndrome spasms", "flexor spasms",
        ],
        source_provenance=["ExECT-V2 seed C1527366", "ILAE 2017"],
    ),
    "unknown_onset_tonic_clonic": ConceptEntry(
        cui="C4476643", sctid=None,
        label="Unknown-onset tonic-clonic seizure (ILAE 2017)",
        synonyms=[
            "unknown onset tonic-clonic seizure",
            "tonic-clonic seizure of unknown onset",
            "bilateral convulsive seizure",
            "convulsive seizure of unknown onset",
            "witnessed generalised convulsion",
        ],
        source_provenance=[
            "ExECT-V2 seed C4476643", "ILAE 2017",
            "F-S train (bilateral convulsive seizure, focal to bilateral convulsive seizures)",
        ],
    ),
    "unknown_onset_motor_other": ConceptEntry(
        cui=None, sctid=None,
        label="Unknown-onset motor seizure, other (ILAE 2017)",
        synonyms=[
            "unknown onset motor seizure", "motor seizure of unknown onset",
            "motor seizure",
        ],
        source_provenance=["ILAE 2017", "domain-knowledge:standard-neurology-vocab"],
    ),
    "unknown_onset_nonmotor": ConceptEntry(
        cui=None, sctid=None,
        label="Unknown-onset non-motor seizure (ILAE 2017)",
        synonyms=[
            "unknown onset non-motor seizure", "non-motor seizure of unknown onset",
            "behavior arrest of unknown onset",
        ],
        source_provenance=["ILAE 2017", "domain-knowledge:standard-neurology-vocab"],
    ),
    "unclassified": ConceptEntry(
        cui="C0270826", sctid=None,
        label="Unclassified epileptic seizure",
        synonyms=[
            "unclassified seizure", "unclassified epileptic seizure",
            "seizure NOS", "seizure not otherwise specified",
        ],
        source_provenance=["ExECT-V2 seed C0270826", "domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 6. Awareness (3 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
AWARENESS_ONTOLOGY: dict[str, ConceptEntry] = {
    "aware": ConceptEntry(
        cui="C0007797", sctid="248220008",
        label="Awareness retained",
        synonyms=[
            "aware", "awareness retained", "retained awareness",
            "consciousness preserved", "fully aware", "conscious",
        ],
        source_provenance=["ILAE 2017", "domain-knowledge:standard-neurology-vocab"],
    ),
    "impaired": ConceptEntry(
        cui="C0234450", sctid="418072004",
        label="Impaired awareness / consciousness",
        synonyms=[
            "impaired awareness", "loss of awareness", "altered awareness",
            "loss of consciousness", "LOC", "unresponsive", "unaware",
            "impaired consciousness", "reduced awareness",
        ],
        source_provenance=[
            "ILAE 2017",
            "F-S train (loss of awareness, altered awareness, loss of consciousness)",
        ],
    ),
    "unknown": ConceptEntry(
        cui=None, sctid=None,
        label="Awareness unknown",
        synonyms=["awareness unknown", "unclear awareness", "awareness not documented"],
        source_provenance=["ILAE 2017"],
    ),
}


# ---------------------------------------------------------------------------
# 7. Laterality (6 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
LATERALITY_ONTOLOGY: dict[str, ConceptEntry] = {
    "left": ConceptEntry(
        cui="C0205091", sctid="7771000",
        label="Left",
        synonyms=["left", "left-sided", "L", "sinister", "left hemisphere"],
        source_provenance=["SNOMED-CT US Edition 7771000", "domain-knowledge:standard-neurology-vocab"],
    ),
    "right": ConceptEntry(
        cui="C0205090", sctid="24028007",
        label="Right",
        synonyms=["right", "right-sided", "R", "dexter", "right hemisphere"],
        source_provenance=["SNOMED-CT US Edition 24028007", "domain-knowledge:standard-neurology-vocab"],
    ),
    "bilateral": ConceptEntry(
        cui="C0238767", sctid="51440002",
        label="Bilateral",
        synonyms=["bilateral", "bilaterally", "both sides", "both hemispheres", "B/L"],
        source_provenance=["SNOMED-CT US Edition 51440002", "domain-knowledge:standard-neurology-vocab"],
    ),
    "midline": ConceptEntry(
        cui="C0444667", sctid="255561001",
        label="Midline",
        synonyms=["midline", "central", "medial", "midsagittal"],
        source_provenance=["SNOMED-CT US Edition 255561001", "domain-knowledge:standard-neurology-vocab"],
    ),
    "diffuse": ConceptEntry(
        cui="C0205219", sctid="49755003",
        label="Diffuse",
        synonyms=["diffuse", "diffusely", "widespread", "generalized"],
        source_provenance=["SNOMED-CT US Edition 49755003", "domain-knowledge:standard-neurology-vocab"],
    ),
    "unknown": ConceptEntry(
        cui=None, sctid=None,
        label="Laterality unknown",
        synonyms=["unknown laterality", "side not specified", "laterality unclear"],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 8. LobarLocalization (8 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
LOBAR_LOCALIZATION_ONTOLOGY: dict[str, ConceptEntry] = {
    "frontal": ConceptEntry(
        cui="C0085541", sctid="102299003",
        label="Frontal lobe",
        synonyms=[
            "frontal lobe", "frontal", "frontal region", "frontal cortex",
            "prefrontal", "frontal lobe epilepsy", "FLE",
        ],
        source_provenance=["ExECT-V2 seed C0085541", "domain-knowledge:standard-neurology-vocab"],
    ),
    "temporal": ConceptEntry(
        cui="C0014556", sctid="78277001",
        label="Temporal lobe",
        synonyms=[
            "temporal lobe", "temporal", "temporal region", "temporal cortex",
            "mesial temporal", "medial temporal", "temporal lobe epilepsy", "TLE",
            "mesial temporal lobe epilepsy", "MTLE",
        ],
        source_provenance=[
            "ExECT-V2 seed C0014556", "domain-knowledge:standard-neurology-vocab",
            "F-S train EA0001 'right temporal lobe epilepsy'",
        ],
    ),
    "parietal": ConceptEntry(
        cui="C0393690", sctid="16630005",
        label="Parietal lobe",
        synonyms=[
            "parietal lobe", "parietal", "parietal region", "parietal cortex",
            "parietal lobe epilepsy", "PLE",
        ],
        source_provenance=["ExECT-V2 seed C0393690", "domain-knowledge:standard-neurology-vocab"],
    ),
    "occipital": ConceptEntry(
        cui="C0393691", sctid="31065004",
        label="Occipital lobe",
        synonyms=[
            "occipital lobe", "occipital", "occipital region", "occipital cortex",
            "occipital lobe epilepsy", "OLE",
        ],
        source_provenance=[
            "ExECT-V2 seed C0393691", "domain-knowledge:standard-neurology-vocab",
            "F-S train (occipital lobe infarct)",
        ],
    ),
    "insular": ConceptEntry(
        cui="C0228281", sctid="90351000",
        label="Insular cortex",
        synonyms=[
            "insula", "insular", "insular cortex", "insular lobe",
            "insular epilepsy", "island of Reil",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "ILAE 2017"],
    ),
    "cingulate": ConceptEntry(
        cui="C0152314", sctid="83251001",
        label="Cingulate cortex",
        synonyms=[
            "cingulate", "cingulate cortex", "cingulate gyrus",
            "anterior cingulate", "posterior cingulate", "cingulate epilepsy",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "ILAE 2017"],
    ),
    "multifocal": ConceptEntry(
        cui=None, sctid=None,
        label="Multifocal",
        synonyms=[
            "multifocal", "multiple foci", "multifocal epilepsy",
            "multifocal onset", "bihemispheric multifocal",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "unknown": ConceptEntry(
        cui=None, sctid=None,
        label="Localization unknown",
        synonyms=["unknown localization", "lobe unclear", "non-localizable"],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 9. LocalizationSource (5 values, CONCEPT_LINKED to source-of-evidence type)
# ---------------------------------------------------------------------------
LOCALIZATION_SOURCE_ONTOLOGY: dict[str, ConceptEntry] = {
    "clinician_hypothesis": ConceptEntry(
        cui=None, sctid=None,
        label="Clinician hypothesis (semiology-based)",
        synonyms=[
            "clinical impression", "clinician suspects", "based on semiology",
            "on clinical grounds", "clinically suggestive of",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "eeg_confirmed": ConceptEntry(
        cui="C0013819", sctid="164727004",
        label="EEG-confirmed localization",
        synonyms=[
            "EEG showed", "EEG confirmed", "on EEG", "EEG revealed",
            "video EEG captured", "ictal EEG showed", "interictal EEG showed",
        ],
        source_provenance=["ExECT-V2 seed C0013819", "domain-knowledge:standard-neurology-vocab"],
    ),
    "mri_confirmed": ConceptEntry(
        cui=None, sctid="113091000",
        label="MRI-confirmed localization",
        synonyms=[
            "MRI showed", "MRI confirmed", "on MRI", "MRI demonstrated",
            "MRI revealed a lesion in", "structural MRI",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "seeg_confirmed": ConceptEntry(
        cui=None, sctid=None,
        label="Stereo-EEG-confirmed localization",
        synonyms=[
            "sEEG showed", "sEEG confirmed", "on stereo-EEG",
            "depth electrode recording showed", "intracranial EEG showed",
            "iEEG confirmed",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "surgical_confirmed": ConceptEntry(
        cui=None, sctid=None,
        label="Surgical / pathology-confirmed localization",
        synonyms=[
            "surgical pathology confirmed", "post-op pathology showed",
            "resected specimen confirmed", "ECoG-confirmed onset zone",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 10. EegStudyType (8 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
EEG_STUDY_TYPE_ONTOLOGY: dict[str, ConceptEntry] = {
    "routine": ConceptEntry(
        cui="C0013819", sctid="54550000",
        label="Routine EEG",
        synonyms=[
            "routine EEG", "standard EEG", "20-minute EEG",
            "outpatient EEG", "awake and drowsy EEG",
        ],
        source_provenance=["ExECT-V2 seed C0013819", "ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "prolonged": ConceptEntry(
        cui=None, sctid="35935001",
        label="Prolonged EEG",
        synonyms=[
            "prolonged EEG", "long-term EEG monitoring", "LTM",
            "extended EEG",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "ambulatory": ConceptEntry(
        cui=None, sctid="426405006",
        label="Ambulatory EEG",
        synonyms=[
            "ambulatory EEG", "aEEG", "outpatient ambulatory EEG",
            "24-hour ambulatory EEG", "48-hour ambulatory EEG",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "video_eeg": ConceptEntry(
        cui=None, sctid="426405006",
        label="Video EEG",
        synonyms=[
            "video EEG", "vEEG", "video-EEG monitoring", "video telemetry",
            "video EEG monitoring", "VEM",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "emu": ConceptEntry(
        cui=None, sctid=None,
        label="Epilepsy Monitoring Unit study",
        synonyms=[
            "EMU", "epilepsy monitoring unit", "inpatient video EEG",
            "epilepsy unit admission",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "intraoperative": ConceptEntry(
        cui=None, sctid=None,
        label="Intraoperative EEG",
        synonyms=[
            "intraoperative EEG", "IONM", "intraoperative electrocorticography",
            "intraop EEG",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "seeg": ConceptEntry(
        cui=None, sctid=None,
        label="Stereo-EEG",
        synonyms=[
            "sEEG", "stereo-EEG", "stereotactic EEG",
            "stereoelectroencephalography", "depth electrode recording",
            "intracranial EEG", "iEEG",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "ILAE 2017"],
    ),
    "ecog": ConceptEntry(
        cui=None, sctid=None,
        label="Electrocorticography (subdural grid/strip)",
        synonyms=[
            "ECoG", "electrocorticography", "subdural grid EEG",
            "subdural strip recording", "corticography",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 11. EegBackground (7 values, CONCEPT_LINKED, ACNS terminology)
# ---------------------------------------------------------------------------
EEG_BACKGROUND_ONTOLOGY: dict[str, ConceptEntry] = {
    "normal": ConceptEntry(
        cui="C0560017", sctid=None,
        label="Normal EEG background",
        synonyms=[
            "normal EEG", "normal background", "EEG normal",
            "posterior dominant rhythm within normal limits",
            "well-formed alpha rhythm", "unremarkable EEG",
        ],
        source_provenance=["ExECT-V2 seed C0560017", "ACNS terminology"],
    ),
    "diffuse_slowing": ConceptEntry(
        cui=None, sctid=None,
        label="Diffuse background slowing",
        synonyms=[
            "diffuse slowing", "generalized slowing", "diffuse background slowing",
            "diffuse theta slowing", "diffuse delta slowing", "generalised slowing",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "focal_slowing": ConceptEntry(
        cui=None, sctid=None,
        label="Focal background slowing",
        synonyms=[
            "focal slowing", "regional slowing", "focal theta slowing",
            "focal delta slowing", "focal polymorphic delta",
            "focal intermittent rhythmic delta activity", "focal IRDA",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "asymmetric": ConceptEntry(
        cui=None, sctid=None,
        label="Asymmetric background",
        synonyms=[
            "asymmetric EEG background", "asymmetry", "hemispheric asymmetry",
            "amplitude asymmetry", "voltage asymmetry",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "suppressed": ConceptEntry(
        cui=None, sctid=None,
        label="Suppressed EEG background",
        synonyms=[
            "suppressed background", "low voltage EEG", "attenuated background",
            "electrocerebral inactivity",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "burst_suppression": ConceptEntry(
        cui="C0234450", sctid=None,
        label="Burst-suppression pattern",
        synonyms=[
            "burst-suppression", "burst suppression pattern",
            "burst-attenuation", "suppression-burst pattern",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "other": ConceptEntry(
        cui="C0151611", sctid=None,
        label="Abnormal EEG background, other",
        synonyms=[
            "abnormal EEG background other", "EEG abnormal",
            "abnormal background other",
        ],
        source_provenance=["ExECT-V2 seed C0151611", "ACNS terminology"],
    ),
}


# ---------------------------------------------------------------------------
# 12. IedType (8 values, CONCEPT_LINKED, ACNS interictal terminology)
# ---------------------------------------------------------------------------
IED_TYPE_ONTOLOGY: dict[str, ConceptEntry] = {
    "spike": ConceptEntry(
        cui="C0234533", sctid="79745007",
        label="Spike (interictal epileptiform discharge)",
        synonyms=[
            "spike", "spikes", "epileptiform spike", "interictal spike",
            "focal spike",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "sharp_wave": ConceptEntry(
        cui=None, sctid=None,
        label="Sharp wave",
        synonyms=[
            "sharp wave", "sharp waves", "sharps", "interictal sharp wave",
            "focal sharp wave",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "spike_and_wave": ConceptEntry(
        cui=None, sctid=None,
        label="Spike-and-wave complex",
        synonyms=[
            "spike-and-wave", "spike and wave complex", "spike-wave discharge",
            "SWD", "generalised spike-and-wave", "generalized spike wave",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "polyspike": ConceptEntry(
        cui=None, sctid=None,
        label="Polyspike",
        synonyms=["polyspike", "polyspikes", "multiple spike complex"],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "polyspike_and_wave": ConceptEntry(
        cui=None, sctid=None,
        label="Polyspike-and-wave",
        synonyms=[
            "polyspike-and-wave", "polyspike and wave complex",
            "polyspike-wave discharge",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "sharp_and_slow": ConceptEntry(
        cui=None, sctid=None,
        label="Sharp-and-slow-wave complex",
        synonyms=[
            "sharp-and-slow-wave", "sharp and slow complex",
            "slow spike-and-wave", "slow spike wave",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
    "generalized_spike_wave_3hz": ConceptEntry(
        cui=None, sctid=None,
        label="Generalized 3 Hz spike-wave",
        synonyms=[
            "3 Hz spike-and-wave", "3 Hz spike-wave", "3-per-second spike-wave",
            "3Hz spike wave discharge", "typical 3 Hz GSW",
        ],
        source_provenance=["ACNS terminology", "ILAE 2017"],
    ),
    "other": ConceptEntry(
        cui=None, sctid=None,
        label="Other interictal epileptiform discharge",
        synonyms=[
            "interictal epileptiform discharge", "IED",
            "epileptiform activity", "epileptiform discharge",
        ],
        source_provenance=["ACNS terminology", "domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 13. MriFinding (18 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
MRI_FINDING_ONTOLOGY: dict[str, ConceptEntry] = {
    "normal": ConceptEntry(
        cui="C0436481", sctid=None,
        label="Normal MRI brain",
        synonyms=[
            "normal MRI", "MRI normal", "unremarkable MRI",
            "MRI brain normal", "no abnormality on MRI",
        ],
        source_provenance=["ExECT-V2 seed C0436481", "domain-knowledge:standard-neurology-vocab"],
    ),
    "hippocampal_sclerosis": ConceptEntry(
        cui="C4749367", sctid="230368004",
        label="Hippocampal sclerosis",
        synonyms=[
            "hippocampal sclerosis", "HS", "mesial temporal sclerosis", "MTS",
            "Ammon's horn sclerosis", "unilateral hippocampal sclerosis",
            # Batch A D4 — compound phrases per Blumcke 2013 ILAE-CTF
            "left hippocampal sclerosis", "right hippocampal sclerosis",
            "bilateral hippocampal sclerosis", "mesial temporal atrophy",
            "hippocampal atrophy", "hippocampal volume loss",
            "mesial temporal signal abnormality", "hippocampal gliosis",
            "sclerosis of the hippocampus", "MTS type 1", "MTS type 2",
            "MTS type 3", "ILAE HS type 1", "ILAE HS type 2", "ILAE HS type 3",
            "hippocampal sclerosis ILAE type",
            # Dual pathology — HS + secondary lesion
            "dual pathology", "hippocampal sclerosis with dual pathology",
        ],
        source_provenance=[
            "ExECT-V2 seed C4749367", "ILAE 2017",
            "F-S train (hippocampal sclerosis)",
            "domain-knowledge:neuroradiology-standard",
            "Blumcke 2013",
        ],
    ),
    "focal_cortical_dysplasia": ConceptEntry(
        cui="C0431384", sctid="253175007",
        label="Focal cortical dysplasia (unspecified subtype)",
        synonyms=[
            "focal cortical dysplasia", "FCD", "cortical dysplasia",
            "cortical malformation", "left frontal cortical dysplasia",
            # Batch A D4 — compound phrases per Blumcke 2011
            "Taylor type dysplasia", "Taylor-type cortical dysplasia",
            "malformation of cortical development", "MCD",
            "FCD type III", "FCD IIIa", "FCD IIIb", "FCD IIIc", "FCD IIId",
            "FCD type IIIa", "FCD type IIIb", "FCD type IIIc", "FCD type IIId",
            "cortical thickening", "blurring of grey-white matter junction",
            "blurred grey-white junction", "transmantle sign",
            "right frontal cortical dysplasia", "left temporal cortical dysplasia",
            "right temporal cortical dysplasia", "parietal cortical dysplasia",
            "occipital cortical dysplasia",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab", "ILAE 2017",
            "F-S train (cortical dysplasia)",
            "domain-knowledge:neuroradiology-standard",
            "Blumcke 2011",
        ],
    ),
    "fcd_palmini_i": ConceptEntry(
        cui=None, sctid=None,
        label="Focal cortical dysplasia, Palmini Type I",
        synonyms=[
            "FCD type I", "Palmini type I FCD", "FCD Ia", "FCD Ib", "FCD Ic",
            "isolated architectural dysplasia",
            # Batch A D4
            "FCD type Ia", "FCD type Ib", "FCD type Ic",
            "focal cortical dysplasia type I",
            "focal cortical dysplasia type Ia",
            "focal cortical dysplasia type Ib",
        ],
        source_provenance=[
            "ILAE 2017", "domain-knowledge:standard-neurology-vocab",
            "domain-knowledge:neuroradiology-standard", "Blumcke 2011",
        ],
    ),
    "fcd_palmini_iia": ConceptEntry(
        cui=None, sctid=None,
        label="Focal cortical dysplasia, Palmini Type IIa",
        synonyms=[
            "FCD type IIa", "FCD IIa", "Palmini type IIa",
            "FCD with dysmorphic neurons",
            # Batch A D4
            "focal cortical dysplasia type IIa",
            "focal cortical dysplasia IIa",
            "type IIa FCD",
        ],
        source_provenance=[
            "ILAE 2017", "domain-knowledge:standard-neurology-vocab",
            "domain-knowledge:neuroradiology-standard", "Blumcke 2011",
        ],
    ),
    "fcd_palmini_iib": ConceptEntry(
        cui=None, sctid=None,
        label="Focal cortical dysplasia, Palmini Type IIb (with balloon cells)",
        synonyms=[
            "FCD type IIb", "FCD IIb", "Palmini type IIb",
            "FCD with balloon cells", "Taylor-type FCD",
            # Batch A D4
            "focal cortical dysplasia type IIb",
            "focal cortical dysplasia IIb",
            "type IIb FCD",
            "Taylor-type focal cortical dysplasia",
            "cortical dysplasia with balloon cells",
        ],
        source_provenance=[
            "ILAE 2017", "domain-knowledge:standard-neurology-vocab",
            "domain-knowledge:neuroradiology-standard", "Blumcke 2011",
        ],
    ),
    "moghe": ConceptEntry(
        cui=None, sctid=None,
        label="Mild MCD with oligodendroglial hyperplasia (MOGHE)",
        synonyms=[
            "MOGHE", "mild malformation of cortical development with oligodendroglial hyperplasia",
            "oligodendroglial hyperplasia in epilepsy",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "tumor": ConceptEntry(
        cui="C0006826", sctid="126906006",
        label="Brain tumor",
        synonyms=[
            "brain tumor", "brain tumour", "intracranial tumor",
            "DNET", "dysembryoplastic neuroepithelial tumor",
            "ganglioglioma", "low-grade glioma", "meningioma",
            # Batch A D4 — epilepsy-associated tumor compound phrases
            "gangliocytoma", "pleomorphic xanthoastrocytoma", "PXA",
            "long-term epilepsy-associated tumor", "LEAT",
            "pilocytic astrocytoma", "oligodendroglioma",
            "epilepsy-associated tumor", "temporal lobe glioma",
            "hypothalamic hamartoma",
            # Batch A D2 — EPIO 2024 (CUI C0006826)
            "neoplasm", "neoplasia", "tumor", "tumour",
            "abnormal tissue mass", "intracranial meningioma",
            "supratentorial meningioma", "meningeal neoplasm",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (meningioma, cavernoma in the right temporal lobe)",
            "domain-knowledge:neuroradiology-standard",
            "EPIO 2024",
        ],
    ),
    "vascular_malformation": ConceptEntry(
        cui="C0339277", sctid="80078006",
        label="Vascular malformation",
        synonyms=[
            "cavernoma", "cavernous malformation", "cavernous angioma",
            "arteriovenous malformation", "AVM", "developmental venous anomaly", "DVA",
            # Batch A D4 — compound vascular malformation phrases
            "cerebral cavernous malformation", "CCM",
            "cerebral arteriovenous malformation",
            "cavernous hemangioma of the brain",
            "cortical cavernoma", "supratentorial AVM",
            "Sturge-Weber angiomatosis", "Sturge-Weber syndrome",
            "leptomeningeal angioma", "leptomeningeal angiomatosis",
            "pial angioma",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (cavernoma, cavernoma in the right temporal lobe)",
            "domain-knowledge:neuroradiology-standard",
        ],
    ),
    "encephalomalacia": ConceptEntry(
        cui="C0270819", sctid="230752002",
        label="Encephalomalacia",
        synonyms=[
            "encephalomalacia", "cerebral encephalomalacia",
            "post-traumatic encephalomalacia", "chronic infarct with encephalomalacia",
            # Batch A D4 — compound phrases
            "porencephalic cyst", "porencephaly",
            "cystic encephalomalacia", "gliotic encephalomalacia",
            "post-traumatic gliosis and encephalomalacia",
            "chronic encephalomalacia",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "domain-knowledge:neuroradiology-standard",
        ],
    ),
    "gliosis": ConceptEntry(
        cui="C0017639", sctid=None,
        label="Gliosis",
        synonyms=[
            "gliosis", "reactive gliosis", "cortical gliosis",
            "peri-lesional gliosis",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "stroke_sequelae": ConceptEntry(
        cui="C3662042", sctid=None,
        label="Stroke sequelae on imaging",
        synonyms=[
            "stroke sequelae", "old infarct", "chronic infarct",
            "post-stroke changes", "MCA infarct", "prior CVA",
            "occipital lobe infarct",
            # Batch A D4 — compound phrases
            "perinatal stroke sequelae", "perinatal arterial ischemic stroke",
            "chronic middle cerebral artery infarct",
            "old MCA territory infarct", "prior middle cerebral artery infarct",
            "chronic posterior cerebral artery infarct",
            "watershed infarct sequelae", "post-hypoxic changes",
            "perinatal white matter injury",
        ],
        source_provenance=[
            "ExECT-V2 seed C3662042",
            "F-S train (MCA infarct, occipital lobe infarct, stroke)",
            "domain-knowledge:neuroradiology-standard",
        ],
    ),
    "polymicrogyria": ConceptEntry(
        cui="C0266464", sctid=None,
        label="Polymicrogyria",
        synonyms=[
            "polymicrogyria", "PMG", "perisylvian polymicrogyria",
            "bilateral perisylvian polymicrogyria",
            # Batch A D4 — compound phrases
            "unilateral perisylvian polymicrogyria",
            "bilateral frontoparietal polymicrogyria",
            "diffuse polymicrogyria", "focal polymicrogyria",
            "schizencephaly with polymicrogyria",
            "polymicrogyria-schizencephaly complex",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "domain-knowledge:neuroradiology-standard",
        ],
    ),
    "heterotopia": ConceptEntry(
        cui="C0221355", sctid=None,
        label="Grey matter heterotopia",
        synonyms=[
            "heterotopia", "grey matter heterotopia", "gray matter heterotopia",
            "periventricular nodular heterotopia", "PVNH", "subependymal heterotopia",
            "band heterotopia",
            # Batch A D4 — compound phrases
            "subependymal nodular heterotopia", "subcortical band heterotopia",
            "double cortex syndrome",
            "focal subcortical heterotopia",
            "bilateral periventricular nodular heterotopia",
            "gray matter heterotopia along the lateral ventricles",
            # schizencephaly / other malformations that co-occur
            "schizencephaly", "open-lip schizencephaly", "closed-lip schizencephaly",
            "unilateral schizencephaly", "bilateral schizencephaly",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "domain-knowledge:neuroradiology-standard",
        ],
    ),
    "lissencephaly": ConceptEntry(
        cui="C0266463", sctid=None,
        label="Lissencephaly",
        synonyms=[
            "lissencephaly", "agyria", "pachygyria",
            "lissencephaly-pachygyria complex",
            # Batch A D4 — compound phrases
            "classic lissencephaly", "type I lissencephaly",
            "cobblestone lissencephaly", "type II lissencephaly",
            "agyria-pachygyria complex",
            "smooth brain", "lissencephaly spectrum",
            "hemimegalencephaly", "unilateral hemimegalencephaly",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "domain-knowledge:neuroradiology-standard",
        ],
    ),
    "tuberous_sclerosis": ConceptEntry(
        cui="C0041341", sctid="63177008",
        label="Tuberous sclerosis complex (MRI features)",
        synonyms=[
            "tuberous sclerosis", "TSC", "cortical tubers", "subependymal nodules",
            "SEGA", "subependymal giant cell astrocytoma",
            # Batch A D4 — compound phrases
            "tuberous sclerosis complex", "TSC1", "TSC2",
            "radial migration lines", "subependymal nodule",
            "white-matter migration lines",
            "cortical tuber", "subcortical tuber",
            "multiple cortical tubers",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (Tuberous sclerosis, tuberous sclerosis)",
            "domain-knowledge:neuroradiology-standard",
        ],
    ),
    "other_lesion": ConceptEntry(
        cui="C1319851", sctid=None,
        label="Other MRI lesion",
        synonyms=[
            "abnormal MRI", "MRI lesion", "MRI abnormality",
            "signal abnormality",
            # Batch A D4 — Rasmussen and other acquired lesions
            "Rasmussen encephalitis", "Rasmussen syndrome",
            "progressive unilateral atrophy",
            "chronic focal encephalitis",
            "unilateral hemispheric atrophy",
            "post-encephalitic changes", "post-infectious changes",
            "post-inflammatory gliosis",
            "arachnoid cyst",
        ],
        source_provenance=[
            "ExECT-V2 seed C1319851",
            "domain-knowledge:standard-neurology-vocab",
            "domain-knowledge:neuroradiology-standard",
        ],
    ),
    "mri_negative": ConceptEntry(
        cui="C0436481", sctid=None,
        label="MRI-negative for structural lesion",
        synonyms=[
            "MRI negative", "MRI-negative epilepsy", "non-lesional MRI",
            "no epileptogenic lesion on MRI",
        ],
        source_provenance=["ExECT-V2 seed C0436481", "domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 14. DrugResistanceStatus (RULES_ONLY, 3 values, ILAE 2010)
# ---------------------------------------------------------------------------
DRUG_RESISTANCE_STATUS_ONTOLOGY: dict[str, ConceptEntry] = {
    "drug_responsive": ConceptEntry(
        cui="C1827389", sctid=None,
        label="Drug-responsive epilepsy (ILAE 2010)",
        synonyms=[
            "drug-responsive", "seizure-free on current ASM",
            "well-controlled", "responsive to medication",
            "epilepsy not refractory",
        ],
        source_provenance=["RULES_ONLY: DrugResistanceStatus", "ILAE 2010", "ExECT-V2 seed C1827389"],
    ),
    "undefined": ConceptEntry(
        cui=None, sctid=None,
        label="Drug-resistance status undefined",
        synonyms=[
            "drug resistance undefined",
            "insufficient ASM trials for classification",
        ],
        source_provenance=["RULES_ONLY: DrugResistanceStatus", "ILAE 2010"],
    ),
    "drug_resistant": ConceptEntry(
        cui="C1096063", sctid=None,
        label="Drug-resistant epilepsy (ILAE 2010)",
        synonyms=[
            "drug-resistant epilepsy", "DRE", "refractory epilepsy",
            "medically refractory epilepsy", "intractable epilepsy",
            "pharmacoresistant epilepsy", "failed two ASMs",
        ],
        source_provenance=["RULES_ONLY: DrugResistanceStatus", "ILAE 2010", "ExECT-V2 seed C1096063"],
    ),
}


# ---------------------------------------------------------------------------
# 15. MedicationStatus (5 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
MEDICATION_STATUS_ONTOLOGY: dict[str, ConceptEntry] = {
    "current": ConceptEntry(
        cui="C1720988", sctid="182840001",
        label="Currently taking",
        synonyms=[
            "current medication", "currently taking", "on", "is on",
            "current antiepileptic medication", "current anti-epileptic medication",
            "he is on", "she is on", "currently prescribed",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (Current antiepileptic medication, He is on, She is currently taking)",
        ],
    ),
    "prior": ConceptEntry(
        cui=None, sctid="410534003",
        label="Previously taken (historical)",
        synonyms=[
            "previous medication", "previously taken", "prior medication",
            "past medication", "used to take", "history of ASM",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "failed": ConceptEntry(
        cui=None, sctid=None,
        label="Failed medication",
        synonyms=[
            "failed", "failed trial of", "trial failed", "did not respond to",
            "ineffective", "not tolerated", "trial of X failed",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "ILAE 2010"],
    ),
    "discontinued_adverse_effect": ConceptEntry(
        cui=None, sctid=None,
        label="Discontinued due to adverse effect",
        synonyms=[
            "discontinued due to side effects", "stopped due to adverse effect",
            "intolerable side effects", "d/c'd for adverse effect",
            "withdrawn due to adverse reaction",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "planned": ConceptEntry(
        cui=None, sctid=None,
        label="Planned initiation",
        synonyms=[
            "planned to start", "will initiate", "to be started on",
            "plan to add", "will commence",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 16. SurgeryType (10 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
SURGERY_TYPE_ONTOLOGY: dict[str, ConceptEntry] = {
    "resection": ConceptEntry(
        cui="C0195028", sctid="107963003",
        label="Epilepsy resective surgery",
        synonyms=[
            "resection", "resective surgery", "anterior temporal lobectomy",
            "ATL", "temporal lobectomy", "amygdalohippocampectomy",
            "focal cortical resection", "lesionectomy", "frontal lobectomy",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "ILAE 2017"],
    ),
    "laser_ablation": ConceptEntry(
        cui=None, sctid=None,
        label="Laser interstitial thermal therapy (LITT)",
        synonyms=[
            "laser ablation", "LITT", "laser interstitial thermal therapy",
            "MRI-guided laser ablation", "Visualase ablation",
            "stereotactic laser ablation",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "disconnection": ConceptEntry(
        cui=None, sctid=None,
        label="Disconnection surgery",
        synonyms=[
            "disconnection", "multiple subpial transection", "MST",
            "hemispherotomy", "functional hemispherectomy (disconnection)",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "hemispherectomy": ConceptEntry(
        cui="C0195035", sctid="70536001",
        label="Hemispherectomy",
        synonyms=[
            "hemispherectomy", "anatomical hemispherectomy",
            "functional hemispherectomy", "hemispherotomy",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "callosotomy": ConceptEntry(
        cui="C0195037", sctid="230861005",
        label="Corpus callosotomy",
        synonyms=[
            "corpus callosotomy", "callosotomy", "anterior 2/3 callosotomy",
            "complete callosotomy",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "neurostimulation_vns": ConceptEntry(
        cui="C0949961", sctid="384719000",
        label="Vagus nerve stimulation (VNS)",
        synonyms=[
            "VNS", "vagus nerve stimulator", "vagus nerve stimulation",
            "vagal nerve stimulator", "AspireSR",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "neurostimulation_rns": ConceptEntry(
        cui=None, sctid=None,
        label="Responsive neurostimulation (RNS)",
        synonyms=[
            "RNS", "responsive neurostimulation", "responsive neurostimulator",
            "NeuroPace RNS", "cortical stimulator",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "neurostimulation_dbs": ConceptEntry(
        cui="C0524851", sctid=None,
        label="Deep brain stimulation (DBS)",
        synonyms=[
            "DBS", "deep brain stimulation", "deep brain stimulator",
            "anterior nucleus of thalamus DBS", "ANT-DBS",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "other": ConceptEntry(
        cui=None, sctid=None,
        label="Other epilepsy surgery",
        synonyms=["other epilepsy surgery", "epilepsy surgery, other"],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "unknown": ConceptEntry(
        cui=None, sctid=None,
        label="Prior epilepsy surgery, type unknown",
        synonyms=[
            "prior epilepsy surgery", "history of brain surgery for epilepsy",
            "previous surgery for seizures",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 17. ConcordanceStatus (RULES_ONLY)
# ---------------------------------------------------------------------------
CONCORDANCE_STATUS_ONTOLOGY: dict[str, ConceptEntry] = {
    "concordant": ConceptEntry(
        cui=None, sctid=None,
        label="Concordant multimodal localization",
        synonyms=[
            "concordant", "concordance between EEG and MRI",
            "MRI concordant with EEG", "multimodal concordance",
            "semiology concordant with EEG",
        ],
        source_provenance=["RULES_ONLY: ConcordanceStatus", "domain-knowledge:standard-neurology-vocab"],
    ),
    "partially_concordant": ConceptEntry(
        cui=None, sctid=None,
        label="Partially concordant localization",
        synonyms=[
            "partially concordant", "partial concordance",
            "EEG and MRI partially agree",
        ],
        source_provenance=["RULES_ONLY: ConcordanceStatus", "domain-knowledge:standard-neurology-vocab"],
    ),
    "discordant": ConceptEntry(
        cui=None, sctid=None,
        label="Discordant multimodal localization",
        synonyms=[
            "discordant", "MRI discordant with EEG",
            "EEG and MRI disagree", "multimodal discordance",
        ],
        source_provenance=["RULES_ONLY: ConcordanceStatus", "domain-knowledge:standard-neurology-vocab"],
    ),
    "not_assessed": ConceptEntry(
        cui=None, sctid=None,
        label="Multimodal concordance not assessed",
        synonyms=[
            "concordance not assessed", "no multimodal comparison",
        ],
        source_provenance=["RULES_ONLY: ConcordanceStatus"],
    ),
}


# ---------------------------------------------------------------------------
# 18. EtiologyCategory (6 values, CONCEPT_LINKED, ILAE 2017)
# ---------------------------------------------------------------------------
ETIOLOGY_CATEGORY_ONTOLOGY: dict[str, ConceptEntry] = {
    "structural": ConceptEntry(
        cui="C4524097", sctid=None,
        label="Structural etiology (ILAE 2017)",
        synonyms=[
            "structural epilepsy", "structural etiology", "structural cause",
            "post-traumatic epilepsy", "post-stroke epilepsy",
            "hippocampal sclerosis", "cortical dysplasia",
            "cavernoma", "traumatic brain injury", "stroke",
            "perinatal insult", "subarachnoid haemorrhage",
        ],
        source_provenance=[
            "ExECT-V2 seed C4524097", "ILAE 2017",
            "F-S train (stroke, traumatic brain injury 2005, perinatal insult)",
            "F-S train (cavernoma in the right temporal lobe, hippocampal sclerosis)",
        ],
    ),
    "genetic": ConceptEntry(
        cui="C0270850", sctid=None,
        label="Genetic etiology (ILAE 2017)",
        synonyms=[
            "genetic epilepsy", "genetic etiology", "idiopathic generalized epilepsy",
            "IGE", "SCN1A mutation", "Dravet syndrome",
            "juvenile myoclonic epilepsy", "JME", "genetic generalised epilepsy",
        ],
        source_provenance=["ExECT-V2 seed C0270850", "ILAE 2017", "domain-knowledge:standard-neurology-vocab"],
    ),
    "infectious": ConceptEntry(
        cui="C4510970", sctid=None,
        label="Infectious etiology (ILAE 2017)",
        synonyms=[
            "post-infectious epilepsy", "meningitis", "encephalitis",
            "herpes encephalitis", "neurocysticercosis", "cerebral abscess",
            "HSV encephalitis",
        ],
        source_provenance=[
            "ExECT-V2 seed C4510970", "ILAE 2017",
            "F-S train (meningitis, cerebral abcess)",
        ],
    ),
    "immune": ConceptEntry(
        cui="C4510729", sctid=None,
        label="Immune etiology (ILAE 2017)",
        synonyms=[
            "autoimmune epilepsy", "immune epilepsy", "autoimmune encephalitis",
            "anti-NMDA receptor encephalitis", "LGI1 encephalitis",
            "limbic encephalitis", "Rasmussen encephalitis",
        ],
        source_provenance=[
            "ExECT-V2 seed C4510729", "ILAE 2017", "Graus 2016",
            "F-S train (Herpes encephalitis)",
        ],
    ),
    "metabolic": ConceptEntry(
        cui="C1299598", sctid=None,
        label="Metabolic etiology (ILAE 2017)",
        synonyms=[
            "metabolic epilepsy", "metabolic etiology", "seizures due to metabolic disorder",
            "hypoglycemia-related seizure", "pyridoxine-dependent epilepsy",
            "GLUT1 deficiency", "mitochondrial disease",
        ],
        source_provenance=["ExECT-V2 seed C1299598", "ILAE 2017"],
    ),
    "unknown": ConceptEntry(
        cui=None, sctid=None,
        label="Unknown etiology (ILAE 2017)",
        synonyms=[
            "cryptogenic", "unknown cause", "etiology unknown",
            "cryptogenic epilepsy", "unknown etiology",
        ],
        source_provenance=[
            "ILAE 2017", "domain-knowledge:standard-neurology-vocab",
            "F-S train (dementia)",  # unknown-etiology-flagged case
        ],
    ),
}


# ---------------------------------------------------------------------------
# 19. FocalMotorOnset (7 values, CONCEPT_LINKED, ILAE 2017)
# ---------------------------------------------------------------------------
FOCAL_MOTOR_ONSET_ONTOLOGY: dict[str, ConceptEntry] = {
    "automatisms": ConceptEntry(
        cui="C0270837", sctid="193004006",
        label="Automatisms (ILAE 2017 focal motor onset)",
        synonyms=[
            "automatisms", "oroalimentary automatisms", "manual automatisms",
            "lip smacking", "chewing automatisms", "epileptic automatism",
        ],
        source_provenance=["ExECT-V2 seed C0270837", "ILAE 2017"],
    ),
    "atonic": ConceptEntry(
        cui="C0270846", sctid="42365007",
        label="Focal atonic seizure (ILAE 2017)",
        synonyms=[
            "focal atonic", "atonic focal seizure", "focal drop attack",
            "atonic component",
        ],
        source_provenance=["ExECT-V2 seed C0270846", "ILAE 2017"],
    ),
    "clonic": ConceptEntry(
        cui="C0752323", sctid=None,
        label="Focal clonic seizure (ILAE 2017)",
        synonyms=[
            "focal clonic", "clonic focal seizure", "focal jerking",
            "rhythmic focal jerking",
        ],
        source_provenance=["ExECT-V2 seed C0752323", "ILAE 2017"],
    ),
    "epileptic_spasms": ConceptEntry(
        cui="C1527366", sctid="28055006",
        label="Epileptic spasms, focal onset (ILAE 2017)",
        synonyms=[
            "epileptic spasms", "focal epileptic spasms",
            "focal-onset spasms", "salaam spasms (focal)",
        ],
        source_provenance=["ExECT-V2 seed C1527366", "ILAE 2017"],
    ),
    "hyperkinetic": ConceptEntry(
        cui=None, sctid=None,
        label="Focal hyperkinetic seizure (ILAE 2017)",
        synonyms=[
            "hyperkinetic seizure", "hypermotor seizure",
            "hyperkinetic focal seizure", "hypermotor focal seizure",
        ],
        source_provenance=["ILAE 2017", "domain-knowledge:standard-neurology-vocab"],
    ),
    "myoclonic": ConceptEntry(
        cui="C4317123", sctid="37356005",
        label="Focal myoclonic seizure (ILAE 2017)",
        synonyms=[
            "focal myoclonic", "focal myoclonic seizure",
            "focal myoclonic jerk", "focal myoclonus",
        ],
        source_provenance=["ExECT-V2 seed C4317123", "ILAE 2017"],
    ),
    "tonic": ConceptEntry(
        cui="C0752324", sctid=None,
        label="Focal tonic seizure (ILAE 2017)",
        synonyms=[
            "focal tonic", "focal tonic seizure", "asymmetric tonic posturing",
            "focal tonic posturing",
        ],
        source_provenance=["ExECT-V2 seed C0752324", "ILAE 2017"],
    ),
}


# ---------------------------------------------------------------------------
# 20. FocalNonmotorOnset (5 values, CONCEPT_LINKED, ILAE 2017)
# ---------------------------------------------------------------------------
FOCAL_NONMOTOR_ONSET_ONTOLOGY: dict[str, ConceptEntry] = {
    "autonomic": ConceptEntry(
        cui=None, sctid=None,
        label="Focal autonomic seizure (ILAE 2017)",
        synonyms=[
            "autonomic seizure", "focal autonomic seizure",
            "epigastric rising", "epigastric aura", "abdominal aura",
            "autonomic aura",
        ],
        source_provenance=["ILAE 2017", "domain-knowledge:standard-neurology-vocab"],
    ),
    "behavior_arrest": ConceptEntry(
        cui=None, sctid=None,
        label="Focal behavior arrest seizure (ILAE 2017)",
        synonyms=[
            "behavior arrest", "behaviour arrest seizure",
            "focal seizure with behavior arrest", "staring spell (focal)",
            "arrest of behavior",
        ],
        source_provenance=["ILAE 2017", "domain-knowledge:standard-neurology-vocab"],
    ),
    "cognitive": ConceptEntry(
        cui="C0422860", sctid="246536003",
        label="Focal cognitive seizure (ILAE 2017)",
        synonyms=[
            "cognitive seizure", "focal cognitive seizure",
            "déjà vu", "jamais vu", "dysphasic seizure",
            "aphasic aura", "cognitive aura",
        ],
        source_provenance=["ExECT-V2 seed C0422860", "ILAE 2017"],
    ),
    "emotional": ConceptEntry(
        cui="C4732752", sctid=None,
        label="Focal emotional seizure (ILAE 2017)",
        synonyms=[
            "focal emotional seizure", "emotional aura",
            "fear aura", "ictal fear", "ictal anxiety",
            "gelastic seizure",
        ],
        source_provenance=["ExECT-V2 seed C4732752", "ILAE 2017"],
    ),
    "sensory": ConceptEntry(
        cui="C0544645", sctid=None,
        label="Focal sensory seizure (ILAE 2017)",
        synonyms=[
            "sensory seizure", "focal sensory seizure", "sensory aura",
            "somatosensory seizure", "olfactory aura", "gustatory aura",
            "visual aura", "auditory aura",
        ],
        source_provenance=["ExECT-V2 seed C0544645", "ILAE 2017"],
    ),
}


# ---------------------------------------------------------------------------
# 21. EngelClass (13 values, RULES_ONLY, Engel 1993)
# ---------------------------------------------------------------------------
ENGEL_CLASS_ONTOLOGY: dict[str, ConceptEntry] = {
    "IA": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IA: completely seizure-free since surgery",
        synonyms=["Engel IA", "Engel Ia", "seizure-free since surgery"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IB": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IB: non-disabling simple partial seizures only",
        synonyms=["Engel IB", "Engel Ib", "auras only post-surgery"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IC": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IC: some disabling seizures after surgery but seizure-free ≥2 years",
        synonyms=["Engel IC", "Engel Ic"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "ID": ConceptEntry(
        cui=None, sctid=None,
        label="Engel ID: generalized convulsions with ASM withdrawal only",
        synonyms=["Engel ID", "Engel Id"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IIA": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IIA: initially free of disabling seizures, now rare",
        synonyms=["Engel IIA", "Engel IIa"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IIB": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IIB: rare disabling seizures since surgery",
        synonyms=["Engel IIB", "Engel IIb", "rare seizures post-op"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IIC": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IIC: more than rare disabling seizures but rare ≥2 years",
        synonyms=["Engel IIC", "Engel IIc"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IID": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IID: nocturnal seizures only",
        synonyms=["Engel IID", "Engel IId", "nocturnal seizures only"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IIIA": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IIIA: worthwhile seizure reduction",
        synonyms=["Engel IIIA", "Engel IIIa", "worthwhile improvement"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IIIB": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IIIB: prolonged seizure-free interval but <50% total follow-up",
        synonyms=["Engel IIIB", "Engel IIIb"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IVA": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IVA: significant seizure reduction",
        synonyms=["Engel IVA", "Engel IVa", "significant seizure reduction"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IVB": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IVB: no appreciable change",
        synonyms=["Engel IVB", "Engel IVb", "no significant change"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
    "IVC": ConceptEntry(
        cui=None, sctid=None,
        label="Engel IVC: worse after surgery",
        synonyms=["Engel IVC", "Engel IVc", "worse post-surgery"],
        source_provenance=["RULES_ONLY: EngelClass", "Engel 1993"],
    ),
}


# ---------------------------------------------------------------------------
# 22. IlaeOutcome (6 values, RULES_ONLY, Wieser 2001)
# ---------------------------------------------------------------------------
ILAE_OUTCOME_ONTOLOGY: dict[str, ConceptEntry] = {
    "1": ConceptEntry(
        cui=None, sctid=None,
        label="ILAE outcome class 1: completely seizure-free, no auras",
        synonyms=["ILAE class 1", "ILAE 1", "seizure-free without auras post-op"],
        source_provenance=["RULES_ONLY: IlaeOutcome", "Wieser 2001"],
    ),
    "2": ConceptEntry(
        cui=None, sctid=None,
        label="ILAE outcome class 2: only auras, no other seizures",
        synonyms=["ILAE class 2", "ILAE 2", "auras only post-op"],
        source_provenance=["RULES_ONLY: IlaeOutcome", "Wieser 2001"],
    ),
    "3": ConceptEntry(
        cui=None, sctid=None,
        label="ILAE outcome class 3: 1-3 seizure days/year, ± auras",
        synonyms=["ILAE class 3", "ILAE 3", "1 to 3 seizure days per year"],
        source_provenance=["RULES_ONLY: IlaeOutcome", "Wieser 2001"],
    ),
    "4": ConceptEntry(
        cui=None, sctid=None,
        label="ILAE outcome class 4: 4 seizure days/year to 50% reduction",
        synonyms=["ILAE class 4", "ILAE 4"],
        source_provenance=["RULES_ONLY: IlaeOutcome", "Wieser 2001"],
    ),
    "5": ConceptEntry(
        cui=None, sctid=None,
        label="ILAE outcome class 5: <50% reduction to 100% increase",
        synonyms=["ILAE class 5", "ILAE 5"],
        source_provenance=["RULES_ONLY: IlaeOutcome", "Wieser 2001"],
    ),
    "6": ConceptEntry(
        cui=None, sctid=None,
        label="ILAE outcome class 6: >100% increase of baseline",
        synonyms=["ILAE class 6", "ILAE 6", "worse than baseline"],
        source_provenance=["RULES_ONLY: IlaeOutcome", "Wieser 2001"],
    ),
}


# ---------------------------------------------------------------------------
# 23. NonDrugTherapyType (9 values, CONCEPT_LINKED)
# ---------------------------------------------------------------------------
NON_DRUG_THERAPY_TYPE_ONTOLOGY: dict[str, ConceptEntry] = {
    "ketogenic_diet": ConceptEntry(
        cui="C0011245", sctid="437931000124103",
        label="Ketogenic diet",
        synonyms=[
            "ketogenic diet", "keto diet", "classical ketogenic diet",
            "4:1 ketogenic diet",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "modified_atkins": ConceptEntry(
        cui=None, sctid=None,
        label="Modified Atkins diet",
        synonyms=[
            "modified Atkins diet", "MAD", "modified Atkins",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "low_glycemic_index": ConceptEntry(
        cui=None, sctid=None,
        label="Low glycemic index treatment",
        synonyms=[
            "low glycemic index treatment", "LGIT",
            "low-glycemic-index diet",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
    "ivig": ConceptEntry(
        cui="C0020971", sctid="333684004",
        label="Intravenous immunoglobulin",
        synonyms=[
            "IVIG", "IVIg", "intravenous immunoglobulin",
            "intravenous immune globulin",
        ],
        source_provenance=["RxNorm", "domain-knowledge:standard-neurology-vocab"],
    ),
    "plasmapheresis": ConceptEntry(
        cui="C0032202", sctid="14130001000004108",
        label="Plasmapheresis / plasma exchange",
        synonyms=[
            "plasmapheresis", "plasma exchange", "PLEX",
            "therapeutic plasma exchange", "TPE",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "Graus 2016"],
    ),
    "steroids": ConceptEntry(
        cui="C0038317", sctid="59058001",
        label="Corticosteroid therapy",
        synonyms=[
            "steroids", "corticosteroids", "high-dose steroids",
            "IV methylprednisolone", "prednisone", "prednisolone",
            "solumedrol",
        ],
        source_provenance=["RxNorm", "domain-knowledge:standard-neurology-vocab"],
    ),
    "rituximab": ConceptEntry(
        cui="C0393022", sctid="386919002",
        label="Rituximab",
        synonyms=["rituximab", "Rituxan", "MabThera"],
        source_provenance=["RxNorm 121191", "Graus 2016"],
    ),
    "acth": ConceptEntry(
        cui="C0001529", sctid=None,
        label="ACTH (adrenocorticotropic hormone)",
        synonyms=[
            "ACTH", "adrenocorticotropic hormone", "corticotropin",
            "H.P. Acthar Gel", "Acthar",
        ],
        source_provenance=["RxNorm", "domain-knowledge:standard-neurology-vocab"],
    ),
    "other": ConceptEntry(
        cui=None, sctid=None,
        label="Non-drug therapy, other",
        synonyms=["non-drug therapy other", "other non-pharmacologic treatment"],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# 24. CausativeAntibody (19 values, CONCEPT_LINKED, Graus 2016)
# ---------------------------------------------------------------------------
CAUSATIVE_ANTIBODY_ONTOLOGY: dict[str, ConceptEntry] = {
    "anti_lgi1": ConceptEntry(
        cui="C3494340", sctid=None,
        label="Anti-LGI1 antibody",
        synonyms=[
            "anti-LGI1", "LGI1 antibody", "leucine-rich glioma-inactivated 1 antibody",
            "anti-LGI1 encephalitis", "faciobrachial dystonic seizures antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_caspr2": ConceptEntry(
        cui="C3812876", sctid=None,
        label="Anti-CASPR2 antibody",
        synonyms=[
            "anti-CASPR2", "CASPR2 antibody", "contactin-associated protein-like 2 antibody",
            "anti-Caspr2", "Morvan syndrome antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_nmdar": ConceptEntry(
        cui="C4517211", sctid=None,
        label="Anti-NMDA receptor antibody",
        synonyms=[
            "anti-NMDAR", "anti-NMDA receptor", "NMDAR antibody",
            "N-methyl-D-aspartate receptor antibody", "anti-NMDA receptor encephalitis",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_gababr": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-GABA-B receptor antibody",
        synonyms=[
            "anti-GABA-B", "GABA-B receptor antibody", "anti-GABABR",
            "gamma-aminobutyric acid B receptor antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_ampar": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-AMPA receptor antibody",
        synonyms=[
            "anti-AMPAR", "AMPA receptor antibody", "anti-AMPA receptor",
            "α-amino-3-hydroxy-5-methyl-4-isoxazolepropionic acid receptor antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_dppx": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-DPPX antibody",
        synonyms=[
            "anti-DPPX", "DPPX antibody", "dipeptidyl-peptidase-like protein 6 antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_glyr": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-glycine receptor antibody",
        synonyms=[
            "anti-glycine receptor", "anti-GlyR", "glycine receptor antibody",
            "GlyR antibody", "PERM antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_iglon5": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-IgLON5 antibody",
        synonyms=[
            "anti-IgLON5", "IgLON5 antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_mglur5": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-mGluR5 antibody",
        synonyms=[
            "anti-mGluR5", "mGluR5 antibody",
            "metabotropic glutamate receptor 5 antibody",
            "Ophelia syndrome antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_hu": ConceptEntry(
        cui="C0201868", sctid=None,
        label="Anti-Hu (ANNA-1) antibody",
        synonyms=[
            "anti-Hu", "ANNA-1", "anti-neuronal nuclear antibody type 1",
            "Hu antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_ma2": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-Ma2 (Ta) antibody",
        synonyms=[
            "anti-Ma2", "Ma2 antibody", "anti-Ta", "PNMA2 antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_yo": ConceptEntry(
        cui="C0201865", sctid=None,
        label="Anti-Yo (PCA-1) antibody",
        synonyms=[
            "anti-Yo", "Yo antibody", "PCA-1",
            "Purkinje cell cytoplasmic antibody type 1",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_ri": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-Ri (ANNA-2) antibody",
        synonyms=[
            "anti-Ri", "Ri antibody", "ANNA-2",
            "anti-neuronal nuclear antibody type 2",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_amphiphysin": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-amphiphysin antibody",
        synonyms=["anti-amphiphysin", "amphiphysin antibody"],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_gad65": ConceptEntry(
        cui="C1531509", sctid=None,
        label="Anti-GAD65 antibody",
        synonyms=[
            "anti-GAD65", "GAD antibody", "GAD65 antibody",
            "glutamic acid decarboxylase antibody", "GADA",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_sox1": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-SOX1 antibody",
        synonyms=["anti-SOX1", "SOX1 antibody", "AGNA"],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_cv2": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-CV2 / CRMP5 antibody",
        synonyms=[
            "anti-CV2", "anti-CRMP5", "CRMP5 antibody", "CV2 antibody",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "anti_zic4": ConceptEntry(
        cui=None, sctid=None,
        label="Anti-Zic4 antibody",
        synonyms=["anti-Zic4", "Zic4 antibody"],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
    "other": ConceptEntry(
        cui=None, sctid=None,
        label="Other autoantibody (rare, per free-text)",
        synonyms=["other autoantibody", "unspecified autoantibody"],
        source_provenance=["Graus 2016"],
    ),
    "none_detected": ConceptEntry(
        cui=None, sctid=None,
        label="No autoantibody detected",
        synonyms=[
            "antibody negative", "no antibodies detected",
            "autoantibody panel negative", "seronegative",
        ],
        source_provenance=["Graus 2016", "domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# Supplementary ontologies — keyed by controlled surface term, not enum value.
# These populate free-text fields in the schema (etiology_details_text,
# semiology_text, medication.generic_name, comorbidities free-text, etc.)
# and feed the MedCAT CDB build directly. Each entry still carries CUI +
# provenance so the ontology stays traceable.
# ---------------------------------------------------------------------------

ETIOLOGY_DETAILS_ONTOLOGY: dict[str, ConceptEntry] = {
    "hippocampal_sclerosis": ConceptEntry(
        cui="C4749367", sctid="230368004",
        label="Hippocampal sclerosis (structural etiology detail)",
        synonyms=[
            "hippocampal sclerosis", "HS", "mesial temporal sclerosis", "MTS",
        ],
        source_provenance=[
            "ExECT-V2 seed C4749367", "ILAE 2017",
            "F-S train (hippocampal sclerosis)",
        ],
    ),
    "stroke": ConceptEntry(
        cui="C0038454", sctid="230690007",
        label="Stroke / cerebrovascular accident (structural etiology detail)",
        synonyms=[
            "stroke", "cerebrovascular accident", "CVA", "ischaemic stroke",
            "ischemic stroke", "MCA infarct", "cerebrovascular disease",
            "cerebrovascular dissease",  # F-S misspelling
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (stroke, cerebrovascular dissease, MCA infarct)",
        ],
    ),
    "traumatic_brain_injury": ConceptEntry(
        cui="C0876926", sctid="127295002",
        label="Traumatic brain injury (structural etiology detail)",
        synonyms=[
            "traumatic brain injury", "TBI", "head injury", "head trauma",
            "post-traumatic", "closed head injury", "minor head injury",
            "skull fracture",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (Traumatic brain injury, head injury, skull fracture)",
        ],
    ),
    "perinatal_insult": ConceptEntry(
        cui="C4511577", sctid=None,
        label="Perinatal anoxic-ischemic brain injury (structural etiology detail)",
        synonyms=[
            "perinatal insult", "perinatal hypoxia", "birth injury",
            "perinatal trauma", "hypoxic ischemic encephalopathy", "HIE",
            "perinatal anoxic injury",
        ],
        source_provenance=[
            "ExECT-V2 seed C4511577", "ILAE 2017",
            "F-S train (perinatal insult, perinatal trauma)",
        ],
    ),
    "cavernoma": ConceptEntry(
        cui="C0333282", sctid="253064006",
        label="Cerebral cavernous malformation",
        synonyms=[
            "cavernoma", "cavernous malformation", "cavernous angioma",
            "cerebral cavernoma", "CCM",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (cavernoma, cavernoma in the right temporal lobe)",
        ],
    ),
    "meningitis": ConceptEntry(
        cui="C0025289", sctid="7180009",
        label="Meningitis",
        synonyms=[
            "meningitis", "bacterial meningitis", "viral meningitis",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (meningitis)",
        ],
    ),
    "herpes_encephalitis": ConceptEntry(
        cui="C0019341", sctid="45170000",
        label="Herpes simplex encephalitis",
        synonyms=[
            "herpes encephalitis", "HSV encephalitis", "herpes simplex encephalitis",
            "HSE",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab", "Graus 2016",
            "F-S train (Herpes encephalitis)",
        ],
    ),
    "cerebral_abscess": ConceptEntry(
        cui="C0007765", sctid="18365005",
        label="Cerebral abscess",
        synonyms=[
            "cerebral abscess", "brain abscess", "cerebral abcess",  # F-S misspell
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (cerebral abcess)",
        ],
    ),
    "meningioma": ConceptEntry(
        cui="C0025286", sctid="20366004",
        label="Meningioma",
        synonyms=[
            "meningioma", "cranial meningioma", "intracranial meningioma",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (meningioma, meningioma resection)",
        ],
    ),
    "subarachnoid_haemorrhage": ConceptEntry(
        cui="C0038525", sctid="21454007",
        label="Subarachnoid haemorrhage",
        synonyms=[
            "subarachnoid haemorrhage", "subarachnoid hemorrhage", "SAH",
            "sub-arachnoid haemorrhage",  # F-S variant
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (Subarachnoid haemorrhage, sub-arachnoid haemorrhag)",
        ],
    ),
    "tuberous_sclerosis": ConceptEntry(
        cui="C0041341", sctid="63177008",
        label="Tuberous sclerosis complex",
        synonyms=[
            "tuberous sclerosis", "tuberous sclerosis complex", "TSC",
            "Bourneville's disease",
            # Batch A D2 — EPIO 2024 (CUI C0041341)
            "Epiloia", "Tuberose sclerosis", "Tuberous sclerosis syndrome",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab", "ILAE 2017",
            "F-S train (Tuberous sclerosis, tuberous sclerosis)",
            "EPIO 2024",
        ],
    ),
    "dementia": ConceptEntry(
        cui="C0002395", sctid="52448006",
        label="Dementia (as etiological comorbidity for late-onset epilepsy)",
        synonyms=[
            "dementia", "senile dementia", "cognitive decline",
            "Alzheimer disease",
            # Batch A D2 — EPIO 2024 (CUI C0002395)
            "Alzheimer's disease", "Alzheimers dementia",
        ],
        source_provenance=[
            "ExECT-V2 seed C0002395",
            "F-S train (Dementia, dementia)",
            "EPIO 2024",
        ],
    ),
    "glut1_deficiency": ConceptEntry(
        cui="C1847501", sctid=None,
        label="GLUT1 deficiency syndrome (metabolic etiology)",
        synonyms=[
            "GLUT1 deficiency", "GLUT1 deficiency syndrome",
            "De Vivo disease", "SLC2A1 deficiency",
        ],
        source_provenance=["ExECT-V2 seed C1847501", "ILAE 2017"],
    ),
    "pyridoxine_dependent_epilepsy": ConceptEntry(
        cui="C1849508", sctid=None,
        label="Pyridoxine-dependent epilepsy (metabolic etiology)",
        synonyms=[
            "pyridoxine-dependent epilepsy", "pyridoxine dependent epilepsy",
            "PDE", "vitamin B6-dependent seizures",
            # Batch A D2 — EPIO 2024 (CUI C1849508)
            "antiquitin deficiency", "AASA dehydrogenase deficiency", "EPD",
            "epilepsy, pyridoxine-dependent",
            "pyridoxine dependency", "pyridoxine dependency with seizures",
        ],
        source_provenance=[
            "ExECT-V2 seed C1849508", "ILAE 2017", "EPIO 2024",
        ],
    ),
    "mitochondrial_disease": ConceptEntry(
        cui="C0751651", sctid=None,
        label="Mitochondrial disease (metabolic etiology)",
        synonyms=[
            "mitochondrial disease", "mitochondrial encephalopathy",
            "MELAS", "MERRF",
        ],
        source_provenance=["ExECT-V2 seed C0751651", "ILAE 2017"],
    ),
    "measles_sspe": ConceptEntry(
        cui=None, sctid=None,
        label="Subacute sclerosing panencephalitis (post-measles)",
        synonyms=[
            "SSPE", "subacute sclerosing panencephalitis",
            "post-measles encephalitis",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (Measles)",
        ],
    ),
    "rasmussen_encephalitis": ConceptEntry(
        cui="C0393484", sctid=None,
        label="Rasmussen encephalitis",
        synonyms=[
            "Rasmussen encephalitis", "Rasmussen syndrome",
            "chronic focal encephalitis",
            # Batch A D2 — EPIO 2024 (CUI C0393484)
            "Rasmussen subacute encephalitis", "CFE", "RE",
        ],
        source_provenance=[
            "ExECT-V2 seed C0393484", "Graus 2016", "EPIO 2024",
        ],
    ),
    "neurocysticercosis": ConceptEntry(
        cui="C0270851", sctid=None,
        label="Neurocysticercosis",
        synonyms=["neurocysticercosis", "NCC", "cerebral cysticercosis"],
        source_provenance=["domain-knowledge:standard-neurology-vocab", "ILAE 2017"],
    ),
}

COMORBIDITY_ONTOLOGY: dict[str, ConceptEntry] = {
    "psychogenic_nonepileptic_seizures": ConceptEntry(
        cui=None, sctid="17470006",
        label="Psychogenic non-epileptic seizures (PNES)",
        synonyms=[
            "PNES", "psychogenic non-epileptic seizures",
            "psychogenic nonepileptic attacks", "dissociative seizures",
            "non-epileptic attacks", "non-epileptic attack disorder", "NEAD",
            "functional seizures",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (Dissociative seizures, non-epileptic psychogenic seizures,"
            " Psychogenic nonepileptic attack disorder, non-epileptic attacks)",
        ],
    ),
    "migraine": ConceptEntry(
        cui="C0149931", sctid="37796009",
        label="Migraine",
        synonyms=[
            "migraine", "migraines", "episodic migraine",
            "migraine headache", "chronic migraine",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (migraine, Migraine, Episodic migraine)",
        ],
    ),
    "diabetes": ConceptEntry(
        cui="C0011847", sctid="73211009",
        label="Diabetes mellitus",
        synonyms=[
            "diabetes", "diabetes mellitus", "DM", "type 1 diabetes",
            "type 2 diabetes", "T1DM", "T2DM",
        ],
        source_provenance=[
            "ExECT-V2 seed C0011847",
            "F-S train (Diabetes, diabetes, Type 1 diabetes)",
        ],
    ),
    "intellectual_disability": ConceptEntry(
        cui="C3714756", sctid="228156007",
        label="Intellectual disability / learning disability",
        synonyms=[
            "intellectual disability", "learning disability", "learning disabilities",
            "severe learning difficulties", "developmental delay",
            # Batch A D3 — HPO 2024 (HP:0001249 + severity subclasses)
            "mental retardation", "mental deficiency",
            "mental retardation, nonspecific",
            "dull intelligence", "low intelligence",
            "nonprogressive intellectual disability",
            "nonprogressive mental retardation",
            "mild intellectual disability", "intellectual disability, mild",
            "mild mental retardation", "mental retardation, mild",
            "moderate intellectual disability",
            "intellectual disability, moderate",
            "moderate mental retardation", "mental retardation, moderate",
            "severe intellectual disability",
            "intellectual disability, severe",
            "severe mental retardation", "mental retardation, severe",
            "profound intellectual disability",
            "intellectual disability, profound",
            "profound mental retardation", "mental retardation, profound",
        ],
        source_provenance=[
            "ExECT-V2 seed C3714756",
            "F-S train (Severe learning difficulties, learning disabilities)",
            "HPO 2024",
        ],
    ),
    "developmental_delay": ConceptEntry(
        cui="C0557874", sctid="248290001",
        label="Global developmental delay",
        synonyms=[
            "global developmental delay", "GDD", "developmental delay",
            # Batch A D3 — HPO 2024 (HP:0001263, HP:0002376)
            "cognitive delay", "delayed cognitive development",
            "delayed development", "delayed developmental milestones",
            "delayed intellectual development", "delayed milestones",
            "delayed psychomotor development",
            "developmental delay in early childhood",
            "developmental delay, global",
            "developmental retardation",
            "lack of psychomotor development",
            "mental and motor retardation",
            "motor and developmental delay",
            "psychomotor delay", "psychomotor developmental delay",
            "retarded development", "retarded mental development",
            "retarded psychomotor development",
            # Regression (HP:0002376)
            "developmental regression",
            "loss of acquired milestones", "loss of developmental milestones",
            "loss of milestones", "neurodevelopmental regression",
            "psychomotor regression",
        ],
        source_provenance=[
            "HPO 2024",
            "domain-knowledge:standard-neurology-vocab",
        ],
    ),
    "autism": ConceptEntry(
        cui="C0004352", sctid="35919005",
        label="Autism spectrum disorder",
        synonyms=[
            # Batch A D3 — HPO 2024 (HP:0000717) — verified label only
            "autism", "autism spectrum disorder", "ASD",
            "autistic disorder", "autistic spectrum disorder",
            "high-functioning autism", "Asperger syndrome",
        ],
        source_provenance=[
            "HPO 2024",
            "domain-knowledge:standard-neurology-vocab",
        ],
    ),
    "cognitive_impairment": ConceptEntry(
        cui="C0338656", sctid="386806002",
        label="Cognitive impairment",
        synonyms=[
            # Batch A D3 — HPO 2024 (HP:0100543)
            "cognitive impairment", "cognitive abnormality",
            "abnormality of cognition",
            "cognitive defects", "cognitive deficits",
            "intellectual impairment",
        ],
        source_provenance=[
            "HPO 2024",
            "domain-knowledge:standard-neurology-vocab",
        ],
    ),
    "anxiety_depression": ConceptEntry(
        cui="C0338908", sctid=None,
        label="Anxiety and depression",
        synonyms=[
            "anxiety", "depression", "anxiety with depression", "mood disorder",
            "major depression",
        ],
        source_provenance=["ExECT-V2 seed C0338908", "domain-knowledge:standard-neurology-vocab"],
    ),
    "iih": ConceptEntry(
        cui="C0033845", sctid="68267002",
        label="Idiopathic intracranial hypertension",
        synonyms=[
            "IIH", "idiopathic intracranial hypertension",
            "pseudotumor cerebri",
        ],
        source_provenance=["ExECT-V2 seed C0033845", "domain-knowledge:standard-neurology-vocab"],
    ),
    "hemiparesis": ConceptEntry(
        cui="C0018989", sctid="127377007",
        label="Hemiparesis",
        synonyms=["hemiparesis", "hemiplegia", "unilateral weakness"],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (hemiparesis)",
        ],
    ),
    "hydrocephalus": ConceptEntry(
        cui="C0020255", sctid="230745008",
        label="Hydrocephalus",
        synonyms=["hydrocephalus", "obstructive hydrocephalus"],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (Hydrocephalus)",
        ],
    ),
    "febrile_seizures": ConceptEntry(
        cui="C0585108", sctid="14135000",
        label="Febrile seizures (history)",
        synonyms=[
            "febrile seizures", "febrile convulsions", "febrile seizure",
            "recurrent febrile fit",
        ],
        source_provenance=[
            "ExECT-V2 seed C0585108",
            "F-S train (febrile seizures)",
        ],
    ),
    "ischaemic_heart_disease": ConceptEntry(
        cui="C0151744", sctid="414545008",
        label="Ischaemic heart disease",
        synonyms=[
            "ischaemic heart disease", "ischemic heart disease", "IHD",
            "coronary artery disease", "CAD",
        ],
        source_provenance=[
            "domain-knowledge:standard-neurology-vocab",
            "F-S train (ischaemic heart disease)",
        ],
    ),
    "status_epilepticus_history": ConceptEntry(
        cui="C0038220", sctid="230456007",
        label="History of status epilepticus",
        synonyms=[
            "status epilepticus", "SE", "convulsive status epilepticus",
            "history of status", "prolonged seizure requiring hospitalization",
        ],
        source_provenance=[
            "ExECT-V2 seed C0038220", "ILAE 2017",
        ],
    ),
    "sudep_risk": ConceptEntry(
        cui="C4304727", sctid=None,
        label="Sudden unexpected death in epilepsy (SUDEP; risk counseling)",
        synonyms=[
            "SUDEP", "sudden unexpected death in epilepsy",
            "sudden unexplained death in epilepsy",
        ],
        source_provenance=["ExECT-V2 seed C4304727", "ILAE 2017"],
    ),
}

BIRTH_HISTORY_ONTOLOGY: dict[str, ConceptEntry] = {
    "term_birth": ConceptEntry(
        cui="C0233324", sctid="30039006",
        label="Term birth (≥37 weeks)",
        synonyms=[
            "born at term", "term birth", "term delivery",
            "full-term delivery", "normal spontaneous vaginal delivery",
            "NSVD",
        ],
        source_provenance=["ExECT-V2 seed C0233324", "domain-knowledge:standard-neurology-vocab"],
    ),
    "preterm_birth": ConceptEntry(
        cui="C0151526", sctid="399261000",
        label="Preterm birth (<37 weeks)",
        synonyms=[
            "preterm birth", "premature birth", "premature delivery",
            "preterm delivery", "premature",
        ],
        source_provenance=[
            "ExECT-V2 seed C0151526",
            "F-S train (premature delivery)",
        ],
    ),
    "late_preterm_birth": ConceptEntry(
        cui="C3829315", sctid=None,
        label="Late preterm birth (34-36+6 wks)",
        synonyms=["late preterm birth", "late preterm delivery"],
        source_provenance=["ExECT-V2 seed C3829315", "domain-knowledge:standard-neurology-vocab"],
    ),
    "very_preterm_birth": ConceptEntry(
        cui="C4053870", sctid=None,
        label="Very preterm birth (28-31+6 wks)",
        synonyms=["very preterm birth", "very preterm delivery"],
        source_provenance=["ExECT-V2 seed C4053870", "domain-knowledge:standard-neurology-vocab"],
    ),
    "extreme_preterm_birth": ConceptEntry(
        cui="C4055046", sctid=None,
        label="Extreme preterm birth (<28 wks)",
        synonyms=["extreme preterm birth", "extreme prematurity", "extremely premature"],
        source_provenance=["ExECT-V2 seed C4055046", "domain-knowledge:standard-neurology-vocab"],
    ),
    "birth_trauma": ConceptEntry(
        cui=None, sctid=None,
        label="Birth trauma / perinatal complication",
        synonyms=[
            "birth trauma", "perinatal complication", "difficult delivery",
            "instrumental delivery",
        ],
        source_provenance=["domain-knowledge:standard-neurology-vocab"],
    ),
}


# ---------------------------------------------------------------------------
# Registry — all 24 enums
# ---------------------------------------------------------------------------
def all_enum_ontologies() -> dict[str, dict[str, ConceptEntry]]:
    """Return the full 24-enum ontology registry.

    Keys are the enum class names (as in ``schema/enums.py``). Values are
    dicts keyed by the enum's string ``.value``. Every enum in the schema
    appears here — rules-only enums included, even though their concept
    entries lack CUI/SCTID anchors.
    """
    return {
        "DocumentType": DOCUMENT_TYPE_ONTOLOGY,
        "Certainty": CERTAINTY_ONTOLOGY,
        "TemporalStatus": TEMPORAL_STATUS_ONTOLOGY,
        "EpilepsyType": EPILEPSY_TYPE_ONTOLOGY,
        "SeizureType": SEIZURE_TYPE_ONTOLOGY,
        "Awareness": AWARENESS_ONTOLOGY,
        "Laterality": LATERALITY_ONTOLOGY,
        "LobarLocalization": LOBAR_LOCALIZATION_ONTOLOGY,
        "LocalizationSource": LOCALIZATION_SOURCE_ONTOLOGY,
        "EegStudyType": EEG_STUDY_TYPE_ONTOLOGY,
        "EegBackground": EEG_BACKGROUND_ONTOLOGY,
        "IedType": IED_TYPE_ONTOLOGY,
        "MriFinding": MRI_FINDING_ONTOLOGY,
        "DrugResistanceStatus": DRUG_RESISTANCE_STATUS_ONTOLOGY,
        "MedicationStatus": MEDICATION_STATUS_ONTOLOGY,
        "SurgeryType": SURGERY_TYPE_ONTOLOGY,
        "ConcordanceStatus": CONCORDANCE_STATUS_ONTOLOGY,
        "EtiologyCategory": ETIOLOGY_CATEGORY_ONTOLOGY,
        "FocalMotorOnset": FOCAL_MOTOR_ONSET_ONTOLOGY,
        "FocalNonmotorOnset": FOCAL_NONMOTOR_ONSET_ONTOLOGY,
        "EngelClass": ENGEL_CLASS_ONTOLOGY,
        "IlaeOutcome": ILAE_OUTCOME_ONTOLOGY,
        "NonDrugTherapyType": NON_DRUG_THERAPY_TYPE_ONTOLOGY,
        "CausativeAntibody": CAUSATIVE_ANTIBODY_ONTOLOGY,
    }


def supplementary_ontologies() -> dict[str, dict[str, ConceptEntry]]:
    """Return non-enum-keyed ontologies used for free-text fields and the
    MedCAT CDB build (medications, etiology details, comorbidities, birth
    history). These are NOT enum-value maps — keys here are controlled
    surface terms — and therefore do not appear in the enum-coverage tests.
    """
    return {
        "Medication": MEDICATION_ONTOLOGY,
        "EtiologyDetails": ETIOLOGY_DETAILS_ONTOLOGY,
        "Comorbidity": COMORBIDITY_ONTOLOGY,
        "BirthHistory": BIRTH_HISTORY_ONTOLOGY,
    }


def total_concept_count() -> int:
    """Total ConceptEntry rows across enum and supplementary ontologies."""
    n = sum(len(o) for o in all_enum_ontologies().values())
    n += sum(len(o) for o in supplementary_ontologies().values())
    return n


# ---------------------------------------------------------------------------
# Additional medication ontology — not a schema enum, but essential for the
# CDB build. Keyed by generic (RxNorm-preferred) name. Included here so the
# rules pipeline has a single vocabulary source. Medications extracted are
# stored in Medication.generic_name (free text) with optional rxnorm_cui.
# ---------------------------------------------------------------------------
MEDICATION_ONTOLOGY: dict[str, ConceptEntry] = {
    "lamotrigine": ConceptEntry(
        cui="C0064636", sctid="386859008",
        label="Lamotrigine",
        synonyms=[
            "lamotrigine", "Lamictal", "LTG",
            "lamotiringe",  # F-S 40 misspelling (EA0193)
            "lamotrigin",   # UK abbreviated
        ],
        source_provenance=[
            "ExECT-V2 seed C0064636", "RxNorm 28439",
            "F-S train (Lamotrigine, Lamictal)",
            "F-S test EA0193 (lamotiringe)",
        ],
    ),
    "levetiracetam": ConceptEntry(
        cui="C0377265", sctid="386846007",
        label="Levetiracetam",
        synonyms=["levetiracetam", "Keppra", "LEV"],
        source_provenance=[
            "ExECT-V2 seed C0377265", "RxNorm 114477",
            "F-S train (levetiracetam, Keppra)",
        ],
    ),
    "carbamazepine": ConceptEntry(
        cui="C0006949", sctid="386887009",
        label="Carbamazepine",
        synonyms=[
            "carbamazepine", "Tegretol", "CBZ", "Carbatrol",
            "carbamazapine",  # F-S 40 misspelling (EA0195)
        ],
        source_provenance=[
            "ExECT-V2 seed C0006949", "RxNorm 2002",
            "F-S train (carbamazepine, Tegretol)",
            "F-S test EA0195 (carbamazapine)",
        ],
    ),
    "oxcarbazepine": ConceptEntry(
        cui="C0069751", sctid="386854003",
        label="Oxcarbazepine",
        synonyms=["oxcarbazepine", "Trileptal", "OXC"],
        source_provenance=["ExECT-V2 seed C0069751", "RxNorm 32624", "F-S train (Oxcarbazepin)"],
    ),
    "sodium_valproate": ConceptEntry(
        cui="C0037567", sctid="386842001",
        label="Sodium valproate / Valproic acid",
        synonyms=[
            "sodium valproate", "valproic acid", "valproate", "divalproex",
            "Depakote", "Depakene", "Epilim", "VPA",
        ],
        source_provenance=[
            "ExECT-V2 seed C0037567", "ExECT-V2 seed C0591451 (Epilim)",
            "RxNorm 11118",
            "F-S train (sodium valproate, Epilim)",
        ],
    ),
    "topiramate": ConceptEntry(
        cui="C0076829", sctid="386845005",
        label="Topiramate",
        synonyms=["topiramate", "Topamax", "TPM"],
        source_provenance=[
            "ExECT-V2 seed C0076829", "RxNorm 38404",
            "F-S train (Topiramate, Topamax)",
        ],
    ),
    "zonisamide": ConceptEntry(
        cui="C0078844", sctid="386853009",
        label="Zonisamide",
        synonyms=[
            "zonisamide", "Zonegran", "ZNS",
            "Zonismaide",  # F-S 40 misspelling (EA0188)
            "zonsiamide",  # F-S 40 misspelling (EA0174)
        ],
        source_provenance=[
            "ExECT-V2 seed C0078844", "RxNorm 42347",
            "F-S train (Zonisamide, Zonegran)",
        ],
    ),
    "phenytoin": ConceptEntry(
        cui="C0031507", sctid="386854003",
        label="Phenytoin",
        synonyms=["phenytoin", "Dilantin", "PHT"],
        source_provenance=[
            "ExECT-V2 seed C0031507", "RxNorm 8183",
            "F-S train (Phenytoin)",
        ],
    ),
    "clobazam": ConceptEntry(
        cui="C0055891", sctid="387042000",
        label="Clobazam",
        synonyms=["clobazam", "Onfi", "CLB"],
        source_provenance=[
            "ExECT-V2 seed C0055891", "RxNorm 2597",
            "F-S train (Clobazam, clobazam)",
        ],
    ),
    "brivaracetam": ConceptEntry(
        cui="C1699861", sctid=None,
        label="Brivaracetam",
        synonyms=[
            "brivaracetam", "Briviact", "BRV",
            "Brivetiracetam",  # F-S train misspelling
            "Brivitiracetam",  # F-S 40 misspelling (EA0188)
            "briviteracetam",  # F-S 40 misspelling (EA0188)
            "brivaracetam",
        ],
        source_provenance=[
            "ExECT-V2 seed C1699861", "RxNorm 1741248",
            "F-S train (Brivaracetam, Brivetiracetam)",
            "F-S test EA0188 (Brivitiracetam, briviteracetam)",
        ],
    ),
    "perampanel": ConceptEntry(
        cui="C2698764", sctid=None,
        label="Perampanel",
        synonyms=["perampanel", "Fycompa"],
        source_provenance=[
            "ExECT-V2 seed C2698764", "RxNorm 1373737",
            "F-S train (Perampanel)",
        ],
    ),
    "lacosamide": ConceptEntry(
        cui="C0893761", sctid=None,
        label="Lacosamide",
        synonyms=["lacosamide", "Vimpat", "LCM"],
        source_provenance=["ExECT-V2 seed C0893761", "RxNorm 727708"],
    ),
    "gabapentin": ConceptEntry(
        cui="C0060926", sctid="386896005",
        label="Gabapentin",
        synonyms=["gabapentin", "Neurontin", "GBP"],
        source_provenance=["ExECT-V2 seed C0060926", "RxNorm 25480"],
    ),
    "pregabalin": ConceptEntry(
        cui="C0657912", sctid=None,
        label="Pregabalin",
        synonyms=["pregabalin", "Lyrica", "PGB"],
        source_provenance=["ExECT-V2 seed C0657912", "RxNorm 187832"],
    ),
    "eslicarbazepine": ConceptEntry(
        cui="C2725260", sctid=None,
        label="Eslicarbazepine acetate",
        synonyms=["eslicarbazepine", "eslicarbazepine acetate", "Aptiom", "Zebinix"],
        source_provenance=[
            "ExECT-V2 seed C2725260", "RxNorm 1160723",
            "F-S train (Eslicarbazepine 800mg od)",
        ],
    ),
    "clonazepam": ConceptEntry(
        cui="C0009011", sctid="387248006",
        label="Clonazepam",
        synonyms=["clonazepam", "Klonopin", "Rivotril", "CZP"],
        source_provenance=["ExECT-V2 seed C0009011", "RxNorm 2598"],
    ),
    "phenobarbital": ConceptEntry(
        cui="C0031412", sctid="387519009",
        label="Phenobarbital",
        synonyms=["phenobarbital", "phenobarbitone", "Luminal", "PB"],
        source_provenance=["ExECT-V2 seed C0031412", "RxNorm 8134"],
    ),
    "midazolam": ConceptEntry(
        cui="C0026056", sctid="373476007",
        label="Midazolam",
        synonyms=["midazolam", "Versed"],
        source_provenance=[
            "ExECT-V2 seed C0026056", "RxNorm 6960",
            "F-S train (Midazolam)",
        ],
    ),
    "ethosuximide": ConceptEntry(
        cui="C0015043", sctid="387139008",
        label="Ethosuximide",
        synonyms=["ethosuximide", "Zarontin", "ESM"],
        source_provenance=["ExECT-V2 seed C0015043", "RxNorm 4064"],
    ),
    "vigabatrin": ConceptEntry(
        cui="C0048044", sctid="386850004",
        label="Vigabatrin",
        synonyms=["vigabatrin", "Sabril", "VGB"],
        source_provenance=["ExECT-V2 seed C0048044", "RxNorm 39998"],
    ),
    "tiagabine": ConceptEntry(
        cui="C0068897", sctid="386849004",
        label="Tiagabine",
        synonyms=["tiagabine", "Gabitril", "TGB"],
        source_provenance=["ExECT-V2 seed C0068897", "RxNorm 39897"],
    ),
    "felbamate": ConceptEntry(
        cui="C0060135", sctid="386866009",
        label="Felbamate",
        synonyms=["felbamate", "Felbatol", "FBM"],
        source_provenance=["ExECT-V2 seed C0060135", "RxNorm 25171"],
    ),
    "primidone": ConceptEntry(
        cui="C0033148", sctid="387327000",
        label="Primidone",
        synonyms=["primidone", "Mysoline", "PRM"],
        source_provenance=["ExECT-V2 seed C0033148", "ExECT-V2 seed C0700016 (Mysolin)", "RxNorm 8815"],
    ),
    "stiripentol": ConceptEntry(
        cui="C0075262", sctid=None,
        label="Stiripentol",
        synonyms=["stiripentol", "Diacomit", "STP"],
        source_provenance=["ExECT-V2 seed C0075262", "RxNorm 226921"],
    ),
    "rufinamide": ConceptEntry(
        cui="C0213404", sctid=None,
        label="Rufinamide",
        synonyms=["rufinamide", "Banzel", "Inovelon", "RUF"],
        source_provenance=["ExECT-V2 seed C0213404", "RxNorm 400732"],
    ),
}

try:
    from .epilepsy_ontology_umls_overrides import apply as _apply_umls_overrides
    _apply_umls_overrides()
except ImportError:
    pass
