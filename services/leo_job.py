"""Job description for a LEO batch run: a request in plain words -> a small record the user checks and edits.

    "give seizure types for the first 100 subjects"  ->  JobSpec  ->  (user confirms or edits)  ->  run

The spec is data, not code.  It can only name things LEO knows: phenotypes and question templates from
``services.leo_catalog``, columns that exist in the uploaded table, a row selection from a short fixed list
(all / first N subjects / first N notes, plus simple column and date conditions) and an output format.  Anything in
the request that is not understood is reported, never guessed.

``parse_request`` is rule-based (key words and numbers); a model-based parser could be added later, but its output
would pass through the same ``validate`` step and the same confirmation.

    spec = parse_request("seizure type and current medications for the first 100 patients", df)
    problems = validate(spec, df)
    print(describe(spec, df))
    table, claims, prov = run_spec(spec, df, runtime)

Pure functions apart from ``run_spec`` (which calls ``services.leo_batch.run_table``); no I/O.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

import pandas as pd

from services import leo_catalog as cat

SPEC_VERSION = 1
SUBJECT_COLS = ("patient_id", "subject_id", "subject", "patient", "mrn", "pat_id", "person_id", "study_id", "pid")
OPS = ("eq", "neq", "contains", "gte", "lte")
MODES = ("all", "first_subjects", "first_notes")
FORMATS = ("csv", "xlsx")

# Phrases that select phenotypes.  More specific phrases first; a matched span is removed so that a shorter
# phrase cannot match inside it again.  Targets are phenotype ids or panel ids (cat.PANELS).
_SYNONYMS: tuple[tuple[str, str], ...] = (
    (r"(?:prior|previous|stopped)(?: and|,| or|/) ?(?:failed|stopped|prior)(?: asms?| medications?| drugs?| aeds?)?", "prior_asms,failed_asms"),
    (r"prior (?:asms?|anti-?seizure (?:medications?|drugs?)|medications?|drugs?|aeds?)|previous(?:ly used)? (?:medications?|drugs?|asms?)|stopped (?:drugs?|medications?)", "prior_asms"),
    (r"failed (?:asms?|medications?|drugs?|aeds?)", "failed_asms"),
    (r"rescue (?:medications?|drugs?|asms?)|rescue", "rescue_medication"),
    (r"drug[- ]resistan\w*|refractory|\bdre\b", "drug_resistance"),
    (r"current (?:asms?|anti-?seizure (?:medications?|drugs?)|medications?|drugs?|aeds?)|medications?|anti-?seizure (?:medications?|drugs?)|\basms?\b|\baeds?\b", "current_asms"),
    (r"seizure[- ]types?|types? of seizures?|seizure classification", "seizure_type"),
    (r"epilepsy[- ]types?|types? of epilepsy", "epilepsy_type"),
    (r"age (?:at|of) (?:seizure )?onset|onset age|age when seizures began", "age_at_onset"),
    (r"seizure[- ]frequenc\w+|how often|frequency", "seizure_frequency"),
    (r"etiology details?|cause details?", "etiology_details"),
    (r"etiolog\w+|\bcauses?\b", "etiology_category"),
    (r"semiolog\w+", "semiology"),
    (r"hippocampal sclerosis|\bhs\b", "hippocampal_sclerosis"),
    (r"focal cortical dysplasia|\bfcd\b", "focal_cortical_dysplasia"),
    (r"mri findings?", "mri_findings"),
    (r"\bmri\b|imaging", "mri"),
    (r"\beeg\b", "eeg"),
    (r"surgery history|epilepsy surgery|neurostimulat\w+|\bvns\b|\brns\b|\bdbs\b|surgical history|surgery|surgeries", "surgery_history"),
    (r"medication roles", "medication"),
    (r"everything|all phenotypes|all fields", "all"),
    (r"\bcore (?:fields|phenotypes|set)\b|\bcore\b", "core"),
)

# Phrases that select predefined questions.
_ASK_SYNONYMS: tuple[tuple[str, str], ...] = (
    (r"status epilepticus", "status_epilepticus"),
    (r"neurostimulation device|vns,? rns or dbs device", "neurostimulation"),
    (r"family history", "family_history"),
    (r"febrile seizures?", "febrile_seizures"),
    (r"\baura\b", "aura"),
    (r"nocturnal|during sleep", "nocturnal"),
    (r"triggers?", "triggers"),
    (r"side effects?|adverse effects?", "adverse_effects"),
    (r"driving", "driving"),
    (r"pregnan\w+|contraception", "pregnancy"),
    (r"developmental (?:delay|disabilit\w+)|intellectual disabilit\w+", "developmental"),
    (r"psychiatric", "psychiatric"),
    (r"seizure[- ]free duration|how long seizure[- ]free", "seizure_free_duration"),
)

_YES_NO_START = re.compile(r"^(?:is|are|was|were|does|do|did|has|have|had|can|could|will|would|should)\b", re.I)
_MONTHS = {m: i for i, m in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"), 1)}


# ─── Data ────────────────────────────────────────────────────────────────

@dataclass
class Condition:
    column: str
    op: str                      # eq | neq | contains | gte | lte
    value: str


@dataclass
class RowSelect:
    mode: str = "all"            # all | first_subjects | first_notes
    n: int = 0
    where: list[Condition] = field(default_factory=list)


@dataclass
class JobSpec:
    request: str = ""
    columns: dict = field(default_factory=lambda: {"text": "", "id": "", "date": "", "subject": ""})
    rows: RowSelect = field(default_factory=RowSelect)
    phenotypes: list[str] = field(default_factory=list)          # phenotype ids (panels already expanded)
    ask_templates: list[str] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)          # [{"question": str, "answer_type": str}]
    output_format: str = "csv"
    include_review: bool = True
    understood: list[str] = field(default_factory=list)          # what the parser took from the request
    warnings: list[str] = field(default_factory=list)
    version: int = SPEC_VERSION

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def spec_from_dict(d: dict) -> JobSpec:
    """Rebuild a spec from JSON (a saved file or the web form).  Unknown keys are rejected, not ignored."""
    allowed = {"request", "columns", "rows", "phenotypes", "ask_templates", "questions", "output_format",
               "include_review", "understood", "warnings", "version"}
    extra = set(d) - allowed
    if extra:
        raise ValueError(f"unknown job field(s): {', '.join(sorted(extra))}")
    r = d.get("rows") or {}
    extra_r = set(r) - {"mode", "n", "where"}
    if extra_r:
        raise ValueError(f"unknown row field(s): {', '.join(sorted(extra_r))}")
    where = [Condition(str(c.get("column", "")), str(c.get("op", "")), str(c.get("value", "")))
             for c in r.get("where") or []]
    cols = {"text": "", "id": "", "date": "", "subject": ""}
    cols.update({k: str(v) for k, v in (d.get("columns") or {}).items() if k in cols})
    return JobSpec(
        request=str(d.get("request", "")), columns=cols,
        rows=RowSelect(str(r.get("mode", "all")), int(r.get("n") or 0), where),
        phenotypes=[str(x) for x in d.get("phenotypes") or []],
        ask_templates=[str(x) for x in d.get("ask_templates") or []],
        questions=[{"question": str(q.get("question", "")), "answer_type": str(q.get("answer_type", "text"))}
                   for q in d.get("questions") or []],
        output_format=str(d.get("output_format", "csv")).lower(), include_review=bool(d.get("include_review", True)),
        understood=[str(x) for x in d.get("understood") or []], warnings=[str(x) for x in d.get("warnings") or []],
        version=int(d.get("version", SPEC_VERSION)))


# ─── Parsing a request ───────────────────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def match_column(name: str, df: pd.DataFrame) -> str:
    """Case- and punctuation-insensitive column lookup; '' if there is no unique match."""
    want = _norm(name)
    hits = [c for c in df.columns if _norm(c) == want]
    return hits[0] if len(hits) == 1 else ""


def detect_subject_col(df: pd.DataFrame) -> str:
    lower = {c.lower(): c for c in df.columns}
    for n in SUBJECT_COLS:
        if n in lower:
            return lower[n]
    return ""


def _date_from_text(s: str) -> Optional[str]:
    """'2021', 'march 2021', '2021-03', '2021-03-15' -> ISO date string (first day), else None."""
    s = s.strip().lower()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}"
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if m:
        return f"{int(m[1]):04d}-{int(m[2]):02d}-01"
    m = re.fullmatch(r"([a-z]+) (\d{4})", s)
    if m and m[1] in _MONTHS:
        return f"{int(m[2]):04d}-{_MONTHS[m[1]]:02d}-01"
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return f"{int(m[1]):04d}-01-01"
    return None


def parse_request(request: str, df: pd.DataFrame, *, text_col: str = "", id_col: str = "", date_col: str = "",
                  subject_col: str = "", default_format: str = "csv") -> JobSpec:
    """Plain-words request -> JobSpec.  Never raises on odd wording: problems go to ``warnings``/``validate``."""
    from services import leo_batch as lb
    spec = JobSpec(request=request.strip())
    spec.output_format = default_format
    low = " " + re.sub(r"\s+", " ", request.lower()) + " "
    # columns
    try:
        c = lb.detect_columns(df, text_col, id_col, date_col)
    except ValueError as e:
        c = {"text": text_col, "id": id_col, "date": date_col}
        spec.warnings.append(str(e))
    spec.columns = {"text": c["text"], "id": c["id"], "date": c["date"],
                    "subject": subject_col or detect_subject_col(df)}

    # --- questions in quotes or after "ask"
    taken: list[tuple[int, int]] = []
    for m in re.finditer(r"[\"“]([^\"”]{6,400})[\"”]", request):
        q = m.group(1).strip()
        spec.questions.append({"question": q if q.endswith("?") else q + "?",
                               "answer_type": "yes_no" if _YES_NO_START.match(q) else "text"})
        spec.understood.append(f"your question: {q!r}")
        low = low.replace(m.group(0).lower(), " " * len(m.group(0)))
    # --- predefined questions
    for pat, aid in _ASK_SYNONYMS:
        if re.search(pat, low):
            if aid not in spec.ask_templates:
                spec.ask_templates.append(aid)
                spec.understood.append(f"question: {cat.ask_template(aid).label}")
            low = re.sub(pat, " ", low)

    # --- row selection
    n_subj = re.search(r"\b(?:first|top)\s+(\d+)\s+(?:subjects?|patients?|people|persons?|participants?|individuals?)\b", low)
    n_note = re.search(r"\b(?:first|top)\s+(\d+)\s+(?:notes?|rows?|records?|documents?|letters?|visits?)\b", low)
    n_bare = re.search(r"\b(?:for|of|in)\s+(\d+)\s+(?:subjects?|patients?|people|participants?)\b", low)
    if n_subj:
        spec.rows = RowSelect("first_subjects", int(n_subj.group(1)))
        low = low.replace(n_subj.group(0), " ")
    elif n_note:
        spec.rows = RowSelect("first_notes", int(n_note.group(1)))
        low = low.replace(n_note.group(0), " ")
    elif n_bare:
        spec.rows = RowSelect("first_subjects", int(n_bare.group(1)))
        spec.warnings.append(f"'{n_bare.group(0).strip()}' was read as the first {n_bare.group(1)} subjects in file order")
        low = low.replace(n_bare.group(0), " ")
    elif re.search(r"\ball (?:the )?(?:subjects?|patients?|notes?|rows?)\b|\beveryone\b|\beach (?:subject|patient|note)\b", low):
        spec.rows = RowSelect("all", 0)
    if spec.rows.mode == "first_subjects":
        spec.understood.append(f"rows: first {spec.rows.n} subjects (in file order), all their notes")
    elif spec.rows.mode == "first_notes":
        spec.understood.append(f"rows: first {spec.rows.n} notes")
    else:
        spec.understood.append("rows: all")

    # --- conditions: "where <column> is/=/contains <value>"; "after/before/since <date>"
    for m in re.finditer(r"\bwhere\s+([a-z0-9_ ]+?)\s+(is not|is|=|equals|contains)\s+['\"]?([^'\",;]+?)['\"]?(?=\s+(?:and|with|for|give|add|export)\b|[,;]|\s*$)", low):
        col = match_column(m.group(1), df)
        op = {"is": "eq", "=": "eq", "equals": "eq", "is not": "neq", "contains": "contains"}[m.group(2)]
        if col:
            spec.rows.where.append(Condition(col, op, m.group(3).strip()))
            spec.understood.append(f"only rows where {col} {m.group(2)} {m.group(3).strip()!r}")
        else:
            spec.warnings.append(f"no column matches {m.group(1).strip()!r}; this condition was not applied")
        low = low.replace(m.group(0), " ")
    for m in re.finditer(r"\b(after|since|before|until)\s+((?:[a-z]+ )?\d{4}(?:-\d{1,2}(?:-\d{1,2})?)?)\b", low):
        d = _date_from_text(m.group(2))
        if d is None:
            spec.warnings.append(f"could not read the date {m.group(2)!r}; this condition was not applied")
            continue
        if not spec.columns["date"]:
            spec.warnings.append(f"'{m.group(0)}' needs a date column and none was found; this condition was not applied")
            continue
        op = "gte" if m.group(1) in ("after", "since") else "lte"
        spec.rows.where.append(Condition(spec.columns["date"], op, d))
        spec.understood.append(f"only notes dated {'on or after' if op == 'gte' else 'on or before'} {d}")
        low = low.replace(m.group(0), " ")

    # --- output
    if re.search(r"\b(?:xlsx|excel)\b", low):
        spec.output_format = "xlsx"
    elif re.search(r"\bcsv\b", low):
        spec.output_format = "csv"
    if re.search(r"\b(?:accepted only|only accepted|only confident|without (?:the )?review|leave .* blank)\b", low):
        spec.include_review = False
        spec.understood.append("values that need review are left blank")

    # --- phenotypes
    found: list[str] = []
    for pat, target in _SYNONYMS:
        if re.search(pat, low):
            found.append(target)
            low = re.sub(pat, " ", low)
    ids: list[str] = []
    for t in found:
        try:
            ids += [p.id for p in cat.resolve_phenotypes(t.split(","))]
        except KeyError:
            spec.warnings.append(f"'{t}' is not in the catalogue")
    spec.phenotypes = [p.id for p in cat.EXTRACT if p.id in set(ids)]
    for p in spec.phenotypes:
        ph = cat.get(p)
        spec.understood.append(f"column: {ph.label} [{ph.evidence}]")
    if not spec.phenotypes and not spec.ask_templates and not spec.questions:
        spec.warnings.append("nothing to extract was recognised in the request; tick phenotypes or add a question")
    return spec


# ─── Checking ────────────────────────────────────────────────────────────

def validate(spec: JobSpec, df: pd.DataFrame) -> list[str]:
    """Problems that must be fixed before running (empty list = ready)."""
    out: list[str] = []
    cols = set(df.columns)
    if not len(df):
        out.append("the file has a header but no notes (no data rows)")
    if spec.version != SPEC_VERSION:
        out.append(f"job version {spec.version} is not supported (expected {SPEC_VERSION})")
    for role in ("text", "id", "date", "subject"):
        v = spec.columns.get(role, "")
        if v and v not in cols:
            out.append(f"{role} column {v!r} is not in the file (columns: {', '.join(map(str, df.columns))})")
    if not spec.columns.get("text"):
        out.append("choose the column that holds the note text")
    if spec.rows.mode not in MODES:
        out.append(f"rows.mode must be one of {', '.join(MODES)}")
    if spec.rows.mode in ("first_subjects", "first_notes") and spec.rows.n <= 0:
        out.append("the number of rows to take must be at least 1")
    if spec.rows.mode == "first_subjects" and not spec.columns.get("subject"):
        out.append("'first N subjects' needs a subject column; choose it, or ask for the first N notes")
    for c in spec.rows.where:
        if c.op not in OPS:
            out.append(f"condition operator {c.op!r} is not one of {', '.join(OPS)}")
        if c.column not in cols:
            out.append(f"condition column {c.column!r} is not in the file")
        if c.op in ("gte", "lte") and _date_from_text(c.value) is None:
            out.append(f"condition value {c.value!r} is not a date (use YYYY, YYYY-MM or YYYY-MM-DD)")
    known = {p.id for p in cat.EXTRACT}
    for p in spec.phenotypes:
        if p not in known:
            out.append(f"unknown phenotype {p!r}")
    for a in spec.ask_templates:
        try:
            cat.ask_template(a)
        except KeyError:
            out.append(f"unknown question template {a!r}")
    for i, q in enumerate(spec.questions, 1):
        try:
            cat.custom_ask(q.get("question", ""), q.get("answer_type", "text"), aid=f"q{i}")
        except ValueError as e:
            out.append(f"question {i}: {e}")
    if not (spec.phenotypes or spec.ask_templates or spec.questions):
        out.append("nothing to extract: choose at least one phenotype or question")
    if spec.output_format not in FORMATS:
        out.append("output format must be csv or xlsx")
    if len(spec.phenotypes) + len(spec.ask_templates) + len(spec.questions) > 60:
        out.append("more than 60 outputs selected; reduce the selection")
    return out


def needs_llm(spec: JobSpec) -> bool:
    return bool(spec.ask_templates or spec.questions)


def selection(spec: JobSpec) -> tuple[list[cat.Phenotype], list[cat.AskSpec]]:
    phen = [cat.get(p) for p in spec.phenotypes]
    asks = [cat.ask_template(a) for a in spec.ask_templates]
    for i, q in enumerate(spec.questions, 1):
        asks.append(cat.custom_ask(q["question"], q.get("answer_type", "text"), aid=f"q{i}"))
    return phen, asks


# ─── Row selection ───────────────────────────────────────────────────────

def _apply(df: pd.DataFrame, c: Condition) -> pd.Series:
    col = df[c.column].astype(str)
    if c.op == "eq":
        return col.str.strip().str.lower() == c.value.strip().lower()
    if c.op == "neq":
        return col.str.strip().str.lower() != c.value.strip().lower()
    if c.op == "contains":
        return col.str.lower().str.contains(re.escape(c.value.lower()), na=False)
    d = pd.to_datetime(col, errors="coerce")
    lim = pd.Timestamp(_date_from_text(c.value))
    return (d >= lim) if c.op == "gte" else (d <= lim)


def select_rows(df: pd.DataFrame, spec: JobSpec) -> tuple[pd.DataFrame, dict]:
    """Rows the run will cover, and counts for the confirmation screen.  The input table is not changed."""
    info: dict[str, Any] = {"notes_in_file": len(df), "subjects_in_file": None}
    subj = spec.columns.get("subject", "")
    if subj and subj in df.columns:
        info["subjects_in_file"] = int(df[subj].astype(str).str.strip().replace("", pd.NA).dropna().nunique())
    mask = pd.Series(True, index=df.index)
    for c in spec.rows.where:
        mask &= _apply(df, c)
    sub = df[mask]
    info["notes_after_conditions"] = len(sub)
    if spec.rows.mode == "first_subjects" and subj:
        keys = sub[subj].astype(str).str.strip()
        first = list(dict.fromkeys(k for k in keys if k))[: spec.rows.n]
        sub = sub[keys.isin(set(first))]
        info["subjects_selected"] = len(first)
    elif spec.rows.mode == "first_notes":
        sub = sub.iloc[: spec.rows.n]
    if subj and subj in sub.columns:
        info["subjects_selected"] = int(sub[subj].astype(str).str.strip().replace("", pd.NA).dropna().nunique())
    info["notes_selected"] = len(sub)
    return sub.reset_index(drop=True), info


def describe(spec: JobSpec, df: Optional[pd.DataFrame] = None) -> str:
    """The plain-words summary the user confirms."""
    lines = []
    if df is not None:
        sub, info = select_rows(df, spec)
        head = f"File: {info['notes_in_file']} notes"
        if info.get("subjects_in_file") is not None:
            head += f", {info['subjects_in_file']} subjects"
        lines.append(head)
        sel = f"This run: {info['notes_selected']} notes"
        if info.get("subjects_selected") is not None:
            sel += f" from {info['subjects_selected']} subjects"
        lines.append(sel)
    c = spec.columns
    lines.append("Columns used: " + ", ".join(f"{k} = {v or '(none)'}" for k, v in c.items()))
    for w in spec.rows.where:
        lines.append(f"Only rows where {w.column} {dict(eq='is', neq='is not', contains='contains', gte='is on or after', lte='is on or before')[w.op]} {w.value}")
    try:
        phen, asks = selection(spec)
    except (KeyError, ValueError):
        phen, asks = [], []
    if phen:
        lines.append("Columns added: " + "; ".join(f"{p.label} [{p.evidence}]" for p in phen))
    if asks:
        lines.append("Questions: " + "; ".join(a.question for a in asks) + "  (answers always need review)")
    lines.append(f"Output: {spec.output_format}, input columns kept, one row per note"
                 + ("" if spec.include_review else "; values needing review left blank"))
    lines += [f"Note: {w}" for w in spec.warnings]
    return "\n".join(lines)


# ─── Running ─────────────────────────────────────────────────────────────

def run_spec(spec: JobSpec, df: pd.DataFrame, rt, *, progress: Optional[Callable[[int, int, str], None]] = None,
             cancel: Optional[Callable[[], bool]] = None):
    """Run the selected rows; returns (table, claims, provenance).  Validates first."""
    from services import leo_batch as lb
    problems = validate(spec, df)
    if problems:
        raise ValueError("job is not ready: " + "; ".join(problems))
    sub, info = select_rows(df, spec)
    if not len(sub):
        raise ValueError("the selection matches no notes")
    phen, asks = selection(spec)
    if asks and not rt.use_llm:
        raise ValueError("questions need the LLM; remove them or run where the model is available")
    table, claims, prov = lb.run_table(
        sub, rt, phenotypes=phen, asks=asks, text_col=spec.columns["text"], id_col=spec.columns["id"],
        date_col=spec.columns["date"], include_review=spec.include_review, progress=progress, cancel=cancel)
    prov["job_spec"] = spec.to_dict()
    prov["row_selection"] = info
    return table, claims, prov


__all__ = ["JobSpec", "RowSelect", "Condition", "parse_request", "validate", "describe", "select_rows",
           "selection", "run_spec", "spec_from_dict", "needs_llm", "match_column", "detect_subject_col", "SPEC_VERSION"]
