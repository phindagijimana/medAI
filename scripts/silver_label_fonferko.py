#!/usr/bin/env python3
"""Convert Fonferko-Shadrach 2024 gold annotations → MedAI-EPI **silver** labels.

Reads the 200 letters + JSON annotations at
`data/fonferko_shadrach_2024/zenodo_8356494/Json/` and produces one silver
`EpilepsyPhenotype` JSON per letter under
`data/fonferko_shadrach_2024/silver_labels_v0_2_1/`.

**Silver**, not gold: this converter applies deterministic mappings +
lookup tables that are imperfect by construction. Use these labels for
M0/M1/M2 dev-set experiments, B1 pretraining, or as example pool for
few-shot; do NOT report per-field metrics against them in the paper as
if they were adjudicated gold.

Mapping strategy (from `docs/FONFERKO_SHADRACH_MAPPING.md`):

  Fonferko entity           → MedAI-EPI field
  ----------------          ---------------------------------
  Prescription              → MedicationModule.current_asms (with a
                              medication-status heuristic on nearby text)
  SeizureFrequency          → ClinicalSeizureModule.seizure_frequency
  Diagnosis + DiagCategory  → epilepsy_type (Epilepsy) / predominant_seizure_type
                              (MultipleSeizures + SingleSeizure) via CUI lookup
  Onset                     → age_at_onset_years (midpoint of AgeLower/Upper)
  EpilepsyCause             → etiology_category (keyword classifier) +
                              etiology_details_text
  PatientHistory            → semiology_text (first non-trivial free-text bucket)

Fields not derivable from ExECT-v2 are emitted as `not_documented`.

Every output record carries a `provenance` block naming the source paper,
DOI, Zenodo record IDs, and this script — so nothing silver can be mistaken
for gold downstream.
"""

from __future__ import annotations

import json
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from schema import (
    SCHEMA_VERSION,
    Awareness,
    Certainty,
    ClinicalSeizureModule,
    DocumentMetadata,
    DocumentType,
    DrugResistanceStatus,
    EpilepsyPhenotype,
    EpilepsyType,
    EtiologyCategory,
    Evidence,
    FocalMotorOnset,
    FocalNonmotorOnset,
    Medication,
    MedicationModule,
    MedicationStatus,
    SeizureFrequency,
    SeizureType,
    TemporalStatus,
)


REPO = Path(__file__).resolve().parent.parent
LETTERS_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8381080" / "Gold1-200_corrected_spelling"
JSON_DIR    = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8356494" / "Json"
OUT_DIR     = REPO / "data" / "fonferko_shadrach_2024" / "silver_labels_v0_2_1"

PROVENANCE = {
    "source_paper": "Fonferko-Shadrach B et al. (2024). Annotation of epilepsy clinic letters for natural language processing. J Biomed Semantics 15:17.",
    "source_doi": "10.1186/s13326-024-00316-z",
    "source_pmcid": "PMC11402197",
    "source_license": "CC-BY-4.0",
    "zenodo_records": ["8381080", "8356494", "8382589", "12520180"],
    "generator_script": "scripts/silver_label_fonferko.py",
    "target_schema_version": SCHEMA_VERSION,
    "label_quality": "silver",
    "notes": "Deterministic conversion; imperfect by construction. Not to be used as adjudicated gold.",
}


# ---------------------------------------------------------------------------
# Mapping tables (starter — extend when new CUIs surface)
# ---------------------------------------------------------------------------

# CUI → EpilepsyType (for Diagnosis entities with DiagCategory=Epilepsy)
CUI_TO_EPILEPSY_TYPE: dict[str, EpilepsyType] = {
    "C0472349": EpilepsyType.FOCAL,         # symptomatic-structural-focal-epilepsy
    "C0014556": EpilepsyType.FOCAL,         # temporal-lobe-epilepsy
    "C0014547": EpilepsyType.FOCAL,         # focal-epilepsy
    "C0270850": EpilepsyType.GENERALIZED,   # genetic-generalised-epilepsy
    "C0014548": EpilepsyType.GENERALIZED,   # generalised-epilepsy
    "C0393697": EpilepsyType.GENERALIZED,   # generalised-tonic-clonic-alone (GTCA)
    "C0022336": EpilepsyType.GENERALIZED,   # juvenile-myoclonic-epilepsy
    "C0751495": EpilepsyType.FOCAL,         # focal-seizures (used as epilepsy label sometimes)
}


