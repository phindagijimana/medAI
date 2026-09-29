"""Pytest configuration for the med42_service test suite.

Ensures the project root is on ``sys.path`` so that first-party modules
(``rules.*``, ``schema.*``, ``services.*``) import cleanly when tests are
run from any working directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
