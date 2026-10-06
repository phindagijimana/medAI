"""Second reader (X1C) and the no-second-reader review policy.  No GPU."""

from __future__ import annotations

import json

import pytest

from schema.claim import ReasonCode, ValidatorVerdict
from services.chain_llm import CombinedReasoner, ExtendedLiveReasoner, FlatLiveReasoner, fuse, flatten, values_agree
from services.chain_pipeline import ChainPipeline
from services.ext_extract import (
    EXT_FIELD_PATHS, FOCAL_MOTOR_ONSETS, FOCAL_NONMOTOR_ONSETS, _EXAMPLES, build_ext_prompt,
    ext_answer_model, parse_ext,
)
from services.flat_extract import FLAT_FIELD_PATHS, parse_flat
from services.leo_runtime import LeoRuntime, env_flag
from test_leo_app import FakeBackend, FLAT_OK, NOTE
from test_leo_v04 import _NoCandidates, ev


def _spec_field(path, value, quote, note):
    mod, fld = path.split(".", 1)
    return {"document": {"doc_id": "x"}, mod: {fld: ev(value, quote, note) if not isinstance(value, list)
                                               else [ev(v, quote, note) for v in value]}}


class _Assembler:
    def __init__(self, pheno):
        self.pheno = pheno

    def process(self, *a, **k):
        return self.pheno


def _pipe(note, specialist, llm, **cfg):
    pipe = ChainPipeline(assembler=_Assembler(specialist), extractor=object(),
                         candidate_service=_NoCandidates(),
                         llm_reasoner=(lambda t, d, dd: llm) if llm is not None else None)
    pipe.cfg.enable_preprocessing = False
    for k, v in cfg.items():
        setattr(pipe.cfg, k, v)
    if llm is not None:
        class _R:
            last_covered_field_paths = cfg.pop("covered", FLAT_FIELD_PATHS | EXT_FIELD_PATHS)
        # covered already applied if passed as kw; set on a dummy reasoner
    return pipe.extract(note, document_id="D1", return_claims=True)


def test_parse_ext_keeps_quoted_vocab_and_drops_the_rest():
    raw = json.dumps({
        "eeg_study": {"value": "routine", "quote": "routine EEG"},
        "eeg_background": {"value": "normal", "quote": "normal background"},
        "interictal_discharges": {"present": True, "quote": "left frontal spikes"},
        "interictal_sites": [{"lobe": "frontal", "side": "left", "quote": "left frontal spikes"}],
        "ictal_onset": {"lobe": "temporal", "side": "right", "quote": "right temporal onset"},
        "focal_motor_onset": {"value": "clonic", "quote": "clonic jerking"},
        "focal_nonmotor_onset": {"value": "emotional", "quote": "a wave of fear"},
        "rescue_drugs": [{"name": "diazepam", "dose": "10 mg", "quote": "rectal diazepam 10 mg"}],
        "surgery": [{"type": "callosotomy", "quote": "corpus callosotomy"}],
    })
    p = parse_ext(raw)
    assert p.parse_ok and p.n_fields_kept >= 9
    eeg, cs, med = p.modules["eeg"], p.modules["clinical_seizure"], p.modules["medication"]
    assert eeg["study_type"]["value"] == "routine"
    assert eeg["ied_present"]["value"] is True
    assert eeg["ied_findings"][0]["value"]["localization"] == "frontal"
    assert cs["focal_motor_onset"]["value"] == "clonic"
    assert med["current_asms"][0]["reader"] == "X1C"
    assert med["surgery_history"][0]["value"]["surgery_type"] == "callosotomy"
    dropped = parse_ext(json.dumps({
        "eeg_study": {"value": "overnight", "quote": "overnight EEG"},
        "focal_motor_onset": {"value": "clonic", "quote": None},
        "rescue_drugs": [{"name": "diazepam", "quote": ""}],
        "surgery": [{"type": "resection", "quote": "resection"}],
    }))
    assert dropped.parse_ok
    assert "study_type" not in (dropped.modules.get("eeg") or {})
    assert "focal_motor_onset" not in (dropped.modules.get("clinical_seizure") or {})
    assert dropped.n_values_dropped >= 2


