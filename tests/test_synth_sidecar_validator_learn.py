"""CPU extract on a v4_ext synthetic slice: all shipped sidecars, Validator store, leo learn.

Does not touch data/leo_runs/ headline files. GPU / extra readers off.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

NOTES = REPO / "data" / "leo_runs" / "v4ext_notes.csv"
SHIPPED = (
    "ctakes", "freq", "stated-type", "hs",
    "fail-reason", "rescue-if", "ictal", "eeg-done", "dre", "first-feature",
)


@pytest.mark.skipif(not NOTES.is_file(), reason="v4ext_notes.csv not on disk")
def test_v4ext_slice_sidecars_then_validator_then_learn(tmp_path):
    pytest.importorskip("medcat")
    from services.ext_detectors import KNOWN_EXT_DETECTORS, parse_ext_detectors
    from services.leo_catalog import resolve_phenotypes
    from services.leo_runtime import LeoRuntime
    from services import leo_batch as lb
    from services import leo_review as lr
    from services import leo_learn as ll

    assert parse_ext_detectors(",".join(SHIPPED)) == SHIPPED
    assert KNOWN_EXT_DETECTORS == SHIPPED
    with pytest.raises(ValueError, match="trained|not registered|catalogue"):
        parse_ext_detectors("b1,xie,decker,engel,ner-onset")

    src = pd.read_csv(NOTES, dtype=str, keep_default_na=False, encoding="utf-8-sig", nrows=3)
    assert len(src) == 3 and src["text"].str.len().min() > 50

    rt = LeoRuntime.load(mode="cpu", ext_detectors=SHIPPED)
    phen = resolve_phenotypes(["core", "medication", "eeg", "mri"])
    table, claims, prov = lb.run_table(
        src, rt, phenotypes=phen, asks=[], text_col="text", id_col="note_id",
        date_col="visit_date", include_review=True,
    )
    assert prov.get("mode") == "specialist_only"
    assert list(prov.get("ext_detectors") or []) == list(SHIPPED)
    assert (table["leo_status"] == "ok").all()
    # Sidecars never mint ACCEPT (may be sidecar_only REVIEW, or a sidecar_alternative on an E cell)
    if "reason_codes" in claims.columns and "verdict" in claims.columns:
        so = claims["reason_codes"].astype(str).str.contains("sidecar_only", regex=False)
        if so.any():
            assert claims.loc[so, "verdict"].str.lower().ne("accept").all()

    det_col = "detectors" if "detectors" in claims.columns else ""
    side_hit = False
    if det_col:
        blob = claims[det_col].astype(str)
        side_hit = any(n in " ".join(blob) for n in SHIPPED)
    if "reason_codes" in claims.columns:
        side_hit = side_hit or claims["reason_codes"].astype(str).str.contains("sidecar").any()
    if "sidecar_alternative" in claims.columns:
        side_hit = side_hit or claims["sidecar_alternative"].astype(str).str.strip().ne("").any()
    sidecar_cols = [c for c in table.columns if c.endswith("_sidecar")]
    if sidecar_cols:
        side_hit = side_hit or any(table[c].astype(str).str.strip().ne("").any() for c in sidecar_cols)
    assert side_hit, "shipped sidecars produced no detector/sidecar signal on these three notes"

    out = tmp_path / "v4ext_slice_leo.csv"
    table.to_csv(out, index=False, encoding="utf-8-sig")
    fields = lr.infer_fields(table)
    store = lr.ReviewStore(tmp_path / "v4ext_slice.reviews.jsonl", tmp_path / "v4ext_slice.reviewed.csv")
    flagged = lr.items(table, fields, {}, "flagged")
    audit = lr.items(table, fields, {}, "accepted_audit", audit_seed="v4ext-slice")
    misses = lr.items(table, fields, {}, "misses")
    assert flagged, "CPU extract should flag every found value"
    assert all(it["status"] == "accepted" for it in audit)
    events = []
    # Accept / Correct / Deny / Add on real synthetic cells
    events.append(lr.make_event(flagged[0], "accept", "", "synth-test", "quote supports", "leo-v0.5"))
    need_why = next((it for it in flagged[1:] if it["field"] != flagged[0]["field"] or it["row"] != flagged[0]["row"]),
                    flagged[min(1, len(flagged) - 1)])
    kw = {"why_tag": "wrong_value"}
    if need_why.get("alternative"):
        kw["reader_preferred"] = "rules"
    events.append(lr.make_event(need_why, "reject", "", "synth-test", "not supported", "leo-v0.5", **kw))
    if misses:
        events.append(lr.make_event(misses[0], "add", "focal", "synth-test", "stated in note", "leo-v0.5"))
    store.add(events)
    md, learned = ll.run([store.csv], min_n=100)
    assert learned["applied"] is False
    assert learned["n_rows"] == len(events)
    assert learned["policy"] == {}
    assert "Loop C" in md or "paused" in md.lower()
    orig = pd.read_csv(out, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert orig["leo_doc_id"].tolist() == table["leo_doc_id"].tolist()
    (tmp_path / "learn.md").write_text(md, encoding="utf-8")
    (tmp_path / "prov.json").write_text(json.dumps({k: prov[k] for k in prov if k != "notes"}, default=str), encoding="utf-8")
