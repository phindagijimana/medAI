"""LEO in the app: catalogue, chunking, ask, spreadsheet in/out, routes.  No GPU: the model is a fake."""

from __future__ import annotations

import io
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

NOTE = ("Dear Dr Smith,\n\nHistory of Present Illness\n\nThe patient has focal epilepsy with seizures beginning at age 11. "
        "Current seizure frequency is about two seizures per month.\n\nMedications\n\n"
        "The patient takes lamotrigine 200 mg twice daily and lacosamide 100 mg twice daily. "
        "In the past valproate was stopped because of tremor.\n\nAssessment\n\nFocal epilepsy, continue current medicines.")


class FakeBackend:
    """Stands in for Med42Backend: returns canned JSON; records prompts."""
    model_name = "fake-med42"

    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def generate_constrained(self, prompt, model, decoding):
        self.prompts.append(prompt)
        r = self.reply(prompt) if callable(self.reply) else self.reply
        return (r if isinstance(r, str) else json.dumps(r)), 10

    generate = generate_constrained


FLAT_OK = {
    "epilepsy_type": {"value": "focal", "quote": "focal epilepsy"},
    "predominant_seizure_type": {"value": None, "quote": None},
    "age_at_onset_years": {"value": 11, "quote": "beginning at age 11"},
    "seizure_frequency": {"count_min": 2, "count_max": 2, "period": "month", "seizure_free": False,
                          "quote": "two seizures per month"},
    "current_asms": [{"name": "lamotrigine", "dose": "200 mg twice daily", "quote": "lamotrigine 200 mg twice daily"},
                     {"name": "lacosamide", "dose": None, "quote": "lacosamide 100 mg twice daily"}],
}


# ---- catalogue -------------------------------------------------------------

def test_panels_and_unknown_names():
    from services.leo_catalog import resolve_phenotypes
    core = [p.id for p in resolve_phenotypes(None)]
    assert core == ["epilepsy_type", "seizure_type", "age_at_onset", "seizure_frequency", "current_asms"]
    assert "rescue_medication" in [p.id for p in resolve_phenotypes(["core", "rescue_medication"])]
    assert len(resolve_phenotypes("all")) > len(core)
    with pytest.raises(KeyError):
        resolve_phenotypes(["epilepsy_typo"])


def test_evidence_levels_match_what_was_measured():
    from services.leo_catalog import EXTRACT, REFERENCES
    from services.leo_evidence import FIELD_MAP
    measured = [p.id for p in EXTRACT if p.evidence == "measured"]
    assert measured == ["epilepsy_type", "seizure_type", "age_at_onset", "seizure_frequency", "current_asms"]
    assert set(FIELD_MAP) == set(measured)                   # a "measured" label needs numbers behind it, and vice versa
    assert {p.id for p in EXTRACT if p.evidence == "indirect"} == {"acute_administration"}
    assert all(p.evidence in ("measured", "rules_only", "indirect", "none") for p in EXTRACT)
    assert {p.id for p in EXTRACT if p.evidence == "rules_only"} == {
        "etiology_category", "drug_resistance", "mri_findings", "mri_normal", "hippocampal_sclerosis",
        "focal_cortical_dysplasia", "surgery_history", "rescue_medication", "prior_asms", "failed_asms",
        "etiology_details", "eeg_background", "semiology", "focal_motor_onset", "focal_nonmotor_onset",
        "eeg_study_type", "eeg_ictal_onset"}
    assert all(r in REFERENCES for p in EXTRACT for r in p.refs)
    assert next(p for p in EXTRACT if p.id == "drug_resistance").derived


def test_custom_question_validation():
    from services.leo_catalog import custom_ask
    assert custom_ask("Which side?", "choice", ("left", "right")).id.startswith("ask_")
    with pytest.raises(ValueError):
        custom_ask("", "text")
    with pytest.raises(ValueError):
        custom_ask("x?", "choice", ("only",))


# ---- LLM channel: flat reasoner, chunking, merge --------------------------------

def test_flat_reasoner_parses_constrained_answer():
    from services.chain_llm import FlatLiveReasoner
    r = FlatLiveReasoner(FakeBackend(FLAT_OK), arm="L1C")
    out = r(NOTE, "d1", "2026-01-01")
    assert out["clinical_seizure"]["epilepsy_type"]["value"] == "focal"
    assert [e["value"]["generic_name"] for e in out["medication"]["current_asms"]] == ["lamotrigine", "lacosamide"]
    with pytest.raises(ValueError):
        FlatLiveReasoner(FakeBackend({}), arm="L2C")


def test_merge_scalars_by_majority_and_drugs_by_union():
    from services.chain_llm import merge_chunk_phenotypes as m
    ev = lambda v, q="q": {"value": v, "evidence_text": q}
    a = {"clinical_seizure": {"epilepsy_type": ev("focal")}, "medication": {"current_asms": [ev({"generic_name": "lamotrigine"})]}}
    b = {"clinical_seizure": {"epilepsy_type": ev("generalized")}, "medication": {"current_asms": [ev({"generic_name": "Lamotrigine"}), ev({"generic_name": "lacosamide"})]}}
    c = {"clinical_seizure": {"epilepsy_type": ev("generalized")}}
    out = m([a, b, c, None])
    assert out["clinical_seizure"]["epilepsy_type"]["value"] == "generalized"
    assert [e["value"]["generic_name"] for e in out["medication"]["current_asms"]] == ["lamotrigine", "lacosamide"]
    assert m([None, None]) is None


def test_chunked_reasoner_passes_short_notes_through_and_splits_long_ones():
    from services.chain_llm import ChunkedReasoner
    calls = []

    def inner(text, doc, date):
        calls.append((len(text), doc))
        return {"clinical_seizure": {"epilepsy_type": {"value": "focal", "evidence_text": "focal"}}}

    r = ChunkedReasoner(inner, max_chars=600, overlap_chars=50)
    r(NOTE, "d", "2026-01-01")
    assert len(calls) == 1 and r.last_n_chunks == 1
    long_note = "\n\n".join([NOTE] * 6)
    calls.clear()
    out = r(long_note, "d", "2026-01-01")
    assert len(calls) > 1 and r.last_n_chunks == len(calls)
    assert all(n <= 700 for n, _ in calls)
    assert out["clinical_seizure"]["epilepsy_type"]["value"] == "focal"


# ---- ask ---------------------------------------------------------------

def test_ask_checks_the_quote_against_the_note():
    from services.leo_ask import Asker
    from services.leo_catalog import ask_template, custom_ask
    good = Asker(FakeBackend({"answer": "yes", "quote": "valproate was stopped because of tremor"}))
    r = good.ask(NOTE, ask_template("aura"))
    assert (r.status, r.reason) == ("needs_review", "llm_only")       # LLM-only: never accepted
    assert NOTE[r.char_start:r.char_end] == r.quote
    bad = Asker(FakeBackend({"answer": "yes", "quote": "she has frequent auras"})).ask(NOTE, ask_template("aura"))
    assert (bad.status, bad.reason) == ("rejected", "offsets_unresolved")
    none = Asker(FakeBackend({"answer": "not_documented", "quote": None})).ask(NOTE, ask_template("aura"))
    assert none.status == "not_documented"
    free = Asker(FakeBackend({"answer": "tremor", "quote": "stopped because of tremor"})).ask(
        NOTE, custom_ask("Why was valproate stopped?", "text"))
    assert free.answer == "tremor" and free.status == "needs_review"


