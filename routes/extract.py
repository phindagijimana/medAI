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


# ---------------------------------------------------------------------------
# CSV output — text OR CSV rows in, structured long-format + wide-format out.
# See services/tabular.py for the row model.
# ---------------------------------------------------------------------------


def _guess_doc_type(text: str) -> str:
    result = _detect_doc_type(text)
    return result.get("doc_type") or "progress_note"


def _extract_one(*, source_text: str, doc_id: str, patient_id: str,
                 doc_date_iso: str, doc_type_str: str, arm: str,
                 visit_date_iso: str | None, chunk_index: int | None,
                 backend, decoding_max_new_tokens: int, seed: int) -> tuple:
    """Run extraction on one document. Returns (phenotype_or_None, error_or_None,
    visit_date_iso, chunk_index) — always adds a doc_id."""
    from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION
    from services.extract import DecodingConfig
    from services.router import extract_phenotype

    try:
        dt = DocumentType(doc_type_str)
    except ValueError:
        return None, f"invalid doc_type {doc_type_str!r}", visit_date_iso, chunk_index
    try:
        d_date = date.fromisoformat(doc_date_iso) if doc_date_iso else date.today()
    except ValueError:
        return None, f"invalid doc_date {doc_date_iso!r}", visit_date_iso, chunk_index

    doc = DocumentMetadata(
        doc_id=doc_id, doc_type=dt, doc_date=d_date, patient_id=patient_id,
    )
    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=decoding_max_new_tokens, seed=seed,
    )
    try:
        result = extract_phenotype(
            doc=doc, source_text=source_text, model_backend=backend,
            arm=arm, schema_version=SCHEMA_VERSION,
            decoding=decoding, write_manifests=True,
        )
        return result.phenotype, None, visit_date_iso, chunk_index
    except Exception as e:
        logger.exception("extract_one failed")
        return None, f"{type(e).__name__}: {e}", visit_date_iso, chunk_index


def _extract_long(*, source_text, doc_id, patient_id, doc_date_iso,
                  doc_type_str, arm, visit_date_iso,
                  backend, max_new_tokens, seed):
    """Chunk + per-module extract_module_long + assemble a top-level phenotype.
    Returns either (EpilepsyPhenotype, meta_dict) on success or an error
    string on failure."""
    from schema import (
        DocumentMetadata, DocumentType, EpilepsyPhenotype, SCHEMA_VERSION,
        modules_for,
    )
    from services.chunker import chunk_text
    from services.extract import DecodingConfig, extract_module_long
    from services.prompt_registry import resolve
    from services.router import MODULE_CLASSES

    try:
        dt = DocumentType(doc_type_str)
    except ValueError:
        return f"invalid doc_type {doc_type_str!r}"
    try:
        d_date = date.fromisoformat(doc_date_iso) if doc_date_iso else date.today()
    except ValueError:
        return f"invalid doc_date {doc_date_iso!r}"

    doc = DocumentMetadata(
        doc_id=doc_id, doc_type=dt, doc_date=d_date, patient_id=patient_id,
    )
    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=max_new_tokens, seed=seed,
    )

    chunks = chunk_text(source_text)
    if not chunks:
        return "chunker produced no chunks"

    applicable = sorted(modules_for(dt))
    phenotype_kwargs: dict = {"document": doc}
    n_chunks_total = len(chunks)
    per_module_ok = {}
    for module_name in applicable:
        module_cls = MODULE_CLASSES.get(module_name)
        if module_cls is None:
            continue
        try:
            prompt = resolve(module_name, arm, "v1")
        except KeyError:
            continue
        try:
            result = extract_module_long(
                module_cls=module_cls, prompt=prompt,
                chunks=chunks, source_doc_meta=doc,
                model_backend=backend, decoding=decoding,
                schema_version=SCHEMA_VERSION,
            )
        except Exception as e:
            logger.exception("extract_module_long failed for %s", module_name)
            per_module_ok[module_name] = False
            continue
        # Persist per-chunk manifests
        for m in result.manifests:
            try:
                m.write()
            except Exception:
                pass
        if result.module is not None:
            phenotype_kwargs[module_name] = result.module
            per_module_ok[module_name] = True
        else:
            per_module_ok[module_name] = False

    phen = EpilepsyPhenotype(**phenotype_kwargs)
    return (phen, {"n_chunks": n_chunks_total, "per_module_ok": per_module_ok})


