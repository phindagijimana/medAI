"""LEO in the web app: pick phenotypes, ask questions, upload a spreadsheet, download it with new columns.

    GET  /leo/ui                        the page
    GET  /leo/guide                     redirect to the user guide (LEO_GUIDE_URL)
    GET  /leo/phenotypes                catalogue: extract phenotypes, panels, question templates
    GET  /leo/status                    LLM status, login, known sidecars, versions
    POST /leo/extract                   one note (JSON) -> phenotype table row, claims, answers
    POST /leo/extract/download          same note -> csv zip or xlsx (same columns as a spreadsheet job)
    POST /leo/jobs/<id>/learn           score Validator labels (applied=False; Loop C paused)
    POST /leo/batch                     spreadsheet upload -> job id
    GET  /leo/jobs/<id>                 progress
    GET  /leo/jobs/<id>/download        result (csv jobs: a zip of the three files; xlsx: the workbook)
    POST /leo/jobs/<id>/cancel
    DELETE /leo/jobs/<id>               delete the upload and the results from the server

Uploads and results live in ``data/leo_jobs/<id>/`` (gitignored) and contain note text.  They are
deleted after ``MEDAI_LEO_JOB_TTL_H`` hours (default 24) or on request.  Opt-in training copies live
in ``data/leo_training/<id>/`` (also gitignored) and are **not** deleted with the job TTL.  Nothing
is written to the evidence ledger by these routes.  The LLM is the web app's own Med42 backend; without it
(``llm=off`` or the model not loaded) LEO runs specialist-only and every response says so.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, redirect, request, send_file
from werkzeug.utils import secure_filename

from services import leo_auth as auth
from services import leo_catalog as cat

logger = logging.getLogger(__name__)
leo_bp = Blueprint("leo", __name__, url_prefix="/leo")

_RUNTIMES: dict[str, Any] = {}
_RT_LOCK = threading.Lock()
# One job at a time on this machine by default: two jobs sharing one GPU can run it out of memory. Jobs that are
# waiting show state "queued". MEDAI_LEO_CONCURRENT_JOBS raises the limit (e.g. for rules-only use).
_SLOT = threading.Semaphore(max(1, int(os.environ.get("MEDAI_LEO_CONCURRENT_JOBS", "1"))))
_EMPTY_SUMMARY = {"rows_processed": 0, "rows_error": 0, "rows_with_llm": 0, "mode": ""}
_JOBS: dict[str, dict] = {}


def _bad(msg: str, status: int = 400):
    return jsonify({"error": msg}), status


def _jobs_root() -> Path:
    root = Path(os.environ.get("APP_HOME", os.getcwd())) / "data" / "leo_jobs"
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)            # notes and results: owner only (the app has no login)
    except OSError:
        pass
    return root


def _purge_old_jobs() -> None:
    ttl = float(os.environ.get("MEDAI_LEO_JOB_TTL_H", "24")) * 3600
    now = time.time()
    for d in _jobs_root().iterdir():
        try:
            if d.is_dir() and now - d.stat().st_mtime > ttl:
                shutil.rmtree(d, ignore_errors=True)
                _JOBS.pop(d.name, None)
        except OSError:
            pass


class _NotReady(Exception):
    pass


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _flags_from(src: Any) -> dict:
    """Opt-in extract flags. Default off. Unknown sidecar names raise ValueError."""
    from services.ext_detectors import parse_ext_detectors
    if hasattr(src, "get"):
        raw = src.get("ext_detectors") or src.get("ext_detector") or ""
    else:
        raw = ""
    if isinstance(raw, str):
        dets = parse_ext_detectors(raw) if str(raw).strip() else ()
    else:
        dets = parse_ext_detectors(list(raw or []))
    research = _truthy(src.get("research_extract") if hasattr(src, "get") else False)
    return {
        "ext_detectors": tuple(dets or ()),
        "quote_entail": _truthy(src.get("quote_entail") if hasattr(src, "get") else False),
        "ask_rag": _truthy(src.get("ask_rag") if hasattr(src, "get") else False),
        "export_codes": _truthy(src.get("export_codes") if hasattr(src, "get") else False),
        "research_extract": research,
    }


def _flags_public(flags: dict | None) -> dict:
    flags = flags or {}
    return {
        "ext_detectors": list(flags.get("ext_detectors") or []),
        "quote_entail": bool(flags.get("quote_entail")),
        "ask_rag": bool(flags.get("ask_rag")),
        "export_codes": bool(flags.get("export_codes")),
        "research_extract": bool(flags.get("research_extract")),
    }


def _cache_key(use_llm: bool, flags: dict | None = None, backend: Any = None) -> str:
    flags = flags or {}
    dets = ",".join(tuple(flags.get("ext_detectors") or ()))
    qe, rag, codes = int(bool(flags.get("quote_entail"))), int(bool(flags.get("ask_rag"))), int(bool(flags.get("export_codes")))
    chunk = int(os.environ.get("MEDAI_LEO_CHUNK_CHARS", "8000"))
    if not use_llm:
        return f"cpu:{chunk}:d{dets}:q{qe}:g{rag}:c{codes}"
    arm = os.environ.get("MEDAI_LEO_ARM", "L1C")
    return (f"llm:{id(backend)}:{arm}:{chunk}:ext{os.environ.get('MEDAI_LEO_EXT_READER', '1')}:"
            f"r{os.environ.get('MEDAI_LEO_REQUIRE_SECOND_READER', '1')}:"
            f"o{os.environ.get('MEDAI_LEO_ONTOLOGY_SELECT', '0')}:d{dets}:q{qe}:g{rag}:c{codes}")


def _runtime(use_llm: bool, flags: dict | None = None):
    """Runtime for this request.  ``use_llm`` needs the app's Med42 backend to be loaded."""
    from services.leo_runtime import LeoRuntime
    flags = flags or {}
    dets = tuple(flags.get("ext_detectors") or ())
    qe = bool(flags.get("quote_entail"))
    rag = bool(flags.get("ask_rag"))
    codes = bool(flags.get("export_codes"))
    arm = os.environ.get("MEDAI_LEO_ARM", "L1C")
    chunk = int(os.environ.get("MEDAI_LEO_CHUNK_CHARS", "8000"))
    with _RT_LOCK:
        if use_llm:
            ensure = getattr(current_app, "ensure_med42_loaded", None)
            status = ensure() if callable(ensure) else "not_available"
            backend = getattr(current_app, "med42_backend", None)
            if backend is None:
                raise _NotReady(f"Med42 is not loaded yet (status: {status}). Retry in a minute, or run with llm=off.")
            key = _cache_key(True, flags, backend)
            if key not in _RUNTIMES:
                _RUNTIMES[key] = LeoRuntime(
                    backend=backend, arm=arm, chunk_max_chars=chunk,
                    adapter_label=Path(os.environ.get("MEDAI_LORA_ADAPTER_DIR", "")).name,
                    ext_detectors=dets, quote_entail=qe, ask_rag=rag, export_codes=codes)
        else:
            key = _cache_key(False, flags)
            if key not in _RUNTIMES:
                _RUNTIMES[key] = LeoRuntime(
                    backend=None, use_llm=False, chunk_max_chars=chunk,
                    ext_detectors=dets, quote_entail=qe, ask_rag=False, export_codes=codes)
        rt = _RUNTIMES[key]
        # share the MedCAT/ontology objects between the two runtimes (loaded once)
        other = next((r for k, r in _RUNTIMES.items() if r is not rt and r._pipeline is not None
                      and getattr(r._pipeline, "_lazy_init_done", False)), None)
        if other is not None and rt._pipeline is None:
            p = rt.pipeline
            p._extractor, p._assembler = other._pipeline._extractor, other._pipeline._assembler
            p._candidate_service, p._lazy_init_done = other._pipeline._candidate_service, True
        return rt


