"""Flat extraction prompts for the base Med42-8B (arms L0 / L1).

Why this exists.  The per-module M0/M1/M2 prompts ask an 8B model to fill
the full ``Evidence[T]`` schema (about 15 nested wrappers per field).  On the
40 held-out Fonferko-Shadrach letters that yields no usable output: M0/M1
produce non-JSON or schema-invalid text and M2 echoes the JSON Schema back
until the token limit; ``smart_repair`` then wraps the echo into an empty
module that counts as "valid" (``docs/EVAL_PROTOCOL_LEO.md``, findings F1-F3).

The flat family asks only for what the LEO chain fuses and the native gold
scores - five fields, each as ``{"value", "quote"}`` - and builds the
``Evidence`` wrappers in code.  Everything the model says must carry a
verbatim quote, which is how LEO checks it against the note.

* ``L0``  zero-shot flat prompt
* ``L1``  the same plus two fixed, synthetic worked examples (never F-S text)
* ``L1C`` / ``L2C``  the L1 / L2 prompt with schema-constrained decoding (``FlatAnswer``): the
          output cannot leave the JSON shape or the closed vocabularies, and generation stops at
          the closing brace.  Motivation: unconstrained L2 sometimes ignored the shape (4 of 40
          letters came back as bare nulls or strings) and always ran to the token limit.
* ``L2``  the same plus the ``k`` most similar annotated F-S *training* letters
          (EA0001-EA0160) with clinician-span quotes (``services.fewshot_bank``)

This module has no torch dependency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

FLAT_PROMPT_VERSION = "v1"
FLAT_ARMS = ("L0", "L1", "L2", "L0C", "L1C", "L2C")

EPILEPSY_TYPES = ("focal", "generalized", "combined_focal_generalized")
SEIZURE_TYPES = (
    "focal_aware", "focal_impaired_awareness", "focal_unknown_awareness",
    "focal_to_bilateral_tonic_clonic", "generalized_tonic_clonic",
    "generalized_tonic", "generalized_clonic", "generalized_myoclonic",
    "generalized_absence_typical", "generalized_absence_atypical",
    "generalized_atonic", "generalized_epileptic_spasms",
    "unknown_onset_tonic_clonic", "unknown_onset_motor_other",
    "unknown_onset_nonmotor",
)
PERIODS = ("day", "week", "month", "year")

_INSTRUCTIONS = f"""You extract facts about one patient's epilepsy from a clinic note.
Reply with ONE JSON object and nothing else. Use null for anything the note does not state.
Every non-null value needs "quote": the exact words copied from the note that support it.

Fields:
- epilepsy_type: one of {list(EPILEPSY_TYPES)} or null
- predominant_seizure_type: one of {list(SEIZURE_TYPES)} or null
- age_at_onset_years: a number or null
- seizure_frequency: count_min, count_max (numbers or null), period (one of {list(PERIODS)} or null), seizure_free (true/false/null)
- current_asms: anti-seizure medicines the patient takes NOW (not past, not planned), generic names

JSON shape:
{{"epilepsy_type": {{"value": null, "quote": null}},
 "predominant_seizure_type": {{"value": null, "quote": null}},
 "age_at_onset_years": {{"value": null, "quote": null}},
 "seizure_frequency": {{"count_min": null, "count_max": null, "period": null, "seizure_free": null, "quote": null}},
 "current_asms": [{{"name": "levetiracetam", "dose": "500 mg twice daily", "quote": "levetiracetam 500 mg twice daily"}}]}}
