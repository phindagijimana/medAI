"""Stated-only guideline sidecars (no new training, not dumped into E).

Each detector fires only when the note *says* the fact. Silence is not a
vote against E (D18: sidecar cannot demote an accept). See EVAL D20.

Sources: NINDS Epilepsy CDEs; Kwan 2010; Pina-Garza 2024; ACNS Hirsch 2013/2021;
Fisher 2017 instruction manual; Uzuner 2010 (acute already on ``ctakes``).
Engel/ILAE class is not registered (schema-ready, not a LEO catalogue column).
"""

from __future__ import annotations

import re

from services.chain_llm import FieldItem
from services.ext_detectors.span import (
    HYPO,
    family_only,
    sentence_window,
    skip_mention,
)

# ---------------------------------------------------------------------------
# Shared FieldItem helpers
# ---------------------------------------------------------------------------


def _scalar(detector: str, path: str, module: str, value, quote: str,
            start: int, end: int, *, multi: bool = False) -> FieldItem:
    return FieldItem(
        field_path=path,
        module=module,
        ev={
            "value": value,
            "evidence_text": quote,
            "char_start": start,
            "char_end": end,
            "certainty": "definite",
            "temporal_status": "current",
            "reader": detector,
        },
        multi=multi,
    )


def _drug(detector: str, path: str, generic: str, quote: str, start: int, end: int,
          reason: str | None = None) -> FieldItem:
    val: dict = {"generic_name": generic}
    if reason:
        val["reason_discontinued"] = reason
    return _scalar(detector, path, "medication", val, quote, start, end, multi=True)