def test_parse_ext_examples_are_verbatim_and_in_vocab():
    for note, ans in _EXAMPLES:
        p = parse_ext(json.dumps(ans))
        assert p.parse_ok and p.n_fields_kept > 0
        blob = json.dumps(p.modules)
        for item in (ans["eeg_study"], ans["eeg_background"], ans["focal_motor_onset"], ans["focal_nonmotor_onset"]):
            if item.get("quote"):
                assert item["quote"] in note
        if ans["focal_motor_onset"].get("value"):
            assert ans["focal_motor_onset"]["value"] in FOCAL_MOTOR_ONSETS
        if ans["focal_nonmotor_onset"].get("value"):
            assert ans["focal_nonmotor_onset"]["value"] in FOCAL_NONMOTOR_ONSETS
        assert "current_asms" in blob or "surgery_history" in blob or "study_type" in blob


def test_ext_answer_model_validates():
    M = ext_answer_model()
    M.model_validate({
        "eeg_study": {"value": None, "quote": None},
        "eeg_background": {"value": None, "quote": None},
        "interictal_discharges": {"present": None, "quote": None},
        "interictal_sites": [],
        "ictal_onset": {"lobe": None, "side": None, "quote": None},
        "focal_motor_onset": {"value": None, "quote": None},
        "focal_nonmotor_onset": {"value": None, "quote": None},
        "rescue_drugs": [],
        "surgery": [],
    })
    with pytest.raises(Exception):
        M.model_validate({
            "eeg_study": {"value": "not_a_type", "quote": "x"},
            "eeg_background": {"value": None, "quote": None},
            "interictal_discharges": {"present": None, "quote": None},
            "interictal_sites": [],
            "ictal_onset": {"lobe": None, "side": None, "quote": None},
            "focal_motor_onset": {"value": None, "quote": None},
            "focal_nonmotor_onset": {"value": None, "quote": None},
            "rescue_drugs": [],
            "surgery": [],
        })


def test_field_path_constants_match_the_parsers():
    p = parse_ext(json.dumps({
        "eeg_study": {"value": "emu", "quote": "EMU"},
        "eeg_background": {"value": "focal_slowing", "quote": "focal slowing"},
        "interictal_discharges": {"present": False, "quote": "no discharges"},
        "interictal_sites": [],
        "ictal_onset": {"lobe": "frontal", "side": "left", "quote": "left frontal onset"},
        "focal_motor_onset": {"value": "tonic", "quote": "tonic stiffening"},
        "focal_nonmotor_onset": {"value": "sensory", "quote": "tingling"},
        "rescue_drugs": [{"name": "midazolam", "quote": "buccal midazolam"}],
        "surgery": [{"type": "resection", "quote": "temporal resection"}],
    }))
    got = {f"{m}.{f}" for m, mod in p.modules.items() for f in mod}
    assert got - {"medication.current_asms"} <= EXT_FIELD_PATHS
    fp = parse_flat(json.dumps(FLAT_OK))
    assert {f"{m}.{f}" for m, mod in fp.modules.items() for f in mod} <= FLAT_FIELD_PATHS


def test_fuse_agrees_on_extended_fields():
    note = "Routine EEG. Seizures begin with clonic jerking."
    spec = flatten({"eeg": {"study_type": ev("routine", "Routine EEG", note)},
                    "clinical_seizure": {"focal_motor_onset": ev("clonic", "clonic jerking", note)}})
    llm = flatten({"eeg": {"study_type": ev("routine", "Routine EEG")},
                   "clinical_seizure": {"focal_motor_onset": ev("clonic", "clonic jerking")}})
    f = fuse(spec, llm)
    assert all(x.status == "agree" for x in f.specialist)
    spec2 = flatten({"eeg": {"study_type": ev("routine", "Routine EEG", note)}})
    llm2 = flatten({"eeg": {"study_type": ev("video_eeg", "video-EEG")}})
    assert fuse(spec2, llm2).specialist[0].status == "disagree"


def test_uncovered_field_goes_to_review_when_the_model_ran():
    note = "MRI showed hippocampal sclerosis. Focal epilepsy."
    spec = {"document": {"doc_id": "x"},
            "mri": {"hippocampal_sclerosis": ev(True, "hippocampal sclerosis", note)},
            "clinical_seizure": {"epilepsy_type": ev("focal", "Focal epilepsy", note)}}
    llm = {"clinical_seizure": {"epilepsy_type": ev("focal", "Focal epilepsy")}}

    class _R:
        last_covered_field_paths = FLAT_FIELD_PATHS | EXT_FIELD_PATHS

    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_NoCandidates(), llm_reasoner=_R())
    pipe.cfg.enable_preprocessing = False
    pipe._reason_llm = lambda *a, **k: llm
    stats, claims = pipe.extract(note, document_id="D1", return_claims=True)
    by = {c.field_path: c for c in claims}
    assert by["clinical_seizure.epilepsy_type"].validator_verdict == ValidatorVerdict.ACCEPT
    assert by["mri.hippocampal_sclerosis"].validator_verdict == ValidatorVerdict.REVIEW
    assert ReasonCode.NO_SECOND_READER in by["mri.hippocampal_sclerosis"].reason_codes
    assert stats.n_no_second_reader >= 1


