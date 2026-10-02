"""Append-only evidence ledger for the LEO chain (Chain-of-Three spec P1.4).

Compendium (page 7): *"Reviewed items enter the ledger only after a
clinician action. The record is marked human-adjudicated and retains the
pre-review proposal. A review cannot overwrite history."*

Implementation choices:
    * SQLite (file-backed, zero-config, concurrent reads).
    * Three tables + a view:
        - ``claims``       — one row per emitted Claim (ACCEPT only; or
                             REVIEW items after human adjudication).
        - ``review_queue`` — pending REVIEW claims awaiting adjudication.
        - ``audit_log``    — REJECT rows plus every adjudication action.
    * Append-only semantics enforced in Python: no UPDATE on claims /
      audit_log. ``review_queue`` is the one mutable surface — items are
      inserted on pipeline publish and removed on adjudication, which
      itself emits a new ``claims`` row.
    * Timestamps are UTC ISO-8601; UUIDs are claim-scoped.

The ledger is the research+audit substrate. It is NOT a FHIR store, NOT
a clinical database. Export to Phenopackets or FHIR happens downstream.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from schema.claim import Claim, ValidatorVerdict


# ─── Schema ──────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id        TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    section         TEXT NOT NULL,
    concept_system  TEXT NOT NULL,
    concept_id      TEXT NOT NULL,
    concept_label   TEXT NOT NULL,
    assertion       TEXT NOT NULL,
    experiencer     TEXT NOT NULL,
    temporal_status TEXT NOT NULL,
    detectors       TEXT NOT NULL,  -- JSON array
    verdict         TEXT NOT NULL,  -- 'accept' | 'human_adjudicated'
    reason_codes    TEXT NOT NULL,  -- JSON array
    human_adjudicated INTEGER NOT NULL DEFAULT 0,  -- 0 | 1
    pre_review_claim_id TEXT,       -- original review-queue claim_id if adjudicated
    claim_json      TEXT NOT NULL,  -- full Claim.model_dump_json()
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_doc  ON claims(document_id);
CREATE INDEX IF NOT EXISTS idx_claims_concept ON claims(concept_system, concept_id);

CREATE TABLE IF NOT EXISTS review_queue (
    claim_id        TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL,
    section         TEXT NOT NULL,
    reason_codes    TEXT NOT NULL,  -- JSON array
    claim_json      TEXT NOT NULL,
    enqueued_at     TEXT NOT NULL,
    status          TEXT NOT NULL   -- 'pending' | 'in_review' | 'resolved'
);
CREATE INDEX IF NOT EXISTS idx_review_doc    ON review_queue(document_id);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_queue(status);

CREATE TABLE IF NOT EXISTS audit_log (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,  -- 'reject' | 'review_action' | 'config_change'
    claim_id        TEXT,
    actor           TEXT,
    payload         TEXT NOT NULL,  -- JSON blob
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_claim ON audit_log(claim_id);
"""


