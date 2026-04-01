"""
Neurology guideline RAG: sentence-transformers + cosine similarity over
data/guidelines/neurology_guidelines.json.

No ChromaDB/SQLite dependency — uses NumPy for retrieval so it runs on older systems.

Environment:
  APP_HOME              — project root (default cwd)
  RAG_CACHE_DIR         — embedding cache (default APP_HOME/data/rag_cache)
  RAG_EMBEDDING_MODEL   — Sentence-Transformers model (default all-MiniLM-L6-v2)
  RAG_FORCE_REINDEX     — if "1", recompute embeddings
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterator

import numpy as np

logger = logging.getLogger("vectaai")

_GUIDELINES_REL = Path("data") / "guidelines" / "neurology_guidelines.json"


def _app_home() -> Path:
    return Path(os.environ.get("APP_HOME", os.getcwd())).resolve()


def _cache_dir() -> Path:
    return Path(os.environ.get("RAG_CACHE_DIR", _app_home() / "data" / "rag_cache"))


def _embedding_model_name() -> str:
    return os.environ.get("RAG_EMBEDDING_MODEL", "all-MiniLM-L6-v2")


def _iter_text_chunks(obj: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, dict):
        if path == "" and "metadata" in obj:
            obj = {k: v for k, v in obj.items() if k != "metadata"}
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            yield from _iter_text_chunks(v, p)
    elif isinstance(obj, list):
        if obj and all(isinstance(x, str) for x in obj):
            text = "; ".join(x.strip() for x in obj if x and str(x).strip())
            if len(text) > 20:
                yield path, text
        else:
            for i, item in enumerate(obj):
                yield from _iter_text_chunks(item, f"{path}[{i}]")
    elif isinstance(obj, str):
        t = obj.strip()
        if len(t) > 15:
            yield path, t


def _topic_from_path(path_key: str) -> str:
    root = path_key.split(".")[0].split("[")[0]
    return root if root else "general"


def _condition_to_topics(condition: str | None) -> list[str] | None:
    if not condition:
        return None
    c = condition.lower()
    topics: set[str] = set()
    if re.search(r"epilepsy|seizure|absence|myoclonic|eeg|aura|asm\b|anti.?seizure", c):
        topics.add("epilepsy_guidelines")
    if re.search(r"parkinson|bradykinesia|dyskinesia|levodopa|dopamine|rigidity|tremor", c):
        topics.add("parkinsons_guidelines")
    if re.search(r"stroke|tia\b|ischemic|thromb|nihss|mca\b|infarct|hemorrhagic", c):
        topics.add("stroke_guidelines")
    if re.search(r"migraine|headache|cluster|ichd", c):
        topics.add("headache_guidelines")
    return list(topics) if topics else None


def _cosine_top_k(
    query_vec: np.ndarray,
    matrix: np.ndarray,
    k: int,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Return indices of top-k cosine similarities (matrix rows normalized)."""
    q = query_vec.astype(np.float64)
    q /= np.linalg.norm(q) + 1e-12
    m = matrix.astype(np.float64)
    norms = np.linalg.norm(m, axis=1, keepdims=True) + 1e-12
    m = m / norms
    sims = m @ q
    if mask is not None:
        sims = np.where(mask, sims, -np.inf)
    k = min(k, len(sims))
    return np.argpartition(-sims, k - 1)[:k]


class RAGSystem:
    def __init__(self) -> None:
        self.available = False
        self._model = None
        self._embeddings: np.ndarray | None = None
        self._documents: list[str] = []
        self._topics: list[str] = []
        self._paths: list[str] = []
        self._error: str | None = None

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            self._error = str(e)
            logger.info("RAG: sentence-transformers not installed (%s)", e)
            return

        try:
            self._model = SentenceTransformer(_embedding_model_name())
        except Exception as e:
            self._error = str(e)
            logger.warning("RAG: SentenceTransformer load failed: %s", e)
            return

        try:
            self._load_index()
            self.available = True
        except Exception as e:
            self._error = str(e)
            logger.warning("RAG: index build failed: %s", e)

    def _guidelines_path(self) -> Path:
        p = _app_home() / _GUIDELINES_REL
        if not p.is_file():
            raise FileNotFoundError(f"Guidelines not found: {p}")
        return p

    def _load_index(self) -> None:
        path = self._guidelines_path()
        raw = path.read_bytes()
        file_hash = hashlib.sha256(raw).hexdigest()

        chunks: list[tuple[str, str, str]] = []
        data = json.loads(raw.decode("utf-8"))
        for path_key, text in _iter_text_chunks(data):
            topic = _topic_from_path(path_key)
            doc = f"[{topic}] {path_key}\n{text}"
            chunks.append((topic, path_key, doc))

        if not chunks:
            raise ValueError("No chunks extracted from guidelines JSON")

        _cache_dir().mkdir(parents=True, exist_ok=True)
        cache_npz = _cache_dir() / f"guidelines_{file_hash[:16]}.npz"
        force = os.environ.get("RAG_FORCE_REINDEX", "").lower() in ("1", "true", "yes")

        if cache_npz.is_file() and not force:
            bundle = np.load(cache_npz, allow_pickle=True)
            self._embeddings = bundle["embeddings"]
            self._topics = list(bundle["topics"])
            self._paths = list(bundle["paths"])
            self._documents = list(bundle["documents"])
            logger.info("RAG: loaded %d cached embeddings from %s", len(self._documents), cache_npz.name)
            return

        texts = [c[2] for c in chunks]
        logger.info("RAG: encoding %d guideline chunks (first run may download model)...", len(texts))
        emb = self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        self._embeddings = np.asarray(emb, dtype=np.float32)
        self._topics = [c[0] for c in chunks]
        self._paths = [c[1] for c in chunks]
        self._documents = texts

        np.savez_compressed(
            cache_npz,
            embeddings=self._embeddings,
            topics=np.array(self._topics, dtype=object),
            paths=np.array(self._paths, dtype=object),
            documents=np.array(self._documents, dtype=object),
        )
        logger.info("RAG: saved embedding cache -> %s", cache_npz)

    def retrieve(
        self,
        query: str,
        condition: str | None = None,
        n_results: int = 2,
    ) -> str:
        if not self.available or self._model is None or self._embeddings is None:
            return ""
        q = (query or "").strip()
        if not q:
            return ""

        n = max(1, min(int(n_results), 8))
        topics = _condition_to_topics(condition)

        qv = self._model.encode([q[:8000]], convert_to_numpy=True)[0]
        matrix = self._embeddings
        m = len(self._documents)

        if topics:
            mask = np.array([t in topics for t in self._topics], dtype=bool)
            if not mask.any():
                mask = None
        else:
            mask = None

        fetch_k = min(n * 6, m) if mask is not None else n
        idx = _cosine_top_k(qv, matrix, fetch_k, mask)
        # re-sort selected by similarity
        qn = qv.astype(np.float64)
        qn /= np.linalg.norm(qn) + 1e-12
        rows = matrix[idx].astype(np.float64)
        rows /= np.linalg.norm(rows, axis=1, keepdims=True) + 1e-12
        sims = rows @ qn
        order = np.argsort(-sims)
        idx = idx[order[:n]]

        lines = ["📚 RELEVANT GUIDELINE EXCERPTS (retrieved):"]
        for i, j in enumerate(idx, 1):
            lines.append(f"[{i}] {self._documents[j]}")
        return "\n".join(lines)


_instance: RAGSystem | None = None


def get_rag_system() -> RAGSystem:
    global _instance
    if _instance is None:
        _instance = RAGSystem()
    return _instance
