#!/usr/bin/env python3
"""Run M0/M1/M2 MRI extraction against real Med42 on one hand-crafted document.

Designed to work whether invoked directly on a GPU node (Med42 loads fast) or
on CPU (works but slow — 30–90s per generation, 3 generations ≈ 3–5 minutes).

Usage:
    python scripts/run_m2_mri_real.py                  # synthetic MRI report
    python scripts/run_m2_mri_real.py --pmc PMC6872800 # excerpt from a PMC case

Outputs manifests under data/run_manifests/<date>/ and prints a comparison line
per arm.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Med42Config
from schema import DocumentMetadata, DocumentType, MriModule, SCHEMA_VERSION
from services.extract import DecodingConfig, extract_module
from services.med42_backend import Med42Backend
from services.med42_model import Med42ModelService
from services.prompt_registry import MRI_M0_V1, MRI_M1_V1, MRI_M2_V1


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("run_m2_mri_real")


# A clean synthetic MRI report — same style as the M1 few-shot example but
# NOT identical. Safe for smoke testing; not for locked eval.
SYNTHETIC_MRI = (
    "MRI BRAIN 3T without contrast — epilepsy protocol.\n"
    "CLINICAL: Refractory focal seizures, evaluate for structural etiology.\n"
    "TECHNIQUE: Axial, coronal, and sagittal T1, T2, FLAIR; DWI; SWI; "
    "high-resolution coronal FLAIR through hippocampi.\n"
    "FINDINGS: There is asymmetric volume loss of the left hippocampus with "
    "T2/FLAIR hyperintensity, consistent with left mesial temporal sclerosis. "
    "The right hippocampus appears normal. No focal cortical dysplasia is "
    "identified. Ventricles are otherwise unremarkable. No mass, no acute "
    "infarct, no hemorrhage. Vessels of the circle of Willis are patent.\n"
    "IMPRESSION: Left hippocampal sclerosis. No other epilepsy-relevant lesion."
)


def load_pmc_mri_excerpt(pmc_id: str) -> str:
    """Extract the MRI-relevant portion from a fetched PMC case narrative.

    PMC case reports are not raw radiology reports — they embed MRI findings in
    prose. We grab the surrounding sentences of any MRI mention. Simple heuristic;
    good enough for a smoke test.
    """
    p = Path(__file__).resolve().parent.parent / "data" / "pmc_cases" / f"{pmc_id}.txt"
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8")
    # Strip the header block
    body = re.split(r"^# ---$", text, maxsplit=1, flags=re.MULTILINE)[-1]
    # Sentences mentioning MRI / hippocamp* / cortical dysplasia / FLAIR
    keep_pat = re.compile(
        r"[^.!?]*(MRI|MR imaging|FLAIR|hippocamp|cortical dysplasia|"
        r"mesial temporal|temporal lobe|T2|sclerosis|lesion|encephalomalacia)"
        r"[^.!?]*[.!?]",
        re.IGNORECASE,
    )
    matches = keep_pat.findall(body)
    # findall returns groups when there's a group; re-run with finditer for full spans
    mri_sentences = [m.group(0).strip() for m in keep_pat.finditer(body)]
    if not mri_sentences:
        raise ValueError(f"No MRI-relevant sentences found in {pmc_id}")
    excerpt = "\n".join(dict.fromkeys(mri_sentences))  # dedupe, preserve order
    return excerpt[:2000]  # keep the prompt tractable


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pmc", type=str, default=None,
                    help="PMC ID to extract MRI content from (e.g. PMC6872800). "
                         "Omit to use the synthetic MRI report.")
    ap.add_argument("--arms", type=str, default="M0,M1,M2",
                    help="Comma-separated arms to run.")
    ap.add_argument("--max-new-tokens", type=int, default=1024)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    # Source document
    if args.pmc:
        text = load_pmc_mri_excerpt(args.pmc)
        doc_id = f"{args.pmc}-mri-excerpt"
        patient_id = f"{args.pmc}-synthetic"
    else:
        text = SYNTHETIC_MRI
        doc_id = "SYN-MRI-eval-001"
        patient_id = "SYN-P-eval-001"

    doc = DocumentMetadata(
        doc_id=doc_id,
        doc_type=DocumentType.MRI_REPORT,
        doc_date=date.today(),
        patient_id=patient_id,
    )
    log.info("Source doc: %s (%d chars)", doc.doc_id, len(text))

    # Load Med42 (long-running on first call)
    config = Med42Config()
    log.info("Loading Med42: %s (cache=%s)", config.model_name, config.model_cache_dir)
    svc = Med42ModelService(config)
    if not svc.load_model():
        log.error("Med42 model load failed: %s", svc.load_error)
        return 2
    log.info("Med42 loaded on %s in %.1fs",
             svc.device, svc.stats.get("model_load_time") or float("nan"))

    backend = Med42Backend(svc)

    # Deterministic decoding for eval
    decoding = DecodingConfig(
        do_sample=False,
        temperature=None,
        top_p=None,
        max_new_tokens=args.max_new_tokens,
        seed=args.seed,
    )

    prompt_by_arm = {"M0": MRI_M0_V1, "M1": MRI_M1_V1, "M2": MRI_M2_V1}
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]

    results = []
    for arm in arms:
        if arm not in prompt_by_arm:
            log.warning("unknown arm %r, skipping", arm)
            continue
        log.info("=== arm %s ===", arm)
        r = extract_module(
            module_cls=MriModule,
            prompt=prompt_by_arm[arm],
            source_text=text,
            source_doc_meta=doc,
            model_backend=backend,
            decoding=decoding,
            schema_version=SCHEMA_VERSION,
        )
        r.manifest.write()
        m = r.manifest
        log.info(
            "arm=%s raw_valid=%s final_valid=%s repair=%s duration=%.1fs tokens=%s",
            m.arm, m.raw_valid, m.final_valid, m.repair_method,
            m.duration_s or 0.0, m.raw_response_tokens,
        )
        results.append((arm, m))

    # Comparison line
    print("\n=== SUMMARY ===")
    print(f"{'arm':<4}  {'raw_valid':<10}  {'final_valid':<12}  {'repair':<28}  {'tokens':<7}  {'duration_s':<10}  hs_extracted")
    for arm, m in results:
        hs = None
        if m.parsed_value:
            hs = m.parsed_value.get("hippocampal_sclerosis", {}).get("value")
        print(
            f"{arm:<4}  {str(m.raw_valid):<10}  {str(m.final_valid):<12}  "
            f"{(m.repair_method or '-'):<28}  {str(m.raw_response_tokens or '-'):<7}  "
            f"{(m.duration_s or 0):<10.2f}  {hs}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