@extract_bp.route("/stream", methods=["POST"])
def extract_stream() -> Any:
    """Streaming variant of POST /extract — same request shape, but the
    response body is newline-delimited JSON (NDJSON): one line per module
    as it completes, plus a final line with the assembled phenotype.

    Each line is a self-contained JSON object with an `event` field
    ("module_start" | "module_done" | "final"). The UI uses this to render
    per-module progress instead of blocking on the full 6-module extraction.
    """
    try:
        from schema import DocumentMetadata, DocumentType, SCHEMA_VERSION
        from services.extract import DecodingConfig
        from services.router import extract_phenotype_streaming
    except ImportError as e:
        return _bad(f"paper-track modules unavailable: {e}", 503)

    payload = request.get_json(silent=True) or {}
    src = payload.get("source_text")
    doc_type_str = payload.get("doc_type")
    arm = payload.get("arm", "M2")

    if not src or not isinstance(src, str):
        return _bad("`source_text` (non-empty string) is required")
    if not doc_type_str:
        return _bad("`doc_type` is required")
    if arm not in ("M0", "M1", "M2"):
        return _bad("`arm` must be one of 'M0', 'M1', 'M2'")
    try:
        doc_type = DocumentType(doc_type_str)
    except ValueError:
        allowed = [d.value for d in DocumentType]
        return _bad(f"invalid doc_type {doc_type_str!r}. Allowed: {allowed}")

    doc_id = payload.get("doc_id") or f"api-{uuid.uuid4().hex[:12]}"
    patient_id = payload.get("patient_id") or doc_id
    try:
        d_date = date.fromisoformat(payload["doc_date"]) if payload.get("doc_date") else date.today()
    except ValueError:
        return _bad(f"invalid doc_date")

    icd = payload.get("icd10cm_codes") or []
    snomed = payload.get("snomed_ct_codes") or []
    doc = DocumentMetadata(
        doc_id=doc_id, doc_type=doc_type, doc_date=d_date,
        patient_id=patient_id, icd10cm_codes=icd, snomed_ct_codes=snomed,
    )

    ensure = getattr(current_app, "ensure_med42_loaded", None)
    if callable(ensure):
        status = ensure()
    else:
        status = "not_available"
    backend = getattr(current_app, "med42_backend", None)
    if backend is None:
        return _bad(f"Med42 backend not yet ready (status={status!r}); retry in 30–60 s.", 503)

    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(payload.get("max_new_tokens", 1024)),
        seed=int(payload.get("seed", 0)),
    )

    def stream():
        import json as _j
        try:
            for evt in extract_phenotype_streaming(
                doc=doc, source_text=src, model_backend=backend,
                arm=arm, schema_version=SCHEMA_VERSION,
                decoding=decoding, write_manifests=True,
            ):
                yield _j.dumps(evt) + "\n"
        except Exception as e:
            logger.exception("stream extraction failed")
            yield _j.dumps({"event": "error", "error": f"{type(e).__name__}: {e}"}) + "\n"

    return Response(stream(), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-store",
                              "X-Accel-Buffering": "no"})