def _q(text: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", text[start:end].strip())


# ---------------------------------------------------------------------------
# fail-reason — NINDS CDE discontinuation reason + Kwan 2010
# ---------------------------------------------------------------------------

_EFFICACY = re.compile(
    r"\b(?:lack of (?:effect|efficacy|control|benefit)|ineffective|"
    r"not (?:controlled|effective)|breakthrough|failed to control|"
    r"no (?:benefit|response|effect)|still (?:having|had) seizures)\b",
    re.I,
)
_ADE = re.compile(
    r"\b(?:not tolerated|intolerable|side effects?|adverse effects?|"
    r"rash|allergic|toxicity|due to (?:a )?rash)\b",
    re.I,
)
_WEAN = re.compile(
    r"\b(?:weaned|tapered|stopped)\b.*\bseizure[- ]free\b|"
    r"\bseizure[- ]free\b.*\b(?:weaned|tapered|discontinued)\b",
    re.I,
)


def extract_fail_reason(text: str) -> list[FieldItem]:
    """failed_asms only when a reason is written; wean → prior, not failed."""
    from services.ext_detectors.ctakes_meds import iter_asm_spans
    out: list[FieldItem] = []
    seen: set[tuple[str, str]] = set()
    for generic, start, end, sent, a, _b in iter_asm_spans(text):
        if family_only(sent, a) or (HYPO.search(sent) and "failed" not in sent.lower()):
            continue
        near = sent
        if _WEAN.search(near):
            path, reason = "medication.prior_asms", "seizure_free_wean"
        elif _EFFICACY.search(near):
            path, reason = "medication.failed_asms", "lack_of_efficacy"
        elif _ADE.search(near):
            path, reason = "medication.failed_asms", "adverse_effect"
        else:
            continue
        key = (path, generic)
        if key in seen:
            continue
        seen.add(key)
        out.append(_drug("fail-reason", path, generic, _q(text, start, end),
                         start, end, reason))
    return out


# ---------------------------------------------------------------------------
# rescue-if — Pina-Garza 2024; skip hypothetical / inpatient instruction
# ---------------------------------------------------------------------------

_HOME_RESCUE = re.compile(
    r"\b(?:rescue|at home|has (?:a )?rescue|prescribed (?:for )?clusters?|"
    r"p\.?\s?r\.?\s?n\.?|as[\s-]+needed|buccal|intranasal|nasal spray|"
    r"diastat|valtoco|nayzilam)\b",
    re.I,
)
_INSTRUCTION = re.compile(
    r"\b(?:if (?:he|she|they|the patient)\s+(?:has|have|should)|"
    r"should (?:he|she) have|in case of|were to have|"
    r"instruct(?:ed)? to (?:give|use)|if there is a cluster)\b",
    re.I,
)
_INPATIENT = re.compile(
    r"\b(?:inpatient|on the ward|while (?:in |admitted)|hospital PRN|"
    r"during (?:this )?admission)\b",
    re.I,
)


def extract_rescue_if(text: str) -> list[FieldItem]:
    """Home PRN rescue only. Instructional if-clauses and inpatient PRN are silent."""
    from services.ext_detectors.ctakes_meds import iter_asm_spans
    out: list[FieldItem] = []
    seen: set[str] = set()
    for generic, start, end, sent, a, _b in iter_asm_spans(text):
        if skip_mention(sent, a):
            continue
        if _INSTRUCTION.search(sent) or HYPO.search(sent) or _INPATIENT.search(sent):
            continue
        if not _HOME_RESCUE.search(sent):
            continue
        if generic in seen:
            continue
        seen.add(generic)
        out.append(_drug("rescue-if", "medication.rescue_medication", generic,
                         _q(text, start, end), start, end))
    return out


# ---------------------------------------------------------------------------
# ictal — ACNS Hirsch: captured electrographic seizure vs not captured
# ---------------------------------------------------------------------------

_NOT_CAPTURED = re.compile(
    r"\bno\s+(?:ictal\s+onset|seizures?\s+captured|electrographic\s+seizures?)\b|"
    r"\b(?:ictal\s+onset|seizures?)\s+not\s+(?:captured|recorded|seen)\b",
    re.I,
)
_CAPTURED = re.compile(
    r"\b(?:seizure|ictal(?:\s+onset)?)\s+(?:was\s+)?(?:captured|recorded)\b|"
    r"\belectrographic\s+seizure\b|"
    r"\bictal\s+onset\b",
    re.I,
)
_LOBE = re.compile(
    r"\b(?P<side>left|right|bilateral)\s+(?P<lobe>frontal|temporal|parietal|"
    r"occipital|insular|cingulate)\b|"
    r"\b(?P<lobe2>frontal|temporal|parietal|occipital|insular|cingulate|"
    r"multifocal)\b",
    re.I,
)
_EEG_CTX = re.compile(r"\b(?:EEG|electrographic|ictal)\b", re.I)


def extract_ictal(text: str) -> list[FieldItem]:
    """Lobe/side only if a seizure was captured; else seizures_captured=false."""
    if not (text or "").strip():
        return []
    out: list[FieldItem] = []
    m_no = _NOT_CAPTURED.search(text)
    if m_no:
        sent, a, _b = sentence_window(text, m_no.start(), m_no.end())
        if not skip_mention(sent, a):
            out.append(_scalar(
                "ictal", "eeg.seizures_captured", "eeg", False,
                _q(text, m_no.start(), m_no.end()), m_no.start(), m_no.end(),
            ))
            return out
    for m in _CAPTURED.finditer(text):
        sent, a, _b = sentence_window(text, m.start(), m.end())
        if skip_mention(sent, a) or not _EEG_CTX.search(sent):
            continue
        loc = _LOBE.search(sent)
        quote = _q(text, m.start(), m.end())
        cs, ce = m.start(), m.end()
        if not loc:
            out.append(_scalar(
                "ictal", "eeg.seizures_captured", "eeg", True, quote, cs, ce,
            ))
            break
        side = (loc.group("side") or "").lower() or None
        lobe = (loc.group("lobe") or loc.group("lobe2") or "").lower()
        if lobe:
            out.append(_scalar("ictal", "eeg.ictal_onset_lobe", "eeg", lobe,
                               quote, cs, ce))
        if side:
            out.append(_scalar("ictal", "eeg.ictal_onset_laterality", "eeg", side,
                               quote, cs, ce))
        out.append(_scalar("ictal", "eeg.seizures_captured", "eeg", True,
                           quote, cs, ce))
        break
    return out


# ---------------------------------------------------------------------------
# eeg-done — study type only if performed, not recommended
# ---------------------------------------------------------------------------

_RECOMMENDED = re.compile(
    r"\b(?:recommend(?:ed)?|consider(?:ed)?|pending|not (?:yet )?(?:available|obtained|performed)|"
    r"to be (?:scheduled|arranged)|if (?:possible|needed))\b",
    re.I,
)
_PERFORMED = re.compile(
    r"\b(?:was |were |is |are )?(?:performed|obtained|completed|showed|demonstrated|revealed)\b",
    re.I,
)
_STUDY: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bSEEG\b|stereo[- ]?EEG", re.I), "seeg"),
    (re.compile(r"\bECoG\b|electrocorticograph", re.I), "ecog"),
    (re.compile(r"\bEMU\b|epilepsy monitoring unit", re.I), "emu"),
    (re.compile(r"video[- ]?EEG|vEEG", re.I), "video_eeg"),
    (re.compile(r"ambulatory\s+EEG", re.I), "ambulatory"),
    (re.compile(r"prolonged\s+EEG|long[- ]term\s+EEG|LTM", re.I), "prolonged"),
    (re.compile(r"intraoperative\s+EEG", re.I), "intraoperative"),
    (re.compile(r"\b(?:routine|standard|30[- ]minute)\s+EEG\b|\bEEG\b", re.I), "routine"),
]


