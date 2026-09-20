"""Evidence-span verification for M3 (paper §12).

Walk a populated `EpilepsyPhenotype` and check every `Evidence` object with a
non-null value:
  1. `evidence_text` is a non-empty substring of the source document
     (with whitespace-tolerant normalization).
  2. If `char_start` / `char_end` offsets are set, they actually point at the
     text.

Returns counts and violation records suitable for scoring:
  - evidence_supported: number of evidence objects where the span verifies
  - evidence_unsupported: value present but evidence_text does not appear
                          in the source doc (this is the "unsupported claim"
                          rate the paper cares about)
  - evidence_missing: value present but evidence_text is None or empty
                      (schema layer already forbids this — expected 0)
  - offset_mismatches: char_start/end set but does not match evidence_text
  - not_documented_ok: value None with certainty=not_documented — no
                       verification needed.

Verification uses a normalized-whitespace substring test: this tolerates the
model quoting a span with slightly different spacing / newlines than the
source. It does NOT tolerate paraphrasing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterator

from pydantic import BaseModel

from schema import Certainty, EpilepsyPhenotype, Evidence


_WS = re.compile(r"\s+")


def _normalize(s: str) -> str:
    """Collapse all runs of whitespace to a single space, strip, lowercase.

    Case-insensitive because real notes freely alternate "Video-EEG" vs
    "video-EEG" without changing meaning. "Verbatim" per §12 means
    same-tokens-in-order, not same-casing.
    """
    return _WS.sub(" ", s).strip().lower()


@dataclass
class EvidenceViolation:
    field_path: str
    value: Any
    evidence_text: str | None
    kind: str          # unsupported_claim / missing_evidence / offset_mismatch
    detail: str = ""


@dataclass
class VerificationReport:
    total_evidence_objects: int = 0
    evidence_supported: int = 0
    evidence_unsupported: int = 0
    evidence_missing: int = 0
    offset_mismatches: int = 0
    not_documented: int = 0
    violations: list[EvidenceViolation] = field(default_factory=list)

    @property
    def unsupported_claim_rate(self) -> float:
        """Fraction of evidenced claims that are NOT supported by the source.
        Denominator excludes not_documented entries — we score only the claims
        the model actually made."""
        denom = self.evidence_supported + self.evidence_unsupported + self.evidence_missing
        if denom == 0:
            return 0.0
        return self.evidence_unsupported / denom

    @property
    def evidence_precision(self) -> float:
        """Fraction of evidenced claims whose evidence span verifies against source."""
        denom = self.evidence_supported + self.evidence_unsupported + self.evidence_missing
        if denom == 0:
            return 0.0
        return self.evidence_supported / denom

    def to_dict(self) -> dict:
        return {
            "total_evidence_objects": self.total_evidence_objects,
            "evidence_supported": self.evidence_supported,
            "evidence_unsupported": self.evidence_unsupported,
            "evidence_missing": self.evidence_missing,
            "offset_mismatches": self.offset_mismatches,
            "not_documented": self.not_documented,
            "unsupported_claim_rate": round(self.unsupported_claim_rate, 4),
            "evidence_precision": round(self.evidence_precision, 4),
            "violations": [
                {"field_path": v.field_path, "value": v.value,
                 "evidence_text": v.evidence_text, "kind": v.kind, "detail": v.detail}
                for v in self.violations
            ],
        }


def _walk_evidence(obj: Any, path: str = "") -> Iterator[tuple[str, Evidence]]:
    """Yield (path, Evidence) for every Evidence field in a populated model tree."""
    if obj is None:
        return
    if isinstance(obj, Evidence):
        yield path or "$", obj
        # Evidence[T] where T is a Pydantic model may hold nested Evidence too —
        # but per our schema, Evidence wraps value objects whose sub-fields are
        # plain (not Evidence-wrapped). So no recursion into obj.value needed.
        return
    if isinstance(obj, BaseModel):
        for name, value in obj.__dict__.items():
            if value is None:
                continue
            yield from _walk_evidence(value, f"{path}.{name}" if path else name)
        return
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_evidence(v, f"{path}[{i}]")
        return
    # Scalars — nothing to walk


def verify_phenotype(phenotype: EpilepsyPhenotype, source_text: str) -> VerificationReport:
    """Walk the phenotype and verify each Evidence object against the source text."""
    report = VerificationReport()
    norm_source = _normalize(source_text)

    for path, ev in _walk_evidence(phenotype):
        report.total_evidence_objects += 1

        # Not-documented → no verification
        if ev.value is None:
            report.not_documented += 1
            continue

        # Value present → evidence_text must exist and appear in source
        if not ev.evidence_text or not ev.evidence_text.strip():
            report.evidence_missing += 1
            report.violations.append(EvidenceViolation(
                field_path=path,
                value=_repr_value(ev.value),
                evidence_text=ev.evidence_text,
                kind="missing_evidence",
                detail="value present but evidence_text empty",
            ))
            continue

        norm_ev = _normalize(ev.evidence_text)
        if norm_ev in norm_source:
            report.evidence_supported += 1
        else:
            report.evidence_unsupported += 1
            report.violations.append(EvidenceViolation(
                field_path=path,
                value=_repr_value(ev.value),
                evidence_text=ev.evidence_text,
                kind="unsupported_claim",
                detail="evidence_text not found in source document",
            ))

        # Offset check (best-effort — offsets are optional)
        if ev.char_start is not None and ev.char_end is not None:
            slice_ = source_text[ev.char_start:ev.char_end]
            if _normalize(slice_) != norm_ev:
                report.offset_mismatches += 1
                report.violations.append(EvidenceViolation(
                    field_path=path,
                    value=_repr_value(ev.value),
                    evidence_text=ev.evidence_text,
                    kind="offset_mismatch",
                    detail=f"source_text[{ev.char_start}:{ev.char_end}] "
                           f"= {slice_[:60]!r}",
                ))

    return report


def _repr_value(v: Any) -> Any:
    """Short JSON-safe representation of a value for reports."""
    if isinstance(v, BaseModel):
        return v.model_dump(mode="json")
    if hasattr(v, "value"):  # str Enum
        return getattr(v, "value")
    return v
