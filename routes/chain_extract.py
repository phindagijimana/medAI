"""LEO chain extraction + evidence ledger + review queue (P1.5 API).

Endpoints (all under ``/extract``):

    POST /extract/chain
        Run the LEO chain (Prepare→Reason→Verify→Publish) on one note;
        optional ledger persist.

    GET /extract/ledger/counts
        Aggregate ledger statistics.

    GET /extract/review/pending
        List claims awaiting human adjudication.

    POST /extract/review/<claim_id>/resolve
        accept_as_is | edit | reject — writes adjudicated row or audit event.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

logger = logging.getLogger(__name__)

chain_bp = Blueprint("chain_extract", __name__, url_prefix="/extract")


def _bad(msg: str, status: int = 400) -> tuple[Response, int]:
    return jsonify({"error": msg}), status


def _no_cache(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp


def _repo_root() -> Path:
    return Path(os.environ.get("APP_HOME", os.getcwd()))


def _ledger_db_path() -> Path:
    raw = os.environ.get("MEDAI_LEDGER_DB", "")
    if raw:
        return Path(raw)
    return _repo_root() / "data" / "ledger" / "evidence.sqlite"


def _get_ledger():
    from services.ledger import EvidenceLedger

    path = _ledger_db_path()
    ledger = getattr(current_app, "_evidence_ledger", None)
    if ledger is None or getattr(ledger, "db_path", None) != path:
        ledger = EvidenceLedger(path)
        current_app._evidence_ledger = ledger  # type: ignore[attr-defined]
    return ledger


def _get_pipeline():
    pipe = getattr(current_app, "_chain_pipeline", None)
    if pipe is None:
        from services.chain_pipeline import ChainPipeline

        # LLM channel is opt-in: MEDAI_LEO_LLM=live loads Med42-8B (GPU);
        # MEDAI_LEO_LORA_DIR selects a tuned adapter; MEDAI_LEO_ARM the
        # base-model prompt arm.  Default is specialist-only (EpExtra + ontology).
        reasoner = None
        if os.environ.get("MEDAI_LEO_LLM", "off").lower() == "live":
            from services.chain_llm import load_live_reasoner
            reasoner = load_live_reasoner(
                arm=os.environ.get("MEDAI_LEO_ARM", "M3"),
                adapter_dir=os.environ.get("MEDAI_LEO_LORA_DIR", ""),
            )
        pipe = ChainPipeline(llm_reasoner=reasoner)
        current_app._chain_pipeline = pipe  # type: ignore[attr-defined]
    return pipe


@chain_bp.route("/chain", methods=["POST"])
def extract_chain() -> Any:
    payload = request.get_json(silent=True) or {}
    src = payload.get("source_text")
    document_id = payload.get("document_id") or f"doc-{uuid.uuid4().hex[:12]}"
    doc_date = payload.get("doc_date") or date.today().isoformat()
    persist = bool(payload.get("persist", True))

    if not src or not isinstance(src, str):
        return _bad("`source_text` (non-empty string) is required")

    try:
        pipeline = _get_pipeline()
        ledger = _get_ledger() if persist else None
        stats, claims = pipeline.extract(
            src.strip(),
            document_id=str(document_id),
            doc_date=str(doc_date),
            ledger=ledger,
            return_claims=True,
        )
    except Exception as e:
        logger.exception("chain extract failed")
        return _bad(f"chain extraction failed: {type(e).__name__}: {e}", 503)

    body = {
        "document_id": document_id,
        "stats": {
            "n_claims_emitted": stats.n_claims_emitted,
            "n_accepted": stats.n_accepted,
            "n_review": stats.n_review,
            "n_rejected": stats.n_rejected,
            "reasons": stats.reasons,
            "llm": {
                "available": stats.llm_available,
                "agree": stats.n_llm_agree,
                "disagree": stats.n_llm_disagree,
                "specialist_only": stats.n_specialist_only,
                "llm_only": stats.n_llm_only,
                "llm_unsupported": stats.n_llm_unsupported,
            },
        },
        "claims": [c.model_dump(mode="json") for c in claims],
        "ledger_path": str(_ledger_db_path()) if persist else None,
    }
    resp = jsonify(body)
    return _no_cache(resp), 200


@chain_bp.route("/ledger/counts", methods=["GET"])
def ledger_counts() -> Any:
    try:
        counts = _get_ledger().counts()
    except Exception as e:
        logger.exception("ledger counts failed")
        return _bad(f"ledger unavailable: {e}", 503)
    resp = jsonify({"counts": counts, "ledger_path": str(_ledger_db_path())})
    return _no_cache(resp), 200


@chain_bp.route("/review/pending", methods=["GET"])
def review_pending() -> Any:
    limit = min(int(request.args.get("limit", 100)), 500)
    try:
        items = _get_ledger().pending_reviews(limit=limit)
    except Exception as e:
        logger.exception("review pending failed")
        return _bad(f"ledger unavailable: {e}", 503)
    resp = jsonify({"pending": items, "count": len(items)})
    return _no_cache(resp), 200


@chain_bp.route("/review/<claim_id>/resolve", methods=["POST"])
def review_resolve(claim_id: str) -> Any:
    from schema.claim import Claim, ReasonCode, ValidatorVerdict

    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    reviewer = payload.get("reviewer") or "anonymous_reviewer"
    notes = payload.get("notes") or ""

    if action not in ("accept_as_is", "edit", "reject"):
        return _bad("`action` must be accept_as_is, edit, or reject")

    ledger = _get_ledger()
    pending = ledger.pending_reviews(limit=500)
    match = next((p for p in pending if p.get("claim_id") == claim_id), None)
    if match is None:
        return _bad(f"claim_id {claim_id!r} not found in pending review queue", 404)

    resolved_claim: Claim | None = None
    if action in ("accept_as_is", "edit"):
        if action == "edit":
            edited = payload.get("claim")
            if not isinstance(edited, dict):
                return _bad("`claim` (full Claim JSON) is required when action=edit")
            resolved_claim = Claim.model_validate(edited)
        else:
            resolved_claim = Claim.model_validate(match)
        resolved_claim = resolved_claim.model_copy(
            update={
                "validator_verdict": ValidatorVerdict.ACCEPT,
                "reason_codes": [ReasonCode.ACCEPT_UNANIMOUS],
            },
        )

    try:
        ledger.resolve_review(
            claim_id,
            action=action,
            reviewer=str(reviewer),
            resolved_claim=resolved_claim,
            notes=str(notes),
        )
    except Exception as e:
        logger.exception("review resolve failed")
        return _bad(f"resolve failed: {type(e).__name__}: {e}", 400)

    resp = jsonify({"ok": True, "claim_id": claim_id, "action": action})
    return _no_cache(resp), 200
