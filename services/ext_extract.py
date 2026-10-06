"""Second reader for the extended fields: flat contract ``X1C`` (arm "X1C", prompt version ``EXT_PROMPT_VERSION``).

Why this exists.  The LEO model reader (``services.flat_extract``, arm L1C) reads five fields.  For every other
field the rules (EpExtra) are the only reader, so nothing cross-checks them (``docs/EVAL_PROTOCOL_LEO.md`` 10.21,
10.22).  X1C is a second, separate call on the same note that reads the fields the rules can produce and a model can
check against a quote:

==============================  ==========================================  ================================
what the model reads            specialist field path it is paired with     vocabulary (= the rules' value ids)
==============================  ==========================================  ================================
EEG study type                  ``eeg.study_type``                          ``EegStudyType``
EEG background                  ``eeg.background``                          ``EegBackground`` (minus "other")
interictal discharges present   ``eeg.ied_present``                        true / false
interictal discharge sites      ``eeg.ied_findings`` (lobe, side)           ``LobarLocalization`` / ``Laterality``
ictal onset lobe / side         ``eeg.ictal_onset_lobe`` / ``..._laterality``  same enums
focal motor onset               ``clinical_seizure.focal_motor_onset``      ``FocalMotorOnset``
focal non-motor onset           ``clinical_seizure.focal_nonmotor_onset``   ``FocalNonmotorOnset``
rescue drugs                    ``medication.current_asms`` (see below)     generic drug name
epilepsy surgery / stimulator   ``medication.surgery_history``              ``SurgeryType`` (by type)
==============================  ==========================================  ================================

Not read: ``clinical_seizure.semiology_text`` (free text, nothing to pair it with), MRI, etiology, drug
resistance, prior and failed ASMs: those stay "needs review: no second reader".

Rescue drugs are emitted under ``medication.current_asms``, the path the rules use for every drug mention, marked
``reader = "X1C"``.  The pipeline already separates rescue and maintenance drugs by the words around each mention
(``ChainPipeline._drug_role``), so a drug that both readers name is fused by drug name first and routed to
``medication.rescue_medication`` afterwards, and the merge with the L1C list keeps one entry per drug.

The prompt and the two worked examples were written for this project before any evaluation (they are synthetic and
not derived from any corpus).  They are not tuned on any evaluation set.  This module has no torch dependency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from services.flat_extract import _ev, _json_obj, _norm_enum

EXT_PROMPT_VERSION = "v1"
EXT_ARM = "X1C"

# Vocabularies: value ids of schema/enums.py, so the fuser can pair them with the specialist's values.
EEG_STUDY_TYPES = ("routine", "prolonged", "ambulatory", "video_eeg", "emu", "intraoperative", "seeg", "ecog")
EEG_BACKGROUNDS = ("normal", "diffuse_slowing", "focal_slowing", "asymmetric", "suppressed", "burst_suppression")
LOBES = ("frontal", "temporal", "parietal", "occipital", "insular", "cingulate", "multifocal")
SIDES = ("left", "right", "bilateral", "midline", "diffuse")
FOCAL_MOTOR_ONSETS = ("automatisms", "atonic", "clonic", "epileptic_spasms", "hyperkinetic", "myoclonic", "tonic")
FOCAL_NONMOTOR_ONSETS = ("autonomic", "behavior_arrest", "cognitive", "emotional", "sensory")
SURGERY_TYPES = ("resection", "laser_ablation", "disconnection", "hemispherectomy", "callosotomy",
                 "neurostimulation_vns", "neurostimulation_rns", "neurostimulation_dbs", "other")

# Specialist field paths this reader can corroborate: exactly what ``parse_ext`` emits (checked against it by
# tests/test_leo_ext_reader.py).  ``medication.current_asms`` is deliberately absent: X1C reads only the rescue
# drugs among them, so it never vouches for the maintenance list (that is L1C's).
EXT_FIELD_PATHS = frozenset({
    "clinical_seizure.focal_motor_onset",
    "clinical_seizure.focal_nonmotor_onset",
    "eeg.study_type",
    "eeg.background",
    "eeg.ied_present",
    "eeg.ied_findings",
    "eeg.ictal_onset_lobe",
    "eeg.ictal_onset_laterality",
    "medication.surgery_history",
})
# Marker on rescue-drug evidence, so the pipeline does not mistake it for the L1C reader having listed drugs.
READER_KEY = "reader"

# A prompt of this size plus the note must fit the 3200-token input limit of constrained decoding
# (services/constrained_decode.py): notes longer than this are split by the reader itself.
EXT_MAX_NOTE_CHARS = 5000

_INSTRUCTIONS = f"""You read one patient's epilepsy clinic note and report only the items below.
Reply with ONE JSON object and nothing else. Use null (or an empty list) for anything the note does not state.
Every non-null value needs "quote": the exact words copied from the note that support it.

