#!/usr/bin/env python3
"""Checks that need the real model (GPU), run as Slurm jobs.  Synthetic data only.

    smoke         load Med42-8B in LEO's own runtime, run one note and one question
    parity_fs     the live model on the 40 held-out F-S letters vs. the evaluation manifests
    parity_synth  the live model on the 143 synthetic US-style notes vs. the evaluation manifests
    long          long documents (a patient's notes joined, 10-40k characters): chunked vs unchunked
    ask           free-text questions with a known answer, plus questions the notes cannot answer

Why each exists (the open items of ``docs/LEO_USER_GUIDE.md``):

* parity: the evaluation manifests were made once, in another environment (torch 2.7, python 3.9).
  The app runs in ``venv-medcat`` (torch 2.14).  Greedy, schema-constrained decoding should give the
  same text; this measures whether it does, and re-scores the live output with the same scorers.
* long: chunking was unit tested only.  Each synthetic patient's notes joined into one document give a
  long input whose patient-level reference is known.
* ask: question answering had no accuracy figure.  Questions are built from the reference record.

Run (inside a GPU job; ``bin/leo`` submits them)::

    venv-medcat/bin/python scripts/leo_gpu_validate.py smoke parity_fs parity_synth
    venv-medcat/bin/python scripts/leo_gpu_validate.py long ask --patients 30
    venv-medcat/bin/python scripts/leo_gpu_validate.py long ask --selftest --patients 2      # CPU, fake model

Results: ``eval/results/leo_gpu_<stage>.json`` (rewritten after each patient or note, so a cut-off job
keeps what it finished).
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
RESULTS = REPO / "eval" / "results"
PY = sys.executable
DATE = "2024-01-01"

SMOKE_NOTE = ("Progress note. 34 year old with focal epilepsy since age 11. Has about two seizures per month. "
              "Takes lamotrigine 200 mg twice daily and lacosamide 100 mg twice daily. Valproate was stopped for tremor.")


# ---- shared ---------------------------------------------------------------------------------

def save(stage: str, obj: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    obj["stage"], obj["written_utc"] = stage, datetime.now(timezone.utc).isoformat(timespec="seconds")
    (RESULTS / f"leo_gpu_{stage}.json").write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def environment() -> dict:
    import platform
    env = {"python": platform.python_version(), "host": platform.node()}
    try:
        import torch, transformers
        env.update(torch=torch.__version__, cuda=torch.version.cuda, cuda_available=torch.cuda.is_available(),
                   transformers=transformers.__version__,
                   gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
    except Exception as e:                                           # pragma: no cover
        env["torch_error"] = str(e)
    return env


class FakeBackend:
    """For --selftest on a CPU node: canned answers, so the harness itself can be debugged without a GPU."""
    model_name = "fake-med42"
    model_cache_dir = ""

    def generate_constrained(self, prompt, model, decoding):
        if "Question:" in prompt:
            return json.dumps({"answer": "not_documented", "quote": None}), 5
        return json.dumps({"epilepsy_type": {"value": "focal", "quote": "focal epilepsy"}}), 5

    generate = generate_constrained


def make_runtime(args, chunk: int = 8000):
    from services.leo_runtime import LeoRuntime
    if args.selftest:
        rt = LeoRuntime(backend=FakeBackend(), chunk_max_chars=chunk)
    else:
        rt = LeoRuntime.load(mode="gpu", chunk_max_chars=chunk)
    return rt


def share_specialist(dst, src) -> None:
    """Load MedCAT and the ontology once and share them between runtimes."""
    src.pipeline._lazy_init()
    p = dst.pipeline
    p._extractor, p._assembler = src.pipeline._extractor, src.pipeline._assembler
    p._candidate_service, p._lazy_init_done = src.pipeline._candidate_service, True


def j(o: Any) -> str:
    return json.dumps(o, sort_keys=True, default=lambda x: x.model_dump() if hasattr(x, "model_dump") else repr(x))


# ---- smoke ----------------------------------------------------------------------------------

def stage_smoke(args) -> dict:
    from services.leo_catalog import ask_template, resolve_phenotypes
    t0 = time.time()
    rt = make_runtime(args)
    load_s = round(time.time() - t0, 1)
    res = rt.extract_note(SMOKE_NOTE, doc_id="smoke", phenotypes=resolve_phenotypes(None), asks=[ask_template("aura")])
    out = {"environment": environment(), "load_seconds": load_s, "llm_used": res.llm_used, "error": res.error,
           "seconds": res.seconds, "row": {k: v for k, v in res.row.items() if not k.endswith(("_evidence", "_source"))},
           "n_claims": res.n_claims, "n_accepted": res.n_accepted, "n_review": res.n_review, "asks": res.asks}
    out["ok"] = bool(res.llm_used and not res.error and res.row.get("epilepsy_type") and res.asks)
    print(json.dumps(out, indent=2, default=str))
    return out


# ---- parity ---------------------------------------------------------------------------------

def _old_raw(manifest_dir: Path, arm: str) -> dict[str, str]:
    out = {}
    for p in manifest_dir.rglob("*.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("arm") == arm and m.get("prompt_id", "").startswith("flat_phenotype."):
            out[m["source_doc_id"]] = m["raw_response"]
    return out


def _parity(args, stage: str, docs: list[tuple[str, str]], old_dir: Path, live_dir: Path, rescore: list[str]) -> dict:
    """``docs`` = [(source_doc_id, text)].  Generate with the live backend exactly as the evaluation script does."""
    from services.chain_llm import FlatLiveReasoner
    from services.extract import DecodingConfig
    from services.flat_extract import FLAT_PROMPT_VERSION, build_flat_prompt, flat_answer_model, parse_flat
    from services.run_manifest import RunManifest, _git_dirty, _git_sha_short, _hardware_info

    if args.selftest:
        live_dir = Path("/tmp/leo_gpu_selftest/manifests") / live_dir.name
    os.environ["MEDAI_MANIFEST_DIR"] = str(live_dir)
    import services.run_manifest as rm
    rm.MANIFEST_ROOT = live_dir
    rt = make_runtime(args)
    backend = rt.backend
    old = _old_raw(old_dir, "L1C")
    decoding = DecodingConfig(do_sample=False, temperature=None, top_p=None, max_new_tokens=768, seed=0, constrained=False)
    live_reasoner = FlatLiveReasoner(backend, arm="L1C")
    rows, n_same_raw, n_same_parsed, n_path_same, n_path = [], 0, 0, 0, 0
    t_start = time.time()
    for i, (doc, text) in enumerate(docs, 1):
        started = datetime.now(timezone.utc)
        t0 = time.time()
        raw, n_tok = backend.generate_constrained(build_flat_prompt(text, "L1C"), flat_answer_model(), decoding)
        dur = time.time() - t0
        fp = parse_flat(raw, FLAT_PROMPT_VERSION)
        RunManifest(
            run_id=f"flat-L1C-{doc}-{started.strftime('%H%M%S')}", started_at=started.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(), duration_s=round(dur, 2), code_sha=_git_sha_short(),
            code_dirty=_git_dirty(), hardware=_hardware_info(), schema_version="v0.2.1",
            prompt_id=f"flat_phenotype.L1C.{FLAT_PROMPT_VERSION}", prompt_version=FLAT_PROMPT_VERSION,
            model_name=backend.model_name, model_cache_dir=getattr(backend, "model_cache_dir", ""),
            decoding=dataclasses.asdict(decoding), source_doc_id=doc, source_doc_type="progress_note",
            source_length_chars=len(text), raw_response=raw, raw_response_tokens=n_tok, raw_valid=fp.parse_ok,
            final_valid=fp.n_fields_kept > 0, repair_method="flat_parse",
            parsed_value={"fields_kept": fp.n_fields_kept, "values_dropped": fp.n_values_dropped}, arm="L1C").write()
        ref = old.get(doc)
        same_raw = ref is not None and raw == ref
        same_parsed = ref is not None and j(fp.modules) == j(parse_flat(ref).modules)
        n_same_raw += same_raw
        n_same_parsed += same_parsed
        row = {"doc": doc, "has_reference": ref is not None, "same_raw": same_raw, "same_parsed": same_parsed,
               "seconds": round(dur, 1)}
        if ref is not None and not same_parsed:
            a, b = parse_flat(ref).modules or {}, fp.modules or {}
            row["differs_in"] = sorted({f"{m}.{k}" for m in set(a) | set(b)
                                        for k in set(a.get(m) or {}) | set(b.get(m) or {})
                                        if j((a.get(m) or {}).get(k)) != j((b.get(m) or {}).get(k))})
        if i <= 5:                                   # the web app's own code path gives the same parsed answer
            n_path += 1
            n_path_same += j(live_reasoner(text, doc, DATE)) == j(fp.modules or None)
        rows.append(row)
        print(f"[{i}/{len(docs)}] {doc} same_raw={same_raw} same_parsed={same_parsed} {dur:.0f}s", flush=True)
        n_ref = sum(r["has_reference"] for r in rows)
        save(stage, {"environment": environment(), "n_docs": len(docs), "n_done": i, "n_with_reference": n_ref,
                     "same_raw": n_same_raw, "same_parsed": n_same_parsed,
                     "app_code_path_matches_script": f"{n_path_same}/{n_path}", "rows": rows,
                     "reference_manifests": str(old_dir), "live_manifests": str(live_dir),
                     "seconds_total": round(time.time() - t_start)})
    out = json.loads((RESULTS / f"leo_gpu_{stage}.json").read_text())
    if rescore and not args.selftest:
        print("re-scoring the live output with the evaluation scorer:", " ".join(rescore), flush=True)
        r = subprocess.run([PY, *rescore], cwd=REPO, capture_output=True, text=True)
        out["rescore_returncode"] = r.returncode
        out["rescore_output_tail"] = (r.stdout + r.stderr)[-3000:]
        save(stage, out)
        print(out["rescore_output_tail"])
    return out


def stage_parity_fs(args) -> dict:
    from scripts.run_med42_flat_on_fs_test import FS_TEXT_DIR, HELD_OUT
    docs = [(f"fs-test-{p}", (FS_TEXT_DIR / f"{p}.txt").read_text(encoding="utf-8")) for p in HELD_OUT]
    if args.limit:
        docs = docs[:args.limit]
    return _parity(args, "parity_fs", docs, REPO / "data" / "run_manifests_fs_test_flat_c",
                   REPO / "data" / "run_manifests_fs_test_flat_c_live",
                   ["scripts/score_leo_vs_fs_gold.py", "--llm", "L1C=data/run_manifests_fs_test_flat_c_live:L1C",
                    "--out", "eval/results/leo_vs_fs_gold_v05_live"])


def stage_parity_synth(args) -> dict:
    from services import synth_eval
    docs = [(f"synth-{v}", synth_eval.note_text(v)) for v in synth_eval.eval_visits()]
    if args.limit:
        docs = docs[:args.limit]
    return _parity(args, "parity_synth", docs, REPO / "data" / "run_manifests_synth_eval_flat",
                   REPO / "data" / "run_manifests_synth_eval_flat_live",
                   ["scripts/score_leo_vs_synth_gold.py", "--llm", "L1C=data/run_manifests_synth_eval_flat_live:L1C",
                    "--out", "eval/results/leo_vs_synth_gold_v05_live"])


# ---- long documents -------------------------------------------------------------------------

def patient_documents(limit: int = 0):
    """[(patient, corpus, [visit ids], joined text)] for the 30 evaluation patients."""
    from services import synth_eval as se
    out = []
    for name, ps in se.eval_patients().items():
        for p in ps:
            vs = se.visits_of(se.STRATA_CORPUS[name], p)
            out.append((p, se.STRATA_CORPUS[name], vs, "\n\n".join(se.note_text(v) for v in vs)))
    out.sort(key=lambda r: r[0])
    return out[:limit] if limit else out


class _Tap:
    """Remember what the LLM channel returned so the model is not called twice for the same text."""

    def __init__(self, inner):
        self.inner, self.info, self.last, self.last_n_chunks = inner, getattr(inner, "info", None), None, 1

    def __call__(self, text, doc_id, doc_date):
        self.last = self.inner(text, doc_id, doc_date)
        self.last_n_chunks = getattr(self.inner, "last_n_chunks", 1)
        return self.last


def stage_long(args) -> dict:
    import scripts.score_leo_vs_synth_gold as sg      # sets the same scoring conventions as the synthetic evaluation
    import scripts.score_leo_vs_fs_gold as fs
    from services.leo_runtime import LeoRuntime

    docs = patient_documents(args.patients)
    chunked = make_runtime(args, 8000)
    # Llama-3 has an 8k-token context: only documents of up to UNCHUNKED_MAX characters can be sent whole
    unchunked = LeoRuntime(backend=chunked.backend, chunk_max_chars=10 ** 6)
    spec = LeoRuntime(backend=None, use_llm=False)
    share_specialist(unchunked, chunked)
    share_specialist(spec, chunked)
    taps = {"chunked": _Tap(chunked.pipeline._llm_reasoner), "unchunked": _Tap(unchunked.pipeline._llm_reasoner)}
    chunked.pipeline._llm_reasoner, unchunked.pipeline._llm_reasoner = taps["chunked"], taps["unchunked"]
    runs = {"chunked": chunked, "unchunked": unchunked}
    UNCHUNKED_MAX = 20000
    per_doc: dict[str, dict[str, list]] = {k: defaultdict(list) for k in ("chunked", "unchunked")}
    per_doc_sub: dict[str, dict[str, list]] = {k: defaultdict(list) for k in ("chunked", "unchunked")}
    rows, t_start = [], time.time()
    for i, (p, corpus, visits, text) in enumerate(docs, 1):
        gold = sg.gold_for(corpus, p)
        row: dict = {"patient": p, "n_notes": len(visits), "chars": len(text)}
        _, sclaims = spec.pipeline.extract(text, document_id=p, doc_date=DATE, return_claims=True)
        spec_pred = fs.native_from_claims(sclaims, {"accept", "review"}, "epextra")
        for name, rt in runs.items():
            if name == "unchunked" and len(text) > UNCHUNKED_MAX:
                continue
            t0 = time.time()
            _, claims = rt.pipeline.extract(text, document_id=p, doc_date=DATE, return_claims=True)
            preds = {"llm": fs.native_from_module_dicts(taps[name].last), "specialist": spec_pred,
                     "leo_auto": fs.native_from_claims(claims, {"accept"}),
                     "leo_review": fs.native_from_claims(claims, {"accept", "review"})}
            row[name] = {"n_chunks": taps[name].last_n_chunks, "seconds": round(time.time() - t0, 1),
                         "llm_answered": taps[name].last is not None}
            for s, pr in preds.items():
                sc = fs.score_doc(pr, gold)
                per_doc[name][s].append(sc)
                if len(text) <= UNCHUNKED_MAX:
                    per_doc_sub[name][s].append(sc)
        rows.append(row)
        print(f"[{i}/{len(docs)}] {p} chars={len(text)} {row.get('chunked')}", flush=True)

        def summ(pd):
            return {n: {s: dict(zip(("p", "r", "f1"), map(lambda x: round(x, 3), fs.micro(v)))) | {"n_patients": len(v)}
                        for s, v in d.items()} for n, d in pd.items() if d}
        ref = _reference("leo_vs_synth_gold_v05_maint.json")
        save("long", {"environment": environment(), "unchunked_max_chars": UNCHUNKED_MAX, "n_done": i, "n_patients": len(docs),
                      "all_patients_chunked": summ({"chunked": per_doc["chunked"]}),
                      "subset_up_to_20000_chars": summ(per_doc_sub), "per_field_chunked_leo_review":
                          fs.per_field(per_doc["chunked"]["leo_review"]) if per_doc["chunked"]["leo_review"] else {},
                      "reference_per_note_aggregate_L1C": ref, "rows": rows, "seconds_total": round(time.time() - t_start),
                      "note": "Each document is one patient's notes joined; the reference is the patient-level record."})
    return json.loads((RESULTS / "leo_gpu_long.json").read_text())


def _reference(name: str) -> Optional[dict]:
    p = RESULTS / name
    if not p.exists():
        return None
    try:
        s = json.loads(p.read_text())["sources"]["L1C"]["systems"]
        return {k: {"f1": round(v["micro_f1"], 3)} for k, v in s.items()}
    except Exception:
        return None


# ---- questions ------------------------------------------------------------------------------

COMMON_ASMS = ["lamotrigine", "levetiracetam", "carbamazepine", "valproate", "lacosamide", "topiramate", "oxcarbazepine",
               "zonisamide", "phenytoin", "clobazam"]
UNANSWERABLE = [("blood_type", "What is the patient's blood type?", "text"),
                ("pet", "Does the patient own a pet dog?", "yes_no"),
                ("shoe", "What is the patient's shoe size?", "number")]


def _pick(patient: str, pool: list[str], k: int) -> list[str]:
    return sorted(pool, key=lambda d: hashlib.sha1(f"{patient}:{d}".encode()).hexdigest())[:k]


def stage_ask(args) -> dict:
    import scripts.score_leo_vs_synth_gold as sg
    import scripts.score_leo_vs_fs_gold as fs
    from services import synth_eval as se
    from services.leo_catalog import custom_ask
    rt = make_runtime(args, 8000)
    asker = rt.asker
    docs = patient_documents(args.patients)
    tally: dict[str, Counter] = defaultdict(Counter)
    rows, t_start = [], time.time()

    def record(kind: str, res, correct: Optional[bool], expected_answer: bool):
        t = tally[kind]
        t["n"] += 1
        t[f"status_{res.status}"] += 1
        if res.status == "needs_review":
            t["quote_found"] += 1
        if res.status == "rejected":
            t["quote_not_found"] += 1
        if expected_answer:
            t["answerable"] += 1
            if correct:
                t["correct"] += 1
        else:
            t["unanswerable"] += 1
            if res.status in ("needs_review", "rejected"):
                t["invented_answer"] += 1               # gave an answer where the note has none

    for i, (p, corpus, visits, text) in enumerate(docs, 1):
        t = json.loads(se.target_path(corpus, p).read_text(encoding="utf-8"))
        gold = sg.gold_for(corpus, p)
        row = {"patient": p, "chars": len(text), "q": []}

        def ask(spec, kind, expected, expect_answer=True):
            res = asker.ask(text, spec)
            ok = None
            if expect_answer:
                a = (res.answer or "").strip().lower()
                if kind == "age_at_onset":
                    try:
                        ok = abs(float(a) - float(expected)) <= 1.0
                    except ValueError:
                        ok = False
                else:
                    ok = a == str(expected).lower()
            record(kind, res, ok, expect_answer)
            row["q"].append({"kind": kind, "expected": expected, "answer": res.answer, "quote": res.quote, "status": res.status, "ok": ok})
            if kind.startswith("yes_no_drug_") and expect_answer:       # positive-class counts for precision / recall
                a = (res.answer or "").lower()
                tally["drug"]["tp"] += (a == "yes" and expected == "yes")
                tally["drug"]["fp"] += (a == "yes" and expected == "no")
                tally["drug"]["fn"] += (a != "yes" and expected == "yes")

        if gold.get("epilepsy_type"):
            ask(custom_ask("What type of epilepsy does the patient have?", "choice",
                           ("focal", "generalized", "combined_focal_generalized", "unknown"), "etype"),
                "epilepsy_type", gold["epilepsy_type"])
        if gold.get("age_at_onset_years") is not None:
            ask(custom_ask("At what age, in years, did the patient's seizures begin?", "number", aid="onset"),
                "age_at_onset", gold["age_at_onset_years"])
        cur = [d for d in gold.get("current_asms") or []]
        for d in _pick(p, cur, 2):
            ask(custom_ask(f"Is the patient currently taking {d}?", "yes_no", aid=f"on_{d}"), f"yes_no_drug_{d}", "yes")
        for d in _pick(p, [x for x in COMMON_ASMS if x not in cur], 2):
            ask(custom_ask(f"Is the patient currently taking {d}?", "yes_no", aid=f"on_{d}"), f"yes_no_drug_{d}", "no")
        mri = (t.get("mri") or {}).get("hippocampal_sclerosis") or {}
        if mri.get("certainty") != "not_documented" and isinstance(mri.get("value"), bool):
            ask(custom_ask("Does the MRI show hippocampal sclerosis?", "yes_no", aid="hs"), "yes_no_hs",
                "yes" if mri["value"] else "no")
        for aid, q, typ in UNANSWERABLE:
            ask(custom_ask(q, typ, aid=aid), "unanswerable", None, expect_answer=False)
        rows.append(row)
        print(f"[{i}/{len(docs)}] {p} {len(row['q'])} questions", flush=True)

        def fold(prefix: str):
            ks = [k for k in tally if k.startswith(prefix)]
            c = sum((tally[k] for k in ks), Counter())
            return c
        summary = {}
        for label, c in (("epilepsy_type", tally["epilepsy_type"]), ("age_at_onset", tally["age_at_onset"]),
                         ("hippocampal_sclerosis_yes_no", tally["yes_no_hs"]), ("unanswerable", tally["unanswerable"]),
                         ("current_drug_yes_no", fold("yes_no_drug_"))):
            d = dict(c)
            if c.get("answerable"):
                d["accuracy"] = round(c["correct"] / c["answerable"], 3)
            if c.get("unanswerable"):
                d["invented_answer_rate"] = round(c["invented_answer"] / c["unanswerable"], 3)
            if label == "current_drug_yes_no":
                tp, fp, fn = tally["drug"]["tp"], tally["drug"]["fp"], tally["drug"]["fn"]
                d.update(tp=tp, fp=fp, fn=fn, precision_yes=round(tp / (tp + fp), 3) if tp + fp else None,
                         recall_yes=round(tp / (tp + fn), 3) if tp + fn else None)
            summary[label] = d
        save("ask", {"environment": environment(), "n_done": i, "n_patients": len(docs), "summary": summary,
                     "seconds_total": round(time.time() - t_start), "rows": rows,
                     "note": "Answers are LEO's: a quote must be found in the note (status needs_review) or the answer is rejected. "
                             "'accuracy' counts only answers equal to the reference. Documents are a patient's notes joined."})
    return json.loads((RESULTS / "leo_gpu_ask.json").read_text())


STAGES = {"smoke": stage_smoke, "parity_fs": stage_parity_fs, "parity_synth": stage_parity_synth,
          "long": stage_long, "ask": stage_ask}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stages", nargs="+", choices=list(STAGES))
    ap.add_argument("--selftest", action="store_true", help="fake model, CPU: only to debug this script")
    ap.add_argument("--limit", type=int, default=0, help="parity: first N documents")
    ap.add_argument("--patients", type=int, default=0, help="long/ask: first N patients (0 = all 30)")
    args = ap.parse_args(argv)
    if args.selftest:                                    # never mix fake output into the real results
        global RESULTS
        RESULTS = Path("/tmp/leo_gpu_selftest")
    bad = 0
    for s in args.stages:
        print(f"\n===== {s} =====", flush=True)
        try:
            out = STAGES[s](args)
            if s == "smoke":
                save("smoke", out)
                bad += not out.get("ok")
        except Exception as e:                                   # a later stage should still run
            import traceback
            traceback.print_exc()
            save(s, {"environment": environment(), "error": f"{type(e).__name__}: {e}"})
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
