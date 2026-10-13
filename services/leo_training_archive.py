"""Opt-in durable copy of review decisions for later training or validation.

The 24-hour job folder is scratch.  When a reviewer checks *Permit use for training*, this module
copies that job's review log, latest decisions, consent record, and note text into
``data/leo_training/<job_id>/`` (gitignored, owner-only).  That folder is **not** deleted with the
job TTL.  Unchecking the box withdraws consent and removes that job's archive.

Nothing here trains a model or changes extract.  A later, versioned run on approved compute may
read these files (``docs/ACTIVE_LEARNING_PLAN.md``).
"""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_JOB_ID = re.compile(r"^[0-9a-f]{32}$")


def archive_root() -> Path:
    root = Path(os.environ.get("MEDAI_LEO_TRAINING_DIR") or
                Path(os.environ.get("APP_HOME", os.getcwd())) / "data" / "leo_training")
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:
        pass
    return root


def job_dir(job_id: str) -> Path:
    if not _JOB_ID.match(job_id or ""):
        raise ValueError("invalid job id")
    return archive_root() / job_id


def _log_consent(event: dict) -> None:
    """Append-only log without note text (audit of permit / withdraw)."""
    p = archive_root() / "_consent_log.jsonl"
    event = {k: event[k] for k in event if k != "text"}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=True) + "\n")


def status(job_id: str) -> dict:
    if not _JOB_ID.match(job_id or ""):
        return {"permitted": False, "n_decisions": 0, "archived_utc": ""}
    consent_path = archive_root() / job_id / "consent.json"
    if not consent_path.is_file():
        return {"permitted": False, "n_decisions": 0, "archived_utc": ""}
    try:
        c = json.loads(consent_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"permitted": False, "n_decisions": 0, "archived_utc": ""}
    return {"permitted": bool(c.get("permitted")), "n_decisions": int(c.get("n_decisions") or 0),
            "archived_utc": str(c.get("permitted_utc") or "")}


def _notes_from_table(table: Any) -> list[dict]:
    from services.leo_batch import ID_COLS, TEXT_COLS
    cols = {c.lower(): c for c in table.columns}
    text_col = next((cols[n] for n in TEXT_COLS if n in cols), "")
    id_col = next((cols[n] for n in ID_COLS if n in cols), "")
    if not text_col:
        return []
    out = []
    for i in range(len(table)):
        r = table.iloc[i]
        out.append({"row": i + 1,
                    "doc_id": (str(r[id_col]).strip() if id_col else "") or f"row{i + 1}",
                    "text": str(r[text_col])})
    return out


def sync(job_id: str, *, store: Any, table: Any, reviewer: str, pipeline: str = "",
         prov: Optional[dict] = None) -> dict:
    """Snapshot this job into the training archive. Call only after explicit permit."""
    dest = job_dir(job_id)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        dest.chmod(0o700)
    except OSError:
        pass
    n = len(store.latest()) if store is not None and hasattr(store, "latest") else 0
    if getattr(store, "csv", None) is not None and Path(store.csv).is_file():
        shutil.copy2(store.csv, dest / "reviewed.csv")
    if getattr(store, "log", None) is not None and Path(store.log).is_file():
        shutil.copy2(store.log, dest / "reviews.jsonl")
    notes = _notes_from_table(table)
    (dest / "notes.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in notes), encoding="utf-8")
    slim = {}
    if isinstance(prov, dict):
        slim = {k: prov[k] for k in ("tool", "pipeline", "llm_arm", "phenotypes", "created_utc") if k in prov}
    utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    consent = {
        "job_id": job_id, "permitted": True, "permitted_utc": utc, "reviewer": reviewer,
        "pipeline": pipeline, "n_decisions": max(n, 0), "n_notes": len(notes),
        "includes_note_text": bool(notes),
        "note": ("Opt-in copy for later training or validation. Not applied to extract. "
                 "Survives the 24-hour job folder. Contains note text."),
        "provenance": slim,
    }
    tmp = dest / "consent.json.tmp"
    tmp.write_text(json.dumps(consent, indent=2, ensure_ascii=True), encoding="utf-8")
    tmp.replace(dest / "consent.json")
    _log_consent({"action": "permit", "job_id": job_id, "reviewer": reviewer, "utc": utc,
                  "n_decisions": consent["n_decisions"]})
    return status(job_id)


def withdraw(job_id: str, *, reviewer: str = "") -> dict:
    """Remove this job from the training archive (consent withdrawn)."""
    dest = job_dir(job_id)
    if dest.is_dir():
        shutil.rmtree(dest, ignore_errors=True)
    utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _log_consent({"action": "withdraw", "job_id": job_id, "reviewer": reviewer, "utc": utc})
    return status(job_id)


__all__ = ["archive_root", "job_dir", "status", "sync", "withdraw"]