def test_ask_long_note_takes_the_majority_answer():
    from services.leo_ask import Asker
    from services.leo_catalog import ask_template
    first = [True]

    def reply(_prompt):
        if first[0]:
            first[0] = False
            return {"answer": "no", "quote": "continue current medicines"}
        return {"answer": "yes", "quote": "stopped because of tremor"}

    a = Asker(FakeBackend(reply), chunk_max_chars=500, overlap_chars=0)
    r = a.ask("\n\n".join([NOTE] * 4), ask_template("aura"))
    assert r.n_chunks >= 2 and r.answer == "yes"


def test_a_quote_about_other_drugs_does_not_support_an_answer_about_this_one():
    from services.leo_ask import Asker
    from services.leo_catalog import custom_ask
    q = custom_ask("Is the patient currently taking levetiracetam?", "yes_no", aid="lev")
    off = Asker(FakeBackend({"answer": "yes", "quote": "takes lamotrigine 200 mg twice daily"})).ask(NOTE, q)
    assert off.status == "rejected" and off.reason == "quote_off_topic" and off.answer == "yes"
    brand = Asker(FakeBackend({"answer": "yes", "quote": "continues Keppra 500 mg"})).ask(
        NOTE + " continues Keppra 500 mg", q)
    assert brand.status == "needs_review"                      # brand name of the asked drug
    ok = Asker(FakeBackend({"answer": "yes", "quote": "takes lamotrigine 200 mg twice daily"})).ask(
        NOTE, custom_ask("Is the patient currently taking lamotrigine?", "yes_no", aid="lam"))
    assert ok.status == "needs_review"
    other = Asker(FakeBackend({"answer": "yes", "quote": "focal epilepsy"})).ask(
        NOTE, custom_ask("Does the patient have focal epilepsy?", "yes_no", aid="x"))
    assert other.status == "needs_review"                      # no drug named: no topic check


# ---- the whole path: pipeline + fake LLM -> table ------------------------------

@pytest.fixture(scope="module")
def runtimes():
    from services.leo_runtime import LeoRuntime
    llm = LeoRuntime(backend=FakeBackend(FLAT_OK))
    cpu = LeoRuntime(backend=None, use_llm=False)
    cpu.pipeline._lazy_init()
    p = llm.pipeline                      # share the MedCAT objects: load once
    p._extractor, p._assembler = cpu.pipeline._extractor, cpu.pipeline._assembler
    p._candidate_service, p._lazy_init_done = cpu.pipeline._candidate_service, True
    return llm, cpu


def test_note_to_row_with_llm_and_specialist(runtimes):
    from services.leo_catalog import resolve_phenotypes
    llm, _ = runtimes
    res = llm.extract_note(NOTE, doc_id="n1", phenotypes=resolve_phenotypes(["core"]))
    assert not res.error and res.llm_used
    row = res.row
    assert row["epilepsy_type"] == "focal" and "llm" in row["epilepsy_type_source"]
    assert row["age_at_onset"] == "11"
    assert row["seizure_frequency"] == "2 per month" and row["seizure_frequency_period"] == "month"
    assert set(row["current_asms"].split("; ")) >= {"lamotrigine", "lacosamide"}
    assert "valproate" not in row["current_asms"]          # the stopped drug stays out of the current list
    assert row["current_asms_status"] in ("accepted", "needs_review")
    assert all(k in res.claims[0] for k in ("field_path", "verdict", "evidence", "char_start"))


def test_specialist_only_says_so(runtimes):
    _, cpu = runtimes
    assert cpu.mode == "specialist_only" and cpu.versions()["llm_arm"] == ""
    res = cpu.extract_note(NOTE, doc_id="n2")
    assert not res.llm_used and res.row["epilepsy_type"] == "focal"
    # one reader: nothing is cross-checked, so nothing may be "accepted"
    from services.leo_catalog import resolve_phenotypes
    phen = resolve_phenotypes(["core"])
    statuses = {res.row[f"{p.id}_status"] for p in phen}
    assert "accepted" not in statuses and "needs_review" in statuses
    assert "no_second_reader" in res.row["epilepsy_type_why"]
    assert res.n_accepted == 0 and {c["verdict"] for c in res.claims} <= {"review", "reject"}
    assert any("no_second_reader" in c["reason_codes"] for c in res.claims)      # the downgraded ones say why
    blank = cpu.extract_note(NOTE, doc_id="n3", include_review=False)
    assert blank.row["epilepsy_type"] == ""                 # accepted-only table is empty without a second reader


def test_spreadsheet_roundtrip_csv_and_xlsx(runtimes, tmp_path):
    from services import leo_batch as lb
    from services.leo_catalog import resolve_phenotypes
    llm, _ = runtimes
    src = pd.DataFrame({"mrn": ["a", "b"], "note_date": ["2026-01-02", "bad-date"], "note_text": [NOTE, ""],
                        "keep_me": ["x", "y"], "epilepsy_type": ["pre-existing", "pre-existing"]})
    p = tmp_path / "in.csv"
    src.to_csv(p, index=False)
    df = lb.read_table(p)
    cols = lb.detect_columns(df)
    assert cols == {"text": "note_text", "id": "", "date": "note_date"}
    phen = resolve_phenotypes(["core"])
    table, claims, prov = lb.run_table(df, llm, phenotypes=phen, asks=[], text_col=cols["text"], date_col=cols["date"])
    assert list(table.columns[:5]) == list(src.columns)                      # input columns first, untouched
    assert table["keep_me"].tolist() == ["x", "y"] and table["epilepsy_type"][0] == "pre-existing"
    assert "epilepsy_type_leo" in table.columns                              # no clobbering of the user's column
    assert table["leo_status"].tolist() == ["ok", "error: empty note"]       # a bad row does not stop the run
    assert prov["rows_processed"] == 2 and prov["rows_error"] == 1 and prov["mode"] == "llm+specialist"
    assert prov["phenotypes_not_measured"] == []
    out = lb.write_outputs(table, claims, prov, tmp_path / "res.csv", "csv", phen)
    assert [x.name for x in out] == ["res.csv", "res.claims.csv", "res.provenance.json"]
    back = pd.read_csv(out[0], dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert back.shape == table.shape
    assert NOTE[:40] not in open(out[2]).read()                              # provenance carries no note text
    xl = lb.write_outputs(table, claims, prov, tmp_path / "res.xlsx", "xlsx", phen)
    sheets = pd.read_excel(xl[0], sheet_name=None, dtype=str)
    assert set(sheets) == {"LEO", "Claims", "About"} and len(sheets["LEO"]) == 2


def test_ambiguous_text_column_stops_instead_of_guessing():
    from services import leo_batch as lb
    df = pd.DataFrame({"a": ["x"], "b": ["y"]})
    with pytest.raises(ValueError, match="Pass --text-col"):
        lb.detect_columns(df)
    assert lb.detect_columns(df, text_col="b")["text"] == "b"


def test_formula_like_evidence_is_neutralised():
    from services.leo_tabular import _safe
    assert _safe("=HYPERLINK(1)").startswith("'") and _safe("+1") == "'+1" and _safe("ok") == "ok"


def test_read_table_formats(tmp_path):
    from services import leo_batch as lb
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "a.txt").write_text("note a")
    (tmp_path / "d" / "b.txt").write_text("note b")
    assert lb.read_table(tmp_path / "d")["note_id"].tolist() == ["a.txt", "b.txt"]
    (tmp_path / "x.jsonl").write_text('{"id": "1", "text": "t1"}\n{"id": "2", "text": "t2"}\n')
    assert lb.read_table(tmp_path / "x.jsonl")["text"].tolist() == ["t1", "t2"]
    with pytest.raises(ValueError):
        lb.read_table(tmp_path / "x.pdf")


