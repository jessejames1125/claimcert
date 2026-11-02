import subprocess
from pathlib import Path

import pytest

from claimcert.report import parse_report

LEAN_ROOT = Path(__file__).resolve().parents[1] / "lean"
STD = {"propext", "Classical.choice", "Quot.sound"}


def test_parse_single_line():
    out = 'x.lean:9:0: info: CCREPORT n0nce {"theorem":"t","binders":[],"axioms":["propext"]}\n'
    assert parse_report(out, "n0nce") == {"theorem": "t", "binders": [], "axioms": ["propext"]}


def test_parse_none_when_missing():
    assert parse_report("no report here", "n0nce") is None


def test_parse_none_when_two_lines():
    line = 'CCREPORT n0nce {"theorem":"t","binders":[],"axioms":[]}\n'
    assert parse_report(line + line, "n0nce") is None


J = '{"theorem":"t","binders":[],"axioms":[]}'


def test_parse_rejects_wrong_nonce():
    assert parse_report(f"CCREPORT other {J}\n", "n0nce") is None
    assert parse_report(f"CCREPORT {J}\n", "n0nce") is None


def test_parse_rejects_right_plus_wrong_nonce():
    assert parse_report(f"CCREPORT n0nce {J}\nCCREPORT bad {J}\n", "n0nce") is None


def test_parse_accepts_one_right_nonce():
    assert parse_report(f"noise\nCCREPORT n0nce {J}\n", "n0nce")["theorem"] == "t"


@pytest.mark.lean
def test_report_fixture_marks_used_and_unused():
    from claimcert.leanrun import run_lean
    fixture = LEAN_ROOT / "ClaimCertTest" / "ReportFixture.lean"
    run = run_lean(LEAN_ROOT, fixture, "ClaimCert", 1800, nonce="n0nce", theorem="fx_uses")
    assert run.status == "ok", run.output[-2000:]
    rep = parse_report(run.output, "n0nce")
    by = {b["name"]: b for b in rep["binders"]}
    assert by["h_used"]["used"] is True
    assert by["h_unused"]["used"] is False
    assert by["a"]["prop"] is False and by["h_used"]["prop"] is True
    assert by["h_used"]["head"] == "LE.le"
    assert set(rep["axioms"]) <= STD


@pytest.mark.lean
def test_lean_library_and_fixtures_build():
    p = subprocess.run(["lake", "build", "ClaimCert", "ClaimCertTest"], cwd=LEAN_ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert p.returncode == 0, p.stdout + p.stderr


def test_parse_none_on_malformed_json():
    assert parse_report("CCREPORT n0nce {not json}", "n0nce") is None
