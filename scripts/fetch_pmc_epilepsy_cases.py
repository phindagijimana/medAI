#!/usr/bin/env python3
"""Fetch diverse open-access epilepsy case reports from PubMed Central.

Uses NCBI E-utilities (esearch + efetch). Only articles in the PMC OA subset
are kept. Text is extracted from <article-title>, <abstract>, and <body>/<sec>
elements. Images/tables/references are ignored.

Output:
  data/pmc_cases/PMC<id>.txt   — one plain-text case per file, with a header
  data/pmc_cases/manifest.json — provenance for every case

Attribution is preserved in each file header and the manifest so downstream
use can cite the original article.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
UA = "MedAI-EPI schema-stress-test (research; contact via project maintainer)"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "pmc_cases"

# Diversity: several narrow queries beat one broad query for varied content.
# Each is combined with a PMC-OA filter and Case Reports publication type.
QUERIES = [
    'temporal lobe epilepsy AND "Case Reports"[Publication Type]',
    'frontal lobe epilepsy AND "Case Reports"[Publication Type]',
    'focal cortical dysplasia AND "Case Reports"[Publication Type]',
    'hippocampal sclerosis AND epilepsy AND "Case Reports"[Publication Type]',
    'drug resistant epilepsy AND "Case Reports"[Publication Type]',
    'juvenile myoclonic epilepsy AND "Case Reports"[Publication Type]',
    'Lennox-Gastaut AND "Case Reports"[Publication Type]',
    'MRI negative epilepsy AND "Case Reports"[Publication Type]',
]

PER_QUERY = 6            # fetch up to N candidates per query
TARGET_TOTAL = 20        # keep at most this many across all queries
MIN_BODY_CHARS = 1200    # skip letters/editorials
MAX_BODY_CHARS = 25000   # keep prompt-tractable
POLITE_DELAY_S = 0.35    # ~3 req/s (NCBI limit without API key)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def esearch(query: str, retmax: int) -> list[str]:
    q = urllib.parse.urlencode({
        "db": "pmc",
        "term": f"({query}) AND open access[filter]",
        "retmax": retmax,
        "retmode": "json",
        "sort": "relevance",
    })
    data = json.loads(_fetch(f"{EUTILS}/esearch.fcgi?{q}"))
    return data.get("esearchresult", {}).get("idlist", [])


def efetch_xml(pmcid: str) -> bytes:
    q = urllib.parse.urlencode({"db": "pmc", "id": pmcid, "rettype": "xml"})
    return _fetch(f"{EUTILS}/efetch.fcgi?{q}")


def _text_join(elem) -> str:
    """Recursive text extraction skipping formulas, xrefs, tables, figures."""
    if elem is None:
        return ""
    skip_tags = {"table-wrap", "fig", "graphic", "media", "inline-formula",
                 "disp-formula", "xref", "ref", "ref-list", "back"}
    out: list[str] = []
    if elem.tag not in skip_tags:
        if elem.text:
            out.append(elem.text)
        for child in elem:
            if child.tag in skip_tags:
                if child.tail:
                    out.append(child.tail)
                continue
            out.append(_text_join(child))
            if child.tail:
                out.append(child.tail)
    return "".join(out)


def _norm_ws(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n[ \t]+", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def parse_article(xml_bytes: bytes) -> dict | None:
    """Return dict with metadata + concatenated case-report text, or None if
    the article is not usable (unparseable, no body, wrong license, or an
    'article-set' with multiple articles)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    # NCBI wraps single-article efetches inside <pmc-articleset>
    articles = root.findall(".//article")
    if not articles:
        return None
    a = articles[0]

    # Metadata
    def _first_text(xpath: str) -> str:
        el = a.find(xpath)
        return _norm_ws(_text_join(el)) if el is not None else ""

    pmcid = ""
    for aid in a.findall(".//article-id"):
        if aid.get("pub-id-type") == "pmc":
            pmcid = "PMC" + (aid.text or "").strip()
            break

    # License check — keep only clearly-open licenses
    license_type = ""
    lic = a.find(".//license")
    if lic is not None:
        license_type = (lic.get("license-type")
                        or lic.get("{http://www.w3.org/1999/xlink}href")
                        or "unspecified")
    lic_paragraph = _norm_ws(_text_join(a.find(".//license"))) if a.find(".//license") is not None else ""

    title = _first_text(".//article-title")
    journal = _first_text(".//journal-title")
    year = _first_text(".//pub-date/year")
    doi = ""
    for aid in a.findall(".//article-id"):
        if aid.get("pub-id-type") == "doi":
            doi = (aid.text or "").strip()
            break

    # Abstract
    abstract_parts: list[str] = []
    for ab in a.findall(".//abstract"):
        abstract_parts.append(_text_join(ab))
    abstract = _norm_ws("\n".join(abstract_parts))

    # Body — sections
    body = a.find(".//body")
    if body is None:
        return None
    sections: list[str] = []
    for sec in body.findall(".//sec"):
        title_el = sec.find("./title")
        sec_title = _norm_ws(_text_join(title_el))
        sec_body = _norm_ws(_text_join(sec))
        if sec_title and sec_body.lower().startswith(sec_title.lower()):
            sec_text = sec_body
        else:
            sec_text = f"{sec_title}\n{sec_body}" if sec_title else sec_body
        if sec_text.strip():
            sections.append(sec_text.strip())
    body_text = _norm_ws("\n\n".join(sections))
    if not body_text:
        # Some articles put text directly under <body> without <sec>
        body_text = _norm_ws(_text_join(body))

    return {
        "pmcid": pmcid,
        "title": title,
        "journal": journal,
        "year": year,
        "doi": doi,
        "license_type": license_type,
        "license_paragraph": lic_paragraph,
        "abstract": abstract,
        "body_text": body_text,
        "body_chars": len(body_text),
    }