# CUI → SeizureType (for Diagnosis entities with DiagCategory=MultipleSeizures/SingleSeizure)
CUI_TO_SEIZURE_TYPE: dict[str, SeizureType] = {
    "C0270834": SeizureType.FOCAL_IMPAIRED_AWARENESS,     # focal-seizures-with-loss-of-awareness
    "C0751495": SeizureType.FOCAL_UNKNOWN_AWARENESS,      # focal-seizures
    "C0270833": SeizureType.FOCAL_AWARE,                  # focal-seizures-without-loss-of-awareness
    "C0270838": SeizureType.FOCAL_TO_BILATERAL_TONIC_CLONIC,  # secondary-generalised-seizures
    "C0234533": SeizureType.UNKNOWN_ONSET_TONIC_CLONIC,   # generalised-seizures (unspecified motor)
    "C0494475": SeizureType.GENERALIZED_TONIC_CLONIC,     # generalised-tonic-clonic
    "C0270824": SeizureType.GENERALIZED_ABSENCE_TYPICAL,  # absence-seizure
    "C0270843": SeizureType.GENERALIZED_MYOCLONIC,        # myoclonic-seizure
    "C0270830": SeizureType.GENERALIZED_ATONIC,           # atonic-seizure
    "C0270817": SeizureType.GENERALIZED_TONIC,            # tonic-seizure
    "C0877017": SeizureType.UNKNOWN_ONSET_TONIC_CLONIC,   # bilateral-convulsive-seizure
    "C0036572": SeizureType.UNCLASSIFIED,                 # generic "seizure"
}


# Etiology keyword classifier — text (usually EpilepsyCause CUIPhrase) → EtiologyCategory
ETIOLOGY_KEYWORDS: list[tuple[re.Pattern[str], EtiologyCategory]] = [
    (re.compile(r"stroke|infarct|haemorrhage|hemorrhage|vascular|arteriovenous|cavernoma",
                re.IGNORECASE), EtiologyCategory.STRUCTURAL),
    (re.compile(r"trauma|tbi|traumatic[ -]brain[ -]injury|head[ -]injury",
                re.IGNORECASE), EtiologyCategory.STRUCTURAL),
    (re.compile(r"sclerosis|dysplasia|malformation|encephalomalacia|gliosis|"
                r"tumou?r|neoplasm|glioma|meningioma|perinatal[ -]insult|"
                r"hippocamp|cortical|tuberous|polymicrogyria|heterotopia",
                re.IGNORECASE), EtiologyCategory.STRUCTURAL),
    (re.compile(r"gene[ -]mutation|genetic|hereditary|de[ -]novo[ -]variant|"
                r"scn1a|scn2a|kcnq2|cdkl5|depdc5|stxbp1|arghap|arhgap",
                re.IGNORECASE), EtiologyCategory.GENETIC),
    (re.compile(r"autoimmune|antibod|paraneoplast|encephalit|nmdar|lgi1|caspr2|gad65|sox1",
                re.IGNORECASE), EtiologyCategory.IMMUNE),
    (re.compile(r"neurocysticerc|hsv|herpes|meningit|viral|bacterial|malaria",
                re.IGNORECASE), EtiologyCategory.INFECTIOUS),
    (re.compile(r"metabolic|mitochondrial|glycine|pyridoxine|amino[ -]acid",
                re.IGNORECASE), EtiologyCategory.METABOLIC),
]


STATUS_PATTERNS: list[tuple[re.Pattern[str], MedicationStatus]] = [
    (re.compile(r"\b(rash|adverse|side[ -]effect|reaction|allergic|allergy|not[ -]tolerated)\b",
                re.IGNORECASE), MedicationStatus.DISCONTINUED_ADVERSE_EFFECT),
    (re.compile(r"\b(failed|did[ -]not[ -]respond|inadequate[ -]control|ineffective|"
                r"discontinued|stopped|withdrawn|weaned[ -]off|tapered[ -]off)\b",
                re.IGNORECASE), MedicationStatus.FAILED),
    (re.compile(r"\b(previous|prior|past|previously[ -]tried|used[ -]to[ -]take|was[ -]on)\b",
                re.IGNORECASE), MedicationStatus.PRIOR),
]


