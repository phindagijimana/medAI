#!/usr/bin/env python3
"""leo: install, check, start and use LEO (LLM + EpExtra + Ontology) for epilepsy phenotype extraction.

    leo install                       add the packages LEO needs to venv-medcat (needs network)
    leo check [--slurm] [--gpu]       verify the install; --slurm runs the GPU check on a GPU node
    leo start [--cpu] [--local]       start the web app (default: Slurm GPU job); then `leo status`
    leo status | stop | ui            where the server is, stop it, print the URL
    leo batch IN [-o OUT]             spreadsheet in -> spreadsheet out with phenotype columns
    leo extract NOTE | -              one note, result as a table row (CSV or JSON)
    leo ask NOTE "question"           one question about one note, with a checked quote
    leo phenotypes                    what can be extracted, panels, question templates
    leo evidence                      what has been measured, with n and the limits

Where it runs.  The default is a Slurm job on a GPU node (Med42-8B + EpExtra): `--cpu` asks for a CPU
node and runs EpExtra only (no LLM: nothing is cross-checked, so every value is marked needs_review);
`--local` runs on this node (`--mode auto` uses the GPU when there is one and says so when it falls back to CPU).  Output files
contain note text; keep them where the input notes are allowed to be.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PY = REPO / "venv-medcat" / "bin" / "python"
STATE = REPO / ".leo_server.json"
JOBDIR = REPO / "logs" / "leo_jobs"
NEEDED = {"flask": "flask", "flask_cors": "flask-cors", "dotenv": "python-dotenv", "lmformatenforcer": "lm-format-enforcer",
          "openpyxl": "openpyxl", "pandas": "pandas", "pydantic": "pydantic", "medcat": "medcat", "medspacy": "medspacy",
          "torch": "torch", "transformers": "transformers", "peft": "peft"}
SAMPLE = ("Dear Dr Smith,\n\nHistory of Present Illness\n\nThe patient has focal epilepsy with seizures beginning at age 11. "
          "Current seizure frequency is about two seizures per month.\n\nMedications\n\nThe patient takes lamotrigine "
          "200 mg twice daily and lacosamide 100 mg twice daily. In the past valproate was stopped because of tremor.\n\n"
          "Assessment\n\nFocal epilepsy, continue current medicines.")


# ─── small helpers ───────────────────────────────────────────────────────

def _say(ok: bool | None, what: str, detail: str = "") -> None:
    mark = {True: "PASS", False: "FAIL", None: "info"}[ok]
    print(f"  [{mark}] {what}" + (f": {detail}" if detail else ""))


def _slurm_ok() -> bool:
    return subprocess.run(["which", "sbatch"], capture_output=True).returncode == 0


def _cuda() -> bool:
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _mode(requested: str) -> str:
    if requested in ("gpu", "cpu"):
        return requested
    if _cuda():
        return "gpu"
    print("[leo] no GPU on this node: running EpExtra only (no LLM; every value will be marked needs_review).", file=sys.stderr)
    return "cpu"


def _runtime(args):
    from services.leo_runtime import LeoRuntime, parse_disagree_llm
    mode = _mode(getattr(args, "mode", "auto"))
    arm = getattr(args, "arm", "") or ("L0C" if getattr(args, "adapter", "") else "L1C")
    return LeoRuntime.load(mode=mode, arm=arm, adapter_dir=getattr(args, "adapter", "") or "",
                           chunk_max_chars=getattr(args, "chunk_chars", 8000),
                           disagree_llm=parse_disagree_llm(getattr(args, "disagree_llm", None)))


def _submit(name: str, argv: list[str], *, gpu: bool, partition: str, hours: int, extra_env: dict | None = None) -> str:
    """Write a Slurm script that runs `leo <argv> --local` and submit it.  Returns the job id."""
    if not _slurm_ok():
        raise SystemExit("sbatch not found: not on a Slurm cluster. Use --local.")
    JOBDIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    script = JOBDIR / f"{name}_{ts}.sh"
    gres = "#SBATCH --gres=gpu:l40s.24g:1\n" if gpu else ""
    env_lines = "".join(f"export {k}={shlex.quote(v)}\n" for k, v in (extra_env or {}).items())
    cmd = " ".join(shlex.quote(a) for a in [str(PY), str(REPO / "scripts" / "leo_cli.py"), *argv])
    script.write_text(f"""#!/bin/bash
