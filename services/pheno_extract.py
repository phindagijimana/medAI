"""Third model reader for the rest of the epilepsy phenotype (arm ``P1C``).

L1C reads five core fields; X1C reads EEG/onset/rescue/surgery.  This call reads the remaining
closed-vocabulary extract fields the specialist already fills, so they can have a second reader:
awareness, other seizure types, etiology category, status epilepticus, MRI, prior/failed ASMs,
non-drug therapies, seizures captured, clinician localization.

Free-text-only fields and the remaining schema leftovers are the fourth call (arm F1C, ``services.full_extract``).
The prompt and examples are synthetic and were not tuned on an evaluation set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from services.ext_extract import LOBES, SIDES
from services.flat_extract import SEIZURE_TYPES, _ev, _json_obj, _norm_enum

PHENO_PROMPT_VERSION = "v1"
PHENO_ARM = "P1C"
PHENO_MAX_NOTE_CHARS = 5000

AWARENESS = ("aware", "impaired", "unknown")
ETIOLOGY = ("structural", "genetic", "infectious", "immune", "metabolic", "unknown")
MRI_FINDINGS = (
    "normal", "hippocampal_sclerosis", "focal_cortical_dysplasia", "tumor",
    "vascular_malformation", "gliosis", "stroke_sequelae", "encephalomalacia",
    "polymicrogyria", "heterotopia", "tuberous_sclerosis", "other_lesion", "mri_negative",
)
NON_DRUG = (
    "ketogenic_diet", "modified_atkins", "low_glycemic_index", "ivig",
    "plasmapheresis", "steroids", "rituximab", "acth", "other",
)

PHENO_FIELD_PATHS = frozenset({
    "clinical_seizure.awareness",
    "clinical_seizure.other_seizure_types",
    "clinical_seizure.etiology_category",
    "clinical_seizure.status_epilepticus_history",
    "mri.overall_normal",
    "mri.hippocampal_sclerosis",
    "mri.focal_cortical_dysplasia",
    "mri.findings",
    "mri.lesion_lobe",
    "mri.lesion_laterality",
    "medication.prior_asms",
    "medication.failed_asms",
    "medication.non_drug_therapies",
    "eeg.seizures_captured",
    "clinical_localization.primary_claim",
})

_INSTRUCTIONS = f"""You read one patient's epilepsy clinic note and report only the items below.
Reply with ONE JSON object and nothing else. Use null or [] when the note does not state the item.
Every non-null value needs "quote": exact words copied from the note.

Report what WAS DONE or IS TRUE. Do not report plans, advice, family history, or denied findings as present.

Items:
- awareness: during typical seizures, one of {list(AWARENESS)} or null (aware = retained; impaired = loss of awareness)
- other_seizure_types: further ILAE types besides the main one, each one of {list(SEIZURE_TYPES)}
- etiology_category: one of {list(ETIOLOGY)} or null (from a stated cause, not guessed)
- status_epilepticus: true if the patient has had status epilepticus, false if denied, null if not stated
- mri_normal: true if MRI is reported normal, false if abnormal, null if no MRI result
- hippocampal_sclerosis: true/false/null as stated
- focal_cortical_dysplasia: true/false/null as stated
- mri_findings: listed lesions, each one of {list(MRI_FINDINGS)}
- lesion: lobe one of {list(LOBES)} and side one of {list(SIDES)} for an MRI lesion, or nulls
- prior_asms: daily ASMs the patient STOPPED (not current). Generic names.
- failed_asms: ASMs stopped for lack of effect or side effects. Generic names.
- non_drug_therapies: one of {list(NON_DRUG)} the patient has used
- seizures_captured: true if EEG recorded a seizure, false if none captured, null if not stated
- localization: clinician's seizure-onset lobe and side (not EEG ictal onset unless the note treats it as the clinical hypothesis)