def _use_llm(mode: str) -> bool:
    mode = (mode or "auto").lower()
    if mode == "off":
        return False
    if mode == "on":
        return True
    return getattr(current_app, "med42_backend", None) is not None       # auto: only if already loaded


def _parse_asks(raw: Any) -> list[cat.AskSpec]:
    """[{"template": id} | {"question": text, "answer_type": ..., "choices": [...]}] -> specs."""
    if isinstance(raw, str):
        raw = json.loads(raw) if raw.strip() else []
    asks: list[cat.AskSpec] = []
    for i, q in enumerate(raw or [], 1):
        if isinstance(q, str):
            q = {"template": q}
        if q.get("template"):
            asks.append(cat.ask_template(q["template"]))
        else:
            asks.append(cat.custom_ask(q.get("question", ""), q.get("answer_type", "text"),
                                       tuple(q.get("choices") or ()), q.get("id") or f"q{i}"))
    if len({a.id for a in asks}) != len(asks):
        raise ValueError("two questions have the same id")
    return asks


@leo_bp.route("/phenotypes", methods=["GET"])
def phenotypes():
    return jsonify(cat.describe())


@leo_bp.route("/evidence", methods=["GET"])
def evidence():
    """What has been measured, read from the scorer outputs in eval/results (see services/leo_evidence.py)."""
    from services.leo_evidence import evidence as ev
    return jsonify(ev())


@leo_bp.route("/status", methods=["GET"])
def status():
    from services.ext_detectors import KNOWN_EXT_DETECTORS
    from services.leo_runtime import LeoRuntime
    llm_ready = getattr(current_app, "med42_backend", None) is not None
    return jsonify({
        "user": auth.current_user() if auth.enabled() else "",
        "login_required": auth.enabled(),
        "llm_status": getattr(current_app, "med42_backend_status", "unknown"),
        "llm_ready": llm_ready,
        "load_med42": os.environ.get("MEDAI_LOAD_MED42", "1") == "1",
        "readers": "model_and_rules" if llm_ready else "rules_only",
        "known_ext_detectors": list(KNOWN_EXT_DETECTORS),
        "versions": LeoRuntime(backend=None, use_llm=False).versions(),
    })


