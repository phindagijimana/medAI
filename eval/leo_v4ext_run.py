#!/usr/bin/env python3
"""Measurement driver: run LEO (same code path as `leo batch --local`) over the v4_ext notes and keep the raw claims.

`leo batch` writes claims.csv with values flattened to text; the extended-phenotype scorer needs the structured value
(e.g. eeg.ied_findings localization / laterality).  This driver calls the same functions as `leo batch`
(LeoRuntime.load -> leo_batch.run_table -> leo_batch.write_outputs) and additionally records, per note, the raw
claims (field_path, structured value, verdict, reasons, detectors), seconds, errors, and samples GPU memory.

    python eval/leo_v4ext_run.py --mode gpu|cpu --out data/leo_runs/v4ext_llm
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def dump(v):
    if hasattr(v, "model_dump"):
        return v.model_dump(mode="json")
    return v


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("gpu", "cpu"), required=True)
    ap.add_argument("--input", default="data/leo_runs/v4ext_notes.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--phenotypes", default="all")
    ap.add_argument("--no-ext-reader", action="store_true",
                    help="core L1C reader only (the previous GPU run; default is L1C+X1C+P1C+F1C)")
    ap.add_argument("--ext-detector", action="append", default=[],
                    help="opt-in sidecar (repeatable). Does not overwrite headline v4ext_* files.")
    args = ap.parse_args()

    from services import leo_batch as lb
    from services import leo_catalog as cat
    from services.leo_runtime import LeoRuntime

    peak = {"mib": 0, "samples": []}
    stop = threading.Event()

    def sampler():
        while not stop.is_set():
            try:
                o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                   capture_output=True, text=True, timeout=10).stdout.split()
                if o:
                    m = int(o[0])
                    peak["mib"] = max(peak["mib"], m)
                    peak["samples"].append((round(time.time() - T0, 1), m))
            except Exception:
                pass
            stop.wait(5)

    T0 = time.time()
    if args.mode == "gpu":
        threading.Thread(target=sampler, daemon=True).start()
    t_load = time.time()
    from services.ext_detectors import parse_ext_detectors
    dets = parse_ext_detectors(args.ext_detector or None)
    rt = LeoRuntime.load(mode=args.mode, arm="L1C", ext_reader=not args.no_ext_reader,
                         ext_detectors=dets)
    if dets:
        print(f"[drv] ext_detectors={list(dets)}", flush=True)
    load_s = round(time.time() - t_load, 1)
    print(f"[drv] mode={rt.mode} model load {load_s}s", flush=True)

    # capture raw claims per note by wrapping the pipeline's extract
    pipe = rt.pipeline
    raw: dict[str, list] = {}
    orig = pipe.extract

    def wrapped(text, document_id=None, **kw):
        stats, claims = orig(text, document_id=document_id, **kw)
        raw[document_id] = [{
            "field_path": c.field_path, "value": dump(c.value), "verdict": c.validator_verdict.value,
            "reasons": [r.value for r in c.reason_codes], "detectors": list(c.detectors or []),
            "evidence": c.mention.text, "assertion": c.assertion.value,
            "temporality": c.temporality.status.value, "section": c.section,
            "sidecar_alternative": getattr(c, "sidecar_alternative", None)} for c in claims]
        return stats, claims

    pipe.extract = wrapped

    per_note = []
    orig_note = rt.extract_note

    def timed(text, **kw):
        t = time.time()
        res = orig_note(text, **kw)
        per_note.append({"note_id": kw.get("doc_id"), "seconds": round(time.time() - t, 2), "error": res.error,
                         "llm_used": res.llm_used, "n_chunks": res.n_chunks, "n_claims": res.n_claims,
                         "n_accepted": res.n_accepted, "n_review": res.n_review, "n_rejected": res.n_rejected,
                         "chars": len(text)})
        return res

    rt.extract_note = timed

    inp = Path(args.input)
    df = lb.read_table(inp)
    cols = lb.detect_columns(df, "text", "note_id", "visit_date")
    phen = cat.resolve_phenotypes(args.phenotypes)

    def prog(i, n, doc):
        print(f"[drv] {i}/{n} {doc} {per_note[-1]['seconds']}s err={per_note[-1]['error']!r}", flush=True)

    t_run = time.time()
    table, claims, prov = lb.run_table(df, rt, phenotypes=phen, asks=[], text_col=cols["text"], id_col=cols["id"],
                                       date_col=cols["date"], include_review=True, limit=args.limit, progress=prog)
    wall = round(time.time() - t_run, 1)
    prov["input_sha256"] = lb.input_hash(inp)
    prov["input_file"] = inp.name
    out = Path(args.out)
    paths = lb.write_outputs(table, claims, prov, out.with_suffix(".csv"), "csv", phen)
    stop.set()
    extra = {"mode": rt.mode, "model_load_seconds": load_s, "run_wall_seconds": wall, "per_note": per_note,
             "gpu_peak_mib_nvidia_smi": peak["mib"], "gpu_samples": peak["samples"][-400:],
             "rows_processed": prov["rows_processed"], "rows_error": prov["rows_error"],
             "rows_with_llm": prov["rows_with_llm"]}
    try:
        import torch
        if torch.cuda.is_available():
            extra["torch_max_memory_allocated_mib"] = round(torch.cuda.max_memory_allocated() / 2**20)
            extra["torch_max_memory_reserved_mib"] = round(torch.cuda.max_memory_reserved() / 2**20)
            extra["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception:
        pass
    Path(str(out) + ".stats.json").write_text(json.dumps(extra, indent=1), encoding="utf-8")
    Path(str(out) + ".rawclaims.json").write_text(json.dumps(raw, default=str), encoding="utf-8")
    print(f"[drv] rows={prov['rows_processed']} errors={prov['rows_error']} llm_rows={prov['rows_with_llm']} wall={wall}s")
    for p in paths:
        print("[drv] wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