def extract_eeg_done(text: str) -> list[FieldItem]:
    """eeg.study_type only when the study was done, not advised."""
    if not (text or "").strip():
        return []
    for pat, value in _STUDY:
        for m in pat.finditer(text):
            sent, a, _b = sentence_window(text, m.start(), m.end())
            if skip_mention(sent, a):
                continue
            if _RECOMMENDED.search(sent) and not _PERFORMED.search(sent):
                continue
            if not _PERFORMED.search(sent) and value == "routine" and m.group(0).upper() == "EEG":
                # Bare "EEG" without a performed verb — too weak.
                continue
            return [_scalar("eeg-done", "eeg.study_type", "eeg", value,
                            _q(text, m.start(), m.end()), m.start(), m.end())]
    return []


# ---------------------------------------------------------------------------
# dre — Kwan 2010 / Xie 2023 *task*: as-stated only, no two-drug inference
# ---------------------------------------------------------------------------

_RESISTANT = re.compile(
    r"\b(?:drug[- ]resistant(?:\s+epilepsy)?|intractable\s+epilepsy|"
    r"refractory\s+epilepsy)\b",
    re.I,
)
_RESPONSIVE = re.compile(
    r"\bdrug[- ]responsive(?:\s+epilepsy)?\b",
    re.I,
)


def extract_dre(text: str) -> list[FieldItem]:
    """medication.drug_resistance_status from explicit phrases only."""
    if not (text or "").strip():
        return []
    for pat, value in ((_RESPONSIVE, "drug_responsive"), (_RESISTANT, "drug_resistant")):
        for m in pat.finditer(text):
            sent, a, _b = sentence_window(text, m.start(), m.end())
            if skip_mention(sent, a):
                continue
            return [_scalar("dre", "medication.drug_resistance_status", "medication",
                            value, _q(text, m.start(), m.end()), m.start(), m.end())]
    return []


# ---------------------------------------------------------------------------
# first-feature — Fisher 2017: first prominent sign, not whole-seizure semiology
# ---------------------------------------------------------------------------

_ONSET_CUE = re.compile(
    r"\b(?:begins?\s+with|starts?\s+with|onset\s+with|at\s+onset|"
    r"first\s+(?:sign|symptom|feature|prominent))\b",
    re.I,
)
_MOTOR: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bautomatisms?|chewing|lip[- ]smacking|picking\b", re.I), "automatisms"),
    (re.compile(r"\batonic|loss of tone\b", re.I), "atonic"),
    (re.compile(r"\bclonic|rhythmic jerking\b", re.I), "clonic"),
    (re.compile(r"\b(?:epileptic\s+)?spasms?\b", re.I), "epileptic_spasms"),
    (re.compile(r"\bhyperkinetic|pedall?ing|thrashing\b", re.I), "hyperkinetic"),
    (re.compile(r"\bmyoclonic\b", re.I), "myoclonic"),
    (re.compile(r"\btonic|stiffening|versive\b", re.I), "tonic"),
]
_NONMOTOR: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bautonomic|epigastric\s+rising\b", re.I), "autonomic"),
    (re.compile(r"\bbehavior(?:al)?\s+arrest|arrest of activity\b", re.I), "behavior_arrest"),
    (re.compile(r"\bcognitive|aphasia|deja vu|jamais vu\b", re.I), "cognitive"),
    (re.compile(r"\bemotional|\bfear\b|panic\b", re.I), "emotional"),
    (re.compile(r"\bsensory|tingling|visual aura|olfactory\b", re.I), "sensory"),
]


def extract_first_feature(text: str) -> list[FieldItem]:
    """focal_motor_onset / focal_nonmotor_onset only with an onset cue in-sentence."""
    if not (text or "").strip():
        return []
    out: list[FieldItem] = []
    for m in _ONSET_CUE.finditer(text):
        sent, a, _b = sentence_window(text, m.start(), m.end())
        if skip_mention(sent, a):
            continue
        for pat, value in _MOTOR:
            hit = pat.search(sent)
            if not hit:
                continue
            out.append(_scalar(
                "first-feature", "clinical_seizure.focal_motor_onset",
                "clinical_seizure", value, _q(text, m.start(), m.end()),
                m.start(), m.end(),
            ))
            break
        for pat, value in _NONMOTOR:
            hit = pat.search(sent)
            if not hit:
                continue
            out.append(_scalar(
                "first-feature", "clinical_seizure.focal_nonmotor_onset",
                "clinical_seizure", value, _q(text, m.start(), m.end()),
                m.start(), m.end(),
            ))
            break
        if out:
            break
    return out


__all__ = [
    "extract_dre",
    "extract_eeg_done",
    "extract_fail_reason",
    "extract_first_feature",
    "extract_ictal",
    "extract_rescue_if",
]