@leo_bp.route("/extract", methods=["POST"])
def extract_one():
    p = request.get_json(silent=True) or {}
    text = p.get("source_text") or p.get("text")
    if not isinstance(text, str) or not text.strip():
        return _bad("`source_text` (non-empty string) is required")
    try:
        phen = cat.resolve_phenotypes(p.get("phenotypes"))
        asks = _parse_asks(p.get("questions"))
        flags = _flags_from(p)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return _bad(str(e))
    use_llm = _use_llm(p.get("llm", "auto"))
    try:
        rt = _runtime(use_llm, flags)
    except _NotReady as e:
        return _bad(str(e), 503)
    auth.audit("extract_note", chars=len(text), llm=use_llm)
    include_review = bool(p.get("include_review", True)) and not flags["research_extract"]
    res = rt.extract_note(text, doc_id=p.get("document_id") or f"note-{uuid.uuid4().hex[:8]}",
                          doc_date=p.get("doc_date") or "", phenotypes=phen, asks=asks,
                          include_review=include_review)
    if res.error:
        return _bad(f"extraction failed: {res.error}", 500)
    pub = _flags_public(flags)
    pub["ask_rag"] = bool(rt.ask_rag)
    pub["quote_entail"] = bool(rt.quote_entail)
    pub["export_codes"] = bool(rt.export_codes)
    pub["ext_detectors"] = list(rt.ext_detectors)
    resp = jsonify({"mode": rt.mode, "llm_used": res.llm_used, "row": res.row, "claims": res.claims,
                    "asks": res.asks, "n_chunks": res.n_chunks, "seconds": res.seconds,
                    "document_id": res.doc_id, "second_reader": bool(res.llm_used),
                    "flags": pub,
                    "phenotypes": [{"id": x.id, "label": x.label, "evidence": x.evidence, "kind": x.kind}
                                   for x in phen],
                    "versions": rt.versions()})
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _safe_stem(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "paste").strip())[:80].strip("._")
    return s or "paste"


def _send_written(paths: list[Path], fmt: str, stem: str):
    if fmt == "xlsx":
        return send_file(io.BytesIO(paths[0].read_bytes()),
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=f"{stem}_leo.xlsx")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, p.name)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"{stem}_leo.zip")


@leo_bp.route("/extract/download", methods=["POST"])
def extract_download():
    """Paste-one-note download: same wide CSV/Excel as uploading a one-row spreadsheet."""
    from services import leo_batch as lb
    from services.leo_runtime import LeoRuntime
    p = request.get_json(silent=True) or {}
    fmt = str(p.get("format") or "csv").lower()
    if fmt not in ("csv", "xlsx"):
        return _bad("format must be csv or xlsx")
    text = p.get("source_text") or p.get("text")
    if not isinstance(text, str) or not text.strip():
        return _bad("`source_text` (non-empty string) is required")
    try:
        phen = cat.resolve_phenotypes(p.get("phenotypes"))
        asks = _parse_asks(p.get("questions"))
        flags = _flags_from(p)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return _bad(str(e))
    include_review = bool(p.get("include_review", True)) and not flags["research_extract"]
    row, claims, asks_out = p.get("row"), p.get("claims"), p.get("asks")
    if row is None:
        use_llm = _use_llm(p.get("llm", "auto"))
        try:
            rt = _runtime(use_llm, flags)
        except _NotReady as e:
            return _bad(str(e), 503)
        auth.audit("extract_note", chars=len(text), llm=use_llm)
        res = rt.extract_note(text, doc_id=p.get("document_id") or f"note-{uuid.uuid4().hex[:8]}",
                              doc_date=p.get("doc_date") or "", phenotypes=phen, asks=asks,
                              include_review=include_review)
        if res.error:
            return _bad(f"extraction failed: {res.error}", 500)
        row, claims, asks_out = res.row, res.claims, res.asks
        doc_id, llm_used, n_chunks, versions = res.doc_id, res.llm_used, res.n_chunks, rt.versions()
        n_review = res.n_review
    else:
        if not isinstance(row, dict):
            return _bad("`row` must be an object")
        if claims is not None and not isinstance(claims, list):
            return _bad("`claims` must be a list")
        doc_id = p.get("document_id") or "paste"
        llm_used = bool(p.get("llm_used"))
        n_chunks = p.get("n_chunks") or 1
        versions = p.get("versions") if isinstance(p.get("versions"), dict) else LeoRuntime(
            backend=None, use_llm=False).versions()
        n_review = p.get("n_review")
        n_review = int(n_review) if n_review is not None else None
        auth.audit("download", job="paste", file=_safe_stem(str(doc_id)))
    table, claims_df, prov = lb.outputs_from_paste(
        text=text, doc_id=str(doc_id), row=row, claims=list(claims or []),
        asks_out=list(asks_out or []), phenotypes=phen, asks=asks, versions=versions,
        llm_used=bool(llm_used), n_chunks=int(n_chunks or 1), include_review=include_review,
        n_review=n_review)
    stem = _safe_stem(str(doc_id))
    with tempfile.TemporaryDirectory() as td:
        paths = lb.write_outputs(table, claims_df, prov, Path(td) / f"{stem}_leo.{fmt}", fmt, phen)
        return _send_written(paths, fmt, stem)


def _wait_for_slot(job: dict) -> bool:
    """Wait for this job's turn.  Returns False if the job was cancelled while waiting (so a cancel takes effect at
    once, not when the job in front finishes); True when it holds the slot and must release it."""
    while True:
        if job.get("cancel"):
            return False
        if _SLOT.acquire(timeout=0.5):
            if job.get("cancel"):
                _SLOT.release()
                return False
            return True


def _in_app_context(fn):
    """Run a background job inside the Flask app context: the model runtime looks up the app (``current_app``),
    which a bare thread does not have.  Captured here, in the request thread."""
    app = current_app._get_current_object()

    def run(*args):
        with app.app_context():
            fn(*args)
    return run


