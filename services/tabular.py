"""Flatten a validated `EpilepsyPhenotype` (or any module) into long-format
CSV rows for downstream analysis.

    to_long_rows(phenotype)   → list[dict], one row per (module, field, list-index)

Long-format columns
-------------------
    doc_id, patient_id, doc_type, doc_date, visit_date, module,
    field, value, evidence_text, confidence, temporal_status,
    char_start, char_end, source_doc_id, chunk_index, note

`field` follows a dotted path so `current_asms[0]` is different from
`current_asms[1]`. This lets pandas `pivot_table` or SQL group-by both
work. `confidence` carries the `certainty` enum value (definite /
probable / possible / unknown / negated / not_documented) — this is
the model's calibration slot.

Values are rendered as:
    - scalar enum   → enum.value
    - primitive     → str(v)
    - value object  → "key1=v1; key2=v2" (Medication et al.)
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel

from schema import Certainty, Evidence, EpilepsyPhenotype


# ---------------------------------------------------------------------------
# Row model (long format)
# ---------------------------------------------------------------------------


LONG_COLUMNS = [
    "doc_id", "patient_id", "doc_type", "doc_date", "visit_date",
    "module", "field",
    "value", "evidence_text", "confidence", "temporal_status",
    "char_start", "char_end", "source_doc_id", "chunk_index",
    "note",
]


def _render_value(v: Any) -> str:
    if v is None:
        return ""
    if hasattr(v, "value") and not hasattr(v, "model_dump"):
        return str(v.value)
    if hasattr(v, "model_dump"):
        d = v.model_dump(mode="json")
        pieces = [f"{k}={_flat_scalar(val)}" for k, val in d.items() if val is not None]
        return "; ".join(pieces)
    return str(v)


def _flat_scalar(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _evidence_row(
    *,
    doc: dict,
    module: str,
    field: str,
    ev: Evidence,
    chunk_index: int | None = None,
) -> dict:
    return {
        **doc,
        "module": module,
        "field": field,
        "value": _render_value(ev.value),
        "evidence_text": ev.evidence_text or "",
        "confidence": ev.certainty.value if isinstance(ev.certainty, Certainty)
                      else str(ev.certainty),
        "temporal_status": ev.temporal_status.value if hasattr(ev.temporal_status, "value")
                           else str(ev.temporal_status),
        "char_start": ev.char_start if ev.char_start is not None else "",
        "char_end": ev.char_end if ev.char_end is not None else "",
        "source_doc_id": ev.source_doc_id,
        "chunk_index": chunk_index if chunk_index is not None else "",
        "note": "",
    }


# ---------------------------------------------------------------------------
# Module flattening
# ---------------------------------------------------------------------------


def _iter_module_fields(module: BaseModel, module_name: str, doc: dict,
                        chunk_index: int | None = None) -> Iterable[dict]:
    """Yield one row per Evidence field (or per list item for list-Evidence)."""
    for fname, finfo in type(module).model_fields.items():
        val = getattr(module, fname)
        if isinstance(val, Evidence):
            yield _evidence_row(doc=doc, module=module_name, field=fname,
                                ev=val, chunk_index=chunk_index)
        elif isinstance(val, list):
            if not val:
                yield {
                    **doc, "module": module_name, "field": fname,
                    "value": "", "evidence_text": "", "confidence": "not_documented",
                    "temporal_status": "unspecified",
                    "char_start": "", "char_end": "",
                    "source_doc_id": doc.get("doc_id", ""),
                    "chunk_index": chunk_index if chunk_index is not None else "",
                    "note": "(empty list)",
                }
                continue
            for i, item in enumerate(val):
                if isinstance(item, Evidence):
                    yield _evidence_row(doc=doc, module=module_name,
                                        field=f"{fname}[{i}]",
                                        ev=item, chunk_index=chunk_index)


# ---------------------------------------------------------------------------
# Public API — long format
# ---------------------------------------------------------------------------


def _doc_cols(phenotype: EpilepsyPhenotype, visit_date: str | None = None) -> dict:
    d = phenotype.document
    return {
        "doc_id": d.doc_id,
        "patient_id": d.patient_id,
        "doc_type": d.doc_type.value if hasattr(d.doc_type, "value") else str(d.doc_type),
        "doc_date": d.doc_date.isoformat(),
        "visit_date": visit_date or "",
    }


def to_long_rows(
    phenotype: EpilepsyPhenotype,
    *,
    visit_date: str | None = None,
    chunk_index: int | None = None,
    include_not_documented: bool = True,
) -> list[dict]:
    """Flatten a phenotype record to long-format rows (one row per field)."""
    doc = _doc_cols(phenotype, visit_date=visit_date)
    rows: list[dict] = []
    for mod_name in ("clinical_seizure", "medication", "clinical_localization",
                     "eeg", "mri", "integrated"):
        module = getattr(phenotype, mod_name, None)
        if module is None:
            continue
        for row in _iter_module_fields(module, mod_name, doc,
                                        chunk_index=chunk_index):
            if (not include_not_documented
                    and row.get("confidence") == "not_documented"):
                continue
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# CSV rendering (buffer utilities)
# ---------------------------------------------------------------------------


def rows_to_csv_bytes(rows: list[dict], *, fieldnames: list[str] | None = None) -> bytes:
    """Render a list of dict-rows to CSV bytes (UTF-8, RFC 4180 quoting)."""
    if not rows:
        # Emit header-only CSV so downstream tooling doesn't choke.
        fn = fieldnames or LONG_COLUMNS
        return (",".join(fn) + "\n").encode("utf-8")
    if fieldnames is None:
        # Union of keys across all rows, preserving first-seen order.
        seen: dict[str, None] = {}
        for r in rows:
            for k in r.keys():
                seen[k] = None
        fieldnames = list(seen.keys())
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore",
                       quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# User-query row (chat pass)
# ---------------------------------------------------------------------------


@dataclass
class UserQueryRow:
    """One row appended to the long-format CSV when the user asks a chat
    question. Value = the model's answer; evidence_text = the quoted span
    the model grounded its answer on; confidence = a coarse self-report
    ('definite' | 'probable' | 'possible' | 'unknown')."""
    doc_id: str
    patient_id: str
    doc_type: str
    doc_date: str
    visit_date: str
    question: str
    answer: str
    evidence_text: str
    confidence: str

    def as_long_row(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "patient_id": self.patient_id,
            "doc_type": self.doc_type,
            "doc_date": self.doc_date,
            "visit_date": self.visit_date,
            "module": "user_query",
            "field": self.question[:120],
            "value": self.answer,
            "evidence_text": self.evidence_text,
            "confidence": self.confidence,
            "temporal_status": "unspecified",
            "char_start": "",
            "char_end": "",
            "source_doc_id": self.doc_id,
            "chunk_index": "",
            "note": "user_query",
        }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import json as _json
    from datetime import date as _d
    from schema import (
        DocumentMetadata, DocumentType, MedicationModule, TemporalStatus,
    )
    from schema.enums import DrugResistanceStatus, MedicationStatus
    from schema.ontology import Medication

    src = {"source_doc_id": "EA0001", "source_doc_type": DocumentType.PROGRESS_NOTE,
           "source_date": _d(2024, 5, 10)}

    def ev(v, txt, cert=Certainty.DEFINITE):
        return Evidence(value=v, certainty=cert,
                        temporal_status=TemporalStatus.CURRENT,
                        evidence_text=txt, **src)

    med_mod = MedicationModule(
        current_asms=[
            ev(Medication(generic_name="lamotrigine", status=MedicationStatus.CURRENT, dose_text="75mg BID"),
               "lamotrigine 75mg BID"),
            ev(Medication(generic_name="levetiracetam", status=MedicationStatus.CURRENT, dose_text="1000mg BID"),
               "levetiracetam 1000mg BID"),
        ],
        prior_asms=[], failed_asms=[],
        adverse_effects_text=Evidence.not_documented(**src),
        drug_resistance_status=ev(DrugResistanceStatus.DRUG_RESISTANT,
                                   "meets ILAE drug-resistance criteria",
                                   cert=Certainty.PROBABLE),
        surgery_history=[], non_drug_therapies=[],
    )
    phen = EpilepsyPhenotype(
        document=DocumentMetadata(
            doc_id="EA0001", doc_type=DocumentType.PROGRESS_NOTE,
            doc_date=_d(2024, 5, 10), patient_id="P1",
        ),
        medication=med_mod,
    )

    rows = to_long_rows(phen)
    csv_bytes = rows_to_csv_bytes(rows, fieldnames=LONG_COLUMNS)
    print(csv_bytes.decode("utf-8"))
