"""medspaCy ConText configuration for MedAI-EPI.

Phase 2 deliverable §3. Builds a spaCy :class:`spacy.language.Language`
pipeline with:

- ``en_core_web_sm`` base model (tokeniser + tagger)
- medspaCy PyRuSH sentencizer (clinical-note-aware sentence boundaries)
- medspaCy :class:`medspacy.context.ConText` with:
  1. medspaCy's US-VA-tuned default rule set (102 rules across NEGATED,
     HISTORICAL, HYPOTHETICAL, POSSIBLE, FAMILY, PSEUDO, TERMINATE).
  2. A curated set of US-clinical additions filling gaps we identified
     against the ExECT-V2 (UK) trigger lists.

Trigger source policy
---------------------
- **medspaCy defaults**: adopted verbatim — Apache-2.0 licensed, US-VA
  tuned for clinical notes. See
  ``medspacy/resources/context/en/generic_targets.json``.
- **US-clinical additions**: our own list of gap-filler triggers derived
  from clinical-practice review (epilepsy-clinic vernacular: "denies",
  "no evidence of", "hx of", "s/p", "r/o", …). These are re-derivations of
  standard American clinical shorthand and do NOT copy any single line
  verbatim from ExECT-V2's proprietary trigger files.
- **ExECT-V2 trigger lists**: read as reference (see
  ``references/exect_v2/plugins/Tagger_ConText/resources/gazetteers/
  triggers/*.lst``, 432 lines total, UK-tuned) to check what phrases we
  might otherwise miss. We do NOT copy the ExECT lists into our tree; we
  re-express US-neutral variants in our own words below.

We tag each of our additions with its ``source`` in ``metadata`` so a
reviewer can filter later.
"""

from __future__ import annotations

import os
from typing import Any, Optional

# PyRuSH (the sentencizer) logs every token of every document at DEBUG through
# loguru's default stderr handler.  That writes the full note text into job logs,
# which is unacceptable for real clinical notes.  Drop it unless explicitly asked.
if os.environ.get("MEDAI_DEBUG_NLP", "").lower() not in ("1", "true", "yes"):
    try:  # pragma: no cover
        from loguru import logger as _loguru_logger

        _loguru_logger.remove()
    except Exception:
        pass

try:  # pragma: no cover - runtime dep on medspacy/spacy
    import medspacy
    import spacy
    from medspacy.context import ConText, ConTextRule
    from spacy.language import Language
except Exception as _e:  # pragma: no cover
    medspacy = None  # type: ignore
    spacy = None  # type: ignore
    ConText = None  # type: ignore
    ConTextRule = None  # type: ignore
    Language = Any  # type: ignore