def _run_job(job_id: str) -> None:
    from services import leo_batch as lb
    job = _JOBS[job_id]
    jd = _jobs_root() / job_id
    held = False
    try:
        held = _wait_for_slot(job)
        if not held:                                        # cancelled while waiting its turn
            job["state"], job["summary"] = "cancelled", dict(_EMPTY_SUMMARY)
            return
        job["state"] = "running"
        df = lb.read_table(job["input"], sheet=job.get("sheet") or None)
        if not len(df):
            raise ValueError("the file has a header but no notes (no data rows)")
        cols = lb.detect_columns(df, job.get("text_col", ""), job.get("id_col", ""), job.get("date_col", ""))
        rt = _runtime(job["use_llm"], job.get("flags") or {})
        job["total"] = min(len(df), job["limit"]) if job["limit"] else len(df)

        def progress(i: int, n: int, doc: str) -> None:
            job["done"] = i

        table, claims, prov = lb.run_table(
            df, rt, phenotypes=job["phen"], asks=job["asks"], text_col=cols["text"], id_col=cols["id"],
            date_col=cols["date"], include_review=job["include_review"], limit=job["limit"],
            progress=progress, cancel=lambda: job.get("cancel", False))
        prov["input_sha256"] = lb.input_hash(job["input"])
        prov["input_file"] = job["filename"]
        out = jd / f"{Path(job['filename']).stem}_leo.{job['format']}"
        files = lb.write_outputs(table, claims, prov, out, job["format"], job["phen"])
        job["files"] = [f.name for f in files]
        job["prov"] = prov
        job["state"] = "cancelled" if job.get("cancel") else "done"
        job["summary"] = {k: prov[k] for k in ("rows_processed", "rows_error", "rows_with_llm", "mode")}
    except _NotReady as e:
        job["state"], job["error"] = "error", str(e)
    except Exception as e:                                  # surfaced to the user, not swallowed
        logger.exception("LEO batch job failed")
        job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
    finally:
        if held:
            _SLOT.release()
        _persist(job_id)


@leo_bp.route("/batch", methods=["POST"])
def batch():
    from services import leo_batch as lb
    f = request.files.get("file")
    if f is None or not f.filename:
        return _bad("upload a file in the `file` field (csv, tsv, xlsx, jsonl or txt)")
    name = secure_filename(f.filename)
    if Path(name).suffix.lower() not in lb.INPUT_SUFFIXES:
        return _bad(f"unsupported file type; use one of {', '.join(lb.INPUT_SUFFIXES)}")
    form = request.form
    try:
        phen = cat.resolve_phenotypes(form.get("phenotypes", ""))
        asks = _parse_asks(form.get("questions", ""))
        flags = _flags_from(form)
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return _bad(str(e))
    fmt = (form.get("format") or "csv").lower()
    if fmt not in ("csv", "xlsx"):
        return _bad("`format` must be csv or xlsx")
    use_llm = _use_llm(form.get("llm", "auto"))
    if use_llm:
        try:
            _runtime(True, flags)
        except _NotReady as e:
            return _bad(str(e), 503)
    elif asks:
        return _bad("questions need the LLM; set llm=on (or remove the questions)")
    _purge_old_jobs()
    job_id = uuid.uuid4().hex
    jd = _jobs_root() / job_id
    jd.mkdir(parents=True, mode=0o700)
    path = jd / name
    f.save(path)
    include_review = form.get("include_review", "1") not in ("0", "false") and not flags["research_extract"]
    _JOBS[job_id] = {"state": "queued", "done": 0, "total": 0, "files": [], "error": "", "input": str(path),
                     "filename": name, "format": fmt, "phen": phen, "asks": asks, "use_llm": use_llm,
                     "include_review": include_review, "flags": flags,
                     "limit": int(form.get("limit") or 0), "sheet": form.get("sheet", ""),
                     "text_col": form.get("text_col", ""), "id_col": form.get("id_col", ""),
                     "date_col": form.get("date_col", ""), "owner": auth.current_user(), "created": time.time()}
    _persist(job_id)
    auth.audit("job_start", job=job_id, file=name, phenotypes=[p.id for p in phen], questions=len(asks), llm=use_llm)
    threading.Thread(target=_in_app_context(_run_job), args=(job_id,), daemon=True, name=f"leo-job-{job_id[:6]}").start()
    return jsonify({"job_id": job_id, "mode": "llm+specialist" if use_llm else "specialist_only"}), 202


# ---- job description: upload + words -> editable plan -> confirmed run ---------------------------------------

def _plan_view(job: dict, spec, df) -> dict:
    from services import leo_job as lj
    problems = lj.validate(spec, df)
    view = {"spec": spec.to_dict(), "problems": problems, "warnings": spec.warnings,
            "description": lj.describe(spec, df), "columns": [str(c) for c in df.columns],
            "needs_llm": lj.needs_llm(spec), "n_rows": int(len(df))}
    if not problems:
        _, view["selection"] = lj.select_rows(df, spec)
    return view


def _plan_df(job: dict):
    from services import leo_batch as lb
    if "_df" not in job:
        job["_df"] = lb.read_table(job["input"], sheet=job.get("sheet") or None)
    return job["_df"]