TIME_PERIOD_MAP: dict[str, str] = {
    "Day": "day", "day": "day", "Days": "day", "days": "day",
    "Week": "week", "Weeks": "week", "week": "week", "weeks": "week",
    "Month": "month", "Months": "month", "month": "month", "months": "month",
    "Year": "year", "Years": "year", "year": "year", "years": "year",
}


AGE_UNIT_TO_YEARS: dict[str, float] = {
    "Year": 1.0, "Years": 1.0, "year": 1.0, "years": 1.0,
    "Month": 1/12, "Months": 1/12, "month": 1/12, "months": 1/12,
    "Day": 1/365.25, "Days": 1/365.25, "day": 1/365.25, "days": 1/365.25,
    "Week": 1/52.14, "Weeks": 1/52.14,
}


YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class Ann:
    entity: str
    start: int
    end: int
    text: str
    attributes: dict[str, str]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Ann":
        return cls(
            entity=d["entity"],
            start=int(d["start_index"]),
            end=int(d["end_index"]),
            text=d.get("text", ""),
            attributes=d.get("attributes", {}) or {},
        )


def _ev_dict(value: Any, evidence_text: str | None, doc: DocumentMetadata,
             certainty: str = "definite", temporal: str = "current",
             char_start: int | None = None, char_end: int | None = None) -> dict[str, Any]:
    """Build a JSON-serializable Evidence dict."""
    if hasattr(value, "value"):  # str Enum
        value = value.value
    d = {
        "value": value,
        "certainty": certainty,
        "temporal_status": temporal,
        "evidence_text": evidence_text,
        "source_doc_id": doc.doc_id,
        "source_doc_type": doc.doc_type.value,
        "source_date": doc.doc_date.isoformat(),
    }
    if char_start is not None and char_end is not None:
        d["char_start"] = char_start
        d["char_end"] = char_end
    return d


def _null_ev(doc: DocumentMetadata) -> dict[str, Any]:
    return {
        "value": None, "certainty": "not_documented",
        "temporal_status": "unspecified", "evidence_text": None,
        "source_doc_id": doc.doc_id, "source_doc_type": doc.doc_type.value,
        "source_date": doc.doc_date.isoformat(),
    }


def _span(letter: str, start: int, end: int) -> str:
    """Return the letter's substring in [start, end), cleaned of leading/trailing WS."""
    return letter[start:end].strip()


def _first_year_date(letter: str) -> date:
    """Best-effort: first 4-digit year 19xx/20xx mentioned in the letter."""
    m = YEAR_RE.search(letter)
    if m:
        try:
            return date(int(m.group(0)), 1, 1)
        except ValueError:
            pass
    return date(2024, 1, 1)   # sensible fallback tied to Fonferko-Shadrach publication year


def _infer_status(letter: str, ann: Ann) -> MedicationStatus:
    """Look ±100 chars around the annotation for status indicators."""
    window = letter[max(0, ann.start - 100):min(len(letter), ann.end + 100)]
    for pat, status in STATUS_PATTERNS:
        if pat.search(window):
            return status
    return MedicationStatus.CURRENT


def _classify_etiology(text: str) -> EtiologyCategory:
    for pat, cat in ETIOLOGY_KEYWORDS:
        if pat.search(text):
            return cat
    return EtiologyCategory.UNKNOWN


def _age_at_onset_years(ann: Ann) -> Optional[float]:
    attrs = ann.attributes
    unit = attrs.get("AgeUnit") or "Year"
    scale = AGE_UNIT_TO_YEARS.get(unit, 1.0)
    if "Age" in attrs:
        try:
            return float(attrs["Age"]) * scale
        except ValueError:
            pass
    lo = attrs.get("AgeLower")
    hi = attrs.get("AgeUpper")
    if lo and hi:
        try:
            return (float(lo) + float(hi)) / 2 * scale
        except ValueError:
            pass
    if lo:
        try:
            return float(lo) * scale
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Module builders
# ---------------------------------------------------------------------------


