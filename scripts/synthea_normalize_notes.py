"""Convert Synthea's structured EHR-list notes into narrative sentences.

Synthea's per-encounter text export uses date-headed structured lists:
    2004-11-13 : History of seizure (situation)
    2006-10-06 : Epilepsy (disorder)
    2006-05-09 + carbamazepine 20 MG/ML Oral Suspension [Tegretol] for Seizure disorder (disorder)

Our extractor is tuned for narrative prose. This normalizer emits a
compact prose version:
    "The patient has a history of seizure since 2004. Epilepsy was
    diagnosed in 2006. The patient was started on carbamazepine
    (Tegretol) in 2006 for seizure disorder."

Preserves original filename → produces {stem}.txt in output dir.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Patterns for structured list items
RE_CONDITION_LINE = re.compile(
    r"^\s*(\d{4})-\d{2}-\d{2}\s*:\s*(.+?)\s*(?:\([^)]+\))?\s*$"
)
RE_MEDICATION_LINE = re.compile(
    r"^\s*(\d{4})-\d{2}-\d{2}\s*\+\s*(.+?)(?:\s+for\s+.+)?\s*$"
)
RE_HEADER = re.compile(r"^\s*(CONDITIONS|MEDICATIONS|CARE PLANS|REPORTS|ALLERGIES|PROCEDURES|IMMUNIZATIONS):\s*$")


def _clean_desc(desc: str) -> str:
    """Strip parenthetical type qualifiers and drug-strength boilerplate."""
    # Remove parenthetical qualifiers
    desc = re.sub(r"\s*\([^)]+\)\s*$", "", desc)
    # Remove drug strength like "20 MG/ML Oral Suspension [Tegretol]"
    desc = re.sub(r"\s+\d+\s*MG.*?(?:\[|$)", " ", desc)
    desc = re.sub(r"\s*\[.*?\]\s*", " ", desc)
    return desc.strip()


def normalize(raw: str) -> str:
    """Return a narrative prose version of the Synthea note."""
    lines = raw.splitlines()
    section = None
    conditions = []
    medications = []
    header_info = []

    # Extract patient header (first ~9 lines)
    for i, line in enumerate(lines[:12]):
        if "Age:" in line or "Gender:" in line or "Race:" in line:
            header_info.append(line.strip())
        if line.startswith("---") or line.startswith("==="):
            continue

    for line in lines:
        h = RE_HEADER.match(line)
        if h:
            section = h.group(1)
            continue
        if line.strip().startswith("---") or line.strip().startswith("==="):
            section = None
            continue

        if section == "CONDITIONS":
            m = RE_CONDITION_LINE.match(line)
            if m:
                year, desc = m.group(1), _clean_desc(m.group(2))
                if desc and desc.lower() not in ("", "n/a"):
                    conditions.append((year, desc))
        elif section == "MEDICATIONS":
            m = RE_MEDICATION_LINE.match(line)
            if m:
                year, desc = m.group(1), _clean_desc(m.group(2))
                if desc and desc.lower() not in ("", "n/a"):
                    medications.append((year, desc))

    # Emit narrative
    parts = []
    if header_info:
        parts.append("Patient demographics: " + "; ".join(header_info) + ".")
    # Group conditions by prose
    epi_conds = [(y, d) for y, d in conditions
                 if re.search(r"epilep|seizur|convuls", d, re.IGNORECASE)]
    other_conds = [(y, d) for y, d in conditions if (y, d) not in epi_conds]

    if epi_conds:
        parts.append("History of Present Illness: The patient has a history of the following seizure/epilepsy-related conditions:")
        for year, desc in epi_conds:
            parts.append(f" {desc.capitalize()} was documented in {year}.")

    if medications:
        parts.append("\nMedications: The patient's medication history includes:")
        for year, desc in medications:
            parts.append(f" {desc.capitalize()} was started in {year}.")

    if other_conds and len(other_conds) < 20:
        parts.append("\nPast Medical History (other): " + "; ".join(
            f"{d} ({y})" for y, d in other_conds[:20]) + ".")

    return " ".join(parts) if parts else raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    in_dir = REPO_ROOT / args.in_dir
    out_dir = REPO_ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    n_ok = 0
    for p in sorted(in_dir.glob("*.txt")):
        raw = p.read_text(encoding="utf-8", errors="replace")
        norm = normalize(raw)
        (out_dir / p.name).write_text(norm)
        n_ok += 1
    print(f"[normalize] Wrote {n_ok} narrativized Synthea notes to {out_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
