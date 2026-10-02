#!/usr/bin/env python3
"""Download and pin ontology releases into data/ontologies/.

Sources:
    hpo      — Human Phenotype Ontology (hp.obo), GitHub latest release
    mondo    — MONDO disease ontology (mondo.obo), OBO PURL
    epio     — Epilepsy Ontology (EPIO_merged.owl), pinned to a git commit
    rxnorm   — RxNorm Full Monthly Release (UMLS licence, via UTS API)
    snomed   — SNOMED CT US Edition (UMLS licence, via UTS API)

Each file is stored under a versioned name and recorded in
data/ontologies/MANIFEST.json with its release, source URL and SHA-256.
Licensed content (RxNorm, SNOMED CT) must never be committed or shared;
data/ontologies/ is gitignored apart from the manifest.

Requires UMLS_APIKEY in the environment or .env for rxnorm / snomed.

Usage:
    venv/bin/python scripts/fetch_ontologies.py                 # all sources
    venv/bin/python scripts/fetch_ontologies.py --only hpo,mondo
    venv/bin/python scripts/fetch_ontologies.py --force         # re-download
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ONTO_DIR = REPO / "data" / "ontologies"
MANIFEST = ONTO_DIR / "MANIFEST.json"

HPO_URL = "https://github.com/obophenotype/human-phenotype-ontology/releases/latest/download/hp.obo"
MONDO_URL = "http://purl.obolibrary.org/obo/mondo.obo"
EPIO_REPO = "SCAI-BIO/EpilepsyOntology"
EPIO_PATH = "release/EPIO_merged.owl"
UTS_RELEASES = "https://uts-ws.nlm.nih.gov/releases?releaseType={}&current=true"
UTS_DOWNLOAD = "https://uts-ws.nlm.nih.gov/download"

ALL_SOURCES = ["hpo", "mondo", "epio", "rxnorm", "snomed"]


def _load_dotenv() -> None:
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "medai-epi-ontology-fetch"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _download(url: str, dest: Path, *, label: str) -> None:
    """Stream url → dest via a .part file. `label` is what gets logged (never the URL)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "medai-epi-ontology-fetch"})
    with urllib.request.urlopen(req, timeout=600) as r, tmp.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        next_report = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total and done >= next_report:
                print(f"  [{label}] {done / 1e6:.0f} / {total / 1e6:.0f} MB", flush=True)
                next_report += max(total // 10, 1)
    tmp.replace(dest)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _obo_data_version(path: Path) -> str:
    """Return the YYYY-MM-DD release from an OBO header's data-version line."""
    with path.open(encoding="utf-8") as f:
        for _ in range(50):
            line = f.readline()
            if line.startswith("data-version:"):
                m = re.search(r"(\d{4}-\d{2}-\d{2})", line)
                if m:
                    return m.group(1)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ─── Sources ─────────────────────────────────────────────────────────────

def fetch_obo(name: str, url: str, force: bool) -> dict:
    out_dir = ONTO_DIR / name
    tmp = out_dir / f"{name}.download.obo"
    _download(url, tmp, label=name)
    release = _obo_data_version(tmp)
    final = out_dir / f"{name}-{release}.obo"
    if final.exists() and not force:
        tmp.unlink()
        print(f"  [{name}] {final.name} already present")
    else:
        tmp.replace(final)
    return {"release": release, "source_url": url, "files": [final]}


def fetch_epio(force: bool) -> dict:
    sha = _get_json(f"https://api.github.com/repos/{EPIO_REPO}/commits/main")["sha"]
    url = f"https://raw.githubusercontent.com/{EPIO_REPO}/{sha}/{EPIO_PATH}"
    final = ONTO_DIR / "epio" / f"EPIO_merged-{sha[:12]}.owl"
    if final.exists() and not force:
        print(f"  [epio] {final.name} already present")
    else:
        _download(url, final, label="epio")
    return {"release": f"git:{sha}", "source_url": url, "files": [final]}


def fetch_uts(name: str, release_type: str, api_key: str, force: bool) -> dict:
    rel = _get_json(UTS_RELEASES.format(release_type))[0]
    out_dir = ONTO_DIR / name
    zpath = out_dir / rel["fileName"]
    if zpath.exists() and not force:
        print(f"  [{name}] {zpath.name} already present")
    else:
        q = urllib.parse.urlencode({"url": rel["downloadUrl"], "apiKey": api_key})
        _download(f"{UTS_DOWNLOAD}?{q}", zpath, label=name)
    if not zipfile.is_zipfile(zpath):
        head = zpath.read_bytes()[:300].decode("utf-8", "replace")
        zpath.unlink()
        raise RuntimeError(f"{name}: UTS did not return a zip (check licence/API key). Response starts: {head!r}")

    extract_dir = out_dir / zpath.stem
    if force and extract_dir.exists():
        shutil.rmtree(extract_dir)
    if not extract_dir.exists():
        print(f"  [{name}] extracting → {extract_dir.relative_to(REPO)}")
        with zipfile.ZipFile(zpath) as z:
            z.extractall(extract_dir)
    return {
        "release": rel["releaseVersion"],
        "source_url": rel["downloadUrl"],
        "files": [zpath],
        "extracted_to": str(extract_dir.relative_to(REPO)),
        "licence": "UMLS Metathesaurus License — do not redistribute",
    }


# ─── Main ────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=",".join(ALL_SOURCES), help=f"Comma-separated subset of {ALL_SOURCES}")
    ap.add_argument("--force", action="store_true", help="Re-download even if the pinned file exists")
    args = ap.parse_args()

    wanted = [s.strip() for s in args.only.split(",") if s.strip()]
    unknown = set(wanted) - set(ALL_SOURCES)
    if unknown:
        raise SystemExit(f"Unknown sources: {sorted(unknown)}")

    _load_dotenv()
    api_key = os.environ.get("UMLS_APIKEY", "")
    if {"rxnorm", "snomed"} & set(wanted) and not api_key:
        raise SystemExit("UMLS_APIKEY not set (needed for rxnorm / snomed)")

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    failures = []
    for name in wanted:
        print(f"== {name}", flush=True)
        try:
            if name == "hpo":
                entry = fetch_obo("hpo", HPO_URL, args.force)
            elif name == "mondo":
                entry = fetch_obo("mondo", MONDO_URL, args.force)
            elif name == "epio":
                entry = fetch_epio(args.force)
            elif name == "rxnorm":
                entry = fetch_uts("rxnorm", "rxnorm-full-monthly-release", api_key, args.force)
            else:
                entry = fetch_uts("snomed", "snomed-ct-us-edition", api_key, args.force)
        except Exception as e:
            print(f"  [{name}] FAILED: {e}", file=sys.stderr)
            failures.append(name)
            continue

        entry["files"] = [
            {"path": str(p.relative_to(REPO)), "sha256": _sha256(p), "bytes": p.stat().st_size}
            for p in entry["files"]
        ]
        entry["fetched_at"] = datetime.now(timezone.utc).isoformat()
        manifest[name] = entry
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"  [{name}] release {entry['release']} OK", flush=True)

    print(f"\nManifest: {MANIFEST.relative_to(REPO)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
