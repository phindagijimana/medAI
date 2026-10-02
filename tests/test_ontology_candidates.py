"""Candidate retrieval over pinned ontology releases (LEO chain, O component).

Release-backed tests skip when data/ontologies/ has not been fetched
(scripts/fetch_ontologies.py); RxNorm and SNOMED CT are UMLS-licensed and
are not available in every checkout.
"""

from __future__ import annotations

import pytest

from services.ontology_candidates import OntologyCandidateService
from services.ontology_releases import available


@pytest.fixture(scope="module")
def svc() -> OntologyCandidateService:
    return OntologyCandidateService()


def _top(svc, mention, field_type):
    cands = svc.get_candidates(mention, field_type=field_type, k=5)
    assert cands, f"no candidates for {mention!r}"
    return cands[0]


needs = lambda *srcs: pytest.mark.skipif(  # noqa: E731
    not set(srcs) <= set(available()), reason=f"ontology releases {srcs} not fetched")


@needs("hpo")
def test_legacy_seizure_term_maps_to_hpo(svc):
    top = _top(svc, "complex partial seizures", "clinical_seizure.predominant_seizure_type")
    assert (top.system, top.id) == ("HPO", "HP:0002384")
    assert top.release.startswith("hpo:")
    assert top.rank_score >= 0.9


@needs("mondo")
def test_epilepsy_syndrome_maps_to_mondo(svc):
    top = _top(svc, "juvenile myoclonic epilepsy", "clinical_seizure.epilepsy_type")
    assert (top.system, top.id) == ("MONDO", "MONDO:0009696")


@needs("rxnorm")
@pytest.mark.parametrize("mention,rxcui", [
    ("Keppra", "114477"),        # brand → levetiracetam
    ("levetiracetam", "114477"),
    ("Depakote", "40254"),       # brand → valproate
    ("valproic acid", "40254"),  # salt form folds into valproate
    ("cenobamate", "2265690"),   # ATC N03A, not in the hand-curated list
    ("Xcopri", "2265690"),
    ("Epidiolex", "2045371"),    # cannabidiol
    ("Valtoco", "3322"),         # rescue diazepam
])
def test_drug_names_map_to_rxnorm_ingredient(svc, mention, rxcui):
    top = _top(svc, mention, "medication.current_asms")
    assert (top.system, top.id) == ("RxNorm", rxcui)


@needs("snomed")
def test_snomed_terms_use_us_preferred_term(svc):
    top = _top(svc, "focal epilepsy", "clinical_seizure.epilepsy_type")
    snomed = [c for c in svc.get_candidates("focal epilepsy", "clinical_seizure.epilepsy_type", k=5)
              if c.system == "SNOMED"]
    assert snomed and snomed[0].label == "Focal epilepsy" and snomed[0].release.startswith("snomed:")
    assert top.rank_score == 1.0


@needs("snomed")
def test_snomed_subset_has_only_disorders_and_findings():
    from services.ontology_loaders import load_terms
    labels = [t.label for t in load_terms() if t.system == "SNOMED"]
    assert labels and not any(l.endswith(")") for l in labels)


def test_ilae_map_ids_are_codes_not_atom_strings(svc):
    for mention in ("tonic-clonic seizure", "absence seizure", "atonic seizure"):
        for c in svc.get_candidates(mention, k=20):
            assert "[" not in c.id and "/" not in c.id, c.id


def test_curated_candidates_carry_their_schema_field(svc):
    field = "clinical_seizure.predominant_seizure_type"
    enum_cands = [c for c in svc.get_candidates("focal aware seizure", field, k=20) if c.schema_enum_value]
    assert enum_cands and enum_cands[0].schema_field == field


@needs("hpo")
def test_field_routing_keeps_scopes_apart(svc):
    cands = svc.get_candidates("hippocampal sclerosis", field_type="medication.current_asms", k=10)
    assert all(c.system != "HPO" for c in cands)


def test_short_synonyms_do_not_substring_match(svc):
    # Laterality entries carry one-letter synonyms ("L", "R").
    cands = svc.get_candidates("generalized spike and wave", field_type="eeg.ied_findings", k=10)
    assert not any(c.label in ("Left", "Right") for c in cands)


def test_curated_only_mode_has_no_release_terms():
    svc = OntologyCandidateService(use_releases=False)
    assert not svc.releases_loaded
    cands = svc.get_candidates("complex partial seizures", field_type="clinical_seizure.predominant_seizure_type")
    assert all(c.system not in ("HPO", "MONDO", "EPIO", "RxNorm") for c in cands)
