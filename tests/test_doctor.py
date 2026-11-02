from pathlib import Path

from claimcert.cli import main
from claimcert.doctor import Row, diagnose, memory_gb, report, setup

ROOT = Path(__file__).resolve().parents[1]


def repo(tmp_path) -> Path:
    (tmp_path / "lean").mkdir()
    (tmp_path / "examples").mkdir()
    (tmp_path / "lean" / "lakefile.toml").write_text("", encoding="utf-8")
    (tmp_path / "lean" / "lean-toolchain").write_text("leanprover/lean4:v4.34.1\n", encoding="utf-8")
    return tmp_path


def test_without_elan_it_names_the_install_page(tmp_path):
    rows = {r.name: r for r in diagnose(repo(tmp_path), which=lambda _: None)}
    assert rows["elan"].ok is False and "lean-lang.org/install" in rows["elan"].detail
    assert rows["mathlib"].ok is False and "claimcert setup" in rows["mathlib"].detail
    assert rows["python"].ok and rows["pyyaml"].ok and rows["examples"].ok


def test_report_separates_replay_from_kernel():
    text, code = report([Row("python", True, "3.11", "replay"), Row("elan", False, "install it", "kernel")])
    assert code == 2 and "claimcert demo: ready" in text and "claimcert check: not ready" in text


def test_report_exit_zero_when_all_ready():
    text, code = report([Row("python", True, "3.11", "replay"), Row("elan", True, "found", "kernel")])
    assert code == 0 and "Ready" in text


def test_report_says_when_even_replay_is_blocked():
    text, code = report([Row("pyyaml", False, "not installed", "replay")])
    assert code == 2 and "claimcert demo: not ready" in text


def test_memory_reading_is_sane_where_available():
    mem = memory_gb()
    if mem is not None:
        total, avail = mem
        assert 0 < avail <= total


def test_setup_without_lake_exits_2(tmp_path, capsys):
    assert setup(repo(tmp_path), lake="lake-does-not-exist") == 2
    assert "lean-lang.org/install" in capsys.readouterr().err


def test_doctor_command_runs_in_a_checkout(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    code = main(["doctor"])
    out = capsys.readouterr().out
    assert code in (0, 2) and "python" in out and "mathlib" in out
