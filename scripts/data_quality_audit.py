#!/usr/bin/env python3
"""Data-quality audit for the fine-tune training/eval corpora.

Produces docs/DATA_QUALITY_AUDIT.md with 5 sections:

  A. Note↔target consistency: 10 random synth-v1 pairs + F-S pair — does
     every value in the target actually appear (or reasonably imply) in
     the note? Manual eyeball reference.
  B. Target field-population %: per Evidence field, what fraction of
     training targets have a real value vs certainty=not_documented.
  C. Enum-value distribution across pilot / synth-v1 / F-S — checks
     for train↔eval distribution shift.
  D. PATIENT_ID prompt-line consistency: does the format we augment at
     TRAIN match what the runner emits at INFERENCE?
  E. Prompt-template drift: side-by-side of the training prompt template
     vs a runner-constructed prompt for the same field.

No compute needed — pure inspection.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

SYNTH_DOCS = REPO / "data" / "episynth_corpus" / "v1" / "documents"
SYNTH_TARGETS = REPO / "data" / "episynth_corpus" / "v1" / "targets"
FS_DOCS = REPO / "data" / "fs_corpus" / "documents"
FS_TARGETS = REPO / "data" / "fs_corpus" / "targets"
PILOT_TARGETS = REPO / "data" / "episynth_pilot" / "run_001" / "targets"
OUT_MD = REPO / "docs" / "DATA_QUALITY_AUDIT.md"


# Fields we care about (matching the 8 ILAE fields the scorer touches)
CORE_FIELDS = [
    ("clinical_seizure", "epilepsy_type"),
    ("clinical_seizure", "predominant_seizure_type"),
    ("clinical_seizure", "age_at_onset_years"),
    ("clinical_seizure", "etiology_category"),
    ("clinical_seizure", "seizure_frequency"),
    ("medication", "drug_resistance_status"),
    ("eeg", "background"),
    ("mri", "findings"),
]


def _load_target(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _load_note(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def _target_field_value(t: dict, module: str, field: str):
    """Return the .value field of the Evidence at t[module][field], or None."""
    if not isinstance(t, dict): return None
    m = t.get(module)
    if not isinstance(m, dict): return None
    ev = m.get(field)
    if isinstance(ev, list):
        # E.g. findings — return the first list-element's value
        if ev and isinstance(ev[0], dict):
            return ev[0].get("value")
        return None
    if not isinstance(ev, dict): return None
    return ev.get("value")


def _target_field_certainty(t: dict, module: str, field: str):
    m = (t or {}).get(module)
    if not isinstance(m, dict): return None
    ev = m.get(field)
    if isinstance(ev, list):
        if ev and isinstance(ev[0], dict):
            return ev[0].get("certainty")
        return None
    if not isinstance(ev, dict): return None
    return ev.get("certainty")


def _iter_pairs(corpus: str):
    """Yield (pid, note_path, target_path) triples for pilot / synth-v1 / fs."""
    if corpus == "pilot":
        pilot_run = REPO / "data" / "episynth_pilot" / "run_001"
        for arm_dir in sorted(pilot_run.iterdir()):
            if not arm_dir.is_dir() or arm_dir.name in ("g2", "targets"):
                continue
            if arm_dir.name == "C0":
                for pd in arm_dir.iterdir():
                    if pd.is_dir() and (pd / "output.txt").exists():
                        yield (pd.name, pd / "output.txt",
                               PILOT_TARGETS / pd.name / "target_phenotype.json")
            else:
                for cond in arm_dir.iterdir():
                    if not cond.is_dir(): continue
                    for pd in cond.iterdir():
                        if pd.is_dir() and (pd / "output.txt").exists():
                            yield (pd.name, pd / "output.txt",
                                   PILOT_TARGETS / pd.name / "target_phenotype.json")
    elif corpus == "synth-v1":
        for pd in sorted(SYNTH_DOCS.iterdir()):
            if not pd.is_dir(): continue
            for dt in pd.iterdir():
                if not dt.is_dir(): continue
                out = dt / "output.txt"
                if out.exists():
                    yield (pd.name, out,
                           SYNTH_TARGETS / pd.name / "target_phenotype.json")
    elif corpus == "fs":
        for pd in sorted(FS_DOCS.iterdir()):
            if not pd.is_dir(): continue
            for dt in pd.iterdir():
                if not dt.is_dir(): continue
                out = dt / "output.txt"
                if out.exists():
                    yield (pd.name, out,
                           FS_TARGETS / pd.name / "target_phenotype.json")


# =========================================================================
# Audit A — note ↔ target consistency (manual eyeball anchors)
# =========================================================================

def audit_a_note_target_consistency(rng: random.Random, out: list) -> None:
    out.append("## A. Note ↔ target consistency\n")
    out.append("Ten random (note, target) pairs. Read each and judge: "
               "does every non-null Evidence value in the target appear "
               "somewhere in the note text?\n")

    for corpus, n_samples in (("synth-v1", 7), ("fs", 3)):
        pairs = list(_iter_pairs(corpus))
        picked = rng.sample(pairs, min(n_samples, len(pairs)))
        for pid, note_p, target_p in picked:
            note = _load_note(note_p) or ""
            t = _load_target(target_p) or {}
            out.append(f"### Sample: `{corpus}/{pid}`\n")
            out.append("**Note (first 500 chars):**")
            out.append(f"```\n{note[:500]}{'…' if len(note)>500 else ''}\n```")
            populated = []
            for mod, fld in CORE_FIELDS:
                v = _target_field_value(t, mod, fld)
                if v is not None:
                    val_short = str(v)
                    if len(val_short) > 80: val_short = val_short[:80] + "…"
                    populated.append(f"  - `{mod}.{fld}`: **{val_short}**")
            out.append("**Target populated values:**")
            out.append("\n".join(populated) if populated else "  (all not_documented)")
            out.append("")


# =========================================================================
# Audit B — target field-population %
# =========================================================================

def audit_b_field_population(out: list) -> None:
    out.append("## B. Target field-population percentages\n")
    out.append("For each field, what % of targets have a real value vs "
               "certainty=not_documented? A field that is ~always null "
               "will teach the model to always emit null.\n")

    out.append("| Corpus | Field | n targets | populated | not_documented | % populated |")
    out.append("|---|---|---:|---:|---:|---:|")

    for corpus in ("synth-v1", "fs", "pilot"):
        # For synth/fs use targets dir directly; for pilot use pilot_targets
        target_paths = []
        if corpus == "synth-v1":
            target_paths = list(SYNTH_TARGETS.rglob("target_phenotype.json"))
        elif corpus == "fs":
            target_paths = list(FS_TARGETS.rglob("target_phenotype.json"))
        elif corpus == "pilot":
            target_paths = list(PILOT_TARGETS.rglob("target_phenotype.json"))
        targets = [_load_target(p) for p in target_paths]
        targets = [t for t in targets if t is not None]
        n = len(targets)
        for mod, fld in CORE_FIELDS:
            populated = sum(1 for t in targets if _target_field_value(t, mod, fld) is not None)
            nd = sum(
                1 for t in targets
                if _target_field_certainty(t, mod, fld) == "not_documented"
            )
            pct = 100 * populated / n if n else 0
            out.append(f"| {corpus} | `{mod}.{fld}` | {n} | {populated} | {nd} | {pct:.0f}% |")
    out.append("")


# =========================================================================
# Audit C — enum-value distribution across corpora
# =========================================================================

def audit_c_enum_distributions(out: list) -> None:
    out.append("## C. Enum-value distribution across corpora\n")
    out.append("For fields with populated values, show the value histogram. "
               "Large mismatch between train and pilot/F-S distributions "
               "signals train↔eval shift.\n")

    dist_fields = [
        ("clinical_seizure", "epilepsy_type"),
        ("clinical_seizure", "predominant_seizure_type"),
        ("medication", "drug_resistance_status"),
        ("clinical_seizure", "etiology_category"),
    ]

    for mod, fld in dist_fields:
        out.append(f"### `{mod}.{fld}`\n")
        out.append("| Corpus | Top 5 values (count) |")
        out.append("|---|---|")
        for corpus in ("synth-v1", "fs", "pilot"):
            targets_root = {
                "synth-v1": SYNTH_TARGETS,
                "fs": FS_TARGETS,
                "pilot": PILOT_TARGETS,
            }[corpus]
            paths = list(targets_root.rglob("target_phenotype.json"))
            targets = [_load_target(p) for p in paths]
            counter = Counter()
            for t in targets:
                v = _target_field_value(t, mod, fld)
                if v is not None:
                    counter[str(v)] += 1
            top = ", ".join(f"`{k}` ({v})" for k, v in counter.most_common(5))
            out.append(f"| {corpus} | {top or '(none populated)'} |")
        out.append("")


# =========================================================================
# Audit D — PATIENT_ID prompt-line consistency
# =========================================================================

def audit_d_patient_id_line(out: list) -> None:
    out.append("## D. PATIENT_ID prompt-line consistency (train vs inference)\n")
    out.append("The v2 augmentation training prepends `PATIENT_ID: SYNPID_XXX` "
               "to each training note. Inference must use the identical format.\n")
    # Grep the finetune script
    ft = (REPO / "scripts" / "finetune_lora_epi.py").read_text()
    train_prefix = "unknown"
    for line in ft.splitlines():
        if "PATIENT_ID:" in line and "SYNPID" in line:
            train_prefix = line.strip()
            break
    # Grep the runner script
    rn = (REPO / "scripts" / "run_med42_on_pilot.py").read_text()
    infer_prefix = "unknown"
    for line in rn.splitlines():
        if 'PATIENT_ID:' in line:
            infer_prefix = line.strip()
            break

    out.append(f"**Train-side augmentation line** (finetune_lora_epi.py):\n")
    out.append(f"```python\n{train_prefix}\n```\n")
    out.append(f"**Inference-side prepend line** (run_med42_on_pilot.py):\n")
    out.append(f"```python\n{infer_prefix}\n```\n")
    out.append("Both should emit `PATIENT_ID: <id>\\n\\n<note>`. If they don't, "
               "the adapter's copy-from-prompt mechanism will not fire at inference.\n")


# =========================================================================
# Audit E — prompt-template drift check
# =========================================================================

def audit_e_prompt_template(out: list) -> None:
    out.append("## E. Prompt-template drift check\n")
    out.append("The finetune script uses `PROMPT_TEMPLATE` from "
               "`finetune_lora_epi.py`. The runner uses templates from "
               "`services/prompt_registry.py`. These need to agree on the "
               "'note goes here, phenotype JSON here' structure.\n")

    ft = (REPO / "scripts" / "finetune_lora_epi.py").read_text()
    # extract PROMPT_TEMPLATE
    tmpl = ""
    in_tmpl = False
    for line in ft.splitlines():
        if line.strip().startswith("PROMPT_TEMPLATE") and "=" in line:
            in_tmpl = True
            tmpl += line + "\n"
            continue
        if in_tmpl:
            tmpl += line + "\n"
            if line.strip().endswith(")"):
                break

    out.append("**Training prompt template** (`finetune_lora_epi.py::PROMPT_TEMPLATE`):\n")
    out.append(f"```python\n{tmpl.strip()}\n```\n")

    # Inference-side: the actual prompt engine uses arm-specific templates
    # from services/prompt_registry.py. Show the M0 clinical_seizure template.
    out.append("**Inference prompts** are constructed per-arm/module in "
               "`services/prompt_registry.py`. They are *different* from "
               "the training PROMPT_TEMPLATE — they include few-shot "
               "examples (M1) or schema fragments (M2), and always emit "
               "one *module* JSON at a time, not the full EpilepsyPhenotype.\n")
    out.append("**⚠ Potential mismatch**: training targets are the FULL "
               "`EpilepsyPhenotype` (all modules in one JSON), but inference "
               "prompts ask for ONE module (e.g. `ClinicalSeizureModule`). "
               "The `smart_repair.py` unwrap fix (commit `e158d51`) is what "
               "reconciles the mismatch by extracting the requested inner "
               "module from a full-phenotype emission. If we ever remove that "
               "fix, all tuned outputs will fail validation again.\n")


# =========================================================================
# main
# =========================================================================

def main() -> None:
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0)
    out = [
        "# Data-quality audit — MedAI-EPI training/eval corpora\n",
        "*Generated by `scripts/data_quality_audit.py`. No compute; "
        "inspection of committed data + code only.*\n",
        "This report checks (A) note↔target consistency, (B) target "
        "field-population %, (C) enum-value distributions across corpora, "
        "(D) PATIENT_ID prompt-line consistency, (E) prompt-template drift.\n",
        "---\n",
    ]
    audit_a_note_target_consistency(rng, out)
    out.append("---\n")
    audit_b_field_population(out)
    out.append("---\n")
    audit_c_enum_distributions(out)
    out.append("---\n")
    audit_d_patient_id_line(out)
    out.append("---\n")
    audit_e_prompt_template(out)
    OUT_MD.write_text("\n".join(out))
    print(f"wrote {OUT_MD}")


if __name__ == "__main__":
    main()
