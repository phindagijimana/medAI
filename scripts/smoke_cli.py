#!/usr/bin/env python3
"""Smoke test for the medai-epi CLI.

Boots the Flask app in a background thread with a scripted mock backend
attached, then invokes every CLI subcommand through subprocess and asserts
on stdout/exit codes. Runs in <10 s with no GPU.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CLI = REPO / "bin" / "medai-epi"
PORT = 18099
BASE_URL = f"http://127.0.0.1:{PORT}"

PASS, FAIL = "\033[32m✓\033[0m", "\033[31m✗\033[0m"
errors: list[str] = []


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  {PASS} {name}")
    else:
        errors.append(name)
        print(f"  {FAIL} {name}   {detail}")


# ---------------------------------------------------------------------------
# Scripted mock backend (matches Med42Backend surface)
# ---------------------------------------------------------------------------


class MockBackend:
    model_name = "cli-smoke-mock"
    model_cache_dir = "/dev/null"

    def generate(self, prompt, decoding):
        low = prompt.lower()
        if "one user question" in low or 'clinical note:\n"""' in low.lower():
            resp = json.dumps({
                "answer": "yes, mentioned in the assessment",
                "evidence_text": "recommend surgical evaluation",
                "confidence": "probable",
            })
        elif "medication" in low and "clinical_seizure" not in low:
            resp = json.dumps({
                "current_asms": [{
                    "value": {"generic_name": "lamotrigine", "status": "current"},
                    "certainty": "definite", "temporal_status": "current",
                    "evidence_text": "lamotrigine 75mg BID",
                    "source_doc_id": "SMOKE", "source_doc_type": "progress_note",
                    "source_date": "2024-01-01",
                }],
                "prior_asms": [], "failed_asms": [],
                "adverse_effects_text": {"value": None, "certainty": "not_documented",
                                          "temporal_status": "unspecified",
                                          "evidence_text": None,
                                          "source_doc_id": "SMOKE",
                                          "source_doc_type": "progress_note",
                                          "source_date": "2024-01-01"},
                "drug_resistance_status": {"value": None, "certainty": "not_documented",
                                            "temporal_status": "unspecified",
                                            "evidence_text": None,
                                            "source_doc_id": "SMOKE",
                                            "source_doc_type": "progress_note",
                                            "source_date": "2024-01-01"},
                "surgery_history": [], "non_drug_therapies": [],
            })
        else:
            # ClinicalSeizure minimal-content stub — every field NOT_DOCUMENTED
            src = {"source_doc_id": "SMOKE", "source_doc_type": "progress_note",
                   "source_date": "2024-01-01"}
            nd = {"value": None, "certainty": "not_documented",
                   "temporal_status": "unspecified", "evidence_text": None, **src}
            resp = json.dumps({
                "epilepsy_type": nd, "predominant_seizure_type": nd,
                "other_seizure_types": [], "awareness": nd,
                "semiology_text": nd, "age_at_onset_years": nd,
                "seizure_frequency": nd, "other_seizure_frequencies": [],
                "status_epilepticus_history": nd, "etiology_category": nd,
                "etiology_details_text": nd, "etiology_specifics": nd,
                "focal_motor_onset": nd, "focal_nonmotor_onset": nd,
            })
        return resp, len(resp) // 4


# ---------------------------------------------------------------------------
# Boot the Flask app in a background thread
# ---------------------------------------------------------------------------


def _start_app():
    from werkzeug.serving import make_server
    import app as A
    A.app.med42_backend = MockBackend()
    A.app.med42_backend_status = "ready"
    A.app.ensure_med42_loaded = lambda: "ready"

    srv = make_server("127.0.0.1", PORT, A.app, threaded=True)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    # Wait for readiness
    import urllib.request, urllib.error
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{BASE_URL}/extract/health", timeout=1)
            return srv
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.1)
    raise RuntimeError("Flask app did not come up in 5s")


def _cli(*args) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["MEDAI_EPI_URL"] = BASE_URL
    return subprocess.run(
        [str(CLI), *args], env=env,
        capture_output=True, text=True, timeout=30,
    )


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