JSON shape:
{{"awareness": {{"value": null, "quote": null}},
 "other_seizure_types": [{{"value": "generalized_absence_typical", "quote": "absences"}}],
 "etiology_category": {{"value": null, "quote": null}},
 "status_epilepticus": {{"value": null, "quote": null}},
 "mri_normal": {{"value": null, "quote": null}},
 "hippocampal_sclerosis": {{"value": null, "quote": null}},
 "focal_cortical_dysplasia": {{"value": null, "quote": null}},
 "mri_findings": [{{"value": "hippocampal_sclerosis", "quote": "MTS"}}],
 "lesion": {{"lobe": null, "side": null, "quote": null}},
 "prior_asms": [{{"name": "carbamazepine", "quote": "stopped carbamazepine"}}],
 "failed_asms": [{{"name": "carbamazepine", "quote": "failed carbamazepine"}}],
 "non_drug_therapies": [{{"type": "ketogenic_diet", "quote": "ketogenic diet"}}],
 "seizures_captured": {{"value": null, "quote": null}},
 "localization": {{"lobe": null, "side": null, "quote": null}}}}
"""

_EXAMPLES = [
    ("""Ms Chen has focal impaired-awareness seizures and rare GTCS. MRI showed left hippocampal sclerosis. She stopped carbamazepine for a rash. She takes lamotrigine. No status epilepticus. EEG did not capture a seizure. The neurologist suspects left temporal onset.""",
     {"awareness": {"value": "impaired", "quote": "focal impaired-awareness seizures"},
      "other_seizure_types": [{"value": "generalized_tonic_clonic", "quote": "rare GTCS"}],
      "etiology_category": {"value": "structural", "quote": "left hippocampal sclerosis"},
      "status_epilepticus": {"value": False, "quote": "No status epilepticus"},
      "mri_normal": {"value": False, "quote": "MRI showed left hippocampal sclerosis"},
      "hippocampal_sclerosis": {"value": True, "quote": "left hippocampal sclerosis"},
      "focal_cortical_dysplasia": {"value": None, "quote": None},
      "mri_findings": [{"value": "hippocampal_sclerosis", "quote": "left hippocampal sclerosis"}],
      "lesion": {"lobe": "temporal", "side": "left", "quote": "left hippocampal sclerosis"},
      "prior_asms": [{"name": "carbamazepine", "quote": "stopped carbamazepine for a rash"}],
      "failed_asms": [{"name": "carbamazepine", "quote": "stopped carbamazepine for a rash"}],
      "non_drug_therapies": [],
      "seizures_captured": {"value": False, "quote": "EEG did not capture a seizure"},
      "localization": {"lobe": "temporal", "side": "left", "quote": "left temporal onset"}}),
    ("""Generalised epilepsy. Absences and myoclonic jerks. MRI brain normal. Currently on valproate after failing lamotrigine. Ketogenic diet in childhood. Presented in status epilepticus at age 12.""",
     {"awareness": {"value": "impaired", "quote": "Absences"},
      "other_seizure_types": [{"value": "generalized_myoclonic", "quote": "myoclonic jerks"}],
      "etiology_category": {"value": None, "quote": None},
      "status_epilepticus": {"value": True, "quote": "status epilepticus at age 12"},
      "mri_normal": {"value": True, "quote": "MRI brain normal"},
      "hippocampal_sclerosis": {"value": False, "quote": "MRI brain normal"},
      "focal_cortical_dysplasia": {"value": False, "quote": "MRI brain normal"},
      "mri_findings": [{"value": "normal", "quote": "MRI brain normal"}],
      "lesion": {"lobe": None, "side": None, "quote": None},
      "prior_asms": [{"name": "lamotrigine", "quote": "failing lamotrigine"}],
      "failed_asms": [{"name": "lamotrigine", "quote": "failing lamotrigine"}],
      "non_drug_therapies": [{"type": "ketogenic_diet", "quote": "Ketogenic diet in childhood"}],
      "seizures_captured": {"value": None, "quote": None},
      "localization": {"lobe": None, "side": None, "quote": None}}),
]


def build_pheno_prompt(note: str) -> str:
    parts = [_INSTRUCTIONS]
    for text, ans in _EXAMPLES:
        parts.append(f'Example note:\n"""\n{text}\n"""\nJSON:\n{json.dumps(ans)}\n')
    parts.append(f'Note:\n"""\n{note}\n"""\nJSON:\n')
    return "\n".join(parts)


def _pheno_answer_model():
    from typing import Literal

    from pydantic import BaseModel, Field

    Quote = Optional[str]
    Sz = Literal[SEIZURE_TYPES]  # type: ignore[valid-type]
    Aw = Literal[AWARENESS]  # type: ignore[valid-type]
    Et = Literal[ETIOLOGY]  # type: ignore[valid-type]
    Mf = Literal[MRI_FINDINGS]  # type: ignore[valid-type]
    Nd = Literal[NON_DRUG]  # type: ignore[valid-type]
    Lobe = Literal[LOBES]  # type: ignore[valid-type]
    Side = Literal[SIDES]  # type: ignore[valid-type]

    class _S(BaseModel):
        value: Optional[str] = None
        quote: Quote = Field(default=None, max_length=160)

    class _Aw(_S):
        value: Optional[Aw] = None  # type: ignore[valid-type]

    class _Et(_S):
        value: Optional[Et] = None  # type: ignore[valid-type]

    class _Bool(BaseModel):
        value: Optional[bool] = None
        quote: Quote = Field(default=None, max_length=160)

    class _Sz(BaseModel):
        value: Sz  # type: ignore[valid-type]
        quote: str = Field(max_length=160)

    class _Find(BaseModel):
        value: Mf  # type: ignore[valid-type]
        quote: str = Field(max_length=160)

    class _Site(BaseModel):
        lobe: Optional[Lobe] = None  # type: ignore[valid-type]
        side: Optional[Side] = None  # type: ignore[valid-type]
        quote: Quote = Field(default=None, max_length=160)

    class _Drug(BaseModel):
        name: str = Field(max_length=40)
        quote: str = Field(max_length=160)

    class _Ther(BaseModel):
        type: Nd  # type: ignore[valid-type]
        quote: str = Field(max_length=160)

    class PhenoAnswer(BaseModel):
        awareness: _Aw
        other_seizure_types: list[_Sz] = Field(max_length=4)
        etiology_category: _Et
        status_epilepticus: _Bool
        mri_normal: _Bool
        hippocampal_sclerosis: _Bool
        focal_cortical_dysplasia: _Bool
        mri_findings: list[_Find] = Field(max_length=4)
        lesion: _Site
        prior_asms: list[_Drug] = Field(max_length=6)
        failed_asms: list[_Drug] = Field(max_length=6)
        non_drug_therapies: list[_Ther] = Field(max_length=3)
        seizures_captured: _Bool
        localization: _Site

    return PhenoAnswer


_PHENO_ANSWER = None


def pheno_answer_model():
    global _PHENO_ANSWER
    if _PHENO_ANSWER is None:
        _PHENO_ANSWER = _pheno_answer_model()
    return _PHENO_ANSWER


@dataclass
class PhenoParse:
    modules: dict
    n_fields_kept: int = 0
    n_values_dropped: int = 0
    parse_ok: bool = False
    notes: list[str] = field(default_factory=list)


def parse_pheno(raw: str) -> PhenoParse:
    obj = _json_obj(raw)
    if obj is None:
        return PhenoParse(modules={}, notes=["no_json"])
    out = PhenoParse(modules={}, parse_ok=True)
    cs: dict = {}
    eeg: dict = {}
    med: dict = {}
    mri: dict = {}
    loc: dict = {}

    def keep(n: int = 1) -> None:
        out.n_fields_kept += n

    def drop(why: str) -> None:
        out.n_values_dropped += 1
        out.notes.append(why)

    def pick(item: dict, key: str, allowed: tuple[str, ...], tag: str) -> Optional[str]:
        raw_v = item.get(key)
        if raw_v is None:
            return None
        v = _norm_enum(raw_v)
        if not v:
            return None
        if v not in allowed:
            drop(f"{tag}:out_of_vocab:{v}")
            return None
        return v

    def quoted(item: Any) -> Optional[str]:
        if not isinstance(item, dict):
            return None
        q = item.get("quote")
        return q if isinstance(q, str) and q.strip() else None

    def scalar_enum(key: str, allowed: tuple[str, ...], target: dict, name: str) -> None:
        item = obj.get(key)
        if not isinstance(item, dict):
            return
        val = pick(item, "value", allowed, key)
        if val is None:
            return
        if not quoted(item):
            drop(f"{key}:no_quote")
            return
        target[name] = _ev(val, item["quote"])
        keep()

    def scalar_bool(key: str, target: dict, name: str) -> None:
        item = obj.get(key)
        if not isinstance(item, dict) or not isinstance(item.get("value"), bool):
            return
        if not quoted(item):
            drop(f"{key}:no_quote")
            return
        target[name] = _ev(item["value"], item["quote"])
        keep()

    scalar_enum("awareness", AWARENESS, cs, "awareness")
    scalar_enum("etiology_category", ETIOLOGY, cs, "etiology_category")
    scalar_bool("status_epilepticus", cs, "status_epilepticus_history")
    scalar_bool("mri_normal", mri, "overall_normal")
    scalar_bool("hippocampal_sclerosis", mri, "hippocampal_sclerosis")
    scalar_bool("focal_cortical_dysplasia", mri, "focal_cortical_dysplasia")
    scalar_bool("seizures_captured", eeg, "seizures_captured")

    others = obj.get("other_seizure_types")
    if isinstance(others, list):
        items, seen = [], set()
        for it in others:
            if not isinstance(it, dict):
                continue
            val = pick(it, "value", SEIZURE_TYPES, "other_seizure_types")
            if val is None or not quoted(it) or val in seen:
                if val is not None and not quoted(it):
                    drop("other_seizure_types:no_quote")
                continue
            seen.add(val)
            items.append(_ev(val, it["quote"]))
            keep()
        if items:
            cs["other_seizure_types"] = items

    findings = obj.get("mri_findings")
    if isinstance(findings, list):
        items, seen = [], set()
        for it in findings:
            if not isinstance(it, dict):
                continue
            val = pick(it, "value", MRI_FINDINGS, "mri_findings")
            if val is None or not quoted(it) or val in seen:
                if val is not None and not quoted(it):
                    drop("mri_findings:no_quote")
                continue
            seen.add(val)
            items.append(_ev(val, it["quote"]))
            keep()
        if items:
            mri["findings"] = items

    les = obj.get("lesion")
    if isinstance(les, dict):
        lobe, side = pick(les, "lobe", LOBES, "lesion"), pick(les, "side", SIDES, "lesion")
        if (lobe or side) and not quoted(les):
            drop("lesion:no_quote")
        else:
            if lobe:
                mri["lesion_lobe"] = _ev(lobe, les["quote"])
                keep()
            if side:
                mri["lesion_laterality"] = _ev(side, les["quote"])
                keep()

    locn = obj.get("localization")
    if isinstance(locn, dict):
        lobe, side = pick(locn, "lobe", LOBES, "localization"), pick(locn, "side", SIDES, "localization")
        if (lobe or side) and not quoted(locn):
            drop("localization:no_quote")
        elif lobe and side:
            loc["primary_claim"] = _ev(
                {"lobe": lobe, "laterality": side, "source": "clinician_hypothesis"}, locn["quote"])
            keep()

    def drugs(key: str, status: str, dest: str) -> None:
        rows = obj.get(key)
        if not isinstance(rows, list):
            return
        items, names = [], set()
        for d in rows:
            if not isinstance(d, dict):
                continue
            name = d.get("name")
            if not isinstance(name, str) or not name.strip() or not quoted(d):
                drop(f"{key}:no_name_or_quote")
                continue
            name = name.strip().lower()
            if name in names:
                continue
            names.add(name)
            items.append(_ev({"generic_name": name, "status": status}, d["quote"]))
            keep()
        if items:
            med[dest] = items

    drugs("prior_asms", "prior", "prior_asms")
    drugs("failed_asms", "failed", "failed_asms")

    th = obj.get("non_drug_therapies")
    if isinstance(th, list):
        items, seen = [], set()
        for t in th:
            if not isinstance(t, dict):
                continue
            typ = pick(t, "type", NON_DRUG, "non_drug_therapies")
            if typ is None or not quoted(t) or typ in seen:
                continue
            seen.add(typ)
            items.append(_ev({"therapy_type": typ, "status": "current"}, t["quote"]))
            keep()
        if items:
            med["non_drug_therapies"] = items

    if cs:
        out.modules["clinical_seizure"] = cs
    if eeg:
        out.modules["eeg"] = eeg
    if med:
        out.modules["medication"] = med
    if mri:
        out.modules["mri"] = mri
    if loc:
        out.modules["clinical_localization"] = loc
    return out


__all__ = ["PHENO_ARM", "PHENO_FIELD_PATHS", "PHENO_MAX_NOTE_CHARS", "PHENO_PROMPT_VERSION",
           "build_pheno_prompt", "parse_pheno", "pheno_answer_model"]