@extract_bp.route("/long", methods=["POST"])
def extract_long() -> Any:
    """Chunk-and-merge extraction for a single long document.

    Same request/response shape as POST /extract, but chunks the source_text
    by clinical section + paragraph, runs each applicable module on every
    chunk via extract_module_long, and merges with services.merge.merge_modules.
    Use when the source text is longer than the model's context (~8000 chars)
    or when the /extract/ui "auto-chunk" checkbox is enabled.
    """
    try:
        from schema import DocumentType, SCHEMA_VERSION
    except ImportError as e:
        return _bad(f"paper-track modules unavailable: {e}", 503)

    payload = request.get_json(silent=True) or {}
    src = payload.get("source_text")
    doc_type_str = payload.get("doc_type")
    arm = payload.get("arm", "M2")

    if not src or not isinstance(src, str):
        return _bad("`source_text` (non-empty string) is required")
    if not doc_type_str:
        return _bad("`doc_type` is required")
    if arm not in ("M0", "M1", "M2"):
        return _bad("`arm` must be one of 'M0', 'M1', 'M2'")

    doc_id = payload.get("doc_id") or f"api-{uuid.uuid4().hex[:12]}"
    patient_id = payload.get("patient_id") or doc_id
    doc_date_str = payload.get("doc_date") or ""

    ensure = getattr(current_app, "ensure_med42_loaded", None)
    if callable(ensure):
        status = ensure()
    else:
        status = "not_available"
    backend = getattr(current_app, "med42_backend", None)
    if backend is None:
        return _bad(
            f"Med42 backend not yet ready (status={status!r}). Retry in 30–60 s.",
            503,
        )

    max_new_tokens = int(payload.get("max_new_tokens", 1024))
    seed = int(payload.get("seed", 0))

    t0 = datetime.utcnow()
    result = _extract_long(
        source_text=src, doc_id=doc_id, patient_id=patient_id,
        doc_date_iso=doc_date_str, doc_type_str=doc_type_str, arm=arm,
        visit_date_iso=None,
        backend=backend, max_new_tokens=max_new_tokens, seed=seed,
    )
    if isinstance(result, str):
        return _bad(f"extract_long failure: {result}", 500)
    phen, meta = result

    return _no_cache(jsonify({
        "phenotype": phen.model_dump(mode="json"),
        "chunking": {
            "n_chunks": meta.get("n_chunks", 0),
            "per_module_ok": meta.get("per_module_ok", {}),
        },
        "schema_version": SCHEMA_VERSION,
        "arm": arm,
        "doc_type": doc_type_str,
        "processing_time_s": (datetime.utcnow() - t0).total_seconds(),
    }))


@extract_bp.route("/csv", methods=["POST"])
def extract_csv() -> Any:
    """Structured phenotype extraction with CSV output (long format).

    Two input shapes:
      (A) JSON:  {"source_text": "...", "doc_type": "progress_note", "arm": "M2",
                  "doc_id": "...", "patient_id": "..." (optional), "doc_date": "..." (optional)}
      (B) CSV file (multipart/form-data 'file' field, or raw text/csv body):
          columns must include a text column (default 'text'), optional
          'doc_id', 'patient_id', 'doc_date', 'visit_date', 'doc_type', 'arm'.

    Response: text/csv, long-format (one row per extracted field) with a
    `confidence` column and an `evidence_text` column next to each value.
    """
    try:
        from services.tabular import (
            LONG_COLUMNS, rows_to_csv_bytes, to_long_rows,
        )
    except ImportError as e:
        return _bad(f"tabular module unavailable: {e}", 503)

    ensure = getattr(current_app, "ensure_med42_loaded", None)
    if callable(ensure):
        ensure()
    backend = getattr(current_app, "med42_backend", None)
    if backend is None:
        status = getattr(current_app, "med42_backend_status", "unknown")
        return _bad(f"Med42 backend not yet ready (status={status!r}); retry in 30–60 s.", 503)

    max_new_tokens = int(request.args.get("max_new_tokens", 1024))
    seed = int(request.args.get("seed", 0))
    # Chunking policy: auto (default) — chunk any row whose text exceeds
    # `chunk_threshold_chars`. Force on with ?chunk=1, off with ?chunk=0.
    chunk_mode = (request.args.get("chunk") or "auto").lower()
    chunk_threshold_chars = int(request.args.get("chunk_threshold_chars", 8000))

    # ---------- Determine input mode ----------
    if request.files.get("file") is not None:
        # multipart CSV upload
        f = request.files["file"]
        raw_csv = f.read().decode("utf-8", errors="replace")
        rows_in = _parse_csv_input(raw_csv)
    elif (request.content_type or "").startswith("text/csv"):
        raw_csv = request.get_data(as_text=True) or ""
        rows_in = _parse_csv_input(raw_csv)
    else:
        payload = request.get_json(silent=True) or {}
        src = payload.get("source_text")
        if not src or not isinstance(src, str):
            return _bad("`source_text` required for single-document JSON mode")
        rows_in = [{
            "text": src,
            "doc_id": payload.get("doc_id") or f"api-{uuid.uuid4().hex[:12]}",
            "patient_id": payload.get("patient_id") or "",
            "doc_type": payload.get("doc_type") or "",
            "doc_date": payload.get("doc_date") or "",
            "visit_date": payload.get("visit_date") or "",
            "arm": payload.get("arm") or "M2",
        }]

    if not rows_in:
        return _bad("no rows to process (empty input)")

    default_arm = (rows_in[0].get("arm") or "M2").strip() or "M2"

    all_long_rows: list[dict] = []
    n_docs_ok = 0
    errors: list[dict] = []

    for i, r in enumerate(rows_in):
        text = (r.get("text") or "").strip()
        if not text:
            errors.append({"row_index": i, "error": "empty text"})
            continue

        doc_id = (r.get("doc_id") or f"row-{i:04d}").strip()
        patient_id = (r.get("patient_id") or doc_id).strip()
        doc_type_str = (r.get("doc_type") or "").strip() or _guess_doc_type(text)
        doc_date_iso = (r.get("doc_date") or "").strip()
        visit_date_iso = (r.get("visit_date") or "").strip() or None
        arm = (r.get("arm") or default_arm).strip() or "M2"

        should_chunk = (
            chunk_mode == "1"
            or (chunk_mode == "auto" and len(text) > chunk_threshold_chars)
        )

        if should_chunk:
            phen_or_err = _extract_long(
                source_text=text,
                doc_id=doc_id, patient_id=patient_id,
                doc_date_iso=doc_date_iso, doc_type_str=doc_type_str, arm=arm,
                visit_date_iso=visit_date_iso,
                backend=backend, max_new_tokens=max_new_tokens, seed=seed,
            )
            if isinstance(phen_or_err, str):
                errors.append({"row_index": i, "doc_id": doc_id, "error": phen_or_err})
                continue
            phen, chunk_meta = phen_or_err
            all_long_rows.extend(to_long_rows(phen, visit_date=visit_date_iso))
            n_docs_ok += 1
            continue

        phen, err, vdate, chunk_idx = _extract_one(
            source_text=text,
            doc_id=doc_id, patient_id=patient_id,
            doc_date_iso=doc_date_iso,
            doc_type_str=doc_type_str, arm=arm,
            visit_date_iso=visit_date_iso, chunk_index=None,
            backend=backend, decoding_max_new_tokens=max_new_tokens, seed=seed,
        )
        if err is not None or phen is None:
            errors.append({"row_index": i, "doc_id": doc_id, "error": err or "extraction failed"})
            continue

        all_long_rows.extend(to_long_rows(phen, visit_date=vdate))
        n_docs_ok += 1

    body = rows_to_csv_bytes(all_long_rows, fieldnames=LONG_COLUMNS)
    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="medai_epi_phenotype.csv"',
        "Cache-Control": "no-store",
        "X-Rows-Extracted": str(len(all_long_rows)),
        "X-Docs-Ok": str(n_docs_ok),
        "X-Docs-Err": str(len(errors)),
    }
    return Response(body, status=200, headers=headers)


