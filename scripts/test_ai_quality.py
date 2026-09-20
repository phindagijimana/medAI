#!/usr/bin/env python3
"""
Send a curated set of medical cases through /analyze and dump every raw
response to a markdown report for clinician grading.

  export MEDAI_SERVICE_URL=http://<node>:8085
  export MEDAI_HTTP_TIMEOUT=1800
  python3 scripts/test_ai_quality.py [report_path]

Tests three modes:
  1. Single rich epilepsy case (free text, classification analysisType)
  2. Three CSV rows pulled from test_patient_data.csv (tabular path)
  3. A "no-MRI" negative-control case (model should say INSUFFICIENT_NOTE)

I do not grade clinical accuracy. Output goes to the report file verbatim.
"""
from __future__ import annotations

import csv
import json
import os
import socket
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
URL = (os.environ.get("MEDAI_SERVICE_URL") or os.environ.get("MEDAI_BASE_URL") or "").rstrip("/")
TIMEOUT = int(os.environ.get("MEDAI_HTTP_TIMEOUT", "1800"))

if not URL:
    sys.exit("Set MEDAI_SERVICE_URL=http://<node>:8085 (or MEDAI_BASE_URL).")


def _post_form(path: str, fields: dict) -> tuple[int, dict | str]:
    body = urlencode(fields).encode("utf-8")
    req = Request(
        URL + path,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(raw)
            except json.JSONDecodeError:
                return r.status, raw
    except HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return e.code, body
    except (URLError, socket.timeout) as e:
        return 0, f"network: {e}"


CASE1 = """CASE 1: EPILEPSY CLASSIFICATION
Patient: 28-year-old female
Chief Complaint: Recurrent episodes of altered awareness

History: 6-month history of episodes beginning with sudden epigastric rising
sensation, followed by behavioral arrest, oral automatisms (lip smacking,
chewing), and bilateral hand automatisms. Episodes last 1-2 minutes.
Post-ictal confusion for 5-10 minutes. Occurs 2-3 times weekly. No
tonic-clonic activity reported.

EEG Findings: Interictal left temporal sharp waves (F7/T3). Ictal recording
shows rhythmic theta activity originating from left temporal region.

Imaging: MRI brain shows left hippocampal sclerosis with volume loss and
increased T2 signal.

Medication Trial: Failed levetiracetam 1500mg BID (breakthrough seizures
2-3x/week).

Family History: Mother with epilepsy (unspecified type).
"""

NEGATIVE_CONTROL = """Patient: 60-year-old male
Chief Complaint: Routine annual visit.

History: No new neurologic symptoms. No seizures, no headaches, no syncope.
Medication list reviewed and unchanged. Vitals stable.

Imaging: None performed at this visit.
"""


def case_tests() -> list[tuple[str, dict]]:
    tests: list[tuple[str, dict]] = []
    tests.append((
        "1. Rich epilepsy case (free text, classification)",
        {
            "prompt": (
                "Classify the seizure type per ILAE 2017, evaluate the EEG/MRI/"
                "treatment evidence, and recommend next steps. Cite guidelines if "
                "you use any."
            ),
            "analysisType": "classification",
            "specialty": "epilepsy",
            "directText": CASE1,
            "userId": "ai-quality-harness",
        },
    ))
    tests.append((
        "2. Negative control: routine visit, no MRI",
        {
            "prompt": (
                "Classify whether documentation supports epilepsy workup. Use "
                "YES/NO/NOT_PERFORMED/INSUFFICIENT_NOTE."
            ),
            "analysisType": "classification",
            "specialty": "epilepsy",
            "directText": NEGATIVE_CONTROL,
            "userId": "ai-quality-harness",
        },
    ))

    csv_path = ROOT / "test_patient_data.csv"
    if csv_path.exists():
        with csv_path.open() as f:
            rows = list(csv.DictReader(f))
        for r in rows[:3]:
            text = "\n".join(f"- {k}: {v}" for k, v in r.items())
            tests.append((
                f"3. CSV patient {r.get('Patient_ID', '?')} ({r.get('Seizure_Type','?')})",
                {
                    "prompt": (
                        "Given this patient summary, classify the seizure type, "
                        "comment on whether the current medication regimen looks "
                        "adequate, and suggest next workup."
                    ),
                    "analysisType": "diagnosis",
                    "specialty": "epilepsy",
                    "directText": text,
                    "userId": "ai-quality-harness",
                },
            ))
    return tests


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / f"tests/ai_quality_{int(time.time())}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with urlopen(URL + "/health", timeout=30) as r:
            health_status: int = r.status
            health: dict | str = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        health_status, health = 0, f"health-check failed: {e}"

    lines: list[str] = []
    lines.append(f"# MedAI /analyze quality run — {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append(f"- Service: `{URL}`")
    lines.append(f"- HTTP timeout: {TIMEOUT}s")
    lines.append(f"- /health status: {health_status}")
    if isinstance(health, dict):
        lines.append("- /health digest:")
        for k in ("model_loaded", "model_name", "device", "cuda_available",
                  "rag_backend_ready", "medai_require_gpu",
                  "inference_signals", "queue_size", "load_error"):
            if k in health:
                lines.append(f"  - `{k}`: {health[k]}")
    else:
        lines.append(f"- /health raw: {health}")
    lines.append("")
    lines.append("---")
    lines.append("")

    tests = case_tests()
    for idx, (title, fields) in enumerate(tests, 1):
        print(f"[{idx}/{len(tests)}] {title}", flush=True)
        t0 = time.time()
        status, body = _post_form("/analyze", fields)
        dt = time.time() - t0

        lines.append(f"## {title}")
        lines.append(f"- HTTP: `{status}`  •  elapsed: `{dt:.1f}s`")
        lines.append("")
        lines.append("**Prompt sent**:")
        lines.append("```")
        lines.append(fields["prompt"])
        lines.append("```")
        lines.append("")
        lines.append("**Input text**:")
        lines.append("```")
        lines.append(fields["directText"].strip())
        lines.append("```")
        lines.append("")
        lines.append("**Response (verbatim)**:")
        if isinstance(body, dict):
            response_text = body.get("response") or body.get("result") or body.get("analysis") or ""
            lines.append("```")
            lines.append(response_text if response_text else json.dumps(body, indent=2)[:5000])
            lines.append("```")
            if response_text:
                lines.append("")
                lines.append("<details><summary>Full JSON (debug)</summary>")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps({k: v for k, v in body.items() if k != "response"}, indent=2)[:4000])
                lines.append("```")
                lines.append("")
                lines.append("</details>")
        else:
            lines.append("```")
            lines.append(str(body)[:5000])
            lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_path.write_text("\n".join(lines))
    print(f"\nReport written to {out_path}")
    print(f"   {len(tests)} cases, /health HTTP {health_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
