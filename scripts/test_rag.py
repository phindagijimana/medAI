#!/usr/bin/env python3
"""
Smoke tests for RAG + few-shot loader (no LLM, no Flask server).

Run from repo root:
  APP_HOME=$(pwd) python3 scripts/test_rag.py
"""
import os
import sys

# Repo root = parent of scripts/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("APP_HOME", ROOT)


def main() -> int:
    errors = []

    # 1) RAG retrieve
    from utils.rag_system import get_rag_system

    r = get_rag_system()
    t = ""
    if not r.available:
        errors.append(f"RAG not available: {getattr(r, '_error', '?')}")
    else:
        t = r.retrieve("IV alteplase ischemic stroke within 4.5 hours", "stroke", 2)
        if "stroke_guidelines" not in t and "thrombolysis" not in t.lower():
            errors.append("RAG stroke query: unexpected output")
        if "RELEVANT GUIDELINE" not in t:
            errors.append("RAG: missing header in output")

    # 2) Few-shot loader
    from utils.few_shot_loader import FewShotExampleLoader

    fs = FewShotExampleLoader()
    ex = fs.get_examples_by_condition("epilepsy", 2, "classification")
    if len(ex) < 1:
        errors.append("Few-shot: no epilepsy examples")
    g = fs.get_guideline_context("epilepsy")
    if len(g) < 100:
        errors.append("Guideline context for epilepsy too short")

    if errors:
        print("FAILED:")
        for e in errors:
            print(" ", e)
        return 1

    print("OK — RAG available:", r.available)
    print("OK — few-shot examples (epilepsy):", len(ex))
    print("OK — static guideline chars (epilepsy):", len(g))
    print("OK — RAG preview (stroke):")
    print((t[:500] if t else "(n/a)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
