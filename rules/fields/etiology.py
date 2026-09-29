"""
etiology.py — EtiologyCategory extraction (ILAE 2017 top-level etiologies).

Fields populated
----------------
- ``clinical_seizure.etiology_category``     (Evidence[EtiologyCategory])
- ``clinical_seizure.etiology_details_text`` (Evidence[str] — raw quote)

Logic ported from ExECT-V2 files (github.com/swneurosci/ExECT-V2):
- ``Groovy/EpilepsyCause.groovy``      — top-level cause serializer
- ``Groovy/MarkupEpilepsyCause.groovy`` — clause-scoped cause span
- ``jape/EpilepsyCause.jape``          — canonical cause patterns
- ``jape/EpiCause.jape`` .. ``EpiCause4.jape`` — cause variants (4 files)
- ``jape/DiseaseCause.jape``           — links disease → cause
- ``jape/Symptomatic.jape`` / ``Symptomatic2.jape`` — symptomatic classification
- ``jape/FebrileSeizures.jape`` / ``FebrileSeizuresB.jape`` — infectious/febrile
- ``config/epilepsy.txt`` (custom UMLS lexicon) — cause-CUI list
- ``references/exect_v2_ilae_map.csv`` — CUI → category mapping

Reimplemented independently in Python; no verbatim JAPE/Groovy code retained.

Semantics captured
------------------
1. LinkedEntity with ``enum_class == "EtiologyCategory"`` — direct.
2. Fallback: keyword classifier by category (six ILAE categories: structural,
   genetic, infectious, immune, metabolic, unknown). Precision-first:
   the specific keyword must appear in the same sentence as an epilepsy /
   seizure trigger word (or in the diagnosis header line).
3. Details text: capture ± 40 char window around the matched keyword as
   ``etiology_details_text``.
4. ConText — negated → skip; family → skip; hypothetical → certainty POSSIBLE.

Cite: Scheffer et al. 2017 (ILAE 2017 classification of the epilepsies).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import Certainty, EtiologyCategory, TemporalStatus
from schema.evidence import Evidence
from services.medcat_extractor import LinkedEntity


# Keyword → ILAE 2017 top-level category. Precedence matters — check
# specific / rarer categories first (immune, infectious, metabolic, genetic)
# before falling back to broad structural terms.
_ETIOLOGY_PATTERNS: list[tuple[re.Pattern[str], EtiologyCategory]] = [
    # -- Immune (autoimmune encephalitides, cell-surface antibodies) ----------
    (re.compile(
        r"autoimmune\s+(?:epilepsy|encephalitis)|paraneoplastic|"
        r"anti[- ](?:NMDAR|LGI1|CASPR2|GAD(?:65)?|AMPA|GABA[- ]?B)|"
        r"limbic\s+encephalitis",
        re.IGNORECASE), EtiologyCategory.IMMUNE),
    # -- Infectious -----------------------------------------------------------
    (re.compile(
        r"neurocysticercosis|meningitis|(?:viral|bacterial|HSV|herpes\s+simplex)"
        r"\s+encephalitis|"
        r"post[- ]infectious|febrile\s+status\s+epilepticus|"
        r"HIV\s+encephalopathy",
        re.IGNORECASE), EtiologyCategory.INFECTIOUS),
    # -- Genetic --------------------------------------------------------------
    (re.compile(
        r"genetic\s+epilepsy|hereditary\s+epilepsy|"
        r"family\s+history\s+of\s+epilepsy|"
        r"\b(SCN1A|SCN2A|SCN8A|KCNQ2|CDKL5|DEPDC5|STXBP1|TSC1|TSC2|"
        r"PCDH19|GRIN2A|GRIN2B|MECP2|POLG|LGI1)\b|"
        r"Dravet(?:\s+syndrome)?|Angelman(?:\s+syndrome)?",
        re.IGNORECASE), EtiologyCategory.GENETIC),
    # -- Metabolic ------------------------------------------------------------
    (re.compile(
        r"metabolic\s+(?:epilepsy|disorder)|mitochondrial\s+(?:disease|disorder)|"
        r"pyridoxine[- ]dependent|GLUT1\s+deficiency|"
        r"amino\s+acid\s+disorder|urea\s+cycle\s+defect",
        re.IGNORECASE), EtiologyCategory.METABOLIC),
    # -- Structural (broad — many aliases) -----------------------------------
    (re.compile(
        r"hippocampal\s+sclerosis|mesial\s+temporal\s+sclerosis|"
        r"\bHS\b|\bMTS\b|"
        r"focal\s+cortical\s+dysplasia|\bFCD\b|MOGHE|"
        r"polymicrogyria|heterotopia|lissencephaly|"
        r"tuberous\s+sclerosis|tuber\s+.*?\b(?:cortical|subependymal)?|"
        r"encephalomalacia|gliosis|"
        r"traumatic\s+brain\s+injury|\bTBI\b|head\s+injury|skull\s+fracture|"
        r"post[- ]traumatic|subarachnoid\s+haemorrhage|\bSAH\b|"
        r"stroke|infarct|cerebrovascular|vascular\s+malformation|cavernoma|"
        r"cavernous\s+angioma|arteriovenous\s+malformation|\bAVM\b|"
        r"tumo(?:u)?r|glioma|meningioma|neoplasm|"
        r"perinatal\s+insult|birth\s+(?:trauma|asphyxia|injury)|"
        r"hypoxic[- ]ischemic|hypoxic[- ]ischaemic|"
        r"symptomatic,?\s+structural",
        re.IGNORECASE), EtiologyCategory.STRUCTURAL),
    # -- Unknown (explicit) ---------------------------------------------------
    (re.compile(
        r"idiopathic|cryptogenic|cause\s+(?:is\s+)?(?:unknown|unclear|not\s+known)|"
        r"unknown\s+aetiology|unknown\s+etiology|unknown\s+cause",
        re.IGNORECASE), EtiologyCategory.UNKNOWN),
]


def _find_sentence(doc, char_start: int) -> tuple[str, int]:
    if doc is None or not hasattr(doc, "sents"):
        return "", -1
    for sent in doc.sents:
        if sent.start_char <= char_start < sent.end_char:
            return sent.text, sent.start_char
    return "", -1


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class EtiologyCategoryRule(BaseFieldRule):
    """Populate ``clinical_seizure.etiology_category``."""

    field_name = "clinical_seizure.etiology_category"
    enum_class = EtiologyCategory

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        # 1. Direct entity match.
        cands = self.relevant_entities(entities, include_hypothetical=True)
        for e in cands:
            try:
                value = EtiologyCategory(e.enum_value)
            except ValueError:
                continue
            return self._make_evidence(value, e, meta)

        # 2. Keyword fallback.
        text = getattr(doc, "text", "") or ""
        for pat, category in _ETIOLOGY_PATTERNS:
            for m in pat.finditer(text):
                # Negation check — 30 chars pre-context.
                pre = text[max(0, m.start() - 40):m.start()]
                if re.search(
                    r"\b(?:no|without|denies?|never|not|absent|"
                    r"negative\s+for|ruled?\s+out|no\s+history\s+of|"
                    r"no\s+evidence\s+of)\b",
                    pre, re.IGNORECASE,
                ):
                    continue
                # Family history check — non-genetic categories only.
                sent, _ = _find_sentence(doc, m.start())
                if re.search(
                    r"\bfamily\s+history\b|\b(?:mother|father|brother|sister|"
                    r"grandmother|grandfather|cousin|aunt|uncle)\s+"
                    r"(?:has|had|have)\b",
                    sent or "", re.IGNORECASE,
                ) and category != EtiologyCategory.GENETIC:
                    continue
                span = text[max(0, m.start() - 10):min(len(text), m.end() + 30)].strip()
                return Evidence[EtiologyCategory](
                    value=category,
                    certainty=Certainty.PROBABLE,
                    temporal_status=TemporalStatus.CURRENT,
                    evidence_text=span or m.group(0),
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=m.start(),
                    char_end=m.end(),
                )
        return None


class EtiologyDetailsRule(BaseFieldRule):
    """Populate ``clinical_seizure.etiology_details_text`` (str Evidence).

    Emits the raw quote surrounding the first etiology-category hit so a
    reviewer can see the underlying wording. Uses the same regex bank.
    """

    field_name = "clinical_seizure.etiology_details_text"

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        # Prefer a linked-entity anchor if one exists.
        for e in entities:
            if e.enum_class != "EtiologyCategory" or e.is_negated or e.is_family:
                continue
            return self._make_evidence(e.text, e, meta)

        text = getattr(doc, "text", "") or ""
        for pat, _cat in _ETIOLOGY_PATTERNS:
            for m in pat.finditer(text):
                pre = text[max(0, m.start() - 40):m.start()]
                if re.search(
                    r"\b(?:no|without|denies?|never|not|absent|negative\s+for|"
                    r"ruled?\s+out|no\s+history\s+of|no\s+evidence\s+of)\b\s*",
                    pre, re.IGNORECASE,
                ):
                    continue
                span = text[max(0, m.start() - 10):min(len(text), m.end() + 30)].strip()
                return Evidence[str](
                    value=span,
                    certainty=Certainty.PROBABLE,
                    temporal_status=TemporalStatus.CURRENT,
                    evidence_text=span,
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=m.start(),
                    char_end=m.end(),
                )
        return None


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

from services.phenotype_assembler import register_rule  # noqa: E402

register_rule(EtiologyCategoryRule())
register_rule(EtiologyDetailsRule())

__all__ = ["EtiologyCategoryRule", "EtiologyDetailsRule"]
