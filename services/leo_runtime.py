"""LEO runtime: one object that the CLI, the web app and the SLURM jobs all use.

    rt = LeoRuntime.load(mode="gpu")                    # Med42-8B + EpExtra + ontology
    rt = LeoRuntime.load(mode="cpu")                    # EpExtra + ontology only (no LLM)
    rt = LeoRuntime(backend=app.med42_backend)          # reuse a model the web app already loaded
    res = rt.extract_note(text, doc_id="n1", phenotypes=resolve_phenotypes(["core"]))

``res.row`` holds the phenotype columns, ``res.claims`` the long claim rows, ``res.asks`` the answers
to any questions.  Nothing is written to the evidence ledger unless a ledger is given: notes may be
protected health information and the ledger stores their text.

The LLM channel is the flat contract with schema-constrained decoding (arm ``L1C`` by default, the
arm the evaluation recommends for US-style notes), wrapped so notes longer than ``chunk_max_chars``
are split by section and paragraph.  Without a backend the run is specialist-only and says so in
``mode``; the specialist alone has lower precision (``docs/LEO_ROUTING_RULES.md``).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from services.leo_ask import Asker
from services.leo_catalog import AskSpec, Phenotype, resolve_phenotypes
from services.leo_tabular import claim_rows, wide_row

logger = logging.getLogger(__name__)


def env_flag(name: str, default: bool = True) -> bool:
    """``MEDAI_LEO_EXT_READER=0`` (or false/no/off) turns a switch off; unset keeps ``default``."""
    import os
    v = os.environ.get(name)
    if v is None or not str(v).strip():
        return default
    return str(v).strip().lower() not in ("0", "false", "no", "off")


@dataclass
class NoteResult:
    doc_id: str
    row: dict = field(default_factory=dict)
    claims: list[dict] = field(default_factory=list)
    asks: list[dict] = field(default_factory=list)
    n_claims: int = 0
    n_accepted: int = 0
    n_review: int = 0
    n_rejected: int = 0
    n_chunks: int = 1
    llm_used: bool = False
    error: str = ""
    seconds: float = 0.0


# Fields where, if the model and the rules give different values, the model's value is the one shown
# (both values always go to a person).  Pilot default: NONE, i.e. the rules' value is shown everywhere.
# Candidate policy CANDIDATE_DISAGREE_LLM (seizure type -> model) helped on synthetic sets but is not
# validated on real notes; see docs/EVAL_PROTOCOL_LEO.md D15/D17 and docs/DISAGREEMENT_ADJUDICATION.md.
DEFAULT_DISAGREE_LLM: tuple[str, ...] = ()
CANDIDATE_DISAGREE_LLM: tuple[str, ...] = ("clinical_seizure.predominant_seizure_type",)

_SHORT_PATH = {
    "epilepsy_type": "clinical_seizure.epilepsy_type",
    "predominant_seizure_type": "clinical_seizure.predominant_seizure_type",
    "age_at_onset_years": "clinical_seizure.age_at_onset_years",
    "seizure_frequency": "clinical_seizure.seizure_frequency",
}


def parse_disagree_llm(value) -> tuple[str, ...]:
    """``None`` -> default (no override); ``""``/``none`` -> no override; ``candidate`` -> the candidate policy;
    otherwise comma-separated field names or claim paths."""
    if value is None:
        return DEFAULT_DISAGREE_LLM
    if isinstance(value, (tuple, list)):
        names = [str(v) for v in value]
    else:
        names = [v.strip() for v in str(value).split(",")]
    names = [n for n in names if n]
    if not names or names == ["none"]:
        return ()
    if names == ["candidate"]:
        return CANDIDATE_DISAGREE_LLM
    return tuple(_SHORT_PATH.get(n, n) for n in names)


class LeoRuntime:
    def __init__(self, *, backend: Any = None, arm: str = "L1C", chunk_max_chars: int = 8000,
                 use_llm: bool = True, disagree_llm: tuple[str, ...] = DEFAULT_DISAGREE_LLM, ledger: Any = None,
                 adapter_label: str = "", ext_reader: Optional[bool] = None,
                 require_second_reader: Optional[bool] = None, ontology_select: Optional[bool] = None):
        self.backend = backend
        self.arm = arm
        self.chunk_max_chars = chunk_max_chars
        self.use_llm = bool(use_llm and backend is not None)
        self.disagree_llm = parse_disagree_llm(disagree_llm)
        self.ledger = ledger
        self.adapter_label = adapter_label
        if ext_reader is None:
            # H2 was trained on the five-field flat contract. Do not run X1C on
            # those weights unless the caller (or MEDAI_LEO_EXT_READER) asks.
            if adapter_label and os.environ.get("MEDAI_LEO_EXT_READER") is None:
                ext_reader = False
            else:
                ext_reader = env_flag("MEDAI_LEO_EXT_READER")
        self.ext_reader = bool(self.use_llm and ext_reader)
        self.require_second_reader = (env_flag("MEDAI_LEO_REQUIRE_SECOND_READER")
                                      if require_second_reader is None else bool(require_second_reader))
        self.ontology_select = bool(self.use_llm and (env_flag("MEDAI_LEO_ONTOLOGY_SELECT", default=False)
                                                      if ontology_select is None else ontology_select))
        self._pipeline = None
        self._reasoner = None
        self._asker: Optional[Asker] = None
        self._lock = threading.Lock()      # one model, one note at a time

    # ---- construction ----------------------------------------------------

    @classmethod
    def load(cls, *, mode: str = "gpu", arm: str = "L1C", adapter_dir: str = "", chunk_max_chars: int = 8000,
             disagree_llm: tuple[str, ...] = DEFAULT_DISAGREE_LLM, ledger: Any = None, model_name: str = "",
             cache_dir: str = "", ext_reader: Optional[bool] = None,
             require_second_reader: Optional[bool] = None,
             ontology_select: Optional[bool] = None) -> "LeoRuntime":
        """``mode`` = ``gpu`` (load Med42-8B; fails loudly without CUDA) or ``cpu`` (no LLM)."""
        if mode == "cpu":
            return cls(backend=None, use_llm=False, chunk_max_chars=chunk_max_chars,
                       disagree_llm=disagree_llm, ledger=ledger, ext_reader=False,
                       require_second_reader=require_second_reader, ontology_select=False)
        if mode != "gpu":
            raise ValueError("mode must be 'gpu' or 'cpu'")
        import os
        from pathlib import Path

        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("mode=gpu but CUDA is not available on this node. Use mode=cpu (specialist only) or "
                               "run on a GPU node (`leo batch` submits one by default).")
        from services.med42_backend import Med42Backend
        from services.med42_model import Med42ModelService
        repo = Path(__file__).resolve().parent.parent
        if adapter_dir:
            os.environ["MEDAI_LORA_ADAPTER_DIR"] = adapter_dir

        class _Cfg:
            pass

        cfg = _Cfg()
        cfg.model_name = model_name or os.environ.get("MODEL_NAME", "m42-health/Llama3-Med42-8B")
        cfg.model_cache_dir = cache_dir or os.environ.get("MED42_MODEL_CACHE_DIR", str(repo / "model_cache"))
        cfg.max_concurrent_users = 1
        svc = Med42ModelService(cfg)
        if not svc.load_model():
            raise RuntimeError(f"Failed to load Med42-8B: {svc.load_error}")
        return cls(backend=Med42Backend(svc), arm=arm, chunk_max_chars=chunk_max_chars,
                   disagree_llm=disagree_llm, ledger=ledger,
                   adapter_label=Path(adapter_dir).name if adapter_dir else "",
                   ext_reader=ext_reader, require_second_reader=require_second_reader,
                   ontology_select=ontology_select)

    # ---- components ------------------------------------------------------

    @property
    def mode(self) -> str:
        return "llm+specialist" if self.use_llm else "specialist_only"

    def _build_pipeline(self):
        from services.chain_pipeline import ChainPipeline, ChainPipelineConfig
        cfg = ChainPipelineConfig(llm_arm=self.arm if self.use_llm else "")
        cfg.require_second_reader_for_uncovered_fields = self.require_second_reader
        cfg.ontology_select = self.ontology_select
        for path in self.disagree_llm:
            cfg.disagree_primary[path] = "llm"
        reasoner = None
        selector = None
        if self.use_llm:
            from services.chain_llm import ChunkedReasoner, CombinedReasoner, ExtendedLiveReasoner, FlatLiveReasoner
            from services.onto_select import OntologySelector
            flat = FlatLiveReasoner(self.backend, arm=self.arm)
            inner: Any = CombinedReasoner(flat, ExtendedLiveReasoner(self.backend)) if self.ext_reader else flat
            reasoner = ChunkedReasoner(inner, max_chars=self.chunk_max_chars)
            if self.ontology_select:
                selector = OntologySelector(self.backend)
        self._reasoner = reasoner
        return ChainPipeline(cfg, llm_reasoner=reasoner, ontology_selector=selector)

    @property
    def pipeline(self):
        if self._pipeline is None:
            self._pipeline = self._build_pipeline()
        return self._pipeline

    @property
    def asker(self) -> Optional[Asker]:
        if self._asker is None and self.backend is not None:
            self._asker = Asker(self.backend, chunk_max_chars=self.chunk_max_chars)
        return self._asker

    def versions(self) -> dict:
        from services.chain_pipeline import ChainPipelineConfig
        c = ChainPipelineConfig()
        return {"pipeline": c.pipeline_version, "rules": c.rules_version, "ontology": c.ontology_release,
                "mode": self.mode, "llm_arm": self.arm if self.use_llm else "",
                "ext_arm": "X1C" if self.ext_reader else "",
                "model": getattr(self.backend, "model_name", "") if self.backend is not None else "",
                "adapter": self.adapter_label, "chunk_max_chars": self.chunk_max_chars,
                "disagree_llm_fields": list(self.disagree_llm),
                "require_second_reader": self.require_second_reader,
                "ontology_select": self.ontology_select}

    # ---- work ------------------------------------------------------------

    def extract_note(self, text: str, *, doc_id: str, row_index: int = 0, doc_date: str = "",
                     phenotypes: Optional[list[Phenotype]] = None, asks: Optional[list[AskSpec]] = None,
                     include_review: bool = True) -> NoteResult:
        res = NoteResult(doc_id=doc_id)
        phenotypes = phenotypes if phenotypes is not None else resolve_phenotypes(None)
        t0 = time.time()
        if not text or not text.strip():
            res.error = "empty note"
            return res
        try:
            date.fromisoformat(doc_date)
        except (TypeError, ValueError):
            doc_date = date.today().isoformat()
        with self._lock:
            try:
                stats, claims = self.pipeline.extract(text.strip(), document_id=doc_id, doc_date=doc_date,
                                                      ledger=self.ledger, return_claims=True)
            except Exception as e:                            # one bad note must not stop a batch
                logger.exception("LEO extraction failed for %s", doc_id)
                res.error = f"{type(e).__name__}: {e}"
                return res
            res.llm_used = bool(stats.llm_available)
            res.n_chunks = getattr(self._reasoner, "last_n_chunks", 1) if self._reasoner is not None else 1
            res.n_claims, res.n_accepted = stats.n_claims_emitted, stats.n_accepted
            res.n_review, res.n_rejected = stats.n_review, stats.n_rejected
            single = not res.llm_used           # ACCEPT means two readers agreed; with one, nothing is accepted
            if single:
                res.n_review, res.n_accepted = res.n_review + res.n_accepted, 0
            res.row = wide_row(claims, phenotypes, include_review=include_review, single_reader=single)
            res.claims = claim_rows(claims, doc_id, row_index, single_reader=single)
            if asks:
                if self.asker is None:
                    res.asks = [{"spec_id": a.id, "question": a.question, "answer": None, "quote": "",
                                 "status": "error", "reason": "no LLM loaded (cpu mode)"} for a in asks]
                else:
                    res.asks = [self.asker.ask(text.strip(), a).as_dict() for a in asks]
        res.seconds = round(time.time() - t0, 2)
        return res


__all__ = ["LeoRuntime", "NoteResult", "env_flag"]
