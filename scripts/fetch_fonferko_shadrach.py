#!/usr/bin/env python3
"""Fetch the Fonferko-Shadrach 2024 synthetic epilepsy clinic-letter corpus from Zenodo.

Paper: Fonferko-Shadrach B et al. (2024). Annotation of epilepsy clinic letters
       for natural language processing. J Biomed Semantics 15:17.
       DOI: 10.1186/s13326-024-00316-z ; PMCID: PMC11402197.

Four Zenodo deposits (all synthetic, no PHI, CC-BY 4.0):

  8381080  — 200 gold-standard letters + Markup annotations (spelling corrected)
  8356494  — Gold JSON annotations
  8382589  — Annotation guidelines
  12520180 — Per-entity-type CSV annotation outputs

Output layout:
  data/fonferko_shadrach_2024/
    manifest.json                 — DOIs, licenses, checksums, file layout
    zenodo_8381080/               — corpus zip contents (letters + .ann files)
    zenodo_8356494/               — JSON annotation files
    zenodo_8382589/               — annotation guidelines
    zenodo_12520180/              — CSV entity-type outputs
    _downloads/*.zip              — raw downloads, checksum-verified
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

UA = "MedAI-EPI corpus-ingestion (research use; contact via project maintainer)"
ROOT = Path(__file__).resolve().parent.parent / "data" / "fonferko_shadrach_2024"
DOWNLOADS = ROOT / "_downloads"

# (record_id, expected subdir name, human-readable description)
RECORDS: tuple[tuple[str, str, str], ...] = (
    ("8381080",  "zenodo_8381080",  "Gold-standard letters + Markup .ann annotations"),
    ("8356494",  "zenodo_8356494",  "Gold JSON annotations"),
    ("8382589",  "zenodo_8382589",  "Annotation guidelines"),
    ("12520180", "zenodo_12520180", "Per-entity-type CSV outputs"),
)


def _fetch(url: str, dest: Path, expected_md5: str | None = None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    with urllib.request.urlopen(req, timeout=60) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    if expected_md5:
        digest = hashlib.md5(tmp.read_bytes()).hexdigest()
        if digest != expected_md5:
            tmp.unlink(missing_ok=True)
            raise ValueError(
                f"checksum mismatch for {dest.name}: expected {expected_md5}, got {digest}"
            )
    tmp.replace(dest)


def _api_record(record_id: str) -> dict:
    url = f"https://zenodo.org/api/records/{record_id}"
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30
    ) as r:
        return json.load(r)


def _extract_zip_safely(zip_path: Path, out_dir: Path) -> list[str]:
    """Extract a zip file, refusing path-traversal entries. Returns list of members."""
    out_dir.mkdir(parents=True, exist_ok=True)
    members: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            # reject absolute paths and .. traversal
            if name.startswith("/") or ".." in Path(name).parts:
                raise ValueError(f"unsafe path in zip: {name!r}")
            members.append(name)
        zf.extractall(out_dir)
    return members


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    DOWNLOADS.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []
    for record_id, subdir, description in RECORDS:
        print(f"\n=== Zenodo record {record_id} — {description} ===")
        try:
            meta = _api_record(record_id)
        except Exception as e:
            print(f"[error] Zenodo API {record_id}: {e}", file=sys.stderr)
            return 2

        rec_entry: dict = {
            "record_id": record_id,
            "doi": meta["doi"],
            "title": meta["metadata"]["title"],
            "license": (meta["metadata"].get("license") or {}).get("id", "unspecified"),
            "record_url": f"https://zenodo.org/records/{record_id}",
            "publication_date": meta["metadata"].get("publication_date"),
            "description": description,
            "files": [],
            "extracted_into": str((ROOT / subdir).relative_to(ROOT.parent.parent)),
        }
        (ROOT / subdir).mkdir(parents=True, exist_ok=True)

        for f in meta.get("files", []):
            key = f["key"]
            size = f["size"]
            checksum_full = f["checksum"]                 # "md5:hex"
            expected_md5 = checksum_full.split(":", 1)[1] if ":" in checksum_full else None
            download_url = f.get("links", {}).get("self") \
                or f"https://zenodo.org/records/{record_id}/files/{key}"

            local = DOWNLOADS / f"zenodo_{record_id}__{key}"
            if local.exists() and local.stat().st_size == size:
                print(f"  [cached] {key} ({size:,} bytes)")
            else:
                print(f"  [download] {key} ({size:,} bytes) ...")
                _fetch(download_url, local, expected_md5=expected_md5)
                print(f"    md5 OK: {expected_md5}")

            entry: dict = {
                "key": key, "size": size, "md5": expected_md5,
                "raw_path": str(local.relative_to(ROOT.parent.parent)),
            }
            # Extract zips into the record subdir
            if key.lower().endswith(".zip"):
                try:
                    members = _extract_zip_safely(local, ROOT / subdir)
                    entry["extracted_members"] = len(members)
                    print(f"    extracted {len(members)} members → {subdir}/")
                except Exception as e:
                    entry["extract_error"] = str(e)
                    print(f"    [warn] extract failed: {e}")
            rec_entry["files"].append(entry)
            time.sleep(0.5)   # be polite

        manifest.append(rec_entry)

    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nmanifest → {ROOT / 'manifest.json'}")

    # Summary
    print("\n=== SUMMARY ===")
    for rec in manifest:
        print(f"{rec['record_id']:>9}  {rec['license']:<10}  "
              f"files={len(rec['files']):<2}  {rec['title'][:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