@leo_bp.route("/job/plan", methods=["POST"])
def job_plan():
    """Upload a file and describe the task in words.  Nothing is run: returns the understood job for editing."""
    from services import leo_batch as lb
    from services import leo_job as lj
    f = request.files.get("file")
    if f is None or not f.filename:
        return _bad("upload a file in the `file` field (csv, tsv, xlsx, jsonl)")
    name = secure_filename(f.filename)
    if Path(name).suffix.lower() not in lb.INPUT_SUFFIXES:
        return _bad(f"unsupported file type; use one of {', '.join(lb.INPUT_SUFFIXES)}")
    req = (request.form.get("request") or "").strip()
    _purge_old_jobs()
    job_id = uuid.uuid4().hex
    jd = _jobs_root() / job_id
    jd.mkdir(parents=True, mode=0o700)
    path = jd / name
    f.save(path)
    job = {"state": "planned", "done": 0, "total": 0, "files": [], "error": "", "input": str(path), "filename": name,
           "sheet": request.form.get("sheet", ""), "owner": auth.current_user(), "created": time.time()}
    try:
        df = _plan_df(job)
        spec = lj.parse_request(req, df, text_col=request.form.get("text_col", ""), id_col=request.form.get("id_col", ""),
                                date_col=request.form.get("date_col", ""),
                                default_format="xlsx" if path.suffix.lower() in (".xlsx", ".xlsm") else "csv")
    except Exception as e:                                  # unreadable file: say so, keep nothing
        shutil.rmtree(jd, ignore_errors=True)
        return _bad(f"could not read the file: {e}")
    _JOBS[job_id] = job
    _persist(job_id)
    auth.audit("job_plan", job=job_id, file=name, rows=int(len(df)))
    resp = jsonify({"job_id": job_id, **_plan_view(job, spec, df)})
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _spec_from_request(job: dict):
    from services import leo_job as lj
    p = request.get_json(silent=True) or {}
    try:
        return lj.spec_from_dict(p.get("spec") or {}), p, None
    except (ValueError, TypeError, KeyError) as e:
        return None, p, _bad(f"job description rejected: {e}")


@leo_bp.route("/job/<job_id>/describe", methods=["POST"])
def job_describe(job_id: str):
    """Re-check an edited job description; returns the plain-words summary, counts and problems."""
    job, err = _job_or_404(job_id)
    if err:
        return err
    if job.get("state") != "planned":
        return _bad("this job has already been started", 409)
    spec, _, err = _spec_from_request(job)
    if err:
        return err
    return jsonify(_plan_view(job, spec, _plan_df(job)))


def _run_spec_job(job_id: str) -> None:
    from services import leo_batch as lb
    from services import leo_job as lj
    job = _JOBS[job_id]
    jd = _jobs_root() / job_id
    spec = job["spec"]
    held = False
    try:
        held = _wait_for_slot(job)
        if not held:
            job["state"], job["summary"] = "cancelled", dict(_EMPTY_SUMMARY)
            return
        job["state"] = "running"
        df = _plan_df(job)
        rt = _runtime(job["use_llm"], job.get("flags") or {})
        sub, _ = lj.select_rows(df, spec)
        job["total"] = len(sub)

        def progress(i: int, n: int, doc: str) -> None:
            job["done"] = i

        table, claims, prov = lj.run_spec(spec, df, rt, progress=progress, cancel=lambda: job.get("cancel", False))
        prov["input_sha256"] = lb.input_hash(job["input"])
        prov["input_file"] = job["filename"]
        out = jd / f"{Path(job['filename']).stem}_leo.{spec.output_format}"
        files = lb.write_outputs(table, claims, prov, out, spec.output_format, job["phen"])
        spec_file = out.with_suffix(".job.json")             # the job description travels with the results
        spec_file.write_text(spec.to_json())
        job["files"] = [f.name for f in files] + [spec_file.name]
        job["prov"] = prov
        job["state"] = "cancelled" if job.get("cancel") else "done"
        job["summary"] = {k: prov[k] for k in ("rows_processed", "rows_error", "rows_with_llm", "mode")}
    except _NotReady as e:
        job["state"], job["error"] = "error", str(e)
    except Exception as e:
        logger.exception("LEO job-description run failed")
        job["state"], job["error"] = "error", f"{type(e).__name__}: {e}"
    finally:
        if held:
            _SLOT.release()
        job.pop("_df", None)
        _persist(job_id)


@leo_bp.route("/job/<job_id>/run", methods=["POST"])
def job_run(job_id: str):
    """Start the confirmed job.  The spec sent here (not the one first proposed) is what runs."""
    from services import leo_job as lj
    job, err = _job_or_404(job_id)
    if err:
        return err
    if job.get("state") != "planned":
        return _bad("this job has already been started", 409)
    spec, p, err = _spec_from_request(job)
    if err:
        return err
    df = _plan_df(job)
    problems = lj.validate(spec, df)
    if problems:
        return _bad("job is not ready: " + "; ".join(problems), 422)
    if not len(lj.select_rows(df, spec)[0]):
        return _bad("the selection matches no notes", 422)
    try:
        flags = _flags_from(p)
    except ValueError as e:
        return _bad(str(e))
    use_llm = _use_llm(p.get("llm", "auto"))
    if lj.needs_llm(spec) and not use_llm:
        return _bad("questions need the LLM; set llm=on (or remove the questions)", 422)
    if use_llm:
        try:
            _runtime(True, flags)
        except _NotReady as e:
            return _bad(str(e), 503)
    if flags["research_extract"]:
        spec.include_review = False
    phen, asks = lj.selection(spec)
    job.update(spec=spec, phen=phen, asks=asks, use_llm=use_llm, state="queued", format=spec.output_format,
               flags=flags)
    _persist(job_id)
    auth.audit("job_start", job=job_id, file=job["filename"], phenotypes=spec.phenotypes, questions=len(asks),
               rows=spec.rows.mode, n=spec.rows.n, llm=use_llm)
    threading.Thread(target=_in_app_context(_run_spec_job), args=(job_id,), daemon=True,
                     name=f"leo-spec-{job_id[:6]}").start()
    return jsonify({"job_id": job_id, "mode": "llm+specialist" if use_llm else "specialist_only"}), 202