Rules for every item:
- Report what the note says was DONE or IS TRUE for this patient. Do not report advice, requests, plans, options or
  things to be considered ("video-EEG recommended", "will discuss surgery"), tests that were not available or not done,
  or findings the note calls only possible or suspected.
- A finding the note denies is reported as false or left out, never as present.

Items:
- eeg_study: the kind of EEG that was actually done, one of {list(EEG_STUDY_TYPES)} or null
  (routine = routine, standard or 30-minute EEG; prolonged = prolonged or long-term EEG; emu = epilepsy monitoring unit stay)
- eeg_background: the EEG background, one of {list(EEG_BACKGROUNDS)} or null
- interictal_discharges: present = true if the EEG showed spikes, sharp waves or other epileptiform discharges between
  seizures, false if the note says there were none, null if not stated
- interictal_sites: where the discharges were, up to 3 entries: lobe one of {list(LOBES)} or null, side one of {list(SIDES)} or null
- ictal_onset: where a recorded seizure STARTED on EEG (not the interictal discharges, not the MRI): lobe and side, same values
- focal_motor_onset: how a focal seizure BEGINS, if the first prominent feature is motor: one of {list(FOCAL_MOTOR_ONSETS)} or null
  (automatisms = chewing, lip smacking, picking; clonic = rhythmic jerking; tonic = stiffening; hyperkinetic = thrashing, pedalling)
- focal_nonmotor_onset: how a focal seizure BEGINS, if the first prominent feature is not motor: one of {list(FOCAL_NONMOTOR_ONSETS)} or null
  (autonomic = epigastric rising, flushing, pallor; behavior_arrest = staring, arrest; cognitive = deja vu, speech or memory
  disturbance; emotional = fear, joy; sensory = tingling, visual, smell, sound)
  Classify by the FIRST prominent sign or symptom (ILAE 2017). Features that appear later in the seizure (spread, loss of
  awareness, automatisms after the start) are not the onset.
- rescue_drugs: medicines taken only AS NEEDED for a seizure emergency (rescue, PRN, "for seizures lasting more than N minutes",
  buccal, intranasal or rectal). Not the daily medicines. Generic names.
- surgery: epilepsy surgery or an implanted stimulator the patient HAS HAD, one type from {list(SURGERY_TYPES)}. Not planned,
  discussed or being considered; not "no surgery".

JSON shape:
{{"eeg_study": {{"value": null, "quote": null}},
 "eeg_background": {{"value": null, "quote": null}},
 "interictal_discharges": {{"present": null, "quote": null}},
 "interictal_sites": [{{"lobe": "temporal", "side": "left", "quote": "left temporal spikes"}}],
 "ictal_onset": {{"lobe": null, "side": null, "quote": null}},
 "focal_motor_onset": {{"value": null, "quote": null}},
 "focal_nonmotor_onset": {{"value": null, "quote": null}},
 "rescue_drugs": [{{"name": "midazolam", "dose": "10 mg buccal", "quote": "buccal midazolam 10 mg"}}],
 "surgery": [{{"type": "resection", "quote": "temporal lobectomy"}}]}}
