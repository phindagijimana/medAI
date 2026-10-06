"""Fourth model reader for leftover schema fields (arm ``F1C``).

L1C / X1C / P1C already cover the closed-vocabulary extract columns.  This call reads the rest of
the v0.2.1 phenotype the specialist fills: free-text spans, etiology specifics, drug resistance as
stated, extra frequencies, seizure count, MRI-negative / field strength, alternative localizations,
and concordance.  Constrained JSON with a verbatim quote on every value.  Synthetic examples; not
tuned on an evaluation set.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from services.ext_extract import LOBES, SIDES
from services.flat_extract import PERIODS, SEIZURE_TYPES, _ev, _json_obj, _norm_enum, _num

FULL_PROMPT_VERSION = "v1"
FULL_ARM = "F1C"
FULL_MAX_NOTE_CHARS = 5000

DRUG_RES = ("drug_responsive", "undefined", "drug_resistant")
CONCORD = ("concordant", "partially_concordant", "discordant", "not_assessed")
ANTIBODIES = (
    "anti_lgi1", "anti_caspr2", "anti_nmdar", "anti_gababr", "anti_ampar", "anti_dppx",
    "anti_glyr", "anti_iglon5", "anti_mglur5", "anti_hu", "anti_ma2", "anti_yo", "anti_ri",
    "anti_amphiphysin", "anti_gad65", "anti_sox1", "anti_cv2", "anti_zic4", "other", "none_detected",
)

FULL_FIELD_PATHS = frozenset({
    "clinical_seizure.semiology_text",
    "clinical_seizure.etiology_details_text",
    "clinical_seizure.etiology_specifics",
    "clinical_seizure.other_seizure_frequencies",
    "medication.adverse_effects_text",
    "medication.drug_resistance_status",
    "eeg.seizures_captured_count",
    "mri.mri_negative_for_epilepsy",
    "mri.field_strength_tesla",
    "clinical_localization.alternative_claims",
    "integrated.concordance",
    "integrated.concordance_notes_text",
})

_INSTRUCTIONS = f"""You read one patient's epilepsy clinic note and report only the leftover items below.
Reply with ONE JSON object and nothing else. Use null or [] when the note does not state the item.
Every non-null value needs "quote": exact words copied from the note.

Report what WAS DONE or IS TRUE. Do not report plans, advice, or inferred concordance.

Items:
- semiology: how a typical seizure looks, as written
- etiology_details: the stated cause in the note's words
- adverse_effects: medication side effects as written
- drug_resistance: one of {list(DRUG_RES)} only if the note states it (do not count failed drugs yourself)
- other_frequencies: extra seizure frequencies besides the main one (count_min, count_max, period one of {list(PERIODS)}, optional seizure type)
- seizures_captured_count: how many seizures EEG recorded, or null
- mri_negative: true if MRI is called non-lesional / MRI-negative for epilepsy
- field_strength_tesla: 1.5, 3 or 7 if stated
- etiology_specifics: causative gene (HGNC), variant (HGVS), antibody one of {list(ANTIBODIES)}, pathogen, metabolic cause, associated tumor
- alternative_localization: other lobes/sides the clinician names besides the main hypothesis; lobe {list(LOBES)}, side {list(SIDES)}
- concordance: one of {list(CONCORD)} only if the note compares EEG and MRI (or says they agree/disagree)
- concordance_notes: the comparison in the note's words

JSON shape:
{{"semiology": {{"value": null, "quote": null}},
 "etiology_details": {{"value": null, "quote": null}},
 "adverse_effects": {{"value": null, "quote": null}},
 "drug_resistance": {{"value": null, "quote": null}},
 "other_frequencies": [{{"count_min": 10, "count_max": 10, "period": "day", "seizure_type": "generalized_absence_typical", "quote": "10 absences a day"}}],
 "seizures_captured_count": {{"value": null, "quote": null}},
 "mri_negative": {{"value": null, "quote": null}},
 "field_strength_tesla": {{"value": null, "quote": null}},
 "etiology_specifics": {{"gene": null, "variant": null, "antibody": null, "pathogen": null, "metabolic": null, "tumor": null, "quote": null}},
 "alternative_localization": [{{"lobe": "frontal", "side": "right", "quote": "also right frontal"}}],
 "concordance": {{"value": null, "quote": null}},
 "concordance_notes": {{"value": null, "quote": null}}}}