# ---- job records survive a restart (job.json in the job folder) --------------------------------------------

_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
_META = "job.json"


def _persist(job_id: str) -> None:
    """Write what is needed to show, download and review a job after the app restarts.  Never raises."""
    job = _JOBS.get(job_id)
    if job is None:
        return
    try:
        meta = {k: job.get(k) for k in ("state", "filename", "format", "owner", "sheet", "files", "error", "summary",
                                         "prov", "total", "use_llm", "created", "permit_training",
                                         "permit_training_at", "permit_training_by", "flags")}
        meta["done"] = job.get("done", 0)
        meta["input"] = Path(job["input"]).name
        meta["phen"] = [p.id for p in job.get("phen") or []]
        meta["asks"] = [{"id": a.id, "question": a.question, "answer_type": a.answer_type, "choices": list(a.choices),
                         "predefined": a.predefined} for a in job.get("asks") or []]
        jd = _jobs_root() / job_id
        tmp = jd / (_META + ".tmp")
        tmp.write_text(json.dumps(meta, default=str))
        tmp.replace(jd / _META)
    except Exception:
        logger.exception("could not save the job record")


def _load_job(job_id: str):
    """A job from an earlier run of the app, or None.  Only a well-formed id ever touches the disk."""
    if not _JOB_ID.match(job_id or ""):
        return None
    jd = _jobs_root() / job_id
    try:
        meta = json.loads((jd / _META).read_text())
        job = dict(meta)
        job["input"] = str(jd / meta["input"])
        job["phen"] = [cat.get(i) for i in meta.get("phen", [])]
        job["asks"] = [cat.ask_template(a["id"]) if a.get("predefined") else
                       cat.AskSpec(a["id"], a["question"], a["answer_type"], tuple(a.get("choices") or ()), "", False)
                       for a in meta.get("asks", [])]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    job.setdefault("files", [])
    if job.get("state") in ("queued", "running"):
        job["state"], job["error"] = "error", "The app restarted while this job was running. Start it again."
    _JOBS[job_id] = job
    return job


def _job_or_404(job_id: str):
    job = _JOBS.get(job_id) or _load_job(job_id)
    if job is None or (auth.enabled() and job.get("owner") != auth.current_user()):
        return None, _bad("unknown job (it may have expired)", 404)
    return job, None


@leo_bp.route("/jobs/<job_id>", methods=["GET"])
def job_status(job_id: str):
    job, err = _job_or_404(job_id)
    if err:
        return err
    body = {k: job.get(k) for k in ("state", "done", "total", "files", "error", "summary", "format", "filename")}
    body["flags"] = _flags_public(job.get("flags") or {})
    return jsonify(body)


