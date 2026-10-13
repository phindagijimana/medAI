"""LEO phenotype catalogue: what a user can ask LEO to extract, by name.

Two kinds of predefined phenotype, kept apart because they carry different evidence:

* **extract** phenotypes are read by the full LEO chain (LLM + EpExtra specialist + ontology),
  fused and verified.  Each carries an ``evidence`` level that says what has actually been measured:
  ``measured`` (own accuracy against gold, numbers in ``services.leo_evidence``), ``rules_only`` (the
  specialist alone was scored against synthetic or F-S gold, no LLM; ``eval/results/leo_extra_phenotypes.md`` and
  ``leo_plan_phenotypes.md``),
  ``indirect`` (only its effect on another field was measured) or ``none`` (nothing measured).  Six are ``measured``.  The
  level is shown in the UI, ``leo phenotypes`` and the About sheet.
* **ask** phenotypes are questions put to the LLM alone, with a verbatim quote that is checked
  against the note.  Nothing cross-checks them, so LEO marks every answer for review.  Users can
  also type their own question.

Panels are named sets of extract phenotypes for the UI and the CLI.  Pure data, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Phenotype:
    id: str                      # column prefix in the output table
    label: str
    field_paths: tuple[str, ...]  # Claim.field_path values that feed this column
    kind: str                    # scalar | list | frequency | bool
    definition: str              # one plain sentence for the UI and the About sheet
    evidence: str = "none"       # measured | indirect | none  (what has been measured; see leo_evidence)
    tags: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()   # keys of REFERENCES that define the categories
    note: str = ""               # plain caveat shown next to the evidence level
    derived: bool = False        # value is computed by a rule from other findings, not read from one span


# Only sources whose bibliographic details are confirmed (docs/REFERENCES.md).
REFERENCES: dict[str, str] = {
    "ilae2017_seizure": "Fisher RS et al. Operational classification of seizure types by the International League "
                        "Against Epilepsy. Epilepsia 2017;58(4):522-530.",
    "ilae2017_epilepsies": "Scheffer IE et al. ILAE classification of the epilepsies: position paper of the ILAE "
                           "Commission for Classification and Terminology. Epilepsia 2017;58(4):512-521.",
    "ilae2010_drug_resistance": "Kwan P et al. Definition of drug resistant epilepsy: consensus proposal by the ad hoc "
                                "Task Force of the ILAE Commission on Therapeutic Strategies. Epilepsia 2010;51(6):1069-1077.",
}

_M = "measured"
_I = "indirect"
_NOTE_RESCUE = ("Specialist alone, F-S letters (As_Required prescriptions): 9 in 200 letters, so only a rough guide. "
                "6 found right, 6 false alarms (one a naming mismatch, two a letter merely suggesting a drug), 3 missed "
                "(docs/EVAL_PROTOCOL_LEO.md 10.16).")
_NOTE_ACUTE = ("No accuracy of its own was measured. The rule moved no drug in 40 F-S letters (10.6); it is a "
               "text-pattern rule written from guidelines.")
_R = "rules_only"
_SYN = ("Synthetic notes, each patient's notes joined, rules only (no LLM). Held-out figures are 80 patients the rules "
        "were not adjusted on (leo_extra_phenotypes_ext). ")
_EXT = ("Synthetic LLM-written notes from an extended plan (v4_ext, 37 patients), rules only, no LLM; the examples "
        "were read after scoring, so these notes are no longer a clean test. ")
_NOTE_PRIOR = ("Specialist alone on synthetic polish notes (the rules were developed on them): recall 0.89 on 90 patients "
               "and 0.80 on 10 held out; precision 0.54 and 0.42 but a lower bound. A stopped drug was listed as current "
               "for 25 of 90 patients (10.16).")

EXTRACT: tuple[Phenotype, ...] = (
    Phenotype("epilepsy_type", "Epilepsy type", ("clinical_seizure.epilepsy_type",), "scalar",
              "Focal, generalized, combined generalized and focal, or unknown (ILAE 2017 epilepsy types).", _M,
              ("core", "seizure"), ("ilae2017_epilepsies",),
              "Unknown means the note says epilepsy but names no type (25 of 38 F-S letters). The rules give "
              "unknown there; the model (prompt v1) cannot, so those cells go to review (see Evidence)."),
    Phenotype("seizure_type", "Predominant seizure type", ("clinical_seizure.predominant_seizure_type",),
              "scalar", "The seizure type the note treats as the main one, using ILAE 2017 operational names.",
              _M, ("core", "seizure"), ("ilae2017_seizure",),
              "Small samples; the specialist and the LLM often disagree on this field."),
    Phenotype("seizure_onset_class", "Seizure onset class", ("clinical_seizure.seizure_onset_class",),
              "scalar", "Focal, generalized or unknown onset: the first level of the ILAE 2017 seizure type.",
              _M, ("seizure",), ("ilae2017_seizure",),
              "Taken from each reader's seizure type and fused on its own, so it can be accepted when the readers "
              "agree on the class but not on the subtype. Only 18 of 40 held-out letters have a gold seizure type.",
              derived=True),
    Phenotype("other_seizure_types", "Other seizure types", ("clinical_seizure.other_seizure_types",),
              "list", "Further ILAE 2017 seizure types named besides the predominant one.",
              _R, ("seizure",), ("ilae2017_seizure",),
              "Weak. Specialist alone; F-S letters F1 0.00 after gating (n=5). Do not rely on this column without review."),
    Phenotype("awareness", "Awareness during seizures", ("clinical_seizure.awareness",),
              "scalar", "Retained, impaired or unknown (ILAE 2017 awareness classifier).",
              _R, ("seizure",), ("ilae2017_seizure",),
              "Specialist and the extra model reader (P1C) when that reader is on. MTSamples silver F1 0.50 (n=9); always review."),
    Phenotype("age_at_onset", "Age at seizure onset (years)", ("clinical_seizure.age_at_onset_years",),
              "scalar", "Age when seizures began.", _M, ("core", "seizure"), (),
              "Only 4 held-out F-S letters state an onset age, so that estimate is very uncertain."),
    Phenotype("seizure_frequency", "Current seizure frequency", ("clinical_seizure.seizure_frequency",),
              "frequency", "How often seizures occur now: counts per day, week, month or year, or seizure free.",
              _M, ("core", "seizure")),
    Phenotype("seizure_free", "Seizure free now", ("clinical_seizure.seizure_free",), "bool",
              "Whether the patient is currently seizure free (no seizures of any type), read from each reader's "
              "current seizure frequency.", _M, ("seizure",), (),
              "Fused on its own, so the readers can agree the patient is not seizure free while disagreeing on the "
              "rate. 29 of 40 held-out F-S letters have a gold value; the model alone reads it better than the rules "
              "(see Evidence).", derived=True),
    Phenotype("pnes_status", "PNES documented", ("clinical_seizure.pnes_status",), "scalar",
              "Whether the note documents psychogenic non-epileptic (dissociative, functional) seizures: PNES only, "
              "PNES with epilepsy, or PNES raised as a possibility.", "none", ("seizure",), (),
              "Rules only, no gold label. When PNES is documented, seizure-count cells (and, for PNES only, seizure "
              "type, onset class and epilepsy type) are never auto-accepted. On the 160 F-S development letters the "
              "flag matched a manual reading of all 16 letters that mention PNES."),
    Phenotype("date_of_last_seizure", "Date of last seizure", ("clinical_seizure.date_of_last_seizure",), "scalar",
              "The latest explicit date of a last seizure (\"last event July 2016\", \"no seizures since Christmas "
              "2015\"), at the precision the note gives.", _M, ("seizure",), (),
              "Rules only; the model does not read it, so it is always reviewed when the model ran. Explicit dates only: "
              "\"seizure free for 7 months\" gives no date. Only 4 held-out F-S letters have a gold date (3 right); "
              "all 14 development letters right (eval/results/leo_last_seizure_fs200.md)."),
    Phenotype("current_asms", "Current maintenance ASMs", ("medication.current_asms",), "list",
              "Daily anti-seizure medicines the patient takes now. Rescue and one-off doses are separate.",
              _M, ("core", "medication"), (),
              "Whether a rescue drug counts as current differs between the two test sets; see Evidence."),
    Phenotype("rescue_medication", "Rescue medication", ("medication.rescue_medication",), "list",
              "As-needed seizure-rescue drugs (PRN, buccal, intranasal, rectal).", _R, ("medication",), (),
              _NOTE_RESCUE),
    Phenotype("acute_administration", "One-off administration", ("medication.acute_administration",), "list",
              "A drug given once during the encounter (IV load, ED dose). Always listed for review.",
              _I, ("medication",), (), _NOTE_ACUTE),
    Phenotype("prior_asms", "Prior (stopped) ASMs", ("medication.prior_asms",), "list",
              "ASMs the patient used before and no longer takes.", _R, ("medication",), (), _NOTE_PRIOR),
    Phenotype("failed_asms", "Failed ASMs", ("medication.failed_asms",), "list",
              "ASMs stopped for lack of effect or side effects.", _R, ("medication",), (),
              "Weak. Synthetic polish notes: a drug stopped for lack of effect was labelled as such for 4 of 23 "
              "(called a side effect for 12); against the ILAE sense of failure precision 0.40, recall 0.15. "
              "Do not rely on this column without review (10.16)."),
    Phenotype("drug_resistance", "Drug resistance status", ("medication.drug_resistance_status",), "scalar",
              "Drug responsive, drug resistant or undefined, worked out by a rule from the ASM history and seizure status "
              "(an approximation of the ILAE 2010 definition).", _R, ("medication",), ("ilae2010_drug_resistance",),
              _SYN + "Held-out: right for 76 of 80 (4 responsive patients called resistant). Read from the note's own "
              "statement (\"drug-resistant\", \"drug-responsive\"), or inferred from the ASM history when the note makes none; an "
              "inferred value has a rule description as evidence and cannot judge whether a trial was adequate or tolerated.", True),
    Phenotype("etiology_category", "Etiology category", ("clinical_seizure.etiology_category",), "scalar",
              "Structural, genetic, infectious, immune, metabolic or unknown (ILAE 2017 etiologies).", _R, ("etiology",),
              ("ilae2017_epilepsies",),
              _SYN + "Held-out: right for 77 of 80; all 3 errors name a structural cause where the reference says unknown."),
    Phenotype("etiology_details", "Etiology details", ("clinical_seizure.etiology_details_text",), "scalar",
              "Free-text etiology as written in the note.", _R, ("etiology",), (),
              "Presence only, on 200 F-S letters: found a stated cause for 24 of 28, but 51 more where the F-S "
              "annotators marked none (precision 0.32; part annotation convention, not separated). Synthetic gene, "
              "variant and antibody values were right for all 27 patients that have one (10.16)."),
    Phenotype("semiology", "Seizure semiology (text)", ("clinical_seizure.semiology_text",), "scalar",
              "How the seizure looks, as written in the note.", _R, ("seizure",), (),
              _EXT + "Lenient key-word check: of the plan's motor features that the notes mention, 19 of 34 were in the "
              "semiology text, and 3 of 13 auras (10.17). Also read by F1C when the extra reader is on."),
    Phenotype("focal_motor_onset", "Focal motor onset", ("clinical_seizure.focal_motor_onset",), "scalar",
              "Motor feature at focal onset (ILAE 2017 seizure classification).", _R, ("seizure",), ("ilae2017_seizure",),
              _EXT + "Right for 7 of 12 patients that have one (3 wrong, 2 missing; 10.21). "
              "Held-out half (odd patient numbers, 5 patients): 2 right, 2 wrong, 1 missing. "
              "The rule now needs an onset cue or a 'focal seizure with X' phrasing, so later evolution is less often called onset."),
    Phenotype("focal_nonmotor_onset", "Focal non-motor onset", ("clinical_seizure.focal_nonmotor_onset",),
              "scalar", "Non-motor feature at focal onset (ILAE 2017 seizure classification).", _R, ("seizure",),
              ("ilae2017_seizure",), _EXT + "Right for 11 of 15 patients that have one (4 wrong; 8 of 15 before the onset-cue "
              "rule, 10.21). Held-out half (6 patients): all 6 right."),
    Phenotype("eeg_study_type", "EEG study type", ("eeg.study_type",), "scalar",
              "Routine, prolonged, ambulatory, video-EEG, EMU and so on.", _R, ("eeg",), (),
              _EXT + "Right for 24 of 37 patients after the rules stopped reading advice (\"video-EEG may be considered\") "
              "and \"not available\" as a study done (13 of 37 before; the fix was written from these patients, so it is "
              "not a held-out figure; 10.17, 10.20). Still often \"video-EEG\" where the plan says routine or prolonged."),
    Phenotype("eeg_background", "EEG background", ("eeg.background",), "scalar",
              "Background activity or slowing.", _R, ("eeg",), (),
              "Only the coarse normal/abnormal call was scored (F-S letters, 67 with an EEG result): when the rules "
              "gave a result it was right 37 of 38 times, but they gave none for 29 of 67 (10.16). Study type and "
              "ictal onset are untested."),
    Phenotype("eeg_ied_present", "Interictal discharges present", ("eeg.ied_present",), "bool",
              "Whether interictal epileptiform discharges are reported.", _R, ("eeg",), (),
              _EXT + "Right for 17 of 27 patients that have IEDs in the plan (4 extra reports where the plan has none; 10.17)."),
    Phenotype("eeg_ied_findings", "Interictal discharge site", ("eeg.ied_findings",), "list",
              "Lobe and side of interictal epileptiform discharges, plus frequency band, recurrence and "
              "dispersal when the note states them.", _R, ("eeg",), (),
              _EXT + "Lobe right for 8 of 12, side 8 of 12 (10.17). Band / recurrence / dispersal are "
              "rules-only extras (SACAR schema); TUH external score is blocked on a data-use agreement (10.46)."),
    Phenotype("eeg_ictal_onset", "EEG ictal onset", ("eeg.ictal_onset_lobe", "eeg.ictal_onset_laterality"),
              "scalar", "Lobe and side of seizure onset on EEG.", _R, ("eeg",), (),
              _EXT + "Right for 4 of 5 recorded onsets, but still reported for 13 patients where the plan has none (20 "
              "before negated and planned sentences were skipped; the fix was written from these patients; 10.17, 10.20)."),
    Phenotype("mri_findings", "MRI findings", ("mri.findings",), "list",
              "Lesions or findings reported on MRI.", _R, ("mri",), (),
              _SYN + "Held-out, 30 patients with an MRI report: precision 0.50, recall 0.93 (the rules add generic lesion labels)."),
    Phenotype("mri_normal", "MRI normal", ("mri.overall_normal",), "bool",
              "True if the MRI is reported as normal.", _R, ("mri",), (),
              _SYN + "Held-out, 30 patients with an MRI report: 29 answered, all right."),
    Phenotype("hippocampal_sclerosis", "Hippocampal sclerosis", ("mri.hippocampal_sclerosis",), "bool",
              "True if hippocampal sclerosis is reported.", _R, ("mri",), (),
              _SYN + "Held-out: 19 of 30 answered, 18 right (1 false alarm). When the note never mentions it, no value is given."),
    Phenotype("focal_cortical_dysplasia", "Focal cortical dysplasia", ("mri.focal_cortical_dysplasia",),
              "bool", "True if focal cortical dysplasia is reported.", _R, ("mri",), (),
              _SYN + "Held-out: 14 of 30 answered, 11 right (3 false alarms). When the note never mentions it, no value is given."),
    Phenotype("mri_lesion", "MRI lesion lobe and side", ("mri.lesion_lobe", "mri.lesion_laterality"),
              "scalar", "Lobe and laterality of an MRI lesion when the note names them.",
              "none", ("mri",), (),
              "Extracted by the specialist (and coded); no patient-level accuracy table yet."),
    Phenotype("surgery_history", "Epilepsy surgery or neurostimulation",
              ("medication.surgery_history",), "list", "Resection, ablation, VNS, RNS, DBS and so on.",
              _R, ("surgery",), (),
              _SYN + "The reference lists no surgery for any patient; held-out, the rules still reported a procedure for 5 of 80 "
              "(an 'epilepsy surgery' phrase or a VNS/RNS/DBS list read as history). Options, plans and 'no surgery documented' are skipped. "
              "On the extended set (v4_ext, 37 patients) all 11 planned procedures were found and 1 extra was reported (10.17)."),
    Phenotype("status_epilepticus_history", "Status epilepticus history",
              ("clinical_seizure.status_epilepticus_history",), "bool",
              "Whether the patient has ever had status epilepticus.", _R, ("seizure",), (),
              "Specialist rule on synthetic notes (test_rules_p2); no patient-level accuracy table. Also read by P1C when the extra reader is on."),
    Phenotype("non_drug_therapies", "Non-drug therapies", ("medication.non_drug_therapies",), "list",
              "Ketogenic diet, immunotherapy and other non-ASM treatments the patient has used.",
              _R, ("medication",), (),
              "Specialist rule on synthetic notes (test_rules_p2); no patient-level accuracy table. Also read by P1C when the extra reader is on."),
    Phenotype("eeg_seizures_captured", "EEG seizures captured", ("eeg.seizures_captured",), "bool",
              "Whether EEG recorded a seizure.", _R, ("eeg",), (),
              "Specialist rule on synthetic notes (test_rules_p2); no patient-level accuracy table. Also read by P1C when the extra reader is on."),
    Phenotype("clinical_localization", "Clinician localization",
              ("clinical_localization.primary_claim",), "scalar",
              "The clinician's hypothesized seizure-onset lobe and side.", _R, ("seizure",), (),
              "Specialist rule on synthetic notes (test_rules_p2); no patient-level accuracy table. Also read by P1C when the extra reader is on."),
    Phenotype("adverse_effects_text", "ASM side effects (text)", ("medication.adverse_effects_text",), "scalar",
              "Medication side effects as written in the note.", _R, ("medication",), (),
              "Free text. Specialist rule on synthetic notes; also read by F1C when the extra reader is on. Always review."),
    Phenotype("other_seizure_frequencies", "Other seizure frequencies",
              ("clinical_seizure.other_seizure_frequencies",), "list",
              "Frequencies for additional seizure types besides the predominant one.", _R, ("seizure",), (),
              "Specialist rule (seizure_frequency.py); also read by F1C. No patient-level accuracy table."),
    Phenotype("etiology_specifics", "Etiology specifics", ("clinical_seizure.etiology_specifics",), "scalar",
              "Gene, variant, antibody, pathogen or metabolic cause when the note names one.",
              _R, ("etiology",), (),
              "Specialist (autoimmune + etiology rules). Synthetic gene/variant/antibody right for all 27 patients that have one (10.16). Also read by F1C."),
    Phenotype("eeg_seizures_captured_count", "EEG seizures captured (count)",
              ("eeg.seizures_captured_count",), "scalar",
              "Number of seizures recorded on EEG.", _R, ("eeg",), (),
              "Specialist rule (eeg_extra.py); also read by F1C. No patient-level accuracy table."),
    Phenotype("mri_negative", "MRI negative for epilepsy", ("mri.mri_negative_for_epilepsy",), "bool",
              "True if MRI is reported non-lesional or MRI-negative for epilepsy.", _R, ("mri",), (),
              "Specialist rule (mri.py); also read by F1C. No patient-level accuracy table."),
    Phenotype("mri_field_strength", "MRI field strength (tesla)", ("mri.field_strength_tesla",), "scalar",
              "Scanner field strength when stated (1.5, 3 or 7 T).", _R, ("mri",), (),
              "Specialist rule (mri_extra.py); also read by F1C. No patient-level accuracy table."),
    Phenotype("alternative_localization", "Alternative localization",
              ("clinical_localization.alternative_claims",), "list",
              "Other seizure-onset sites the clinician names besides the primary claim.", _R, ("seizure",), (),
              "Specialist rule (clinical_localization.py); also read by F1C. No patient-level accuracy table."),
    Phenotype("concordance", "EEG–MRI concordance", ("integrated.concordance",), "scalar",
              "Whether clinical, EEG and MRI localization agree (concordant, partially concordant, discordant, not assessed).",
              _R, ("integrated",), (),
              "Derived by a rule from the three localizations, and also read as stated by F1C. No patient-level accuracy table.",
              True),
    Phenotype("concordance_notes", "Concordance notes", ("integrated.concordance_notes_text",), "scalar",
              "The note's own words comparing EEG and MRI localization.", _R, ("integrated",), (),
              "Free text; F1C reads a quoted span when the extra reader is on."),
)

PANELS: dict[str, tuple[str, str]] = {
    # id -> (label, tag in Phenotype.tags)
    "core": ("Core: type, onset, frequency, current ASMs (measured accuracy)", "core"),
    "seizure": ("Seizure history", "seizure"),
    "medication": ("Medication roles", "medication"),
    "etiology": ("Etiology", "etiology"),
    "eeg": ("EEG", "eeg"),
    "mri": ("MRI", "mri"),
    "surgery": ("Surgery and neurostimulation", "surgery"),
    "integrated": ("Concordance (EEG / MRI / clinical)", "integrated"),
    "all": ("Everything LEO can extract", ""),
}


@dataclass(frozen=True)
class AskSpec:
    id: str
    question: str
    answer_type: str = "text"            # yes_no | text | number | choice
    choices: tuple[str, ...] = ()
    label: str = ""
    predefined: bool = False


ASK_TEMPLATES: tuple[AskSpec, ...] = tuple(
    AskSpec(i, q, t, c, lbl, True) for i, q, t, c, lbl in (
        ("status_epilepticus", "Has the patient ever had status epilepticus?", "yes_no", (), "Status epilepticus history"),
        ("epilepsy_surgery", "Has the patient had epilepsy surgery?", "yes_no", (), "Epilepsy surgery"),
        ("neurostimulation", "Does the patient have a VNS, RNS or DBS device?", "yes_no", (), "Neurostimulation device"),
        ("family_history", "Is there a family history of epilepsy or seizures?", "yes_no", (), "Family history of epilepsy"),
        ("febrile_seizures", "Did the patient have febrile seizures in childhood?", "yes_no", (), "Febrile seizures"),
        ("aura", "Does the patient report an aura before seizures?", "yes_no", (), "Aura"),
        ("nocturnal", "Do seizures occur during sleep?", "yes_no", (), "Nocturnal seizures"),
        ("triggers", "What triggers seizures, if any are stated?", "text", (), "Seizure triggers"),
        ("adverse_effects", "What medication side effects are reported?", "text", (), "ASM side effects"),
        ("driving", "What does the note say about driving?", "text", (), "Driving status"),
        ("pregnancy", "Is pregnancy or contraception discussed, and what is said?", "text", (), "Pregnancy / contraception"),
        ("developmental", "Does the patient have developmental delay or intellectual disability?", "yes_no", (),
         "Developmental delay"),
        ("psychiatric", "Is a psychiatric comorbidity (depression, anxiety, psychosis) documented?", "yes_no", (),
         "Psychiatric comorbidity"),
        ("seizure_free_duration", "For how many months has the patient been seizure free, if stated?", "number", (),
         "Seizure-free duration (months)"),
        ("dre_kwan",
         "Does this ASM history meet the ILAE 2010 definition of drug-resistant epilepsy "
         "(two adequate, tolerated trials that failed to achieve seizure freedom)?",
         "yes_no", (), "ILAE 2010 drug-resistant epilepsy (ask/audit)"),
        ("first_feature",
         "Is the described onset the first feature of the seizure, or later evolution?",
         "choice", ("first_feature", "later_evolution", "not_documented"),
         "ILAE 2017 first feature vs evolution (ask/audit)"),
        ("ltm_sense",
         "In this note, is LTM (or cEEG / long-term monitoring) an EEG study or a drug?",
         "choice", ("eeg_study", "drug", "not_documented"),
         "ACNS LTM study vs drug (ask/audit)"),
    ))

_BY_ID = {p.id: p for p in EXTRACT}
_ASK_BY_ID = {a.id: a for a in ASK_TEMPLATES}


def get(pid: str) -> Phenotype:
    try:
        return _BY_ID[pid]
    except KeyError:
        raise KeyError(f"unknown phenotype {pid!r}; known: {', '.join(_BY_ID)}") from None


def resolve_phenotypes(selection: Optional[list[str] | str]) -> list[Phenotype]:
    """Names and panel ids -> phenotypes, in catalogue order, no duplicates.

    ``None`` or ``[]`` selects the ``core`` panel.  A panel id expands to its members; ``all`` is every
    phenotype.  Unknown names raise ``KeyError`` (a typo must not silently drop a column).
    """
    if selection is None or selection == [] or selection == "":
        selection = ["core"]
    if isinstance(selection, str):
        selection = [x.strip() for x in selection.split(",") if x.strip()]
    want: set[str] = set()
    for item in selection:
        if item in PANELS:
            tag = PANELS[item][1]
            want |= {p.id for p in EXTRACT if (not tag or tag in p.tags)}
        else:
            want.add(get(item).id)
    return [p for p in EXTRACT if p.id in want]


def ask_template(aid: str) -> AskSpec:
    try:
        return _ASK_BY_ID[aid]
    except KeyError:
        raise KeyError(f"unknown question template {aid!r}; known: {', '.join(_ASK_BY_ID)}") from None


def custom_ask(question: str, answer_type: str = "text", choices: tuple[str, ...] = (), aid: str = "") -> AskSpec:
    """A user-typed question.  ``aid`` becomes the column prefix (slugged); default ``q_<n>`` is set by the caller."""
    import re
    if answer_type not in ("yes_no", "text", "number", "choice"):
        raise ValueError("answer_type must be yes_no, text, number or choice")
    if answer_type == "choice" and len(choices) < 2:
        raise ValueError("a choice question needs at least two choices")
    q = (question or "").strip()
    if not q:
        raise ValueError("question is empty")
    slug = re.sub(r"[^a-z0-9]+", "_", (aid or q).lower()).strip("_")[:40] or "question"
    return AskSpec(f"ask_{slug}", q[:400], answer_type, tuple(choices), "", False)


def describe() -> dict:
    """JSON for the UI and ``leo phenotypes``."""
    return {
        "extract": [{"id": p.id, "label": p.label, "definition": p.definition, "kind": p.kind,
                     "evidence": p.evidence, "note": p.note, "derived": p.derived,
                     "refs": [REFERENCES[r] for r in p.refs], "tags": list(p.tags)} for p in EXTRACT],
        "panels": [{"id": k, "label": v[0], "members": [p.id for p in resolve_phenotypes([k])]}
                   for k, v in PANELS.items()],
        "ask_templates": [{"id": a.id, "label": a.label, "question": a.question, "answer_type": a.answer_type}
                          for a in ASK_TEMPLATES],
    }


__all__ = ["Phenotype", "AskSpec", "REFERENCES", "EXTRACT", "PANELS", "ASK_TEMPLATES", "get", "resolve_phenotypes",
           "ask_template", "custom_ask", "describe"]
