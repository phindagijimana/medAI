"""Arm E: ontology selector cannot invent a code.  No GPU."""

from __future__ import annotations

import json

from schema.claim import ValidatorVerdict
from services.chain_pipeline import ChainPipeline
from services.onto_select import OntologySelector, parse_select, snapshot
from test_leo_v04 import _NoCandidates, ev


def test_parse_select_picks_only_from_the_list():
    items = [{"id": "a", "mention": "focal epilepsy", "field_path": "clinical_seizure.epilepsy_type",
              "candidates": snapshot([_C("HPO", "HP:0001250", "Seizure", 0.5),
                                      _C("SNOMED", "230381007", "Focal epilepsy", 0.7)])}]
    got = parse_select(json.dumps({"picks": [{"id": "a", "choice": 2, "quote": "focal epilepsy"}]}), items)
    assert got["a"].picked["id"] == "230381007"
    bad = parse_select(json.dumps({"picks": [{"id": "a", "choice": 9, "quote": "x"}]}), items)
    assert bad["a"].picked is None and bad["a"].note == "out_of_range"
    invent = parse_select(json.dumps({"picks": [{"id": "a", "choice": 1, "quote": "HP:9999999"}]}), items)
    # quote is ignored for the id; the id still comes from the list
    assert invent["a"].picked["id"] == "HP:0001250"
    missing = parse_select("{}", items)
    assert missing["a"].picked is None


class _C:
    def __init__(self, system, id, label, score):
        self.system, self.id, self.label, self.rank_score = system, id, label, score
        self.is_obsolete = False
        self.release = "hpo:test"
        self.definition = ""


class _Cands:
    def __init__(self, cands, exact=False):
        self.cands, self.exact = cands, exact

    def get_candidates(self, **kw):
        return self.cands


class _Assembler:
    def __init__(self, pheno):
        self.pheno = pheno

    def process(self, *a, **k):
        return self.pheno


class _Sel:
    def __init__(self, choice):
        self.choice = choice

    def __call__(self, note, items):
        from services.onto_select import parse_select
        picks = [{"id": it["id"], "choice": self.choice, "quote": it["mention"]} for it in items]
        return parse_select(json.dumps({"picks": picks}), items)


def test_exact_hit_skips_the_selector():
    note = "Focal epilepsy since childhood."
    spec = {"document": {"doc_id": "x"}, "clinical_seizure": {"epilepsy_type": ev("focal", "Focal epilepsy", note)}}
    cands = [_C("SNOMED", "230381007", "Focal epilepsy", 1.0)]
    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_Cands(cands), llm_reasoner=None,
                         ontology_selector=_Sel(2))
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.ontology_select = True
    stats, claims = pipe.extract(note, document_id="D1", return_claims=True)
    c = next(c for c in claims if c.field_path == "clinical_seizure.epilepsy_type")
    assert c.ontology_match == "exact" and c.concept.id == "230381007"
    assert stats.n_ontology_selected == 0


def test_selector_adopts_a_listed_code_and_rejects_an_invented_index():
    note = "Focal epilepsy since childhood."
    spec = {"document": {"doc_id": "x"}, "clinical_seizure": {"epilepsy_type": ev("focal", "Focal epilepsy", note)}}
    cands = [_C("HPO", "HP:0001250", "Seizure", 0.5), _C("SNOMED", "230381007", "Focal epilepsy", 0.7)]
    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_Cands(cands), llm_reasoner=None,
                         ontology_selector=_Sel(2))
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.ontology_select = True
    _, claims = pipe.extract(note, document_id="D1", return_claims=True)
    c = next(c for c in claims if c.field_path == "clinical_seizure.epilepsy_type")
    assert c.ontology_match == "selected" and c.concept.id == "230381007"
    pipe2 = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                          candidate_service=_Cands(cands), llm_reasoner=None,
                          ontology_selector=_Sel(9))
    pipe2.cfg.enable_preprocessing = False
    pipe2.cfg.ontology_select = True
    _, claims2 = pipe2.extract(note, document_id="D1", return_claims=True)
    c2 = next(x for x in claims2 if x.field_path == "clinical_seizure.epilepsy_type")
    assert c2.ontology_match == "abstain" and c2.concept.system == "MEDAI-ENUM"


def test_code_accepted_only_when_value_accepted_and_code_is_real():
    from services.ext_extract import EXT_FIELD_PATHS
    from services.flat_extract import FLAT_FIELD_PATHS
    note = "Focal epilepsy."
    spec = {"document": {"doc_id": "x"}, "clinical_seizure": {"epilepsy_type": ev("focal", "Focal epilepsy", note)}}
    llm = {"clinical_seizure": {"epilepsy_type": ev("focal", "Focal epilepsy")}}
    cands = [_C("SNOMED", "230381007", "Focal epilepsy", 1.0)]

    class _R:
        last_covered_field_paths = FLAT_FIELD_PATHS | EXT_FIELD_PATHS

        def __call__(self, *a, **k):
            return llm

    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_Cands(cands), llm_reasoner=_R())
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.ontology_select = True
    _, claims = pipe.extract(note, document_id="D1", return_claims=True)
    c = next(x for x in claims if x.field_path == "clinical_seizure.epilepsy_type")
    assert c.validator_verdict == ValidatorVerdict.ACCEPT
    assert c.code_accepted is True
    # MRI-like uncovered field: even an exact code is only a suggestion
    spec2_note = "MRI showed hippocampal sclerosis."
    spec2 = {"document": {"doc_id": "x"}, "mri": {"hippocampal_sclerosis": ev(True, "hippocampal sclerosis", spec2_note)}}
    pipe2 = ChainPipeline(assembler=_Assembler(spec2), extractor=object(),
                          candidate_service=_Cands(cands), llm_reasoner=_R())
    pipe2.cfg.enable_preprocessing = False
    _, claims2 = pipe2.extract(spec2_note, document_id="D1", return_claims=True)
    hs = next(x for x in claims2 if "hippocampal" in x.field_path)
    assert hs.validator_verdict == ValidatorVerdict.REVIEW
    assert hs.code_accepted is False


def test_runtime_ontology_select_defaults_off(monkeypatch):
    monkeypatch.delenv("MEDAI_LEO_ONTOLOGY_SELECT", raising=False)
    from services.leo_runtime import LeoRuntime
    from test_leo_app import FakeBackend, FLAT_OK
    rt = LeoRuntime(backend=FakeBackend(FLAT_OK))
    assert rt.ontology_select is False
    rt = LeoRuntime(backend=FakeBackend(FLAT_OK), ontology_select=True)
    assert rt.ontology_select is True
