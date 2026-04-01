#!/usr/bin/env python3
"""
Build neurology-only CSVs from the MIMIC-IV Clinical Database *Demo* (PhysioNet).

Downloads the official gzipped hosp tables (no credentialing required), applies an
ICD-based neurology filter, and writes ONLY neurology subset files next to this script.

Neurology filter (testing / pipeline use, not a validated clinical cohort):
  ICD-10-CM: G* (nervous system); I60–I69 (cerebrovascular); R56 (convulsions).
  ICD-9-CM: 3-digit categories 320–389.

Source: https://physionet.org/content/mimiciv-demo/2.2/

Outputs:
  neurology_diagnoses.csv
  neurology_admissions.csv
  neurology_patients.csv
  neurology_hadm_ids.txt

Usage: python3 build_neurology_subset.py
"""
from __future__ import annotations

import csv
import gzip
import io
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
PHYSIONET_HOSP = "https://physionet.org/files/mimic-iv-demo/2.2/hosp"


def fetch_gz_csv(name: str) -> list[dict[str, str]]:
    url = f"{PHYSIONET_HOSP}/{name}.csv.gz"
    print(f"Fetching {url} ...", file=sys.stderr)
    with urllib.request.urlopen(url, timeout=120) as resp:
        raw = resp.read()
    text = gzip.decompress(raw).decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def is_neurology_row(icd_code: str, icd_version: str) -> bool:
    c = (icd_code or "").strip().upper().replace(".", "")
    if not c:
        return False
    v = str(icd_version).strip()
    if v == "10":
        if c.startswith("G"):
            return True
        if len(c) >= 3 and c[0] == "I" and c[1] == "6" and c[2] in "0123456789":
            return True
        if c.startswith("R56"):
            return True
        return False
    if v == "9":
        if not c.isdigit():
            return False
        prefix = int(c[:3]) if len(c) >= 3 else int(c)
        return 320 <= prefix <= 389
    return False


def main() -> None:
    diag_rows = fetch_gz_csv("diagnoses_icd")
    adm_rows = fetch_gz_csv("admissions")
    pat_rows = fetch_gz_csv("patients")

    rows_out: list[dict] = []
    hadm_ids: set[str] = set()

    for row in diag_rows:
        if is_neurology_row(row.get("icd_code", ""), row.get("icd_version", "")):
            rows_out.append(row)
            hid = row.get("hadm_id")
            if hid is not None:
                hadm_ids.add(str(hid))

    if not rows_out:
        raise SystemExit("No neurology-coded rows; check filter or download.")

    fieldnames = list(rows_out[0].keys())
    out_diag = HERE / "neurology_diagnoses.csv"
    with open(out_diag, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    adm_keep = [r for r in adm_rows if str(r.get("hadm_id", "")) in hadm_ids]
    subject_ids = {str(r["subject_id"]) for r in adm_keep if r.get("subject_id") is not None}

    af = list(adm_rows[0].keys()) if adm_rows else []
    out_adm = HERE / "neurology_admissions.csv"
    with open(out_adm, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=af)
        w.writeheader()
        w.writerows(adm_keep)

    pat_keep = [r for r in pat_rows if str(r.get("subject_id", "")) in subject_ids]
    pf = list(pat_rows[0].keys()) if pat_rows else []
    out_pat = HERE / "neurology_patients.csv"
    with open(out_pat, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=pf)
        w.writeheader()
        w.writerows(pat_keep)

    out_ids = HERE / "neurology_hadm_ids.txt"
    with open(out_ids, "w", encoding="utf-8") as f:
        for hid in sorted(hadm_ids, key=lambda x: int(x) if x.isdigit() else x):
            f.write(f"{hid}\n")

    print(f"Wrote {len(rows_out)} diagnosis rows -> {out_diag.name}", file=sys.stderr)
    print(f"Wrote {len(adm_keep)} admission rows -> {out_adm.name}", file=sys.stderr)
    print(f"Wrote {len(pat_keep)} patient rows -> {out_pat.name}", file=sys.stderr)
    print(f"Unique neurology admissions: {len(hadm_ids)} -> {out_ids.name}", file=sys.stderr)


if __name__ == "__main__":
    main()
