#!/usr/bin/env python3
"""
POST /analyze with sample_patient_visits.csv: classify MRI documentation as epilepsy-relevant or not.

In-process (loads model in this Python process — use on a GPU node with CUDA PyTorch for GPU):
  export APP_HOME=$(pwd)
  export VECTA_MAX_NEW_TOKENS=384 VECTA_GREEDY_FAST=1
  python3 scripts/test_mri_epilepsy_csv.py

HTTP (hit a running gunicorn, e.g. Slurm job on the compute node — RAG/few-shot/GPU follow server env):
  export VECTA_SERVICE_URL=http://127.0.0.1:8085
  # From login node, run curl inside the allocation:
  srun --jobid=<id> --overlap bash -lc 'cd /path/to/med42_service && python3 scripts/test_mri_epilepsy_csv.py'

On GPU node, same command after activating CUDA PyTorch; much faster than CPU.
"""
import json
import os
import sys
import uuid
from typing import Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("APP_HOME", ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

MRI_EPILEPSY_PROMPT = """You are reviewing tabular visit data. For each row, focus ONLY on MRI BRAIN (or MRI head/spine if present) text in the clinical_note.

For each visit_id, output one line in this exact pattern:
visit_id | MRI_epilepsy_relevant: YES | NO | NOT_PERFORMED | INSUFFICIENT_NOTE
- YES = MRI describes findings that can support an epilepsy workup (e.g., hippocampal sclerosis signal, focal cortical dysplasia, lesion, mesial temporal changes, post-TBI gliosis) per what is written.
- NO = MRI explicitly normal for epilepsy-relevant pathology, or describes only non-epilepsy pathology (e.g., acute stroke only) with no epileptogenic structural correlate claimed.
- NOT_PERFORMED = MRI not done or explicitly deferred.
- INSUFFICIENT_NOTE = MRI section missing or too vague.

Then end with exactly these four bullets (max 25 words each):
- Classification:
- Clinical_Confidence:
- Evidence:
- Medication_Analysis:

Do not diagnose the patient; only classify what the MRI documentation states."""


def _service_url() -> Optional[str]:
    u = os.environ.get("VECTA_SERVICE_URL") or os.environ.get("VECTA_BASE_URL")
    return u.strip().rstrip("/") if u else None


def _multipart_analyze_body(csv_path: str) -> Tuple[bytes, str]:
    """Build multipart/form-data so `prompt` is a text field (Flask request.form), not a file upload."""
    boundary = b"vecta-" + uuid.uuid4().hex.encode("ascii")
    crlf = b"\r\n"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.append(b"--" + boundary + crlf)
        disp = (
            b'Content-Disposition: form-data; name="'
            + name.encode("utf-8")
            + b'"'
            + crlf
            + crlf
        )
        parts.append(disp + value.encode("utf-8") + crlf)

    add_field("prompt", MRI_EPILEPSY_PROMPT)
    add_field("analysisType", "classification")
    add_field("specialty", "neurology")
    add_field("userId", "mri-epilepsy-csv-test")

    parts.append(b"--" + boundary + crlf)
    fname = os.path.basename(csv_path)
    parts.append(
        b'Content-Disposition: form-data; name="file"; filename="'
        + fname.encode("utf-8")
        + b'"'
        + crlf
        + b"Content-Type: text/csv"
        + crlf
        + crlf
    )
    with open(csv_path, "rb") as fp:
        parts.append(fp.read() + crlf)
    parts.append(b"--" + boundary + b"--" + crlf)
    body = b"".join(parts)
    ctype = "multipart/form-data; boundary=" + boundary.decode("ascii")
    return body, ctype


def _run_http(csv_path: str) -> int:
    base = _service_url()
    assert base
    try:
        hr = urlopen(Request(f"{base}/health", method="GET"), timeout=15)
        print("--- GET /health ---", file=sys.stderr)
        print(hr.read().decode("utf-8", errors="replace")[:4000], file=sys.stderr)
    except (HTTPError, URLError, OSError) as e:
        print("GET /health failed:", e, file=sys.stderr)

    body, ctype = _multipart_analyze_body(csv_path)
    url = f"{base}/analyze"
    timeout = int(os.environ.get("VECTA_HTTP_TIMEOUT", "1200"))
    req = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": ctype},
    )
    print("POST", url, file=sys.stderr)
    try:
        resp = urlopen(req, timeout=timeout)
        raw = resp.read().decode("utf-8", errors="replace")
        code = resp.status
    except HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        code = e.code
        print("HTTP", code, raw[:2000], file=sys.stderr)
        return 1

    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        print(raw[:2000], file=sys.stderr)
        return 1

    print("HTTP", code)
    if not out.get("success"):
        print(out.get("error", out))
        return 1
    print("chunking:", out.get("chunking"))
    print("confidence_score:", out.get("confidence_score"))
    print("\n--- analysis ---\n")
    print((out.get("analysis") or "")[:8000])
    return 0


def main() -> int:
    csv_path = os.path.join(ROOT, "data", "sample_patient_visits", "patient_visits.csv")
    if not os.path.isfile(csv_path):
        print("Missing:", csv_path, file=sys.stderr)
        return 1

    if _service_url():
        return _run_http(csv_path)

    try:
        import torch
        _cuda = bool(torch.cuda.is_available())
        print("torch.cuda.is_available():", _cuda, file=sys.stderr)
    except Exception as e:
        print("torch:", e, file=sys.stderr)

    from app import app
    from app import inference_augmentation_flags

    ur, ufs = inference_augmentation_flags()
    print("USE_RAG:", ur, "USE_FEW_SHOT:", ufs, file=sys.stderr)

    with open(csv_path, "rb") as fp:
        data = {
            "prompt": MRI_EPILEPSY_PROMPT,
            "analysisType": "classification",
            "specialty": "neurology",
            "userId": "mri-epilepsy-csv-test",
            "file": (fp, "patient_visits.csv"),
        }
        with app.test_client() as c:
            r = c.post("/analyze", data=data, content_type="multipart/form-data")

    print("HTTP", r.status_code)
    out = r.get_json(silent=True)
    if not out:
        print(r.data[:8000])
        return 1
    if not out.get("success"):
        print(out.get("error", out))
        return 1
    print("chunking:", out.get("chunking"))
    print("confidence_score:", out.get("confidence_score"))
    print("\n--- analysis ---\n")
    print((out.get("analysis") or "")[:8000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
