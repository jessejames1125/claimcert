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


def test_toolchain_listed_by_elan_counts_as_installed(tmp_path, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="leanprover/lean4:v4.34.1\n"))
    rows = {r.name: r for r in diagnose(repo(tmp_path), which=lambda _: "elan")}
    assert "installed" in rows["toolchain"].detail and "download" not in rows["toolchain"].detail


def test_low_free_memory_alone_is_not_missing(tmp_path, monkeypatch):
    from claimcert import doctor
    monkeypatch.setattr(doctor, "memory_gb", lambda: (16.0, 1.0))
    rows = {r.name: r for r in diagnose(repo(tmp_path), which=lambda _: None)}
    assert rows["memory"].ok and "1.0 GB free" in rows["memory"].detail
    monkeypatch.setattr(doctor, "memory_gb", lambda: (4.0, 3.0))
    rows = {r.name: r for r in diagnose(tmp_path, which=lambda _: None)}
    assert not rows["memory"].ok


def test_doctor_names_the_verifier(tmp_path):
    rows = {r.name: r for r in diagnose(repo(tmp_path), which=lambda _: None)}
    assert rows["verifier"].ok is False and "claimcert setup" in rows["verifier"].detail


def test_setup_retries_a_failed_build_once(tmp_path, monkeypatch, capsys):
    import subprocess
    from types import SimpleNamespace
    from claimcert import doctor
    codes = iter([0, 1, 0])
    calls = []

    def fake(cmd, cwd):
        calls.append(cmd[1:])
        return SimpleNamespace(returncode=next(codes))
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "lake")
    monkeypatch.setattr(subprocess, "run", fake)
    assert setup(repo(tmp_path)) == 0
    assert [c[0] for c in calls] == ["exe", "build", "build"]
    assert "retrying the build once" in capsys.readouterr().out


def test_setup_gives_up_after_the_second_failed_build(tmp_path, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    from claimcert import doctor
    codes = iter([0, 1, 1])
    monkeypatch.setattr(doctor.shutil, "which", lambda _: "lake")
    monkeypatch.setattr(subprocess, "run", lambda cmd, cwd: SimpleNamespace(returncode=next(codes)))
    assert setup(repo(tmp_path)) == 1
