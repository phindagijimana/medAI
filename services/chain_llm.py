"""LEO Reason-B: the LLM channel and the specialist/LLM fusion rule.

LEO = LLM + EpExtra + Ontology.  `services.chain_pipeline` already runs the
EpExtra specialist and the ontology candidate service.  This module adds
the missing third corner: **Med42-8B**, treated as an *interpreter, not an
authority* (Chain-of-Three compendium, p. 6-7).

Two ways to obtain an LLM phenotype for a note, both returning the same
shape (an ``EpilepsyPhenotype.model_dump`` dict):

* :class:`LiveLLMReasoner`      runs base Med42-8B now (needs GPU + a loaded
  ``Med42Backend``), one prompt per applicable module, via
  ``services.router.extract_phenotype``.
* :class:`FTLiveReasoner`       runs a LoRA-tuned Med42-8B in its training
  contract (one full-phenotype generation); see ``services.ft_extract``.
* :class:`ManifestLLMReasoner`  re-reads Med42 outputs already on disk
  (``data/run_manifests_*``).  This makes the fusion rule evaluable
  against every existing arm (base M0-M3, tuned Arm H, ...) with no GPU,
  and guarantees that the arm numbers and the LEO numbers come from the
  same model outputs.

Fusion rule (pure function :func:`fuse`, no I/O, unit-tested):

==========================  ===============================================
specialist vs LLM           outcome
==========================  ===============================================
both, values agree          ``detectors=[epextra, llm]``; may auto-accept
both, scalar disagree       specialist value kept, ``source_disagreement``,
                            LLM value stored in ``Claim.alternative``;
                            routed to REVIEW
specialist only             unchanged (specialist alone can accept)
LLM only                    new claim, ``detectors=[llm]``, ``llm_only``;
                            REVIEW if its quote is verbatim in the note,
                            REJECT (``offsets_unresolved``) if not
==========================  ===============================================

The LLM can therefore never introduce an accepted fact on its own, and an
LLM claim whose quote is not in the note is counted as an unsupported
claim rather than silently dropped.  That count is a reported metric.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

logger = logging.getLogger(__name__)

LLM_DETECTOR = "llm"

# Values that carry no information; an LLM "unspecified" must not be treated
# as a dissenting value.
_NULLISH = {"", "unknown", "unspecified", "unclassified", "not_documented",
            "not documented", "unclear", "n/a", "na"}
# Fields where "unknown" is a real answer (schema.enums.UNKNOWN_EPILEPSY_TYPE_DEFINITION), not an empty one.
_UNKNOWN_IS_VALUE = frozenset({"clinical_seizure.epilepsy_type"})
# Paths where a lone "unknown" is abstention, not a research-extract fact (silent + unknown → REVIEW).
UNKNOWN_SILENT_PATHS = frozenset({
    "clinical_seizure.epilepsy_type",
    "clinical_seizure.seizure_onset_class",
})


def is_unknown_value(field_path: str, value: Any) -> bool:
    """True when the asserted value is the schema 'unknown' / unknown-onset abstention."""
    if not isinstance(value, str):
        return False
    n = _norm_str(value)
    if field_path == "clinical_seizure.epilepsy_type":
        return n == "unknown"
    if field_path == "clinical_seizure.seizure_onset_class":
        return n in ("unknown", "unknown_onset")
    return False

# Numeric fields (ages, counts) agree within this absolute tolerance.  It is
# the same tolerance the field scorers use (``tol1``), so "agree" here means
# what "correct" means in the evaluation.
NUMERIC_TOLERANCE = 1.0

# Keys that identify an item inside a structured Evidence value.
_IDENTITY_KEYS = ("generic_name", "procedure", "therapy", "name", "type",
                  "finding", "diagnosis", "surgery_type")

# List fields where one LLM item may corroborate several specialist items.  The rules emit one interictal-discharge
# finding per (discharge type, side, lobe); the model reads one entry per site, so the same entry vouches for every
# specialist finding at that site.
REUSABLE_LLM_PATHS = frozenset({"eeg.ied_findings"})

_WS = re.compile(r"\s+")


# ─── Flattening an EpilepsyPhenotype dict into comparable items ──────────

@dataclass
class FieldItem:
    """One populated Evidence[T] of a phenotype, addressed by field path."""
    field_path: str          # "clinical_seizure.epilepsy_type"
    module: str              # "clinical_seizure"
    ev: dict                 # the Evidence dict (value, evidence_text, ...)
    multi: bool              # True when the field is a list of Evidence


def flatten(pheno: Optional[dict]) -> list[FieldItem]:
    """Every Evidence with a non-null value, in document-schema order."""
    out: list[FieldItem] = []
    for mod_name, module in (pheno or {}).items():
        if not isinstance(module, dict) or mod_name in ("document", "schema_version"):
            continue
        for fld, val in module.items():
            path = f"{mod_name}.{fld}"
            if isinstance(val, dict) and "value" in val:
                if val.get("value") is not None:
                    out.append(FieldItem(path, mod_name, val, False))
            elif isinstance(val, list):
                for ev in val:
                    if isinstance(ev, dict) and "value" in ev and ev.get("value") is not None:
                        out.append(FieldItem(path, mod_name, ev, True))
    return out


def _canon_drug(name: str) -> str:
    try:
        from rules.fields.medication import canonicalize_drug_name
        return canonicalize_drug_name(name)
    except Exception:
        return re.sub(r"[\s\-_]+", "", (name or "").strip().lower())


def _norm_str(v: Any) -> str:
    return _WS.sub(" ", str(v)).strip().lower()


def is_nullish(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return _norm_str(value) in _NULLISH
    return False


def display_value(value: Any) -> str:
    """Short, stable text form of an Evidence value for reviewers/logs."""
    if isinstance(value, dict):
        for k in _IDENTITY_KEYS:
            if value.get(k):
                return str(value[k])
        parts = [f"{k}={v}" for k, v in value.items() if v not in (None, "", [])]
        return ", ".join(parts)[:200]
    return str(value)


def values_agree(a: Any, b: Any) -> bool:
    """Do two Evidence values denote the same fact?

    * enums / strings: case- and whitespace-insensitive equality;
    * numbers: within :data:`NUMERIC_TOLERANCE`;
    * drug dicts: same canonical generic name;
    * seizure-frequency dicts: same period and counts within tolerance
      (unspecified period is ignored on either side);
    * other dicts: same identity key, else equal after dropping nulls.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= NUMERIC_TOLERANCE
    if isinstance(a, dict) and isinstance(b, dict):
        if a.get("generic_name") or b.get("generic_name"):
            return _canon_drug(a.get("generic_name") or "") == _canon_drug(b.get("generic_name") or "")
        if "period" in a or "period" in b or "count_min" in a or "count_min" in b:
            return _freq_agree(a, b)
        if "ied_type" in a or "ied_type" in b:
            return _ied_agree(a, b)
        for k in _IDENTITY_KEYS:
            if a.get(k) and b.get(k):
                return _norm_str(a[k]) == _norm_str(b[k])
        strip = lambda d: {k: v for k, v in d.items() if v not in (None, "", [])}
        return json.dumps(strip(a), sort_keys=True, default=str).lower() == \
            json.dumps(strip(b), sort_keys=True, default=str).lower()
    return _norm_str(a) == _norm_str(b)