def is_case_report(record: dict) -> bool:
    """Heuristic: reject non-case content that slipped past the Publication Type filter."""
    body = record["body_text"].lower()
    title = (record.get("title") or "").lower()
    if record["body_chars"] < MIN_BODY_CHARS:
        return False

    # Title-level rejections (systematic reviews, drug-discovery, animal work,
    # case-control / case-series analytic studies)
    title_reject = [
        "review:", "systematic review", "meta-analysis",
        "case-control", "case control study",
        "worldwide case series", "case series of",
        "discovery of", "development of",
    ]
    if any(s in title for s in title_reject):
        return False

    # Body-level rejections
    body_reject = [
        "systematic review", "meta-analysis", "we conducted a review",
        "prisma", "inclusion criteria were",
        "in this review",
    ]
    if any(s in body for s in body_reject):
        return False

    # Species check — exclude non-human veterinary case reports
    species_reject = [
        "rhodesian ridgeback", "canine", "in dogs", "feline", "in cats",
        "veterinary", "mouse model", "murine model",
    ]
    if any(s in body for s in species_reject) and "human" not in body[:2000]:
        return False

    # Positive case-report signals
    case_signals = ["case report", "case presentation", "we present", "we describe",
                    "year-old", "years old", "presented with", "admitted"]
    return any(s in body for s in case_signals)


def looks_openly_licensed(record: dict) -> bool:
    lt = (record["license_type"] or "").lower()
    if lt.startswith("cc") or "creative commons" in lt or "open-access" in lt:
        return True
    lp = (record["license_paragraph"] or "").lower()
    return "creative commons" in lp or "cc-by" in lp or "cc by" in lp


def _slug_header(record: dict, query: str) -> str:
    return (
        f"# Source: {record['pmcid']}\n"
        f"# Title: {record['title']}\n"
        f"# Journal: {record['journal']} ({record['year']})\n"
        f"# DOI: {record['doi']}\n"
        f"# License: {record['license_type']}\n"
        f"# Fetched via query: {query}\n"
        f"# URL: https://www.ncbi.nlm.nih.gov/pmc/articles/{record['pmcid']}/\n"
        "# ---\n"
    )


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    kept: dict[str, dict] = {}
    per_query_counts: dict[str, int] = {}

    for query in QUERIES:
        if len(kept) >= TARGET_TOTAL:
            break
        try:
            ids = esearch(query, PER_QUERY)
        except Exception as e:
            print(f"[warn] esearch failed for {query!r}: {e}", file=sys.stderr)
            continue
        per_query_counts[query] = 0
        for pmc_num in ids:
            if len(kept) >= TARGET_TOTAL:
                break
            pmcid_key = "PMC" + pmc_num
            if pmcid_key in kept:
                continue
            time.sleep(POLITE_DELAY_S)
            try:
                xml = efetch_xml(pmc_num)
            except Exception as e:
                print(f"[warn] efetch failed for {pmcid_key}: {e}", file=sys.stderr)
                continue
            rec = parse_article(xml)
            if rec is None:
                continue
            if not looks_openly_licensed(rec):
                continue
            if not is_case_report(rec):
                continue
            if rec["body_chars"] > MAX_BODY_CHARS:
                # Truncate on a sentence boundary — keep header intact
                cut = rec["body_text"][:MAX_BODY_CHARS]
                cut = cut[: cut.rfind(". ") + 1] if ". " in cut else cut
                rec["body_text"] = cut + "\n\n[Truncated for stress-test length limits.]"
                rec["body_chars"] = len(rec["body_text"])
            rec["_query"] = query
            rec["pmcid"] = pmcid_key  # authoritative id from esearch
            kept[pmcid_key] = rec
            per_query_counts[query] += 1
            print(f"kept {pmcid_key}  chars={rec['body_chars']:>6}  query={query[:40]}…")

    # Write files
    manifest = []
    for pmcid, rec in kept.items():
        path = OUT_DIR / f"{pmcid}.txt"
        header = _slug_header(rec, rec["_query"])
        text = header
        if rec["abstract"]:
            text += "\n## Abstract\n\n" + rec["abstract"] + "\n\n"
        text += "## Body\n\n" + rec["body_text"] + "\n"
        path.write_text(text, encoding="utf-8")
        manifest.append({
            "pmcid": pmcid,
            "title": rec["title"],
            "journal": rec["journal"],
            "year": rec["year"],
            "doi": rec["doi"],
            "license_type": rec["license_type"],
            "query": rec["_query"],
            "body_chars": rec["body_chars"],
            "path": str(path.relative_to(OUT_DIR.parent.parent)),
        })

    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\n--- Summary ---")
    print(f"Total cases kept: {len(kept)}")
    for q, n in per_query_counts.items():
        print(f"  {n:>2} × {q}")
    print(f"Output: {OUT_DIR}")
    return 0 if kept else 1


if __name__ == "__main__":
    sys.exit(main())
