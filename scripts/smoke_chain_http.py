#!/usr/bin/env python3
"""HTTP smoke test for the LEO chain: /extract/chain, ledger, review queue, review UI.

Runs the REAL specialist (EpExtra on MedCAT + ontology candidates) with a SCRIPTED LLM
reasoner (no GPU), against a temporary ledger database.  Checks that the new Claim fields
(`field_path`, `value`, `alternative`, `detectors`) and the fusion counters survive the
HTTP -> ledger -> review round trip.

Needs flask and medcat in one interpreter.  The repo has them in separate venvs, so run:

    PYTHONPATH=<dir with flask packages> venv-medcat/bin/python scripts/smoke_chain_http.py

Exit code 0 iff every check passes.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PASS, FAIL = "\033[32m✓\033[0m", "\033[31m✗\033[0m"
errors: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {PASS if ok else FAIL} {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        errors.append(name)


NOTE = (
    "Neurology clinic. 34 year old woman with focal epilepsy since age 10. "
    "Current medication: levetiracetam 500 mg twice daily and lamotrigine 100 mg twice daily. "
    "Seizures occur about 2 per month. MRI brain was normal."
)


def ev(value, quote):
    return {"value": value, "certainty": "definite", "temporal_status": "current",
            "evidence_text": quote, "char_start": None, "char_end": None}


def scripted_llm(text, document_id, doc_date):
    """Agrees on type and levetiracetam, disagrees on onset age, adds a supported
    lamotrigine and an unsupported (invented-quote) topiramate."""
    return {
        "document": {"doc_id": document_id},
        "clinical_seizure": {
            "epilepsy_type": ev("focal", "focal epilepsy"),
            "age_at_onset_years": ev(25, "since age 10"),
        },
        "medication": {"current_asms": [
            ev({"generic_name": "levetiracetam"}, "levetiracetam 500 mg twice daily"),
            ev({"generic_name": "lamotrigine"}, "lamotrigine 100 mg twice daily"),
            ev({"generic_name": "topiramate"}, "topiramate 50 mg at night"),
        ]},
    }


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="leo_smoke_")
    os.environ["MEDAI_LEDGER_DB"] = str(Path(tmp) / "evidence.sqlite")
    os.environ.setdefault("APP_HOME", str(REPO))

    import app as app_module
    from services.chain_pipeline import ChainPipeline

    app = app_module.app
    pipe = ChainPipeline(llm_reasoner=scripted_llm)
    app._chain_pipeline = pipe
    client = app.test_client()

    print("== POST /extract/chain (specialist + scripted LLM) ==")
    r = client.post("/extract/chain", json={"source_text": NOTE, "document_id": "SMOKE-1",
                                            "doc_date": "2026-01-15"})
    check("status 200", r.status_code == 200, str(r.status_code))
    body = r.get_json() or {}
    stats = body.get("stats", {})
    llm = stats.get("llm", {})
    claims = body.get("claims", [])
    check("claims returned", len(claims) > 0, str(len(claims)))
    check("llm channel reported available", llm.get("available") is True, str(llm))
    check("unsupported LLM quote counted", llm.get("llm_unsupported") == 1, str(llm))
    check("claims carry field_path", any(c.get("field_path") for c in claims))
    check("some claim has two detectors", any(len(c.get("detectors", [])) == 2 for c in claims))
    only = [c for c in claims if c.get("detectors") == ["llm"]]
    check("at least one LLM-only claim present", len(only) > 0)
    check("LLM-only claims never ACCEPT",
          all(str(c.get("validator_verdict")).lower() != "accept" for c in only),
          str([c.get("validator_verdict") for c in only]))
    check("unsupported claim is REJECT",
          any(str(c.get("validator_verdict")).lower() == "reject" and "offsets_unresolved" in c.get("reason_codes", [])
              for c in only))
    dis = [c for c in claims if c.get("alternative")]
    check("disagreement keeps alternative and REVIEW",
          len(dis) > 0 and all(str(c.get("validator_verdict")).lower() == "review" for c in dis),
          str(len(dis)))
    check("counters add up",
          stats.get("n_accepted", 0) + stats.get("n_review", 0) + stats.get("n_rejected", 0)
          == stats.get("n_claims_emitted"), str(stats))

    print("== GET /extract/ledger/counts ==")
    r = client.get("/extract/ledger/counts")
    check("status 200", r.status_code == 200)
    counts = (r.get_json() or {}).get("counts", {})
    check("ledger has rows", sum(v for v in counts.values() if isinstance(v, int)) > 0, str(counts))

    print("== GET /extract/review/pending ==")
    r = client.get("/extract/review/pending")
    check("status 200", r.status_code == 200)
    pending = (r.get_json() or {}).get("pending", [])
    check("review queue not empty", len(pending) > 0, str(len(pending)))
    check("pending rows keep new fields",
          all("field_path" in p for p in pending) if pending else False)
    check("alternative survives ledger round trip",
          (not dis) or any(p.get("alternative") for p in pending))

    if pending:
        print("== POST /extract/review/<id>/resolve ==")
        cid = pending[0]["claim_id"]
        r = client.post(f"/extract/review/{cid}/resolve",
                        json={"action": "accept_as_is", "reviewer": "smoke", "notes": "ok"})
        check("accept_as_is 200", r.status_code == 200, r.get_data(as_text=True)[:200])
        after = (client.get("/extract/review/pending").get_json() or {}).get("pending", [])
        check("claim left the queue", all(p["claim_id"] != cid for p in after))
        r = client.post("/extract/review/does-not-exist/resolve", json={"action": "reject"})
        check("unknown claim -> 404", r.status_code == 404)
        r = client.post(f"/extract/review/{cid}/resolve", json={"action": "bogus"})
        check("bad action -> 400", r.status_code == 400)

    print("== CLI (medai-epi chain / review) against a live local server ==")
    import subprocess
    import threading
    from werkzeug.serving import make_server

    port = 18177
    srv = make_server("127.0.0.1", port, app, threaded=True)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        note_path = Path(tmp) / "note.txt"
        note_path.write_text(NOTE, encoding="utf-8")
        cli = [sys.executable, str(REPO / "scripts" / "medai_epi_cli.py"), "--server", f"http://127.0.0.1:{port}"]
        out_path = Path(tmp) / "claims.jsonl"
        r = subprocess.run(cli + ["chain", str(note_path), "--doc-id", "SMOKE-CLI", "-o", str(out_path)],
                           capture_output=True, text=True, timeout=120)
        check("cli chain exit 0", r.returncode == 0, r.stderr[-200:])
        check("cli chain wrote JSONL", out_path.exists() and out_path.read_text().count("\n") > 0)
        r = subprocess.run(cli + ["review", "list"], capture_output=True, text=True, timeout=60)
        check("cli review list exit 0", r.returncode == 0, r.stderr[-200:])
        first = (r.stdout.split() or [""])[0]
        check("cli review list shows claim ids", bool(first))
        if first:
            r = subprocess.run(cli + ["review", "resolve", first, "reject", "--reviewer", "smoke"],
                               capture_output=True, text=True, timeout=60)
            check("cli review resolve reject exit 0", r.returncode == 0, r.stdout[-200:] + r.stderr[-200:])
    finally:
        srv.shutdown()

    print("== validation ==")
    r = client.post("/extract/chain", json={})
    check("missing source_text -> 400", r.status_code == 400)

    print("== GET /extract/ui/review ==")
    r = client.get("/extract/ui/review")
    check("review UI 200", r.status_code == 200, str(r.status_code))
    check("review UI serves HTML", b"<html" in r.data.lower() or b"<!doctype" in r.data.lower())

    print()
    if errors:
        print(f"\033[31m{len(errors)} CHECK(S) FAILED:\033[0m " + "; ".join(errors))
        return 1
    print("\033[32mALL CHECKS PASSED.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