def _freq_period(d: dict) -> Optional[str]:
    p = d.get("period")
    if p is None:
        return None
    p = _norm_str(p)
    return None if p in ("unspecified", "") else p


def freq_counts(d: dict) -> tuple[Optional[float], Optional[float]]:
    """(count_min, count_max) of a seizure-frequency value; "seizure-free" with no counts is 0."""
    lo, hi = d.get("count_min"), d.get("count_max")
    if d.get("seizure_free") is True and lo is None and hi is None:
        return 0.0, 0.0
    return lo, hi


def is_empty_frequency(value: Any) -> bool:
    """A seizure-frequency value that asserts nothing: no counts, no period, not seizure-free.

    The specialist emits one when a note mentions active seizures without a frequency.  It has
    no text span and no content, so it must neither be reported as a claim nor "agree" with an
    LLM value (agreement on nothing is not agreement).
    """
    if not isinstance(value, dict):
        return False
    lo, hi = freq_counts(value)
    return lo is None and hi is None and _freq_period(value) is None


def _ied_agree(a: dict, b: dict) -> bool:
    """Same interictal-discharge site: lobe and side must match wherever both sides state one, and at least one
    of them must be stated by both.  The discharge type is not compared (the model reader does not read it)."""
    compared = 0
    for k in ("localization", "laterality"):
        va, vb = a.get(k), b.get(k)
        if va in (None, "", "unknown") or vb in (None, "", "unknown"):
            continue
        if _norm_str(va) != _norm_str(vb):
            return False
        compared += 1
    return compared > 0


def _freq_agree(a: dict, b: dict) -> bool:
    """Same frequency: every field both sides state must match, and at least one must be stated
    by both (two empty values do not agree)."""
    compared = 0
    pa, pb = _freq_period(a), _freq_period(b)
    if pa is not None and pb is not None:
        if pa != pb:
            return False
        compared += 1
    (amin, amax), (bmin, bmax) = freq_counts(a), freq_counts(b)
    for va, vb in ((amin, bmin), (amax, bmax)):
        if va is not None and vb is not None:
            if abs(float(va) - float(vb)) > NUMERIC_TOLERANCE:
                return False
            compared += 1
    fa, fb = a.get("seizure_free"), b.get("seizure_free")
    if fa is not None and fb is not None and bool(fa) != bool(fb):
        return False
    return compared > 0


# ─── Fusion ──────────────────────────────────────────────────────────────

@dataclass
class FusedSpecialist:
    item: FieldItem
    status: str                      # "agree" | "disagree" | "specialist_only"
    alternative: Optional[str] = None
    llm_item: Optional[FieldItem] = None


@dataclass
class Fusion:
    specialist: list[FusedSpecialist]
    llm_only: list[FieldItem]


