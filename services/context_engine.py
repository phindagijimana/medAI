"""ConText ablation inside E: swap the preprocessor, same phenotype fields.

Default remains medspaCy ConText (``docs/METACAT_EVAL.md``). Opt-in engines:

  * ``medspacy`` — current pipeline (default).
  * ``sentence`` — ``rules.sentence_context`` negated / option / history cues.
  * ``negex`` — Chapman 2001 pre-negation in the sentence before the mention
    (same helpers as extra detectors, ``services.ext_detectors.span``).

This is not a third phenotype arm. Do not publish "ConText F1 vs EpExtra F1".
Flag off / ``medspacy`` ≡ previous E.
"""

from __future__ import annotations

from typing import Optional

KNOWN_CONTEXT_ENGINES = ("medspacy", "sentence", "negex")


def parse_context_engine(value: Optional[str] = None) -> str:
    import os
    raw = (value if value is not None else os.environ.get("MEDAI_LEO_CONTEXT_ENGINE", "")).strip().lower()
    if not raw:
        return "medspacy"
    if raw not in KNOWN_CONTEXT_ENGINES:
        raise ValueError(
            f"unknown context engine {raw!r}; known: {', '.join(KNOWN_CONTEXT_ENGINES)}. "
            "This is an ablation inside E, not a phenotype system."
        )
    return raw


def _fill_sentence(entity, text: str) -> None:
    from rules.sentence_context import sentence_span
    s, e = sentence_span(text, entity.char_start, entity.char_end)
    entity.sentence_text = text[s:e]
    entity.sentence_start = s


def _apply_sentence(entity, text: str) -> None:
    from rules.sentence_context import history_cue, negated, option_only
    from services.ext_detectors.span import FAMILY, family_only, sentence_window
    _fill_sentence(entity, text)
    entity.is_negated = negated(text, entity.char_start, entity.char_end)
    entity.is_hypothetical = option_only(text, entity.char_start, entity.char_end)
    entity.is_historical = history_cue(text, entity.char_start, entity.char_end)
    sent, ms, _ = sentence_window(text, entity.char_start, entity.char_end)
    entity.is_family = family_only(sent, ms) or bool(FAMILY.search(sent[:ms]))


def _apply_negex(entity, text: str) -> None:
    from services.ext_detectors.span import (
        CURRENT, HISTORICAL, HYPO, family_only, pre_negated, sentence_window,
    )
    _fill_sentence(entity, text)
    sent, ms, _ = sentence_window(text, entity.char_start, entity.char_end)
    entity.is_negated = pre_negated(sent, ms)
    entity.is_family = family_only(sent, ms)
    entity.is_hypothetical = bool(HYPO.search(sent))
    entity.is_historical = bool(HISTORICAL.search(sent)) and not CURRENT.search(sent)


def attach_entity_context(entities: list, text: str, nlp=None, engine: str = "medspacy"):
    """Decorate ``LinkedEntity`` flags. ``engine='medspacy'`` is the shipped default."""
    engine = parse_context_engine(engine)
    if engine == "medspacy":
        from services.medcat_extractor import attach_medspacy_context
        if nlp is None:
            raise ValueError("medspacy context engine needs a spaCy/medspaCy nlp")
        return attach_medspacy_context(entities, text, nlp)

    doc = None
    if nlp is not None:
        doc = nlp.make_doc(text)
        for name, component in nlp.pipeline:
            if "context" in name.lower():
                continue
            doc = component(doc)
    apply = _apply_sentence if engine == "sentence" else _apply_negex
    for e in entities:
        apply(e, text)
    return doc


__all__ = ["KNOWN_CONTEXT_ENGINES", "parse_context_engine", "attach_entity_context"]