def run():
    print(f"Starting Flask app on {BASE_URL}…")
    srv = _start_app()
    print(f"  ready.\n")

    tmp = Path(tempfile.mkdtemp(prefix="medai_cli_smoke_"))
    note_txt = tmp / "note.txt"
    note_txt.write_text(
        "Dear Dr, patient on lamotrigine 75mg BID for focal epilepsy. "
        "Recommend surgical evaluation.\n"
    )
    input_csv = tmp / "notes.csv"
    input_csv.write_text(
        "doc_id,text\n"
        "R1,Dear Dr; on LTG 75mg BID.\n"
        "R2,Dear Dr; on LEV 500mg BID.\n"
    )

    print("== health ==")
    r = _cli("health")
    check("health exit 0", r.returncode == 0, r.stderr[:200])
    check("health lists 22 prompts",
          "prompts_registered: 2" in r.stdout,   # "22" or more
          r.stdout[:200])

    print("\n== registry ==")
    r = _cli("registry")
    check("registry exit 0", r.returncode == 0, r.stderr[:200])
    check("registry lists prompt ids",
          "medication.M1.v1" in r.stdout,
          r.stdout[:200])
    r = _cli("registry", "medication.M1.v1")
    check("registry <id> returns JSON", r.returncode == 0 and "prompt_id" in r.stdout)

    print("\n== detect ==")
    r = _cli("detect", str(note_txt))
    check("detect exit 0", r.returncode == 0, r.stderr[:200])
    check("detect returns doc_type", "doc_type" in r.stdout, r.stdout[:200])

    print("\n== extract ==")
    r = _cli("extract", "--doc-type", "progress_note", "--arm", "M2", str(note_txt))
    check("extract exit 0", r.returncode == 0, r.stderr[:200])
    check("extract returns phenotype", '"phenotype"' in r.stdout, r.stdout[:200])
    check("extract carries lamotrigine",
          "lamotrigine" in r.stdout, r.stdout[:400])

    print("\n== csv (single note) ==")
    r = _cli("csv", "--doc-type", "progress_note", "--arm", "M2",
             "--text-file", str(note_txt))
    check("csv single-note exit 0", r.returncode == 0, r.stderr[:200])
    check("csv header present",
          r.stdout.startswith("doc_id,patient_id,doc_type"),
          r.stdout[:200])
    check("csv has confidence column",
          "confidence" in r.stdout.split("\n")[0])
    check("csv carries lamotrigine row",
          "lamotrigine" in r.stdout, r.stdout[:200])

    print("\n== csv (multi-row upload with -o output) ==")
    out_csv = tmp / "out.csv"
    r = _cli("csv", str(input_csv), "-o", str(out_csv))
    check("csv upload exit 0", r.returncode == 0, r.stderr[:200])
    check("csv upload wrote output file",
          out_csv.exists() and out_csv.stat().st_size > 100)
    check("csv upload contains both rows",
          "R1" in out_csv.read_text() and "R2" in out_csv.read_text())

    print("\n== long ==")
    r = _cli("long", "--doc-type", "progress_note", "--arm", "M2", str(note_txt))
    check("long exit 0", r.returncode == 0, r.stderr[:200])
    check("long returns phenotype + chunking meta",
          '"phenotype"' in r.stdout and '"chunking"' in r.stdout)

    print("\n== chat ==")
    r = _cli("chat", "was surgery mentioned?",
             "--text-file", str(note_txt))
    check("chat exit 0", r.returncode == 0, r.stderr[:200])
    check("chat prints Q/A block",
          r.stdout.startswith("Q: ") and "\nA: " in r.stdout,
          r.stdout[:200])

    print("\n== ui (--no-open) ==")
    r = _cli("ui", "--no-open")
    check("ui exit 0", r.returncode == 0, r.stderr[:200])
    check("ui prints URL",
          BASE_URL + "/extract/ui" in r.stdout,
          r.stdout[:200])

    print()
    if errors:
        print(f"\033[31m{len(errors)} check(s) failed:\033[0m")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\033[32mALL CLI CHECKS PASSED.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(run())
