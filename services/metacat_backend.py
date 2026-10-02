"""MetaCAT backend — load trained MetaCAT classifiers and overlay their
contextual labels onto LinkedEntity records (replacing ConText's flags).

    from services.metacat_backend import MetaCATBackend

    mc = MetaCATBackend.from_dir("checkpoints/metacat")
    entities, doc = extractor.extract_with_context(text, nlp)   # ConText first
    mc.enrich(entities, text)                                    # then MetaCAT

Each task directory under ``checkpoints/metacat/`` is a MedCAT 2.9 serialised
MetaCAT (``medcat.storage.serialisers.deserialise``).  Inference reproduces
``MetaCAT.prepare_document``: tokenise the whole note, take ``cntx_left`` /
``cntx_right`` tokens around each entity's tokens, and call
``ml_utils.predict``.

MedCAT 2.9's ``train_raw`` computes the label→id map but does not store it in
the config when it starts empty, so the saved models have
``category_value2id == {}``.  The map is then read from ``label_map.json`` in
the task directory (recovered from the training report's per-class support;
see docs/METACAT_EVAL.md).  A task with neither is skipped, and so is a task
trained on a single class.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.medcat_extractor import LinkedEntity


TASKS = ["Presence", "Experiencer", "Temporality", "Certainty"]


@dataclass
class MetaCATBackend:
    """Loaded MetaCAT models per task, with their id→label maps."""
    models: dict[str, Any]
    labels: dict[str, dict[int, str]]

    @classmethod
    def from_dir(cls, checkpoint_dir: str | Path,
                 tasks: list[str] | None = None) -> "MetaCATBackend":
        import warnings
        from medcat.storage.serialisers import deserialise

        models: dict[str, Any] = {}
        labels: dict[str, dict[int, str]] = {}
        for t in tasks or TASKS:
            task_dir = Path(checkpoint_dir) / t
            if not task_dir.exists():
                continue
            try:
                mc = deserialise(str(task_dir))
            except Exception as e:  # noqa: BLE001 — a broken task must not stop extraction
                warnings.warn(f"MetaCAT: failed to load {t} from {task_dir}: {e}")
                continue
            v2id = dict(mc.config.general.category_value2id or {})
            label_map = task_dir / "label_map.json"
            if not v2id and label_map.exists():
                v2id = json.loads(label_map.read_text(encoding="utf-8"))["category_value2id"]
            if len(v2id) < 2:
                warnings.warn(f"MetaCAT: {t} has {len(v2id)} label(s); skipped")
                continue
            models[t] = mc
            labels[t] = {int(i): v for v, i in v2id.items()}
        return cls(models=models, labels=labels)

    def predict(self, task: str, entities: list[LinkedEntity], text: str) -> list[tuple[str, float] | None]:
        """(label, confidence) per entity, None where the span maps to no tokens."""
        from medcat.components.addons.meta_cat.ml_utils import predict

        mc = self.models[task]
        g = mc.config.general
        tok = mc.tokenizer(text.lower() if g.lowercase else text)
        ids, offsets = tok["input_ids"], tok["offset_mapping"]
        samples, where = [], []
        for n, e in enumerate(entities):
            idx = [i for i, (s, t) in enumerate(offsets) if t > e.char_start and s < e.char_end]
            if not idx:
                continue
            lo = max(0, idx[0] - g.cntx_left)
            hi = min(len(ids), idx[-1] + 1 + g.cntx_right)
            samples.append([ids[lo:hi], [i - lo for i in idx]])
            where.append(n)
        out: list[tuple[str, float] | None] = [None] * len(entities)
        if samples:
            preds, confs = predict(mc.model, samples, mc.config)
            for n, p, c in zip(where, preds, confs):
                out[n] = (self.labels[task][int(p)], float(c))
        return out

    def enrich(self, entities: list[LinkedEntity], text: str) -> list[LinkedEntity]:
        """Overwrite ConText's flags with MetaCAT's labels (in place)."""
        if not self.models or not entities or not text:
            return entities
        for task in self.models:
            for ent, res in zip(entities, self.predict(task, entities, text)):
                if res is not None:
                    self._apply_label(ent, task, res[0])
        return entities

    @staticmethod
    def _apply_label(ent: LinkedEntity, task: str, label: str) -> None:
        label = label.lower()
        if task == "Presence":
            ent.is_negated = label == "negated"
        elif task == "Experiencer":
            ent.is_family = label in ("family", "other")
        elif task == "Temporality":
            ent.is_historical = label == "past"
            ent.is_hypothetical = label == "hypothetical"
        elif task == "Certainty":
            ent.context = {**(ent.context or {}), "certainty": label}


__all__ = ["MetaCATBackend", "TASKS"]
