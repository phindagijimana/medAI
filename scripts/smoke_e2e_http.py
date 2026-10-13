#!/usr/bin/env python3
"""End-to-end HTTP smoke test for the MedAI-EPI Flask surface.

Runs entirely offline: installs a scripted mock Med42Backend on the app,
exercises every /extract/* endpoint via Flask's test_client, and asserts on
response shape + CSV row shape. Runs in <5 seconds with no GPU.

Endpoints covered:
    GET  /                          (redirect to /extract/ui)
    GET  /extract/ui                (single-page research UI)
    GET  /extract/health            (backend probe)
    GET  /extract/registry          (prompt inventory)
    POST /extract/detect_doc_type   (heuristic classifier)
    POST /extract                   (single-doc structured extraction)
    POST /extract/batch             (multi-doc)
    POST /extract/csv               (JSON in → long CSV out)
    POST /extract/csv               (CSV upload → long CSV out)
    POST /extract/csv?chunk=1       (forced long-note chunking path)
    POST /extract/chat              (freeform question → grounded answer row)

Exit code 0 iff every check passes; non-zero + red diagnostic on failure.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Scripted backend — matches services.med42_backend.Med42Backend surface
# ---------------------------------------------------------------------------


def _make_module_json(module_name):
    """Emit an Evidence-wrapped JSON string that validates against the target
    module's schema. Kept minimal — only the fields we care about are populated;
    everything else is `not_documented`."""
    src = {
        "source_doc_id": "SMOKE",
        "source_doc_type": "progress_note",
        "source_date": "2024-01-01",
    }
    nd = lambda: {"value": None, "certainty": "not_documented",
                  "temporal_status": "unspecified", "evidence_text": None, **src}
    ev = lambda v, t: {"value": v, "certainty": "definite",
                       "temporal_status": "current", "evidence_text": t, **src}

    if module_name.startswith("medication"):
        return json.dumps({
            "current_asms": [{
                "value": {"generic_name": "lamotrigine", "status": "current"},
                "certainty": "definite", "temporal_status": "current",
                "evidence_text": "lamotrigine 75mg BID", **src,
            }],
            "prior_asms": [], "failed_asms": [],
            "adverse_effects_text": nd(),
            "drug_resistance_status": nd(),
            "surgery_history": [], "non_drug_therapies": [],
        })
    if module_name.startswith("clinical_seizure"):
        return json.dumps({
            "epilepsy_type": ev("focal", "focal epilepsy"),
            "predominant_seizure_type": nd(),
            "other_seizure_types": [],
            "awareness": nd(), "semiology_text": nd(),
            "age_at_onset_years": nd(),
            "seizure_frequency": nd(),
            "other_seizure_frequencies": [],
            "status_epilepticus_history": nd(),
            "etiology_category": nd(),
            "etiology_details_text": nd(),
            "etiology_specifics": nd(),
            "focal_motor_onset": nd(), "focal_nonmotor_onset": nd(),
        })
    # Chat prompt (freeform, not a schema-conforming module)
    return '{"answer": "yes", "evidence_text": "seizure-free for 6 months", "confidence": "probable"}'


class MockBackend:
    model_name = "smoke-mock-med42"
    model_cache_dir = "/dev/null"

    def generate(self, prompt, decoding):
        # Route response by the module keyword in the prompt.
        low = prompt.lower()
        if "medication" in low and "clinical_seizure" not in low:
            module = "medication"
        elif "clinical_seizure" in low or "seizure" in low[:400]:
            module = "clinical_seizure"
        elif "one user question" in low or "clinical note:" in low:
            module = "chat"
        else:
            module = "medication"
        return _make_module_json(module), 512


# ---------------------------------------------------------------------------
# Tiny assertion helpers
# ---------------------------------------------------------------------------


PASS, FAIL = "\033[32m✓\033[0m", "\033[31m✗\033[0m"
errors = []


def check(name, cond, detail=""):
    global errors
    if cond:
        print(f"  {PASS} {name}")
    else:
        errors.append(name)
        print(f"  {FAIL} {name}   {detail}")


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------


def run():
    import app as A
    A.app.med42_backend = MockBackend()
    A.app.med42_backend_status = "ready"
    A.app.ensure_med42_loaded = lambda: "ready"
    c = A.app.test_client()

    print("\n== /  and /extract/ui ==")
    r = c.get("/")
    check("root redirects", r.status_code == 302 and "/leo/ui" in r.headers.get("Location", ""))
    r = c.get("/extract/ui")
    check("ui renders", r.status_code == 200 and b"MedAI-EPI" in r.data)

    print("\n== /extract/health + /extract/registry ==")
    r = c.get("/extract/health")
    d = r.get_json()
    check("health 200", r.status_code == 200)
    check("22 prompts registered", len(d.get("prompts_registered") or []) >= 22)
    r = c.get("/extract/registry")
    check("registry 200", r.status_code == 200)
    check("registry lists prompts", isinstance(r.get_json(), (list, dict)))

    print("\n== POST /extract/detect_doc_type ==")
    r = c.post("/extract/detect_doc_type", json={"source_text": "Dear Dr, follow-up clinic note."})
    check("detect 200", r.status_code == 200)
    check("detect returns doc_type", r.get_json().get("doc_type") in ("progress_note", None))

    print("\n== POST /extract (single-doc) ==")
    r = c.post("/extract", json={
        "source_text": "Dear Dr, on lamotrigine 75mg BID. Focal epilepsy.",
        "doc_type": "progress_note", "arm": "M2",
        "doc_id": "SMOKE1",
    })
    check("extract 200", r.status_code == 200, f"body={r.get_data(as_text=True)[:400]}")
    if r.status_code == 200:
        d = r.get_json()
        check("phenotype returned", "phenotype" in d and d["phenotype"]["document"]["doc_id"] == "SMOKE1")
        check("manifests present", len(d.get("manifests") or []) > 0)

    print("\n== POST /extract/batch ==")
    r = c.post("/extract/batch", json={
        "documents": [
            {"source_text": "Dear Dr, on LTG.", "doc_type": "progress_note",
             "doc_id": "B1"},
            {"source_text": "Dear Dr, on LEV.", "doc_type": "progress_note",
             "doc_id": "B2"},
        ],
        "arm": "M1",
    })
    check("batch 200", r.status_code == 200, f"body={r.get_data(as_text=True)[:200]}")
    if r.status_code == 200:
        d = r.get_json()
        check("batch returns 2 results", len(d.get("results") or []) == 2)

    print("\n== POST /extract/csv (JSON in → CSV out) ==")
    r = c.post("/extract/csv", json={
        "source_text": "Dear Dr, on lamotrigine 75mg BID.",
        "doc_type": "progress_note", "arm": "M2", "doc_id": "CSV1",
    })
    check("csv-json 200", r.status_code == 200)
    body = r.get_data(as_text=True)
    check("csv header row", body.startswith("doc_id,patient_id,doc_type,doc_date"))
    check("csv has confidence column", "confidence" in body.splitlines()[0])
    check("csv has evidence_text column", "evidence_text" in body.splitlines()[0])
    check("csv has ≥1 data row", len(body.splitlines()) >= 2)

    print("\n== POST /extract/csv (CSV upload → CSV out) ==")
    csv_in = "doc_id,visit_date,text\nR1,2024-01-15,Dear Dr; on LTG.\nR2,2024-06-01,Dear Dr; on LEV.\n"
    r = c.post("/extract/csv", data=csv_in, content_type="text/csv")
    check("csv-upload 200", r.status_code == 200)
    body = r.get_data(as_text=True)
    lines = body.splitlines()
    check("csv-upload multiple rows", len(lines) >= 3)
    check("csv-upload preserves doc_ids", "R1" in body and "R2" in body)

    print("\n== POST /extract/csv?chunk=1 (forced long-note chunking) ==")
    long_text = "Dear Dr,\n\n" + ("Section paragraph text.\n\n" * 400)   # ~10k chars
    r = c.post("/extract/csv?chunk=1", json={
        "source_text": long_text, "doc_type": "progress_note",
        "arm": "M2", "doc_id": "LONG1",
    })
    check("chunk=1 200", r.status_code == 200, f"body={r.get_data(as_text=True)[:200]}")
    body = r.get_data(as_text=True)
    check("chunk=1 emits rows", len(body.splitlines()) >= 2)

    print("\n== POST /extract/chat ==")
    r = c.post("/extract/chat", json={
        "source_text": "Dear Dr, patient has been seizure-free for 6 months.",
        "question": "is the patient seizure-free?",
        "doc_id": "CHAT1",
    })
    check("chat 200", r.status_code == 200)
    if r.status_code == 200:
        d = r.get_json()
        check("chat answer present", bool(d.get("answer")))
        check("chat csv_row shape", isinstance(d.get("csv_row"), dict) and d["csv_row"].get("module") == "user_query")

    print()
    if errors:
        print(f"\033[31m{len(errors)} check(s) failed:\033[0m")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\033[32mALL CHECKS PASSED.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(run())
