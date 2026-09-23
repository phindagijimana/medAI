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

    # Backend selection — trigger lazy Med42 load if not yet started
    ensure = getattr(current_app, "ensure_med42_loaded", None)
    if callable(ensure):
        status = ensure()
    else:
        status = "not_available"
    backend = getattr(current_app, "med42_backend", None)
    if backend is None:
        return _bad(
            f"Med42 backend not yet ready (status={status!r}). The model loads "
            "on first request to /extract/*; retry in 30–60 s.",
            503,
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
        from schema import SCHEMA_VERSION, DocumentType
        from services.prompt_registry import all_prompt_ids
    except ImportError as e:
        return jsonify({"ok": False, "error": str(e)}), 503

    backend = getattr(current_app, "med42_backend", None)
    load_status = getattr(current_app, "med42_backend_status", "unknown")
    return jsonify({
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "prompts_registered": all_prompt_ids(),
        "doc_types_supported": [d.value for d in DocumentType],
        "med42_backend_attached": backend is not None,
        "med42_load_status": load_status,   # not_started / starting / loading / ready / load_failed:…
        "backend_model": getattr(backend, "model_name", None) if backend else None,
    })


# ---------------------------------------------------------------------------
# Doc-type auto-detection (UX §1.1 in docs/APP_UX_IMPROVEMENTS.md)
# ---------------------------------------------------------------------------

# Keyword signatures per doc type — ranked by specificity. First strong hit wins.
_DOC_TYPE_SIGNATURES: list[tuple[str, tuple[str, ...], str]] = [
    ("mri_report", (
        "MRI BRAIN", "MRI OF THE BRAIN", "T1 WEIGHTED", "FLAIR",
        "TECHNIQUE:", "IMPRESSION:", "hippocampal sclerosis",
        "focal cortical dysplasia", "MRI-negative",
    ), "radiology-report boilerplate + brain-imaging findings"),
    ("eeg_report", (
        "EEG STUDY", "video-EEG", "video EEG", "EMU MONITORING",
        "posterior dominant rhythm", "epileptiform discharges",
        "ictal onset", "electrographic seizures",
    ), "EEG-report boilerplate + neurophysiology terms"),
    ("presurgical_evaluation", (
        "PRESURGICAL", "PRE-SURGICAL EVALUATION", "epilepsy monitoring unit summary",
        "epilepsy surgery conference", "recommended for surgery",
        "concordant for", "discordant for",
    ), "presurgical / EMU / surgery-conference vocabulary"),
    ("emu_discharge", (
        "EMU DISCHARGE", "DISCHARGE SUMMARY", "admitted to the EMU",
        "seizures were captured",
    ), "EMU discharge language"),
    ("procedure_seeg", (
        "SEEG", "stereo-EEG", "stereo EEG", "depth electrodes",
        "subdural grid",
    ), "stereo-EEG procedure documentation"),
    ("procedure_resection", (
        "temporal lobectomy", "anterior temporal lobectomy",
        "amygdalohippocampectomy", "resection", "corticectomy",
    ), "resection procedure documentation"),
    ("procedure_neurostim", (
        "vagus nerve stimulation", "VNS", "responsive neurostimulation",
        "RNS", "deep brain stimulation", "DBS",
    ), "neurostimulation procedure documentation"),
    ("initial_consult", (
        "initial epilepsy consult", "initial consultation",
        "seen in initial consultation",
    ), "initial-consult heading"),
    ("progress_note", (
        "Dear Dr", "Dear doctor", "I reviewed", "follow-up",
        "clinic note", "review of systems",
    ), "clinic-letter or progress-note salutation"),
]


def _detect_doc_type(text: str) -> dict[str, Any]:
    """Deterministic keyword-based doc-type classifier.

    Not authoritative — the caller must confirm. Returns:
      {
        "doc_type": <best guess string or None>,
        "confidence": "low" | "medium" | "high",
        "reasons": [ ...matching phrases... ],
        "alternatives": [ ...other doc_types that matched at all... ]
      }
    """
    if not text or not isinstance(text, str):
        return {"doc_type": None, "confidence": "low", "reasons": [],
                "alternatives": [], "detail": "empty text"}

    lower = text.lower()
    scored: list[tuple[str, list[str], str]] = []
    for dt, patterns, why in _DOC_TYPE_SIGNATURES:
        hits = [p for p in patterns if p.lower() in lower]
        if hits:
            scored.append((dt, hits, why))

    if not scored:
        return {
            "doc_type": None, "confidence": "low", "reasons": [],
            "alternatives": [], "detail": "no signature matched",
        }

    # Sort by hit count then by rank in the signature list (earlier = more specific)
    scored.sort(key=lambda t: (-len(t[1]),
                                [d for d, *_ in _DOC_TYPE_SIGNATURES].index(t[0])))
    top = scored[0]
    hit_count = len(top[1])
    if hit_count >= 3:
        conf = "high"
    elif hit_count == 2:
        conf = "medium"
    else:
        conf = "low"

    return {
        "doc_type": top[0],
        "confidence": conf,
        "reasons": top[1],
        "reason_rationale": top[2],
        "alternatives": [s[0] for s in scored[1:5]],
    }


# ---------------------------------------------------------------------------
# /extract/batch — many docs in one call (synchronous)
# ---------------------------------------------------------------------------


@extract_bp.route("/batch", methods=["POST"])
def extract_batch() -> Any:
    """Batch extraction. Body:
        {
          "documents": [
            {"doc_id": "...", "source_text": "...", "doc_type": "...",
             "patient_id": "...", "doc_date": "..."},   # per-doc metadata
            ...
          ],
          "arm": "M0" | "M1" | "M2",
          "max_new_tokens": 1024,          # optional
          "seed": 0,                        # optional
          "prompt_version": "v1"            # optional
        }

    Returns a list of phenotype records + per-doc summary. Runs serially
    on a single Med42 load. Suitable for tens of documents; for hundreds,
    submit an SLURM sweep instead.
    """
    try:
        from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION
        from services.extract import DecodingConfig
        from services.router import extract_phenotype
    except ImportError as e:
        return _bad(f"paper-track modules unavailable: {e}", 503)

    payload = request.get_json(silent=True) or {}
    documents = payload.get("documents") or []
    arm = payload.get("arm", "M2")
    if not isinstance(documents, list) or not documents:
        return _bad("`documents` must be a non-empty list")
    if arm not in ("M0", "M1", "M2"):
        return _bad("`arm` must be one of 'M0', 'M1', 'M2'")

    ensure = getattr(current_app, "ensure_med42_loaded", None)
    status = ensure() if callable(ensure) else "not_available"
    backend = getattr(current_app, "med42_backend", None)
    if backend is None:
        return _bad(
            f"Med42 backend not yet ready (status={status!r}). Retry after model loads.",
            503,
        )

    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(payload.get("max_new_tokens", 1024)),
        seed=int(payload.get("seed", 0)),
    )
    prompt_version = payload.get("prompt_version", "v1")

    results = []
    t_all_start = datetime.utcnow()
    for i, item in enumerate(documents):
        src = item.get("source_text")
        dt_str = item.get("doc_type")
        if not src or not dt_str:
            results.append({"index": i, "error": "missing source_text or doc_type"})
            continue
        try:
            doc_type = DocumentType(dt_str)
        except ValueError:
            results.append({"index": i, "error": f"invalid doc_type {dt_str!r}"})
            continue

        doc_id = item.get("doc_id") or f"batch-{i:04d}-{uuid.uuid4().hex[:6]}"
        patient_id = item.get("patient_id") or doc_id
        dd = item.get("doc_date")
        try:
            doc_date = date.fromisoformat(dd) if dd else date.today()
        except ValueError:
            results.append({"index": i, "error": f"invalid doc_date {dd!r}"})
            continue

        doc = DocumentMetadata(
            doc_id=doc_id, doc_type=doc_type, doc_date=doc_date,
            patient_id=patient_id,
            icd10cm_codes=item.get("icd10cm_codes") or [],
            snomed_ct_codes=item.get("snomed_ct_codes") or [],
        )

        t0 = datetime.utcnow()
        try:
            result = extract_phenotype(
                doc=doc, source_text=src, model_backend=backend,
                arm=arm, schema_version=SCHEMA_VERSION,
                decoding=decoding, write_manifests=True,
            )
            elapsed = (datetime.utcnow() - t0).total_seconds()
            results.append({
                "index": i, "doc_id": doc_id, "arm": arm,
                "processing_time_s": round(elapsed, 2),
                "summary": result.summary(),
                "phenotype": result.phenotype.model_dump(mode="json"),
            })
        except Exception as e:
            elapsed = (datetime.utcnow() - t0).total_seconds()
            results.append({
                "index": i, "doc_id": doc_id, "arm": arm,
                "processing_time_s": round(elapsed, 2),
                "error": f"{type(e).__name__}: {e}",
            })

    total_elapsed = (datetime.utcnow() - t_all_start).total_seconds()
    resp = jsonify({
        "n_documents": len(documents),
        "arm": arm,
        "prompt_version": prompt_version,
        "schema_version": SCHEMA_VERSION,
        "total_time_s": round(total_elapsed, 2),
        "results": results,
    })
    return _no_cache(resp)


