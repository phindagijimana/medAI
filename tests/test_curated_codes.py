"""Curated ontology codes vs the pinned releases (services.curated_code_audit).

Fixes live in data/curated/curated_code_corrections.csv; hand-checked false
positives in data/curated/curated_code_reviewed.csv.  These tests fail when a new
bad code appears, a correction is reverted, or the candidate service still
emits a corrected-away code.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from services.curated_code_audit import KNOWN_ISSUES, audit
from services.ontology_releases import available

CORRECTIONS = Path(__file__).resolve().parent.parent / "data" / "curated" / "curated_code_corrections.csv"


@pytest.fixture(scope="module")
def issues():
    return audit()


def test_no_new_curated_code_issues(issues):
    known = {tuple(x) for x in json.loads(KNOWN_ISSUES.read_text(encoding="utf-8"))}
    new = sorted({(i.group, i.key, i.kind, i.code) for i in issues} - known)
    assert not new, ("new curated-code issues (run scripts/audit_curated_codes.py):\n"
                     + "\n".join(map(str, new)))


def test_curated_medications_match_rxnorm(issues):
    assert not [i for i in issues if i.group == "Medication"]


def test_asm_lexicon_shared_by_detection_and_coding():
    from rules.asm_lexicon import ASM_LEXICON
    from rules.epilepsy_ontology import MEDICATION_ONTOLOGY

    assert ASM_LEXICON["cenobamate"]["role"] == "asm"
    assert ASM_LEXICON["diazepam"]["role"] == "rescue"
    assert "valproic_acid" not in ASM_LEXICON          # folded into sodium_valproate
    assert set(ASM_LEXICON) <= set(MEDICATION_ONTOLOGY)
    assert "Xcopri" in MEDICATION_ONTOLOGY["cenobamate"].synonyms


def test_no_unreviewed_issues_remain(issues):
    assert not issues, "\n".join(f"{i.group}.{i.key} {i.kind} {i.code} {i.detail}" for i in issues)


def test_corrections_are_applied():
    from rules.epilepsy_ontology import all_enum_ontologies, supplementary_ontologies

    maps = {**all_enum_ontologies(), **supplementary_ontologies()}
    rows = list(csv.DictReader(CORRECTIONS.open(encoding="utf-8")))
    assert rows
    for r in rows:
        entry = maps[r["group"]][r["key"]]
        current = getattr(entry, r["field"])
        assert current != (r["old"] or None), f"{r['group']}.{r['key']} still has {r['field']} {r['old']}"
        if r["field"] == "sctid":
            assert current == (r["new"] or None)
        elif r["new"] == "none":
            assert current is None


@pytest.mark.skipif("snomed" not in available(), reason="SNOMED CT release not fetched")
def test_corrected_sctids_are_emitted_not_the_old_ones():
    from rules.epilepsy_ontology import all_enum_ontologies
    from services.ontology_candidates import OntologyCandidateService

    enum_maps = all_enum_ontologies()
    svc = OntologyCandidateService()
    checked = 0
    for r in csv.DictReader(CORRECTIONS.open(encoding="utf-8")):
        if r["field"] != "sctid" or r["group"] not in enum_maps:
            continue
        entry = enum_maps[r["group"]][r["key"]]
        ids = {c.id for c in svc.get_candidates(entry.label, k=20) if c.schema_enum_value == r["key"]}
        assert r["old"] not in ids, f"{r['group']}.{r['key']} still emits {r['old']}"
        if r["new"]:
            assert r["new"] in ids, f"{r['group']}.{r['key']} does not emit {r['new']}"
        checked += 1
    assert checked