def _build_medication_module(letter: str, anns: list[Ann],
                             doc: DocumentMetadata) -> dict[str, Any]:
    current_asms: list[dict[str, Any]] = []
    prior_asms: list[dict[str, Any]] = []
    failed_asms: list[dict[str, Any]] = []

    for a in anns:
        if a.entity != "Prescription":
            continue
        attrs = a.attributes
        drug = attrs.get("DrugName") or attrs.get("CUIPhrase") or ""
        drug = drug.replace("-", " ").strip().lower()
        if not drug:
            continue

        # Dose text: try to reconstruct from attributes; else grab the span
        parts: list[str] = []
        if attrs.get("DrugDose"):
            parts.append(str(attrs["DrugDose"]))
        if attrs.get("DoseUnit"):
            parts.append(str(attrs["DoseUnit"]))
        if attrs.get("Frequency"):
            parts.append(f"× {attrs['Frequency']}/day")
        dose_text = " ".join(parts) if parts else None

        status = _infer_status(letter, a)
        span = _span(letter, a.start, a.end)

        med_dict = {
            "generic_name": drug,
            "status": status.value,
            "dose_text": dose_text,
            "reason_discontinued": None,
            "rxnorm_cui": None,
        }
        ev = _ev_dict(
            value=med_dict,
            evidence_text=span,
            doc=doc,
            temporal={"current": "current", "prior": "historical",
                      "failed": "historical", "discontinued_adverse_effect": "historical",
                      "planned": "planned"}[status.value],
            char_start=a.start, char_end=a.end,
        )
        if status == MedicationStatus.CURRENT:
            current_asms.append(ev)
        elif status == MedicationStatus.PRIOR:
            prior_asms.append(ev)
        else:
            failed_asms.append(ev)

    return {
        "current_asms": current_asms,
        "prior_asms": prior_asms,
        "failed_asms": failed_asms,
        "adverse_effects_text": _null_ev(doc),
        "drug_resistance_status": _null_ev(doc),
        "surgery_history": [],
        "non_drug_therapies": [],
    }


def _build_clinical_seizure_module(letter: str, anns: list[Ann],
                                   doc: DocumentMetadata) -> dict[str, Any]:
    # Epilepsy type from the first Diagnosis with DiagCategory=Epilepsy
    epi_type_ev: dict[str, Any] = _null_ev(doc)
    for a in anns:
        if a.entity != "Diagnosis" or a.attributes.get("DiagCategory", "").lower() != "epilepsy":
            continue
        cui = a.attributes.get("CUI", "")
        mapped = CUI_TO_EPILEPSY_TYPE.get(cui)
        if mapped is None:
            continue
        epi_type_ev = _ev_dict(mapped, _span(letter, a.start, a.end), doc,
                               char_start=a.start, char_end=a.end)
        break

    # Predominant seizure type from Diagnosis DiagCategory=MultipleSeizures / SingleSeizure
    seizure_type_ev: dict[str, Any] = _null_ev(doc)
    other_seizure_types: list[dict[str, Any]] = []
    first = True
    for a in anns:
        if a.entity != "Diagnosis":
            continue
        dc = a.attributes.get("DiagCategory", "").lower()
        if dc not in ("multipleseizures", "singleseizure"):
            continue
        cui = a.attributes.get("CUI", "")
        mapped = CUI_TO_SEIZURE_TYPE.get(cui)
        if mapped is None:
            continue
        ev = _ev_dict(mapped, _span(letter, a.start, a.end), doc,
                      char_start=a.start, char_end=a.end)
        if first:
            seizure_type_ev = ev
            first = False
        else:
            other_seizure_types.append(ev)

    # Seizure frequency from SeizureFrequency entities
    frequency_ev: dict[str, Any] = _null_ev(doc)
    other_frequencies: list[dict[str, Any]] = []
    seen_freq = False
    for a in anns:
        if a.entity != "SeizureFrequency":
            continue
        attrs = a.attributes
        raw = _span(letter, a.start, a.end)
        period = TIME_PERIOD_MAP.get(attrs.get("TimePeriod", ""), "unspecified")
        lo = attrs.get("LowerNumberOfSeizures")
        hi = attrs.get("UpperNumberOfSeizures") or lo
        seizure_free = False
        # ExECT flags "seizure-free" via NumberOfSeizures=0 or similar; heuristic on text
        if re.search(r"seizure[ -]free", raw, re.IGNORECASE):
            seizure_free = True
        freq_obj: dict[str, Any] = {
            "raw_text": raw or "unspecified",
            "period": period,
            "count_min": float(lo) if lo else None,
            "count_max": float(hi) if hi else None,
            "seizure_free": seizure_free,
            "duration_text": None,
            "applies_to_type": None,
        }
        ev = _ev_dict(freq_obj, raw, doc, char_start=a.start, char_end=a.end)
        if not seen_freq:
            frequency_ev = ev
            seen_freq = True
        else:
            other_frequencies.append(ev)

    # Age at onset
    age_ev: dict[str, Any] = _null_ev(doc)
    for a in anns:
        if a.entity != "Onset":
            continue
        yrs = _age_at_onset_years(a)
        if yrs is None:
            continue
        age_ev = _ev_dict(round(yrs, 2), _span(letter, a.start, a.end), doc,
                          char_start=a.start, char_end=a.end)
        break

    # Etiology from EpilepsyCause (first one)
    etiology_cat_ev: dict[str, Any] = _null_ev(doc)
    etiology_details_ev: dict[str, Any] = _null_ev(doc)
    for a in anns:
        if a.entity != "EpilepsyCause":
            continue
        text = a.attributes.get("CUIPhrase") or _span(letter, a.start, a.end)
        text = text.replace("-", " ").strip()
        cat = _classify_etiology(text)
        etiology_cat_ev = _ev_dict(cat, _span(letter, a.start, a.end), doc,
                                   char_start=a.start, char_end=a.end)
        etiology_details_ev = _ev_dict(text, _span(letter, a.start, a.end), doc,
                                       char_start=a.start, char_end=a.end)
        break

    # Semiology: first PatientHistory of decent length as free-text bag
    semiology_ev: dict[str, Any] = _null_ev(doc)
    for a in anns:
        if a.entity != "PatientHistory":
            continue
        span = _span(letter, a.start, a.end)
        if len(span) < 8:
            continue
        semiology_ev = _ev_dict(span, span, doc, char_start=a.start, char_end=a.end)
        break

    return {
        "epilepsy_type": epi_type_ev,
        "predominant_seizure_type": seizure_type_ev,
        "other_seizure_types": other_seizure_types,
        "awareness": _null_ev(doc),
        "semiology_text": semiology_ev,
        "age_at_onset_years": age_ev,
        "seizure_frequency": frequency_ev,
        "other_seizure_frequencies": other_frequencies,
        "status_epilepticus_history": _null_ev(doc),
        "etiology_category": etiology_cat_ev,
        "etiology_details_text": etiology_details_ev,
        "etiology_specifics": _null_ev(doc),
        "focal_motor_onset": _null_ev(doc),
        "focal_nonmotor_onset": _null_ev(doc),
    }


