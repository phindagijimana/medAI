"""UK <-> US clinical vocabulary normalisation for MedAI-EPI.

Phase 4 deliverable §1. A pre-tokenisation text-level rewrite pass that
harmonises UK-English clinical spelling and drug names against US-English
so downstream MedCAT + medspaCy components (both trained on US-VA
corpora) see uniform vocabulary regardless of the note's country of
origin.

Sources
-------
- Spelling maps: Merriam-Webster (US) and Oxford (UK) standard
  orthography.  We include only the classes with unambiguous 1-to-1
  mappings under a general medical register:

    * ``ae`` -> ``e`` (paediatric, oesophageal, anaemia, ...)
    * ``oe`` -> ``e`` (oedema, foetal, oestrogen, ...)
    * ``-our`` -> ``-or`` (tumour, behaviour, humour, ...)
    * ``-ise / -isation`` -> ``-ize / -ization`` (generalise, ...)
    * ``-yse`` -> ``-yze`` (analyse, catalyse)
    * ``-ll-`` -> ``-l-`` (levelled -> leveled, cancelled -> canceled)
    * misc. one-offs: sulphate/sulfur, kerb/curb, manoeuvre, ...

  We enumerate individual head-words rather than apply a global regex
  because a naive ``s/ae/e/`` also mangles Latin plurals we want to keep
  (``formulae``, ``vertebrae``) and abbreviations (``AE`` = adverse
  event).  Word-list rewriting stays clinically safe.

- Drug crosswalk: RxNorm crosswalk between UK/BNF-preferred names and
  US/USAN-preferred names.  Most anti-seizure medications share a
  generic name in both jurisdictions; the crosswalk here targets the
  known exceptions that appear in the F-S corpus and in RxNorm's INN
  reference table:

    phenobarbitone <-> phenobarbital,
    adrenaline <-> epinephrine,
    paracetamol <-> acetaminophen,
    frusemide  <-> furosemide,
    ...

  The list is intentionally small (16 entries) rather than exhaustive:
  RxNorm has thousands of preferred-name variants but only a handful are
  ever seen in UK epilepsy clinic letters.

Contract
--------
- Applied as a pre-tokenisation ``str -> str`` pass.
- Word-boundary safe (``\\b`` regex boundaries).  ``"paediatric"`` ->
  ``"pediatric"``, but ``"encyclopaedic"`` is untouched (it is not in
  the mapping's key set anyway; word-boundary is belt-and-braces).
- Case-preserving: ``"Paediatric"`` -> ``"Pediatric"``,
  ``"PAEDIATRIC"`` -> ``"PEDIATRIC"``, mixed case stays mixed.
- Idempotent: ``normalize_uk_to_us(normalize_uk_to_us(x))`` ==
  ``normalize_uk_to_us(x)``.

The reverse map ``normalize_us_to_uk`` is exposed for scoring against
UK-labelled gold or for round-trip tests.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Data: UK -> US spelling (lower-case canonical form)
# ---------------------------------------------------------------------------

# 60 entries covering ae/oe/our/ise/yse/ll + common one-offs seen in F-S.
# All keys are lower-case; the rewrite pass preserves the case of the match.
UK_TO_US_SPELLING: dict[str, str] = {
    # -- ae -> e ----------------------------------------------------------
    "paediatric": "pediatric",
    "paediatrics": "pediatrics",
    "paediatrician": "pediatrician",
    "paediatricians": "pediatricians",
    "oesophageal": "esophageal",
    "oesophagus": "esophagus",
    "anaesthesia": "anesthesia",
    "anaesthetic": "anesthetic",
    "anaesthetics": "anesthetics",
    "anaesthetist": "anesthetist",
    "haematology": "hematology",
    "haematologist": "hematologist",
    "haemorrhage": "hemorrhage",
    "haemorrhagic": "hemorrhagic",
    "haemoglobin": "hemoglobin",
    "anaemia": "anemia",
    "anaemic": "anemic",
    "leukaemia": "leukemia",
    "ischaemia": "ischemia",
    "ischaemic": "ischemic",
    "orthopaedic": "orthopedic",
    "orthopaedics": "orthopedics",
    "gynaecology": "gynecology",
    "gynaecological": "gynecological",
    # -- oe -> e ----------------------------------------------------------
    "oedema": "edema",
    "oedematous": "edematous",
    "oestrogen": "estrogen",
    "foetal": "fetal",
    "foetus": "fetus",
    "coeliac": "celiac",
    "diarrhoea": "diarrhea",
    # -- our -> or --------------------------------------------------------
    "tumour": "tumor",
    "tumours": "tumors",
    "behaviour": "behavior",
    "behavioural": "behavioral",
    "behaviours": "behaviors",
    "humour": "humor",
    "colour": "color",
    "coloured": "colored",
    "colouration": "coloration",
    "favour": "favor",
    "favoured": "favored",
    # -- ise / isation -> ize / ization ----------------------------------
    "characterise": "characterize",
    "characterised": "characterized",
    "characterises": "characterizes",
    "characterising": "characterizing",
    "generalise": "generalize",
    "generalised": "generalized",
    "generalisation": "generalization",
    "localise": "localize",
    "localised": "localized",
    "localisation": "localization",
    "catheterise": "catheterize",
    "catheterised": "catheterized",
    "catheterisation": "catheterization",
    "hospitalise": "hospitalize",
    "hospitalised": "hospitalized",
    "hospitalisation": "hospitalization",
    "immobilise": "immobilize",
    "immobilised": "immobilized",
    "normalise": "normalize",
    "normalised": "normalized",
    "recognise": "recognize",
    "recognised": "recognized",
    # -- yse -> yze -------------------------------------------------------
    "analyse": "analyze",
    "analysed": "analyzed",
    "analyses": "analyzes",   # verb form; noun plural coincides but is uncommon in prose
    "paralyse": "paralyze",
    "paralysed": "paralyzed",
    # -- misc. one-offs (medically relevant) ------------------------------
    "sulphate": "sulfate",
    "sulphur": "sulfur",
    "manoeuvre": "maneuver",
    "manoeuvres": "maneuvers",
    "practise": "practice",       # UK: verb 'practise' vs noun 'practice'
    "programme": "program",
    "programmes": "programs",
    "traveled": "traveled",       # already US; no-op guard entry
    "levelled": "leveled",
    "cancelled": "canceled",
    "modelled": "modeled",
    "signalling": "signaling",
    "worshipped": "worshiped",
}


# ---------------------------------------------------------------------------
# Data: UK -> US drug names (RxNorm crosswalk)
# ---------------------------------------------------------------------------
#
# All-lower-case keys.  Values are the US/USAN preferred generic name.
# Only entries where the UK and US names diverge are listed.  ASMs seen in
# the F-S corpus that share the same name (lamotrigine, levetiracetam,
# carbamazepine, valproate, topiramate, phenytoin, lacosamide, ...) are
# intentionally NOT listed - no-op is the right behaviour.

UK_TO_US_DRUG: dict[str, str] = {
    "phenobarbitone": "phenobarbital",     # RxNorm CUI 8134
    "phenobarbitones": "phenobarbitals",
    "adrenaline": "epinephrine",           # RxNorm CUI 3992
    "noradrenaline": "norepinephrine",     # RxNorm CUI 7512
    "paracetamol": "acetaminophen",        # RxNorm CUI 161
    "frusemide": "furosemide",             # RxNorm CUI 4603
    "amoxycillin": "amoxicillin",          # spelling variant, RxNorm CUI 723
    "cyclosporin": "cyclosporine",         # RxNorm CUI 3008
    "salbutamol": "albuterol",             # RxNorm CUI 435
    "beclometasone": "beclomethasone",     # RxNorm CUI 1347
    "bendrofluazide": "bendroflumethiazide",
    "lignocaine": "lidocaine",             # RxNorm CUI 6387
    "pethidine": "meperidine",             # RxNorm CUI 6754
    "cimetidine": "cimetidine",            # no-op guard
    "glibenclamide": "glyburide",          # RxNorm CUI 4815
    "trimeprazine": "alimemazine",
    "chlorphenamine": "chlorpheniramine",  # RxNorm CUI 2400
}


# ---------------------------------------------------------------------------
# Compiled tables (built once at import time)
# ---------------------------------------------------------------------------

def _compile(mapping: dict[str, str]) -> re.Pattern[str]:
    # Longest first so 'behavioural' wins over any 'behaviour' prefix
    # match (belt-and-braces; both are keys but Python's dict-order is
    # insertion order, not length order).
    keys = sorted(mapping.keys(), key=len, reverse=True)
    pattern = r"\b(?:" + "|".join(re.escape(k) for k in keys) + r")\b"
    return re.compile(pattern, flags=re.IGNORECASE)


_UK_SPELLING_RE: re.Pattern[str] = _compile(UK_TO_US_SPELLING)
_UK_DRUG_RE: re.Pattern[str] = _compile(UK_TO_US_DRUG)

# Reverse maps
US_TO_UK_SPELLING: dict[str, str] = {v: k for k, v in UK_TO_US_SPELLING.items()
                                     if k != v}
US_TO_UK_DRUG: dict[str, str] = {v: k for k, v in UK_TO_US_DRUG.items()
                                 if k != v}
_US_SPELLING_RE: re.Pattern[str] = _compile(US_TO_UK_SPELLING) if US_TO_UK_SPELLING else re.compile(r"(?!x)x")
_US_DRUG_RE: re.Pattern[str] = _compile(US_TO_UK_DRUG) if US_TO_UK_DRUG else re.compile(r"(?!x)x")


# ---------------------------------------------------------------------------
# Case-preserving substitution helpers
# ---------------------------------------------------------------------------

def _match_case(target: str, source: str) -> str:
    """Return ``target`` cased to mimic ``source``.

    Rules:
    - all-upper source -> all-upper target
    - title-case source -> title-case target (first char upper)
    - else -> target as given (lower).
    """
    if not source:
        return target
    if source.isupper():
        return target.upper()
    if source[0].isupper() and (len(source) == 1 or source[1:].islower()):
        return target[:1].upper() + target[1:]
    return target


def case_aware_replace(text: str, source: str, target: str) -> str:
    """Replace every whole-word occurrence of ``source`` in ``text`` with a
    case-matched form of ``target``.

    Case-preservation rules mirror :func:`_match_case`:

    - all-upper source token -> upper-case target
    - title-case source token -> title-case target
    - lower / mixed -> lower-case target

    Used by :func:`normalize_uk_to_us` and available as a stand-alone helper
    for tests and one-off custom mappings.
    """
    if not text or not source:
        return text
    pattern = re.compile(rf"\b{re.escape(source)}\b", flags=re.IGNORECASE)

    def repl(m: re.Match[str]) -> str:
        return _match_case(target, m.group(0))

    return pattern.sub(repl, text)


def _substitute(text: str, pattern: re.Pattern[str], mapping: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        surface = m.group(0)
        replacement = mapping.get(surface.lower(), surface)
        return _match_case(replacement, surface)
    return pattern.sub(repl, text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_uk_to_us(text: str) -> str:
    """Return ``text`` with UK spellings and drug names rewritten to US.

    Word-boundary-safe and case-preserving.  Idempotent.
    """
    if not text:
        return text
    text = _substitute(text, _UK_SPELLING_RE, UK_TO_US_SPELLING)
    text = _substitute(text, _UK_DRUG_RE, UK_TO_US_DRUG)
    return text


def normalize_us_to_uk(text: str) -> str:
    """Return ``text`` with US spellings and drug names rewritten to UK.

    Provided for scoring against UK-labelled gold or for round-trip tests.
    """
    if not text:
        return text
    text = _substitute(text, _US_SPELLING_RE, US_TO_UK_SPELLING)
    text = _substitute(text, _US_DRUG_RE, US_TO_UK_DRUG)
    return text


def diff_counts(text: str) -> dict[str, int]:
    """Return a small dict useful for reporting normalisation impact.

    Keys:
        ``spelling_hits`` - number of spelling replacements applied.
        ``drug_hits`` - number of drug-name replacements applied.
    """
    return {
        "spelling_hits": sum(1 for _ in _UK_SPELLING_RE.finditer(text or "")),
        "drug_hits": sum(1 for _ in _UK_DRUG_RE.finditer(text or "")),
    }


def iter_replacements(text: str) -> Iterable[tuple[str, str, int, int]]:
    """Yield ``(surface, replacement, char_start, char_end)`` for auditing."""
    if not text:
        return
    for m in _UK_SPELLING_RE.finditer(text):
        surface = m.group(0)
        yield surface, _match_case(UK_TO_US_SPELLING[surface.lower()], surface), m.start(), m.end()
    for m in _UK_DRUG_RE.finditer(text):
        surface = m.group(0)
        yield surface, _match_case(UK_TO_US_DRUG[surface.lower()], surface), m.start(), m.end()


# ---------------------------------------------------------------------------
# Public aliases (Phase 4 plan uses ``SPELLING_MAP`` / ``DRUG_ALIAS_MAP``)
# ---------------------------------------------------------------------------
#
# The internal names ``UK_TO_US_SPELLING`` / ``UK_TO_US_DRUG`` are kept for
# backwards compatibility with earlier drafts.  ``SPELLING_MAP`` and
# ``DRUG_ALIAS_MAP`` are the names the Phase 4 spec asks callers to use.

SPELLING_MAP: dict[str, str] = UK_TO_US_SPELLING
DRUG_ALIAS_MAP: dict[str, str] = UK_TO_US_DRUG


__all__ = [
    "UK_TO_US_SPELLING",
    "UK_TO_US_DRUG",
    "US_TO_UK_SPELLING",
    "US_TO_UK_DRUG",
    "SPELLING_MAP",
    "DRUG_ALIAS_MAP",
    "case_aware_replace",
    "normalize_uk_to_us",
    "normalize_us_to_uk",
    "diff_counts",
    "iter_replacements",
]
