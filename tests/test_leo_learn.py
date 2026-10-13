"""Loop A/B from validator files: labels only, CI gate, no extract learning, Loop C paused."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pandas as pd
import pytest

from services import leo_learn as ll
from services import leo_review as lr


def _row(**kw):
    rec = {c: "" for c in lr.REVIEWED_COLUMNS}
    rec.update(kw)
    return rec


def _csv(tmp_path: Path, rows: list[dict], name: str = "x.reviewed.csv") -> Path:
    p = tmp_path / name
    pd.DataFrame(rows, columns=lr.REVIEWED_COLUMNS).to_csv(p, index=False, encoding="utf-8-sig")
    return p


def test_claim_path_maps_phenotype_id_to_fusion_path():
    assert ll.claim_path("seizure_type") == "clinical_seizure.predominant_seizure_type"
    assert ll.claim_path("epilepsy_type") == "clinical_seizure.epilepsy_type"


def test_loop_a_emits_policy_only_when_ci_gate_met(tmp_path):
    rows = [_row(field="seizure_type", decision="correct", why_tag="wrong_reader",
                 reader_preferred="model", proposed_status="needs_review")
            for _ in range(12)]
    p = _csv(tmp_path, rows)
    md, res = ll.run([p], min_n=10, loops="a")
    assert res["applied"] is False
    assert res["policy"].get("clinical_seizure.predominant_seizure_type") == "llm"
    assert "show model" in md
    empty, res100 = ll.run([p], min_n=100, loops="a")
    assert res100["policy"] == {}
    assert "n below gate" in empty


def test_loop_b_splits_audit_from_flagged_and_does_not_apply(tmp_path):
    rows = [
        _row(field="epilepsy_type", decision="accept", proposed_status="accepted",
             quote_ok="yes"),
        _row(field="epilepsy_type", decision="reject", proposed_status="accepted",
             why_tag="quote_does_not_support", quote_ok="no"),
        _row(field="epilepsy_type", decision="correct", proposed_status="needs_review",
             why_tag="wrong_value", reader_preferred="rules"),
    ]
    for _ in range(5):
        rows.append(_row(field="current_asms", decision="reject",
                         proposed_status="needs_review", why_tag="wrong_status"))
    for _ in range(5):
        rows.append(_row(field="seizure_type", decision="reject",
                         proposed_status="needs_review", why_tag="quote_does_not_support",
                         quote_ok="no"))
    p = _csv(tmp_path, rows)
    md, res = ll.run([p], min_n=100, loops="b")
    b = res["loop_b"]
    assert b["audit"]["n"] == 2 and b["flagged"]["n"] == 11
    assert b["audit"]["changed"] == 1
    assert any("quote-entail" in r or "quote_does_not_support" in r for r in b["recommendations"])
    assert any("wrong_status" in r for r in b["recommendations"])
    assert any("not applied" in r.lower() or "not change" in md.lower() for r in b["recommendations"])
    assert res["applied"] is False
    assert "Flagged-only rates are biased" in md


def test_loop_c_is_paused():
    with pytest.raises(ValueError, match="paused"):
        ll.run([], loops="c")


def test_cli_learn_writes_empty_policy_and_refuses_apply(tmp_path, capsys):
    from scripts import leo_cli
    p = _csv(tmp_path, [_row(field="epilepsy_type", decision="accept",
                             proposed_status="accepted", quote_ok="yes")])
    dest = tmp_path / "policy.json"
    assert leo_cli.main(["learn", str(p), "--emit-policy", str(dest)]) == 0
    out = capsys.readouterr().out
    assert "extract unchanged" in out or "Does not change D17" in out
    assert json.loads(dest.read_text()) == {}
    with pytest.raises(SystemExit, match="does not change extract"):
        leo_cli.main(["learn", str(p), "--apply"])
    with pytest.raises(SystemExit, match="paused"):
        leo_cli.main(["learn", str(p), "--lora"])


def test_archive_flag_reads_permitted_copy(tmp_path, monkeypatch):
    from scripts import leo_cli
    monkeypatch.setenv("MEDAI_LEO_TRAINING_DIR", str(tmp_path / "leo_training"))
    job = tmp_path / "leo_training" / ("a" * 32)
    job.mkdir(parents=True)
    rows = [_row(field="seizure_type", decision="accept", reader_preferred="rules",
                 proposed_status="needs_review")]
    pd.DataFrame(rows, columns=lr.REVIEWED_COLUMNS).to_csv(job / "reviewed.csv", index=False)
    (job / "consent.json").write_text('{"permitted": true}', encoding="utf-8")
    md, res = ll.run(ll.archive_reviewed_paths(), min_n=100, loops="a")
    assert res["n_rows"] == 1
    assert leo_cli.main(["learn", "--archive", "--loop", "a"]) == 0


def test_validator_store_clicks_then_learn(tmp_path):
    """Accept / Correct / Deny on the same store the Validator writes, then leo learn."""
    t = pd.DataFrame({
        "note_id": ["n1", "n2", "n3"], "leo_doc_id": ["n1", "n2", "n3"], "leo_status": ["ok"] * 3,
        "epilepsy_type": ["focal", "generalized", ""],
        "epilepsy_type_status": ["accepted", "needs_review", "not_found"],
        "epilepsy_type_evidence": ["focal epilepsy", "GTC", ""],
        "epilepsy_type_why": ["", "source_disagreement", ""],
        "epilepsy_type_source": ["llm+specialist", "specialist", ""],
        "epilepsy_type_alternative": ["", "focal", ""],
        "age_at_onset": ["11", "12", ""],
        "age_at_onset_status": ["needs_review", "accepted", "not_found"],
        "age_at_onset_evidence": ["age 11", "age 12", ""],
        "age_at_onset_why": ["llm_only", "", ""],
        "age_at_onset_source": ["llm", "llm+specialist", ""],
    })
    fields = lr.infer_fields(t)
    store = lr.ReviewStore(tmp_path / "x.reviews.jsonl", tmp_path / "x.reviewed.csv")
    epi, age = fields
    events = [
        lr.make_event(lr.proposal(t, epi, 1), "accept", "", "jd", "quote supports", "leo-v0.5"),
        lr.make_event(lr.proposal(t, epi, 2), "reject", "", "jd", "not in the note", "leo-v0.5",
                      why_tag="quote_does_not_support", reader_preferred="rules"),
        lr.make_event(lr.proposal(t, age, 1), "correct", "12", "jd", "age 12", "leo-v0.5",
                      why_tag="wrong_value"),
        lr.make_event(lr.proposal(t, epi, 3), "add", "focal", "jd", "focal epilepsy", "leo-v0.5"),
    ]
    store.add(events)
    latest = store.latest()
    assert set(latest) == {(1, "epilepsy_type"), (2, "epilepsy_type"), (1, "age_at_onset"), (3, "epilepsy_type")}
    flagged = lr.items(t, fields, latest, "flagged")
    assert any(it["decision"] == "reject" and it["why_tag"] == "quote_does_not_support" for it in flagged)
    audit = lr.items(t, fields, latest, "accepted_audit", audit_seed="test")
    assert all(it["status"] == "accepted" for it in audit)
    md, res = ll.run([store.csv], min_n=100)
    assert res["applied"] is False and res["n_rows"] == 4
    assert res["loop_a"]["scores"]["epilepsy_type"]["rules"] == 1
    assert res["loop_b"]["fields"]["epilepsy_type"]["reject"] == 1
    assert res["loop_b"]["fields"]["epilepsy_type"]["add"] == 1
    assert res["loop_b"]["audit"]["n"] == 1 and res["loop_b"]["audit"]["kept"] == 1
    assert res["policy"] == {}
    from scripts import leo_cli
    dest = tmp_path / "from_validator.policy.json"
    assert leo_cli.main(["learn", str(store.csv), "--emit-policy", str(dest)]) == 0
    assert json.loads(dest.read_text()) == {}


def test_extract_does_not_import_learn():
    import services.chain_pipeline as cp
    import services.leo_batch as lb
    assert "leo_learn" not in inspect.getsource(cp)
    assert "leo_learn" not in inspect.getsource(lb)