# ---------------------------------------------------------------------------
# Per-letter conversion
# ---------------------------------------------------------------------------


def convert_letter(letter_id: str) -> tuple[Optional[dict[str, Any]], list[str]]:
    """Convert one letter. Returns (record_or_None, warnings)."""
    warnings: list[str] = []
    letter_path = LETTERS_DIR / f"{letter_id}.txt"
    ann_path = JSON_DIR / f"{letter_id}.json"
    if not letter_path.exists() or not ann_path.exists():
        return None, [f"missing letter or annotations: {letter_id}"]

    letter = letter_path.read_text(encoding="utf-8")
    raw_anns = json.loads(ann_path.read_text(encoding="utf-8"))
    anns = [Ann.from_dict(x) for x in raw_anns]

    doc = DocumentMetadata(
        doc_id=letter_id,
        doc_type=DocumentType.PROGRESS_NOTE,       # closest fit for clinic letters
        doc_date=_first_year_date(letter),
        patient_id=letter_id,                       # 1 letter ≈ 1 synthetic patient
        icd10cm_codes=[],
        snomed_ct_codes=[],
    )

    clinical_seizure = _build_clinical_seizure_module(letter, anns, doc)
    medication = _build_medication_module(letter, anns, doc)

    phenotype_dict = {
        "schema_version": SCHEMA_VERSION,
        "document": {
            "doc_id": doc.doc_id,
            "doc_type": doc.doc_type.value,
            "doc_date": doc.doc_date.isoformat(),
            "patient_id": doc.patient_id,
            "icd10cm_codes": doc.icd10cm_codes,
            "snomed_ct_codes": doc.snomed_ct_codes,
        },
        "clinical_seizure": clinical_seizure,
        "medication": medication,
        "clinical_localization": None,
        "eeg": None,
        "mri": None,
        "integrated": None,
    }

    # Validate — this catches mapping-table errors early
    try:
        EpilepsyPhenotype.model_validate(phenotype_dict)
    except ValidationError as e:
        warnings.append(f"validation error: {str(e)[:300]}")
        return None, warnings

    record = {
        "doc_id": letter_id,
        "doc_type": doc.doc_type.value,
        "patient_id": doc.patient_id,
        "source_text_path": str(letter_path.relative_to(REPO)),
        "provenance": PROVENANCE,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phenotype": phenotype_dict,
    }
    return record, warnings


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def main() -> int:
    if not JSON_DIR.exists():
        print(f"error: {JSON_DIR} not found — run scripts/fetch_fonferko_shadrach.py first",
              file=sys.stderr)
        return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    letter_ids = sorted(p.stem for p in JSON_DIR.glob("*.json"))
    ok = 0
    failed = 0
    warnings_all: list[str] = []
    # per-field population stats
    field_populated = {
        "clinical_seizure.epilepsy_type": 0,
        "clinical_seizure.predominant_seizure_type": 0,
        "clinical_seizure.seizure_frequency": 0,
        "clinical_seizure.age_at_onset_years": 0,
        "clinical_seizure.etiology_category": 0,
        "clinical_seizure.semiology_text": 0,
        "medication.current_asms.nonempty": 0,
        "medication.prior_asms.nonempty": 0,
        "medication.failed_asms.nonempty": 0,
    }
    status_counter: dict[str, int] = {}
    etiology_counter: dict[str, int] = {}

    for lid in letter_ids:
        rec, warns = convert_letter(lid)
        warnings_all.extend(f"{lid}: {w}" for w in warns)
        if rec is None:
            failed += 1
            continue
        ok += 1
        (OUT_DIR / f"{lid}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")

        ph = rec["phenotype"]
        cs = ph["clinical_seizure"]
        med = ph["medication"]
        if cs["epilepsy_type"]["value"]:
            field_populated["clinical_seizure.epilepsy_type"] += 1
        if cs["predominant_seizure_type"]["value"]:
            field_populated["clinical_seizure.predominant_seizure_type"] += 1
        if cs["seizure_frequency"]["value"]:
            field_populated["clinical_seizure.seizure_frequency"] += 1
        if cs["age_at_onset_years"]["value"] is not None:
            field_populated["clinical_seizure.age_at_onset_years"] += 1
        if cs["etiology_category"]["value"]:
            field_populated["clinical_seizure.etiology_category"] += 1
            etiology_counter[cs["etiology_category"]["value"]] = \
                etiology_counter.get(cs["etiology_category"]["value"], 0) + 1
        if cs["semiology_text"]["value"]:
            field_populated["clinical_seizure.semiology_text"] += 1
        if med["current_asms"]:
            field_populated["medication.current_asms.nonempty"] += 1
        if med["prior_asms"]:
            field_populated["medication.prior_asms.nonempty"] += 1
        if med["failed_asms"]:
            field_populated["medication.failed_asms.nonempty"] += 1
        for asm_list in (med["current_asms"], med["prior_asms"], med["failed_asms"]):
            for e in asm_list:
                s = e["value"]["status"]
                status_counter[s] = status_counter.get(s, 0) + 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_letters": len(letter_ids),
        "n_ok": ok, "n_failed": failed,
        "field_populated": field_populated,
        "medication_status_counter": status_counter,
        "etiology_category_counter": etiology_counter,
        "warnings_sample": warnings_all[:20],
        "target_schema_version": SCHEMA_VERSION,
    }
    (OUT_DIR / "_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Console report
    print(f"\n=== Silver-label conversion summary ({SCHEMA_VERSION}) ===")
    print(f"Letters processed: {len(letter_ids)}   ok={ok}   failed={failed}")
    print(f"Silver records written to: {OUT_DIR}")
    print("\nField population (n / 200):")
    for k, v in field_populated.items():
        print(f"  {k:<50} {v:>3}")
    print("\nMedication status counts:")
    for k, v in sorted(status_counter.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<30} {v:>4}")
    print("\nEtiology category counts:")
    for k, v in sorted(etiology_counter.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<15} {v:>4}")
    if warnings_all:
        print(f"\nWarnings: {len(warnings_all)} total (first 5):")
        for w in warnings_all[:5]:
            print(f"  {w}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
