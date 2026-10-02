"""LEO in the web app: pick phenotypes, ask questions, upload a spreadsheet, download it with new columns.

    GET  /leo/ui                        the page
    GET  /leo/guide                     redirect to the user guide (LEO_GUIDE_URL)
    GET  /leo/phenotypes                catalogue: extract phenotypes, panels, question templates
    GET  /leo/status                    LLM status and versions
    POST /leo/extract                   one note (JSON) -> phenotype table row, claims, answers
    POST /leo/batch                     spreadsheet upload -> job id
    GET  /leo/jobs/<id>                 progress
    GET  /leo/jobs/<id>/download        result (csv jobs: a zip of the three files; xlsx: the workbook)
    POST /leo/jobs/<id>/cancel
    DELETE /leo/jobs/<id>               delete the upload and the results from the server

Uploads and results live in ``data/leo_jobs/<id>/`` (gitignored) and contain note text.  They are
deleted after ``MEDAI_LEO_JOB_TTL_H`` hours (default 24) or on request.  Nothing is written to the
evidence ledger by these routes.  The LLM is the web app's own Med42 backend; without it
(``llm=off`` or the model not loaded) LEO runs specialist-only and every response says so.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, redirect, request, send_file
from werkzeug.utils import secure_filename

from services import leo_catalog as cat

logger = logging.getLogger(__name__)
leo_bp = Blueprint("leo", __name__, url_prefix="/leo")

_RUNTIMES: dict[str, Any] = {}
_RT_LOCK = threading.Lock()
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


def _runtime(use_llm: bool):
    """Runtime for this request.  ``use_llm`` needs the app's Med42 backend to be loaded."""
    from services.leo_runtime import LeoRuntime
    arm = os.environ.get("MEDAI_LEO_ARM", "L1C")
    chunk = int(os.environ.get("MEDAI_LEO_CHUNK_CHARS", "8000"))
    with _RT_LOCK:
        if use_llm:
            ensure = getattr(current_app, "ensure_med42_loaded", None)
            status = ensure() if callable(ensure) else "not_available"
            backend = getattr(current_app, "med42_backend", None)
            if backend is None:
                raise _NotReady(f"Med42 is not loaded yet (status: {status}). Retry in a minute, or run with llm=off.")
            key = f"llm:{id(backend)}:{arm}:{chunk}"
            if key not in _RUNTIMES:
                _RUNTIMES[key] = LeoRuntime(backend=backend, arm=arm, chunk_max_chars=chunk,
                                            adapter_label=Path(os.environ.get("MEDAI_LORA_ADAPTER_DIR", "")).name)
        else:
            key = f"cpu:{chunk}"
            if key not in _RUNTIMES:
                _RUNTIMES[key] = LeoRuntime(backend=None, use_llm=False, chunk_max_chars=chunk)
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
    from services.leo_runtime import LeoRuntime
    return jsonify({"llm_status": getattr(current_app, "med42_backend_status", "unknown"),
                    "llm_ready": getattr(current_app, "med42_backend", None) is not None,
                    "versions": LeoRuntime(backend=None, use_llm=False).versions()})