class EvidenceLedger:
    """SQLite-backed append-only evidence store.

    Thread-safety: SQLite's default connection isolation handles the single-
    writer case; for multi-process writers, pass check_same_thread=False
    and rely on SQLite's WAL mode (enabled below).
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript("PRAGMA journal_mode=WAL;")
            c.executescript(_SCHEMA_SQL)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), isolation_level=None, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

    # ---- Writes ---------------------------------------------------------

    def publish(self, claim: Claim, actor: str = "pipeline") -> None:
        """Route a validated Claim to the correct destination.

        ACCEPT  → claims
        REVIEW  → review_queue
        REJECT  → audit_log
        """
        v = claim.validator_verdict
        if v == ValidatorVerdict.ACCEPT:
            self._insert_claim(claim, human_adjudicated=False)
        elif v == ValidatorVerdict.REVIEW:
            self._enqueue_review(claim)
        elif v == ValidatorVerdict.REJECT:
            self._log_reject(claim, actor=actor)
        else:
            raise ValueError(f"Unknown verdict: {v}")

    def _insert_claim(self, claim: Claim, *, human_adjudicated: bool,
                      pre_review_claim_id: Optional[str] = None) -> None:
        row = (
            claim.claim_id,
            claim.document_id,
            claim.section,
            claim.concept.system,
            claim.concept.id,
            claim.concept.label,
            claim.assertion.value,
            claim.experiencer.value,
            claim.temporality.status.value,
            json.dumps(claim.detectors),
            "human_adjudicated" if human_adjudicated else "accept",
            json.dumps([r.value for r in claim.reason_codes]),
            1 if human_adjudicated else 0,
            pre_review_claim_id,
            claim.model_dump_json(),
            claim.created_at,
        )
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO claims
                   (claim_id, document_id, section, concept_system, concept_id,
                    concept_label, assertion, experiencer, temporal_status,
                    detectors, verdict, reason_codes, human_adjudicated,
                    pre_review_claim_id, claim_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                row,
            )

    def _enqueue_review(self, claim: Claim) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR IGNORE INTO review_queue
                   (claim_id, document_id, section, reason_codes, claim_json,
                    enqueued_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending')""",
                (
                    claim.claim_id,
                    claim.document_id,
                    claim.section,
                    json.dumps([r.value for r in claim.reason_codes]),
                    claim.model_dump_json(),
                    _now_iso(),
                ),
            )

    def _log_reject(self, claim: Claim, *, actor: str) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT INTO audit_log
                   (event_type, claim_id, actor, payload, created_at)
                   VALUES ('reject', ?, ?, ?, ?)""",
                (claim.claim_id, actor, claim.model_dump_json(), _now_iso()),
            )

    # ---- Reviewer adjudication -----------------------------------------

    def resolve_review(
        self,
        review_claim_id: str,
        *,
        action: str,
        reviewer: str,
        resolved_claim: Optional[Claim] = None,
        notes: str = "",
    ) -> None:
        """Mark a review item resolved and (if accepted) write the final claim.

        Args:
            action: one of "accept_as_is" | "edit" | "reject"
            resolved_claim: when action is "accept_as_is" or "edit", the
                final Claim to persist (must have validator_verdict=ACCEPT).
        """
        if action not in ("accept_as_is", "edit", "reject"):
            raise ValueError(f"Unknown review action: {action}")

        with self._conn() as c:
            # Mark the queue item resolved
            c.execute(
                "UPDATE review_queue SET status='resolved' WHERE claim_id=?",
                (review_claim_id,),
            )
            # Audit trail
            c.execute(
                """INSERT INTO audit_log
                   (event_type, claim_id, actor, payload, created_at)
                   VALUES ('review_action', ?, ?, ?, ?)""",
                (
                    review_claim_id,
                    reviewer,
                    json.dumps({"action": action, "notes": notes}),
                    _now_iso(),
                ),
            )

        # If accept, persist the final claim as human-adjudicated
        if action in ("accept_as_is", "edit"):
            if resolved_claim is None:
                raise ValueError("accept actions require a resolved_claim")
            self._insert_claim(
                resolved_claim,
                human_adjudicated=True,
                pre_review_claim_id=review_claim_id,
            )

    # ---- Reads ---------------------------------------------------------

    def list_claims(
        self,
        *,
        document_id: Optional[str] = None,
        concept_system: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict]:
        q = "SELECT claim_json FROM claims WHERE 1=1"
        args: list = []
        if document_id:
            q += " AND document_id = ?"
            args.append(document_id)
        if concept_system:
            q += " AND concept_system = ?"
            args.append(concept_system)
        q += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            cur = c.execute(q, args)
            return [json.loads(r[0]) for r in cur.fetchall()]

    def pending_reviews(self, limit: int = 100) -> list[dict]:
        with self._conn() as c:
            cur = c.execute(
                """SELECT claim_json FROM review_queue
                   WHERE status='pending' ORDER BY enqueued_at ASC LIMIT ?""",
                (limit,),
            )
            return [json.loads(r[0]) for r in cur.fetchall()]

    def counts(self) -> dict[str, int]:
        with self._conn() as c:
            def _n(sql: str) -> int:
                return c.execute(sql).fetchone()[0]
            return {
                "accepted": _n("SELECT COUNT(*) FROM claims"),
                "human_adjudicated": _n(
                    "SELECT COUNT(*) FROM claims WHERE human_adjudicated=1"),
                "pending_review": _n(
                    "SELECT COUNT(*) FROM review_queue WHERE status='pending'"),
                "rejects": _n(
                    "SELECT COUNT(*) FROM audit_log WHERE event_type='reject'"),
            }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["EvidenceLedger"]