# ---- routes ---------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path, monkeypatch, runtimes):
    monkeypatch.setenv("MEDAI_LOAD_MED42", "0")
    monkeypatch.setenv("APP_HOME", str(tmp_path))
    pytest.importorskip("flask_cors")
    import app as appmod
    import routes.leo as leo
    llm, cpu = runtimes
    monkeypatch.setattr(leo, "_RUNTIMES", {"cpu:8000": cpu})
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client(), leo


def test_routes_catalogue_extract_and_batch(client, tmp_path):
    c, leo = client
    cat = c.get("/leo/phenotypes").get_json()
    assert {p["id"] for p in cat["extract"]} >= {"epilepsy_type", "current_asms"} and cat["ask_templates"]
    ev = c.get("/leo/evidence").get_json()
    assert [d["id"] for d in ev["datasets"]] == ["fs", "synth"] and all(d["available"] for d in ev["datasets"])
    assert set(ev["fields"]) == {"epilepsy_type", "seizure_type", "age_at_onset", "seizure_frequency", "current_asms"}
    assert c.get("/leo/ui").status_code == 200 and b"Epilepsy phenotype extraction" in c.get("/leo/ui").data
    g = c.get("/leo/guide")
    assert g.status_code == 302 and g.headers["Location"].endswith("docs/LEO_USER_GUIDE.md")
    r = c.post("/leo/extract", json={"source_text": NOTE, "phenotypes": ["core"], "llm": "off"})
    j = r.get_json()
    assert r.status_code == 200 and j["mode"] == "specialist_only" and j["row"]["epilepsy_type"] == "focal"
    assert c.post("/leo/extract", json={"source_text": NOTE, "phenotypes": ["nope"]}).status_code == 400
    assert c.post("/leo/extract", json={"source_text": ""}).status_code == 400
    # questions need a loaded model
    r = c.post("/leo/batch", data={"file": (io.BytesIO(b"text\nhello\n"), "n.csv"), "llm": "off",
                                   "questions": json.dumps([{"template": "aura"}])})
    assert r.status_code == 400
    csv = "note_id,text\nn1," + json.dumps(NOTE) + "\n"
    r = c.post("/leo/batch", data={"file": (io.BytesIO(csv.encode()), "notes.csv"), "llm": "off", "format": "csv"})
    assert r.status_code == 202
    jid = r.get_json()["job_id"]
    for _ in range(120):
        st = c.get(f"/leo/jobs/{jid}").get_json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert st["state"] == "done", st
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/leo/jobs/{jid}/download").data))
    assert sorted(z.namelist()) == ["notes_leo.claims.csv", "notes_leo.csv", "notes_leo.provenance.json"]
    res = pd.read_csv(z.open("notes_leo.csv"), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert res["epilepsy_type"][0] == "focal" and res["note_id"][0] == "n1"
    assert c.delete(f"/leo/jobs/{jid}").status_code == 200 and c.get(f"/leo/jobs/{jid}").status_code == 404
    assert not (Path(os.environ["APP_HOME"]) / "data" / "leo_jobs" / jid).exists()
    assert c.post("/leo/batch", data={"file": (io.BytesIO(b"x"), "evil.exe")}).status_code == 400


# ---- evidence: numbers must come from the result files, not from the code -----------------

def test_evidence_numbers_are_read_from_the_result_files():
    from services import leo_evidence as le
    ev = le.evidence()
    for d in ev["datasets"]:
        raw = json.loads((le.RESULTS / le.DATASETS[d["id"]]["file"]).read_text())
        src = raw["sources"][le.DATASETS[d["id"]]["source"]]
        assert d["arm"] == "L1C" and src["arm"] == "L1C"             # the shipped arm, not an arm that is not offered live
        assert d["systems"]["leo_review"]["micro_f1"] == round(src["systems"]["leo_review"]["micro_f1"], 3)
        assert d["text"] == "synthetic"
    fs = ev["fields"]["current_asms"][0]["fs"]["reviewed"]
    raw = json.loads((le.RESULTS / "leo_vs_fs_gold_v05_default.json").read_text())
    assert fs["f1"] == round(raw["sources"]["L1C"]["systems"]["leo_review"]["per_field"]["current_asms"]["f1"], 3)
    assert fs["n"] == 37
    assert any("synthetic" in c for c in ev["caveats"]) and any("No real clinical note" in c for c in ev["caveats"])


def test_evidence_reports_missing_files_instead_of_inventing(monkeypatch, tmp_path):
    from services import leo_evidence as le
    monkeypatch.setattr(le, "RESULTS", tmp_path)
    ev = le.evidence()
    assert not any(d["available"] for d in ev["datasets"])
    assert all(e[d] is None for es in ev["fields"].values() for e in es for d in ("fs", "synth"))


def test_shipped_configuration_is_the_scored_configuration():
    """Pilot default (D17): the rules' value is shown on a disagreement; the seizure-type policy is opt-in."""
    from services.leo_runtime import LeoRuntime, parse_disagree_llm
    assert LeoRuntime(backend=None, use_llm=False).disagree_llm == ()
    assert parse_disagree_llm(None) == () and parse_disagree_llm("none") == () and parse_disagree_llm("") == ()
    assert parse_disagree_llm("candidate") == ("clinical_seizure.predominant_seizure_type",)
    assert parse_disagree_llm("epilepsy_type") == ("clinical_seizure.epilepsy_type",)
    assert LeoRuntime(backend=None, use_llm=False, disagree_llm=()).disagree_llm == ()
    assert LeoRuntime(backend=None, use_llm=False).versions()["pipeline"] == "leo-v0.5"


# ---- review: decisions recorded, then merged into the result ---------------------------------------------

def _tiny_table():
    return pd.DataFrame({
        "note_id": ["n1", "n2", "n3"], "leo_doc_id": ["n1", "n2", "n3"], "leo_status": ["ok"] * 3,
        "epilepsy_type": ["focal", "generalized", ""], "epilepsy_type_status": ["accepted", "needs_review", "not_found"],
        "epilepsy_type_evidence": ["focal epilepsy", "GTC", ""], "epilepsy_type_why": ["", "llm_only", ""],
        "epilepsy_type_source": ["llm+specialist", "llm", ""],
        "age_at_onset": ["11", "=SUM(1)", ""], "age_at_onset_status": ["needs_review", "needs_review", "not_found"],
        "age_at_onset_evidence": ["age 11", "x", ""], "age_at_onset_why": ["llm_only", "llm_only", ""],
        "age_at_onset_source": ["llm", "llm", ""],
    })


def test_merge_keeps_leo_columns_and_labels_where_each_final_value_came_from():
    from services import leo_review as lr
    t = _tiny_table()
    fields = lr.infer_fields(t)
    assert [f.id for f in fields] == ["epilepsy_type", "age_at_onset"]
    latest = {(2, "epilepsy_type"): {"decision": "correct", "final_value": "=cmd|' /C calc'!A0", "reviewer": "r", "comment": ""},
              (1, "age_at_onset"): {"decision": "accept", "final_value": "", "reviewer": "r", "comment": ""},
              (2, "age_at_onset"): {"decision": "reject", "final_value": "", "reviewer": "r", "comment": ""}}
    m = lr.merge(t, fields, latest)
    assert list(m.columns).index("epilepsy_type_final") == list(m.columns).index("epilepsy_type_why") + 1
    for c in t.columns:                                              # LEO's own columns are untouched
        assert m[c].tolist() == t[c].tolist()
    assert m["epilepsy_type_review"].tolist() == ["auto_accepted", "corrected", ""]
    assert m["epilepsy_type_final"].tolist()[0] == "focal" and m["epilepsy_type_final"].tolist()[2] == ""
    assert m["epilepsy_type_final"][1].startswith("'=")              # a typed correction cannot run as a formula
    assert m["age_at_onset_review"].tolist() == ["accepted_by_reviewer", "rejected", ""]
    assert m["age_at_onset_final"].tolist() == ["11", "", ""]
    # nobody looked at a value that needed review: blank by default, LEO's value on request, both say "unreviewed"
    m2 = lr.merge(t, fields, {})
    assert m2["epilepsy_type_review"].tolist() == ["auto_accepted", "unreviewed", ""]
    assert m2["epilepsy_type_final"].tolist() == ["focal", "", ""]
    m3 = lr.merge(t, fields, {}, unreviewed="proposal")
    assert m3["epilepsy_type_final"].tolist() == ["focal", "generalized", ""] and m3["epilepsy_type_review"][1] == "unreviewed"
    with pytest.raises(ValueError):
        lr.merge(t, fields, {(1, "nope"): {"decision": "accept", "final_value": ""}})


def test_reviewed_csv_is_checked_against_the_table(tmp_path):
    from services import leo_review as lr
    t, hdr = _tiny_table(), ",".join(lr.REVIEWED_COLUMNS)
    pad = lambda *v: ",".join(v)
    def write(body):
        p = tmp_path / "r.csv"; p.write_text(hdr + "\n" + body + "\n", encoding="utf-8"); return p
    ok = lr.read_reviewed(write(pad("2", "n2", "epilepsy_type", "", "", "", "", "", "", "Correct ", "focal", "", "", "", "") + "\n" +
                                pad("1", "n1", "age_at_onset", "", "", "", "", "", "", "", "", "", "", "", "")), t)
    assert list(ok) == [(2, "epilepsy_type")] and ok[(2, "epilepsy_type")]["decision"] == "correct"      # blank decision = not yet decided
    for body, why in ((pad("2", "n9", "epilepsy_type", *[""] * 6, "accept", *[""] * 5), "doc_id"),
                      (pad("9", "n2", "epilepsy_type", *[""] * 6, "accept", *[""] * 5), "outside"),
                      (pad("2", "n2", "epilepsy_type", *[""] * 6, "maybe", *[""] * 5), "decision"),
                      (pad("2", "n2", "epilepsy_type", *[""] * 6, "correct", *[""] * 5), "needs final_value")):
        with pytest.raises(ValueError, match=why):
            lr.read_reviewed(write(body), t)


def _run_job(c, fmt="csv"):
    csv = "note_id,text\nn1," + json.dumps(NOTE) + "\nn2," + json.dumps(NOTE) + "\n"
    r = c.post("/leo/batch", data={"file": (io.BytesIO(csv.encode()), "notes.csv"), "llm": "off", "format": fmt,
                                   "phenotypes": "epilepsy_type,current_asms"})
    assert r.status_code == 202
    jid = r.get_json()["job_id"]
    for _ in range(120):
        st = c.get(f"/leo/jobs/{jid}").get_json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert st["state"] == "done", st
    return jid


def test_review_routes_save_decisions_and_export_merged(client):
    c, _ = client
    jid = _run_job(c)
    r = c.get(f"/leo/jobs/{jid}/review").get_json()
    # rules only: nothing was cross-checked, so every found value needs review
    assert r["counts"]["total"] == 4 and r["counts"]["reviewed"] == 0 and {i["status"] for i in r["items"]} == {"needs_review"}
    assert c.get(f"/leo/jobs/{jid}/review/export?kind=merged").status_code == 409             # nothing reviewed yet
    save = lambda **kw: c.post(f"/leo/jobs/{jid}/review", json={"reviewer": kw.pop("reviewer", "jd"), "decisions": [kw]})
    assert save(reviewer="", row=1, field="epilepsy_type", decision="accept").status_code == 400    # who reviewed it?
    assert save(row=1, field="nope", decision="accept").status_code == 400
    assert save(row=1, field="epilepsy_type", decision="correct", value="").status_code == 400
    assert save(row=1, field="epilepsy_type", decision="accept").status_code == 200
    assert save(row=2, field="epilepsy_type", decision="correct", value="generalized").status_code == 200
    assert save(row=1, field="current_asms", decision="reject", comment="was about a sibling").status_code == 200
    assert save(row=2, field="current_asms", decision="accept").status_code == 200
    assert save(row=2, field="current_asms", decision="undo").status_code == 200
    r = c.get(f"/leo/jobs/{jid}/review").get_json()
    assert r["counts"] == {"total": 4, "reviewed": 3, "accept": 1, "correct": 1, "reject": 1}
    jd = Path(os.environ["APP_HOME"]) / "data" / "leo_jobs" / jid
    log = [json.loads(x) for x in (jd / "notes_leo.reviews.jsonl").read_text().splitlines()]
    assert len(log) == 5 and log[0]["proposed_value"] == "focal" and log[0]["reviewer"] == "jd"        # history and the original proposal are kept
    dec = pd.read_csv(io.BytesIO(c.get(f"/leo/jobs/{jid}/review/export?kind=reviewed").data), dtype=str,
                      keep_default_na=False, encoding="utf-8-sig")
    assert len(dec) == 3 and set(dec["decision"]) == {"accept", "correct", "reject"} and dec["comment"].str.contains("sibling").any()
    m = pd.read_csv(io.BytesIO(c.get(f"/leo/jobs/{jid}/review/export?kind=merged").data), dtype=str,
                    keep_default_na=False, encoding="utf-8-sig")
    assert m["epilepsy_type_final"].tolist() == ["focal", "generalized"] and m["epilepsy_type_review"].tolist() == ["accepted_by_reviewer", "corrected"]
    assert m["current_asms_final"].tolist() == ["", ""] and m["current_asms_review"].tolist() == ["rejected", "unreviewed"]
    orig = pd.read_csv(jd / "notes_leo.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert orig["epilepsy_type"].tolist() == ["focal", "focal"] and "epilepsy_type_final" not in orig.columns   # LEO's file is not changed
    n = c.get(f"/leo/jobs/{jid}/note/2").get_json()
    assert "lamotrigine" in n["text"] and c.get(f"/leo/jobs/{jid}/note/9").status_code == 404
    assert c.get("/leo/jobs/nope/review").status_code == 404


def test_review_merge_into_the_excel_output_keeps_the_other_sheets(client):
    openpyxl = pytest.importorskip("openpyxl")
    c, _ = client
    jid = _run_job(c, "xlsx")
    assert c.post(f"/leo/jobs/{jid}/review", json={"reviewer": "jd", "decisions": [
        {"row": 1, "field": "epilepsy_type", "decision": "accept"}]}).status_code == 200
    r = c.get(f"/leo/jobs/{jid}/review/export?kind=merged&unreviewed=proposal")
    wb = openpyxl.load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames[0] == "LEO" and {"Claims", "About", "Reviews"} <= set(wb.sheetnames)
    head = [x.value for x in wb["LEO"][1]]
    assert "epilepsy_type_final" in head and "epilepsy_type_review" in head
    assert wb["Reviews"].max_row == 2


def test_cli_template_fill_and_merge_files(tmp_path):
    """The file route: leo review -> fill decision in a spreadsheet -> leo merge."""
    from services import leo_review as lr
    tp = tmp_path / "x_leo.csv"
    _tiny_table().to_csv(tp, index=False, encoding="utf-8-sig")
    tpl = lr.template(lr.load_table(tp), lr.infer_fields(lr.load_table(tp)))
    assert len(tpl) == 3 and (tpl["decision"] == "").all()                                       # only values that need review
    tpl.loc[tpl["field"] == "epilepsy_type", ["decision", "final_value"]] = ["correct", "focal"]
    rp = tmp_path / "x_leo.reviewed.csv"
    tpl.to_csv(rp, index=False, encoding="utf-8-sig")
    out = lr.merge_files(tp, rp)
    assert out.name == "x_leo.merged.csv"
    m = pd.read_csv(out, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert m["epilepsy_type_final"].tolist() == ["focal", "focal", ""] and m["epilepsy_type_review"][1] == "corrected"
    assert m["age_at_onset_review"].tolist() == ["unreviewed", "unreviewed", ""]


def test_job_folder_is_owner_only(tmp_path, monkeypatch):
    import stat
    from routes import leo as leo_routes
    monkeypatch.setenv("APP_HOME", str(tmp_path))
    root = leo_routes._jobs_root()
    assert stat.S_IMODE(root.stat().st_mode) == 0o700


def test_rollup_takes_the_latest_note_that_states_a_value_and_never_mixes_notes():
    from services.leo_rollup import rollup
    t = pd.DataFrame({
        "patient": ["a", "a", "a", "b"], "visit": ["2024-01-01", "2024-06-01", "2024-03-01", "2024-02-01"],
        "leo_doc_id": ["1", "2", "3", "4"],
        "epilepsy_type": ["focal", "", "generalized", "focal"],
        "epilepsy_type_status": ["accepted", "not_found", "needs_review", "needs_review"],
        "epilepsy_type_evidence": ["focal epilepsy", "", "GTC", "focal"], "epilepsy_type_why": ["", "", "llm_only", "no_second_reader"],
        "epilepsy_type_source": ["llm+specialist", "", "llm", "specialist"],
    })
    r = rollup(t, "patient", "visit").set_index("patient")
    assert r.loc["a", "epilepsy_type"] == "generalized"          # 2024-06 is silent; 2024-03 is the latest that states one
    assert r.loc["a", "epilepsy_type_from_row"] == 3 and r.loc["a", "epilepsy_type_from_date"] == "2024-03-01"
    assert r.loc["a", "epilepsy_type_status"] == "needs_review" and r.loc["a", "leo_notes"] == 3
    assert r.loc["b", "epilepsy_type_why"] == "no_second_reader"          # status and reason copied, never upgraded
    # without a date column the later row is the later note
    assert rollup(t, "patient").set_index("patient").loc["a", "epilepsy_type_from_row"] == 3
    with pytest.raises(ValueError):
        rollup(t, "nope")


# ---- model-vs-rules disagreements: blind export and scoring --------------------------------------------

def _claims_with_disagreements():
    return pd.DataFrame({
        "document_id": ["n1", "n1", "n2", "n3"], "row_index": ["1", "1", "2", "3"],
        "field_path": ["clinical_seizure.epilepsy_type", "clinical_seizure.age_at_onset_years",
                       "clinical_seizure.epilepsy_type", "clinical_seizure.epilepsy_type"],
        "value": ["focal", "5", "generalised", "focal"], "verdict": ["review"] * 4,
        "reason_codes": ["source_disagreement", "", "source_disagreement", "source_disagreement"],
        "alternative": ["generalised", "", "focal", "unknown"], "evidence": ["q1", "q2", "q3", "q4"]})


def test_disagreement_export_is_blind_and_reproducible():
    from services import leo_disagree as ld
    a = ld.export_cases(_claims_with_disagreements())
    b = ld.export_cases(_claims_with_disagreements())
    assert len(a) == 3 and list(a["case_id"]) == list(b["case_id"]) and list(a["key_A_is"]) == list(b["key_A_is"])
    for _, r in a.iterrows():                                  # A and B are the two readings, in a hidden order
        assert {r["reading_A"], r["reading_B"]} in ({"focal", "generalised"}, {"focal", "unknown"})
        assert r["truth"] == "" and r["key_A_is"] in ("shown", "other")
    with pytest.raises(ValueError):
        ld.export_cases(pd.DataFrame({"x": [1]}))


def test_disagreement_scoring_maps_blind_answers_back_to_the_readers():
    from services import leo_disagree as ld
    sheet = ld.export_cases(_claims_with_disagreements())
    # adjudicator always picks "focal" (the rules' value in n1 and n3, the other reader's in n2)
    truths = []
    for _, r in sheet.iterrows():
        truths.append("A" if r["reading_A"] == "focal" else "B")
    sheet["truth"] = truths
    res = ld.score_cases(sheet, "rules")["clinical_seizure.epilepsy_type"]
    assert res["rules"] == 2 and res["model"] == 1 and res["n_scored"] == 3
    assert res["rules_right"]["k"] == 2 and res["model_right"]["k"] == 1
    sheet.loc[0, "truth"] = "unclear"
    res = ld.score_cases(sheet, "rules")["clinical_seizure.epilepsy_type"]
    assert res["unclear"] == 1 and res["n_scored"] == 2
    sheet.loc[1, "truth"] = "C"
    with pytest.raises(ValueError):
        ld.score_cases(sheet, "rules")
    assert 0 <= ld.wilson(2, 3)[0] < ld.wilson(2, 3)[1] <= 1


# ─── job description (services.leo_job) ──────────────────────────────────────

def _job_df():
    import pandas as pd
    rows = []
    for s in range(1, 6):
        for n in range(1, 4):
            rows.append({"patient_id": f"P{s}", "note_id": f"P{s}_N{n}", "note_date": f"202{n}-0{s}-15",
                         "clinic": "Neurology" if s % 2 else "ED", "text": "He has focal seizures. Lamotrigine 100 mg."})
    return pd.DataFrame(rows)


def test_job_parses_the_example_request_and_selects_subjects_not_rows():
    from services import leo_job as j
    df = _job_df()
    spec = j.parse_request("give seizure types for the first 2 subjects", df)
    assert spec.phenotypes == ["seizure_type"] and spec.rows.mode == "first_subjects" and spec.rows.n == 2
    assert spec.columns["subject"] == "patient_id" and spec.columns["text"] == "text"
    assert j.validate(spec, df) == []
    sub, info = j.select_rows(df, spec)
    assert info["notes_selected"] == 6 and info["subjects_selected"] == 2           # all notes of the first 2 subjects
    assert set(sub["patient_id"]) == {"P1", "P2"} and len(df) == 15                  # input is not changed
    assert "6 notes from 2 subjects" in j.describe(spec, df)


def test_job_parser_handles_conditions_questions_and_output_and_reports_what_it_cannot_do():
    from services import leo_job as j
    df = _job_df()
    spec = j.parse_request('prior and failed medications and eeg for all patients after 2022 where clinic is Neurology, '
                           'as excel: "Does the patient drive?"', df)
    assert {"prior_asms", "failed_asms"} <= set(spec.phenotypes) and "eeg_study_type" in spec.phenotypes
    assert spec.output_format == "xlsx" and spec.questions[0]["answer_type"] == "yes_no"
    cols = {(c.column, c.op) for c in spec.rows.where}
    assert ("clinic", "eq") in cols and ("note_date", "gte") in cols
    sub, info = j.select_rows(df, spec)
    assert set(sub["clinic"]) == {"Neurology"} and set(sub["note_date"].str[:4]) <= {"2022", "2023"}
    # a request LEO cannot do is reported, not guessed
    none = j.parse_request("predict surgical outcome", df)
    assert none.phenotypes == [] and any("nothing" in p for p in j.validate(none, df))
    # an unknown column in a condition is dropped with a warning
    bad = j.parse_request("seizure type where payer is Medicaid", df)
    assert bad.rows.where == [] and any("payer" in w for w in bad.warnings)


def test_job_validation_and_json_round_trip_reject_bad_edits():
    import pytest
    from services import leo_job as j
    df = _job_df()
    spec = j.parse_request("seizure type for the first 3 subjects", df)
    again = j.spec_from_dict(json.loads(spec.to_json()))
    assert again.to_dict() == spec.to_dict()
    again.columns["subject"] = "nope"
    again.phenotypes.append("not_a_phenotype")
    again.rows.n = 0
    problems = " | ".join(j.validate(again, df))
    assert "nope" in problems and "not_a_phenotype" in problems and "at least 1" in problems
    with pytest.raises(ValueError):
        j.spec_from_dict({"rows": {"mode": "all", "shell": "rm -rf"}})
    with pytest.raises(ValueError):
        j.spec_from_dict({"run_this": "x"})
    no_subj = j.parse_request("seizure type for the first 3 subjects", df.drop(columns=["patient_id"]))
    assert any("subject column" in p for p in j.validate(no_subj, df.drop(columns=["patient_id"])))


def test_job_run_adds_columns_to_every_selected_note():
    from services import leo_job as j
    from services.leo_runtime import LeoRuntime
    df = _job_df()
    spec = j.parse_request("seizure type for the first 2 subjects", df)
    table, claims, prov = j.run_spec(spec, df, LeoRuntime(backend=None, use_llm=False))
    assert len(table) == 6 and "seizure_type" in " ".join(table.columns) and "clinic" in table.columns
    assert prov["job_spec"]["rows"]["n"] == 2 and prov["row_selection"]["notes_selected"] == 6


def test_routes_job_description_plan_edit_run_and_results_keep_the_job_file(client):
    c, leo = client
    rows = ["patient_id,note_id,text"] + [f"P{s},P{s}_{n},{json.dumps(NOTE)}" for s in range(1, 5) for n in (1, 2)]
    data = "\n".join(rows).encode()
    r = c.post("/leo/job/plan", data={"file": (io.BytesIO(data), "notes.csv"),
                                      "request": "give seizure types for the first 2 subjects"})
    plan = r.get_json()
    assert r.status_code == 200 and plan["spec"]["phenotypes"] == ["seizure_type"] and plan["problems"] == []
    assert plan["selection"]["notes_selected"] == 4 and "text" in plan["columns"]
    jid = plan["job_id"]
    # the user edits the plan: 3 subjects and one more field; the edited spec is what runs
    spec = plan["spec"]
    spec["rows"]["n"] = 3
    spec["phenotypes"].append("epilepsy_type")
    d = c.post(f"/leo/job/{jid}/describe", json={"spec": spec}).get_json()
    assert d["selection"]["notes_selected"] == 6 and "Epilepsy type" in d["description"]
    # bad edits are refused, not guessed
    bad = dict(spec, phenotypes=["nope"])
    assert c.post(f"/leo/job/{jid}/run", json={"spec": bad, "llm": "off"}).status_code == 422
    assert c.post(f"/leo/job/{jid}/run", json={"spec": dict(spec, shell="rm -rf /"), "llm": "off"}).status_code == 400
    assert c.post(f"/leo/job/{jid}/run", json={"spec": dict(spec, questions=[{"question": "Q?", "answer_type": "text"}]),
                                              "llm": "off"}).status_code == 422          # questions need the model
    r = c.post(f"/leo/job/{jid}/run", json={"spec": spec, "llm": "off"})
    assert r.status_code == 202
    for _ in range(120):
        st = c.get(f"/leo/jobs/{jid}").get_json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert st["state"] == "done", st
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/leo/jobs/{jid}/download").data))
    assert "notes_leo.job.json" in z.namelist()
    assert json.loads(z.read("notes_leo.job.json"))["rows"]["n"] == 3
    res = pd.read_csv(z.open("notes_leo.csv"), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert len(res) == 6 and "epilepsy_type" in res.columns and "patient_id" in res.columns
    assert c.post(f"/leo/job/{jid}/describe", json={"spec": spec}).status_code == 409   # already started
    assert c.get(f"/leo/jobs/{jid}/review?scope=all").status_code == 200                   # review still works
    assert c.post("/leo/job/plan", data={"file": (io.BytesIO(b"x"), "evil.exe")}).status_code == 400
    unknown = c.post("/leo/job/plan", data={"file": (io.BytesIO(data), "n2.csv"), "request": "predict outcome"}).get_json()
    assert unknown["problems"] and unknown["spec"]["phenotypes"] == []


def test_cli_run_writes_a_job_file_and_refuses_to_guess(tmp_path):
    import subprocess
    inp = tmp_path / "n.csv"
    inp.write_text("patient_id,note_id,text\n" + "\n".join(f"P{i},N{i},{json.dumps(NOTE)}" for i in range(3)) + "\n")
    py = sys.executable
    cli = str(Path(__file__).resolve().parents[1] / "scripts" / "leo_cli.py")
    r = subprocess.run([py, cli, "run", "seizure types for the first 2 subjects", "--input", str(inp), "--plan-only"],
                       capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 0 and "This run: 2 notes from 2 subjects" in r.stdout
    spec = json.loads((tmp_path / "n_leo.job.json").read_text())
    assert spec["phenotypes"] == ["seizure_type"] and spec["rows"] == {"mode": "first_subjects", "n": 2, "where": []}
    # no terminal and no --yes: nothing starts
    r = subprocess.run([py, cli, "run", "seizure types", "--input", str(inp), "--local", "--cpu"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, cwd=str(tmp_path))
    assert r.returncode == 2 and not (tmp_path / "n_leo.csv").exists()
    # an unrecognised request is a problem, not a silent default
    r = subprocess.run([py, cli, "run", "predict outcome", "--input", str(inp), "--yes", "--local", "--cpu"],
                       capture_output=True, text=True, cwd=str(tmp_path))
    assert r.returncode == 2 and "PROBLEM" in r.stdout


# ---- local hosting: login, audit log, per-user jobs, jobs that survive a restart ----------------

def test_login_audit_isolation_and_restart(client, tmp_path):
    import base64
    from services import leo_auth as la
    c, leo = client
    la._FAILS.clear()
    assert c.get("/leo/phenotypes").status_code == 200                    # no users: login is off
    la.add_user("alice", "correct horse battery")
    la.add_user("bob", "another long passphrase")
    with pytest.raises(ValueError):
        la.add_user("eve", "short")                                       # too short
    mode = oct(la.users_path().stat().st_mode & 0o777)
    assert mode == "0o600" and "correct horse" not in la.users_path().read_text()   # hashed, owner-only
    # everything but /health and the login page needs a login
    assert c.get("/leo/phenotypes").status_code == 401
    assert c.post("/leo/extract", json={"source_text": NOTE}).status_code == 401
    assert c.get("/health").status_code in (200, 503)
    r = c.get("/leo/ui", headers={"Accept": "text/html"})
    assert r.status_code == 302 and "/leo/login" in r.headers["Location"]
    assert c.get("/leo/login").status_code == 200
    # wrong password; and a login cannot send the browser to another site
    assert c.post("/leo/login", data={"username": "alice", "password": "nope-nope-nope"}).status_code == 401
    r = c.post("/leo/login", data={"username": "alice", "password": "correct horse battery", "next": "//evil.example/x"})
    assert r.status_code == 302 and r.headers["Location"] == "/leo/ui"
    assert c.get("/leo/phenotypes").status_code == 200
    assert c.get("/leo/status").get_json()["user"] == "alice"
    # scripts can use HTTP Basic
    auth = {"Authorization": "Basic " + base64.b64encode(b"bob:another long passphrase").decode()}
    assert c.application.test_client().get("/leo/phenotypes", headers=auth).status_code == 200
    bad = {"Authorization": "Basic " + base64.b64encode(b"bob:wrong wrong wrong").decode()}
    assert c.application.test_client().get("/leo/phenotypes", headers=bad).status_code == 401
    # a page on another site cannot act with alice's cookie
    assert c.post("/leo/extract", json={"source_text": NOTE, "llm": "off"},
                  headers={"Origin": "http://evil.example"}).status_code == 403
    # alice runs a job
    csv = "note_id,text\nn1," + json.dumps(NOTE) + "\n"
    r = c.post("/leo/batch", data={"file": (io.BytesIO(csv.encode()), "notes.csv"), "llm": "off", "format": "csv"})
    assert r.status_code == 202
    jid = r.get_json()["job_id"]
    for _ in range(120):
        st = c.get(f"/leo/jobs/{jid}").get_json()
        if st["state"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert st["state"] == "done", st
    bob = c.application.test_client()
    bob.post("/leo/login", data={"username": "bob", "password": "another long passphrase"})
    assert bob.get("/leo/jobs/" + jid).status_code == 404                  # not bob's job
    assert bob.get(f"/leo/jobs/{jid}/download").status_code == 404
    assert bob.delete("/leo/jobs/" + jid).status_code == 404
    # the app restarts: the job is still there for alice, still hidden from bob
    leo._JOBS.clear()
    assert c.get(f"/leo/jobs/{jid}").get_json()["state"] == "done"
    assert zipfile.ZipFile(io.BytesIO(c.get(f"/leo/jobs/{jid}/download").data)).namelist()
    assert c.get(f"/leo/jobs/{jid}/review?scope=all").status_code == 200   # review works on a restored job
    leo._JOBS.clear()
    assert bob.get("/leo/jobs/" + jid).status_code == 404
    # a job that was running when the app stopped says so instead of hanging
    meta_path = Path(os.environ["APP_HOME"]) / "data" / "leo_jobs" / jid / "job.json"
    meta = json.loads(meta_path.read_text())
    meta["state"] = "running"
    meta_path.write_text(json.dumps(meta))
    leo._JOBS.clear()
    st = c.get(f"/leo/jobs/{jid}").get_json()
    assert st["state"] == "error" and "restarted" in st["error"]
    assert leo._load_job("../../etc") is None and leo._load_job("A" * 32) is None
    # audit log: who did what, no note text
    log = la.audit_path().read_text()
    events = [json.loads(l) for l in log.splitlines()]
    assert {"login", "login_failed", "job_start", "download"} <= {e["event"] for e in events}
    assert all(e["user"] in ("alice", "bob", "(no login)") for e in events)
    assert NOTE[:40] not in log and "correct horse" not in log
    assert oct(la.audit_path().stat().st_mode & 0o777) == "0o600"
    # five wrong passwords lock that user and address for a while, even for the right password
    other = c.application.test_client()
    for _ in range(5):
        other.post("/leo/login", data={"username": "bob", "password": "wrong wrong wrong"})
    assert other.post("/leo/login", data={"username": "bob", "password": "another long passphrase"}).status_code == 429
    la._FAILS.clear()
    # sign out
    assert c.post("/leo/logout").status_code == 302 and c.get("/leo/phenotypes").status_code == 401
    # removing the last users turns login off again
    la.remove_user("alice"); la.remove_user("bob")
    assert c.get("/leo/phenotypes").status_code == 200


def test_required_login_with_no_users_locks_everyone_out(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("MEDAI_LEO_REQUIRE_LOGIN", "1")
    assert c.get("/leo/phenotypes").status_code == 401
    assert c.post("/leo/login", data={"username": "x", "password": "yyyyyyyyyyyy"}).status_code == 401


# ---- one job at a time; odd files -------------------------------------------------------

def _wait_state(c, jid, want, secs=60):
    for _ in range(int(secs * 4)):
        st = c.get(f"/leo/jobs/{jid}").get_json()
        if st["state"] in want:
            return st
        time.sleep(0.25)
    return st


def test_jobs_wait_for_their_turn_and_a_waiting_job_can_be_cancelled(client, monkeypatch):
    import threading
    c, leo = client
    slot = threading.Semaphore(1)
    monkeypatch.setattr(leo, "_SLOT", slot)
    csv = "note_id,text\nn1," + json.dumps(NOTE) + "\n"
    slot.acquire()                                               # pretend another job is running
    try:
        j1 = c.post("/leo/batch", data={"file": (io.BytesIO(csv.encode()), "a.csv"), "llm": "off"}).get_json()["job_id"]
        j2 = c.post("/leo/batch", data={"file": (io.BytesIO(csv.encode()), "b.csv"), "llm": "off"}).get_json()["job_id"]
        time.sleep(1.0)
        assert c.get(f"/leo/jobs/{j1}").get_json()["state"] == "queued"
        assert c.get(f"/leo/jobs/{j2}").get_json()["state"] == "queued"
        assert c.post(f"/leo/jobs/{j2}/cancel").status_code == 200
    finally:
        slot.release()
    assert _wait_state(c, j1, ("done", "error"))["state"] == "done"
    st2 = _wait_state(c, j2, ("cancelled", "done", "error"))
    assert st2["state"] == "cancelled" and st2["summary"]["rows_processed"] == 0
    assert c.get(f"/leo/jobs/{j2}/download").status_code == 409     # nothing to download, said plainly


def test_background_jobs_with_the_model_run_inside_the_app_context(client, runtimes, monkeypatch):
    """A job thread has no request: the model runtime looks up the app, so the thread must carry the app context.
    (This failed on a real GPU run while the fake-free CPU tests passed.)  Both job kinds, model on."""
    c, leo = client
    llm, _ = runtimes
    backend = object()
    monkeypatch.setattr(c.application, "med42_backend", backend, raising=False)
    monkeypatch.setattr(c.application, "ensure_med42_loaded", lambda: "ready")
    monkeypatch.setitem(leo._RUNTIMES, f"llm:{id(backend)}:L1C:8000", llm)
    csv = "patient_id,note_id,text\nP1,n1," + json.dumps(NOTE) + "\n"
    r = c.post("/leo/batch", data={"file": (io.BytesIO(csv.encode()), "a.csv"), "llm": "on"})
    assert r.status_code == 202 and r.get_json()["mode"] == "llm+specialist"
    st = _wait_state(c, r.get_json()["job_id"], ("done", "error"))
    assert st["state"] == "done" and st["summary"]["rows_with_llm"] == 1, st
    plan = c.post("/leo/job/plan", data={"file": (io.BytesIO(csv.encode()), "b.csv"),
                                         "request": "seizure types for the first 1 subjects"}).get_json()
    r = c.post(f"/leo/job/{plan['job_id']}/run", json={"spec": plan["spec"], "llm": "on"})
    assert r.status_code == 202
    st = _wait_state(c, plan["job_id"], ("done", "error"))
    assert st["state"] == "done" and st["summary"]["rows_with_llm"] == 1, st


def test_a_running_job_cannot_be_deleted_only_cancelled_first(client, monkeypatch):
    import threading
    c, leo = client
    slot = threading.Semaphore(1)
    monkeypatch.setattr(leo, "_SLOT", slot)
    slot.acquire()
    try:
        jid = c.post("/leo/batch", data={"file": (io.BytesIO(b"text\nx\n"), "a.csv"), "llm": "off"}).get_json()["job_id"]
        time.sleep(0.5)
        assert c.delete(f"/leo/jobs/{jid}").status_code == 409
        assert c.post(f"/leo/jobs/{jid}/cancel").status_code == 200
    finally:
        slot.release()
    assert _wait_state(c, jid, ("cancelled",))["state"] == "cancelled"
    assert c.delete(f"/leo/jobs/{jid}").status_code == 200


def test_odd_files_give_a_clear_message_not_a_crash(client):
    c, leo = client
    def post(data, name="x.csv", **kw):
        return c.post("/leo/batch", data={"file": (io.BytesIO(data), name), "llm": "off", **kw})
    def outcome(r):
        if r.status_code != 202:
            return r.status_code, r.get_json()["error"]
        st = _wait_state(c, r.get_json()["job_id"], ("done", "error"), secs=150)
        return st["state"], st["error"]
    # empty file, header only, no text column
    for data in (b"", b"text\n", b"a,b\n1,2\n"):
        state, msg = outcome(post(data))
        assert state in (400, "error") and msg, (data, state, msg)
    # text with a BOM, Windows line endings, latin-1 accents and a blank note still run
    bom = ("\ufefftext\r\n" + json.dumps(NOTE) + "\r\n\r\n").encode("utf-8")
    state, _ = outcome(post(bom))
    assert state == "done"
    latin = ("text\n" + json.dumps(NOTE.replace("seizures", "crises é")) + "\n").encode("latin-1", "replace")
    assert outcome(post(latin))[0] in ("done", 400, "error")        # must not hang or 500
    # one very long note (about 30 KB; a 100 KB note takes minutes when the machine is busy) is processed or
    # refused, never a crash or a hang
    big = ("text\n" + json.dumps(NOTE * 180) + "\n").encode()
    state, msg = outcome(post(big))
    assert state in ("done", 400, "error"), (state, msg)
    # a file over the size limit is refused with a message
    c.application.config["MAX_CONTENT_LENGTH"] = 1024
    try:
        r = post(b"text\n" + b"x" * 5000 + b"\n")
        assert r.status_code == 413
    finally:
        c.application.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