def fuse(specialist: Iterable[FieldItem], llm: Iterable[FieldItem]) -> Fusion:
    """Align specialist items with LLM items field by field.

    Scalar fields: one value each; equal → agree, different → disagree
    (the specialist value is kept; the LLM value becomes the alternative).
    List fields (medications, comorbidities, ...): items pair up greedily
    by :func:`values_agree`; unpaired specialist items are specialist-only
    and unpaired LLM items are LLM-only.  Nullish LLM values are dropped,
    except "unknown" epilepsy type (``_UNKNOWN_IS_VALUE``).
    """
    llm_by_path: dict[str, list[FieldItem]] = {}
    for it in llm:
        v = it.ev.get("value")
        if is_nullish(v) and not (it.field_path in _UNKNOWN_IS_VALUE and isinstance(v, str)
                                  and _norm_str(v) == "unknown"):
            continue
        llm_by_path.setdefault(it.field_path, []).append(it)

    spec_list = list(specialist)
    fused: list[FusedSpecialist] = []
    used: set[int] = set()        # id() of items that matched at least once (kept out of llm_only)
    used_pool: set[int] = set()   # id() of items removed from the matching pool (reusable paths stay)

    for sp in spec_list:
        pool = [c for c in llm_by_path.get(sp.field_path, []) if id(c) not in used_pool]
        match = next((c for c in pool if values_agree(sp.ev.get("value"), c.ev.get("value"))), None)
        if match is not None:
            used.add(id(match))
            if match.field_path not in REUSABLE_LLM_PATHS:
                used_pool.add(id(match))
            fused.append(FusedSpecialist(sp, "agree", llm_item=match))
            continue
        if not sp.multi and pool:
            # Scalar field, LLM committed to a different value.
            other = pool[0]
            used.add(id(other))
            used_pool.add(id(other))
            fused.append(FusedSpecialist(
                sp, "disagree",
                alternative=display_value(other.ev.get("value")),
                llm_item=other,
            ))
            continue
        fused.append(FusedSpecialist(sp, "specialist_only"))

    llm_only = [it for items in llm_by_path.values() for it in items if id(it) not in used]
    return Fusion(fused, llm_only)


# ─── Locating an LLM quote in the note ───────────────────────────────────

def locate_quote(quote: str, text: str) -> Optional[tuple[int, int]]:
    """Find ``quote`` in ``text`` tolerating whitespace and case drift.

    Returns the (start, end) of the *actual* source slice, or None when the
    quote is not in the note (a paraphrase or a hallucination).  Matching
    is deliberately the same notion of "verbatim" used by
    ``services.evidence_verifier``: same tokens in the same order.
    """
    quote = (quote or "").strip()
    if not quote:
        return None
    idx = text.find(quote)
    if idx >= 0:
        return idx, idx + len(quote)
    toks = quote.split()
    if not toks:
        return None
    pat = r"\s+".join(re.escape(t) for t in toks)
    m = re.search(pat, text, flags=re.IGNORECASE)
    return (m.start(), m.end()) if m else None


# ─── Value grounding (evidence located by the system, not by the model) ───

_NUMW = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
         "sixteen seventeen eighteen nineteen twenty").split()
_NUM_RX = r"(?:\d+(?:\.\d+)?|" + "|".join(_NUMW) + r")"
_DOSE_TAIL = re.compile(
    r"\s+\d[\d.,]*\s*(?:mg|g|mcg|ml)\b(?:\s+(?:once|twice|three times|four times|bd|bid|od|tds|qds|nocte|mane|"
    r"daily|a day|per day|in the (?:morning|evening)|at night)\b[a-z\- ]{0,25})?", re.I)

_ETYPE_RX = {
    "generalized": r"generali[sz]ed|idiopathic generali[sz]ed|\bGGE\b|\bJME\b|juvenile myoclonic|absence epilepsy",
    "focal": r"\bfocal\b|partial|temporal lobe|frontal lobe|parietal|occipital|\bTLE\b|\bFLE\b",
    "combined_focal_generalized": r"generali[sz]ed and focal|focal and generali[sz]ed|combined",
}
_STYPE_RX = {
    "generalized_tonic_clonic": r"generali[sz]ed\W+tonic\W*clonic|\bGTCS?\b|grand mal|tonic\W*clonic",
    "focal_to_bilateral_tonic_clonic": r"secondar(?:ily|y)\W+generali[sz]ed|focal\W+to\W+bilateral|bilateral\W+tonic\W*clonic|focal.{0,40}tonic\W*clonic",
    "focal_impaired_awareness": r"impaired (?:awareness|consciousness)|loss of awareness|complex partial|focal.{0,30}(?:awareness|dyscognitive)",
    "focal_aware": r"focal aware|simple partial|without (?:loss|impair\w*)(?: of)? (?:awareness|consciousness)|aura",
    "focal_unknown_awareness": r"\bfocal\b|partial",
    "generalized_absence_typical": r"absence",
    "generalized_absence_atypical": r"atypical absence",
    "generalized_myoclonic": r"myoclon",
    "generalized_atonic": r"atonic|drop attack",
    "generalized_tonic": r"\btonic\b",
    "generalized_clonic": r"\bclonic\b",
    "generalized_epileptic_spasms": r"spasm",
}
_FREE_RX = re.compile(
    r"seizure[- ]free|free of seizures|no (?:further |recent |more )?(?:seizures|fits|events|attacks)|"
    r"not had (?:a |any )?(?:further |recent )?(?:seizure|fit)s?|(?:seizures|fits) (?:have )?stopped", re.I)
_FREQ_RX = re.compile(
    rf"(?:{_NUM_RX}(?:\s*(?:-|to|or)\s*{_NUM_RX})?\s+(?:\w+\s+){{0,4}}?(?:per|a|each|every|in a|over)\s+"
    r"(?:day|week|month|year|fortnight)s?|"
    r"(?:once|twice)\s+(?:a|per|every|each)\s+(?:day|week|month|year)|"
    r"every\s+(?:\w+\s+)?(?:days?|weeks?|months?|years?)|"
    r"(?:daily|weekly|monthly|yearly|annual))", re.I)


def _to_num(tok: str) -> Optional[float]:
    tok = tok.lower()
    if tok in _NUMW:
        return float(_NUMW.index(tok) + 1)
    try:
        return float(tok)
    except ValueError:
        return None