# ---------------------------------------------------------------------------
# /extract/registry — browse the prompt registry
# ---------------------------------------------------------------------------


@extract_bp.route("/registry", methods=["GET"])
def registry_index() -> Any:
    """List all registered prompt templates with metadata."""
    try:
        from services.prompt_registry import _REGISTRY
    except ImportError as e:
        return _bad(f"prompt registry unavailable: {e}", 503)

    entries = []
    for pid, p in sorted(_REGISTRY.items()):
        entries.append({
            "prompt_id": p.prompt_id,
            "doc_type": p.doc_type.value,
            "module_name": p.module_name,
            "arm": p.arm,
            "version": p.version,
            "n_few_shot": len(p.few_shot),
            "few_shot_ids": [ex.example_id for ex in p.few_shot],
            "rationale": p.rationale[:200],
        })
    return jsonify({"n_prompts": len(entries), "prompts": entries})


@extract_bp.route("/registry/<prompt_id>", methods=["GET"])
def registry_show(prompt_id: str) -> Any:
    """Return one prompt template in full (task instruction, few-shot content).
    Intended for auditors / reviewers who want to see the exact prompt without cloning the repo."""
    try:
        from services.prompt_registry import get as get_prompt
    except ImportError as e:
        return _bad(f"prompt registry unavailable: {e}", 503)
    try:
        p = get_prompt(prompt_id)
    except KeyError:
        return _bad(f"unknown prompt_id {prompt_id!r}", 404)
    return jsonify({
        "prompt_id": p.prompt_id,
        "doc_type": p.doc_type.value,
        "module_name": p.module_name,
        "arm": p.arm,
        "version": p.version,
        "system_prompt": p.system_prompt,
        "task_instruction": p.task_instruction,
        "output_directives": p.output_directives,
        "rationale": p.rationale,
        "few_shot": [
            {"example_id": ex.example_id,
             "document_excerpt": ex.document_excerpt,
             "expected_json_keys": list(ex.expected_json.keys())
                                    if isinstance(ex.expected_json, dict) else None}
            for ex in p.few_shot
        ],
    })


@extract_bp.route("/detect_doc_type", methods=["POST"])
def detect_doc_type() -> Any:
    """Suggest a `doc_type` for a pasted document. Not authoritative — the
    caller confirms before calling `/extract`. Deterministic; no LLM needed."""
    payload = request.get_json(silent=True) or {}
    text = payload.get("source_text") or payload.get("text")
    if not text:
        return _bad("`source_text` (non-empty string) is required")
    result = _detect_doc_type(text)
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "no-store"
    return resp
