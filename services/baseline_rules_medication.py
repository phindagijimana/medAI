"""B0 rules baseline — Medication + surgery + drug-resistance (paper Table 6).

Regex extractor producing a valid `MedicationModule`. Runs without an LLM.
Draws from the ~30 most common anti-seizure medications and detects:

- current_asms / prior_asms / failed_asms (via dose + status heuristic)
- drug_resistance_status (ILAE 2010 keyword — "drug-resistant", "refractory")
- surgery_history (resection, laser ablation, VNS, RNS, DBS)
- non_drug_therapies (ketogenic diet, IVIG, plasmapheresis, steroids)

Status inference uses the same ±100-char keyword heuristic as
`scripts/silver_label_fonferko.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from schema import DocumentMetadata


# ---------------------------------------------------------------------------
# ASM vocabulary — canonical generic names + spelling variants
# ---------------------------------------------------------------------------

ASM_CANONICAL: dict[str, list[str]] = {
    "levetiracetam": ["levetiracetam", "keppra"],
    "lamotrigine": ["lamotrigine", "lamictal"],
    "valproate": ["valproate", "valproic acid", "sodium valproate", "depakote", "epilim"],
    "carbamazepine": ["carbamazepine", "tegretol"],
    "oxcarbazepine": ["oxcarbazepine", "trileptal"],
    "phenytoin": ["phenytoin", "dilantin"],
    "phenobarbital": ["phenobarbital", "phenobarbitone", "luminal"],
    "topiramate": ["topiramate", "topamax"],
    "zonisamide": ["zonisamide", "zonegran"],
    "lacosamide": ["lacosamide", "vimpat"],
    "perampanel": ["perampanel", "fycompa"],
    "brivaracetam": ["brivaracetam", "brivetiracetam", "briviact"],
    "clobazam": ["clobazam", "onfi", "frisium"],
    "clonazepam": ["clonazepam", "klonopin", "rivotril"],
    "midazolam": ["midazolam", "buccolam"],
    "diazepam": ["diazepam", "valium"],
    "lorazepam": ["lorazepam", "ativan"],
    "gabapentin": ["gabapentin", "neurontin"],
    "pregabalin": ["pregabalin", "lyrica"],
    "vigabatrin": ["vigabatrin", "sabril"],
    "ethosuximide": ["ethosuximide", "zarontin"],
    "eslicarbazepine": ["eslicarbazepine", "aptiom", "zebinix"],
    "rufinamide": ["rufinamide", "inovelon", "banzel"],
    "stiripentol": ["stiripentol", "diacomit"],
    "cenobamate": ["cenobamate", "xcopri"],
    "cannabidiol": ["cannabidiol", "epidiolex", "cbd"],
    "primidone": ["primidone", "mysoline"],
    "acetazolamide": ["acetazolamide", "diamox"],
    "tiagabine": ["tiagabine", "gabitril"],
    "felbamate": ["felbamate", "felbatol"],
}

# Reverse index: alias → canonical
ASM_LOOKUP: dict[str, str] = {}
for canon, aliases in ASM_CANONICAL.items():
    for a in aliases:
        ASM_LOOKUP[a.lower()] = canon


# One regex that finds any known ASM alias (word-boundary safe)
_ASM_RE = re.compile(
    r"\b(" + "|".join(sorted(map(re.escape, ASM_LOOKUP.keys()),
                              key=lambda s: -len(s))) + r")\b",
    re.IGNORECASE,
)

# Dose regex — captures "1500 mg BID", "200 mg twice a day", "1g QDS", etc.
_DOSE_RE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:mg|g|mcg|units?))"
    r"(?:\s*(?:once|twice|thrice|three\s+times|four\s+times|daily|"
    r"bd|bid|tid|qds|qid|qod|prn|nocte|mane|od|BD|BID|TID|QDS|QID))?",
    re.IGNORECASE,
)


STATUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(rash|adverse|side[- ]effect|reaction|allergic|allergy|not tolerated)\b",
                re.IGNORECASE), "discontinued_adverse_effect"),
    (re.compile(r"\b(failed|did not respond|inadequate control|ineffective|"
                r"discontinued|stopped|withdrawn|weaned off|tapered off|"
                r"trialled but ineffective)\b", re.IGNORECASE), "failed"),
    (re.compile(r"\b(previous|prior|past|previously tried|used to take|was on|has been on)\b",
                re.IGNORECASE), "prior"),
]


DRUG_RESISTANCE_RE = re.compile(
    r"drug[- ]resistant epilepsy|refractory epilepsy|"
    r"medically[- ]refractory|pharmaco[- ]?resistant|"
    r"failed (?:two|2|three|3) (?:tolerated )?(?:appropriately[- ]chosen )?"
    r"(?:anti-?seizure|anti-?epileptic|ASM|AED)",
    re.IGNORECASE,
)


# Surgery detection
SURGERY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"vagus nerve stimulation|\bVNS\b\s*(?:implant|insertion|placement)?",
                re.IGNORECASE), "neurostimulation_vns"),
    (re.compile(r"responsive neurostimulation|\bRNS\b\s*(?:implant|system)?",
                re.IGNORECASE), "neurostimulation_rns"),
    (re.compile(r"deep brain stimulation|\bDBS\b", re.IGNORECASE), "neurostimulation_dbs"),
    (re.compile(r"laser (?:interstitial )?thermal ablation|\bLITT\b",
                re.IGNORECASE), "laser_ablation"),
    (re.compile(r"hemispherectomy|hemispherotomy", re.IGNORECASE), "hemispherectomy"),
    (re.compile(r"corpus callosotomy|callosotomy", re.IGNORECASE), "callosotomy"),
    (re.compile(r"(?:anterior )?temporal lobectomy|temporal lobe resection|"
                r"selective amygdalohippocampectomy|SAH\b",
                re.IGNORECASE), "resection"),
    (re.compile(r"(?:tailored )?resection|corticectomy", re.IGNORECASE), "resection"),
    (re.compile(r"disconnection", re.IGNORECASE), "disconnection"),
]


NON_DRUG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ketogenic diet", re.IGNORECASE), "ketogenic_diet"),
    (re.compile(r"modified Atkins", re.IGNORECASE), "modified_atkins"),
    (re.compile(r"low[- ]glycemic index", re.IGNORECASE), "low_glycemic_index"),
    (re.compile(r"\bIVIG\b|intravenous immunoglobulin", re.IGNORECASE), "ivig"),
    (re.compile(r"plasmapheresis|plasma exchange", re.IGNORECASE), "plasmapheresis"),
    (re.compile(r"corticosteroid|methylprednisolone|prednisolone|prednisone",
                re.IGNORECASE), "steroids"),
    (re.compile(r"\brituximab\b", re.IGNORECASE), "rituximab"),
    (re.compile(r"\bACTH\b|adrenocorticotropic hormone", re.IGNORECASE), "acth"),
]


LATERALITY_RE = re.compile(r"\b(left|right|bilateral)\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


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


_SENT_END = re.compile(r"[.!?;\n]")


def _infer_status(text: str, start: int, end: int) -> str:
    """Status inference within the CURRENT sentence only.

    Clinic-letter status keywords ("Currently on", "Previously tried",
    "Failed") normally appear in the SAME sentence as the drug. Scoping to
    the sentence prevents contamination from the next sentence's status
    keyword. Sentence boundaries: . ! ? ; or newline.
    """
    # Sentence start: last sentence-terminator before `start`
    sent_start = 0
    for m in _SENT_END.finditer(text[:start]):
        sent_start = m.end()
    # Sentence end: first terminator at or after `end`
    m = _SENT_END.search(text, end)
    sent_end = m.start() if m else len(text)
    ctx = text[sent_start:sent_end]

    for pat, status in STATUS_PATTERNS:
        if pat.search(ctx):
            return status
    return "current"


def _nearest_dose(text: str, start: int, end: int, window: int = 50) -> Optional[str]:
    ctx_start = max(0, start - 20)
    ctx_end = min(len(text), end + window)
    ctx = text[ctx_start:ctx_end]
    m = _DOSE_RE.search(ctx)
    return m.group(0).strip() if m else None


def _nearest_year(text: str, start: int, end: int, window: int = 40) -> Optional[int]:
    ctx = text[max(0, start - window):min(len(text), end + window)]
    m = YEAR_RE.search(ctx)
    if m:
        try:
            y = int(m.group(0))
            if 1900 < y <= 2100:
                return y
        except ValueError:
            pass
    return None


def _nearest_laterality(text: str, start: int, end: int, window: int = 60) -> Optional[str]:
    ctx = text[max(0, start - window):min(len(text), end + window)]
    m = LATERALITY_RE.search(ctx)
    return m.group(0).lower() if m else None


def extract_medication(text: str, doc: DocumentMetadata) -> dict[str, Any]:
    """Produce a dict matching MedicationModule's JSON schema."""
    current_asms: list[dict[str, Any]] = []
    prior_asms: list[dict[str, Any]] = []
    failed_asms: list[dict[str, Any]] = []

    seen_asms: set[tuple[str, str]] = set()   # (canonical_name, status)
    for m in _ASM_RE.finditer(text):
        alias = m.group(1).lower()
        canon = ASM_LOOKUP.get(alias, alias)
        status = _infer_status(text, m.start(), m.end())
        key = (canon, status)
        if key in seen_asms:
            continue
        seen_asms.add(key)
        dose_text = _nearest_dose(text, m.start(), m.end())
        med = {
            "generic_name": canon,
            "status": status,
            "dose_text": dose_text,
            "reason_discontinued": None,
            "rxnorm_cui": None,
        }
        span = text[m.start():min(len(text), m.end() + 20)].strip()
        temporal = "current" if status == "current" else "historical"
        ev = _ev(med, span, doc, temporal=temporal, char_start=m.start(), char_end=m.end())
        if status == "current":
            current_asms.append(ev)
        elif status == "prior":
            prior_asms.append(ev)
        else:
            failed_asms.append(ev)

    # Drug resistance
    drug_res_ev = _null(doc)
    m = DRUG_RESISTANCE_RE.search(text)
    if m:
        drug_res_ev = _ev("drug_resistant", m.group(0), doc, certainty="definite",
                          char_start=m.start(), char_end=m.end())

    # Surgery history
    surgery_history: list[dict[str, Any]] = []
    seen_surgery: set[str] = set()
    for pat, val in SURGERY_PATTERNS:
        for m in pat.finditer(text):
            key = val + "|" + m.group(0).lower()
            if key in seen_surgery:
                continue
            seen_surgery.add(key)
            surgery = {
                "surgery_type": val,
                "target": None,
                "laterality": _nearest_laterality(text, m.start(), m.end()),
                "year": _nearest_year(text, m.start(), m.end()),
                "outcome_text": None,
                "engel_class": None,
                "ilae_outcome": None,
                "device_model_text": None,
                "stimulation_parameters_text": None,
                "pathology_notes_text": None,
            }
            span = text[max(0, m.start() - 5):min(len(text), m.end() + 30)].strip()
            surgery_history.append(_ev(surgery, span, doc, temporal="historical",
                                       char_start=m.start(), char_end=m.end()))

    # Non-drug therapies
    non_drug: list[dict[str, Any]] = []
    for pat, val in NON_DRUG_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        status = _infer_status(text, m.start(), m.end())
        ndt = {"therapy_type": val, "status": status, "response_text": None}
        temporal = "current" if status == "current" else "historical"
        non_drug.append(_ev(ndt, m.group(0), doc, temporal=temporal,
                            char_start=m.start(), char_end=m.end()))

    return {
        "current_asms": current_asms,
        "prior_asms": prior_asms,
        "failed_asms": failed_asms,
        "adverse_effects_text": _null(doc),
        "drug_resistance_status": drug_res_ev,
        "surgery_history": surgery_history,
        "non_drug_therapies": non_drug,
    }


@dataclass
class RulesMedicationBackend:
    doc: DocumentMetadata
    model_name: str = "baseline/rules-medication"
    model_cache_dir: str = ""

    def generate(self, prompt: str, decoding) -> tuple[str, Optional[int]]:
        import json
        source = getattr(self, "_current_source", None)
        if source is None:
            return json.dumps({}), 0
        return json.dumps(extract_medication(source, self.doc)), None


def run_b0_medication(source_text: str, doc: DocumentMetadata) -> dict[str, Any]:
    return extract_medication(source_text, doc)