def _parse_csv_input(raw: str) -> list[dict]:
    """Parse an uploaded CSV. Auto-detects text-column name from
    ('text', 'note', 'source_text', 'clinical_note') — first match wins."""
    import csv as _csv, io as _io
    if not raw or not raw.strip():
        return []
    reader = _csv.DictReader(_io.StringIO(raw))
    if reader.fieldnames is None:
        return []
    candidate_cols = ("text", "note", "source_text", "clinical_note", "content")
    text_col = None
    for c in candidate_cols:
        if c in reader.fieldnames:
            text_col = c
            break
    if text_col is None:
        # Fall back to first column if we can't identify one by name.
        text_col = reader.fieldnames[0]

    out: list[dict] = []
    for row in reader:
        r = dict(row)
        r["text"] = r.pop(text_col, "") or r.get("text", "")
        out.append(r)
    return out


# ---------------------------------------------------------------------------
# Freeform chat pass — user question grounded in the same clinical note.
# Additive: structured extraction still runs from /extract or /extract/csv;
# this endpoint answers ONE user question about ONE note, with an evidence
# quote, and returns a row that can be appended to the CSV output.
# ---------------------------------------------------------------------------


_CHAT_SYSTEM_PROMPT = (
    "You are a research phenotyping assistant for epilepsy clinical notes. "
    "You answer ONE user question about ONE clinical note, and you MUST "
    "ground your answer in a verbatim quote from the note. If the note "
    "does not address the question, answer 'not_documented' with an empty "
    "quote. Do not diagnose, treat, or opine — you extract facts only. "
    "Reply with a single JSON object and nothing else."
)

