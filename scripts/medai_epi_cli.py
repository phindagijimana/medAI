#!/usr/bin/env python3
"""medai-epi — command-line client for the MedAI-EPI extraction service.

Wraps the /extract/* HTTP surface so a researcher can run phenotype extraction
from the shell without writing curl by hand or opening the browser UI.

Usage examples:

    # Health probe (backend load status, registered prompts, doc types)
    medai-epi health

    # Single-document extraction from a file
    medai-epi extract --doc-type progress_note --arm M1 note.txt

    # Batch a CSV of notes → long-format CSV out
    medai-epi csv notes.csv > phenotypes.csv

    # Freeform question grounded in one note
    medai-epi chat --text-file note.txt "was surgery mentioned?"

    # Long-note extraction (auto-chunk + merge)
    medai-epi long --doc-type progress_note --arm M1 long_letter.txt

    # Open the browser UI (starts nothing; just prints/opens the URL)
    medai-epi ui

By default connects to http://localhost:8085 (override with --server URL or
$MEDAI_EPI_URL). Exits non-zero on HTTP error; prints structured JSON or CSV
to stdout on success.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


DEFAULT_URL = os.environ.get("MEDAI_EPI_URL", "http://localhost:8085")


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only — no `requests` dependency for the CLI)
# ---------------------------------------------------------------------------


def _http(method: str, url: str, *, body: dict | bytes | None = None,
          content_type: str | None = None, timeout: int = 600) -> tuple[int, bytes, dict]:
    if isinstance(body, dict):
        body_bytes = json.dumps(body).encode("utf-8")
        content_type = content_type or "application/json"
    else:
        body_bytes = body

    req = urllib.request.Request(url, method=method, data=body_bytes)
    if content_type:
        req.add_header("Content-Type", content_type)
    req.add_header("Accept", "application/json, text/csv")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, (e.read() if hasattr(e, "read") else b""), dict(e.headers or {})
    except urllib.error.URLError as e:
        sys.stderr.write(f"ERROR: cannot reach {url}: {e}\n")
        sys.stderr.write("  Is the MedAI-EPI service running? "
                         "  Try:  docker compose up   or   python app.py\n")
        sys.exit(3)


def _die_on_error(status: int, body: bytes) -> None:
    if status < 200 or status >= 300:
        try:
            msg = json.loads(body).get("error", body.decode("utf-8", "replace"))
        except Exception:
            msg = body.decode("utf-8", "replace")
        sys.stderr.write(f"ERROR: HTTP {status}: {msg}\n")
        sys.exit(4)


def _read_text_source(args) -> str:
    if getattr(args, "text_file", None):
        return Path(args.text_file).read_text(encoding="utf-8")
    if getattr(args, "text", None):
        return args.text
    if getattr(args, "note_file", None):
        return Path(args.note_file).read_text(encoding="utf-8")
    # positional file (last non-option arg)
    positional = getattr(args, "positional_file", None)
    if positional:
        return Path(positional).read_text(encoding="utf-8")
    sys.stderr.write("ERROR: no note text supplied. "
                     "Pass a file path as the positional argument or use "
                     "--text-file / --text.\n")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_health(args):
    url = f"{args.server}/extract/health"
    status, body, _ = _http("GET", url)
    _die_on_error(status, body)
    d = json.loads(body)
    print(f"schema_version    : {d.get('schema_version')}")
    print(f"backend_attached  : {d.get('med42_backend_attached')}")
    print(f"backend_status    : {d.get('med42_load_status')}")
    print(f"backend_model     : {d.get('backend_model')}")
    print(f"device_selected   : {d.get('device_selected')}")
    print(f"prompts_registered: {len(d.get('prompts_registered') or [])}")
    print(f"doc_types_supported: {', '.join(d.get('doc_types_supported') or [])}")
    return 0


def cmd_registry(args):
    url = f"{args.server}/extract/registry"
    if args.prompt_id:
        url += f"/{args.prompt_id}"
    status, body, _ = _http("GET", url)
    _die_on_error(status, body)
    print(json.dumps(json.loads(body), indent=2))
    return 0


def cmd_extract(args):
    # If a LoRA adapter dir was supplied, publish it into the environment BEFORE
    # any downstream backend is instantiated. services/med42_model.py reads
    # MEDAI_LORA_ADAPTER_DIR at Med42ModelService.__init__ time; setting it here
    # lets `medai-epi extract --lora-adapter DIR ...` reach the backend even in
    # in-process / test-launch scenarios where the service is spawned by the
    # same Python process.
    if getattr(args, "lora_adapter", None):
        os.environ["MEDAI_LORA_ADAPTER_DIR"] = args.lora_adapter

    text = _read_text_source(args)
    payload = {
        "source_text": text,
        "doc_type": args.doc_type,
        "arm": args.arm,
    }
    if args.doc_id:
        payload["doc_id"] = args.doc_id
    if args.patient_id:
        payload["patient_id"] = args.patient_id
    if getattr(args, "model", None):
        payload["model"] = args.model
    if getattr(args, "verify", False) and getattr(args, "verifier_model", None):
        payload["verify"] = True
        payload["verifier_model"] = args.verifier_model
    status, body, _ = _http("POST", f"{args.server}/extract", body=payload)
    _die_on_error(status, body)
    print(json.dumps(json.loads(body), indent=2))
    return 0


def cmd_csv(args):
    if args.input_csv:
        raw = Path(args.input_csv).read_bytes()
        status, body, hdrs = _http(
            "POST", f"{args.server}/extract/csv",
            body=raw, content_type="text/csv",
        )
    else:
        text = _read_text_source(args)
        payload = {"source_text": text, "doc_type": args.doc_type, "arm": args.arm}
        if args.doc_id: payload["doc_id"] = args.doc_id
        status, body, hdrs = _http(
            "POST", f"{args.server}/extract/csv", body=payload,
        )
    _die_on_error(status, body)
    output = args.output
    if output:
        Path(output).write_bytes(body)
        rows = hdrs.get("X-Rows-Extracted") or "?"
        docs = hdrs.get("X-Docs-Ok") or "?"
        errs = hdrs.get("X-Docs-Err") or "?"
        sys.stderr.write(f"wrote {output}  ({rows} rows, {docs} docs ok, {errs} err)\n")
    else:
        sys.stdout.buffer.write(body)
    return 0


def cmd_long(args):
    text = _read_text_source(args)
    payload = {
        "source_text": text,
        "doc_type": args.doc_type,
        "arm": args.arm,
    }
    if args.doc_id: payload["doc_id"] = args.doc_id
    status, body, _ = _http("POST", f"{args.server}/extract/long", body=payload)
    _die_on_error(status, body)
    print(json.dumps(json.loads(body), indent=2))
    return 0


def cmd_chat(args):
    text = _read_text_source(args)
    payload = {
        "source_text": text,
        "question": args.question,
    }
    if args.doc_id: payload["doc_id"] = args.doc_id
    status, body, _ = _http("POST", f"{args.server}/extract/chat", body=payload)
    _die_on_error(status, body)
    d = json.loads(body)
    print(f"Q: {args.question}")
    print(f"A: {d.get('answer', '(no answer)')}")
    print(f"   confidence: {d.get('confidence', 'unknown')}")
    if d.get("evidence_text"):
        print(f"   evidence : \"{d['evidence_text']}\"")
    if args.json:
        print("\n" + json.dumps(d, indent=2))
    return 0


def cmd_chain(args):
    """Run the LEO chain on one note; prints claims (or writes them as JSONL)."""
    text = _read_text_source(args)
    payload = {"source_text": text, "persist": not args.no_persist}
    if args.doc_id:
        payload["document_id"] = args.doc_id
    if args.doc_date:
        payload["doc_date"] = args.doc_date
    status, body, _ = _http("POST", f"{args.server}/extract/chain", body=payload)
    _die_on_error(status, body)
    res = json.loads(body)
    if args.output:
        Path(args.output).write_text(
            "\n".join(json.dumps(c) for c in res["claims"]) + "\n", encoding="utf-8")
        st = res["stats"]
        print(f"claims={st['n_claims_emitted']} accept={st['n_accepted']} review={st['n_review']} "
              f"reject={st['n_rejected']} -> {args.output}")
    else:
        print(json.dumps(res, indent=2))
    return 0


def cmd_review_list(args):
    status, body, _ = _http("GET", f"{args.server}/extract/review/pending?limit={args.limit}")
    _die_on_error(status, body)
    res = json.loads(body)
    for p in res["pending"]:
        alt = f"  (other source: {p['alternative']})" if p.get("alternative") else ""
        print(f"{p.get('claim_id')}  {p.get('field_path') or '-':44s} {str(p.get('value'))[:50]}{alt}")
    print(f"{res['count']} pending", file=sys.stderr)
    return 0


def cmd_review_resolve(args):
    payload = {"action": args.action, "reviewer": args.reviewer, "notes": args.notes or ""}
    if args.action == "edit":
        if not args.claim_json:
            sys.stderr.write("ERROR: --claim-json FILE is required for action=edit\n")
            return 2
        payload["claim"] = json.loads(Path(args.claim_json).read_text(encoding="utf-8"))
    status, body, _ = _http("POST", f"{args.server}/extract/review/{args.claim_id}/resolve", body=payload)
    _die_on_error(status, body)
    print(json.dumps(json.loads(body)))
    return 0


def cmd_ui(args):
    url = f"{args.server}/extract/ui"
    if args.no_open:
        print(url)
    else:
        print(f"Opening {url} in your browser…")
        try:
            webbrowser.open(url)
        except Exception:
            print(f"(browser open failed; navigate manually to: {url})")
    return 0


def cmd_detect(args):
    text = _read_text_source(args)
    status, body, _ = _http("POST", f"{args.server}/extract/detect_doc_type",
                            body={"source_text": text})
    _die_on_error(status, body)
    print(json.dumps(json.loads(body), indent=2))
    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="medai-epi",
        description="Command-line client for the MedAI-EPI research phenotyping service.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "environment:\n"
            "  MEDAI_EPI_URL       default server URL (overridden by --server)\n\n"
            "quick examples:\n"
            "  medai-epi health\n"
            "  medai-epi extract --doc-type progress_note note.txt\n"
            "  medai-epi csv notes.csv -o phenotypes.csv\n"
            "  medai-epi chat --text-file note.txt \"was surgery mentioned?\"\n"
        ),
    )
    p.add_argument("--server", default=DEFAULT_URL,
                    help=f"MedAI-EPI service base URL (default: {DEFAULT_URL})")

    sub = p.add_subparsers(dest="cmd", metavar="COMMAND")
    sub.required = True

    # health
    sp = sub.add_parser("health", help="backend load status + registered prompts")
    sp.set_defaults(func=cmd_health)

    # registry
    sp = sub.add_parser("registry", help="list prompts (or dump one)")
    sp.add_argument("prompt_id", nargs="?", default=None,
                     help="if given, dump that prompt's full definition")
    sp.set_defaults(func=cmd_registry)

    # detect_doc_type
    sp = sub.add_parser("detect", help="heuristic doc-type suggestion for a note")
    sp.add_argument("positional_file", nargs="?", default=None,
                     help="path to note text (or use --text / --text-file)")
    sp.add_argument("--text-file", dest="text_file", default=None)
    sp.add_argument("--text", default=None)
    sp.set_defaults(func=cmd_detect)

    # extract (JSON)
    sp = sub.add_parser("extract", help="single-doc phenotype extraction → JSON")
    sp.add_argument("positional_file", nargs="?", default=None,
                     help="path to note text (or use --text / --text-file)")
    sp.add_argument("--text-file", dest="text_file", default=None)
    sp.add_argument("--text", default=None)
    sp.add_argument("--doc-type", required=True,
                     help="e.g. progress_note / mri_report / eeg_report")
    sp.add_argument("--arm", default="M2", choices=["M0", "M1", "M2"])
    sp.add_argument("--model", default=None,
                     help="med42 (default) / deepseek / openai[:model_id]")
    sp.add_argument("--verify", action="store_true",
                     help="run a verifier pass with --verifier-model")
    sp.add_argument("--verifier-model", default=None,
                     help="e.g. openai:gpt-5.6-terra or deepseek")
    sp.add_argument("--doc-id", default=None)
    sp.add_argument("--patient-id", default=None)
    sp.add_argument("--lora-adapter", dest="lora_adapter", default=None,
                     metavar="DIR",
                     help="path to a PEFT LoRA adapter directory to layer on "
                          "top of the base Med42-8B weights (sets "
                          "MEDAI_LORA_ADAPTER_DIR before the backend loads).")
    sp.set_defaults(func=cmd_extract)

    # csv
    sp = sub.add_parser("csv",
                         help="extract many notes → long-format CSV out")
    sp.add_argument("input_csv", nargs="?", default=None,
                     help="path to a CSV with a text column (positional). "
                          "If omitted, use --text-file / --text for one note.")
    sp.add_argument("--text-file", dest="text_file", default=None)
    sp.add_argument("--text", default=None)
    sp.add_argument("--doc-type", default="progress_note")
    sp.add_argument("--arm", default="M2", choices=["M0", "M1", "M2"])
    sp.add_argument("--doc-id", default=None)
    sp.add_argument("-o", "--output", default=None,
                     help="output CSV path (default: stdout)")
    sp.set_defaults(func=cmd_csv)

    # long (auto-chunk)
    sp = sub.add_parser("long", help="auto-chunk + merge extraction → JSON")
    sp.add_argument("positional_file", nargs="?", default=None)
    sp.add_argument("--text-file", dest="text_file", default=None)
    sp.add_argument("--text", default=None)
    sp.add_argument("--doc-type", required=True)
    sp.add_argument("--arm", default="M2", choices=["M0", "M1", "M2"])
    sp.add_argument("--doc-id", default=None)
    sp.set_defaults(func=cmd_long)

    # chat
    sp = sub.add_parser("chat", help="freeform grounded Q&A on one note")
    sp.add_argument("question", help="the question to ask")
    sp.add_argument("positional_file", nargs="?", default=None)
    sp.add_argument("--text-file", dest="text_file", default=None)
    sp.add_argument("--text", default=None)
    sp.add_argument("--doc-id", default=None)
    sp.add_argument("--json", action="store_true",
                     help="also emit the full JSON body")
    sp.set_defaults(func=cmd_chat)

    # chain (LEO)
    sp = sub.add_parser("chain", help="LEO chain on one note -> claims (ACCEPT/REVIEW/REJECT)")
    sp.add_argument("positional_file", nargs="?", help="note text file")
    sp.add_argument("--text-file")
    sp.add_argument("--text")
    sp.add_argument("--doc-id")
    sp.add_argument("--doc-date")
    sp.add_argument("--no-persist", action="store_true", help="do not write to the evidence ledger")
    sp.add_argument("--output", "-o", help="write claims as JSONL here")
    sp.set_defaults(func=cmd_chain)

    # review queue
    sp = sub.add_parser("review", help="human review queue for REVIEW claims")
    rsub = sp.add_subparsers(dest="review_cmd", required=True)
    rp = rsub.add_parser("list", help="claims awaiting review")
    rp.add_argument("--limit", type=int, default=100)
    rp.set_defaults(func=cmd_review_list)
    rp = rsub.add_parser("resolve", help="accept_as_is | edit | reject one claim")
    rp.add_argument("claim_id")
    rp.add_argument("action", choices=["accept_as_is", "edit", "reject"])
    rp.add_argument("--reviewer", default="cli")
    rp.add_argument("--notes")
    rp.add_argument("--claim-json", help="full Claim JSON file (action=edit)")
    rp.set_defaults(func=cmd_review_resolve)

    # ui
    sp = sub.add_parser("ui", help="open the /extract/ui browser page")
    sp.add_argument("--no-open", action="store_true",
                     help="print URL instead of opening browser")
    sp.set_defaults(func=cmd_ui)

    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
