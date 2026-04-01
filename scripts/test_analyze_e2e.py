#!/usr/bin/env python3
"""
End-to-end test: POST /analyze via Flask test client (loads app + model if available).

Run from repo root:
  APP_HOME=$(pwd) python3 scripts/test_analyze_e2e.py

Exit codes:
  0 — HTTP 200 and JSON success, or 503 with clear model-missing message
  1 — unexpected failure
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("APP_HOME", ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> int:
    # Import after APP_HOME
    from app import app

    payload = {
        "prompt": "Provide a brief clinical classification of this case.",
        "analysisType": "classification",
        "directText": (
            "72-year-old with sudden right hemiparesis and aphasia. Last known well 2 hours ago. "
            "NIHSS 14. CT no hemorrhage. Discuss acute ischemic stroke management including IV alteplase."
        ),
        "specialty": "neurology",
        "userId": "e2e-test",
    }

    with app.test_client() as client:
        resp = client.post("/analyze", data=payload)

    print("HTTP", resp.status_code)
    try:
        data = resp.get_json()
    except Exception:
        print(resp.data[:500])
        return 1

    if resp.status_code == 503:
        err = (data or {}).get("error", "")
        print("Model not available (expected in CI without GPU/model):", err[:200])
        return 0

    if resp.status_code != 200:
        print(json.dumps(data, indent=2)[:800])
        return 1

    if not data.get("success"):
        print(json.dumps(data, indent=2)[:800])
        return 1

    text = (data.get("analysis") or "")[:800]
    print("OK — success=True")
    print("Analysis preview:", text[:600] if text else "(empty)")
    # RAG/few-shot may mention stroke or thrombolysis when model runs
    return 0


if __name__ == "__main__":
    sys.exit(main())
