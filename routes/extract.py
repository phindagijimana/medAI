"""POST /extract — paper-track structured phenotype extraction endpoint.

Wraps `services.router.extract_phenotype` with a small Flask surface so
external researchers can hit MedAI-EPI programmatically. Not a chat
interface — one call = one document → one `EpilepsyPhenotype` JSON.

Request body (JSON):
    {
      "source_text": "…full clinical document text…",       (required)
      "doc_type":   "mri_report",                            (required; see DocumentType)
      "arm":        "M2",                                    (required; "M0" | "M1" | "M2")
      "doc_id":     "MRI-0001",                              (optional; auto-generated if absent)
      "patient_id": "P-0001",                                (optional)
      "doc_date":   "2025-06-14",                            (optional ISO date; default today)
      "icd10cm_codes": ["G40.909"],                          (optional)
      "snomed_ct_codes": []                                  (optional)
    }

Response (JSON):
    {
      "phenotype":  { …EpilepsyPhenotype v0.2.1 JSON… },     # None per-module if not applicable
      "manifests":  [ …one per extracted module… ],
      "summary":    { module → {raw_valid, final_valid, repair_method, duration_s, tokens} },
      "schema_version": "v0.2.1"
    }

Only accepts POST. All responses set `Cache-Control: no-store`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

logger = logging.getLogger(__name__)

extract_bp = Blueprint("extract", __name__, url_prefix="/extract")


def _bad(msg: str, status: int = 400) -> tuple[Response, int]:
    return jsonify({"error": msg}), status


def _no_cache(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp


@extract_bp.route("", methods=["POST"])
def extract() -> Any:
    # Lazy imports so this module can load even if paper-track deps or the
    # loaded Med42 backend aren't available at Flask import time.
    try:
        from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION
        from services.extract import DecodingConfig
        from services.router import extract_phenotype
    except ImportError as e:
        logger.exception("paper-track imports failed")
        return _bad(f"paper-track modules unavailable: {e}", 503)

    payload = request.get_json(silent=True) or {}
    src = payload.get("source_text")
    doc_type_str = payload.get("doc_type")
    arm = payload.get("arm", "M2")

    if not src or not isinstance(src, str):
        return _bad("`source_text` (non-empty string) is required")
    if not doc_type_str:
        return _bad("`doc_type` is required (e.g. 'mri_report', 'eeg_report', 'progress_note')")
    if arm not in ("M0", "M1", "M2"):
        return _bad("`arm` must be one of 'M0', 'M1', 'M2'")

    try:
        doc_type = DocumentType(doc_type_str)
    except ValueError:
        allowed = [d.value for d in DocumentType]
        return _bad(f"invalid doc_type {doc_type_str!r}. Allowed: {allowed}")

    # Doc metadata
    doc_id = payload.get("doc_id") or f"api-{uuid.uuid4().hex[:12]}"
    patient_id = payload.get("patient_id") or doc_id
    doc_date_str = payload.get("doc_date")
    try:
        doc_date = date.fromisoformat(doc_date_str) if doc_date_str else date.today()
    except ValueError:
        return _bad(f"invalid doc_date {doc_date_str!r} (expected ISO YYYY-MM-DD)")

    icd = payload.get("icd10cm_codes") or []
    snomed = payload.get("snomed_ct_codes") or []
    if not isinstance(icd, list) or not isinstance(snomed, list):
        return _bad("`icd10cm_codes` and `snomed_ct_codes` must be lists of strings")

    doc = DocumentMetadata(
        doc_id=doc_id, doc_type=doc_type, doc_date=doc_date,
        patient_id=patient_id, icd10cm_codes=icd, snomed_ct_codes=snomed,
    )

    # Backend selection — Med42 if loaded on the app, else 503
    backend = getattr(current_app, "med42_backend", None)
    if backend is None:
        return _bad(
            "Med42 backend not attached to the Flask app. See the deployment "
            "guide for setting `app.med42_backend = Med42Backend(...)` after "
            "the model finishes loading.", 503,
        )

    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(payload.get("max_new_tokens", 1024)),
        seed=int(payload.get("seed", 0)),
    )

    t0 = datetime.utcnow()
    try:
        result = extract_phenotype(
            doc=doc, source_text=src, model_backend=backend,
            arm=arm, schema_version=SCHEMA_VERSION,
            decoding=decoding, write_manifests=True,
        )
    except Exception as e:
        logger.exception("extract_phenotype failed")
        return _bad(f"extraction failure: {type(e).__name__}: {e}", 500)

    resp_json = {
        "phenotype": result.phenotype.model_dump(mode="json"),
        "manifests": [
            {
                "module": mname,
                "manifest_run_id": r.manifest.run_id,
                "raw_valid": r.manifest.raw_valid,
                "final_valid": r.manifest.final_valid,
                "repair_method": r.manifest.repair_method,
                "duration_s": r.manifest.duration_s,
                "tokens_generated": r.manifest.raw_response_tokens,
                "prompt_id": r.manifest.prompt_id,
            }
            for mname, r in result.per_module.items()
        ],
        "summary": result.summary(),
        "schema_version": SCHEMA_VERSION,
        "arm": arm,
        "doc_type": doc_type.value,
        "processing_time_s": (datetime.utcnow() - t0).total_seconds(),
    }
    return _no_cache(jsonify(resp_json))


@extract_bp.route("/health", methods=["GET"])
def extract_health() -> Any:
    try:
        from schema import SCHEMA_VERSION
        from services.prompt_registry import all_prompt_ids
    except ImportError as e:
        return jsonify({"ok": False, "error": str(e)}), 503

    backend = getattr(current_app, "med42_backend", None)
    return jsonify({
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "prompts_registered": all_prompt_ids(),
        "med42_backend_attached": backend is not None,
        "backend_model": getattr(backend, "model_name", None) if backend else None,
    })