def test_uncovered_field_is_accepted_when_the_switch_is_off():
    note = "MRI showed hippocampal sclerosis."
    spec = {"document": {"doc_id": "x"},
            "mri": {"hippocampal_sclerosis": ev(True, "hippocampal sclerosis", note)}}
    llm = {"clinical_seizure": {"epilepsy_type": ev("focal", "focal")}}

    class _R:
        last_covered_field_paths = FLAT_FIELD_PATHS

    pipe = ChainPipeline(assembler=_Assembler(spec), extractor=object(),
                         candidate_service=_NoCandidates(), llm_reasoner=_R())
    pipe.cfg.enable_preprocessing = False
    pipe.cfg.require_second_reader_for_uncovered_fields = False
    pipe._reason_llm = lambda *a, **k: llm
    _, claims = pipe.extract(note, document_id="D1", return_claims=True)
    hs = [c for c in claims if c.field_path == "mri.hippocampal_sclerosis"][0]
    assert hs.validator_verdict == ValidatorVerdict.ACCEPT
    assert ReasonCode.NO_SECOND_READER not in hs.reason_codes


def test_rescue_drug_read_by_both_is_accepted():
    from services.chain_pipeline import RESCUE_FIELD_PATH
    from test_leo_rescue import NOTE as RNOTE, _llm, _spec
    pipe = ChainPipeline(assembler=_Assembler(_spec()), extractor=object(),
                         candidate_service=_NoCandidates(),
                         llm_reasoner=lambda t, d, dd: _llm())
    pipe.cfg.enable_preprocessing = False

    class _R:
        last_covered_field_paths = FLAT_FIELD_PATHS | EXT_FIELD_PATHS
    pipe._llm_reasoner = _R()
    pipe._reason_llm = lambda *a, **k: _llm()
    stats, claims = pipe.extract(RNOTE, document_id="D1", return_claims=True)
    resc = [c for c in claims if c.field_path == RESCUE_FIELD_PATH]
    assert resc and resc[0].validator_verdict == ValidatorVerdict.ACCEPT


def test_combined_reasoner_merges_and_survives_one_failure():
    class Boom:
        last_ok = False
        last_covered_field_paths = frozenset()
        info = type("I", (), {"model": "x", "prompt": "boom"})()

        def __call__(self, *a, **k):
            raise RuntimeError("boom")

    class Ok:
        last_ok = True
        last_covered_field_paths = FLAT_FIELD_PATHS
        info = type("I", (), {"model": "x", "prompt": "ok"})()

        def __call__(self, *a, **k):
            self.last_ok = True
            return {"clinical_seizure": {"epilepsy_type": ev("focal", "focal")}}

    c = CombinedReasoner(Ok(), Boom())
    out = c("note", "d", "2024-01-01")
    assert out["clinical_seizure"]["epilepsy_type"]["value"] == "focal"
    assert "clinical_seizure.epilepsy_type" in c.last_covered_field_paths


def test_runtime_switch(monkeypatch):
    monkeypatch.setenv("MEDAI_LEO_EXT_READER", "0")
    rt = LeoRuntime(backend=FakeBackend(FLAT_OK), ext_reader=None)
    assert rt.ext_reader is False
    monkeypatch.setenv("MEDAI_LEO_EXT_READER", "1")
    rt = LeoRuntime(backend=FakeBackend(FLAT_OK), ext_reader=None)
    assert rt.ext_reader is True
    rt = LeoRuntime(backend=FakeBackend(FLAT_OK), ext_reader=False)
    assert rt.ext_reader is False
    assert env_flag("MEDAI_LEO_EXT_READER") is True


def test_ied_sites_agree_without_matching_type():
    a = {"ied_type": "spike", "localization": "temporal", "laterality": "left"}
    b = {"ied_type": None, "localization": "temporal", "laterality": "left"}
    assert values_agree(a, b)
    assert not values_agree(a, {"ied_type": None, "localization": "frontal", "laterality": "left"})


def test_prompt_contains_onset_and_plan_rules():
    p = build_ext_prompt("short note")
    assert "FIRST prominent" in p
    assert "Do not report advice" in p
    assert "AS NEEDED" in p