"""

# Two worked examples, written for this project.  Not derived from any corpus or letter.  Each answer quote is a
# verbatim span of its note (checked by the tests).
_EXAMPLES = [
    ("""Mr Okafor, 52, has focal epilepsy. His seizures begin with clonic jerking of the right hand; later in the seizure he becomes unresponsive. A routine EEG last month showed a normal background with left frontal spikes. He had a corpus callosotomy in 2015. He takes levetiracetam 1000 mg twice daily and keeps rectal diazepam 10 mg for seizures lasting more than five minutes. I have asked for a video-EEG admission and will discuss a vagus nerve stimulator with him.""",
     {"eeg_study": {"value": "routine", "quote": "routine EEG"},
      "eeg_background": {"value": "normal", "quote": "normal background"},
      "interictal_discharges": {"present": True, "quote": "left frontal spikes"},
      "interictal_sites": [{"lobe": "frontal", "side": "left", "quote": "left frontal spikes"}],
      "ictal_onset": {"lobe": None, "side": None, "quote": None},
      "focal_motor_onset": {"value": "clonic", "quote": "clonic jerking of the right hand"},
      "focal_nonmotor_onset": {"value": None, "quote": None},
      "rescue_drugs": [{"name": "diazepam", "dose": "10 mg rectal",
                        "quote": "rectal diazepam 10 mg for seizures lasting more than five minutes"}],
      "surgery": [{"type": "callosotomy", "quote": "corpus callosotomy in 2015"}]}),
    ("""Ms Lindqvist, 29, has temporal lobe epilepsy. Her seizures start with a sudden wave of fear, then lip smacking, then she loses awareness. Video-EEG monitoring last year recorded three seizures with onset in the right temporal lobe. The background showed diffuse slowing and there were no epileptiform discharges. She has not had epilepsy surgery. She takes lacosamide 100 mg twice daily and has no rescue medicine.""",
     {"eeg_study": {"value": "video_eeg", "quote": "Video-EEG monitoring"},
      "eeg_background": {"value": "diffuse_slowing", "quote": "diffuse slowing"},
      "interictal_discharges": {"present": False, "quote": "no epileptiform discharges"},
      "interictal_sites": [],
      "ictal_onset": {"lobe": "temporal", "side": "right", "quote": "onset in the right temporal lobe"},
      "focal_motor_onset": {"value": None, "quote": None},
      "focal_nonmotor_onset": {"value": "emotional", "quote": "a sudden wave of fear"},
      "rescue_drugs": [],
      "surgery": []}),
]


def build_ext_prompt(note: str) -> str:
    """Prompt text of arm X1C: instructions, two fixed synthetic examples, then the note."""
    parts = [_INSTRUCTIONS]
    for text, ans in _EXAMPLES:
        parts.append(f'Example note:\n"""\n{text}\n"""\nJSON:\n{json.dumps(ans)}\n')
    parts.append(f'Note:\n"""\n{note}\n"""\nJSON:\n')
    return "\n".join(parts)


# ─── Constrained-decoding schema ─────────────────────────────────────────

def _ext_answer_model():
    """Pydantic model of the X1C JSON answer (built lazily; used by ``generate_constrained``)."""
    from typing import Literal

    from pydantic import BaseModel, Field

    Quote = Optional[str]

    def _scalar(vocab):
        V = Literal[vocab]                                   # type: ignore[valid-type]

        class _S(BaseModel):
            value: Optional[V] = None                        # type: ignore[valid-type]
            quote: Quote = Field(default=None, max_length=160)

        return _S

    Lobe = Literal[LOBES]                                    # type: ignore[valid-type]
    Side = Literal[SIDES]                                    # type: ignore[valid-type]
    Surg = Literal[SURGERY_TYPES]                            # type: ignore[valid-type]

    class _Ied(BaseModel):
        present: Optional[bool] = None
        quote: Quote = Field(default=None, max_length=160)

    class _Site(BaseModel):
        lobe: Optional[Lobe] = None                          # type: ignore[valid-type]
        side: Optional[Side] = None                          # type: ignore[valid-type]
        quote: str = Field(max_length=160)

    class _Ictal(BaseModel):
        lobe: Optional[Lobe] = None                          # type: ignore[valid-type]
        side: Optional[Side] = None                          # type: ignore[valid-type]
        quote: Quote = Field(default=None, max_length=160)

    class _Drug(BaseModel):
        name: str = Field(max_length=40)
        dose: Optional[str] = Field(default=None, max_length=40)
        quote: str = Field(max_length=160)

    class _Surgery(BaseModel):
        type: Surg                                           # type: ignore[valid-type]
        quote: str = Field(max_length=160)

    class ExtAnswer(BaseModel):
        eeg_study: _scalar(EEG_STUDY_TYPES)                  # type: ignore[valid-type]
        eeg_background: _scalar(EEG_BACKGROUNDS)             # type: ignore[valid-type]
        interictal_discharges: _Ied
        interictal_sites: list[_Site] = Field(max_length=3)
        ictal_onset: _Ictal
        focal_motor_onset: _scalar(FOCAL_MOTOR_ONSETS)       # type: ignore[valid-type]
        focal_nonmotor_onset: _scalar(FOCAL_NONMOTOR_ONSETS)  # type: ignore[valid-type]
        rescue_drugs: list[_Drug] = Field(max_length=4)
        surgery: list[_Surgery] = Field(max_length=4)

    return ExtAnswer


_EXT_ANSWER = None


def ext_answer_model():
    global _EXT_ANSWER
    if _EXT_ANSWER is None:
        _EXT_ANSWER = _ext_answer_model()
    return _EXT_ANSWER


# ─── Parsing ─────────────────────────────────────────────────────────────

@dataclass
class ExtParse:
    modules: dict
    n_fields_kept: int = 0
    n_values_dropped: int = 0        # present but out of vocabulary, or without a quote
    parse_ok: bool = False
    notes: list[str] = field(default_factory=list)


def parse_ext(raw: str) -> ExtParse:
    """X1C JSON text -> ``{module: {field: Evidence-dict | [Evidence-dict]}}`` for the fuser.

    Same conventions as ``parse_flat``: values outside the closed vocabularies are dropped (counted), and a value
    without a verbatim quote is dropped (LEO cannot check it).  Keys the model was not asked for are ignored.
    """
    obj = _json_obj(raw)
    if obj is None:
        return ExtParse(modules={}, notes=["no_json"])
    out = ExtParse(modules={}, parse_ok=True)
    cs: dict = {}
    eeg: dict = {}
    med: dict = {}

    def keep(n: int = 1) -> None:
        out.n_fields_kept += n

    def drop(why: str) -> None:
        out.n_values_dropped += 1
        out.notes.append(why)

    def pick(item: dict, key: str, allowed: tuple[str, ...], tag: str) -> Optional[str]:
        """A vocabulary value from ``item[key]``, or None (counted when present but unusable)."""
        raw_v = item.get(key)
        if raw_v is None:
            return None
        v = _norm_enum(raw_v)
        if v is None or v == "":
            return None
        if v not in allowed:
            drop(f"{tag}:out_of_vocab:{v}")
            return None
        return v

    def scalar(key: str, allowed: tuple[str, ...], target: dict, name: str) -> None:
        item = obj.get(key)
        if not isinstance(item, dict):
            return
        val = pick(item, "value", allowed, key)
        if val is None:
            return
        if not item.get("quote"):
            drop(f"{key}:no_quote")
            return
        target[name] = _ev(val, item["quote"])
        keep()

    scalar("eeg_study", EEG_STUDY_TYPES, eeg, "study_type")
    scalar("eeg_background", EEG_BACKGROUNDS, eeg, "background")
    scalar("focal_motor_onset", FOCAL_MOTOR_ONSETS, cs, "focal_motor_onset")
    scalar("focal_nonmotor_onset", FOCAL_NONMOTOR_ONSETS, cs, "focal_nonmotor_onset")

    # interictal discharges: present / absent, then where
    present: Optional[bool] = None
    ied = obj.get("interictal_discharges")
    if isinstance(ied, dict) and isinstance(ied.get("present"), bool):
        if ied.get("quote"):
            present = ied["present"]
            eeg["ied_present"] = _ev(present, ied["quote"])
            keep()
        else:
            drop("interictal_discharges:no_quote")
    sites = obj.get("interictal_sites")
    if isinstance(sites, list) and present is not False:
        items, seen = [], set()
        for s in sites:
            if not isinstance(s, dict):
                continue
            lobe, side = pick(s, "lobe", LOBES, "interictal_sites"), pick(s, "side", SIDES, "interictal_sites")
            if lobe is None and side is None:
                continue
            if not s.get("quote"):
                drop("interictal_sites:no_quote")
                continue
            if (lobe, side) in seen:
                continue
            seen.add((lobe, side))
            # ied_type is not read by X1C; values_agree compares lobe and side only (services.chain_llm).
            items.append(_ev({"ied_type": None, "localization": lobe, "laterality": side}, s["quote"]))
            keep()
        if items:
            eeg["ied_findings"] = items
    elif isinstance(sites, list) and sites:
        drop("interictal_sites:ignored_discharges_absent")

    # ictal onset: lobe and side share one quote
    ict = obj.get("ictal_onset")
    if isinstance(ict, dict):
        lobe, side = pick(ict, "lobe", LOBES, "ictal_onset"), pick(ict, "side", SIDES, "ictal_onset")
        if (lobe is not None or side is not None) and not ict.get("quote"):
            drop("ictal_onset:no_quote")
        else:
            if lobe is not None:
                eeg["ictal_onset_lobe"] = _ev(lobe, ict["quote"])
                keep()
            if side is not None:
                eeg["ictal_onset_laterality"] = _ev(side, ict["quote"])
                keep()

    # rescue drugs (under medication.current_asms; the pipeline splits rescue from maintenance by text role)
    drugs = obj.get("rescue_drugs")
    if isinstance(drugs, list):
        items, names = [], set()
        for d in drugs:
            if not isinstance(d, dict):
                continue
            name = d.get("name")
            if not isinstance(name, str) or not name.strip() or not d.get("quote"):
                drop("rescue_drugs:no_name_or_quote")
                continue
            name = name.strip().lower()
            if name in names:
                continue
            names.add(name)
            e = _ev({"generic_name": name, "status": "current",
                     "dose_text": d.get("dose") if isinstance(d.get("dose"), str) else None}, d["quote"])
            e[READER_KEY] = EXT_ARM
            items.append(e)
            keep()
        if items:
            med["current_asms"] = items

    # surgery / stimulators done
    surg = obj.get("surgery")
    if isinstance(surg, list):
        items, types = [], set()
        for s in surg:
            if not isinstance(s, dict):
                continue
            t = pick(s, "type", SURGERY_TYPES, "surgery")
            if t is None or t in types:
                continue
            if not s.get("quote"):
                drop("surgery:no_quote")
                continue
            types.add(t)
            items.append(_ev({"surgery_type": t}, s["quote"]))
            keep()
        if items:
            med["surgery_history"] = items

    if cs:
        out.modules["clinical_seizure"] = cs
    if eeg:
        out.modules["eeg"] = eeg
    if med:
        out.modules["medication"] = med
    return out


__all__ = ["EXT_ARM", "EXT_PROMPT_VERSION", "EXT_FIELD_PATHS", "EXT_MAX_NOTE_CHARS", "READER_KEY", "ExtParse",
           "build_ext_prompt", "ext_answer_model", "parse_ext", "EEG_STUDY_TYPES", "EEG_BACKGROUNDS", "LOBES", "SIDES",
           "FOCAL_MOTOR_ONSETS", "FOCAL_NONMOTOR_ONSETS", "SURGERY_TYPES"]
