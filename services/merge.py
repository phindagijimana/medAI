"""Evidence-aware merging of per-chunk module outputs.

Given a Pydantic module class (e.g. `MedicationModule`) and a list of
`(Chunk, extracted_module_or_None)` pairs, produce:

    merged_module  — a single instance of the module class, validated
    MergeReport    — provenance of the merge: how many chunks contributed,
                     which fields had conflicts, and the discarded values.

Merge rules (§ long-doc / longitudinal-visit handling):

    list[Evidence[T]] fields
        Union across chunks. Dedup on (normalized_value, evidence_text).
        char_start/char_end are adjusted to the ORIGINAL text by adding
        the source chunk's char_offset (only when char_offset > 0).

    Evidence[T] scalar fields
        1) Filter to chunks where value is a concrete assertion
           (certainty != NOT_DOCUMENTED and value is not None).
        2) If any of those chunks has a visit_date → latest visit_date wins
           (temporal semantics — Excel-per-visit case).
        3) Otherwise → highest certainty wins; on ties, later chunk position
           wins (free-text case; later in the note usually reflects the
           physician's final judgment in Assessment/Plan).
        4) If ≥ 2 concrete values disagree, the losers are recorded in
           MergeReport.field_conflicts — the schema itself is not mutated.

The merger DOES NOT rewrap Evidence — it reuses the winning `Evidence[T]`
object as-is, so the invariants enforced by Evidence's model_validator
carry over unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Type, get_args, get_origin

from pydantic import BaseModel, ValidationError

from schema import Certainty, Evidence
from .chunker import Chunk


# ---------------------------------------------------------------------------
# Merge report
# ---------------------------------------------------------------------------


@dataclass
class MergeReport:
    module_name: str
    n_chunks_total: int
    n_chunks_contributed: int
    field_conflicts: dict[str, list[dict]] = field(default_factory=dict)
    list_field_dedup_counts: dict[str, tuple[int, int]] = field(default_factory=dict)
    # per-field trace: {field_name: [{"chunk_index":..., "visit_date":..., "value":..., "won":bool}, ...]}
    field_trace: dict[str, list[dict]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Certainty ranking (used for tie-break in free-text case)
# ---------------------------------------------------------------------------

_CERTAINTY_RANK = {
    Certainty.DEFINITE: 4,
    Certainty.PROBABLE: 3,
    Certainty.POSSIBLE: 2,
    Certainty.UNKNOWN: 1,
    Certainty.NEGATED: 1,   # negation is a concrete assertion but should not
                            # dominate a positive one
    Certainty.NOT_DOCUMENTED: 0,
}


def _rank(ev: Evidence) -> int:
    return _CERTAINTY_RANK.get(ev.certainty, 0)


def _is_concrete(ev: Evidence) -> bool:
    return ev.certainty != Certainty.NOT_DOCUMENTED and ev.value is not None


# ---------------------------------------------------------------------------
# Annotation classification
# ---------------------------------------------------------------------------


def _is_evidence_type(tp) -> bool:
    """True iff tp is Evidence, Evidence[...], or a pydantic-v2 concrete
    subclass of Evidence."""
    if tp is Evidence:
        return True
    origin = get_origin(tp)
    if origin is Evidence:
        return True
    try:
        return isinstance(tp, type) and issubclass(tp, Evidence)
    except TypeError:
        return False


def _classify_field(annotation) -> str:
    """Return 'list_evidence' | 'evidence' | 'other'."""
    if _is_evidence_type(annotation):
        return "evidence"
    if get_origin(annotation) is list:
        (inner,) = get_args(annotation) or (None,)
        if inner is not None and _is_evidence_type(inner):
            return "list_evidence"
    return "other"


# ---------------------------------------------------------------------------
# Per-field merge helpers
# ---------------------------------------------------------------------------


# Identifier fields for common value objects — when a list of Evidence[T]
# is merged in longitudinal (has-visit-date) mode, entries are collapsed on
# the identifier and only the latest visit is kept.
_IDENTIFIER_FIELDS = ("generic_name", "therapy_type", "surgery_type", "ied_type")


def _value_identity(v) -> Any:
    """Identifier for a value object — used for longitudinal dedup."""
    if v is None:
        return None
    if hasattr(v, "model_dump"):
        d = v.model_dump(mode="json")
        for key in _IDENTIFIER_FIELDS:
            if key in d and d[key] is not None:
                return (key, d[key])
        return tuple(sorted(d.items()))
    if hasattr(v, "value"):     # enum
        return v.value
    return v


def _dedup_key(ev: Evidence, longitudinal: bool) -> tuple:
    """Key used to collapse duplicate list entries across chunks.

    Longitudinal (visit_date present anywhere): key on value identity only,
    so the same medication mentioned across visits collapses to one entry.
    Non-longitudinal (single note): key on (value, evidence_text) to keep
    distinct mentions as distinct assertions.
    """
    if longitudinal:
        return (_value_identity(ev.value),)
    try:
        v_key = ev.value if not hasattr(ev.value, "model_dump") else tuple(
            sorted(ev.value.model_dump(mode="json").items())
        )
    except Exception:
        v_key = str(ev.value)
    et = (ev.evidence_text or "").strip().lower()
    return (v_key, et)


def _adjust_offsets(ev: Evidence, offset: int) -> Evidence:
    """Shift char_start/char_end by chunk's char_offset. Return the same
    Evidence if offset is 0 or offsets are absent, else a copy with the
    adjustment."""
    if offset == 0 or ev.char_start is None or ev.char_end is None:
        return ev
    return ev.model_copy(update={
        "char_start": ev.char_start + offset,
        "char_end": ev.char_end + offset,
    })


def _merge_list_field(
    per_chunk: list[tuple[Chunk, list]],
) -> tuple[list, tuple[int, int]]:
    """Union + dedup. Returns (deduped_list, (raw_count, deduped_count)).

    If ANY chunk carries a visit_date, we're in longitudinal mode:
    collapse entries by value identity and keep the entry from the latest
    visit (dose_text etc. reflect the current state). Otherwise, keep
    distinct (value, evidence_text) pairs as separate assertions.
    """
    longitudinal = any(c.visit_date is not None for c, _ in per_chunk)
    seen: dict[tuple, tuple[Chunk, Evidence]] = {}
    total = 0
    for chunk, entries in per_chunk:
        if not entries:
            continue
        for ev in entries:
            total += 1
            ev_adj = _adjust_offsets(ev, chunk.char_offset)
            k = _dedup_key(ev_adj, longitudinal)
            if k not in seen:
                seen[k] = (chunk, ev_adj)
                continue
            prev_chunk, prev_ev = seen[k]
            if longitudinal:
                prev_d = prev_chunk.visit_date
                cur_d = chunk.visit_date
                if (prev_d is None and cur_d is not None) or (
                    prev_d is not None and cur_d is not None and cur_d > prev_d
                ):
                    seen[k] = (chunk, ev_adj)
            else:
                if _rank(ev_adj) > _rank(prev_ev):
                    seen[k] = (chunk, ev_adj)
    return [e for _, e in seen.values()], (total, len(seen))


def _merge_scalar_field(
    field_name: str,
    per_chunk: list[tuple[Chunk, Evidence]],
    fallback_nd: Evidence,
) -> tuple[Evidence, list[dict], list[dict]]:
    """Return (winning_evidence, conflicts, trace).

    conflicts is a list of dicts describing loser Evidence entries whose
    concrete value differs from the winner (schema-safe: dicts, not
    Evidence). trace is a per-chunk record of what was seen for this field.
    """
    concrete: list[tuple[Chunk, Evidence]] = [
        (c, e) for c, e in per_chunk if e is not None and _is_concrete(e)
    ]
    trace: list[dict] = []
    for c, e in per_chunk:
        trace.append({
            "chunk_index": c.chunk_index,
            "visit_date": c.visit_date.isoformat() if c.visit_date else None,
            "certainty": e.certainty.value if e is not None else None,
            "value": _value_summary(e) if e is not None else None,
            "concrete": _is_concrete(e) if e is not None else False,
        })

    if not concrete:
        return fallback_nd, [], trace

    dated = [(c, e) for c, e in concrete if c.visit_date is not None]
    if dated:
        dated.sort(key=lambda t: t[0].visit_date)
        winner_chunk, winner = dated[-1]
    else:
        # Highest certainty wins; on ties, later chunk_index wins.
        concrete.sort(key=lambda t: (_rank(t[1]), t[0].chunk_index))
        winner_chunk, winner = concrete[-1]

    winner_adj = _adjust_offsets(winner, winner_chunk.char_offset)

    longitudinal = any(c.visit_date is not None for c, _ in per_chunk)
    winner_key = _dedup_key(winner_adj, longitudinal)
    conflicts: list[dict] = []
    for c, e in concrete:
        if (c, e) is (winner_chunk, winner):
            continue
        ea = _adjust_offsets(e, c.char_offset)
        if _dedup_key(ea, longitudinal) == winner_key:
            continue
        conflicts.append({
            "chunk_index": c.chunk_index,
            "visit_date": c.visit_date.isoformat() if c.visit_date else None,
            "certainty": ea.certainty.value,
            "value": _value_summary(ea),
            "evidence_text": ea.evidence_text,
        })

    for t in trace:
        t["won"] = (t["chunk_index"] == winner_chunk.chunk_index)
    return winner_adj, conflicts, trace


def _value_summary(ev: Evidence) -> Any:
    if ev.value is None:
        return None
    if hasattr(ev.value, "model_dump"):
        return ev.value.model_dump(mode="json")
    if hasattr(ev.value, "value"):        # enum
        return ev.value.value
    return ev.value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def merge_modules(
    module_cls: Type[BaseModel],
    per_chunk_outputs: list[tuple[Chunk, BaseModel | None]],
    *,
    fallback_source_doc_id: str = "MERGED",
    fallback_source_doc_type: Any = None,
    fallback_source_date: date | None = None,
) -> tuple[BaseModel | None, MergeReport]:
    """Merge per-chunk module outputs into a single module instance.

    Chunks whose module is None are skipped (extraction failed on that
    chunk). If every chunk failed, returns (None, report).

    For every scalar Evidence field where NO chunk provided a concrete
    assertion, a NOT_DOCUMENTED placeholder is synthesized using the
    fallback_source_* arguments so the resulting module still validates.
    """
    report = MergeReport(
        module_name=module_cls.__name__,
        n_chunks_total=len(per_chunk_outputs),
        n_chunks_contributed=sum(1 for _, m in per_chunk_outputs if m is not None),
    )

    if report.n_chunks_contributed == 0:
        return None, report

    contributed = [(c, m) for c, m in per_chunk_outputs if m is not None]

    merged_fields: dict[str, Any] = {}

    for fname, finfo in module_cls.model_fields.items():
        kind = _classify_field(finfo.annotation)

        if kind == "list_evidence":
            per_chunk_lists = [(c, getattr(m, fname) or []) for c, m in contributed]
            merged, (raw, dedup) = _merge_list_field(per_chunk_lists)
            merged_fields[fname] = merged
            report.list_field_dedup_counts[fname] = (raw, dedup)

        elif kind == "evidence":
            per_chunk_evs = [(c, getattr(m, fname)) for c, m in contributed]
            # Any Evidence carries source_doc_id/type/date, so pick a
            # NOT_DOCUMENTED fallback from the first available Evidence.
            sample = next((e for _, e in per_chunk_evs if e is not None), None)
            if sample is not None:
                fallback = Evidence.not_documented(
                    source_doc_id=sample.source_doc_id,
                    source_doc_type=sample.source_doc_type,
                    source_date=sample.source_date,
                )
            elif (fallback_source_doc_type is not None
                  and fallback_source_date is not None):
                fallback = Evidence.not_documented(
                    source_doc_id=fallback_source_doc_id,
                    source_doc_type=fallback_source_doc_type,
                    source_date=fallback_source_date,
                )
            else:
                raise ValueError(
                    f"Cannot synthesize NOT_DOCUMENTED fallback for '{fname}': "
                    "no chunk contributed an Evidence with source_* metadata "
                    "and no fallback_source_* provided."
                )
            winner, conflicts, trace = _merge_scalar_field(fname, per_chunk_evs, fallback)
            merged_fields[fname] = winner
            report.field_trace[fname] = trace
            if conflicts:
                report.field_conflicts[fname] = conflicts

        else:
            # Non-Evidence field — take the value from the first chunk that
            # produced this module (they should be constants like
            # `schema_version` in the top-level record; module classes here
            # only carry Evidence-wrapped fields).
            merged_fields[fname] = getattr(contributed[0][1], fname)

    try:
        merged = module_cls.model_validate(merged_fields)
    except ValidationError as e:
        # Surface merge failures — this indicates a bug in merge semantics
        # or a schema-level cross-field validator that the merged view
        # violates (e.g. MriModule's HS-boolean-vs-findings-list guard).
        report.field_conflicts["__merge_validation__"] = [{"error": str(e)[:2000]}]
        return None, report

    return merged, report


# ---------------------------------------------------------------------------
# Smoke test — synthetic MedicationModule across 3 visits
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    from datetime import date as _d
    from schema import (
        DocumentMetadata, DocumentType, MedicationModule, Medication,
        Certainty as _Cert, TemporalStatus,
    )
    from schema.enums import DrugResistanceStatus, MedicationStatus

    doc = DocumentMetadata(
        doc_id="TEST", doc_type=DocumentType.PROGRESS_NOTE,
        doc_date=_d(2024, 1, 1), patient_id="P1",
    )
    src = {"source_doc_id": "TEST", "source_doc_type": DocumentType.PROGRESS_NOTE, "source_date": _d(2024, 1, 1)}

    def ev(value, evidence_text, certainty=_Cert.DEFINITE):
        return Evidence(value=value, certainty=certainty, temporal_status=TemporalStatus.CURRENT,
                        evidence_text=evidence_text, **src)

    def med(name, status, evidence_text):
        return ev(Medication(generic_name=name, status=status), evidence_text)

    # Visit 1: on LTG
    m1 = MedicationModule(
        current_asms=[med("lamotrigine", MedicationStatus.CURRENT, "on lamotrigine 25mg BID")],
        prior_asms=[], failed_asms=[],
        adverse_effects_text=Evidence.not_documented(**src),
        drug_resistance_status=Evidence.not_documented(**src),
        surgery_history=[], non_drug_therapies=[],
    )
    # Visit 2: added LEV; DR still not documented
    m2 = MedicationModule(
        current_asms=[
            med("lamotrigine", MedicationStatus.CURRENT, "continues lamotrigine 75mg BID"),
            med("levetiracetam", MedicationStatus.CURRENT, "added levetiracetam 500mg BID"),
        ],
        prior_asms=[], failed_asms=[],
        adverse_effects_text=Evidence.not_documented(**src),
        drug_resistance_status=Evidence.not_documented(**src),
        surgery_history=[], non_drug_therapies=[],
    )
    # Visit 3: drug-resistant confirmed
    m3 = MedicationModule(
        current_asms=[
            med("lamotrigine", MedicationStatus.CURRENT, "lamotrigine 75mg BID"),
            med("levetiracetam", MedicationStatus.CURRENT, "levetiracetam 1000mg BID"),
        ],
        prior_asms=[], failed_asms=[],
        adverse_effects_text=Evidence.not_documented(**src),
        drug_resistance_status=ev(DrugResistanceStatus.DRUG_RESISTANT,
                                   "meets ILAE drug-resistance criteria"),
        surgery_history=[], non_drug_therapies=[],
    )

    chunks_and_mods = [
        (Chunk(text="v1", chunk_index=0, visit_date=_d(2023, 3, 1)), m1),
        (Chunk(text="v2", chunk_index=1, visit_date=_d(2023, 9, 15)), m2),
        (Chunk(text="v3", chunk_index=2, visit_date=_d(2024, 6, 1)), m3),
    ]

    merged, report = merge_modules(MedicationModule, chunks_and_mods)
    print("merged.current_asms unique:", len(merged.current_asms))
    for e in merged.current_asms:
        print(f"  - {e.value.generic_name}  «{e.evidence_text[:60]}»")
    print("drug_resistance:", merged.drug_resistance_status.value,
          "via evidence:", merged.drug_resistance_status.evidence_text)
    print("dedup counts:", report.list_field_dedup_counts)
    print("conflicts:", report.field_conflicts)
    print("chunks contributed:", report.n_chunks_contributed, "/", report.n_chunks_total)
