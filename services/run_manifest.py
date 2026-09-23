"""Per-inference run manifest writer (paper §20, Table 9).

Every extraction run emits one JSON manifest recording:
  - code SHA
  - prompt id + version
  - schema version
  - model identifier and cache path
  - decoding config (temperature, top_p, seed, max_new_tokens)
  - hardware (device, GPU name if any)
  - timestamps (started_at, finished_at, duration_s)
  - source doc id + doc_type
  - raw model response text
  - parsed value (dict, if any)
  - raw_valid (did the very first response parse against the schema?)
  - repair_attempts count
  - repair_method (regex_json_extraction / json_repair / strip_prose / failed)
  - final_valid, final_value

Manifests live under `data/run_manifests/<yyyy-mm-dd>/<uuid>.json` so a
locked test run produces a diffable directory tree that can be attached
as supplementary material.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
# MANIFEST_ROOT can be overridden by the MEDAI_MANIFEST_DIR env var so a
# sensitivity-analysis SLURM run (e.g. max_new_tokens=4096) can write to a
# separate directory without colliding with the baseline manifests.
MANIFEST_ROOT = Path(os.environ.get(
    "MEDAI_MANIFEST_DIR",
    str(REPO_ROOT / "data" / "run_manifests"),
))


def _git_sha_short() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "-C", str(REPO_ROOT), "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
        ).decode()
        return bool(out.strip())
    except Exception:
        return False


def _hardware_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
    }
    try:
        import torch  # local import — do not require torch at manifest-write time
        info["torch"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["cuda_version"] = torch.version.cuda
    except ImportError:
        info["torch"] = None
    return info


@dataclass
class DecodingConfig:
    """Decoding settings used for the inference. For M0/M1/M2 eval runs,
    do_sample should be False (deterministic) or seeded."""
    do_sample: bool
    temperature: float | None
    top_p: float | None
    max_new_tokens: int
    seed: int | None
    repetition_penalty: float | None = None


@dataclass
class RunManifest:
    # Identity
    run_id: str
    started_at: str
    finished_at: str | None = None
    duration_s: float | None = None

    # Environment
    code_sha: str = ""
    code_dirty: bool = False
    hardware: dict[str, Any] = field(default_factory=dict)

    # Versioned artifacts
    schema_version: str = ""
    prompt_id: str = ""
    prompt_version: str = ""
    fewshot_ids: list[str] = field(default_factory=list)
    model_name: str = ""
    model_cache_dir: str = ""

    # Config
    decoding: dict[str, Any] = field(default_factory=dict)

    # Source
    source_doc_id: str = ""
    source_doc_type: str = ""
    source_length_chars: int = 0

    # Output
    raw_response: str = ""
    raw_response_tokens: int | None = None
    raw_valid: bool = False
    parse_error_raw: str | None = None
    repair_attempts: int = 0
    repair_method: str | None = None       # regex_json_extraction / json_repair / strip_prose / failed
    final_valid: bool = False
    parse_error_final: str | None = None
    parsed_value: dict[str, Any] | None = None

    # Optional arm label (M0/M1/M2/…)
    arm: str = ""

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(asdict(self), indent=indent, default=str)

    def write(self, root: Path | None = None) -> Path:
        base = root or MANIFEST_ROOT
        day = datetime.fromisoformat(self.started_at).strftime("%Y-%m-%d")
        out_dir = base / day
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.run_id}.json"
        path.write_text(self.to_json(), encoding="utf-8")
        return path


class ManifestBuilder:
    """Fluent builder — set fields incrementally as the inference progresses.

    Usage:
        m = ManifestBuilder.start(
            schema_version="v0.2.1",
            prompt=some_prompt_template,
            model_name="m42-health/Llama3-Med42-8B",
            model_cache_dir="/some/cache",
            decoding=DecodingConfig(do_sample=False, temperature=None,
                                    top_p=None, max_new_tokens=1024, seed=0),
            source_doc_id="MRI-001",
            source_doc_type="mri_report",
            source_length_chars=len(text),
            arm="M2",
        )
        m.record_raw(response_text, n_tokens=..., raw_valid=True, parsed_value={...})
        # or on failure:
        m.record_raw(response_text, raw_valid=False, parse_error_raw="...")
        m.record_repair(method="regex_json_extraction", attempts=1,
                        final_valid=True, parsed_value={...})
        m.finish().write()
    """

    def __init__(self, manifest: RunManifest):
        self._m = manifest

    @classmethod
    def start(
        cls,
        *,
        schema_version: str,
        prompt,               # PromptTemplate — duck-typed to avoid import cycle
        model_name: str,
        model_cache_dir: str,
        decoding: DecodingConfig,
        source_doc_id: str,
        source_doc_type: str,
        source_length_chars: int,
        arm: str,
    ) -> "ManifestBuilder":
        m = RunManifest(
            run_id=uuid.uuid4().hex[:12],
            started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            code_sha=_git_sha_short(),
            code_dirty=_git_dirty(),
            hardware=_hardware_info(),
            schema_version=schema_version,
            prompt_id=prompt.prompt_id,
            prompt_version=prompt.version,
            fewshot_ids=[ex.example_id for ex in prompt.few_shot],
            model_name=model_name,
            model_cache_dir=model_cache_dir,
            decoding=asdict(decoding),
            source_doc_id=source_doc_id,
            source_doc_type=source_doc_type,
            source_length_chars=source_length_chars,
            arm=arm,
        )
        return cls(m)

    def record_raw(
        self,
        response: str,
        *,
        n_tokens: int | None = None,
        raw_valid: bool,
        parsed_value: dict | None = None,
        parse_error: str | None = None,
    ) -> "ManifestBuilder":
        self._m.raw_response = response
        self._m.raw_response_tokens = n_tokens
        self._m.raw_valid = raw_valid
        if raw_valid:
            self._m.parsed_value = parsed_value
            self._m.final_valid = True
        else:
            self._m.parse_error_raw = parse_error
        return self

    def record_repair(
        self,
        *,
        method: str,
        attempts: int,
        final_valid: bool,
        parsed_value: dict | None = None,
        parse_error: str | None = None,
    ) -> "ManifestBuilder":
        self._m.repair_attempts = attempts
        self._m.repair_method = method
        self._m.final_valid = final_valid
        if final_valid:
            self._m.parsed_value = parsed_value
        else:
            self._m.parse_error_final = parse_error
        return self

    def finish(self) -> RunManifest:
        finished = datetime.now(timezone.utc).isoformat(timespec="seconds")
        started_dt = datetime.fromisoformat(self._m.started_at)
        finished_dt = datetime.fromisoformat(finished)
        self._m.finished_at = finished
        self._m.duration_s = (finished_dt - started_dt).total_seconds()
        return self._m
