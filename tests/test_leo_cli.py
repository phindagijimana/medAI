"""LEO command line: catalogue, local specialist-only batch/extract, Slurm script generation (no submission)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))

import leo_cli  # noqa: E402

pytest.importorskip("medcat")


def test_phenotypes_lists_everything(capsys):
    assert leo_cli.main(["phenotypes"]) == 0
    out = capsys.readouterr().out
    assert "current_asms" in out and "PANELS" in out and "status_epilepticus" in out
    assert leo_cli.main(["phenotypes", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)["extract"]) == 41


def test_batch_local_cpu_adds_columns_and_keeps_input(tmp_path, capsys):
    src = tmp_path / "notes.csv"
    pd.DataFrame({"mrn": ["a"], "note": ["Focal epilepsy. Takes lamotrigine 100 mg twice daily."], "x": [1]}).to_csv(src, index=False)
    out = tmp_path / "res.csv"
    rc = leo_cli.main(["batch", str(src), "-o", str(out), "--local", "--mode", "cpu", "--phenotypes", "core"])
    assert rc == 0 and out.exists() and (tmp_path / "res.claims.csv").exists() and (tmp_path / "res.provenance.json").exists()
    t = pd.read_csv(out, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    assert list(t.columns[:3]) == ["mrn", "note", "x"]
    assert t.loc[0, "epilepsy_type"] == "focal" and t.loc[0, "current_asms"] == "lamotrigine"
    assert json.loads((tmp_path / "res.provenance.json").read_text())["mode"] == "specialist_only"


def test_batch_cpu_rejects_questions(tmp_path):
    src = tmp_path / "n.csv"
    pd.DataFrame({"note": ["Focal epilepsy."]}).to_csv(src, index=False)
    with pytest.raises(SystemExit):
        leo_cli.main(["batch", str(src), "--local", "--mode", "cpu", "--question", "Is there an aura?"])


def test_batch_unknown_phenotype_stops(tmp_path):
    src = tmp_path / "n.csv"
    pd.DataFrame({"note": ["Focal epilepsy."]}).to_csv(src, index=False)
    with pytest.raises(KeyError):
        leo_cli.main(["batch", str(src), "--local", "--mode", "cpu", "--phenotypes", "not_a_phenotype"])


def test_extract_json_from_file(tmp_path, capsys):
    f = tmp_path / "n.txt"
    f.write_text("Generalised epilepsy. Takes levetiracetam 500 mg twice daily.")
    assert leo_cli.main(["extract", str(f), "--mode", "cpu", "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["mode"] == "specialist_only" and d["row"]["epilepsy_type"] == "generalized"


def test_slurm_script_gpu_and_cpu(tmp_path, monkeypatch):
    monkeypatch.setattr(leo_cli, "JOBDIR", tmp_path)
    monkeypatch.setattr(leo_cli, "_slurm_ok", lambda: True)
    calls = []

    class R:
        returncode, stdout, stderr = 0, "4242\n", ""

    monkeypatch.setattr(leo_cli.subprocess, "run", lambda cmd, **k: calls.append(cmd) or R())
    assert leo_cli._submit("t", ["check", "--gpu"], gpu=True, partition="interactive", hours=1) == "4242"
    g = next(tmp_path.glob("t_*.sh")).read_text()
    assert "--gres=gpu:l40s.24g:1" in g and "--partition=interactive" in g and "leo_cli.py check --gpu" in g
    assert "UMLS" not in g                                   # secrets are sourced from .env, never written into scripts
    for f in tmp_path.glob("t_*.sh"):
        f.unlink()
    leo_cli._submit("t", ["batch", "x", "--local", "--mode", "cpu"], gpu=False, partition="general", hours=2)
    c = next(tmp_path.glob("t_*.sh")).read_text()
    assert "gres" not in c and "--time=02:00:00" in c


def test_batch_default_submits_gpu_job(tmp_path, monkeypatch):
    src = tmp_path / "n.csv"
    pd.DataFrame({"note": ["Focal epilepsy."]}).to_csv(src, index=False)
    seen = {}
    monkeypatch.setattr(leo_cli, "_submit", lambda name, argv, **k: seen.update(argv=argv, **k) or "1")
    leo_cli.main(["batch", str(src), "--question", "Is there an aura?", "--phenotypes", "seizure"])
    assert seen["gpu"] is True and "--local" in seen["argv"] and "gpu" == seen["argv"][seen["argv"].index("--mode") + 1]
    assert "--question" in seen["argv"] and "seizure" in seen["argv"]
    leo_cli.main(["batch", str(src), "--cpu"])
    assert seen["gpu"] is False and "cpu" == seen["argv"][seen["argv"].index("--mode") + 1]


def test_h2_flag_resolves_shipped_adapter(tmp_path, monkeypatch):
    assert (leo_cli.H2_ADAPTER / "adapter_config.json").exists()
    src = tmp_path / "n.csv"
    pd.DataFrame({"note": ["Focal epilepsy."]}).to_csv(src, index=False)
    seen = {}
    monkeypatch.setattr(leo_cli, "_submit", lambda name, argv, **k: seen.update(argv=argv, **k) or "1")
    leo_cli.main(["batch", str(src), "--h2"])
    argv = seen["argv"]
    assert "--adapter" in argv
    assert argv[argv.index("--adapter") + 1].endswith("llama3-med42-8b_lora_epi_h2")