#SBATCH --job-name=leo-{name}
#SBATCH --partition={partition}
{gres}#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task={8 if gpu else 16}
#SBATCH --mem={'64G' if gpu else '48G'}
#SBATCH --time={hours:02d}:00:00
#SBATCH --output={JOBDIR}/%x_%j.out
#SBATCH --error={JOBDIR}/%x_%j.err
set -euo pipefail
cd {shlex.quote(str(REPO))}
if [ -f .env ]; then set -a; . ./.env; set +a; fi
export APP_HOME={shlex.quote(str(REPO))} PYTHONNOUSERSITE=1 OMP_NUM_THREADS="${{SLURM_CPUS_PER_TASK:-4}}"
module load cuda 2>/dev/null || true
{env_lines}echo "node=$(hostname) job=${{SLURM_JOB_ID}} start=$(date)"
{'nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv || true' if gpu else ''}
exec {cmd}
""")
    out = subprocess.run(["sbatch", "--parsable", str(script)], capture_output=True, text=True)
    if out.returncode:
        raise SystemExit(f"sbatch failed: {out.stderr.strip()}")
    jid = out.stdout.strip().split(";")[0]
    print(f"[leo] submitted Slurm job {jid} ({'GPU' if gpu else 'CPU'}); script {script}; logs {JOBDIR}/leo-{name}_{jid}.out")
    return jid


def _wait(jid: str) -> None:
    print(f"[leo] waiting for job {jid} (Ctrl-C leaves it running) …")
    while True:
        r = subprocess.run(["squeue", "-j", jid, "-h", "-o", "%T"], capture_output=True, text=True).stdout.strip()
        if not r:
            return
        time.sleep(15)


# ─── commands ────────────────────────────────────────────────────────────

def cmd_phenotypes(args) -> int:
    from services import leo_catalog as c
    d = c.describe()
    if args.json:
        print(json.dumps(d, indent=2))
        return 0
    print("EXTRACT (LLM + EpExtra + ontology, fused and verified)")
    print("  accuracy: measured = tested against reference notes (synthetic only); rules_only = the specialist alone was")
    print("  scored (synthetic); indirect = only its effect on another field was tested; none = not tested.")
    print("  `leo evidence` prints the figures.\n")
    for p in d["extract"]:
        lvl = p["evidence"] + (" (inferred)" if p["derived"] else "")
        print(f"  {p['id']:<26} {lvl:<20} {p['label']}")
    print("\nPANELS   (use with --phenotypes)")
    for p in d["panels"]:
        print(f"  {p['id']:<12} {len(p['members']):2d} items  {p['label']}")
    print("\nQUESTION TEMPLATES (LLM only, quote checked, always for review, accuracy not measured; use --ask-template ID)")
    for a in d["ask_templates"]:
        print(f"  {a['id']:<22} [{a['answer_type']:<6}] {a['question']}")
    print('\nYour own question: --question "Which side is the lesion?" [--question-type yes_no|text|number]')
    return 0


def cmd_evidence(args) -> int:
    from services.leo_evidence import evidence
    e = evidence()
    if args.json:
        print(json.dumps(e, indent=2))
        return 0
    print(f"Configuration tested: {e['config']}\n")
    for d in e["datasets"]:
        print(f"{d['label']}  [{d['text']} text, n={d.get('n', '?')} {d['unit']}]" + ("" if d["available"] else "  FILE MISSING"))
        for s, v in (d.get("systems") or {}).items():
            ci = f"  95% CI [{v['ci'][0]:.2f}, {v['ci'][1]:.2f}]" if v.get("ci") else ""
            print(f"    {s:<11} micro-F1 {v['micro_f1']:.2f}  (P {v['micro_p']:.2f}, R {v['micro_r']:.2f}){ci}")
    print("\nPer field, F1 of LEO reviewed output / auto-accepted only / model alone   (n = notes with a reference value)")
    for pid, entries in e["fields"].items():
        for en in entries:
            cells = []
            for d in e["datasets"]:
                x = en.get(d["id"])
                if x and x["reviewed"]:
                    cells.append(f"{d['id']}: {x['reviewed']['f1']:.2f} / {x['auto']['f1']:.2f} / {x['llm_alone']['f1']:.2f} (n={x['reviewed']['n']})")
            print(f"  {pid:<18} {en['metric']:<34} " + "   ".join(cells))
    print("\nLimits:")
    for c in e["caveats"]:
        print("  - " + c)
    return 0


def _selection(args):
    from services import leo_catalog as cat
    phen = cat.resolve_phenotypes(args.phenotypes or None)
    asks = [cat.ask_template(t) for t in (args.ask_template or [])]
    types = list(args.question_type or [])
    for i, q in enumerate(args.question or []):
        asks.append(cat.custom_ask(q, types[i] if i < len(types) else "text", aid=f"q{i + 1}"))
    return phen, asks


def cmd_batch(args) -> int:
    from services import leo_batch as lb
    inp = Path(args.input).expanduser()
    if not inp.exists():
        raise SystemExit(f"input not found: {inp}")
    if not args.local:
        argv = ["batch", str(inp.resolve()), "--local", "--mode", "cpu" if args.cpu else "gpu"]
        for flag, val in (("-o", args.output), ("--format", args.format), ("--phenotypes", args.phenotypes),
                          ("--text-col", args.text_col), ("--id-col", args.id_col), ("--date-col", args.date_col),
                          ("--sheet", args.sheet), ("--adapter", args.adapter), ("--arm", args.arm),
                          ("--limit", str(args.limit) if args.limit else ""), ("--chunk-chars", str(args.chunk_chars))):
            if val:
                argv += [flag, str(Path(val).resolve()) if flag == "-o" else val]
        for t in args.ask_template or []:
            argv += ["--ask-template", t]
        for i, q in enumerate(args.question or []):
            argv += ["--question", q]
            if args.question_type and i < len(args.question_type):
                argv += ["--question-type", args.question_type[i]]
        if args.accepted_only:
            argv.append("--accepted-only")
        jid = _submit("batch", argv, gpu=not args.cpu, partition=args.partition or "interactive", hours=args.hours)
        if args.wait:
            _wait(jid)
        return 0
    phen, asks = _selection(args)
    if asks and _mode(args.mode) == "cpu":
        raise SystemExit("questions need the LLM (GPU). Remove --question/--ask-template or run without --cpu.")
    df = lb.read_table(inp, sheet=args.sheet or None)
    cols = lb.detect_columns(df, args.text_col, args.id_col, args.date_col)
    fmt = (args.format or (Path(args.output).suffix.lstrip(".") if args.output else "") or
           ("xlsx" if inp.suffix.lower() in (".xlsx", ".xlsm") else "csv")).lower()
    out = Path(args.output) if args.output else lb.default_output(inp, fmt)
    if args.output is None and not os.access(out.parent, os.W_OK):
        out = Path.cwd() / out.name
    rt = _runtime(args)

    def prog(i, n, doc):
        if i == 1 or i % 10 == 0 or i == n:
            print(f"[leo] {i}/{n} {doc}", file=sys.stderr, flush=True)

    table, claims, prov = lb.run_table(df, rt, phenotypes=phen, asks=asks, text_col=cols["text"], id_col=cols["id"],
                                       date_col=cols["date"], include_review=not args.accepted_only, limit=args.limit,
                                       progress=prog)
    prov["input_sha256"] = lb.input_hash(inp)
    prov["input_file"] = inp.name
    paths = lb.write_outputs(table, claims, prov, out, fmt, phen)
    print(f"[leo] mode={rt.mode} rows={prov['rows_processed']} errors={prov['rows_error']} llm_rows={prov['rows_with_llm']}")
    for p in paths:
        print(f"[leo] wrote {p}")
    return 1 if prov["rows_error"] == prov["rows_processed"] and prov["rows_processed"] else 0


def cmd_review(args) -> int:
    """Write a reviewed.csv to fill in (Excel works), listing the values that need review."""
    from services import leo_review as lr
    tp = Path(args.table).expanduser()
    table = lr.load_table(tp)
    fields = lr.infer_fields(table)
    if not fields:
        raise SystemExit(f"{tp.name} does not look like a LEO result (no <field>_status columns)")
    df = lr.template(table, fields, "all" if args.all else "flagged")
    out = Path(args.output) if args.output else tp.with_name(tp.stem + ".reviewed.csv")
    if out.exists() and not args.force:
        raise SystemExit(f"{out} exists; use --force to overwrite (decisions in it would be lost)")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"[leo] wrote {out}: {len(df)} value(s) to review")
    print("[leo] fill `decision` (accept | correct | reject) and, for correct, `final_value`; then run: "
          f"leo merge {tp} {out}")
    return 0


def cmd_merge(args) -> int:
    """Add the reviewed values to a LEO result table (<field>_final and <field>_review columns)."""
    from services import leo_review as lr
    out = lr.merge_files(Path(args.table).expanduser(), Path(args.reviewed).expanduser(), args.output,
                         "proposal" if args.keep_unreviewed else "blank")
    print(f"[leo] wrote {out}")
    return 0


def cmd_rollup(args) -> int:
    """One row per patient from a per-note result (optional; the result itself stays per note)."""
    from services import leo_review as lr
    from services.leo_rollup import rollup
    src = Path(args.table).expanduser()
    out = rollup(lr.load_table(src), args.patient_col, args.date_col)
    dest = Path(args.output) if args.output else src.with_name(src.stem + ".patients.csv")
    out.to_csv(dest, index=False, encoding="utf-8-sig")
    print(f"[leo] wrote {dest} ({len(out)} patients). Per field: the latest note that states a value; see docs/LEO_USER_GUIDE.md.")
    return 0


def cmd_extract(args) -> int:
    phen, asks = _selection(args)
    text = sys.stdin.read() if args.note == "-" else Path(args.note).read_text(encoding="utf-8")
    rt = _runtime(args)
    res = rt.extract_note(text, doc_id=args.document_id, phenotypes=phen, asks=asks)
    if res.error:
        raise SystemExit(f"extraction failed: {res.error}")
    if args.json:
        print(json.dumps({"mode": rt.mode, "row": res.row, "claims": res.claims, "asks": res.asks,
                          "versions": rt.versions()}, indent=2, default=str))
        return 0
    print(f"mode: {rt.mode}   llm_used: {res.llm_used}   chunks: {res.n_chunks}")
    for p in phen:
        print(f"  {p.id:<22} {str(res.row.get(p.id, '')):<34} [{res.row.get(p.id + '_status')}]  "
              f"{res.row.get(p.id + '_why', '')}")
    for a in res.asks:
        print(f"  {a['spec_id']:<22} {str(a.get('answer') or ''):<34} [{a['status']}]  {a.get('quote', '')[:80]}")
    return 0


def cmd_ask(args) -> int:
    from services import leo_catalog as cat
    spec = cat.custom_ask(args.question, args.type, tuple(args.choices or ()), "q")
    text = sys.stdin.read() if args.note == "-" else Path(args.note).read_text(encoding="utf-8")
    args.mode = "gpu" if args.mode == "auto" and _cuda() else args.mode
    rt = _runtime(args)
    if rt.asker is None:
        raise SystemExit("questions need the LLM (GPU node).")
    r = rt.asker.ask(text, spec)
    print(json.dumps(r.as_dict(), indent=2))
    return 0


def _read_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def _bind_host(args) -> str:
    """The app has no login, so it listens on this machine only, unless it runs on a Slurm node (where an SSH
    tunnel from the login node needs the node's own address) or ``--host`` says otherwise."""
    return getattr(args, "host", "") or ("0.0.0.0" if os.environ.get("SLURM_JOB_ID") else "127.0.0.1")


def cmd_start(args) -> int:
    if args.local:
        port = str(args.port)
        mode = _mode(args.mode)
        env = dict(os.environ, SERVICE_PORT=port, SERVICE_HOST=_bind_host(args), APP_HOME=str(REPO),
                   MEDAI_LOAD_MED42="1" if mode == "gpu" else "0", MEDAI_REQUIRE_GPU="1" if mode == "gpu" else "0")
        if args.adapter:
            env["MEDAI_LORA_ADAPTER_DIR"] = str(Path(args.adapter).resolve())
            env["MEDAI_LEO_ARM"] = args.arm or "L0C"
        elif args.arm:
            env["MEDAI_LEO_ARM"] = args.arm
        STATE.write_text(json.dumps({"node": os.uname().nodename, "port": args.port, "mode": mode,
                                     "job": os.environ.get("SLURM_JOB_ID", ""), "started": datetime.now().isoformat()}))
        print(f"[leo] starting LEO web app on {os.uname().nodename}:{port} ({mode}); UI at /leo/ui")
        os.chdir(REPO)
        os.execve(str(PY), [str(PY), "app.py"], env)
    argv = ["start", "--local", "--port", str(args.port), "--mode", "cpu" if args.cpu else "gpu"]
    if args.adapter:
        argv += ["--adapter", str(Path(args.adapter).resolve())]
    if args.arm:
        argv += ["--arm", args.arm]
    _submit("server", argv, gpu=not args.cpu, partition=args.partition or "general", hours=args.hours)
    print("[leo] when it starts, `leo status` shows the URL and the SSH tunnel command.")
    return 0


def cmd_status(args) -> int:
    st = _read_state()
    if _slurm_ok():
        q = subprocess.run(["squeue", "-u", os.environ.get("USER", ""), "-h", "-o", "%i %j %T %M %R"],
                           capture_output=True, text=True).stdout
        mine = [l for l in q.splitlines() if " leo-" in l]
        print("Slurm jobs:\n  " + ("\n  ".join(mine) if mine else "none"))
    if not st:
        print("server: not started (leo start)")
        return 0
    print(f"server: {st.get('mode')} on {st['node']}:{st['port']} (job {st.get('job') or 'local'}, started {st.get('started')})")
    print(f"  UI:      http://{st['node']}:{st['port']}/leo/ui")
    print(f"  tunnel:  ssh -L {st['port']}:{st['node']}:{st['port']} {os.environ.get('USER', 'USER')}@<login-host>   then http://localhost:{st['port']}/leo/ui")
    return 0


def cmd_stop(args) -> int:
    st = _read_state()
    if st.get("job"):
        subprocess.run(["scancel", st["job"]])
        print(f"[leo] cancelled job {st['job']}")
    else:
        print("[leo] no Slurm job recorded; stop a local server with Ctrl-C")
    STATE.unlink(missing_ok=True)
    return 0


def cmd_ui(args) -> int:
    st = _read_state()
    print(f"http://{st['node']}:{st['port']}/leo/ui" if st else "http://localhost:8085/leo/ui   (start it first: leo start)")
    return 0


def cmd_install(args) -> int:
    import importlib
    print(f"[leo] python: {sys.executable}")
    if not PY.exists():
        print(f"[leo] {PY} not found. Create it first: python3.11 -m venv venv-medcat && "
              "venv-medcat/bin/pip install medcat medspacy torch transformers peft (see docs/MedCAT.md).")
        return 1
    missing = []
    for mod, pkg in NEEDED.items():
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    if not missing:
        print("[leo] all packages present")
        return 0
    print(f"[leo] missing: {', '.join(missing)}")
    if args.check_only:
        return 1
    return subprocess.call([str(PY), "-m", "pip", "install", *missing])


def cmd_check(args) -> int:
    if args.slurm:
        jid = _submit("check", ["check", "--gpu"], gpu=True, partition="interactive", hours=1)
        if args.wait:
            _wait(jid)
            out = JOBDIR / f"leo-check_{jid}.out"
            print(out.read_text() if out.exists() else "(no output yet)")
        return 0
    fails = 0

    def rec(ok, what, detail=""):
        nonlocal fails
        fails += (ok is False)
        _say(ok, what, detail)

    print("LEO check")
    import importlib
    for mod, pkg in NEEDED.items():
        try:
            importlib.import_module(mod)
            try:
                from importlib.metadata import version
                ver = version(pkg)
            except Exception:
                ver = ""
            rec(True, f"import {mod}", ver)
        except Exception as e:
            rec(False, f"import {mod}", f"{type(e).__name__}: run `leo install`")
    cdb = REPO / "data" / "medcat_cdb_epilepsy" / "cdb"
    rec(cdb.exists(), "EpExtra concept database", str(cdb))
    rec((REPO / "data" / "ontologies" / "MANIFEST.json").exists(), "ontology manifest")
    cache = REPO / "model_cache"
    rec(any(cache.glob("models--m42-health--Llama3-Med42-8B")), "Med42-8B weights in model_cache", str(cache))
    if args.adapter:
        rec(Path(args.adapter, "adapter_config.json").exists(), "adapter", args.adapter)
    rec(None, "GPU visible", "yes" if _cuda() else "no (normal on a login node)")
    from services.leo_catalog import ask_template, resolve_phenotypes
    from services.leo_runtime import LeoRuntime
    try:
        rt = LeoRuntime.load(mode="cpu")
        res = rt.extract_note(SAMPLE, doc_id="check", phenotypes=resolve_phenotypes(["core"]))
        ok = not res.error and res.row.get("epilepsy_type") == "focal"
        rec(ok, "specialist-only extraction on a sample note", res.error or f"epilepsy_type={res.row.get('epilepsy_type')}")
    except Exception as e:
        rec(False, "specialist-only extraction", f"{type(e).__name__}: {e}")
    if args.gpu:
        if not _cuda():
            rec(False, "GPU requested but none visible", "run `leo check --slurm`")
        else:
            try:
                t0 = time.time()
                rt = LeoRuntime.load(mode="gpu", adapter_dir=args.adapter or "", arm="L0C" if args.adapter else "L1C")
                rec(True, "Med42-8B loaded", f"{time.time() - t0:.0f}s")
                res = rt.extract_note(SAMPLE, doc_id="check", phenotypes=resolve_phenotypes(["core"]))
                row = res.row
                ok = (not res.error and res.llm_used and row.get("epilepsy_type") == "focal"
                      and "lamotrigine" in row.get("current_asms", "") and "valproate" not in row.get("current_asms", ""))
                rec(ok, "LLM + specialist extraction on a sample note", res.error or json.dumps(
                    {k: row.get(k) for k in ("epilepsy_type", "age_at_onset", "seizure_frequency", "current_asms")}))
                a = rt.asker.ask(SAMPLE, ask_template("aura"))
                rec(a.status in ("needs_review", "not_documented"), "question answering with quote check", f"{a.status} {a.answer}")
            except Exception as e:
                rec(False, "GPU path", f"{type(e).__name__}: {e}")
    print("RESULT:", "ALL CHECKS PASSED" if not fails else f"{fails} FAILED")
    return 1 if fails else 0


# ─── argument parsing ────────────────────────────────────────────────────

def _common(sp, *, model=True):
    sp.add_argument("--phenotypes", default="", help="comma list of phenotype ids and/or panel ids (default: core)")
    sp.add_argument("--ask-template", action="append", help="predefined question id (repeatable)")
    sp.add_argument("--question", action="append", help="your own question (repeatable)")
    sp.add_argument("--question-type", action="append", help="yes_no | text | number, one per --question")
    if model:
        sp.add_argument("--mode", choices=("auto", "gpu", "cpu"), default="auto", help="where the model runs (local runs)")
        sp.add_argument("--adapter", default="", help="flat-contract LoRA adapter dir (Arm H2)")
        sp.add_argument("--arm", default="", help="LLM prompt arm (default L1C; L0C with an adapter)")
        sp.add_argument("--chunk-chars", type=int, default=8000, help="split notes longer than this (default 8000)")
        sp.add_argument("--disagree-llm", default=None,
                        help="fields where the model's value is shown when model and rules disagree "
                             "(default predominant_seizure_type; 'none' = rules value everywhere)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="leo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("install", help="add missing packages to venv-medcat")
    sp.add_argument("--check-only", action="store_true")
    sp.set_defaults(fn=cmd_install)

    sp = sub.add_parser("check", help="verify the install")
    sp.add_argument("--gpu", action="store_true", help="also load the model and run the LLM path (GPU node)")
    sp.add_argument("--slurm", action="store_true", help="run `check --gpu` as a Slurm GPU job")
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--adapter", default="")
    sp.set_defaults(fn=cmd_check)

    sp = sub.add_parser("start", help="start the web app (default: Slurm GPU job)")
    sp.add_argument("--cpu", action="store_true", help="CPU node, EpExtra only")
    sp.add_argument("--local", action="store_true", help="run on this node")
    sp.add_argument("--mode", choices=("auto", "gpu", "cpu"), default="auto")
    sp.add_argument("--port", type=int, default=8085)
    sp.add_argument("--host", default="", help="address to listen on (default: this machine only; the app has no login)")
    sp.add_argument("--adapter", default="")
    sp.add_argument("--arm", default="")
    sp.add_argument("--partition", default="")
    sp.add_argument("--hours", type=int, default=24)
    sp.set_defaults(fn=cmd_start)

    for name, fn in (("status", cmd_status), ("stop", cmd_stop), ("ui", cmd_ui)):
        sp = sub.add_parser(name)
        sp.set_defaults(fn=fn)

    sp = sub.add_parser("batch", help="spreadsheet in, spreadsheet out")
    sp.add_argument("input", help=".csv .tsv .xlsx .jsonl .txt or a directory of .txt")
    sp.add_argument("-o", "--output", default=None, help="output path (default: <input>_leo.csv|xlsx)")
    sp.add_argument("--format", choices=("csv", "xlsx"), default=None)
    sp.add_argument("--text-col", default="")
    sp.add_argument("--id-col", default="")
    sp.add_argument("--date-col", default="")
    sp.add_argument("--sheet", default="")
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--accepted-only", action="store_true", help="leave values that need review blank")
    sp.add_argument("--cpu", action="store_true", help="submit a CPU job (EpExtra only)")
    sp.add_argument("--local", action="store_true", help="run here instead of submitting a Slurm job")
    sp.add_argument("--wait", action="store_true")
    sp.add_argument("--partition", default="")
    sp.add_argument("--hours", type=int, default=4)
    _common(sp)
    sp.set_defaults(fn=cmd_batch)

    sp = sub.add_parser("review", help="make a reviewed.csv to fill in from a result table")
    sp.add_argument("table", help="a LEO result (.csv or .xlsx)")
    sp.add_argument("-o", "--output", default=None, help="default: <table>.reviewed.csv")
    sp.add_argument("--all", action="store_true", help="list accepted values too, not only those needing review")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(fn=cmd_review)

    sp = sub.add_parser("merge", help="add reviewed values to a result table")
    sp.add_argument("table", help="a LEO result (.csv or .xlsx)")
    sp.add_argument("reviewed", help="the reviewed.csv (from the app, or filled in after `leo review`)")
    sp.add_argument("-o", "--output", default=None, help="default: <table>.merged.csv|xlsx")
    sp.add_argument("--keep-unreviewed", action="store_true",
                    help="in <field>_final, keep LEO's value for unreviewed values that need review (default: blank)")
    sp.set_defaults(fn=cmd_merge)

    sp = sub.add_parser("rollup", help="one row per patient from a per-note result (optional)")
    sp.add_argument("table", help="a LEO result (.csv or .xlsx)")
    sp.add_argument("--patient-col", required=True, help="column that identifies the patient")
    sp.add_argument("--date-col", default="", help="note date column (default: later row = later note)")
    sp.add_argument("-o", "--output", default=None, help="default: <table>.patients.csv")
    sp.set_defaults(fn=cmd_rollup)

    sp = sub.add_parser("extract", help="one note")
    sp.add_argument("note", help="text file or - for stdin")
    sp.add_argument("--document-id", default="note")
    sp.add_argument("--json", action="store_true")
    _common(sp)
    sp.set_defaults(fn=cmd_extract)

    sp = sub.add_parser("ask", help="one question about one note")
    sp.add_argument("note")
    sp.add_argument("question")
    sp.add_argument("--type", choices=("yes_no", "text", "number", "choice"), default="text")
    sp.add_argument("--choices", nargs="*")
    sp.add_argument("--mode", choices=("auto", "gpu", "cpu"), default="auto")
    sp.add_argument("--adapter", default="")
    sp.add_argument("--arm", default="")
    sp.add_argument("--chunk-chars", type=int, default=8000)
    sp.set_defaults(fn=cmd_ask)

    sp = sub.add_parser("evidence", help="what has been measured (from eval/results)")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_evidence)

    sp = sub.add_parser("phenotypes", help="catalogue")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_phenotypes)

    args = ap.parse_args(argv)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