# ---------------------------------------------------------------------------
# US-clinical additions (our own; not copied from ExECT)
# ---------------------------------------------------------------------------
# Each tuple: (literal, category, direction, metadata)
#
# NEGATED_EXISTENCE — additive over medspaCy defaults
_US_ADDITIONS: list[tuple[str, str, str, dict[str, str]]] = [
    # -- Negation, pre-condition ------------------------------------------------
    ("denies",                 "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("denied",                 "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("no evidence of",         "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("no h/o",                 "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-abbreviation"}),
    ("negative for",           "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("no signs of",            "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("no symptoms of",         "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("without",                "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("pt reports no",          "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("patient reports no",     "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("unremarkable for",       "NEGATED_EXISTENCE", "FORWARD",  {"source": "us-clinical-vernacular"}),
    # -- Historical -------------------------------------------------------------
    ("history of",             "HISTORICAL",        "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("hx of",                  "HISTORICAL",        "FORWARD",  {"source": "us-clinical-abbreviation"}),
    ("h/o",                    "HISTORICAL",        "FORWARD",  {"source": "us-clinical-abbreviation"}),
    ("s/p",                    "HISTORICAL",        "FORWARD",  {"source": "us-clinical-abbreviation"}),
    ("status post",            "HISTORICAL",        "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("previously",             "HISTORICAL",        "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("in the past",            "HISTORICAL",        "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("prior to admission",     "HISTORICAL",        "FORWARD",  {"source": "us-clinical-vernacular"}),
    # -- Phase 8 Iter 1 additions: expanded HISTORICAL cues for prior-med
    # detection.  Each is FORWARD scoped so the modifier reaches the drug
    # entity immediately after the trigger phrase.
    ("previously tried",       "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("previously on",          "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("was previously on",      "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("used to take",           "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("used to be on",          "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("history of taking",      "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("history of using",       "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("no longer on",           "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("stopped",                "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("discontinued",           "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("she stopped",            "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("he stopped",             "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("years ago",              "HISTORICAL",        "BACKWARD", {"source": "phase8-us-clinical"}),
    ("during childhood",       "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("in her teens",           "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("in his teens",           "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("in her twenties",        "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("in his twenties",        "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("has tried",              "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("she has tried",          "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("he has tried",           "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("she tried",              "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("he tried",               "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("switched from",          "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("switching from",         "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("changing from",          "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("weaned off",             "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("tapered off",            "HISTORICAL",        "FORWARD",  {"source": "phase8-us-clinical"}),
    ("of her own accord",      "HISTORICAL",        "BACKWARD", {"source": "phase8-us-clinical"}),
    ("of his own accord",      "HISTORICAL",        "BACKWARD", {"source": "phase8-us-clinical"}),
    # -- Hypothetical / rule-out ------------------------------------------------
    ("if",                     "HYPOTHETICAL",      "FORWARD",  {"source": "medspacy-parity"}),
    ("unless",                 "HYPOTHETICAL",      "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("would consider",         "HYPOTHETICAL",      "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("r/o",                    "HYPOTHETICAL",      "FORWARD",  {"source": "us-clinical-abbreviation"}),
    ("rule out",               "HYPOTHETICAL",      "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("possible",               "POSSIBLE_EXISTENCE","FORWARD",  {"source": "us-clinical-vernacular"}),
    ("suspected",              "POSSIBLE_EXISTENCE","FORWARD",  {"source": "us-clinical-vernacular"}),
    ("presumed",               "POSSIBLE_EXISTENCE","FORWARD",  {"source": "us-clinical-vernacular"}),
    # -- Family / experiencer ---------------------------------------------------
    ("family history of",      "FAMILY",            "FORWARD",  {"source": "us-clinical-vernacular"}),
    ("family hx of",           "FAMILY",            "FORWARD",  {"source": "us-clinical-abbreviation"}),
    ("fhx of",                 "FAMILY",            "FORWARD",  {"source": "us-clinical-abbreviation"}),
    # -- Pseudo-negation (prevent false NEG on 'no change', 'not only', …) ------
    ("no change",              "NEGATED_EXISTENCE", "PSEUDO",   {"source": "medspacy-parity"}),
    ("no significant change",  "NEGATED_EXISTENCE", "PSEUDO",   {"source": "medspacy-parity"}),
    ("not only",               "NEGATED_EXISTENCE", "PSEUDO",   {"source": "medspacy-parity"}),
    ("not necessarily",        "NEGATED_EXISTENCE", "PSEUDO",   {"source": "medspacy-parity"}),
    # -- Termination (scope-bounding conjunctions) ------------------------------
    ("but",                    "CONJ",              "TERMINATE",{"source": "medspacy-parity"}),
    ("however",                "CONJ",              "TERMINATE",{"source": "medspacy-parity"}),
]

#: Count of ExECT-V2 trigger phrases we consulted (not copied verbatim).
#: Sum of `wc -l` over the ten .lst files under ``resources/gazetteers/
#: triggers/`` in ``references/exect_v2``.
EXECT_TRIGGERS_CONSULTED: int = 432


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

def _add_us_rules(context: "ConText") -> int:
    """Register the US-clinical additions on an existing ConText component.

    Returns the number of rules actually added (a rule is skipped if its
    (literal, category) pair is already in the component).
    """
    existing = {(r.literal.lower(), r.category) for r in context.rules}
    added = 0
    for literal, category, direction, meta in _US_ADDITIONS:
        key = (literal.lower(), category)
        if key in existing:
            continue
        rule = ConTextRule(
            literal=literal,
            category=category,
            direction=direction,
            metadata=meta,
        )
        context.add([rule])
        existing.add(key)
        added += 1
    return added


def build_medspacy_pipeline(
    base_model: str = "en_core_web_sm",
    *,
    add_us_rules: bool = True,
) -> "Language":
    """Return a spaCy :class:`Language` object with medspaCy ConText attached.

    Pipeline order (matches medspaCy.load() defaults):
        1. ``en_core_web_sm`` tokeniser + tagger + lemmatiser
        2. ``medspacy_pyrush`` sentencizer
        3. ``medspacy_context`` ConText tagger

    The ``medspacy_target_matcher`` component is NOT added — MedCAT handles
    span linking upstream; ConText only needs the sentence boundaries and
    modifier scopes.
    """
    if medspacy is None or spacy is None:
        raise RuntimeError(
            "medspacy / spacy not importable in this environment; use "
            "venv-medcat interpreter."
        )
    # medspacy.load builds a Language with pyrush + target_matcher + context
    # pre-registered. We remove target_matcher so entities from MedCAT stay
    # authoritative.
    nlp = medspacy.load(base_model, enable={"medspacy_pyrush", "medspacy_context"})
    ctx_comp: Optional[ConText] = None
    for name, comp in nlp.pipeline:
        if isinstance(comp, ConText):
            ctx_comp = comp
            break
    if ctx_comp is None:
        raise RuntimeError("ConText component not found in medspaCy pipeline.")

    n_default_before = len(ctx_comp.rules)
    n_added = _add_us_rules(ctx_comp) if add_us_rules else 0

    # Cache stats on the Language so callers can report them.
    nlp.meta.setdefault("medai_epi", {}).update({
        "medspacy_default_rules": n_default_before,
        "us_additions": n_added,
        "exect_consulted_triggers": EXECT_TRIGGERS_CONSULTED,
    })
    return nlp


def pipeline_stats(nlp: "Language") -> dict[str, Any]:
    """Return the ConText rule stats stashed on ``nlp.meta``."""
    return dict(nlp.meta.get("medai_epi", {}))


__all__ = [
    "build_medspacy_pipeline",
    "pipeline_stats",
    "EXECT_TRIGGERS_CONSULTED",
]
