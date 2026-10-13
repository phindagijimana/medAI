"""
eeg.py — EEG background + interictal-epileptiform-discharge extraction.

Fields populated
----------------
- ``eeg.background``   (Evidence[EegBackground])
- ``eeg.ied_present``  (Evidence[bool])
- ``eeg.ied_findings`` (list[Evidence[IedFinding]])

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``jape/investigations.jape``          — top-level composition
- ``jape/InvestigationsEEG.jape``       — EEG-specific patterns
- ``jape/NegatedFindingEEG.jape``       — "no epileptiform activity"
- ``jape/InvestigationBlock.jape``      — sentence-block scope
- ``jape/InvestigationWithin.jape``     — nested "with X and Y" findings
- ``jape/InvestigationsLookup.jape``    — gazetteer lookup
- ``jape/LocationAndFinding.jape``      — IED + laterality + lobe combo
- ``jape/Lateralisation.jape``          — laterality tokens
- ``resources/gazetteers/EEG_results.lst`` — background + IED vocabulary
- ``Groovy/Investigations.groovy``      — top-level serializer
- ``Groovy/MarkupInvestigations.groovy`` — span builder

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. Background — LinkedEntity with ``enum_class == "EegBackground"``; fallback
   regex over: normal PDR, diffuse slowing, focal slowing, asymmetric,
   burst-suppression, suppressed.
2. IEDs — LinkedEntity with ``enum_class == "IedType"``; fallback regex
   over spike, sharp wave, spike-and-wave, polyspike, 3-Hz spike-wave,
   generalised spike-wave.
3. Localisation of each IED: nearest lobar word ± 80 chars; laterality ± 80
   chars; dominant Hz within ± 30 chars. If no word gives the lobe or side,
   scalp electrode names in the same window do ("maximal at T8" → right
   temporal; ``rules/eeg_electrodes.py``). Frequency band, recurrence and
   dispersal come from the same window (``rules/eeg_attributes.py``).
4. ``ied_present``: True iff any positive IED detected; False iff an
   explicit negation ("no epileptiform discharges").
5. Sentence context: EEG-related keyword must appear in a nearby sentence
   (EEG, video-EEG, ambulatory EEG, background rhythm).
6. ConText — negated → skip IED; family → skip.
7. EEG reports (TUH-style headers): findings from description / impression
   only, not history or the introduction (``rules/eeg_sections.py``). Clinic
   letters have no those headers and are unchanged.

Cite: Fonferko-Shadrach et al. 2019; 2024. ACNS EEG terminology (Hirsch 2013).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from rules.eeg_attributes import ied_attributes
from rules.eeg_electrodes import electrode_location
from rules.eeg_sections import in_finding_section
from schema.enums import (
    Certainty,
    EegBackground,
    IedType,
    Laterality,
    LobarLocalization,
    TemporalStatus,
)
from schema.evidence import Evidence
from schema.ontology import IedFinding
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Vocab
# ---------------------------------------------------------------------------

_EEG_CONTEXT_RE = re.compile(
    r"\bEEG\b|electroencephalogr|video[- ]?EEG|ambulatory\s+EEG|"
    r"scalp\s+EEG|routine\s+EEG|prolonged\s+EEG|\bLTM\b|\bcEEG\b|"
    r"posterior\s+dominant\s+rhythm|background\s+rhythm|"
    r"epileptiform\s+discharg|interictal|periodic\s+discharges?",
    re.IGNORECASE,
)

_BACKGROUND_FALLBACK: list[tuple[re.Pattern[str], EegBackground]] = [
    (re.compile(r"burst[- ]?suppression", re.IGNORECASE),
     EegBackground.BURST_SUPPRESSION),
    (re.compile(r"(?:diffuse|generali[sz]ed)\s+slow(?:ing)?",
                re.IGNORECASE), EegBackground.DIFFUSE_SLOWING),
    (re.compile(r"focal\s+slow(?:ing)?", re.IGNORECASE),
     EegBackground.FOCAL_SLOWING),
    (re.compile(r"asymmetr(?:y|ic)", re.IGNORECASE), EegBackground.ASYMMETRIC),
    (re.compile(r"suppress(?:ed|ion)\s+background|electrocerebral\s+silence",
                re.IGNORECASE), EegBackground.SUPPRESSED),
    (re.compile(r"normal\s+(?:background|posterior\s+dominant\s+rhythm|"
                r"waking\s+background)|well[- ]?organi[sz]ed\s+(?:background|"
                r"posterior\s+dominant\s+rhythm)|"
                r"posterior\s+dominant\s+rhythm\s+at\s+\d+",
                re.IGNORECASE), EegBackground.NORMAL),
]

_IED_FALLBACK: list[tuple[re.Pattern[str], IedType]] = [
    (re.compile(r"3[- ]?Hz\s+spike[- ]and[- ]wave|3/s\s+spike[- ]?wave|"
                r"generali[sz]ed\s+3[- ]?Hz\s+spike[- ]?wave",
                re.IGNORECASE), IedType.GENERALIZED_SPIKE_WAVE_3HZ),
    (re.compile(r"polyspike[- ]and[- ]wave|polyspike[- ]?wave",
                re.IGNORECASE), IedType.POLYSPIKE_AND_WAVE),
    (re.compile(r"\bpolyspikes?\b", re.IGNORECASE), IedType.POLYSPIKE),
    (re.compile(r"spike[- ]and[- ]wave|spike[- ]?wave\s+complex(?:es)?|"
                r"generali[sz]ed\s+spike[- ]?wave",
                re.IGNORECASE), IedType.SPIKE_AND_WAVE),
    (re.compile(r"sharp[- ]and[- ]slow", re.IGNORECASE), IedType.SHARP_AND_SLOW),
    (re.compile(r"sharp\s+waves?", re.IGNORECASE), IedType.SHARP_WAVE),
    # ACNS 2012/2013 critical-care terms (Hirsch et al.): LPDs replace PLEDs;
    # schema has no LPD enum, so they count as an IED of type other.
    (re.compile(
        r"\bLPDs?\b|lateralized\s+periodic\s+discharges?|"
        r"\bPLEDs?\b|periodic\s+lateralized\s+epileptiform|"
        r"\bGPDs?\b|generalized\s+periodic\s+discharges?|"
        r"\bGPEDs?\b|BiPDs?|BIPLEDs?",
        re.IGNORECASE), IedType.OTHER),
    (re.compile(r"(?<!poly)(?<![- ])\bspikes?\b(?![- ]?(?:and[- ]?wave|wave))",
                re.IGNORECASE), IedType.SPIKE),
]

_NEG_RE = re.compile(
    r"(?:^|\W)(?:no\s+|without\s+|absent\s+|not\s+identified\s+|"
    r"none\s+(?:seen|noted|captured)\s+|negative\s+for\s+)",
    re.IGNORECASE,
)

_HZ_RE = re.compile(r"(\d+(?:\.\d+)?)\s*Hz", re.IGNORECASE)

_LATERALITY_MAP = {
    "left": Laterality.LEFT,
    "right": Laterality.RIGHT,
    "bilateral": Laterality.BILATERAL,
    "midline": Laterality.MIDLINE,
    "diffuse": Laterality.DIFFUSE,
    "generalized": Laterality.DIFFUSE,
    "generalised": Laterality.DIFFUSE,
}

_LOBE_MAP = {
    "frontal": LobarLocalization.FRONTAL,
    "temporal": LobarLocalization.TEMPORAL,
    "parietal": LobarLocalization.PARIETAL,
    "occipital": LobarLocalization.OCCIPITAL,
    "insular": LobarLocalization.INSULAR,
    "cingulate": LobarLocalization.CINGULATE,
    "multifocal": LobarLocalization.MULTIFOCAL,
    "hippocampal": LobarLocalization.TEMPORAL,
    "centro-temporal": LobarLocalization.TEMPORAL,
    "fronto-temporal": LobarLocalization.FRONTAL,
    "mesial temporal": LobarLocalization.TEMPORAL,
}


def _preceded_by_neg(text: str, start: int, back: int = 30) -> bool:
    return bool(_NEG_RE.search(text[max(0, start - back):start]))


_SENT_NEG_RE = re.compile(
    r"\b(?:no|without|absent|never|not|negative\s+for)\b", re.IGNORECASE)
_SENT_CONJ_RE = re.compile(r"\b(?:but|however|although|except)\b", re.IGNORECASE)


def _ied_sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    cuts = [text.rfind(c, 0, start) for c in (".", "\n", ";", "!")]
    left = max(cuts) + 1
    rights = [i for i in (text.find(c, end) for c in (".", "\n", ";", "!")) if i != -1]
    right = min(rights) if rights else len(text)
    return left, right


def _sentence_negates_ied(text: str, start: int, end: int) -> bool:
    """Skip IEDs under a same-sentence 'no … LPDs/spikes' list (Hirsch terms sit far from 'no')."""
    left, _right = _ied_sentence_span(text, start, end)
    pre = text[left:start]
    last = None
    for m in _SENT_NEG_RE.finditer(pre):
        last = m
    if last is None:
        return False
    if _SENT_CONJ_RE.search(pre[last.end():]):
        return False
    return True


def _nearest(text: str, start: int, end: int, word_map: dict, window: int = 80):
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    ctx = text[ctx_start:ctx_end].lower()
    hits: list[tuple[int, Any]] = []
    for key, value in word_map.items():
        for m in re.finditer(r"\b" + re.escape(key) + r"\b", ctx):
            hits.append((abs(m.start() - (start - ctx_start)), value))
    if not hits:
        return None
    hits.sort()
    return hits[0][1]


def _location(text: str, start: int, end: int, window: int = 80):
    """Side and lobe from location words; electrode names fill what the words leave empty.

    On a generalized discharge the electrodes give its predominance, not a focus, so they
    never add a lobe there ("generalized spike-and-wave, bifrontal at Fp1/Fp2").
    """
    lat = _nearest(text, start, end, _LATERALITY_MAP, window)
    lobe = _nearest(text, start, end, _LOBE_MAP, window)
    if lat is None or lobe is None:
        e_lat, e_lobe = electrode_location(text, start, end, window)
        lat = lat or e_lat
        if lat != Laterality.DIFFUSE:
            lobe = lobe or e_lobe
    return lat, lobe


def _eeg_context_present(sentence: str, doc_text: str) -> bool:
    if _EEG_CONTEXT_RE.search(sentence or ""):
        return True
    return bool(_EEG_CONTEXT_RE.search(doc_text[:400]))


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class EegBackgroundRule(BaseFieldRule):
    field_name = "eeg.background"
    enum_class = EegBackground

    def apply(self, entities, doc, meta):
        for e in self.relevant_entities(entities, include_hypothetical=True):
            try:
                value = EegBackground(e.enum_value)
            except ValueError:
                continue
            if not _eeg_context_present(e.sentence_text, getattr(doc, "text", "")):
                continue
            if not in_finding_section(getattr(doc, "text", "") or "", e.char_start, e.char_end):
                continue
            return self._make_evidence(value, e, meta)

        # Fallback regex.
        text = getattr(doc, "text", "") or ""
        for pat, value in _BACKGROUND_FALLBACK:
            m = pat.search(text)
            if not m:
                continue
            if not in_finding_section(text, m.start(), m.end()):
                continue
            window = text[max(0, m.start() - 200):min(len(text), m.end() + 200)]
            if not _EEG_CONTEXT_RE.search(window):
                continue
            if _preceded_by_neg(text, m.start()):
                continue
            return Evidence[EegBackground](
                value=value,
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )
        return None


def _collect_ieds(entities, doc):
    """Return list of (IedType, char_start, char_end, quote, lat, lobe, hz,
    is_hyp, is_hist). Deduplicates by (ied_type, lat, lobe)."""
    text = getattr(doc, "text", "") or ""
    out = []
    seen: set[tuple] = set()

    for e in entities:
        if e.enum_class != "IedType":
            continue
        if e.is_negated or e.is_family:
            continue
        if _sentence_negates_ied(text, e.char_start, e.char_end):
            continue
        if not in_finding_section(text, e.char_start, e.char_end):
            continue
        if not _eeg_context_present(e.sentence_text, text):
            continue
        try:
            ied_type = IedType(e.enum_value)
        except ValueError:
            continue
        lat, lobe = _location(text, e.char_start, e.char_end)
        hz = None
        hz_m = _HZ_RE.search(text[max(0, e.char_start - 30):e.char_end + 30])
        if hz_m:
            try:
                hz_val = float(hz_m.group(1))
                if 0.1 <= hz_val < 100:
                    hz = hz_val
            except ValueError:
                pass
        key = (ied_type,
               lat.value if lat else None,
               lobe.value if lobe else None)
        if key in seen:
            continue
        seen.add(key)
        quote = text[max(0, e.char_start - 5):min(len(text), e.char_end + 30)].strip()
        out.append((ied_type, e.char_start, e.char_end, quote,
                    lat, lobe, hz, e.is_hypothetical, e.is_historical))

    # Fallback regex sweep.
    for pat, ied_type in _IED_FALLBACK:
        for m in pat.finditer(text):
            if _preceded_by_neg(text, m.start()) or _sentence_negates_ied(text, m.start(), m.end()):
                continue
            if not in_finding_section(text, m.start(), m.end()):
                continue
            window = text[max(0, m.start() - 200):min(len(text), m.end() + 200)]
            if not _EEG_CONTEXT_RE.search(window):
                continue
            lat, lobe = _location(text, m.start(), m.end())
            hz = None
            hz_m = _HZ_RE.search(text[max(0, m.start() - 30):m.end() + 30])
            if hz_m:
                try:
                    hz_val = float(hz_m.group(1))
                    if 0.1 <= hz_val < 100:
                        hz = hz_val
                except ValueError:
                    pass
            key = (ied_type,
                   lat.value if lat else None,
                   lobe.value if lobe else None)
            if key in seen:
                continue
            seen.add(key)
            quote = text[max(0, m.start() - 5):min(len(text), m.end() + 30)].strip()
            out.append((ied_type, m.start(), m.end(), quote,
                        lat, lobe, hz, False, False))
    return out


class IedPresentRule(BaseFieldRule):
    field_name = "eeg.ied_present"

    def apply(self, entities, doc, meta):
        hits = _collect_ieds(entities, doc)
        text = getattr(doc, "text", "") or ""
        if hits:
            _t, cs, ce, quote, *_ = hits[0]
            return Evidence[bool](
                value=True,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=quote,
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=cs,
                char_end=ce,
            )
        # Explicit negation.
        m = re.search(
            r"no\s+(?:epileptiform\s+discharg(?:es)?|interictal\s+"
            r"epileptiform\s+activity|spikes?|sharp\s+waves?|"
            r"LPDs?|PLEDs?|GPDs?|GPEDs?|BiPDs?|BIPLEDs?)",
            text, re.IGNORECASE,
        )
        if m and in_finding_section(text, m.start(), m.end()) and _EEG_CONTEXT_RE.search(
                text[max(0, m.start() - 200):min(len(text), m.end() + 200)]):
            return Evidence[bool](
                value=False,
                certainty=Certainty.DEFINITE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )
        return None


class IedFindingsRule(BaseFieldRule):
    field_name = "eeg.ied_findings"

    def apply(self, entities, doc, meta):
        hits = _collect_ieds(entities, doc)
        if not hits:
            return None
        text = getattr(doc, "text", "") or ""
        out: list[Evidence] = []
        for ied_type, cs, ce, quote, lat, lobe, hz, is_hyp, is_hist in hits:
            band, rec, disp = ied_attributes(text, cs, ce, hz)
            finding = IedFinding(
                ied_type=ied_type,
                localization=lobe,
                laterality=lat,
                dominant_frequency_hz=hz,
                frequency_band=band,
                recurrence=rec,
                dispersal=disp,
            )
            certainty = Certainty.POSSIBLE if is_hyp else Certainty.DEFINITE
            temporal = (TemporalStatus.HISTORICAL if is_hist
                        else TemporalStatus.CURRENT)
            out.append(Evidence[IedFinding](
                value=finding,
                certainty=certainty,
                temporal_status=temporal,
                evidence_text=quote,
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=cs,
                char_end=ce,
            ))
        return out or None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(EegBackgroundRule())
register_rule(IedPresentRule())
register_rule(IedFindingsRule())

__all__ = ["EegBackgroundRule", "IedPresentRule", "IedFindingsRule"]