def _drug_names(name: str) -> list[str]:
    """The generic name plus lexicon salts, brands and other names for it."""
    names = {name.lower()}
    try:
        from rules.asm_lexicon import ASM_LEXICON
        for key, e in ASM_LEXICON.items():
            group = {key, (e.get("label") or "").lower(), *[x.lower() for x in e.get("salts", [])],
                     *[x.lower() for x in e.get("brands", [])], *[x.lower() for x in e.get("other_names", [])]}
            if name.lower() in group or any(name.lower() in g or g in name.lower() for g in group if len(g) > 4):
                names |= {g for g in group if g}
    except Exception:
        pass
    return sorted((n for n in names if n), key=len, reverse=True)


def ground_value(field_path: str, value: Any, text: str) -> Optional[tuple[int, int]]:
    """Find a span of ``text`` that supports ``value`` of ``field_path``.

    Used when the model's own quote cannot be found in the note (the
    fine-tuned adapter writes templated evidence strings, not copied ones).
    The span is chosen by this function, never taken from the model, so a
    grounded claim still carries evidence a reviewer can read in the note.
    Returns None when nothing in the note supports the value.
    """
    if value is None or not text:
        return None
    try:
        if field_path == "medication.current_asms":
            name = (value.get("generic_name") if isinstance(value, dict) else str(value)) or ""
            for n in _drug_names(name.strip()):
                m = re.search(rf"\b{re.escape(n)}\b", text, re.I)
                if m:
                    tail = _DOSE_TAIL.match(text, m.end())
                    return m.start(), (tail.end() if tail else m.end())
            return None
        if field_path == "clinical_seizure.epilepsy_type":
            rx = _ETYPE_RX.get(str(value).lower())
            m = re.search(rx, text, re.I) if rx else None
            return (m.start(), m.end()) if m else None
        if field_path == "clinical_seizure.predominant_seizure_type":
            rx = _STYPE_RX.get(str(value).lower())
            m = re.search(rx, text, re.I) if rx else None
            return (m.start(), m.end()) if m else None
        if field_path == "clinical_seizure.age_at_onset_years":
            v = float(value)
            for m in re.finditer(
                    rf"(?:age[d]?|started|began|onset|since|from|at)\W+(?:\w+\W+){{0,4}}?({_NUM_RX})\b", text, re.I):
                n = _to_num(m.group(1))
                if n is not None and abs(n - v) <= 1.0:
                    return m.start(), m.end()
            return None
        if field_path == "clinical_seizure.seizure_frequency" and isinstance(value, dict):
            if value.get("seizure_free"):
                m = _FREE_RX.search(text)
                return (m.start(), m.end()) if m else None
            lo, hi = value.get("count_min"), value.get("count_max")
            first = None
            for m in _FREQ_RX.finditer(text):
                first = first or m
                nums = [_to_num(t) for t in re.findall(_NUM_RX, m.group(0), re.I)]
                nums = [x for x in nums if x is not None]
                if lo is None or (nums and any(abs(x - float(lo)) < 1e-6 for x in nums)):
                    return m.start(), m.end()
            return (first.start(), first.end()) if (first and lo is None) else None
    except Exception:
        return None
    return None


# ─── Reasoners ───────────────────────────────────────────────────────────

# A reasoner maps (note_text, document_id, doc_date) -> phenotype dict | None.
LLMReasoner = Callable[[str, str, str], Optional[dict]]


@dataclass
class LLMRunInfo:
    """Provenance that goes into ``Claim.versions``."""
    model: str = ""
    prompt: str = ""


class LiveLLMReasoner:
    """Run Med42-8B on the note now (one prompt per applicable module)."""

    def __init__(self, backend: Any, *, arm: str = "M3", version: str = "v1",
                 decoding: Any = None, write_manifests: bool = False):
        self.backend = backend
        self.arm = arm
        self.version = version
        self.decoding = decoding
        self.write_manifests = write_manifests
        self.info = LLMRunInfo(
            model=getattr(backend, "model_name", ""),
            prompt=f"*.{arm}.{version}",
        )

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        from schema import SCHEMA_VERSION, DocumentMetadata, DocumentType
        from services.extract import DecodingConfig
        from services.router import extract_phenotype
        try:
            dd = date.fromisoformat(doc_date)
        except Exception:
            dd = date(2026, 1, 1)
        doc = DocumentMetadata(doc_id=document_id, patient_id=document_id,
                               doc_type=DocumentType.PROGRESS_NOTE, doc_date=dd)
        decoding = self.decoding or DecodingConfig(
            do_sample=False, temperature=None, top_p=None,
            max_new_tokens=4096, seed=0, constrained=False,
        )
        try:
            res = extract_phenotype(
                doc=doc, source_text=text, model_backend=self.backend,
                arm=self.arm, schema_version=SCHEMA_VERSION,
                decoding=decoding, version=self.version,
                write_manifests=self.write_manifests,
            )
        except Exception:
            logger.exception("LLM extraction failed; continuing specialist-only")
            return None
        return res.phenotype.model_dump(mode="json")