"""

_EXAMPLES = [
    ("""Drug-resistant genetic epilepsy, SCN1A c.123A>G. Seizures begin with a rising epigastric aura then oral automatisms. Also 10 absences a day. Lamotrigine caused a rash. 3T MRI non-lesional. Video-EEG captured two seizures. EEG and MRI are discordant; EEG is temporal, MRI is normal.""",
     {"semiology": {"value": "rising epigastric aura then oral automatisms", "quote": "rising epigastric aura then oral automatisms"},
      "etiology_details": {"value": "SCN1A c.123A>G", "quote": "SCN1A c.123A>G"},
      "adverse_effects": {"value": "rash", "quote": "Lamotrigine caused a rash"},
      "drug_resistance": {"value": "drug_resistant", "quote": "Drug-resistant genetic epilepsy"},
      "other_frequencies": [{"count_min": 10, "count_max": 10, "period": "day",
                             "seizure_type": "generalized_absence_typical", "quote": "10 absences a day"}],
      "seizures_captured_count": {"value": 2, "quote": "captured two seizures"},
      "mri_negative": {"value": True, "quote": "3T MRI non-lesional"},
      "field_strength_tesla": {"value": 3.0, "quote": "3T MRI"},
      "etiology_specifics": {"gene": "SCN1A", "variant": "c.123A>G", "antibody": None,
                             "pathogen": None, "metabolic": None, "tumor": None, "quote": "SCN1A c.123A>G"},
      "alternative_localization": [],
      "concordance": {"value": "discordant", "quote": "EEG and MRI are discordant"},
      "concordance_notes": {"value": "EEG is temporal, MRI is normal", "quote": "EEG is temporal, MRI is normal"}}),
    ("""Possible anti-LGI1 encephalitis. Also considered right frontal onset. No side effects. 1.5 Tesla MRI. Concordance not discussed.""",
     {"semiology": {"value": None, "quote": None},
      "etiology_details": {"value": "anti-LGI1 encephalitis", "quote": "anti-LGI1 encephalitis"},
      "adverse_effects": {"value": None, "quote": None},
      "drug_resistance": {"value": None, "quote": None},
      "other_frequencies": [],
      "seizures_captured_count": {"value": None, "quote": None},
      "mri_negative": {"value": None, "quote": None},
      "field_strength_tesla": {"value": 1.5, "quote": "1.5 Tesla MRI"},
      "etiology_specifics": {"gene": None, "variant": None, "antibody": "anti_lgi1",
                             "pathogen": None, "metabolic": None, "tumor": None, "quote": "anti-LGI1 encephalitis"},
      "alternative_localization": [{"lobe": "frontal", "side": "right", "quote": "right frontal onset"}],
      "concordance": {"value": None, "quote": None},
      "concordance_notes": {"value": None, "quote": None}}),
]


def build_full_prompt(note: str) -> str:
    parts = [_INSTRUCTIONS]
    for text, ans in _EXAMPLES:
        parts.append(f'Example note:\n"""\n{text}\n"""\nJSON:\n{json.dumps(ans)}\n')
    parts.append(f'Note:\n"""\n{note}\n"""\nJSON:\n')
    return "\n".join(parts)


def _full_answer_model():
    from typing import Literal

    from pydantic import BaseModel, Field

    Quote = Optional[str]
    Dr = Literal[DRUG_RES]  # type: ignore[valid-type]
    Co = Literal[CONCORD]  # type: ignore[valid-type]
    Ab = Literal[ANTIBODIES]  # type: ignore[valid-type]
    Per = Literal[PERIODS]  # type: ignore[valid-type]
    Sz = Literal[SEIZURE_TYPES]  # type: ignore[valid-type]
    Lobe = Literal[LOBES]  # type: ignore[valid-type]
    Side = Literal[SIDES]  # type: ignore[valid-type]

    class _Txt(BaseModel):
        value: Optional[str] = Field(default=None, max_length=200)
        quote: Quote = Field(default=None, max_length=200)

    class _Dr(BaseModel):
        value: Optional[Dr] = None  # type: ignore[valid-type]
        quote: Quote = Field(default=None, max_length=160)

    class _Co(BaseModel):
        value: Optional[Co] = None  # type: ignore[valid-type]
        quote: Quote = Field(default=None, max_length=160)

    class _Num(BaseModel):
        value: Optional[float] = None
        quote: Quote = Field(default=None, max_length=80)

    class _Freq(BaseModel):
        count_min: Optional[float] = None
        count_max: Optional[float] = None
        period: Optional[Per] = None  # type: ignore[valid-type]
        seizure_type: Optional[Sz] = None  # type: ignore[valid-type]
        quote: str = Field(max_length=160)

    class _Spec(BaseModel):
        gene: Optional[str] = Field(default=None, max_length=20)
        variant: Optional[str] = Field(default=None, max_length=40)
        antibody: Optional[Ab] = None  # type: ignore[valid-type]
        pathogen: Optional[str] = Field(default=None, max_length=40)
        metabolic: Optional[str] = Field(default=None, max_length=40)
        tumor: Optional[str] = Field(default=None, max_length=40)
        quote: Quote = Field(default=None, max_length=160)

    class _Alt(BaseModel):
        lobe: Optional[Lobe] = None  # type: ignore[valid-type]
        side: Optional[Side] = None  # type: ignore[valid-type]
        quote: str = Field(max_length=160)

    class _Bool(BaseModel):
        value: Optional[bool] = None
        quote: Quote = Field(default=None, max_length=160)

    class FullAnswer(BaseModel):
        semiology: _Txt
        etiology_details: _Txt
        adverse_effects: _Txt
        drug_resistance: _Dr
        other_frequencies: list[_Freq] = Field(max_length=3)
        seizures_captured_count: _Num
        mri_negative: _Bool
        field_strength_tesla: _Num
        etiology_specifics: _Spec
        alternative_localization: list[_Alt] = Field(max_length=3)
        concordance: _Co
        concordance_notes: _Txt

    return FullAnswer


_FULL_ANSWER = None


def full_answer_model():
    global _FULL_ANSWER
    if _FULL_ANSWER is None:
        _FULL_ANSWER = _full_answer_model()
    return _FULL_ANSWER


@dataclass
class FullParse:
    modules: dict
    n_fields_kept: int = 0
    n_values_dropped: int = 0
    parse_ok: bool = False
    notes: list[str] = field(default_factory=list)


def parse_full(raw: str) -> FullParse:
    obj = _json_obj(raw)
    if obj is None:
        return FullParse(modules={}, notes=["no_json"])
    out = FullParse(modules={}, parse_ok=True)
    cs: dict = {}
    eeg: dict = {}
    med: dict = {}
    mri: dict = {}
    loc: dict = {}
    integ: dict = {}

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

    def scalar_text(key: str, target: dict, name: str) -> None:
        item = obj.get(key)
        if not isinstance(item, dict):
            return
        val = item.get("value")
        if not isinstance(val, str) or not val.strip():
            return
        if not quoted(item):
            drop(f"{key}:no_quote")
            return
        target[name] = _ev(val.strip(), item["quote"])
        keep()

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

    scalar_text("semiology", cs, "semiology_text")
    scalar_text("etiology_details", cs, "etiology_details_text")
    scalar_text("adverse_effects", med, "adverse_effects_text")
    scalar_text("concordance_notes", integ, "concordance_notes_text")
    scalar_enum("drug_resistance", DRUG_RES, med, "drug_resistance_status")
    scalar_enum("concordance", CONCORD, integ, "concordance")
    scalar_bool("mri_negative", mri, "mri_negative_for_epilepsy")

    tesla = obj.get("field_strength_tesla")
    if isinstance(tesla, dict) and tesla.get("value") is not None:
        t = _num(tesla.get("value"))
        if t is None or round(t, 1) not in (1.5, 3.0, 7.0) or not quoted(tesla):
            drop("field_strength_tesla:bad_or_no_quote")
        else:
            mri["field_strength_tesla"] = _ev(t, tesla["quote"])
            keep()

    cap = obj.get("seizures_captured_count")
    if isinstance(cap, dict) and cap.get("value") is not None:
        n = _num(cap.get("value"))
        if n is None or n < 0 or n > 100 or not quoted(cap):
            drop("seizures_captured_count:bad_or_no_quote")
        else:
            eeg["seizures_captured_count"] = _ev(int(n), cap["quote"])
            keep()

    freqs = obj.get("other_frequencies")
    if isinstance(freqs, list):
        items = []
        for it in freqs:
            if not isinstance(it, dict) or not quoted(it):
                if isinstance(it, dict) and (it.get("count_min") is not None or it.get("period")):
                    drop("other_frequencies:no_quote")
                continue
            lo, hi = _num(it.get("count_min")), _num(it.get("count_max"))
            per = pick(it, "period", PERIODS, "other_frequencies") if it.get("period") else None
            sz = pick(it, "seizure_type", SEIZURE_TYPES, "other_frequencies") if it.get("seizure_type") else None
            if lo is None and hi is None and per is None:
                continue
            q = it["quote"]
            items.append(_ev({
                "raw_text": q, "period": per or "unspecified",
                "count_min": lo, "count_max": hi, "seizure_free": False,
                "applies_to_type": sz,
            }, q))
            keep()
        if items:
            cs["other_seizure_frequencies"] = items

    spec = obj.get("etiology_specifics")
    if isinstance(spec, dict) and quoted(spec):
        gene = spec.get("gene") if isinstance(spec.get("gene"), str) else None
        variant = spec.get("variant") if isinstance(spec.get("variant"), str) else None
        antibody = pick(spec, "antibody", ANTIBODIES, "etiology_specifics")
        pathogen = spec.get("pathogen") if isinstance(spec.get("pathogen"), str) else None
        metabolic = spec.get("metabolic") if isinstance(spec.get("metabolic"), str) else None
        tumor = spec.get("tumor") if isinstance(spec.get("tumor"), str) else None
        slots = {
            "causative_gene": (gene or "").strip().upper() or None,
            "causative_variant": (variant or "").strip() or None,
            "causative_antibody": antibody,
            "causative_pathogen_text": (pathogen or "").strip() or None,
            "causative_metabolic_text": (metabolic or "").strip() or None,
            "associated_tumor_text": (tumor or "").strip() or None,
        }
        if any(slots.values()):
            cs["etiology_specifics"] = _ev(slots, spec["quote"])
            keep()

    alts = obj.get("alternative_localization")
    if isinstance(alts, list):
        items, seen = [], set()
        for it in alts:
            if not isinstance(it, dict):
                continue
            lobe, side = pick(it, "lobe", LOBES, "alternative_localization"), pick(it, "side", SIDES, "alternative_localization")
            if not (lobe and side) or not quoted(it) or (lobe, side) in seen:
                if (lobe or side) and not quoted(it):
                    drop("alternative_localization:no_quote")
                continue
            seen.add((lobe, side))
            items.append(_ev({"lobe": lobe, "laterality": side, "source": "clinician_hypothesis"}, it["quote"]))
            keep()
        if items:
            loc["alternative_claims"] = items

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
    if integ:
        out.modules["integrated"] = integ
    return out


__all__ = ["FULL_ARM", "FULL_FIELD_PATHS", "FULL_MAX_NOTE_CHARS", "FULL_PROMPT_VERSION",
           "build_full_prompt", "parse_full", "full_answer_model"]
