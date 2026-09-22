"""B0 rules baseline — EEG (paper Table 6).

Transparent regex/keyword extractor producing a valid `EegModule` from
EEG-report prose (or clinic-letter EEG paragraphs). Runs without an LLM.

Detection per field:
- study_type: routine / prolonged / ambulatory / video_eeg / emu / SEEG / ECoG
- background: normal / diffuse_slowing / focal_slowing / asymmetric /
  suppressed / burst_suppression / other
- ied_present: bool — any interictal epileptiform discharge phrase, negation-aware
- ied_findings: list — per detected IED type, nearest lobe + laterality + Hz
- seizures_captured: bool — negation-aware
- seizures_captured_count: int if a number is stated near "seizures captured"
- ictal_onset_lobe / ictal_onset_laterality: nearest lobe/lateral word to an
  "ictal onset" mention

Not designed for high recall — precision-first per B0 convention. Emits
`not_documented` when in doubt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from schema import DocumentMetadata


# ---------------------------------------------------------------------------
# Regex bank
# ---------------------------------------------------------------------------

_RE_STUDY_TYPE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"stereo[- ]?EEG|\bsEEG\b|\bSEEG\b"), "seeg"),
    (re.compile(r"\bECoG\b|electrocorticograph|intraoperative EEG", re.IGNORECASE), "ecog"),
    (re.compile(r"video[- ]?EEG", re.IGNORECASE), "video_eeg"),
    (re.compile(r"epilepsy monitoring unit|\bEMU\b\s*(?:study|admission|monitoring)?",
                re.IGNORECASE), "emu"),
    (re.compile(r"ambulatory EEG|\d+[- ]?hour ambulatory", re.IGNORECASE), "ambulatory"),
    (re.compile(r"prolonged EEG|long[- ]?term (?:EEG )?monitoring", re.IGNORECASE), "prolonged"),
    (re.compile(r"routine EEG|standard EEG|30[- ]?minute EEG", re.IGNORECASE), "routine"),
    (re.compile(r"intraoperative", re.IGNORECASE), "intraoperative"),
]

_RE_BACKGROUND: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"burst[- ]?suppression", re.IGNORECASE), "burst_suppression"),
    (re.compile(r"(diffuse|generalized|generalised)\s+slow(?:ing|-wave)?", re.IGNORECASE),
     "diffuse_slowing"),
    (re.compile(r"focal\s+slow(?:ing|-wave)?", re.IGNORECASE), "focal_slowing"),
    (re.compile(r"asymmetr(?:y|ic)", re.IGNORECASE), "asymmetric"),
    (re.compile(r"suppress(?:ed|ion)\s+background|electrocerebral silence",
                re.IGNORECASE), "suppressed"),
    (re.compile(r"normal\s+(?:background|posterior dominant rhythm)|"
                r"well[- ]?organi[sz]ed\s+(?:background|posterior dominant rhythm)|"
                r"posterior dominant rhythm\s+at\s+\d+", re.IGNORECASE), "normal"),
]

# IED type patterns
_RE_IED: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"3[- ]?Hz\s+spike[- ]and[- ]wave|3/s\s+spike[- ]?wave",
                re.IGNORECASE), "generalized_spike_wave_3hz"),
    (re.compile(r"polyspike[- ]and[- ]wave|polyspike[- ]?wave", re.IGNORECASE),
     "polyspike_and_wave"),
    (re.compile(r"\bpolyspikes?\b", re.IGNORECASE), "polyspike"),
    (re.compile(r"spike[- ]and[- ]wave|spike[- ]?wave complex(?:es)?", re.IGNORECASE),
     "spike_and_wave"),
    (re.compile(r"sharp[- ]and[- ]slow", re.IGNORECASE), "sharp_and_slow"),
    (re.compile(r"sharp\s+wave(?:s)?", re.IGNORECASE), "sharp_wave"),
    # Plain "spike" — exclude when part of spike-and-wave / spike-wave / polyspike compounds
    (re.compile(r"(?<!poly)(?<![- ])\bspikes?\b(?![- ]?(?:and[- ]?wave|wave))",
                re.IGNORECASE), "spike"),
]

_RE_NEG = re.compile(
    r"(?:^|\W)(?:no\s+|without\s+|absent\s+|not\s+identified|"
    r"none\s+(?:seen|noted|captured)|negative\s+for)\s*",
    re.IGNORECASE,
)

_RE_ICTAL_ONSET = re.compile(
    r"ictal\s+onset|seizure\s+onset\s+(?:in|at|localized to|from)|"
    r"onset\s+(?:localized\s+)?(?:in|to|at|from)\s+the",
    re.IGNORECASE,
)

_RE_SEIZURES_CAPTURED = re.compile(
    r"(\d+)\s+(?:electrographic\s+|clinical\s+)?seizures?\s+(?:were\s+)?(?:captured|recorded|observed)|"
    r"captured\s+(\d+)\s+seizures?",
    re.IGNORECASE,
)

_RE_SEIZURE_FREE_MENTION = re.compile(r"no\s+(?:electrographic\s+)?seizures?\s+(?:were\s+)?"
                                       r"(?:captured|recorded|observed)", re.IGNORECASE)

_RE_HZ = re.compile(r"(\d+(?:\.\d+)?)\s*Hz", re.IGNORECASE)

_LATERALITY_WORDS = {
    "left": "left", "right": "right", "bilateral": "bilateral",
    "midline": "midline", "diffuse": "diffuse", "generalized": "diffuse",
    "generalised": "diffuse",
}

_LOBAR_WORDS = {
    "frontal": "frontal", "temporal": "temporal", "parietal": "parietal",
    "occipital": "occipital", "insular": "insular", "cingulate": "cingulate",
    "multifocal": "multifocal",
    "hippocampal": "temporal", "mesial temporal": "temporal",
    "fronto-temporal": "frontal", "fronto temporal": "frontal",
    "centro-temporal": "temporal", "centro temporal": "temporal",
}


def _ev(value: Any, evidence_text: str, doc: DocumentMetadata,
        certainty: str = "probable", temporal: str = "current",
        char_start: int | None = None, char_end: int | None = None) -> dict[str, Any]:
    d = {
        "value": value.value if hasattr(value, "value") else value,
        "certainty": certainty,
        "temporal_status": temporal,
        "evidence_text": evidence_text,
        "source_doc_id": doc.doc_id,
        "source_doc_type": doc.doc_type.value,
        "source_date": doc.doc_date.isoformat(),
    }
    if char_start is not None and char_end is not None:
        d["char_start"] = char_start
        d["char_end"] = char_end
    return d


def _null(doc: DocumentMetadata) -> dict[str, Any]:
    return {
        "value": None, "certainty": "not_documented",
        "temporal_status": "unspecified", "evidence_text": None,
        "source_doc_id": doc.doc_id, "source_doc_type": doc.doc_type.value,
        "source_date": doc.doc_date.isoformat(),
    }


def _preceded_by_neg(text: str, span_start: int, back: int = 30) -> bool:
    lookback = text[max(0, span_start - back):span_start]
    return bool(_RE_NEG.search(lookback))


def _nearest_word(text: str, span_start: int, span_end: int,
                  word_map: dict[str, str], window: int = 80) -> Optional[str]:
    start = max(0, span_start - window)
    end = min(len(text), span_end + window)
    context = text[start:end].lower()
    hits: list[tuple[int, str]] = []
    for key in word_map:
        for m in re.finditer(r"\b" + re.escape(key) + r"\b", context):
            hits.append((abs(m.start() - (span_start - start)), word_map[key]))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


# ---------------------------------------------------------------------------
# Rules extractor
# ---------------------------------------------------------------------------


def extract_eeg(text: str, doc: DocumentMetadata) -> dict[str, Any]:
    """Produce a dict matching EegModule's JSON schema."""

    # Study type — highest-specificity match wins (patterns already ordered)
    study_type_ev = _null(doc)
    for pat, val in _RE_STUDY_TYPE:
        m = pat.search(text)
        if m:
            quote = text[max(0, m.start() - 5):min(len(text), m.end() + 5)].strip()
            study_type_ev = _ev(val, quote, doc,
                                char_start=m.start(), char_end=m.end())
            break

    # Background — highest-specificity match wins
    background_ev = _null(doc)
    for pat, val in _RE_BACKGROUND:
        m = pat.search(text)
        if m:
            quote = text[max(0, m.start() - 5):min(len(text), m.end() + 30)].strip()
            background_ev = _ev(val, quote, doc,
                                char_start=m.start(), char_end=m.end())
            break

    # IEDs — scan all types, dedupe by (ied_type, laterality, lobe)
    ied_findings: list[dict[str, Any]] = []
    ied_present_flag: Optional[bool] = None
    seen_ieds: set[tuple[str, Optional[str], Optional[str]]] = set()
    for pat, val in _RE_IED:
        for m in pat.finditer(text):
            negated = _preceded_by_neg(text, m.start())
            if negated:
                if ied_present_flag is None:
                    ied_present_flag = False
                continue
            ied_present_flag = True
            quote = text[max(0, m.start() - 5):min(len(text), m.end() + 30)].strip()
            lobe = _nearest_word(text, m.start(), m.end(), _LOBAR_WORDS)
            lat = _nearest_word(text, m.start(), m.end(), _LATERALITY_WORDS)
            # Optional Hz within a small window
            hz_val: Optional[float] = None
            hz_ctx = text[max(0, m.start() - 30):min(len(text), m.end() + 30)]
            hz_m = _RE_HZ.search(hz_ctx)
            if hz_m:
                try:
                    hz_val = float(hz_m.group(1))
                    if not (0.1 <= hz_val < 100):
                        hz_val = None
                except ValueError:
                    pass
            key = (val, lat, lobe)
            if key in seen_ieds:
                continue
            seen_ieds.add(key)
            ied = {"ied_type": val, "localization": lobe,
                   "laterality": lat, "dominant_frequency_hz": hz_val}
            ied_findings.append(_ev(ied, quote, doc,
                                    char_start=m.start(), char_end=m.end()))

    ied_present_ev = (
        _ev(True, "IED detected by rules", doc)
        if ied_present_flag is True
        else _ev(False, "no epileptiform discharges", doc, certainty="negated")
        if ied_present_flag is False
        else _null(doc)
    )

    # Seizures captured
    seizures_captured_ev = _null(doc)
    seizures_count_ev = _null(doc)
    m = _RE_SEIZURES_CAPTURED.search(text)
    if m:
        num = m.group(1) or m.group(2)
        quote = m.group(0)
        try:
            n = int(num)
            seizures_captured_ev = _ev(True, quote, doc,
                                       char_start=m.start(), char_end=m.end())
            seizures_count_ev = _ev(n, quote, doc,
                                    char_start=m.start(), char_end=m.end())
        except (TypeError, ValueError):
            pass
    elif _RE_SEIZURE_FREE_MENTION.search(text):
        mm = _RE_SEIZURE_FREE_MENTION.search(text)
        seizures_captured_ev = _ev(False, mm.group(0), doc,
                                   certainty="negated",
                                   char_start=mm.start(), char_end=mm.end())

    # Ictal onset
    onset_lobe_ev = _null(doc)
    onset_lat_ev = _null(doc)
    m = _RE_ICTAL_ONSET.search(text)
    if m:
        lobe = _nearest_word(text, m.start(), m.end(), _LOBAR_WORDS, window=120)
        lat = _nearest_word(text, m.start(), m.end(), _LATERALITY_WORDS, window=120)
        quote = text[max(0, m.start() - 10):min(len(text), m.end() + 60)].strip()
        if lobe:
            onset_lobe_ev = _ev(lobe, quote, doc,
                                char_start=m.start(), char_end=m.end())
        if lat:
            onset_lat_ev = _ev(lat, quote, doc,
                               char_start=m.start(), char_end=m.end())

    return {
        "study_type": study_type_ev,
        "background": background_ev,
        "ied_present": ied_present_ev,
        "ied_findings": ied_findings,
        "seizures_captured": seizures_captured_ev,
        "seizures_captured_count": seizures_count_ev,
        "ictal_onset_lobe": onset_lobe_ev,
        "ictal_onset_laterality": onset_lat_ev,
    }


# ---------------------------------------------------------------------------
# ModelBackend adapter — B0-EEG-through-pipeline
# ---------------------------------------------------------------------------


@dataclass
class RulesEegBackend:
    """Deterministic non-LLM 'backend' that emits rules-generated EEG JSON."""
    doc: DocumentMetadata
    model_name: str = "baseline/rules-eeg"
    model_cache_dir: str = ""

    def generate(self, prompt: str, decoding) -> tuple[str, Optional[int]]:
        import json
        source = getattr(self, "_current_source", None)
        if source is None:
            return json.dumps({}), 0
        return json.dumps(extract_eeg(source, self.doc)), None


def run_b0_eeg(source_text: str, doc: DocumentMetadata) -> dict[str, Any]:
    return extract_eeg(source_text, doc)