class FTLiveReasoner:
    """Run a LoRA-tuned Med42-8B in its training contract (Arm H).

    One full-phenotype generation with the training prompt, split per module
    (``services.ft_extract``).  Use this, not :class:`LiveLLMReasoner`, with
    an adapter: the adapters were never trained on the M0-M3 prompts.
    """

    def __init__(self, backend: Any, *, max_new_tokens: int = 4096):
        self.backend = backend
        self.max_new_tokens = max_new_tokens
        self.info = LLMRunInfo(model=getattr(backend, "model_name", ""),
                               prompt="epilepsy_phenotype.FT.v1")

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        from services.ft_extract import generate_ft, is_degenerate, split_phenotype
        try:
            raw, _ = generate_ft(self.backend, text, document_id,
                                 max_new_tokens=self.max_new_tokens)
        except Exception:
            logger.exception("tuned LLM generation failed; continuing specialist-only")
            return None
        modules = split_phenotype(raw, doc_id=document_id)
        if not modules or is_degenerate(modules):
            logger.warning("tuned LLM returned no populated modules for %s", document_id)
            return None
        return modules


class FlatLiveReasoner:
    """Run Med42-8B on the flat contract now (arms L0/L1/L0C/L1C; or Arm H2 with its adapter).

    This is the arm the evaluation recommends: five fields, each with a verbatim quote, with
    schema-constrained decoding for the ``C`` arms (``docs/EVAL_PROTOCOL_LEO.md`` 10.3).  The
    parsed output has the shape the fuser reads.  ``L2``/``L2C`` need F-S exemplars and are not
    offered here.
    """

    def __init__(self, backend: Any, *, arm: str = "L1C", max_new_tokens: int = 768):
        if arm not in ("L0", "L1", "L0C", "L1C"):
            raise ValueError(f"FlatLiveReasoner arm must be L0, L1, L0C or L1C, got {arm!r}")
        self.backend = backend
        self.arm = arm
        self.max_new_tokens = max_new_tokens
        from services.flat_extract import FLAT_PROMPT_VERSION
        self.version = FLAT_PROMPT_VERSION
        self.info = LLMRunInfo(model=getattr(backend, "model_name", ""),
                               prompt=f"flat_phenotype.{arm}.{self.version}")
        self.n_calls = 0
        self.last_ok = False

    @property
    def last_covered_field_paths(self):
        from services.flat_extract import FLAT_FIELD_PATHS
        return FLAT_FIELD_PATHS if self.last_ok else frozenset()

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        from services.extract import DecodingConfig
        from services.flat_extract import build_flat_prompt, flat_answer_model, parse_flat
        self.last_ok = False
        decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                                  max_new_tokens=self.max_new_tokens, seed=0, constrained=False)
        prompt = build_flat_prompt(text, self.arm, version=self.version)
        try:
            if self.arm.endswith("C"):
                raw, _ = self.backend.generate_constrained(prompt, flat_answer_model(self.version), decoding)
            else:
                raw, _ = self.backend.generate(prompt, decoding)
        except Exception:
            logger.exception("flat LLM generation failed; continuing specialist-only")
            return None
        self.n_calls += 1
        parsed = parse_flat(raw, self.version)
        if not parsed.parse_ok:
            return None
        self.last_ok = True
        return parsed.modules or {}


class ExtendedLiveReasoner:
    """Second call on the same note: the extended fields (arm X1C).  See ``services.ext_extract``."""

    def __init__(self, backend: Any, *, max_new_tokens: int = 768):
        self.backend = backend
        self.max_new_tokens = max_new_tokens
        from services.ext_extract import EXT_ARM, EXT_PROMPT_VERSION
        self.info = LLMRunInfo(model=getattr(backend, "model_name", ""),
                               prompt=f"ext_phenotype.{EXT_ARM}.{EXT_PROMPT_VERSION}")
        self.n_calls = 0
        self.last_ok = False

    @property
    def last_covered_field_paths(self):
        from services.ext_extract import EXT_FIELD_PATHS
        return EXT_FIELD_PATHS if self.last_ok else frozenset()

    def _one(self, text: str, document_id: str) -> Optional[dict]:
        from services.extract import DecodingConfig
        from services.ext_extract import build_ext_prompt, ext_answer_model, parse_ext
        decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                                  max_new_tokens=self.max_new_tokens, seed=0, constrained=False)
        try:
            raw, _ = self.backend.generate_constrained(build_ext_prompt(text),
                                                       ext_answer_model(), decoding)
        except Exception:
            logger.exception("extended LLM generation failed; continuing without X1C")
            return None
        self.n_calls += 1
        parsed = parse_ext(raw)
        return parsed.modules or {} if parsed.parse_ok else None

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        from services.ext_extract import EXT_MAX_NOTE_CHARS
        self.last_ok = False
        if len(text) > EXT_MAX_NOTE_CHARS:
            from services.chunker import chunk_text
            chunks = chunk_text(text, max_chars=EXT_MAX_NOTE_CHARS, overlap_chars=400, pack=True)
            parts = [self._one(c.text, f"{document_id}#x{c.chunk_index}") for c in chunks]
            self.last_ok = any(p is not None for p in parts)
            return merge_chunk_phenotypes(parts)
        out = self._one(text, document_id)
        self.last_ok = out is not None
        return out


