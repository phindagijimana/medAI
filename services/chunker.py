"""Section- and paragraph-aware chunking for long clinical notes.

Two shapes of input are supported:

    chunk_text(note_text)         # one long free-text note
    chunk_rows(rows, ...)         # list of per-visit records (Excel-like)

Both return the same `Chunk` list, which the downstream extractor + merger
consume uniformly. The chunker never splits mid-sentence and prefers to
break on clinical section headers (HPI, Assessment, EEG, MRI, …).

Row-based chunking treats each row as one chunk (a visit is an atomic unit
of context); if a single row exceeds the token budget it falls back to
text-chunking that row internally, preserving the visit_date on every
sub-chunk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable


# ---------------------------------------------------------------------------
# Chunk record
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """One unit of text handed to the extractor.

    - `char_offset` is the offset in the ORIGINAL text (0 for row-based
      chunks — each row's char offsets are locally meaningful).
    - `visit_date` is populated only for row-based chunks; the merger uses
      it as the temporal key for "latest wins".
    - `section_hint` is a best-effort label ("Assessment", "EEG", …) for
      the sub-region a chunk covers; the merger uses it for tie-breaking
      only, never for correctness.
    """

    text: str
    chunk_index: int
    total_chunks: int = 1
    char_offset: int = 0
    visit_date: date | None = None
    visit_id: str | None = None
    section_hint: str | None = None
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text chunker
# ---------------------------------------------------------------------------

# Common clinical section headers seen in epilepsy clinic letters (case
# insensitive, header line only). Order does not matter — we split by
# regex alternation and keep the header text as section_hint.
_SECTION_HEADERS = [
    r"chief\s+complaint",
    r"history\s+of\s+present\s+illness",
    r"hpi",
    r"past\s+medical\s+history",
    r"pmh",
    r"medications?",
    r"current\s+medications?",
    r"allergies",
    r"family\s+history",
    r"social\s+history",
    r"review\s+of\s+systems",
    r"physical\s+exam(?:ination)?",
    r"neurologic(?:al)?\s+exam(?:ination)?",
    r"seizure\s+history",
    r"seizures?",
    r"eeg(?:\s+report)?",
    r"electroencephalogram",
    r"mri(?:\s+report)?",
    r"neuroimaging",
    r"imaging",
    r"assessment",
    r"impression",
    r"plan",
    r"recommendations?",
    r"follow[- ]?up",
]

_SECTION_HEADER_RE = re.compile(
    r"(?im)^\s*(" + "|".join(_SECTION_HEADERS) + r")\s*:?\s*$"
)


def _split_by_sections(text: str) -> list[tuple[str | None, str, int]]:
    """Return [(section_hint, section_text, char_offset), ...].

    If no headers are found, returns [(None, text, 0)].
    """
    matches = list(_SECTION_HEADER_RE.finditer(text))
    if not matches:
        return [(None, text, 0)]

    sections: list[tuple[str | None, str, int]] = []

    # Preamble before the first header (patient demographics, letterhead, …)
    first_start = matches[0].start()
    if first_start > 0:
        preamble = text[:first_start]
        if preamble.strip():
            sections.append((None, preamble, 0))

    for i, m in enumerate(matches):
        header_hint = m.group(1).strip().lower()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end]
        if body.strip():
            sections.append((header_hint, body, body_start))

    return sections


_PARA_SPLIT_RE = re.compile(r"\n\s*\n+")


def _pack_paragraphs(
    section_text: str,
    section_offset: int,
    max_chars: int,
    overlap_chars: int,
    section_hint: str | None,
) -> list[tuple[str, int, str | None]]:
    """Split a section into overlapping windows on paragraph boundaries.

    Returns [(window_text, absolute_char_offset, section_hint), ...].
    Overlap is realized by re-including the last paragraph of the previous
    window when it fits — never a mid-sentence chop.
    """
    if len(section_text) <= max_chars:
        return [(section_text, section_offset, section_hint)]

    paragraphs: list[tuple[str, int]] = []
    cursor = 0
    for m in _PARA_SPLIT_RE.finditer(section_text):
        chunk = section_text[cursor:m.start()]
        if chunk.strip():
            paragraphs.append((chunk, section_offset + cursor))
        cursor = m.end()
    tail = section_text[cursor:]
    if tail.strip():
        paragraphs.append((tail, section_offset + cursor))

    if not paragraphs:
        return [(section_text, section_offset, section_hint)]

    windows: list[tuple[str, int, str | None]] = []
    i = 0
    while i < len(paragraphs):
        buf_paras: list[tuple[str, int]] = [paragraphs[i]]
        buf_len = len(paragraphs[i][0])
        j = i + 1
        while j < len(paragraphs) and buf_len + len(paragraphs[j][0]) + 2 <= max_chars:
            buf_paras.append(paragraphs[j])
            buf_len += len(paragraphs[j][0]) + 2
            j += 1

        window_text = "\n\n".join(p[0] for p in buf_paras)
        window_offset = buf_paras[0][1]
        windows.append((window_text, window_offset, section_hint))

        if j >= len(paragraphs):
            break

        # Overlap: back off by paragraphs that fit inside overlap_chars.
        overlap_len = 0
        overlap_start = j
        for k in range(j - 1, i, -1):
            if overlap_len + len(paragraphs[k][0]) <= overlap_chars:
                overlap_start = k
                overlap_len += len(paragraphs[k][0]) + 2
            else:
                break
        i = overlap_start if overlap_start < j else j

    return windows


def chunk_text(
    text: str,
    *,
    max_chars: int = 8000,
    overlap_chars: int = 400,
) -> list[Chunk]:
    """Chunk a single free-text note by clinical section, then paragraph.

    `max_chars` targets ~2k input tokens (roughly 4 chars/token English
    prose). `overlap_chars` guards against a fact straddling two chunks.
    """
    if not text or not text.strip():
        return []

    sections = _split_by_sections(text)
    all_windows: list[tuple[str, int, str | None]] = []
    for hint, body, offset in sections:
        all_windows.extend(
            _pack_paragraphs(body, offset, max_chars, overlap_chars, hint)
        )

    total = len(all_windows)
    return [
        Chunk(
            text=w_text,
            chunk_index=i,
            total_chunks=total,
            char_offset=w_offset,
            section_hint=w_hint,
        )
        for i, (w_text, w_offset, w_hint) in enumerate(all_windows)
    ]


# ---------------------------------------------------------------------------
# Row chunker (Excel-like: one visit per row)
# ---------------------------------------------------------------------------


def _coerce_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        # accept YYYY-MM-DD / YYYY/MM/DD / MM/DD/YYYY
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                from datetime import datetime
                return datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                continue
    return None


def chunk_rows(
    rows: Iterable[dict],
    *,
    text_key: str = "text",
    date_key: str = "visit_date",
    visit_id_key: str = "visit_id",
    max_chars: int = 8000,
    overlap_chars: int = 400,
) -> list[Chunk]:
    """Chunk an iterable of visit records.

    Each dict must have `text_key`; `date_key` is optional but strongly
    recommended (the merger uses it as the temporal key). Rows are
    processed in the order given — sort by visit_date first if you want
    chronological order enforced upstream.
    """
    chunks: list[Chunk] = []
    row_list = [r for r in rows if r and r.get(text_key)]

    for row_i, row in enumerate(row_list):
        row_text = str(row[text_key])
        row_date = _coerce_date(row.get(date_key))
        row_vid = row.get(visit_id_key) or f"row_{row_i}"

        if len(row_text) <= max_chars:
            chunks.append(Chunk(
                text=row_text,
                chunk_index=len(chunks),
                char_offset=0,
                visit_date=row_date,
                visit_id=str(row_vid),
                section_hint=None,
                metadata={k: v for k, v in row.items() if k != text_key},
            ))
            continue

        sub = chunk_text(row_text, max_chars=max_chars, overlap_chars=overlap_chars)
        for s in sub:
            chunks.append(Chunk(
                text=s.text,
                chunk_index=len(chunks),
                char_offset=s.char_offset,
                visit_date=row_date,
                visit_id=str(row_vid),
                section_hint=s.section_hint,
                metadata={k: v for k, v in row.items() if k != text_key},
            ))

    total = len(chunks)
    for c in chunks:
        c.total_chunks = total
    return chunks


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    demo = """
    HPI:
    45yo F with intractable focal epilepsy since age 12.

    Assessment:
    Drug-resistant focal epilepsy. Seizure-free for 8 months.

    MRI:
    3T scan shows left hippocampal sclerosis.

    Plan:
    Continue current ASMs. EMU admission next month.
    """
    for c in chunk_text(demo):
        print(f"[{c.chunk_index}/{c.total_chunks}] section={c.section_hint!r} "
              f"offset={c.char_offset} len={len(c.text)}")

    rows = [
        {"visit_date": "2024-01-15", "text": "Baseline visit. On lamotrigine."},
        {"visit_date": "2024-06-10", "text": "Breakthrough seizure. Added levetiracetam."},
        {"visit_date": "2024-12-05", "text": "Seizure-free 5 months. Continue current regimen."},
    ]
    for c in chunk_rows(rows):
        print(f"[{c.chunk_index}] visit={c.visit_date} id={c.visit_id} "
              f"len={len(c.text)}")
