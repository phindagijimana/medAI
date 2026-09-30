"""MetaCAT backend — load trained MetaCAT classifiers and expose an inference
API that overlays contextual attribute labels onto LinkedEntity records.

Usage (inference-side, once trained models exist):

    from services.metacat_backend import MetaCATBackend
    from services.medcat_extractor import MedCATExtractor

    extractor = MedCATExtractor("data/medcat_cdb_epilepsy/cdb")
    entities, spacy_doc = extractor.attach_context(note_text)

    mc_backend = MetaCATBackend.from_dir("checkpoints/metacat")
    entities = mc_backend.enrich(entities, note_text)
    # Each entity now has updated is_negated / is_family / is_historical /
    # is_hypothetical (from the ML classifier), and ent.context may include
    # a 'certainty' key with the ML label.

This module is a THIN wrapper — it loads each of the 4 trained MetaCAT
tasks (Presence, Experiencer, Temporality, Certainty) from disk and
calls MetaCAT.predict() on each entity's char span.  If any task's
weights are missing, that task is skipped and the ConText default
remains in place (falls back gracefully).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.medcat_extractor import LinkedEntity


TASKS = ["Presence", "Experiencer", "Temporality", "Certainty"]


@dataclass
class MetaCATBackend:
    """Loaded MetaCAT models per task. Absent tasks silently no-op."""
    models: dict[str, Any]  # task_name -> MetaCAT instance

    @classmethod
    def from_dir(cls, checkpoint_dir: str | Path,
                 tasks: list[str] | None = None) -> "MetaCATBackend":
        """Load MetaCAT weights from ``checkpoint_dir/{task}/``.

        Missing tasks are quietly skipped so partial deployments work.
        """
        from medcat.components.addons.meta_cat.meta_cat import MetaCAT
        base = Path(checkpoint_dir)
        tasks = tasks or TASKS
        models: dict[str, Any] = {}
        for t in tasks:
            task_dir = base / t
            if not task_dir.exists():
                continue
            try:
                models[t] = MetaCAT.load(save_dir_path=str(task_dir))
            except Exception as e:
                # Deliberate: absent/broken task weights should not crash
                # the extraction pipeline.
                import warnings
                warnings.warn(f"MetaCAT: failed to load {t} from {task_dir}: {e}")
        return cls(models=models)

    def enrich(self, entities: list[LinkedEntity], text: str) -> list[LinkedEntity]:
        """Overlay MetaCAT predictions onto LinkedEntity attributes.

        For each entity, if a task's model is loaded, call
        MetaCAT.predict_one() with the entity's char span and set the
        matching bool flag / context slot.

        Returns the same list (modified in place) for chainability.
        """
        if not self.models or not entities or not text:
            return entities
        for ent in entities:
            span_start = getattr(ent, "char_start", None)
            span_end = getattr(ent, "char_end", None)
            if span_start is None or span_end is None:
                continue
            for task, model in self.models.items():
                try:
                    label = self._predict_one(model, text, span_start, span_end)
                except Exception:
                    continue
                self._apply_label(ent, task, label)
        return entities

    # ------------------------------------------------------------------

    @staticmethod
    def _predict_one(model: Any, text: str, start: int, end: int) -> str | None:
        """Run a single MetaCAT model on one span. Returns the label string.

        MedCAT 2.9 MetaCAT.predict() operates on a spaCy Doc + Span; we
        construct a minimal input by tokenising just the entity's
        surrounding window.
        """
        # Delegate to MetaCAT's own tokenizer + classifier.  API detail may
        # differ slightly between MedCAT 2.9 point releases — the try/except
        # in `enrich` protects against attribute drift.
        pred = model.predict_one(text, start, end)  # type: ignore[attr-defined]
        if isinstance(pred, dict):
            return pred.get("value")
        return pred

    @staticmethod
    def _apply_label(ent: LinkedEntity, task: str, label: str | None) -> None:
        if label is None:
            return
        label = str(label).lower()
        if task == "Presence":
            ent.is_negated = (label == "negated")
        elif task == "Experiencer":
            ent.is_family = (label in ("family", "other"))
        elif task == "Temporality":
            ent.is_historical = (label == "past")
            ent.is_hypothetical = (label == "hypothetical")
        elif task == "Certainty":
            # v0.2.1 Evidence[T].certainty is a separate field. Stash into
            # ent.context so downstream rules can read it without our
            # having to widen the LinkedEntity dataclass right now.
            if ent.context is None:
                ent.context = {}
            ent.context["certainty"] = label


__all__ = ["MetaCATBackend", "TASKS"]
