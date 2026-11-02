import json
import shutil
from pathlib import Path

import pytest

from claimcert.check import _scrub, check_claim
from claimcert.claims import write_new
from claimcert.cli import main
from claimcert.leanrun import LeanRun
from claimcert.replay import demo, registry_for, render, replay_claim, replay_tree, repo_root

FIX = Path(__file__).parent / "fixtures"
REG = FIX / "registry.yaml"
ROOT = Path(__file__).resolve().parents[1]
PROOF = "  unfold A_fx_cap at h_fx_cap\n  linarith\n"


def fake_lean(monkeypatch):
    """A stand-in for the kernel run, so these tests exercise only the record and match logic."""
    from claimcert import check as chk

    def run(*a, nonce, **k):
        rep = {"theorem": "fx_pass", "axioms": ["propext"],
               "binders": [{"name": "h_fx_cap", "prop": True, "head": "ClaimCertTest.A_fx_cap", "used": True},
                           {"name": "h_fx_unused_cap", "prop": True, "head": "ClaimCertTest.A_fx_unused_cap",
                            "used": False}]}
        return LeanRun("ok", f"CCREPORT {nonce} {json.dumps(rep)}", 0.1)
    monkeypatch.setattr(chk, "run_lean", run)


def lake_root(tmp_path) -> Path:
    root = tmp_path / "lake"
    (root / "ClaimCertTest").mkdir(parents=True)
    (root / "ClaimCert").mkdir()
    shutil.copy(ROOT / "lean" / "ClaimCertTest" / "Assumptions.lean", root / "ClaimCertTest" / "Assumptions.lean")
    shutil.copy(ROOT / "lean" / "ClaimCert" / "Dim.lean", root / "ClaimCert" / "Dim.lean")
    (root / "lean-toolchain").write_text("leanprover/lean4:v4.34.1\n", encoding="utf-8")
    (root / "lake-manifest.json").write_text("{}\n", encoding="utf-8")
    return root


def staged(tmp_path, monkeypatch) -> tuple[Path, Path]:
    fake_lean(monkeypatch)
    root = lake_root(tmp_path)
    claim = tmp_path / "fx_pass.yaml"
    shutil.copy(FIX / "claims" / "fx_pass.yaml", claim)
    proof = tmp_path / "proof.lean"
    proof.write_text(PROOF, encoding="utf-8")
    write_new(claim, REG, proof)
    assert check_claim(claim, REG, root)["status"] == "PASS"
    return claim, root


def test_recorded_verdict_replays_when_nothing_changed(tmp_path, monkeypatch):
    claim, root = staged(tmp_path, monkeypatch)
    result = replay_claim(claim, REG, root)
    assert result.state == "recorded" and result.ok and result.verdict["status"] == "PASS"


def test_edited_proof_makes_the_record_stale(tmp_path, monkeypatch):
    claim, root = staged(tmp_path, monkeypatch)
    lean = claim.with_suffix(".lean")
    lean.write_text(lean.read_text(encoding="utf-8").replace("  linarith\n", "  linarith -- edited\n"), encoding="utf-8")
    result = replay_claim(claim, REG, root)
    assert result.state == "stale" and not result.ok and "lean_sha256" in result.detail
    assert "do not trust" in render(result)


@pytest.mark.parametrize("change,field", [
    (lambda root: (root / "lean-toolchain").write_text("leanprover/lean4:v9\n", encoding="utf-8"), "toolchain"),
    (lambda root: (root / "lake-manifest.json").write_text('{"x": 1}\n', encoding="utf-8"), "manifest_sha256"),
    (lambda root: (root / "ClaimCert" / "Dim.lean").write_text("-- edited\n", encoding="utf-8"), "core_sha256"),
])
def test_changed_toolchain_or_core_makes_the_record_stale(tmp_path, monkeypatch, change, field):
    claim, root = staged(tmp_path, monkeypatch)
    change(root)
    result = replay_claim(claim, REG, root)
    assert result.state == "stale" and field in result.detail


