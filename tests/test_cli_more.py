"""Registry and lake root defaults, so a stranger's command stays short."""
import json
from pathlib import Path

from claimcert.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_check_finds_the_registry_and_lake_root(monkeypatch, capsys):
    """A dimension failure stops before Lean, so this runs the real path with no toolchain."""
    monkeypatch.chdir(ROOT)
    claim = ROOT / "examples" / "software" / "rate_vs_size_planted.yaml"
    before = claim.with_suffix(".verdict.json").read_text(encoding="utf-8")
    try:
        assert main(["check", str(claim.relative_to(ROOT))]) == 1
        assert "at stage dimension" in capsys.readouterr().out
    finally:
        claim.with_suffix(".verdict.json").write_text(before, encoding="utf-8", newline="\n")


def test_replay_of_the_examples_exits_zero(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    assert main(["replay", "examples"]) == 0
    assert "recorded" in capsys.readouterr().out


def test_replay_fails_on_a_folder_with_no_claims(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    assert main(["replay", str(tmp_path)]) == 1


def test_claim_without_a_registry_above_it_is_a_clean_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "c.yaml").write_text("name: c\n", encoding="utf-8")
    assert main(["new", "c.yaml"]) == 1
    assert "no registry.yaml" in capsys.readouterr().err


def test_demo_verdicts_are_valid_json_with_a_record():
    for name in ("gpu_memory_planted", "gpu_memory_true"):
        v = json.loads((ROOT / "examples" / "software" / f"{name}.verdict.json").read_text(encoding="utf-8"))
        assert v["recorded"]["toolchain"].startswith("leanprover/lean4:")