class PhenoLiveReasoner:
    """Third call on the same note: remaining closed-vocab phenotype fields (arm P1C)."""

    def __init__(self, backend: Any, *, max_new_tokens: int = 768):
        self.backend = backend
        self.max_new_tokens = max_new_tokens
        from services.pheno_extract import PHENO_ARM, PHENO_PROMPT_VERSION
        self.info = LLMRunInfo(model=getattr(backend, "model_name", ""),
                               prompt=f"pheno_phenotype.{PHENO_ARM}.{PHENO_PROMPT_VERSION}")
        self.n_calls = 0
        self.last_ok = False

    @property
    def last_covered_field_paths(self):
        from services.pheno_extract import PHENO_FIELD_PATHS
        return PHENO_FIELD_PATHS if self.last_ok else frozenset()

    def _one(self, text: str, document_id: str) -> Optional[dict]:
        from services.extract import DecodingConfig
        from services.pheno_extract import build_pheno_prompt, parse_pheno, pheno_answer_model
        decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                                  max_new_tokens=self.max_new_tokens, seed=0, constrained=False)
        try:
            raw, _ = self.backend.generate_constrained(build_pheno_prompt(text),
                                                       pheno_answer_model(), decoding)
        except Exception:
            logger.exception("phenotype LLM generation failed; continuing without P1C")
            return None
        self.n_calls += 1
        parsed = parse_pheno(raw)
        return parsed.modules or {} if parsed.parse_ok else None

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        from services.pheno_extract import PHENO_MAX_NOTE_CHARS
        self.last_ok = False
        if len(text) > PHENO_MAX_NOTE_CHARS:
            from services.chunker import chunk_text
            chunks = chunk_text(text, max_chars=PHENO_MAX_NOTE_CHARS, overlap_chars=400, pack=True)
            parts = [self._one(c.text, f"{document_id}#p{c.chunk_index}") for c in chunks]
            self.last_ok = any(p is not None for p in parts)
            return merge_chunk_phenotypes(parts)
        out = self._one(text, document_id)
        self.last_ok = out is not None
        return out


class FullLiveReasoner:
    """Fourth call: leftover schema fields (arm F1C).  See ``services.full_extract``."""

    def __init__(self, backend: Any, *, max_new_tokens: int = 768):
        self.backend = backend
        self.max_new_tokens = max_new_tokens
        from services.full_extract import FULL_ARM, FULL_PROMPT_VERSION
        self.info = LLMRunInfo(model=getattr(backend, "model_name", ""),
                               prompt=f"full_phenotype.{FULL_ARM}.{FULL_PROMPT_VERSION}")
        self.n_calls = 0
        self.last_ok = False

    @property
    def last_covered_field_paths(self):
        from services.full_extract import FULL_FIELD_PATHS
        return FULL_FIELD_PATHS if self.last_ok else frozenset()

    def _one(self, text: str, document_id: str) -> Optional[dict]:
        from services.extract import DecodingConfig
        from services.full_extract import build_full_prompt, full_answer_model, parse_full
        decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None,
                                  max_new_tokens=self.max_new_tokens, seed=0, constrained=False)
        try:
            raw, _ = self.backend.generate_constrained(build_full_prompt(text),
                                                       full_answer_model(), decoding)
        except Exception:
            logger.exception("full-phenotype LLM generation failed; continuing without F1C")
            return None
        self.n_calls += 1
        parsed = parse_full(raw)
        return parsed.modules or {} if parsed.parse_ok else None

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        from services.full_extract import FULL_MAX_NOTE_CHARS
        self.last_ok = False
        if len(text) > FULL_MAX_NOTE_CHARS:
            from services.chunker import chunk_text
            chunks = chunk_text(text, max_chars=FULL_MAX_NOTE_CHARS, overlap_chars=400, pack=True)
            parts = [self._one(c.text, f"{document_id}#f{c.chunk_index}") for c in chunks]
            self.last_ok = any(p is not None for p in parts)
            return merge_chunk_phenotypes(parts)
        out = self._one(text, document_id)
        self.last_ok = out is not None
        return out


class CombinedReasoner:
    """Run L1C, X1C, P1C and F1C on the same text and merge their modules.

    One reader failing does not drop the others.  ``last_covered_field_paths`` is the union of the
    readers that parsed, so the pipeline can tell "the model read this field and found nothing"
    from "no model reads this field".
    """

    def __init__(self, flat: Any, ext: Any, pheno: Any = None, full: Any = None):
        self.flat, self.ext, self.pheno, self.full = flat, ext, pheno, full
        prompts = [getattr(flat, "info", LLMRunInfo()).prompt,
                   getattr(ext, "info", LLMRunInfo()).prompt]
        if pheno is not None:
            prompts.append(getattr(pheno, "info", LLMRunInfo()).prompt)
        if full is not None:
            prompts.append(getattr(full, "info", LLMRunInfo()).prompt)
        self.info = LLMRunInfo(model=getattr(flat, "info", LLMRunInfo()).model,
                               prompt="+".join(prompts))
        self.last_ok = False
        self.last_covered_field_paths: Optional[frozenset] = frozenset()

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        from services.ext_extract import EXT_FIELD_PATHS
        from services.flat_extract import FLAT_FIELD_PATHS
        from services.full_extract import FULL_FIELD_PATHS
        from services.pheno_extract import PHENO_FIELD_PATHS
        a = b = c = d = None
        try:
            a = self.flat(text, document_id, doc_date)
        except Exception:
            logger.exception("core LLM reader failed; continuing with the other readers")
        try:
            b = self.ext(text, document_id, doc_date)
        except Exception:
            logger.exception("extended LLM reader failed; continuing with the other readers")
        if self.pheno is not None:
            try:
                c = self.pheno(text, document_id, doc_date)
            except Exception:
                logger.exception("phenotype LLM reader failed; continuing with the other readers")
        if self.full is not None:
            try:
                d = self.full(text, document_id, doc_date)
            except Exception:
                logger.exception("full-phenotype LLM reader failed; continuing with the other readers")
        cov: set[str] = set()
        if getattr(self.flat, "last_ok", False):
            cov |= set(getattr(self.flat, "last_covered_field_paths", None) or FLAT_FIELD_PATHS)
        if getattr(self.ext, "last_ok", False):
            cov |= set(getattr(self.ext, "last_covered_field_paths", None) or EXT_FIELD_PATHS)
        if self.pheno is not None and getattr(self.pheno, "last_ok", False):
            cov |= set(getattr(self.pheno, "last_covered_field_paths", None) or PHENO_FIELD_PATHS)
        if self.full is not None and getattr(self.full, "last_ok", False):
            cov |= set(getattr(self.full, "last_covered_field_paths", None) or FULL_FIELD_PATHS)
        self.last_covered_field_paths = frozenset(cov)
        self.last_ok = bool(cov)
        parts = [p for p in (a, b, c, d) if p is not None]
        if not parts:
            return {} if cov else None
        return merge_chunk_phenotypes(parts)


