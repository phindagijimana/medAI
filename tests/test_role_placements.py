"""RAG (ask only), O export codes, in-E ConText ablation. Default extract path frozen."""

from __future__ import annotations

import json

import pytest

from services.chain_pipeline import ChainPipeline, ChainPipelineConfig
from services.context_engine import attach_entity_context, parse_context_engine
from services.guideline_rag import is_guideline_question, retrieve
from services.leo_ask import Asker, build_ask_prompt
from services.leo_catalog import ask_template
from services.leo_runtime import LeoRuntime
from services.medcat_extractor import LinkedEntity
from services.o_code_maps import map_export_codes

NOTE = (
    "Assessment: 34 year old with focal epilepsy. "
    "Takes levetiracetam 500 mg twice daily. "
    "Seizures occur about 2 per month. Denies lamotrigine use."
)


class FakeBackend:
    model_name = "fake-med42"

    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def generate_constrained(self, prompt, model, decoding):
        self.prompts.append(prompt)
        r = self.reply(prompt) if callable(self.reply) else self.reply
        return (r if isinstance(r, str) else json.dumps(r)), 10


class _Pheno:
    def __init__(self, d):
        self._d = d

    def model_dump(self, **kw):
        return self._d


class _Assembler:
    def __init__(self, d):
        self._d = d

    def process(self, text, **kw):
        return _Pheno(self._d)


class _NoCandidates:
    def get_candidates(self, **kw):
        return []


def _ev(value, quote):
    return {"value": value, "certainty": "definite", "temporal_status": "current",
            "evidence_text": quote, "char_start": None, "char_end": None}


def _specialist():
    return {
        "document": {"doc_id": "x"},
        "clinical_seizure": {
            "epilepsy_type": _ev("focal", "focal epilepsy"),
            "age_at_onset_years": _ev(10, "34 year old"),
        },
        "medication": {"current_asms": [_ev({"generic_name": "levetiracetam"}, "levetiracetam 500 mg")]},
    }


def _ent(note: str, span: str) -> LinkedEntity:
    i = note.index(span)
    return LinkedEntity(
        text=span, cui="X", sctid=None, label=span, enum_class=None, enum_value=None,
        char_start=i, char_end=i + len(span), confidence=1.0, linker_tier="custom",
    )


# ---- RAG: ask_/audit only --------------------------------------------------

def test_rag_skips_span_copy_questions():
    assert retrieve("What is the seizure type?", spec_id="seizure_type") == []
    assert not is_guideline_question("focal impaired awareness seizures", "seizure_type")
    hits = retrieve(ask_template("dre_kwan").question, spec_id="dre_kwan")
    assert hits and hits[0].id == "kwan_2010_dre"
    hits = retrieve(ask_template("ltm_sense").question, spec_id="ltm_sense")
    assert any(p.id == "acns_ltm_study" for p in hits)
    hits = retrieve(ask_template("first_feature").question, spec_id="first_feature")
    assert any(p.id == "fisher_2017_first_feature" for p in hits)


def test_ask_prompt_default_has_no_guideline_block():
    p = build_ask_prompt("the note", ask_template("aura"))
    assert "Guideline excerpts" not in p
    hits = retrieve(ask_template("dre_kwan").question, spec_id="dre_kwan")
    p2 = build_ask_prompt("the note", ask_template("dre_kwan"), passages=hits)
    assert "Guideline excerpts" in p2 and "quote MUST copy words from the Note" in p2
    assert "kwan_2010_dre" in p2


def test_asker_rag_off_does_not_stuff_prompt_and_quote_must_be_in_note():
    note = "Failed levetiracetam and lamotrigine at adequate tolerated doses; still has weekly seizures."
    spec = ask_template("dre_kwan")
    off = Asker(FakeBackend({"answer": "yes", "quote": "Failed levetiracetam and lamotrigine"}))
    r = off.ask(note, spec)
    assert off.guideline_rag is False
    assert "Guideline excerpts" not in off.backend.prompts[0]
    assert r.rag_ids == ()
    assert r.status == "needs_review"
    echo = Asker(FakeBackend({"answer": "yes", "quote": "failure of two tolerated"}), guideline_rag=True)
    bad = echo.ask(note, spec)
    assert bad.status == "rejected" and bad.reason == "offsets_unresolved"
    assert "kwan_2010_dre" in bad.rag_ids
    on = Asker(FakeBackend({"answer": "yes", "quote": "Failed levetiracetam and lamotrigine"}),
               guideline_rag=True)
    ok = on.ask(note, spec)
    assert "Guideline excerpts" in on.backend.prompts[0]
    assert ok.status == "needs_review" and ok.rag_ids


