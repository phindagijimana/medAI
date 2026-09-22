#!/usr/bin/env python3
"""Analyze the Fonferko-Shadrach 2024 (ExECT-v2) annotation schema against
our MedAI-EPI EpilepsyPhenotype (`schema/`).

Walks all 200 gold JSON annotation files, enumerates entity types + attributes,
counts frequencies, and reports:
  - Which ExECT-v2 entities map DIRECTLY to fields on our schema
  - Which map PARTIALLY (same concept, different granularity)
  - Which have NO equivalent in our schema (candidate gap for v0.3)
  - Which of our schema fields have NO source in ExECT-v2 (their labels
    won't populate that field — informative for scoping the pilot)

Prints a table and writes docs/FONFERKO_SHADRACH_MAPPING.md.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JSON_DIR = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_8356494" / "Json"
CSV_DIR  = REPO / "data" / "fonferko_shadrach_2024" / "zenodo_12520180"
OUT_MD   = REPO / "docs" / "FONFERKO_SHADRACH_MAPPING.md"


# Manual mapping table: ExECT-v2 entity → our schema module.field.
# "direct" means the concept aligns 1:1 with a MedAI-EPI field.
# "partial" means the concept overlaps but granularity or scope differs.
# "no_equivalent" means we don't extract this in v0.2.1.
MAPPING: dict[str, dict[str, str]] = {
    "Diagnosis": {
        "verdict": "partial",
        "our_field": "ClinicalSeizureModule.epilepsy_type + .predominant_seizure_type",
        "notes": (
            "ExECT-v2 uses a DiagCategory attribute (Epilepsy / MultipleSeizures / …). "
            "Fine-grained ILAE seizure/epilepsy type mapping requires post-processing the "
            "UMLS CUI and DiagCategory. Feasible via a lookup table."
        ),
    },
    "Prescription": {
        "verdict": "direct",
        "our_field": "MedicationModule.current_asms / prior_asms / failed_asms",
        "notes": (
            "DrugName, DrugDose, DoseUnit, Frequency all present as attributes. "
            "Status (current vs prior vs failed) is not attributed — must infer "
            "from letter context or leave as CURRENT."
        ),
    },
    "SeizureFrequency": {
        "verdict": "direct",
        "our_field": "ClinicalSeizureModule.seizure_frequency",
        "notes": (
            "LowerNumberOfSeizures + UpperNumberOfSeizures + TimePeriod map cleanly "
            "to our count_min/count_max/period. No duration or per-type qualifier."
        ),
    },
    "Investigations": {
        "verdict": "partial",
        "our_field": "MriModule / EegModule (imaging + neurophysiology sub-selection)",
        "notes": (
            "ExECT-v2 flattens all imaging/EEG under 'Investigations' with CT/MRI/EEG "
            "sub-flags. Requires post-processing to route into the right module."
        ),
    },
    "Onset": {
        "verdict": "direct",
        "our_field": "ClinicalSeizureModule.age_at_onset_years",
        "notes": "Age-at-onset concept; free-text or YearDate attribute for year of onset.",
    },
    "PatientHistory": {
        "verdict": "partial",
        "our_field": "ClinicalSeizureModule.semiology_text / .status_epilepticus_history / etiology_details_text",
        "notes": (
            "Broad free-text bucket. UMLS CUI can hint at semiology vs etiology; requires "
            "manual/heuristic partition into our sub-fields."
        ),
    },
    "EpilepsyCause": {
        "verdict": "direct",
        "our_field": "ClinicalSeizureModule.etiology_category + .etiology_details_text",
        "notes": (
            "Their 'EpilepsyCause' entity maps directly to our etiology fields. Free "
            "text with UMLS CUI; would need a controlled-vocabulary layer to derive "
            "our 6-category EtiologyCategory enum from the CUI."
        ),
    },
    "BirthHistory": {
        "verdict": "no_equivalent",
        "our_field": "—",
        "notes": (
            "Birth history / obstetric complications — not in our v0.2.1 schema. "
            "Includes a PrematureBirth attribute. Could inform etiology (perinatal "
            "insult → structural) but requires a new slot. Candidate for v0.3."
        ),
    },
    "WhenDiagnosed": {
        "verdict": "no_equivalent",
        "our_field": "—",
        "notes": (
            "Year/age at diagnosis. Distinct from age-at-onset. Our schema captures "
            "onset but not date of diagnosis. Low priority — usually derivable from "
            "document date."
        ),
    },
}


# ExECT-v2 attributes we track separately (per-attribute frequency).
KEY_ATTRIBUTES = (
    "DiagCategory", "Certainty", "Negation",
    "DrugName", "DrugDose", "DoseUnit", "Frequency",
    "LowerNumberOfSeizures", "UpperNumberOfSeizures", "TimePeriod", "NumberOfTimePeriods",
    "CT_Performed", "CT_Results", "MRI_Performed", "MRI_Results",
    "EEG_Performed", "EEG_Results", "YearDate",
    "CUI", "CUIPhrase",
)


def _load_all() -> list[list[dict]]:
    files = sorted(JSON_DIR.glob("*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def _entity_stats(all_anns: list[list[dict]]) -> tuple[Counter, dict[str, Counter]]:
    """Return (entity_counts, per_entity_attribute_counts)."""
    entities: Counter = Counter()
    attrs: dict[str, Counter] = {}
    for doc in all_anns:
        for ann in doc:
            e = ann["entity"]
            entities[e] += 1
            attr_bag = ann.get("attributes", {}) or {}
            attrs.setdefault(e, Counter()).update(attr_bag.keys())
    return entities, attrs


def _attribute_values(all_anns: list[list[dict]], entity: str, attr: str) -> Counter:
    c: Counter = Counter()
    for doc in all_anns:
        for ann in doc:
            if ann["entity"] != entity:
                continue
            v = (ann.get("attributes") or {}).get(attr)
            if v is not None:
                c[str(v)] += 1
    return c


def _our_schema_fields_missing_from_exect() -> list[str]:
    """Fields in our v0.2.1 schema for which ExECT-v2 has no natural source."""
    return [
        "ClinicalSeizureModule.awareness",
        "ClinicalSeizureModule.focal_motor_onset",
        "ClinicalSeizureModule.focal_nonmotor_onset",
        "ClinicalSeizureModule.etiology_specifics.causative_gene",
        "ClinicalSeizureModule.etiology_specifics.causative_variant",
        "ClinicalSeizureModule.etiology_specifics.causative_antibody",
        "ClinicalSeizureModule.etiology_specifics.associated_tumor_text",
        "ClinicalSeizureModule.etiology_specifics.causative_pathogen_text",
        "ClinicalSeizureModule.etiology_specifics.causative_metabolic_text",
        "MedicationModule.drug_resistance_status",
        "MedicationModule.surgery_history.engel_class",
        "MedicationModule.surgery_history.ilae_outcome",
        "MedicationModule.non_drug_therapies",
        "EegModule.study_type",
        "EegModule.background",
        "EegModule.ied_findings.dominant_frequency_hz",
        "EegModule.ictal_onset_lobe",
        "EegModule.ictal_onset_laterality",
        "MriModule.field_strength_tesla",
        "MriModule.findings (specific enum members: MOGHE, FCD Palmini I/IIa/IIb, HS, …)",
        "MriModule.lesion_lobe",
        "MriModule.lesion_laterality",
        "IntegratedPhenotypeModule.concordance",
        "IntegratedPhenotypeModule.*_localization",
    ]


def main() -> int:
    if not JSON_DIR.exists():
        print(f"error: {JSON_DIR} does not exist — run fetch_fonferko_shadrach.py first",
              file=sys.stderr)
        return 2

    anns = _load_all()
    entity_counts, per_entity_attrs = _entity_stats(anns)

    # ---- Print & collect for report ----
    print(f"Loaded {len(anns)} documents.")
    total_anns = sum(entity_counts.values())
    print(f"Total annotations: {total_anns}")
    print(f"Entity types: {len(entity_counts)}\n")

    # Entity-frequency table
    print("Entity frequencies:")
    for ent, n in entity_counts.most_common():
        print(f"  {ent:<20} n={n:>5}  attrs={sorted(per_entity_attrs[ent])}")

    # Attribute-value distributions for the interesting cases
    print("\nDiagCategory value distribution:")
    for v, n in _attribute_values(anns, "Diagnosis", "DiagCategory").most_common():
        print(f"  {v:<30} n={n:>4}")
    print("\nTimePeriod value distribution (SeizureFrequency):")
    for v, n in _attribute_values(anns, "SeizureFrequency", "TimePeriod").most_common():
        print(f"  {v:<10} n={n:>4}")

    # ---- Write mapping report ----
    lines: list[str] = []
    lines.append("# ExECT-v2 (Fonferko-Shadrach 2024) → MedAI-EPI v0.2.1 mapping\n")
    lines.append(
        "Generated by `scripts/analyze_fonferko_schema.py`. Regenerate whenever\n"
        "either schema changes.\n"
    )
    lines.append("## Corpus statistics\n")
    lines.append(f"- Documents: **{len(anns)}**")
    lines.append(f"- Total annotations: **{total_anns}**")
    lines.append(f"- Distinct entity types: **{len(entity_counts)}**\n")

    lines.append("## Entity coverage\n")
    lines.append("| Entity type | Count | Verdict | Maps to | Notes |")
    lines.append("|---|---:|:---:|---|---|")
    for ent, n in entity_counts.most_common():
        m = MAPPING.get(ent, {"verdict": "unmapped", "our_field": "—",
                              "notes": "Not classified — add to MAPPING in analyzer."})
        verdict = m["verdict"]
        emoji = {"direct": "✅", "partial": "🔶", "no_equivalent": "❌",
                 "unmapped": "❓"}.get(verdict, verdict)
        lines.append(f"| `{ent}` | {n} | {emoji} {verdict} | {m['our_field']} | {m['notes']} |")

    lines.append("\n## Attribute-value distributions\n")
    lines.append("### `Diagnosis.DiagCategory`\n")
    lines.append("| Value | Count |")
    lines.append("|---|---:|")
    for v, n in _attribute_values(anns, "Diagnosis", "DiagCategory").most_common():
        lines.append(f"| `{v}` | {n} |")

    lines.append("\n### `SeizureFrequency.TimePeriod`\n")
    lines.append("| Value | Count |")
    lines.append("|---|---:|")
    for v, n in _attribute_values(anns, "SeizureFrequency", "TimePeriod").most_common():
        lines.append(f"| `{v}` | {n} |")

    lines.append("\n### `Investigations` subtype flags\n")
    for flag in ("CT_Performed", "MRI_Performed", "EEG_Performed"):
        vals = _attribute_values(anns, "Investigations", flag)
        if vals:
            lines.append(f"\n**{flag}**:")
            for v, n in vals.most_common():
                lines.append(f"- `{v}`: {n}")

    lines.append("\n## MedAI-EPI schema fields with no direct ExECT-v2 source\n")
    lines.append(
        "These v0.2.1 fields will not be populated from adapted Fonferko-Shadrach "
        "annotations. They are candidates for annotator focus during the "
        "institutional pilot, or explicit `not_documented` values in the "
        "adapted subset.\n"
    )
    for f in _our_schema_fields_missing_from_exect():
        lines.append(f"- `{f}`")

    lines.append("\n## Practical uses of this corpus in MedAI-EPI\n")
    lines.append(
        "1. **Bootstrap few-shot examples.** Replace hand-written synthetic examples "
        "in `services/prompt_registry.py` with adapted ExECT-v2 letters + annotations. "
        "Adapted example IDs get citation provenance to the Zenodo DOIs.\n"
        "2. **Schema-completeness cross-check.** The gaps table above surfaces v0.2.1 "
        "fields that need active annotator attention (they can't be back-derived).\n"
        "3. **Annotator training material.** Guidelines PDF at `data/fonferko_shadrach_2024/"
        "zenodo_8382589/ExECT V2 .1- What and How of annotating_v9.docx`.\n"
        "4. **External-validation slice (Flagship, §26).** Evaluate our system on "
        "the 200 letters after schema-mapping — reports out-of-institution robustness.\n"
        "5. **Weak-supervision seed for B1 BioClinicalBERT.** The 200 letters + attributes "
        "can train per-field heads for medications, seizure frequency, diagnosis category.\n"
    )
    lines.append("\n## Provenance\n")
    lines.append(
        "- Paper: Fonferko-Shadrach B et al. (2024). *Annotation of epilepsy clinic letters "
        "for natural language processing.* J Biomed Semantics 15:17. "
        "DOI: [10.1186/s13326-024-00316-z](https://doi.org/10.1186/s13326-024-00316-z). "
        "PMCID: PMC11402197.\n"
        "- Zenodo records: 8381080 (corpus), 8356494 (JSON), 8382589 (guidelines), "
        "12520180 (CSV).\n"
        "- License: CC-BY 4.0 (all analyzed records). Attribution required in any "
        "publication using this corpus.\n"
    )

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nreport → {OUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
