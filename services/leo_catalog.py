"""LEO phenotype catalogue: what a user can ask LEO to extract, by name.

Two kinds of predefined phenotype, kept apart because they carry different evidence:

* **extract** phenotypes are read by the full LEO chain (LLM + EpExtra specialist + ontology),
  fused and verified.  Each carries an ``evidence`` level that says what has actually been measured:
  ``measured`` (own accuracy against gold, numbers in ``services.leo_evidence``), ``rules_only`` (the
  specialist alone was scored against synthetic gold, no LLM; ``eval/results/leo_extra_phenotypes.md``),
  ``indirect`` (only its effect on another field was measured) or ``none`` (nothing measured).  Five are ``measured``.  The
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
_NOTE_RESCUE = ("No accuracy of its own was measured. Its effect on the current-ASM list was measured; the rescue "
                "rule re-routed one drug in 40 F-S letters (docs/EVAL_PROTOCOL_LEO.md 10.7).")
_NOTE_ACUTE = ("No accuracy of its own was measured. The rule moved no drug in 40 F-S letters (10.6); it is a "
               "text-pattern rule written from guidelines.")
_R = "rules_only"
_SYN = ("Synthetic notes, each patient's notes joined, rules only (no LLM). Held-out figures are 80 patients the rules "
        "were not adjusted on (leo_extra_phenotypes_ext). ")
_NOTE_PRIOR = ("No accuracy of its own was measured. Only stopped drugs wrongly listed as current were counted "
               "(10.5).")

EXTRACT: tuple[Phenotype, ...] = (
    Phenotype("epilepsy_type", "Epilepsy type", ("clinical_seizure.epilepsy_type",), "scalar",
              "Focal, generalized, combined generalized and focal, or unknown (ILAE 2017 epilepsy types).", _M,
              ("core", "seizure"), ("ilae2017_epilepsies",),
              "The F-S gold says unknown when the diagnosis line names no type (25 of 38 letters), and LEO often "
              "states a type there; whether those are errors was not adjudicated (see Evidence)."),
    Phenotype("seizure_type", "Predominant seizure type", ("clinical_seizure.predominant_seizure_type",),
              "scalar", "The seizure type the note treats as the main one, using ILAE 2017 operational names.",
              _M, ("core", "seizure"), ("ilae2017_seizure",),
              "Small samples; the specialist and the LLM often disagree on this field."),
    Phenotype("age_at_onset", "Age at seizure onset (years)", ("clinical_seizure.age_at_onset_years",),
              "scalar", "Age when seizures began.", _M, ("core", "seizure"), (),
              "Only 4 held-out F-S letters state an onset age, so that estimate is very uncertain."),
    Phenotype("seizure_frequency", "Current seizure frequency", ("clinical_seizure.seizure_frequency",),
              "frequency", "How often seizures occur now: counts per day, week, month or year, or seizure free.",
              _M, ("core", "seizure")),
    Phenotype("current_asms", "Current maintenance ASMs", ("medication.current_asms",), "list",
              "Daily anti-seizure medicines the patient takes now. Rescue and one-off doses are separate.",
              _M, ("core", "medication"), (),
              "Whether a rescue drug counts as current differs between the two test sets; see Evidence."),
    Phenotype("rescue_medication", "Rescue medication", ("medication.rescue_medication",), "list",
              "As-needed seizure-rescue drugs (PRN, buccal, intranasal, rectal).", _I, ("medication",), (),
              _NOTE_RESCUE),
    Phenotype("acute_administration", "One-off administration", ("medication.acute_administration",), "list",
              "A drug given once during the encounter (IV load, ED dose). Always listed for review.",
              _I, ("medication",), (), _NOTE_ACUTE),
    Phenotype("prior_asms", "Prior (stopped) ASMs", ("medication.prior_asms",), "list",
              "ASMs the patient used before and no longer takes.", _I, ("medication",), (), _NOTE_PRIOR),
    Phenotype("failed_asms", "Failed ASMs", ("medication.failed_asms",), "list",
              "ASMs stopped for lack of effect or side effects.", "none", ("medication",)),
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
              "Free-text etiology as written in the note.", "none", ("etiology",)),
    Phenotype("semiology", "Seizure semiology (text)", ("clinical_seizure.semiology_text",), "scalar",
              "How the seizure looks, as written in the note.", "none", ("seizure",)),
    Phenotype("focal_motor_onset", "Focal motor onset", ("clinical_seizure.focal_motor_onset",), "scalar",
              "Motor feature at focal onset (ILAE 2017 seizure classification).", "none", ("seizure",), ("ilae2017_seizure",)),
    Phenotype("focal_nonmotor_onset", "Focal non-motor onset", ("clinical_seizure.focal_nonmotor_onset",),
              "scalar", "Non-motor feature at focal onset (ILAE 2017 seizure classification).", "none", ("seizure",),
              ("ilae2017_seizure",)),
    Phenotype("eeg_study_type", "EEG study type", ("eeg.study_type",), "scalar",
              "Routine, prolonged, ambulatory, video-EEG, EMU and so on.", "none", ("eeg",)),
    Phenotype("eeg_background", "EEG background", ("eeg.background",), "scalar",
              "Background activity or slowing.", "none", ("eeg",)),
    Phenotype("eeg_ictal_onset", "EEG ictal onset", ("eeg.ictal_onset_lobe", "eeg.ictal_onset_laterality"),
              "scalar", "Lobe and side of seizure onset on EEG.", "none", ("eeg",)),
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
    Phenotype("surgery_history", "Epilepsy surgery or neurostimulation",
              ("medication.surgery_history",), "list", "Resection, ablation, VNS, RNS, DBS and so on.",
              _R, ("surgery",), (),
              _SYN + "The reference lists no surgery for any patient; held-out, the rules still reported a procedure for 5 of 80 "
              "(an 'epilepsy surgery' phrase or a VNS/RNS/DBS list read as history). Options, plans and 'no surgery documented' are skipped"),
)

PANELS: dict[str, tuple[str, str]] = {
    # id -> (label, tag in Phenotype.tags)
    "core": ("Core: type, onset, frequency, current ASMs (the five fields with measured accuracy)", "core"),
    "seizure": ("Seizure history", "seizure"),
    "medication": ("Medication roles", "medication"),
    "etiology": ("Etiology", "etiology"),
    "eeg": ("EEG", "eeg"),
    "mri": ("MRI", "mri"),
    "surgery": ("Surgery and neurostimulation", "surgery"),
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
