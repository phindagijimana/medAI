#!/usr/bin/env python3
"""Rerun the three scoring scripts against data/run_manifests_maxtok4096/
by monkey-patching each script's MANIFESTS constant before calling its
main() function. Outputs go to eval/results/*_maxtok4096.{md,json,csv}.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

MANIFESTS_4096 = REPO / "data" / "run_manifests_maxtok4096"
OUT = REPO / "eval" / "results"


def _run(script_module_name: str, out_attr: str, suffix: str) -> None:
    """Import a scorer, patch its MANIFESTS + output-dir attribute so files
    land under *_maxtok4096.{md,json,csv}, then call main()."""
    print(f"\n=== running {script_module_name} on {MANIFESTS_4096.name} ===")
    mod = importlib.import_module(script_module_name)
    mod.MANIFESTS = MANIFESTS_4096

    original_out = getattr(mod, out_attr)
    class _OutProxy:
        def __truediv__(self, name):
            stem, dot, ext = name.rpartition(".")
            new = f"{stem}_{suffix}.{ext}" if dot else name
            return original_out / new
        def mkdir(self, *a, **kw):
            return original_out.mkdir(*a, **kw)
    setattr(mod, out_attr, _OutProxy())
    mod.main()


if __name__ == "__main__":
    _run("scripts.score_llm_arms", "OUT_DIR", "maxtok4096")
    _run("scripts.score_llm_arms_vs_fs_gold", "OUT", "maxtok4096")
    _run("scripts.mcnemar_arm_comparisons", "OUT", "maxtok4096")