def _merge_key(value: Any) -> str:
    if isinstance(value, dict):
        return json.dumps({k: value.get(k) for k in ("period", "count_min", "count_max", "seizure_free")},
                          sort_keys=True)
    return _norm_str(value)


def _list_key(ev: dict) -> str:
    v = ev.get("value")
    if isinstance(v, dict):
        if v.get("generic_name"):
            return "drug:" + _canon_drug(v["generic_name"])
        return json.dumps(v, sort_keys=True, default=str)
    return _canon_drug(str(v or ""))


def merge_chunk_phenotypes(parts: list[Optional[dict]]) -> Optional[dict]:
    """Merge per-chunk LLM phenotypes (``{module: {field: Evidence | [Evidence]}}``) into one.

    Scalar fields: the value found in most chunks wins; a tie goes to the earliest chunk.  List
    fields: union, one entry per identity (drug name, or the whole structured value), first quote
    kept.  Quotes are verbatim in the chunk and so in the note; offsets are located later in the
    full text by the pipeline.  A single non-empty part is returned unchanged.
    """
    parts = [p for p in parts if p is not None]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    merged: dict = {}
    modules = {m for p in parts for m in p}
    for module in modules:
        fields = {f for p in parts for f in (p.get(module) or {})}
        out: dict = {}
        for fld in fields:
            cands = [(p.get(module) or {}).get(fld) for p in parts]
            cands = [c for c in cands if c]
            if not cands:
                continue
            if isinstance(cands[0], list):
                seen: dict[str, Any] = {}
                for lst in cands:
                    for ev in lst:
                        seen.setdefault(_list_key(ev), ev)
                out[fld] = list(seen.values())
            else:
                counts: dict[str, list] = {}
                for ev in cands:
                    counts.setdefault(_merge_key(ev.get("value")), []).append(ev)
                out[fld] = max(counts.values(), key=len)[0]      # max keeps the first of equal sizes
        if out:
            merged[module] = out
    return merged or None


class ChunkedReasoner:
    """Run any LLM reasoner on long notes by splitting them into sections and paragraphs.

    The specialist (EpExtra) always reads the whole note; only the LLM channel has a context
    limit.  Notes up to ``max_chars`` go to the inner reasoner unchanged (so short notes behave
    exactly as in the evaluation).  Longer notes are split by ``services.chunker.chunk_text``
    (clinical section, then paragraph, ``overlap_chars`` of overlap) and the answers merged with
    :func:`merge_chunk_phenotypes`.  Not evaluated on long notes: the evaluation sets are short.
    """

    def __init__(self, inner: Any, *, max_chars: int = 8000, overlap_chars: int = 400):
        self.inner = inner
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars
        self.info = getattr(inner, "info", LLMRunInfo())
        self.last_n_chunks = 1
        self.last_covered_field_paths: Optional[frozenset] = None

    def has(self, document_id: str) -> bool:
        return getattr(self.inner, "has", lambda _d: True)(document_id)

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        if len(text) <= self.max_chars:
            self.last_n_chunks = 1
            out = self.inner(text, document_id, doc_date)
            self.last_covered_field_paths = getattr(self.inner, "last_covered_field_paths", None)
            return out
        from services.chunker import chunk_text
        chunks = chunk_text(text, max_chars=self.max_chars, overlap_chars=self.overlap_chars, pack=True)
        self.last_n_chunks = max(1, len(chunks))
        parts, covered = [], []
        for c in chunks:
            parts.append(self.inner(c.text, f"{document_id}#c{c.chunk_index}", doc_date))
            covered.append(getattr(self.inner, "last_covered_field_paths", None))
        if any(c is None for c in covered):
            self.last_covered_field_paths = None
        elif covered:
            self.last_covered_field_paths = frozenset.intersection(*[frozenset(c) for c in covered])
        else:
            self.last_covered_field_paths = frozenset()
        return merge_chunk_phenotypes(parts)



