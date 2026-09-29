"""US section-aware ConText augmentation (Phase 4 deliverable §3).

Phase 2's ``rules.context_config.build_medspacy_pipeline`` already ships the
US-tuned medspaCy ConText defaults plus 30 US-clinical additions
(``denies``, ``h/o``, ``s/p``, ``r/o``, ``hx of``, ``family history of``,
…) — that file remains the *sentence-scope* source of truth.

What Phase 4 adds
-----------------
Section-scope context.  medspaCy ConText operates within a sentence; it
cannot express rules like "everything under ``PMH:`` until the next section
header is historical".  Phase 4's SOAP detector
(:mod:`rules.us_note_structure`) fills that gap by producing a list of
``Section`` spans, and this module wires those spans back to entity-level
context flags.

Concretely, :func:`apply_section_context` walks a list of
:class:`~services.medcat_extractor.LinkedEntity` records, looks each up in
the section list, and mutates the entity's context flags:

- entity in ``PMH`` / ``PSH`` -> ``is_historical=True`` (unless a sentence
  trigger already flipped it True — we only ever *promote*, never demote,
  so a "not historical" ConText attribute wins over the section default).
- entity in ``FAMILY_HISTORY`` -> ``is_family=True`` **and**
  ``is_historical=True``.
- entity in ``PLAN`` / ``RECOMMENDATIONS`` / ``IMPRESSION`` ->
  ``is_hypothetical=True`` when the sentence didn't already say so; the
  intent is "the rule dispatcher should route these to future/planned
  intents rather than confirmed current state".
- entity in ``MEDICATIONS`` -> no context change (medspaCy will handle the
  sentence-scope negation), but the section tag ``MEDICATIONS`` on the
  entity is picked up by ``rules/fields/medication.py`` to boost the
  ``currently_taking`` confidence.

The section overrides come from :data:`rules.us_note_structure.SECTION_CONTEXT_DEFAULT`.
This module deliberately owns *no* trigger literals of its own — it is a
composition layer, not a new rule set.

Diff vs Phase 2
---------------
- Phase 2 ``context_config.py``:  sentence-scope ConText rules (30 US
  additions on top of medspaCy defaults).
- Phase 4 ``context_config_us.py``:  section-scope defaults applied after
  ConText has run.  Zero new sentence-scope triggers; all information
  comes from the section detector's canonical section names.

Nothing here calls into spaCy; :func:`apply_section_context` is a plain
dataclass mutator.  That keeps the assembler free to call it either before
or after the medspaCy pass without worrying about token alignment.
"""

from __future__ import annotations

from typing import Iterable, Optional

from rules.us_note_structure import (
    Section,
    SECTION_CONTEXT_DEFAULT,   # noqa: F401 — re-exported for callers
    section_at,
)

try:  # pragma: no cover - dependency present in venv-medcat only
    from services.medcat_extractor import LinkedEntity
except Exception:  # pragma: no cover
    LinkedEntity = object  # type: ignore


# Documented list of new (relative to Phase 2) *section-scope* overrides
# provided by this module.  Each entry: (canonical_section, override_keys).
# ``override_keys`` are attributes on :class:`LinkedEntity` that this module
# is allowed to *promote* to ``True`` (never to demote from ``True`` to
# ``False``).
SECTION_SCOPE_OVERRIDES: dict[str, list[str]] = {
    "PMH":            ["is_historical"],
    "PSH":            ["is_historical"],
    "FAMILY_HISTORY": ["is_historical", "is_family"],
    "PLAN":           ["is_hypothetical"],
    "RECOMMENDATIONS":["is_hypothetical"],
    "IMPRESSION":     [],   # no promotion; only tag section_type
    "MEDICATIONS":    [],   # sentence-scope handles this
    "HPI":            [],
    "ROS":            [],
    "PE":             [],
    "NEURO_EXAM":     [],
    "LABS":           [],
    "IMAGING":        [],
    "DIAGNOSTIC_STUDIES": [],
    "ASSESSMENT":     [],
    "ALLERGIES":      [],
    "SOCIAL_HISTORY": [],
}


# Explicit target values Phase 4 promotes for each (section, flag) tuple.
# We keep this as a dedicated table (rather than reusing
# ``SECTION_CONTEXT_DEFAULT``) so ``us_note_structure.SECTION_CONTEXT_DEFAULT``
# stays a *description* of the section, and Phase 4's *policy* lives here.
_SECTION_PROMOTIONS: dict[str, dict[str, bool]] = {
    "PMH":             {"is_historical": True},
    "PSH":             {"is_historical": True},
    "FAMILY_HISTORY":  {"is_historical": True, "is_family": True},
    "PLAN":            {"is_hypothetical": True},
    "RECOMMENDATIONS": {"is_hypothetical": True},
}


def apply_section_context(
    entities: Iterable["LinkedEntity"],
    sections: list[Section],
    *,
    promote_only: bool = True,
) -> int:
    """Attach ``section_type`` and section-scope context overrides.

    Parameters
    ----------
    entities
        Iterable of :class:`LinkedEntity` (mutated in place).
    sections
        Output of :func:`rules.us_note_structure.detect_sections`.  When
        empty, only ``section_type`` mutation is skipped; nothing else
        changes.
    promote_only
        When ``True`` (default) a per-sentence ConText result that already
        marked an entity ``True`` on some flag is preserved.  When
        ``False``, the section default overwrites the flag unconditionally.

    Returns
    -------
    int
        Number of entities that received at least one flag or ``section_type``
        update.  Useful for smoke reports.
    """
    n = 0
    for e in entities:
        # 1. section_type — always populated from the char range.
        sec_name = section_at(sections, e.char_start) if sections else None
        setattr(e, "section_type", sec_name)
        changed = False

        # 2. flag promotion for the sections we chose to enrich.
        if sec_name is None:
            continue
        keys = SECTION_SCOPE_OVERRIDES.get(sec_name, [])
        if not keys:
            if sec_name is not None:
                n += 1
            continue

        promotions = _SECTION_PROMOTIONS.get(sec_name, {})
        for k in keys:
            want = bool(promotions.get(k, False))
            if not want:
                continue
            cur = bool(getattr(e, k, False))
            if promote_only and cur:
                continue
            setattr(e, k, want)
            changed = True

        if changed or sec_name is not None:
            n += 1
    return n


def section_scope_summary() -> dict[str, list[str]]:
    """Return a copy of :data:`SECTION_SCOPE_OVERRIDES` for reporting."""
    return {k: list(v) for k, v in SECTION_SCOPE_OVERRIDES.items()}


__all__ = [
    "SECTION_SCOPE_OVERRIDES",
    "apply_section_context",
    "section_scope_summary",
]
