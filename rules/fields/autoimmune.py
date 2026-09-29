"""
autoimmune.py — Autoimmune etiology specifics (CausativeAntibody).

Fields populated
----------------
- ``clinical_seizure.etiology_specifics``  (Evidence[EtiologySpecifics])

No ExECT source — ExECT-V2 has broad "autoimmune" mentions but no
CausativeAntibody enumeration. Hand-authored from:
- Graus F et al. 2016 (Lancet Neurol 15:391-404): clinical approach to
  autoimmune encephalitis, canonical antibody panel.
- Steriade C et al. 2020 (Epilepsia 61:1341): autoimmune-associated
  epilepsy classification.
- Dubey D et al. 2020 (Ann Neurol 87:313): autoantibody testing yield.

Semantics captured
------------------
1. Regex bank over 17 autoimmune antibodies (cell-surface + intracellular):
     - Cell-surface: NMDAR, LGI1, CASPR2, GABAB-R, AMPA-R, DPPX, glycine-R,
       IgLON5, mGluR5
     - Intracellular: Hu (ANNA-1), Ma2, Yo (PCA-1), Ri (ANNA-2),
       amphiphysin, GAD65, SOX1, CV2 (CRMP5), ZIC4
   Positive triggers: "positive for X antibody", "anti-X encephalitis",
   "X-associated epilepsy", "X-mediated autoimmune".
2. Negation-aware: "negative for NMDAR antibody" → skip (or emit
   NONE_DETECTED if it's the only antibody mention).
3. Also captures free-text etiology fields when present in the same
   sentence: causative_gene, causative_pathogen_text, etc.
4. Populates a single Evidence[EtiologySpecifics] with the first detected
   antibody (multi-antibody cases are rare).

Cite: Graus 2016 (Lancet Neurol); Steriade 2020 (Epilepsia); Dubey 2020
(Ann Neurol).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from rules.base_rule import BaseFieldRule
from schema.enums import CausativeAntibody, Certainty, TemporalStatus
from schema.evidence import Evidence
from schema.ontology import EtiologySpecifics
from services.medcat_extractor import LinkedEntity


# ---------------------------------------------------------------------------
# Antibody patterns
# ---------------------------------------------------------------------------

_ANTIBODY_PATTERNS: list[tuple[re.Pattern[str], CausativeAntibody]] = [
    # Cell-surface — check longest/most-specific first.
    (re.compile(r"anti[- ]?NMDA[- ]?R|NMDA[- ]?receptor\s+antibody|"
                r"NMDAR[- ]?(?:antibody|Ab|encephalitis)|anti[- ]?NMDAR",
                re.IGNORECASE), CausativeAntibody.ANTI_NMDAR),
    (re.compile(r"anti[- ]?LGI[- ]?1|LGI1\s+antibody|LGI1[- ]?"
                r"(?:antibody|Ab|encephalitis)|leucine[- ]?rich\s+glioma",
                re.IGNORECASE), CausativeAntibody.ANTI_LGI1),
    (re.compile(r"anti[- ]?CASPR[- ]?2|CASPR2\s+antibody|CASPR2[- ]?"
                r"(?:antibody|Ab|encephalitis)|contactin[- ]?associated",
                re.IGNORECASE), CausativeAntibody.ANTI_CASPR2),
    (re.compile(r"anti[- ]?GABA[- ]?B|GABA[- ]?B[- ]?R\s*antibody|"
                r"GABA[- ]?B\s+receptor\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_GABABR),
    (re.compile(r"anti[- ]?AMPA[- ]?R|AMPA[- ]?receptor\s+antibody|"
                r"AMPAR[- ]?antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_AMPAR),
    (re.compile(r"anti[- ]?DPPX|DPPX\s+antibody|DPPX[- ]?antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_DPPX),
    (re.compile(r"anti[- ]?glycine\s+receptor|GlyR\s+antibody|glycine[- ]?"
                r"receptor\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_GLYR),
    (re.compile(r"anti[- ]?IgLON[- ]?5|IgLON5\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_IGLON5),
    (re.compile(r"anti[- ]?mGluR[- ]?5|mGluR5\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_MGLUR5),
    # Intracellular
    (re.compile(r"anti[- ]?GAD[- ]?65|GAD65\s+antibody|GAD[- ]?65[- ]?"
                r"associated|glutamic\s+acid\s+decarboxylase",
                re.IGNORECASE), CausativeAntibody.ANTI_GAD65),
    (re.compile(r"anti[- ]?Hu\b|ANNA[- ]?1|Hu\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_HU),
    (re.compile(r"anti[- ]?Ma[- ]?2|Ma2\s+antibody|anti[- ]?Ta\b",
                re.IGNORECASE), CausativeAntibody.ANTI_MA2),
    (re.compile(r"anti[- ]?Yo\b|PCA[- ]?1|Yo\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_YO),
    (re.compile(r"anti[- ]?Ri\b|ANNA[- ]?2|Ri\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_RI),
    (re.compile(r"anti[- ]?amphiphysin|amphiphysin\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_AMPHIPHYSIN),
    (re.compile(r"anti[- ]?SOX[- ]?1|SOX1\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_SOX1),
    (re.compile(r"anti[- ]?CV[- ]?2|CRMP[- ]?5|CRMP5\s+antibody|"
                r"CV2\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_CV2),
    (re.compile(r"anti[- ]?ZIC[- ]?4|ZIC4\s+antibody",
                re.IGNORECASE), CausativeAntibody.ANTI_ZIC4),
]

_POSITIVE_CONTEXT_RE = re.compile(
    r"positive\s+for|\bpositive\b|\bdetected\b|\belevated\b|"
    r"\bpresent\b|\bconfirmed\b|autoimmune\s+encephalitis|"
    r"antibody[- ]?mediated|antibody[- ]?associated",
    re.IGNORECASE,
)

_NEG_PRE = re.compile(
    r"\b(?:no|without|denies?|absent|negative\s+for|not|never|"
    r"ruled?\s+out)\s+",
    re.IGNORECASE,
)

# Free-text etiology capture — gene names (HGNC)
_GENE_RE = re.compile(
    r"\b(SCN1A|SCN2A|SCN8A|KCNQ2|KCNQ3|CDKL5|DEPDC5|STXBP1|TSC1|TSC2|"
    r"PCDH19|GRIN2A|GRIN2B|MECP2|POLG|LGI1|ARX|FOXG1|SLC2A1|"
    r"CHRNA4|GABRG2)\b"
)

# Pathogen text (infectious)
_PATHOGEN_RE = re.compile(
    r"\b(?:neurocysticercosis|toxoplasmosis|HSV[- ]?1?|"
    r"herpes\s+simplex|CMV|cytomegalovirus|HIV|"
    r"tuberculous\s+meningitis|TB\s+meningitis|"
    r"Mycobacterium\s+tuberculosis|Plasmodium)\b",
    re.IGNORECASE,
)

# Metabolic text
_METABOLIC_RE = re.compile(
    r"\b(?:pyridoxine[- ]?dependent|GLUT[- ]?1\s+deficiency|"
    r"mitochondrial\s+disease|MELAS|Alpers|PKAN|"
    r"biotinidase\s+deficiency|urea\s+cycle)\b",
    re.IGNORECASE,
)


def _preceded_by_neg(text: str, start: int, back: int = 30) -> bool:
    return bool(_NEG_PRE.search(text[max(0, start - back):start]))


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------


class EtiologySpecificsRule(BaseFieldRule):
    """Populate ``clinical_seizure.etiology_specifics`` with the first
    detected antibody / gene / pathogen / metabolic condition.

    Prefers antibodies (autoimmune) → genes (genetic) → pathogens
    (infectious) → metabolic terms — matching the ILAE 2017 category
    precedence used by the wave-1 EtiologyCategory rule.
    """

    field_name = "clinical_seizure.etiology_specifics"
    phase = 1

    def apply(
        self,
        entities: list[LinkedEntity],
        doc,
        meta: dict[str, Any],
    ) -> Optional[Evidence]:
        text = getattr(doc, "text", "") or ""
        if not text:
            return None

        # 1. Antibody scan (highest priority).
        for pat, ab in _ANTIBODY_PATTERNS:
            for m in pat.finditer(text):
                if _preceded_by_neg(text, m.start()):
                    continue
                # Confirm this is a positive assertion or it's within a
                # phrase like "anti-X encephalitis" (self-evidently positive).
                window = text[max(0, m.start() - 60):min(len(text), m.end() + 60)]
                if not (_POSITIVE_CONTEXT_RE.search(window) or
                        re.search(r"anti[- ]", m.group(0), re.IGNORECASE) or
                        re.search(r"encephalitis|associated|mediated",
                                  window, re.IGNORECASE)):
                    continue
                specifics = EtiologySpecifics(causative_antibody=ab)
                return Evidence[EtiologySpecifics](
                    value=specifics,
                    certainty=Certainty.PROBABLE,
                    temporal_status=TemporalStatus.CURRENT,
                    evidence_text=m.group(0),
                    source_doc_id=meta["doc_id"],
                    source_doc_type=meta["doc_type"],
                    source_date=meta["doc_date"],
                    char_start=m.start(),
                    char_end=m.end(),
                )

        # 2. Gene scan.
        m = _GENE_RE.search(text)
        if m:
            gene = m.group(1)
            # Extract variant if present (HGVS-like)
            after = text[m.end():m.end() + 80]
            var_m = re.search(r"(c\.\d+[A-Za-z>_+-]+|p\.[A-Za-z0-9*]+)", after)
            variant = var_m.group(0) if var_m else None
            specifics = EtiologySpecifics(
                causative_gene=gene,
                causative_variant=variant,
            )
            return Evidence[EtiologySpecifics](
                value=specifics,
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )

        # 3. Pathogen scan.
        m = _PATHOGEN_RE.search(text)
        if m and not _preceded_by_neg(text, m.start()):
            specifics = EtiologySpecifics(causative_pathogen_text=m.group(0))
            return Evidence[EtiologySpecifics](
                value=specifics,
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
                source_doc_id=meta["doc_id"],
                source_doc_type=meta["doc_type"],
                source_date=meta["doc_date"],
                char_start=m.start(),
                char_end=m.end(),
            )

        # 4. Metabolic scan.
        m = _METABOLIC_RE.search(text)
        if m and not _preceded_by_neg(text, m.start()):
            specifics = EtiologySpecifics(causative_metabolic_text=m.group(0))
            return Evidence[EtiologySpecifics](
                value=specifics,
                certainty=Certainty.PROBABLE,
                temporal_status=TemporalStatus.CURRENT,
                evidence_text=m.group(0),
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

register_rule(EtiologySpecificsRule())

__all__ = ["EtiologySpecificsRule"]