def test_edited_statement_is_refused_live(tmp_path, monkeypatch):
    claim, root = staged(tmp_path, monkeypatch)
    lean = claim.with_suffix(".lean")
    lean.write_text(lean.read_text(encoding="utf-8").replace("z ≤ (4 : ℝ)", "z ≤ (5 : ℝ)"), encoding="utf-8")
    result = replay_claim(claim, REG, root)
    assert result.state == "live" and result.verdict["stage"] == "statement"


def test_forged_status_cannot_hide_a_sorry(tmp_path, monkeypatch):
    claim, root = staged(tmp_path, monkeypatch)
    lean = claim.with_suffix(".lean")
    lean.write_text(lean.read_text(encoding="utf-8").replace("  linarith\n", "  sorry\n"), encoding="utf-8")
    result = replay_claim(claim, REG, root)
    assert result.state == "live" and result.verdict["stage"] == "hygiene" and result.verdict["status"] == "FAIL"


def test_missing_verdict_is_not_ok(tmp_path, monkeypatch):
    claim, root = staged(tmp_path, monkeypatch)
    claim.with_suffix(".verdict.json").unlink()
    result = replay_claim(claim, REG, root)
    assert result.state == "missing" and not result.ok


def test_verdict_records_what_it_checked(tmp_path, monkeypatch):
    claim, _ = staged(tmp_path, monkeypatch)
    recorded = json.loads(claim.with_suffix(".verdict.json").read_text(encoding="utf-8"))["recorded"]
    assert recorded["toolchain"] == "leanprover/lean4:v4.34.1" and len(recorded["lean_sha256"]) == 64
    assert recorded["date"] and recorded["claimcert"]


def test_scrub_removes_paths_and_nonce_whatever_the_slash_or_case(tmp_path):
    lean = tmp_path / "c.lean"
    text = f"{lean}:10:3: error\n{str(lean).replace(chr(92), '/').upper()}:1:1\nCCREPORT n0nce {{}}\n{tmp_path}/lake/x"
    out = _scrub(text, lean, tmp_path / "lake", "n0nce")
    assert "c.lean:10:3" in out and "n0nce" not in out and "<nonce>" in out and "<lake-root>/x" in out
    assert str(tmp_path).replace("\\", "/").lower() not in out.replace("\\", "/").lower()


def test_failing_lean_output_leaves_no_absolute_path_in_the_verdict(tmp_path, monkeypatch):
    from claimcert import check as chk
    claim, root = staged(tmp_path, monkeypatch)
    lean = claim.with_suffix(".lean").resolve()
    monkeypatch.setattr(chk, "run_lean", lambda *a, **k: LeanRun("error", f"{lean}:10:3: error: unsolved goals", 0.1))
    v = check_claim(claim, REG, root)
    assert v["stage"] == "elaboration" and v["reason"].startswith("fx_pass.lean:10:3")
    text = claim.with_suffix(".verdict.txt").read_text(encoding="utf-8")
    assert str(tmp_path) not in text and str(tmp_path) not in claim.with_suffix(".verdict.json").read_text(encoding="utf-8")


def test_registry_for_walks_up(tmp_path):
    (tmp_path / "registry.yaml").write_text("x: 1\n", encoding="utf-8")
    (tmp_path / "a" / "b").mkdir(parents=True)
    assert registry_for(tmp_path / "a" / "b" / "c.yaml") == (tmp_path / "registry.yaml").resolve()


def test_repo_root_found_from_a_subfolder():
    assert repo_root(ROOT / "examples" / "software") == ROOT


def test_cli_explains_a_missing_checkout(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["demo"]) == 1
    assert "inside a claimcert checkout" in capsys.readouterr().err


def test_replay_tree_counts_states(tmp_path, monkeypatch):
    claim, root = staged(tmp_path, monkeypatch)
    shutil.copy(REG, tmp_path / "registry.yaml")
    text, ok = replay_tree(tmp_path, root)
    assert ok and "1 recorded" in text and "fx_pass" in text


def test_demo_needs_no_lean_on_the_path(monkeypatch):
    monkeypatch.setenv("PATH", "")
    text, ok = demo(ROOT)
    assert ok
    assert "gpu_memory_planted: FAIL" in text and "gpu_memory_true: PASS" in text
    assert "rate_vs_size_planted: FAIL (point) at stage dimension" in text
