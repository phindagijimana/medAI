"""Check the hand-curated codes in rules.epilepsy_ontology against the pinned releases.

Issue kinds
-----------
    sctid_missing           SCTID does not exist in the pinned SNOMED CT release
    sctid_inactive          SCTID exists but is retired (``detail`` names the replacement)
    sctid_shared            two different concepts in one group carry the same SCTID
    sctid_name_mismatch     the SNOMED name shares no word with the curated label/synonyms
    rxnorm_mismatch         "RxNorm <n>" provenance differs from the lexicon's ingredient RXCUI
    cui_name_mismatch       the UMLS names of the curated CUI (cached UTS responses in
                            .cache/umls_api/) share no word with the curated label/synonyms
    umls_synonyms_unrelated every synonym the UMLS enrichment added is unrelated to the entry,
                            i.e. the entry's UMLS CUI points at the wrong concept

Issues listed in data/curated/curated_code_reviewed.csv were checked by hand and
are correct despite the word-overlap test (e.g. bilateral = "Right and left");
they are not reported.  Fixes are recorded in data/curated/curated_code_corrections.csv
and applied by scripts/apply_curated_code_corrections.py.

    venv/bin/python scripts/audit_curated_codes.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

KNOWN_ISSUES = Path(__file__).resolve().parent.parent / "data" / "curated" / "curated_code_known_issues.json"
REVIEWED = Path(__file__).resolve().parent.parent / "data" / "curated" / "curated_code_reviewed.csv"

_STOP = {"of", "and", "or", "the", "with", "without", "in", "to", "for", "by", "on",
         "a", "an", "nos", "disorder", "finding", "structure", "procedure", "substance",
         "product", "containing", "only", "type"}
_WORD = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Issue:
    group: str
    key: str
    kind: str
    code: str
    detail: str = ""


def _stems(*texts: str) -> set[str]:
    out = set()
    for t in texts:
        for w in _WORD.findall((t or "").lower()):
            if w not in _STOP and len(w) > 2:
                out.add(w[:5])
    return out


def _curated_maps() -> dict[str, dict]:
    from rules.epilepsy_ontology import all_enum_ontologies, supplementary_ontologies
    return {**all_enum_ontologies(), **supplementary_ontologies()}


def _umls_added() -> dict[tuple[str, str], list[str]]:
    try:
        from rules.epilepsy_ontology_umls_overrides import UMLS_OVERRIDES
    except ImportError:
        return {}
    return {(g, k): p.get("add_synonyms", []) for g, vals in UMLS_OVERRIDES.items() for k, p in vals.items()}


_UMLS_CACHE = Path(__file__).resolve().parent.parent / ".cache" / "umls_api"


def _umls_cui_names(cui: str) -> list[str] | None:
    """English atom names for ``cui`` from the UTS responses cached by
    scripts/enrich_ontology_from_umls.py; None when the CUI was never fetched."""
    p = _UMLS_CACHE / f"{cui}.json"
    if not p.exists():
        return None
    try:
        atoms = json.loads(p.read_text(encoding="utf-8")).get("result") or []
    except (OSError, ValueError):
        return None
    return [a["name"] for a in atoms if a.get("language") == "ENG" and a.get("name")] or None


def curated_sctids() -> set[str]:
    """Every SCTID in the curated maps and references/exect_v2_ilae_map.csv;
    shared with the candidate service so both hit the same snomed_lookup cache."""
    ids = {str(e.sctid) for onto in _curated_maps().values() for e in onto.values() if e.sctid}
    ilae = Path(__file__).resolve().parent.parent / "references" / "exect_v2_ilae_map.csv"
    if ilae.exists():
        ids |= set(re.findall(r"/SNOMEDCT_US/\w+/(\d+)\]", ilae.read_text(encoding="utf-8")))
    return ids


def audit() -> list[Issue]:
    from services.ontology_loaders import snomed_lookup

    maps = _curated_maps()
    added = _umls_added()
    lookup = snomed_lookup(curated_sctids())
    issues: list[Issue] = []

    for group, onto in maps.items():
        by_sctid: dict[str, list[str]] = defaultdict(list)
        for key, e in onto.items():
            umls_syns = set(added.get((group, key), []))
            own = [e.label, key.replace("_", " "), *(s for s in e.synonyms if s not in umls_syns)]

            if e.sctid and lookup:
                sct = str(e.sctid)
                by_sctid[sct].append(key)
                info = lookup.get(sct)
                if not info or not info["exists"]:
                    issues.append(Issue(group, key, "sctid_missing", sct))
                elif not info["active"]:
                    issues.append(Issue(group, key, "sctid_inactive", sct,
                                        f"replaced by {info['replaced_by']}" if info["replaced_by"] else ""))
                elif "generated:asm_lexicon" not in e.source_provenance \
                        and not (_stems(*own) & _stems(info["pt"] or "", info["fsn"] or "")):
                    issues.append(Issue(group, key, "sctid_name_mismatch", sct,
                                        f"SNOMED says {info['fsn']!r}"))

            cui_names = _umls_cui_names(e.cui) if e.cui else None
            if cui_names and not (_stems(*own) & _stems(*cui_names)):
                issues.append(Issue(group, key, "cui_name_mismatch", e.cui,
                                    f"UMLS says {cui_names[0]!r}"))

            if umls_syns and not (_stems(*own) & _stems(*umls_syns)):
                sample = ", ".join(sorted(umls_syns)[:2])
                issues.append(Issue(group, key, "umls_synonyms_unrelated", e.cui or "",
                                    f"{len(umls_syns)} added, e.g. {sample}"))

        for sct, keys in by_sctid.items():
            if len(keys) > 1:
                for key in keys:
                    issues.append(Issue(group, key, "sctid_shared", sct, f"shared with {sorted(set(keys) - {key})}"))

    try:
        from rules.asm_lexicon import ASM_LEXICON
    except ImportError:
        ASM_LEXICON = {}
    for key, e in maps.get("Medication", {}).items():
        lex = ASM_LEXICON.get(key)
        if not lex:
            continue
        valid = {lex["rxcui"], *lex["alt_rxcuis"]}
        for p in e.source_provenance:
            m = re.fullmatch(r"RxNorm (\d+)", p)
            if m and m.group(1) not in valid:
                issues.append(Issue("Medication", key, "rxnorm_mismatch", m.group(1),
                                    f"ingredient is {lex['rxcui']} ({lex['label']})"))
    ok = reviewed()
    return [i for i in issues if (i.group, i.key, i.kind, i.code) not in ok]


def reviewed() -> set[tuple[str, str, str, str]]:
    """Issues a person checked and accepted (with a reason) in data/curated/curated_code_reviewed.csv."""
    if not REVIEWED.exists():
        return set()
    import csv
    with REVIEWED.open(encoding="utf-8") as f:
        return {(r["group"], r["key"], r["kind"], r["code"]) for r in csv.DictReader(f)}


__all__ = ["KNOWN_ISSUES", "REVIEWED", "Issue", "audit", "curated_sctids", "reviewed"]