"""

# Two worked examples, written for this project.  Not derived from F-S letters.
_EXAMPLES = [
    ("""Dear Dr Smith, I saw Mr Jones, 41, who has had focal seizures with impaired awareness since the age of 12. He has about 3 to 4 seizures per month despite lamotrigine 200 mg twice daily. He stopped carbamazepine last year because of a rash.""",
     {"epilepsy_type": {"value": "focal", "quote": "focal seizures"},
      "predominant_seizure_type": {"value": "focal_impaired_awareness", "quote": "focal seizures with impaired awareness"},
      "age_at_onset_years": {"value": 12, "quote": "since the age of 12"},
      "seizure_frequency": {"count_min": 3, "count_max": 4, "period": "month", "seizure_free": False,
                            "quote": "3 to 4 seizures per month"},
      "current_asms": [{"name": "lamotrigine", "dose": "200 mg twice daily",
                        "quote": "lamotrigine 200 mg twice daily"}]}),
    ("""Ms Patel is a 19 year old with generalised epilepsy. She has had no seizures for two years on sodium valproate 500 mg twice daily. We discussed contraception.""",
     {"epilepsy_type": {"value": "generalized", "quote": "generalised epilepsy"},
      "predominant_seizure_type": {"value": None, "quote": None},
      "age_at_onset_years": {"value": None, "quote": None},
      "seizure_frequency": {"count_min": None, "count_max": None, "period": None, "seizure_free": True,
                            "quote": "no seizures for two years"},
      "current_asms": [{"name": "sodium valproate", "dose": "500 mg twice daily",
                        "quote": "sodium valproate 500 mg twice daily"}]}),
]


_BANK = None


def _bank():
    global _BANK
    if _BANK is None:
        from services.fewshot_bank import ExemplarBank
        _BANK = ExemplarBank()
    return _BANK


def build_flat_prompt(note: str, arm: str = "L0", *, exclude: str = "", k: int = 3) -> str:
    arm = arm[:-1] if arm.endswith("C") else arm      # L1C/L2C share the L1/L2 prompt text
    """Prompt text for arm L0 (zero-shot), L1 (two fixed examples) or L2 (k retrieved F-S training letters).

    ``exclude`` removes one letter id from the L2 bank (used when running on a
    development letter, so a letter is never its own example).
    """
    if arm not in ("L0", "L1", "L2"):
        raise ValueError(f"arm must be one of {FLAT_ARMS}, got {arm!r}")
    parts = [_INSTRUCTIONS]
    if arm == "L1":
        for text, ans in _EXAMPLES:
            parts.append(f'Example note:\n"""\n{text}\n"""\nJSON:\n{json.dumps(ans)}\n')
    elif arm == "L2":
        for ex in _bank().select(note, k=k, exclude=exclude):
            parts.append(f'Example note:\n"""\n{ex.text.strip()}\n"""\nJSON:\n{json.dumps(ex.answer)}\n')
    parts.append(f'Note:\n"""\n{note}\n"""\nJSON:\n')
    return "\n".join(parts)


# ─── Constrained-decoding schema ─────────────────────────────────────────

def _flat_answer_model():
    """Pydantic model of the flat JSON answer (built lazily; used by ``generate_constrained``)."""
    from typing import Literal

    from pydantic import BaseModel, Field

    Epi = Literal[EPILEPSY_TYPES]            # type: ignore[valid-type]
    Sz = Literal[SEIZURE_TYPES]              # type: ignore[valid-type]
    Per = Literal[PERIODS]                   # type: ignore[valid-type]
    Quote = Optional[str]

    class _Epi(BaseModel):
        value: Optional[Epi] = None
        quote: Quote = Field(default=None, max_length=160)

    class _Sz(BaseModel):
        value: Optional[Sz] = None
        quote: Quote = Field(default=None, max_length=160)

    class _Age(BaseModel):
        value: Optional[float] = None
        quote: Quote = Field(default=None, max_length=160)

    class _Freq(BaseModel):
        count_min: Optional[float] = None
        count_max: Optional[float] = None
        period: Optional[Per] = None
        seizure_free: Optional[bool] = None
        quote: Quote = Field(default=None, max_length=160)

    class _Asm(BaseModel):
        name: str = Field(max_length=40)
        dose: Optional[str] = Field(default=None, max_length=40)
        quote: str = Field(max_length=160)

    class FlatAnswer(BaseModel):
        epilepsy_type: _Epi
        predominant_seizure_type: _Sz
        age_at_onset_years: _Age
        seizure_frequency: _Freq
        current_asms: list[_Asm] = Field(max_length=12)

    return FlatAnswer


_FLAT_ANSWER = None


def flat_answer_model():
    global _FLAT_ANSWER
    if _FLAT_ANSWER is None:
        _FLAT_ANSWER = _flat_answer_model()
    return _FLAT_ANSWER


# ─── Parsing ─────────────────────────────────────────────────────────────

@dataclass
class FlatParse:
    modules: dict
    n_fields_kept: int = 0
    n_values_dropped: int = 0        # present but not in the allowed value set
    parse_ok: bool = False
    notes: list[str] = field(default_factory=list)


def _json_obj(raw: str) -> Optional[dict]:
    from services.extract import _extract_first_json_object, _strip_code_fence
    fenced = _strip_code_fence(raw or "")
    blob = _extract_first_json_object(fenced if fenced else (raw or ""))
    if not blob:
        return None
    try:
        obj = json.loads(blob)
    except Exception:
        try:
            import json_repair  # type: ignore
            obj = json_repair.loads(blob)
        except Exception:
            return None
    return obj if isinstance(obj, dict) else None


def _ev(value: Any, quote: Any) -> dict:
    return {"value": value, "certainty": "definite", "temporal_status": "current",
            "evidence_text": (str(quote).strip() if quote else None),
            "char_start": None, "char_end": None}


def _num(x: Any) -> Optional[float]:
    if isinstance(x, bool):
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _norm_enum(v: Any) -> Optional[str]:
    if not isinstance(v, str):
        return None
    return re.sub(r"[\s\-]+", "_", v.strip().lower())


def parse_flat(raw: str) -> FlatParse:
    """Flat JSON text -> ``{module: {field: Evidence-dict}}`` for the fuser.

    Values outside the closed vocabularies are dropped (counted), numbers
    are coerced, and a value without a quote is dropped: LEO cannot check
    it, and the compendium requires a span for every claim.
    """
    obj = _json_obj(raw)
    if obj is None:
        return FlatParse(modules={}, notes=["no_json"])
    out = FlatParse(modules={}, parse_ok=True)
    cs: dict = {}
    med: dict = {}

    def scalar(key: str, allowed: tuple[str, ...]) -> None:
        item = obj.get(key)
        if not isinstance(item, dict):
            return
        val = _norm_enum(item.get("value"))
        if val is None:
            return
        quote = item.get("quote")
        if val not in allowed:
            out.n_values_dropped += 1
            out.notes.append(f"{key}:out_of_vocab:{val}")
            return
        if not quote:
            out.n_values_dropped += 1
            out.notes.append(f"{key}:no_quote")
            return
        cs[key] = _ev(val, quote)
        out.n_fields_kept += 1

    scalar("epilepsy_type", EPILEPSY_TYPES)
    scalar("predominant_seizure_type", SEIZURE_TYPES)

    age = obj.get("age_at_onset_years")
    if isinstance(age, dict) and age.get("value") is not None:
        a = _num(age.get("value"))
        if a is None or not (0 <= a <= 100) or not age.get("quote"):
            out.n_values_dropped += 1
        else:
            cs["age_at_onset_years"] = _ev(a, age.get("quote"))
            out.n_fields_kept += 1

    sf = obj.get("seizure_frequency")
    if isinstance(sf, dict) and sf.get("quote"):
        period = _norm_enum(sf.get("period"))
        if period is not None and period not in PERIODS:
            out.n_values_dropped += 1
            period = None
        lo, hi = _num(sf.get("count_min")), _num(sf.get("count_max"))
        free = sf.get("seizure_free")
        free = free if isinstance(free, bool) else None
        if lo is not None and hi is None:
            hi = lo
        if any(x is not None for x in (period, lo, hi)) or free:
            cs["seizure_frequency"] = _ev({
                "raw_text": str(sf["quote"]), "period": period or "unspecified",
                "count_min": lo, "count_max": hi, "seizure_free": bool(free),
            }, sf["quote"])
            out.n_fields_kept += 1

    asms = obj.get("current_asms")
    if isinstance(asms, list):
        items = []
        for a in asms:
            if not isinstance(a, dict):
                continue
            name = a.get("name")
            if not isinstance(name, str) or not name.strip() or not a.get("quote"):
                out.n_values_dropped += 1
                continue
            items.append(_ev({"generic_name": name.strip().lower(), "status": "current",
                              "dose_text": a.get("dose") if isinstance(a.get("dose"), str) else None},
                             a["quote"]))
            out.n_fields_kept += 1
        if items:
            med["current_asms"] = items

    if cs:
        out.modules["clinical_seizure"] = cs
    if med:
        out.modules["medication"] = med
    return out


__all__ = ["flat_answer_model", "FLAT_ARMS", "FLAT_PROMPT_VERSION", "FlatParse", "build_flat_prompt", "parse_flat",
           "EPILEPSY_TYPES", "SEIZURE_TYPES", "PERIODS"]
