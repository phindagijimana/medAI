"""B0 rules baseline — Clinical Seizure module (paper Table 6).

Regex/keyword extractor producing a valid `ClinicalSeizureModule` from
progress-note / clinic-letter prose. Runs without an LLM. Deliberately
narrow / precision-first — silver-labeled ExECT-v2 shows that the same
clinic-letter concepts we care about here are covered by regex + a small
canonical vocabulary.

Fields covered (silver-quality):
  - epilepsy_type (focal / generalized / unknown, via keyword patterns)
  - predominant_seizure_type (ILAE 2017 canonical types via keyword patterns)
  - awareness (aware / impaired / unknown)
  - age_at_onset_years (regex over "since age X" / "onset at X years")
  - seizure_frequency (Lower/Upper count + period from natural language)
  - status_epilepticus_history (bool + negation)
  - etiology_category (structural / genetic / infectious / immune / metabolic /
                       unknown — keyword classifier)
  - etiology_details_text (raw quote)
  - focal_motor_onset (ILAE 2017 motor subtypes via keyword)
  - focal_nonmotor_onset (ILAE 2017 non-motor subtypes via keyword)

Fields explicitly left as `not_documented`:
  - semiology_text (broad — better to leave than to guess)
  - other_seizure_types / other_seizure_frequencies (list-typed; needs
    more careful parsing to avoid double-counting the predominant)
  - etiology_specifics (structured slot — LLM better here)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from schema import DocumentMetadata


# ---------------------------------------------------------------------------
# Epilepsy type patterns
# ---------------------------------------------------------------------------

_EPILEPSY_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Combined focal + generalized (specific syndromes)
    (re.compile(r"Lennox[- ]Gastaut|combined focal and generalized",
                re.IGNORECASE), "combined_focal_generalized"),
    # Generalized
    (re.compile(r"generali[sz]ed epilepsy|generali[sz]ed idiopathic|"
                r"juvenile myoclonic epilepsy|\bJME\b|"
                r"childhood absence epilepsy|\bCAE\b|"
                r"epilepsy with generali[sz]ed tonic[- ]clonic seizures alone",
                re.IGNORECASE), "generalized"),
    # Focal
    (re.compile(r"focal epilepsy|localization[- ]related epilepsy|"
                r"temporal lobe epilepsy|\bTLE\b|frontal lobe epilepsy|\bFLE\b|"
                r"parietal lobe epilepsy|occipital lobe epilepsy|"
                r"symptomatic structural(?:\s+focal)?\s+epilepsy",
                re.IGNORECASE), "focal"),
    # Unknown / unclassified
    (re.compile(r"epilepsy of unknown (?:origin|etiology)|unclassified epilepsy",
                re.IGNORECASE), "unknown"),
]


# ---------------------------------------------------------------------------
# Seizure type patterns (ILAE 2017)
# ---------------------------------------------------------------------------

_SEIZURE_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"focal to bilateral tonic[- ]clonic|"
                r"secondary(?:ily)? generali[sz]ed(?:\s+tonic[- ]clonic)?|"
                r"FBTC", re.IGNORECASE), "focal_to_bilateral_tonic_clonic"),
    (re.compile(r"focal impaired[- ]awareness|"
                r"complex partial seizure|\bCPS\b", re.IGNORECASE),
     "focal_impaired_awareness"),
    (re.compile(r"focal aware seizure|simple partial seizure|\bSPS\b",
                re.IGNORECASE), "focal_aware"),
    (re.compile(r"typical absence|3[- ]Hz spike[- ]?wave.*absence",
                re.IGNORECASE), "generalized_absence_typical"),
    (re.compile(r"atypical absence", re.IGNORECASE), "generalized_absence_atypical"),
    (re.compile(r"generali[sz]ed tonic[- ]clonic seizure|\bGTCS\b|\bTCS\b",
                re.IGNORECASE), "generalized_tonic_clonic"),
    (re.compile(r"myoclonic seizure|myoclonus\b", re.IGNORECASE),
     "generalized_myoclonic"),
    (re.compile(r"atonic seizure|drop attack", re.IGNORECASE),
     "generalized_atonic"),
    (re.compile(r"epileptic spasm|infantile spasm", re.IGNORECASE),
     "generalized_epileptic_spasms"),
    (re.compile(r"tonic seizure(?!\s+clonic)", re.IGNORECASE),
     "generalized_tonic"),
    # Generic focal fallback if nothing more specific matched
    (re.compile(r"focal seizure", re.IGNORECASE), "focal_unknown_awareness"),
]


AWARENESS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"loss[ -]of[ -]awareness|impaired[ -]awareness|"
                r"impaired[ -]consciousness|"
                r"unresponsive|behavioural[ -]arrest|behavioral[ -]arrest|"
                r"complex[ -]partial", re.IGNORECASE), "impaired"),
    (re.compile(r"retained[ -]awareness|preserved[ -]awareness|aware[ -]seizure|"
                r"simple[ -]partial", re.IGNORECASE), "aware"),
]


# ---------------------------------------------------------------------------
# Focal motor / non-motor onset (ILAE 2017)
# ---------------------------------------------------------------------------

FOCAL_MOTOR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bautomatism", re.IGNORECASE), "automatisms"),
    (re.compile(r"hyperkinetic", re.IGNORECASE), "hyperkinetic"),
    (re.compile(r"myoclonic (?:jerk|movement|activity)", re.IGNORECASE), "myoclonic"),
    (re.compile(r"tonic (?:posturing|movement|stiffening)", re.IGNORECASE), "tonic"),
    (re.compile(r"clonic (?:jerk|movement)", re.IGNORECASE), "clonic"),
    (re.compile(r"atonic drop|atonic seizure", re.IGNORECASE), "atonic"),
    (re.compile(r"epileptic spasm", re.IGNORECASE), "epileptic_spasms"),
]

FOCAL_NONMOTOR_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"deja[- ]vu|jamais[- ]vu|fear aura|emotional aura",
                re.IGNORECASE), "emotional"),
    (re.compile(r"\baura\b|epigastric rising|olfactory hallucin|"
                r"gustatory hallucin", re.IGNORECASE), "sensory"),
    (re.compile(r"autonomic aura|palpitations?\s+during|piloerection",
                re.IGNORECASE), "autonomic"),
    (re.compile(r"cognitive aura|confusion(?:al)? episode|"
                r"forced thinking", re.IGNORECASE), "cognitive"),
    (re.compile(r"behavio[u]?r(?:al)? arrest|staring spell",
                re.IGNORECASE), "behavior_arrest"),
]


# ---------------------------------------------------------------------------
# Age at onset
# ---------------------------------------------------------------------------

AGE_AT_ONSET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:since|from|at)\s+(?:the\s+)?age\s+(?:of\s+)?(\d+)(?:\s*(?:years?|yrs?))?",
               re.IGNORECASE),
    re.compile(r"seizure(?:s)?\s+(?:started|began|first occurred)\s+(?:at|in)\s+"
               r"(?:the\s+age\s+of\s+)?(\d+)(?:\s*years?)?", re.IGNORECASE),
    re.compile(r"onset\s+(?:at|of)\s+(\d+)\s*(?:years?|months?)", re.IGNORECASE),
    re.compile(r"age of onset\s+(?:was\s+)?(\d+)", re.IGNORECASE),
    re.compile(r"first seizure\s+at\s+(\d+)\s*(?:years?)?", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Seizure frequency
# ---------------------------------------------------------------------------

FREQUENCY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(\d+)\s*[-–]\s*(\d+)\s+(?:seizures?)?\s*(?:per|a|/)\s+"
                r"(day|week|month|year)", re.IGNORECASE), "range"),
    (re.compile(r"(\d+)\s+(?:seizures?)?\s*(?:per|a|/)\s+"
                r"(day|week|month|year)", re.IGNORECASE), "single"),
    (re.compile(r"once\s+(?:a|per)\s+(day|week|month|year)", re.IGNORECASE), "once"),
    (re.compile(r"twice\s+(?:a|per)\s+(day|week|month|year)", re.IGNORECASE), "twice"),
    (re.compile(r"(daily|weekly|monthly|yearly)\s+seizures?", re.IGNORECASE), "adjective"),
    (re.compile(r"seizure[- ]free|no seizures for", re.IGNORECASE), "free"),
]


# ---------------------------------------------------------------------------
# Status epilepticus + Etiology
# ---------------------------------------------------------------------------

STATUS_EPI_RE = re.compile(
    r"(?<!no\s)(?<!no\s\s)status epilepticus|convulsive status", re.IGNORECASE,
)
NO_STATUS_EPI_RE = re.compile(
    r"no (?:history of )?status epilepticus", re.IGNORECASE,
)


ETIOLOGY_KEYWORDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"traumatic brain injury|\bTBI\b|head injury|skull fracture|"
                r"post[- ]traumatic|subarachnoid haemorrhage|SAH\b",
                re.IGNORECASE), "structural"),
    (re.compile(r"stroke|infarct|cerebrovascular|vascular malformation|cavernoma",
                re.IGNORECASE), "structural"),
    (re.compile(r"hippocampal sclerosis|mesial temporal sclerosis|\bHS\b|\bMTS\b|"
                r"focal cortical dysplasia|\bFCD\b|MOGHE|polymicrogyria|"
                r"heterotopia|tuberous sclerosis|encephalomalacia",
                re.IGNORECASE), "structural"),
    (re.compile(r"perinatal insult|birth (?:trauma|asphyxia|injury)|"
                r"hypoxic[- ]ischemic", re.IGNORECASE), "structural"),
    (re.compile(r"tumo(?:u)?r|glioma|meningioma|neoplasm", re.IGNORECASE), "structural"),
    (re.compile(r"gene mutation|genetic epilepsy|hereditary|"
                r"SCN1A|SCN2A|KCNQ2|CDKL5|DEPDC5|STXBP1|ARHGAP\d+|ARGHAP",
                re.IGNORECASE), "genetic"),
    (re.compile(r"autoimmune|antibody|paraneoplastic|encephalitis|NMDAR|"
                r"LGI1|CASPR2|GAD65|SOX1", re.IGNORECASE), "immune"),
    (re.compile(r"neurocysticercosis|meningitis|viral encephalit|HSV|"
                r"herpes simplex", re.IGNORECASE), "infectious"),
    (re.compile(r"metabolic|mitochondrial|pyridoxine[- ]dependent|"
                r"glucose transporter|GLUT1|amino acid disorder",
                re.IGNORECASE), "metabolic"),
]


TIME_PERIOD_MAP = {
    "day": "day", "week": "week", "month": "month", "year": "year",
    "daily": "day", "weekly": "week", "monthly": "month", "yearly": "year",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _match_first(text: str, patterns) -> tuple[Optional[str], Optional[re.Match]]:
    for pat, val in patterns:
        m = pat.search(text)
        if m:
            return val, m
    return None, None


def extract_clinical_seizure(text: str, doc: DocumentMetadata) -> dict[str, Any]:
    """Produce a dict matching ClinicalSeizureModule's JSON schema."""

    # Epilepsy type
    epi_type = _null(doc)
    val, m = _match_first(text, _EPILEPSY_TYPE_PATTERNS)
    if val:
        epi_type = _ev(val, m.group(0), doc, char_start=m.start(), char_end=m.end())

    # Predominant seizure type
    seizure_type = _null(doc)
    val, m = _match_first(text, _SEIZURE_TYPE_PATTERNS)
    if val:
        seizure_type = _ev(val, m.group(0), doc, char_start=m.start(), char_end=m.end())

    # Awareness
    awareness = _null(doc)
    val, m = _match_first(text, AWARENESS_PATTERNS)
    if val:
        awareness = _ev(val, m.group(0), doc, char_start=m.start(), char_end=m.end())

    # Age at onset
    age_at_onset = _null(doc)
    for pat in AGE_AT_ONSET_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                yrs = float(m.group(1))
                if 0 <= yrs <= 100:
                    age_at_onset = _ev(yrs, m.group(0), doc,
                                       char_start=m.start(), char_end=m.end())
                    break
            except (ValueError, IndexError):
                pass

    # Seizure frequency
    seizure_frequency = _null(doc)
    for pat, kind in FREQUENCY_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        raw = m.group(0)
        if kind == "free":
            freq_obj = {"raw_text": raw, "period": "unspecified",
                        "count_min": None, "count_max": None,
                        "seizure_free": True, "duration_text": None,
                        "applies_to_type": None}
        elif kind == "range":
            freq_obj = {"raw_text": raw, "period": TIME_PERIOD_MAP.get(m.group(3).lower(), "unspecified"),
                        "count_min": float(m.group(1)), "count_max": float(m.group(2)),
                        "seizure_free": False, "duration_text": None, "applies_to_type": None}
        elif kind == "single":
            freq_obj = {"raw_text": raw, "period": TIME_PERIOD_MAP.get(m.group(2).lower(), "unspecified"),
                        "count_min": float(m.group(1)), "count_max": float(m.group(1)),
                        "seizure_free": False, "duration_text": None, "applies_to_type": None}
        elif kind in ("once", "twice"):
            count = 1.0 if kind == "once" else 2.0
            freq_obj = {"raw_text": raw, "period": TIME_PERIOD_MAP.get(m.group(1).lower(), "unspecified"),
                        "count_min": count, "count_max": count,
                        "seizure_free": False, "duration_text": None, "applies_to_type": None}
        elif kind == "adjective":
            freq_obj = {"raw_text": raw, "period": TIME_PERIOD_MAP.get(m.group(1).lower(), "unspecified"),
                        "count_min": None, "count_max": None,
                        "seizure_free": False, "duration_text": None, "applies_to_type": None}
        else:
            continue
        seizure_frequency = _ev(freq_obj, raw, doc,
                                char_start=m.start(), char_end=m.end())
        break

    # Status epilepticus
    status_epi = _null(doc)
    m = NO_STATUS_EPI_RE.search(text)
    if m:
        status_epi = _ev(False, m.group(0), doc, certainty="negated",
                         char_start=m.start(), char_end=m.end())
    else:
        m = STATUS_EPI_RE.search(text)
        if m:
            status_epi = _ev(True, m.group(0), doc,
                             char_start=m.start(), char_end=m.end())

    # Etiology
    etiology_cat = _null(doc)
    etiology_details = _null(doc)
    val, m = _match_first(text, ETIOLOGY_KEYWORDS)
    if val:
        span = text[max(0, m.start() - 5):min(len(text), m.end() + 30)].strip()
        etiology_cat = _ev(val, span, doc, char_start=m.start(), char_end=m.end())
        etiology_details = _ev(m.group(0), span, doc,
                               char_start=m.start(), char_end=m.end())

    # Focal motor / non-motor onset
    focal_motor = _null(doc)
    val, m = _match_first(text, FOCAL_MOTOR_PATTERNS)
    if val:
        focal_motor = _ev(val, m.group(0), doc,
                          char_start=m.start(), char_end=m.end())

    focal_nonmotor = _null(doc)
    val, m = _match_first(text, FOCAL_NONMOTOR_PATTERNS)
    if val:
        focal_nonmotor = _ev(val, m.group(0), doc,
                             char_start=m.start(), char_end=m.end())

    return {
        "epilepsy_type": epi_type,
        "predominant_seizure_type": seizure_type,
        "other_seizure_types": [],
        "awareness": awareness,
        "semiology_text": _null(doc),          # deliberately left as not_documented
        "age_at_onset_years": age_at_onset,
        "seizure_frequency": seizure_frequency,
        "other_seizure_frequencies": [],
        "status_epilepticus_history": status_epi,
        "etiology_category": etiology_cat,
        "etiology_details_text": etiology_details,
        "etiology_specifics": _null(doc),
        "focal_motor_onset": focal_motor,
        "focal_nonmotor_onset": focal_nonmotor,
    }


@dataclass
class RulesClinicalSeizureBackend:
    doc: DocumentMetadata
    model_name: str = "baseline/rules-clinical-seizure"
    model_cache_dir: str = ""

    def generate(self, prompt: str, decoding) -> tuple[str, Optional[int]]:
        import json
        source = getattr(self, "_current_source", None)
        if source is None:
            return json.dumps({}), 0
        return json.dumps(extract_clinical_seizure(source, self.doc)), None


def run_b0_clinical_seizure(source_text: str, doc: DocumentMetadata) -> dict[str, Any]:
    return extract_clinical_seizure(source_text, doc)