_CHAT_INSTRUCTION = (
    "Return a JSON object with EXACTLY these keys:\n"
    "  answer         — concise fact-string (≤ 40 words) or 'not_documented'\n"
    "  evidence_text  — verbatim quote from the note, or empty string\n"
    "  confidence     — one of: definite | probable | possible | unknown\n"
    "No prose outside the JSON."
)


def _parse_chat_response(raw: str) -> dict:
    """Return {answer, evidence_text, confidence} — falls back gracefully."""
    import json as _j
    import re as _re
    for candidate in (_re.search(r"\{.*\}", raw, _re.DOTALL),):
        if candidate is None:
            break
        try:
            d = _j.loads(candidate.group(0))
            return {
                "answer": str(d.get("answer") or "").strip(),
                "evidence_text": str(d.get("evidence_text") or "").strip(),
                "confidence": (d.get("confidence") or "unknown").strip().lower(),
            }
        except Exception:
            break
    return {
        "answer": raw.strip()[:400],
        "evidence_text": "",
        "confidence": "unknown",
    }


@extract_bp.route("/chat", methods=["POST"])
def extract_chat() -> Any:
    """One user question, one note, one grounded answer.

    Request body (JSON):
      {
        "question":     "was surgery mentioned?",             (required)
        "source_text":  "…full note…",                        (required)
        "doc_id":       "EA0001",                             (optional)
        "patient_id":   "P1",                                 (optional)
        "doc_date":     "2024-05-10",                         (optional)
        "visit_date":   "2024-05-10",                         (optional)
        "doc_type":     "progress_note"                       (optional)
      }

    Response (JSON):
      {"answer": "...", "evidence_text": "...", "confidence": "probable",
       "csv_row": { …one long-format row you can append to /extract/csv output… }}
    """
    ensure = getattr(current_app, "ensure_med42_loaded", None)
    if callable(ensure):
        ensure()
    backend = getattr(current_app, "med42_backend", None)
    if backend is None:
        status = getattr(current_app, "med42_backend_status", "unknown")
        return _bad(f"Med42 backend not yet ready (status={status!r}); retry in 30–60 s.", 503)

    try:
        from services.extract import DecodingConfig
        from services.tabular import UserQueryRow
    except ImportError as e:
        return _bad(f"paper-track modules unavailable: {e}", 503)

    payload = request.get_json(silent=True) or {}
    question = (payload.get("question") or "").strip()
    src = payload.get("source_text") or payload.get("text") or ""
    if not question:
        return _bad("`question` is required")
    if not src.strip():
        return _bad("`source_text` is required")

    doc_id = (payload.get("doc_id") or f"chat-{uuid.uuid4().hex[:8]}").strip()
    patient_id = (payload.get("patient_id") or doc_id).strip()
    doc_date = (payload.get("doc_date") or date.today().isoformat()).strip()
    visit_date = (payload.get("visit_date") or "").strip()
    doc_type = (payload.get("doc_type") or "progress_note").strip()

    prompt = (
        f"{_CHAT_SYSTEM_PROMPT}\n\n"
        f"Question: {question}\n\n"
        f"Clinical note:\n\"\"\"\n{src}\n\"\"\"\n\n"
        f"{_CHAT_INSTRUCTION}\n"
    )
    decoding = DecodingConfig(
        do_sample=False, temperature=None, top_p=None,
        max_new_tokens=int(payload.get("max_new_tokens", 256)),
        seed=int(payload.get("seed", 0)),
    )
    try:
        raw, _n = backend.generate(prompt, decoding)
    except Exception as e:
        logger.exception("chat backend.generate failed")
        return _bad(f"generation failure: {type(e).__name__}: {e}", 500)

    parsed = _parse_chat_response(raw)
    row = UserQueryRow(
        doc_id=doc_id, patient_id=patient_id, doc_type=doc_type,
        doc_date=doc_date, visit_date=visit_date,
        question=question,
        answer=parsed["answer"],
        evidence_text=parsed["evidence_text"],
        confidence=parsed["confidence"],
    ).as_long_row()

    return _no_cache(jsonify({
        "answer": parsed["answer"],
        "evidence_text": parsed["evidence_text"],
        "confidence": parsed["confidence"],
        "csv_row": row,
        "raw_response": raw,
    }))


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