def test_runtime_defaults_leave_rag_and_export_off():
    rt = LeoRuntime(backend=None, use_llm=False)
    assert rt.ask_rag is False and rt.export_codes is False
    assert rt.context_engine == "medspacy"
    assert rt.versions()["ask_rag"] is False
    assert rt.pipeline.cfg.export_codes is False
    assert rt.pipeline.cfg.context_engine == "medspacy"


# ---- O export codes: after extract, never E --------------------------------

def test_icd_orphanet_score_epso_map_from_extracted_values_only():
    icd = map_export_codes("clinical_seizure.epilepsy_type", "focal")
    assert any(c["system"] == "ICD-10-CM" and c["id"] == "G40.1" for c in icd)
    assert any(c["system"] == "EpSO" and c["id"] == "FocalEpilepsy" for c in icd)
    assert map_export_codes("medication.drug_resistance_status", "resistant") == []
    orpha = map_export_codes("clinical_seizure.etiology_specifics", "Dravet syndrome", "SCN1A Dravet")
    assert any(c["system"] == "Orphanet" and c["id"] == "ORPHA:33069" for c in orpha)
    assert map_export_codes("clinical_seizure.predominant_seizure_type", "focal_impaired_awareness")
    score = map_export_codes("eeg.ied_findings", "spike")
    assert any(c["system"] == "SCORE" and c["id"] == "spike" for c in score)
    lpd = map_export_codes("eeg.ied_findings", "other", "EEG with LPDs over the left hemisphere")
    assert any(c["id"] == "LPD" for c in lpd)
    assert map_export_codes("eeg.ied_findings", "other", "No LPDs, GPDs, or BiPDs") == []
    assert map_export_codes("clinical_seizure.predominant_seizure_type", "focal_impaired_awareness")
    # seizure type is not an Orphanet job
    st = map_export_codes("clinical_seizure.predominant_seizure_type", "focal_impaired_awareness")
    assert not any(c["system"] == "Orphanet" for c in st)


def test_export_codes_flag_off_does_not_attach_and_does_not_change_verdict():
    pipe = ChainPipeline(
        assembler=_Assembler(_specialist()),
        extractor=object(), candidate_service=_NoCandidates(),
        llm_reasoner=lambda t, d, dd: {
            "document": {"doc_id": "x"},
            "clinical_seizure": {
                "epilepsy_type": {
                    "value": "focal", "certainty": "definite", "temporal_status": "current",
                    "evidence_text": "focal epilepsy", "char_start": None, "char_end": None,
                }
            },
        },
    )
    pipe.cfg.enable_preprocessing = False
    assert pipe.cfg.export_codes is False
    _, off = pipe.extract(NOTE, document_id="D1", return_claims=True)
    et = [c for c in off if c.field_path == "clinical_seizure.epilepsy_type"]
    assert et and et[0].export_codes == []
    verdict = et[0].validator_verdict
    pipe.cfg.export_codes = True
    _, on = pipe.extract(NOTE, document_id="D1", return_claims=True)
    et2 = [c for c in on if c.field_path == "clinical_seizure.epilepsy_type"]
    assert et2[0].export_codes and et2[0].validator_verdict == verdict
    assert any(x["system"] == "ICD-10-CM" for x in et2[0].export_codes)


# ---- ConText ablation inside E ---------------------------------------------

def test_context_engine_parse_and_negation_ablation():
    assert parse_context_engine("") == "medspacy"
    assert parse_context_engine("sentence") == "sentence"
    with pytest.raises(ValueError, match="ablation"):
        parse_context_engine("cot")
    note = "No LPDs. Mother has epilepsy. Plan VNS if seizures continue."
    lpd = _ent(note, "LPDs")
    attach_entity_context([lpd], note, nlp=None, engine="negex")
    assert lpd.is_negated is True
    fam = _ent(note, "epilepsy")
    attach_entity_context([fam], note, nlp=None, engine="sentence")
    assert fam.is_family is True
    vns = _ent(note, "VNS")
    attach_entity_context([vns], note, nlp=None, engine="sentence")
    assert vns.is_hypothetical is True


def test_chain_config_default_context_is_medspacy():
    assert ChainPipelineConfig().context_engine == "medspacy"
    assert ChainPipelineConfig().export_codes is False
    assert ChainPipelineConfig().ext_detectors == ()
