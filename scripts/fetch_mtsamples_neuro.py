"""Fetch MTSamples neurology corpus for Phase 6b evaluation.

Scrapes https://www.mtsamples.com/site/pages/browse.asp?Type=42-Neurology
(226 samples as of 2026-09), extracts the sample body from each linked
detail page, filters for epilepsy/seizure keywords, and stores kept notes
under ``data/eval_corpora/mtsamples_neuro/``.

Politeness
----------
- robots.txt allows all crawlers (verified 2026-09-29; site returns
  ``User-agent: *  Disallow:``).
- 2 second minimum delay between HTTP requests (`--delay 2.0`).
- Local disk cache at
  ``data/eval_corpora/mtsamples_neuro/.cache/`` — reruns short-circuit
  every URL already fetched. Delete a cache file to force re-fetch.
- User-Agent identifies the project + contact for site admin.

Output layout
-------------
    data/eval_corpora/mtsamples_neuro/
        .cache/<sha1>.html            # raw HTML, one per URL
        mt_sample_0001/
            note.txt                  # extracted body text
            metadata.json             # {source_url, sample_id, title,
                                      #  specialty, fetch_date, keyword_matches}
        mt_sample_0002/
            ...
        README.md
        manifest.csv                  # id, source_url, char_count,
                                      # epilepsy_keyword_match, keywords

Usage
-----
    venv-medcat/bin/python scripts/fetch_mtsamples_neuro.py --limit 100

Attribution / ToS
-----------------
MTSamples has no explicit LICENSE. Notes are educational transcription
samples ("this is not medical advice"). We store them locally for
research-only NLP evaluation; the corpus directory is gitignored.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = REPO_ROOT / "data" / "eval_corpora" / "mtsamples_neuro"
CACHE_DIR = OUT_ROOT / ".cache"

BASE = "https://www.mtsamples.com"
INDEX_URL = f"{BASE}/site/pages/browse.asp?Type=42-Neurology"
ROBOTS_URL = f"{BASE}/robots.txt"

USER_AGENT = (
    "MedAI-EPI-research/0.1 (academic epilepsy NLP eval; "
    "contact phindagiji@gmail.com)"
)

# Epilepsy keyword filter. Case-insensitive; word-boundary anchored to
# avoid false positives (e.g. "MRI brain" matches only when both words
# present near each other — we do a phrase check).
EPI_KEYWORDS = [
    r"\bseizure(s|d)?\b",
    r"\bepilep(sy|tic|siform)\b",
    r"\bEEG\b",
    r"\bMRI\s+brain\b",
    r"\bneurology\s+consult\b",
    r"\banti[- ]?convulsant\b",
    r"\bpostictal\b",
    r"\bconvulsion(s)?\b",
]
EPI_RE = re.compile("|".join(EPI_KEYWORDS), re.IGNORECASE)


# --------------------------------------------------------------------------
# HTTP + cache
# --------------------------------------------------------------------------

def _cache_key(url: str) -> Path:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{h}.html"


def fetch(url: str, session: requests.Session, delay: float,
          last_fetch: list[float]) -> str:
    """Fetch a URL with disk cache + rate limit. `last_fetch` is a
    one-element list holding the wall-clock time of the previous
    network fetch (0 on first call), so we can sleep the difference."""
    cache = _cache_key(url)
    if cache.exists():
        return cache.read_text()

    # Rate-limit: at least `delay` seconds between network calls.
    now = time.monotonic()
    if last_fetch[0] > 0:
        elapsed = now - last_fetch[0]
        if elapsed < delay:
            time.sleep(delay - elapsed)

    r = session.get(url, timeout=20)
    last_fetch[0] = time.monotonic()
    r.raise_for_status()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(r.text)
    return r.text


# --------------------------------------------------------------------------
# HTML parsing
# --------------------------------------------------------------------------

def extract_sample_links(index_html: str) -> list[dict]:
    """Return [{url, sample_id, title}, ...] parsed from the neurology
    browse-page HTML. Deduplicates by numeric `sample_id` (the same sample
    appears twice on the index with slightly different URL encodings —
    `%2D` vs `-`, `%2520` vs `%20`, etc.).
    """
    seen_urls: set[str] = set()
    seen_ids: set[str] = set()
    out: list[dict] = []
    for m in re.finditer(
        r'href=["\']'
        r'(https?://www\.mtsamples\.com/site/pages/sample\.asp\?Type=42-Neurology&Sample=([^"\']+))'
        r'["\']',
        index_html,
    ):
        url = unescape(m.group(1))
        raw = unescape(m.group(2))
        if url in seen_urls:
            continue
        seen_urls.add(url)
        # sample string is "<id>-<title>" (id numeric, title may contain
        # spaces, punctuation, URL-encoded chars).
        id_match = re.match(r"(\d+)-?(.*)", raw)
        if id_match:
            sample_id = id_match.group(1)
            title = id_match.group(2).strip().replace("+", " ")
        else:
            sample_id = hashlib.sha1(raw.encode()).hexdigest()[:8]
            title = raw
        if sample_id in seen_ids:
            continue
        seen_ids.add(sample_id)
        out.append({"url": url, "sample_id": sample_id, "title": title})
    return out


# Sample body sits between the LAST `<hr />` before the "About This Sample"
# banner and the banner itself. Some samples start with `<B>...`, others with
# plain text — we don't assume a leading tag.
BODY_RE = re.compile(
    r"<hr\s*/?>\s*(.*?)<!--\s*About This Sample",
    re.S,
)
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.S | re.I)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_ADSENSE_RE = re.compile(r"\(adsbygoogle\s*=.*?push\(\{\}\);", re.S)
_MULTI_BLANK = re.compile(r"\n\s*\n\s*\n+")


def extract_body(sample_html: str) -> str | None:
    """Return the sample-body plain text, or None if not parseable."""
    m = BODY_RE.search(sample_html)
    if not m:
        return None
    body_html = m.group(1)
    body_html = _SCRIPT_RE.sub("", body_html)
    body_html = _STYLE_RE.sub("", body_html)
    # Preserve line structure — insert newlines at <br>, </p>, </div>.
    body_html = re.sub(r"<br\s*/?>", "\n", body_html, flags=re.I)
    body_html = re.sub(r"</p>", "\n\n", body_html, flags=re.I)
    body_html = re.sub(r"</div>", "\n", body_html, flags=re.I)
    text = _TAG_RE.sub("", body_html)
    text = unescape(text)
    text = _ADSENSE_RE.sub("", text)
    text = _MULTI_BLANK.sub("\n\n", text).strip()
    return text or None


def keyword_matches(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in EPI_RE.finditer(text)})


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def _check_robots(session: requests.Session) -> None:
    try:
        r = session.get(ROBOTS_URL, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[fetch] WARN: could not check robots.txt ({e}); "
              "proceeding respectfully anyway.")
        return
    body = r.text.lower()
    if "user-agent: *" in body and "disallow:" in body:
        # Look for a "Disallow: /" line under a "* " agent block.
        for chunk in re.split(r"user-agent:", body):
            if chunk.strip().startswith("*"):
                for line in chunk.splitlines():
                    if line.strip().startswith("disallow:"):
                        rule = line.split(":", 1)[1].strip()
                        if rule and rule != "":
                            print(f"[fetch] WARN: robots.txt disallows "
                                  f"'{rule}' for wildcard agent.")
                            return
    print("[fetch] robots.txt OK — scraping permitted.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100,
                        help="Max notes to keep after keyword filter.")
    parser.add_argument("--max-fetch", type=int, default=250,
                        help="Max sample-page fetches (upper bound).")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Minimum seconds between network requests.")
    parser.add_argument("--no-filter", action="store_true",
                        help="Keep every fetched note (skip keyword filter).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch index only; print counts and exit.")
    args = parser.parse_args(argv)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    last_fetch = [0.0]
    _check_robots(session)

    # 1. Fetch neurology index.
    print(f"[fetch] Index: {INDEX_URL}")
    try:
        index_html = fetch(INDEX_URL, session, args.delay, last_fetch)
    except Exception as e:
        print(f"[fetch] FAIL: could not fetch index ({e})")
        return 2
    links = extract_sample_links(index_html)
    print(f"[fetch] Sample links found: {len(links)}")
    if not links:
        print("[fetch] FAIL: 0 sample links parsed from index HTML")
        return 3

    if args.dry_run:
        for l in links[:20]:
            print(f"    {l['sample_id']}: {l['title']}")
        return 0

    # 2. Fetch samples, filter for epilepsy keywords, save kept ones.
    kept: list[dict] = []
    fetched = 0
    parse_fail = 0
    filtered_out = 0

    for link in links:
        if fetched >= args.max_fetch or len(kept) >= args.limit:
            break
        try:
            html = fetch(link["url"], session, args.delay, last_fetch)
        except Exception as e:
            print(f"[fetch] SKIP {link['sample_id']}: {e}")
            continue
        fetched += 1
        text = extract_body(html)
        if not text:
            parse_fail += 1
            continue
        kws = keyword_matches(text)
        matched = bool(kws)
        if not args.no_filter and not matched:
            filtered_out += 1
            continue

        idx = len(kept) + 1
        doc_id = f"mt_sample_{idx:04d}"
        doc_dir = OUT_ROOT / doc_id
        doc_dir.mkdir(exist_ok=True)
        (doc_dir / "note.txt").write_text(text)
        metadata = {
            "doc_id": doc_id,
            "source_url": link["url"],
            "sample_id": link["sample_id"],
            "title": link["title"],
            "specialty": "Neurology",
            "sample_type": "neurology",
            "fetch_date": datetime.now(timezone.utc).isoformat(),
            "epilepsy_keyword_match": matched,
            "keywords_hit": kws,
            "char_count": len(text),
        }
        (doc_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
        kept.append(metadata)
        print(f"[fetch] KEEP {doc_id} ({link['sample_id']}): "
              f"{link['title'][:50]} chars={len(text)} kws={kws}")

    # 3. Manifest.
    manifest_path = OUT_ROOT / "manifest.csv"
    fields = ["id", "source_url", "sample_id", "title",
              "char_count", "epilepsy_keyword_match", "keywords_hit"]
    with manifest_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for m in kept:
            w.writerow({
                "id": m["doc_id"],
                "source_url": m["source_url"],
                "sample_id": m["sample_id"],
                "title": m["title"],
                "char_count": m["char_count"],
                "epilepsy_keyword_match": m["epilepsy_keyword_match"],
                "keywords_hit": "|".join(m["keywords_hit"]),
            })

    # 4. README.
    _write_readme(OUT_ROOT, len(links), fetched, parse_fail, filtered_out,
                  len(kept), args)

    print()
    print(f"[fetch] Summary:")
    print(f"    index links seen  : {len(links)}")
    print(f"    detail pages fetched: {fetched}")
    print(f"    body-parse failures: {parse_fail}")
    print(f"    filtered out       : {filtered_out}")
    print(f"    kept               : {len(kept)}")
    return 0 if kept else 4


def _write_readme(out: Path, n_links: int, n_fetched: int,
                  n_parse_fail: int, n_filtered: int, n_kept: int,
                  args) -> None:
    lines = [
        "# Phase 6b — MTSamples neurology evaluation corpus",
        "",
        "## Source",
        "",
        "- Base URL: https://www.mtsamples.com/site/pages/browse.asp?Type=42-Neurology",
        "- Content: publicly-hosted medical-transcription samples (educational,",
        "  \"not medical advice\").",
        "- robots.txt: `User-agent: *  Disallow:` (crawling permitted).",
        "- No explicit LICENSE published by mtsamples.com. Notes are stored",
        "  locally for research-only NLP evaluation; this directory is",
        "  gitignored.",
        "",
        "## Fetch protocol",
        "",
        f"- User-Agent identifies MedAI-EPI project + contact email.",
        f"- Rate limit: {args.delay}s minimum between network requests.",
        f"- Local HTML cache at `.cache/<sha1>.html`; reruns short-circuit.",
        f"- Epilepsy keyword filter: `{'|'.join(EPI_KEYWORDS)}`",
        "",
        "## Stats (last run)",
        "",
        f"- Neurology index links seen: {n_links}",
        f"- Detail pages fetched: {n_fetched}",
        f"- Body-parse failures: {n_parse_fail}",
        f"- Filtered out (no epilepsy keyword): {n_filtered}",
        f"- Kept: **{n_kept}**",
        "",
        "## Layout",
        "",
        "- `mt_sample_NNNN/note.txt` — extracted plain-text note.",
        "- `mt_sample_NNNN/metadata.json` — source URL, sample id, title,",
        "  fetch date, keyword matches.",
        "- `manifest.csv` — one row per kept note.",
        "",
        "## Rerun",
        "",
        "    venv-medcat/bin/python scripts/fetch_mtsamples_neuro.py "
        "--limit 100",
        "",
        "Only NEW URLs will hit the network — the disk cache is respected.",
        "Delete `.cache/` to force refetch (do NOT do this without cause;",
        "be polite to the site).",
        "",
        "## Silver-labelling",
        "",
        "10-note silver labels via GPT-5.6-terra live at `silver_gold_10.json`",
        "when produced (research-only OpenAI use, held-out tier).",
    ]
    (out / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