@leo_bp.route("/jobs/<job_id>/download", methods=["GET"])
def job_download(job_id: str):
    job, err = _job_or_404(job_id)
    if err:
        return err
    if job["state"] not in ("done", "cancelled") or not job["files"]:
        return _bad("job has no result yet", 409)
    jd = (_jobs_root() / job_id).resolve()
    paths = [jd / n for n in job["files"]]
    auth.audit("download", job=job_id, file=job.get("filename", ""))
    if any(not str(p.resolve()).startswith(str(jd)) for p in paths):
        return _bad("bad path", 400)
    if len(paths) == 1:
        return send_file(paths[0], as_attachment=True, download_name=paths[0].name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            z.write(p, p.name)
    buf.seek(0)
    return send_file(buf, mimetype="application/zip", as_attachment=True,
                     download_name=f"{Path(job['filename']).stem}_leo.zip")


@leo_bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def job_cancel(job_id: str):
    job, err = _job_or_404(job_id)
    if err:
        return err
    job["cancel"] = True
    auth.audit("job_cancel", job=job_id)
    return jsonify({"ok": True})


@leo_bp.route("/jobs/<job_id>", methods=["DELETE"])
def job_delete(job_id: str):
    job, err = _job_or_404(job_id)
    if err:
        return err
    if job.get("state") in ("queued", "running"):
        return _bad("this job is still waiting or running; cancel it first, then delete it", 409)
    shutil.rmtree(_jobs_root() / job_id, ignore_errors=True)
    _JOBS.pop(job_id, None)
    auth.audit("job_delete", job=job_id)
    return jsonify({"ok": True})


# ---- review: look at flagged values, record decisions, merge them into the result -------------------------

def _review_ctx(job_id: str):
    """(job, table, fields, store) for a finished batch job, or (None, error response)."""
    from services import leo_review as lr
    job, err = _job_or_404(job_id)
    if err:
        return None, err
    if job["state"] not in ("done", "cancelled") or not job["files"]:
        return None, _bad("job has no result yet", 409)
    jd = _jobs_root() / job_id
    if "_table" not in job:
        main = next(n for n in job["files"] if n.endswith((".csv", ".xlsx")) and ".claims" not in n)
        job["_table"] = lr.load_table(jd / main)
    stem = f"{Path(job['filename']).stem}_leo"
    store = lr.ReviewStore(jd / f"{stem}.reviews.jsonl", jd / f"{stem}.reviewed.csv")
    fields = lr.fields_from(job["prov"].get("column_map", {}), job["phen"], job["asks"])
    return (job, job["_table"], fields, store), None


@leo_bp.route("/jobs/<job_id>/review", methods=["GET"])
def review_items(job_id: str):
    from services import leo_review as lr
    ctx, err = _review_ctx(job_id)
    if err:
        return err
    job, table, fields, store = ctx
    scope = request.args.get("scope", "flagged")
    try:
        its = lr.items(table, fields, store.latest(), scope, audit_seed=job_id)
    except ValueError as e:
        return _bad(str(e))
    try:
        off, lim = max(int(request.args.get("offset", 0) or 0), 0), min(int(request.args.get("limit", 25) or 25), 200)
        row = int(request.args.get("row", 0) or 0)
    except ValueError:
        return _bad("offset, limit and row must be numbers")
    reasons = sorted({r for it in its for r in (it["why"] or "").split(";") if r})
    field, reason = request.args.get("field", ""), request.args.get("reason", "")
    if field:
        its = [it for it in its if it["field"] == field]
    if reason:
        its = [it for it in its if reason in (it["why"] or "").split(";")]
    counts = lr.counts(its)
    if request.args.get("pending") in ("1", "true"):
        its = [it for it in its if not it["decision"]]
    from services.leo_training_archive import status as train_status
    train = train_status(job_id)
    if not train["permitted"] and job.get("permit_training"):
        train = {**train, "permitted": True}
    body = {"scope": scope, "counts": counts, "offset": off,
            "items": [it for it in its if it["row"] == row] if row else its[off:off + lim],
            "fields": [{"id": f.id, "label": f.label} for f in fields], "reasons": reasons,
            "training_permit": train}
    if request.args.get("notes") in ("1", "true"):
        notes: dict = {}
        for it in its:
            n = notes.setdefault(it["row"], {"row": it["row"], "doc_id": it["doc_id"], "total": 0, "pending": 0})
            n["total"] += 1
            n["pending"] += not it["decision"]
        body["notes"] = list(notes.values())
    resp = jsonify(body)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@leo_bp.route("/jobs/<job_id>/review", methods=["POST"])
def review_save(job_id: str):
    from services import leo_review as lr
    ctx, err = _review_ctx(job_id)
    if err:
        return err
    job, table, fields, store = ctx
    p = request.get_json(silent=True) or {}
    decisions = p.get("decisions")
    if not isinstance(decisions, list) or not decisions or len(decisions) > 200:
        return _bad("`decisions` must be a list of 1 to 200 items")
    by_id = {f.id: f for f in fields}
    events = []
    try:
        for d in decisions:
            f = by_id.get(d.get("field"))
            row = int(d.get("row", 0))
            if f is None or not 1 <= row <= len(table):
                raise ValueError(f"unknown value: row {d.get('row')!r}, field {d.get('field')!r}")
            prop = lr.proposal(table, f, row)
            dec = (d.get("decision") or "").strip().lower()
            if prop["status"] == "not_found":
                if dec not in ("add", "undo"):
                    raise ValueError(f"{f.label} in row {row} was not found; use add to supply the missed value")
            elif prop["status"] in lr.NOT_REVIEWABLE:
                raise ValueError(f"{f.label} in row {row} has nothing to review ({prop['status'] or 'empty'})")
            elif dec == "add":
                raise ValueError(f"{f.label} in row {row} already has a value; use correct to change it")
            events.append(lr.make_event(prop, d.get("decision", ""), d.get("value", ""),
                                        auth.current_user() if auth.enabled() else p.get("reviewer", ""),
                                        d.get("comment", ""), str(job["prov"].get("pipeline", "")),
                                        why_tag=d.get("why_tag", ""), reader_preferred=d.get("reader_preferred", "")))
    except (ValueError, TypeError, AttributeError) as e:
        return _bad(str(e))
    latest = store.add(events)
    train = {"permitted": False, "n_decisions": 0, "archived_utc": ""}
    if job.get("permit_training"):
        from services.leo_training_archive import sync as train_sync
        reviewer = auth.current_user() if auth.enabled() else (p.get("reviewer") or "")
        train = train_sync(job_id, store=store, table=table, reviewer=str(reviewer),
                           pipeline=str(job.get("prov", {}).get("pipeline", "")), prov=job.get("prov") or {})
    else:
        from services.leo_training_archive import status as train_status
        train = train_status(job_id)
    auth.audit("review_save", job=job_id, decisions=len(events))
    return jsonify({"saved": len(events), "counts": lr.counts(lr.items(table, fields, latest, "flagged")),
                    "reviewed_total": len(latest), "training_permit": train})


@leo_bp.route("/jobs/<job_id>/note/<int:row>", methods=["GET"])
def review_note(job_id: str, row: int):
    """The note behind one row, so the reviewer can read the quote in context."""
    from services import leo_batch as lb
    ctx, err = _review_ctx(job_id)
    if err:
        return err
    job, table, _, _ = ctx
    if not 1 <= row <= len(table):
        return _bad("no such row", 404)
    if "_input" not in job:
        job["_input"] = lb.read_table(job["input"], sheet=job.get("sheet") or None)
    col = job["prov"]["text_column"]
    resp = jsonify({"row": row, "text": str(job["_input"].iloc[row - 1][col])})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@leo_bp.route("/jobs/<job_id>/training-permit", methods=["GET", "POST"])
def training_permit(job_id: str):
    """Opt-in copy of this job's reviews into ``data/leo_training/``. Default off. Does not train."""
    from datetime import datetime, timezone
    from services.leo_training_archive import status as train_status, sync as train_sync, withdraw as train_withdraw
    ctx, err = _review_ctx(job_id)
    if err:
        return err
    job, table, _, store = ctx
    if request.method == "GET":
        st = train_status(job_id)
        if not st["permitted"] and job.get("permit_training"):
            st = {**st, "permitted": True}
        resp = jsonify(st)
        resp.headers["Cache-Control"] = "no-store"
        return resp
    p = request.get_json(silent=True) or {}
    if "permit" not in p:
        return _bad("`permit` must be true or false")
    raw = p.get("permit")
    if raw in (True, 1, "1", "true", "True"):
        permit = True
    elif raw in (False, 0, "0", "false", "False"):
        permit = False
    else:
        return _bad("`permit` must be true or false")
    reviewer = auth.current_user() if auth.enabled() else str(p.get("reviewer") or "").strip()
    if permit and not reviewer:
        return _bad("enter a reviewer name or ID before permitting use for training")
    if permit:
        job["permit_training"] = True
        job["permit_training_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        job["permit_training_by"] = reviewer
        st = train_sync(job_id, store=store, table=table, reviewer=reviewer,
                        pipeline=str(job.get("prov", {}).get("pipeline", "")), prov=job.get("prov") or {})
        auth.audit("training_permit", job=job_id, permit=True)
    else:
        job["permit_training"] = False
        job["permit_training_at"] = ""
        job["permit_training_by"] = ""
        st = train_withdraw(job_id, reviewer=reviewer)
        auth.audit("training_permit", job=job_id, permit=False)
    _persist(job_id)
    return jsonify(st)


@leo_bp.route("/jobs/<job_id>/learn", methods=["POST"])
def learn(job_id: str):
    """Score Validator labels (Loop A/B). Never applies a policy. Loop C is paused."""
    from services import leo_learn as ll
    ctx, err = _review_ctx(job_id)
    if err:
        return err
    _, _, _, store = ctx
    latest = store.latest()
    if not latest:
        return _bad("nothing has been reviewed yet", 409)
    store._write_csv(latest)
    p = request.get_json(silent=True) or {}
    try:
        min_n = int(p.get("min_n") or ll.MIN_N)
        loops = str(p.get("loops") or "all")
        md, result = ll.run([store.csv], min_n=min_n, loops=loops)
    except (ValueError, FileNotFoundError) as e:
        return _bad(str(e))
    result["applied"] = False
    result["report"] = md
    result["apply"] = ("CLI only: leo learn --emit-policy after ≥100 scored clashes/field, "
                       "then --disagree-llm policy:FILE on a new leo-v0.x. D17 stays.")
    auth.audit("learn", job=job_id, rows=result.get("n_rows", 0))
    return jsonify(result)


@leo_bp.route("/jobs/<job_id>/review/export", methods=["GET"])
def review_export(job_id: str):
    """kind=reviewed: the decisions (csv).  kind=merged: the result with <field>_final / <field>_review added."""
    from services import leo_review as lr
    ctx, err = _review_ctx(job_id)
    if err:
        return err
    job, table, fields, store = ctx
    latest = store.latest()
    if not latest:
        return _bad("nothing has been reviewed yet", 409)
    jd = _jobs_root() / job_id
    kind = request.args.get("kind", "merged")
    auth.audit("review_export", job=job_id, kind=kind[:20])
    if kind == "reviewed":
        store._write_csv(latest)
        return send_file(store.csv, as_attachment=True, download_name=store.csv.name)
    if kind != "merged":
        return _bad("kind must be reviewed or merged")
    try:
        merged = lr.merge(table, fields, latest, request.args.get("unreviewed", "blank"))
    except ValueError as e:
        return _bad(str(e))
    stem = f"{Path(job['filename']).stem}_leo"
    src = next(n for n in job["files"] if n.endswith((".csv", ".xlsx")) and ".claims" not in n)
    out = jd / f"{stem}.merged.{job['format']}"
    lr.write_merged(merged, lr.reviewed_frame(latest), out, source_xlsx=(jd / src) if job["format"] == "xlsx" else None)
    return send_file(out, as_attachment=True, download_name=out.name)


_UI_FILE = Path(__file__).with_name("leo_ui.html")


GUIDE_URL = "https://github.com/phindagijimana/medAI/blob/main/docs/LEO_USER_GUIDE.md"


@leo_bp.route("/guide", methods=["GET"])
def guide():
    """The user guide lives in the repository; set LEO_GUIDE_URL to point at another copy."""
    return redirect(os.environ.get("LEO_GUIDE_URL", GUIDE_URL), code=302)


@leo_bp.route("/ui", methods=["GET"])
def leo_ui() -> Response:
    resp = Response(_UI_FILE.read_text(encoding="utf-8"), mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store"
    return resp
