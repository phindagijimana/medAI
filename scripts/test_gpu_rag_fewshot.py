#!/usr/bin/env python3
"""
Verify inference stack: GPU (PyTorch CUDA), RAG, and few-shot.

  USE_RAG=1 USE_FEW_SHOT=1 APP_HOME=$(pwd) python3 scripts/test_gpu_rag_fewshot.py

GPU: requires NVIDIA drivers + CUDA-enabled PyTorch on the machine. If CUDA is
unavailable, the script still tests RAG and few-shot and exits 0 with a clear
[SKIP] for GPU.

Exit 0 — RAG + few-shot OK (GPU section either OK or skipped)
Exit 1 — RAG or few-shot failure
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("APP_HOME", ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Defaults match app.py — explicit for the test harness
os.environ.setdefault("USE_RAG", "1")
os.environ.setdefault("USE_FEW_SHOT", "1")


def _gpu_section() -> list[str]:
    lines: list[str] = ["--- GPU (PyTorch) ---"]
    try:
        import torch
    except ImportError as e:
        lines.append(f"[FAIL] PyTorch not importable: {e}")
        return lines

    ok = torch.cuda.is_available()
    lines.append(f"torch.cuda.is_available(): {ok}")
    if ok:
        lines.append(f"device_count: {torch.cuda.device_count()}")
        lines.append(f"device 0: {torch.cuda.get_device_name(0)}")
        lines.append("[OK] GPU available for this process (Med42 can use cuda).")
    else:
        lines.append(
            "[SKIP] No CUDA device — run on a GPU node with NVIDIA drivers and "
            "a CUDA build of PyTorch to exercise GPU inference."
        )
    return lines


def _inference_augmentation_flags() -> tuple[bool, bool]:
    """Same rules as app.inference_augmentation_flags() — avoid importing Flask app."""
    use_rag = os.environ.get("USE_RAG", "1").lower() not in ("0", "false", "no")
    use_fs = os.environ.get("USE_FEW_SHOT", "1").lower() not in ("0", "false", "no")
    return use_rag, use_fs


def _flags_section() -> list[str]:
    lines = ["--- Env flags (USE_RAG / USE_FEW_SHOT) ---"]
    ur, ufs = _inference_augmentation_flags()
    lines.append(f"USE_RAG effective: {ur}")
    lines.append(f"USE_FEW_SHOT effective: {ufs}")
    if ur and ufs:
        lines.append("[OK] Both augmentation paths enabled.")
    else:
        lines.append("[WARN] One or both disabled via environment.")
    return lines


def _rag_section() -> tuple[list[str], bool]:
    lines = ["--- RAG ---"]
    from utils.rag_system import get_rag_system

    r = get_rag_system()
    if not r.available:
        lines.append(f"[FAIL] RAG unavailable: {getattr(r, '_error', '?')}")
        return lines, False
    text = r.retrieve("acute ischemic stroke IV alteplase", "stroke", 2)
    if "RELEVANT GUIDELINE" not in text:
        lines.append("[FAIL] RAG output missing expected header.")
        return lines, False
    lines.append("[OK] RAG retrieve returned guideline text.")
    lines.append(f"preview: {text[:240].replace(chr(10), ' ')}...")
    return lines, True


def _fewshot_section() -> tuple[list[str], bool]:
    lines = ["--- Few-shot ---"]
    from utils.few_shot_loader import FewShotExampleLoader

    fs = FewShotExampleLoader()
    ex = fs.get_examples_by_condition("epilepsy", 2, "classification")
    if len(ex) < 1:
        lines.append("[FAIL] No epilepsy few-shot examples.")
        return lines, False
    lines.append(f"[OK] Loaded {len(ex)} epilepsy example(s) for classification.")
    return lines, True


def main() -> int:
    print("Inference stack test (GPU + RAG + few-shot)\n")
    for block in (_gpu_section(), _flags_section()):
        for line in block:
            print(line)
        print()

    ok_rag = ok_fs = False
    for name, fn in (("RAG", _rag_section), ("Few-shot", _fewshot_section)):
        lines, ok = fn()
        for line in lines:
            print(line)
        print()
        if name == "RAG":
            ok_rag = ok
        else:
            ok_fs = ok

    if ok_rag and ok_fs:
        print("SUMMARY: [OK] RAG and few-shot verified.")
        return 0
    print("SUMMARY: [FAIL] Fix RAG or few-shot errors above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