@leo_bp.route("/extract", methods=["POST"])
def extract_one():
    p = request.get_json(silent=True) or {}
    text = p.get("source_text") or p.get("text")
    if not isinstance(text, str) or not text.strip():
        return _bad("`source_text` (non-empty string) is required")
    try:
        phen = cat.resolve_phenotypes(p.get("phenotypes"))
        asks = _parse_asks(p.get("questions"))
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return _bad(str(e))
    use_llm = _use_llm(p.get("llm", "auto"))
    try:
        rt = _runtime(use_llm)
    except _NotReady as e:
        return _bad(str(e), 503)
    res = rt.extract_note(text, doc_id=p.get("document_id") or f"note-{uuid.uuid4().hex[:8]}",
                          doc_date=p.get("doc_date") or "", phenotypes=phen, asks=asks,
                          include_review=bool(p.get("include_review", True)))
    if res.error:
        return _bad(f"extraction failed: {res.error}", 500)
    resp = jsonify({"mode": rt.mode, "llm_used": res.llm_used, "row": res.row, "claims": res.claims,
                    "asks": res.asks, "n_chunks": res.n_chunks, "seconds": res.seconds,
                    "phenotypes": [{"id": x.id, "label": x.label, "evidence": x.evidence, "kind": x.kind}
                                   for x in phen],
                    "versions": rt.versions()})
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _run_job(job_id: str) -> None:
    from services import leo_batch as lb
    job = _JOBS[job_id]
    jd = _jobs_root() / job_id
    try:
        job["state"] = "running"
        df = lb.read_table(job["input"], sheet=job.get("sheet") or None)
        cols = lb.detect_columns(df, job.get("text_col", ""), job.get("id_col", ""), job.get("date_col", ""))
        rt = _runtime(job["use_llm"])
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
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        return _bad(str(e))
    fmt = (form.get("format") or "csv").lower()
    if fmt not in ("csv", "xlsx"):
        return _bad("`format` must be csv or xlsx")
    use_llm = _use_llm(form.get("llm", "auto"))
    if use_llm:
        try:
            _runtime(True)
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
    _JOBS[job_id] = {"state": "queued", "done": 0, "total": 0, "files": [], "error": "", "input": str(path),
                     "filename": name, "format": fmt, "phen": phen, "asks": asks, "use_llm": use_llm,
                     "include_review": form.get("include_review", "1") not in ("0", "false"),
                     "limit": int(form.get("limit") or 0), "sheet": form.get("sheet", ""),
                     "text_col": form.get("text_col", ""), "id_col": form.get("id_col", ""),
                     "date_col": form.get("date_col", "")}
    threading.Thread(target=_run_job, args=(job_id,), daemon=True, name=f"leo-job-{job_id[:6]}").start()
    return jsonify({"job_id": job_id, "mode": "llm+specialist" if use_llm else "specialist_only"}), 202


def _job_or_404(job_id: str):
    job = _JOBS.get(job_id)
    if job is None:
        return None, _bad("unknown job (it may have expired)", 404)
    return job, None


@leo_bp.route("/jobs/<job_id>", methods=["GET"])
def job_status(job_id: str):
    job, err = _job_or_404(job_id)
    if err:
        return err
    return jsonify({k: job.get(k) for k in ("state", "done", "total", "files", "error", "summary", "format")})


@leo_bp.route("/jobs/<job_id>/download", methods=["GET"])
def job_download(job_id: str):
    job, err = _job_or_404(job_id)
    if err:
        return err
    if job["state"] not in ("done", "cancelled") or not job["files"]:
        return _bad("job has no result yet", 409)
    jd = (_jobs_root() / job_id).resolve()
    paths = [jd / n for n in job["files"]]
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
    return jsonify({"ok": True})


@leo_bp.route("/jobs/<job_id>", methods=["DELETE"])
def job_delete(job_id: str):
    job, err = _job_or_404(job_id)
    if err:
        return err
    shutil.rmtree(_jobs_root() / job_id, ignore_errors=True)
    _JOBS.pop(job_id, None)
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
    _, table, fields, store = ctx
    scope = request.args.get("scope", "flagged")
    try:
        its = lr.items(table, fields, store.latest(), scope)
    except ValueError as e:
        return _bad(str(e))
    try:
        off, lim = max(int(request.args.get("offset", 0) or 0), 0), min(int(request.args.get("limit", 25) or 25), 200)
    except ValueError:
        return _bad("offset and limit must be numbers")
    resp = jsonify({"scope": scope, "counts": lr.counts(its), "offset": off, "items": its[off:off + lim]})
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
            if prop["status"] in lr.NOT_REVIEWABLE:
                raise ValueError(f"{f.label} in row {row} has nothing to review ({prop['status'] or 'empty'})")
            events.append(lr.make_event(prop, d.get("decision", ""), d.get("value", ""), p.get("reviewer", ""),
                                        d.get("comment", ""), str(job["prov"].get("pipeline", ""))))
    except (ValueError, TypeError, AttributeError) as e:
        return _bad(str(e))
    latest = store.add(events)
    return jsonify({"saved": len(events), "counts": lr.counts(lr.items(table, fields, latest, "flagged")),
                    "reviewed_total": len(latest)})


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