def load_live_reasoner(*, arm: str = "M3", adapter_dir: str = "",
                       model_name: str = "", cache_dir: str = "", backend: Any = None,
                       chunk_max_chars: int = 0) -> Any:
    """Load Med42-8B (optionally with a LoRA adapter) and wrap it.

    Needs a GPU.  ``arm`` selects the reasoner: ``L0``/``L1``/``L0C``/``L1C`` the flat contract
    (recommended: ``L1C``; also used with the Arm H2 adapter), ``M0``-``M3`` the per-module
    prompts, and any other arm with ``adapter_dir`` the Arm H contract.  Pass ``backend`` to reuse
    a model that is already loaded (the web app does).  ``chunk_max_chars > 0`` wraps the reasoner
    in :class:`ChunkedReasoner`.
    """
    import os

    repo = Path(__file__).resolve().parent.parent
    if backend is None:
        from services.med42_backend import Med42Backend
        from services.med42_model import Med42ModelService

        if adapter_dir:
            os.environ["MEDAI_LORA_ADAPTER_DIR"] = adapter_dir

        class _Cfg:
            pass

        cfg = _Cfg()
        cfg.model_name = model_name or os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
        cfg.model_cache_dir = cache_dir or os.environ.get("MED42_MODEL_CACHE_DIR", str(repo / "model_cache"))
        cfg.max_concurrent_users = 1
        svc = Med42ModelService(cfg)
        if not svc.load_model():
            raise RuntimeError(f"Failed to load Med42-8B: {svc.load_error}")
        backend = Med42Backend(svc)
    if arm in ("L0", "L1", "L0C", "L1C"):
        reasoner: Any = FlatLiveReasoner(backend, arm=arm)
    elif adapter_dir:
        reasoner = FTLiveReasoner(backend)
    else:
        reasoner = LiveLLMReasoner(backend, arm=arm)
    return ChunkedReasoner(reasoner, max_chars=chunk_max_chars) if chunk_max_chars > 0 else reasoner


class ManifestLLMReasoner:
    """Replay Med42 outputs from run manifests instead of calling the model.

    ``manifest_dirs`` are searched recursively for ``*.json`` manifests.  A
    manifest belongs to a note when its ``source_doc_id`` equals
    ``doc_id_map(document_id)`` (default: ``fs-test-<document_id>``, the
    convention of ``scripts/run_med42_on_fs_test.py``) and its ``arm`` is
    ``arm``.  ``flat_phenotype.L0|L1.v1`` manifests (base model, flat prompts) are
    parsed by ``services.flat_extract.parse_flat``.  Manifests of
    ``prompt_id = epilepsy_phenotype.FT.v1`` (written by
    ``scripts/run_med42_ft_on_fs_test.py``) hold one full-phenotype generation
    and are split per module by ``services.ft_extract.split_phenotype``.
    Invalid LLM output is repaired exactly as the arm scorer does
    (``try_smart_repair``), so LEO sees the same phenotype the arm table
    scored.
    """

    def __init__(self, manifest_dirs: Iterable[str | Path], *, arm: str,
                 doc_id_map: Optional[Callable[[str], str]] = None):
        self.arm = arm
        self.doc_id_map = doc_id_map or (lambda d: f"fs-test-{d}")
        self._index: dict[str, dict[str, dict]] = {}   # doc -> module -> manifest
        self.info = LLMRunInfo(model="", prompt=f"*.{arm}.v1")
        for d in manifest_dirs:
            for p in sorted(Path(d).rglob("*.json")):
                try:
                    m = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if m.get("arm") != arm:
                    continue
                parts = (m.get("prompt_id") or "").split(".")
                if len(parts) != 3:
                    continue
                self._index.setdefault(m.get("source_doc_id", ""), {})[parts[0]] = m
                self.info.model = self.info.model or m.get("model_name", "")

    def has(self, document_id: str) -> bool:
        return self.doc_id_map(document_id) in self._index

    def __call__(self, text: str, document_id: str, doc_date: str) -> Optional[dict]:
        mods = self._index.get(self.doc_id_map(document_id))
        if not mods:
            return None
        flat = next((m for k, m in mods.items() if k == "flat_phenotype"), None)
        if flat is not None:
            from services.flat_extract import parse_flat
            return parse_flat(flat.get("raw_response", ""),
                              flat.get("prompt_version") or "v1").modules or None
        if "epilepsy_phenotype" in mods:
            # In-contract output of a tuned adapter: one full-phenotype generation.
            from services.ft_extract import split_phenotype
            return split_phenotype(mods["epilepsy_phenotype"].get("raw_response", ""),
                                   doc_id=document_id) or None
        from schema import DocumentMetadata, DocumentType
        from services.router import MODULE_CLASSES
        from services.smart_repair import try_smart_repair
        doc = DocumentMetadata(
            doc_id=document_id, patient_id=document_id,
            doc_type=DocumentType.PROGRESS_NOTE, doc_date=date(2024, 1, 1),
        )
        pheno: dict = {}
        for module, man in mods.items():
            cls = MODULE_CLASSES.get(module)
            if cls is None:
                continue
            validated, _raw, _err = try_smart_repair(man.get("raw_response", ""), cls, doc)
            if validated is not None:
                pheno[module] = validated.model_dump(mode="json")
        return pheno or None


__all__ = [
    "freq_counts", "is_empty_frequency", "FieldItem", "Fusion", "FusedSpecialist", "LLM_DETECTOR", "LLMReasoner",
    "FTLiveReasoner", "FlatLiveReasoner", "ExtendedLiveReasoner", "PhenoLiveReasoner", "FullLiveReasoner", "CombinedReasoner",
    "ChunkedReasoner", "merge_chunk_phenotypes", "LLMRunInfo", "LiveLLMReasoner", "ManifestLLMReasoner", "load_live_reasoner",
    "display_value", "flatten", "fuse", "is_nullish", "locate_quote",
    "values_agree",
]
