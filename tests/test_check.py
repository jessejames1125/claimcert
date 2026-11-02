import json
import shutil
from pathlib import Path

import pytest

from claimcert.check import check_claim
from claimcert.claims import write_new
from claimcert.leanrun import hygiene

FIX = Path(__file__).parent / "fixtures"
REG = FIX / "registry.yaml"
LEAN_ROOT = Path(__file__).resolve().parents[1] / "lean"


def stage(tmp_path, name, proof: str | None = None) -> Path:
    dst = tmp_path / f"{name}.yaml"
    shutil.copy(FIX / "claims" / f"{name}.yaml", dst)
    pf = None
    if proof is not None:
        pf = tmp_path / "proof.lean"
        pf.write_text(proof, encoding="utf-8")
    write_new(dst, REG, pf)
    return dst


@pytest.mark.parametrize("proof", [
    "  sorry\n",
    "  native_decide\n",
    '  set_option leancert.trust "native" in linarith\n',
    "  leancert (trust := auto)\n",
    "  exact (by admit)\n",
])
def test_hygiene_rejects(proof):
    assert hygiene(proof) is not None


def test_hygiene_allows_plain_proof():
    assert hygiene("  unfold A_fx_cap at h_fx_cap\n  linarith\n") is None


def test_sorry_fails_before_lean(tmp_path):
    v = check_claim(stage(tmp_path, "fx_pass"), REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["status"] == "FAIL" and v["stage"] == "hygiene"


def test_native_trust_fails_hygiene(tmp_path):
    p = stage(tmp_path, "fx_native", '  set_option leancert.trust "native" in linarith\n')
    v = check_claim(p, REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["stage"] == "hygiene"


def test_edited_statement_fails(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    lean = p.with_suffix(".lean")
    lean.write_text(lean.read_text(encoding="utf-8").replace("z ≤ (4 : ℝ)", "z ≤ (5 : ℝ)"), encoding="utf-8")
    v = check_claim(p, REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["stage"] == "statement"


def test_second_report_line_fails(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n#cc_report fx_pass\n")
    v = check_claim(p, REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["stage"] == "trailer"


def test_missing_toolchain(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    v = check_claim(p, REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["status"] == "FAIL" and v["stage"] == "toolchain"
    assert json.loads(p.with_suffix(".verdict.json").read_text(encoding="utf-8"))["stage"] == "toolchain"


def test_cli_exits_2_when_lake_missing(tmp_path):
    from claimcert.cli import main
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    rc = main(["check", str(p), "--registry", str(REG), "--lake-root", str(LEAN_ROOT),
               "--lake", "lake-does-not-exist"])
    assert rc == 2


def test_dimension_error_gives_fail_verdict(tmp_path):
    p = tmp_path / "fx_dim.yaml"
    p.write_text((FIX / "claims" / "fx_false.yaml").read_text(encoding="utf-8")
                 .replace("name: fx_false", "name: fx_dim").replace('"2 m"', '"2 s"'), encoding="utf-8")
    v = check_claim(p, REG, LEAN_ROOT)
    assert v["stage"] == "dimension"


@pytest.mark.lean
def test_pass_lists_used_and_unused(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    v = check_claim(p, REG, LEAN_ROOT)
    assert v["status"] == "PASS", v
    assert v["assumptions"]["FIT"] == ["fx_cap"]
    assert v["unused_assumptions"] == ["fx_unused_cap"]
    assert v["audit"] == "UNAUDITED"


@pytest.mark.lean
def test_false_claim_fails_in_elaboration(tmp_path):
    p = stage(tmp_path, "fx_false", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    v = check_claim(p, REG, LEAN_ROOT)
    assert v["status"] == "FAIL" and v["stage"] == "elaboration"


@pytest.mark.lean
def test_timeout(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    v = check_claim(p, REG, LEAN_ROOT, timeout_s=0.01)
    assert v["stage"] == "timeout"


FORGED = ('  linarith\n#eval IO.println "CCREPORT {\\"theorem\\":\\"fx_pass\\",\\"binders\\":[],\\"axioms\\":[]}"\n#exit\n')


def test_forged_report_fails_hygiene(tmp_path):
    p = stage(tmp_path, "fx_pass", FORGED)
    v = check_claim(p, REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["status"] == "FAIL" and v["stage"] == "hygiene"


def test_run_tac_forgery_fails_hygiene(tmp_path):
    proof = '  run_tac Lean.logInfo "x"\n  linarith\n'
    v = check_claim(stage(tmp_path, "fx_pass", proof), REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["stage"] == "hygiene"


def test_column_zero_command_fails_hygiene(tmp_path):
    v = check_claim(stage(tmp_path, "fx_pass", "  linarith\nexample : True := trivial\n"), REG, LEAN_ROOT,
                    lake="lake-does-not-exist")
    assert v["stage"] == "hygiene"


@pytest.mark.parametrize("proof", ["  linarith\n#exit\n", "  run_cmd foo\n", "  elab x\n", "  macro x\n",
                                   "  initialize\n", "  IO.println 1\n", "  dbg_trace 1\n",
                                   "  CCREPORT\n", "  run_elab x\n"])
def test_hygiene_rejects_more(proof):
    assert hygiene(proof) is not None


def test_hygiene_allows_comments_and_blank_lines():
    assert hygiene("-- note\n\n  linarith\n") is None


def test_trailer_needs_own_line(tmp_path):
    p = stage(tmp_path, "fx_pass", "  linarith\n")
    lean = p.with_suffix(".lean")
    lean.write_text(lean.read_text(encoding="utf-8").replace("  linarith\n\n#cc_report", "  linarith#cc_report"),
                    encoding="utf-8")
    v = check_claim(p, REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["stage"] == "trailer"


def test_missing_lake_root_is_toolchain_fail(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    v = check_claim(p, REG, tmp_path / "nope", lake="python")
    assert v["status"] == "FAIL" and v["stage"] == "toolchain"


def test_no_report_line_fails_at_report(tmp_path, monkeypatch):
    from claimcert import check as chk
    from claimcert.leanrun import LeanRun
    monkeypatch.setattr(chk, "run_lean", lambda *a, **k: LeanRun("ok", "all fine, no report", 0.1))
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    assert check_claim(p, REG, LEAN_ROOT)["stage"] == "report"


def test_malformed_report_shape_fails_at_report(tmp_path, monkeypatch):
    from claimcert import check as chk
    from claimcert.leanrun import LeanRun
    monkeypatch.setattr(chk, "run_lean", lambda *a, nonce, **k: LeanRun("ok", "CCREPORT " + nonce + ' {"foo":1}', 0.1))
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    v = check_claim(p, REG, LEAN_ROOT)
    assert v["status"] == "FAIL" and v["stage"] == "report"


def test_shared_deadline(monkeypatch, tmp_path):
    import time
    from claimcert import leanrun
    seen = []

    def fake(cmd, cwd, env, timeout):
        seen.append(timeout)
        time.sleep(0.02)
        time.sleep(0.02)
        return 0, ""
    monkeypatch.setattr(leanrun.shutil, "which", lambda x: "lake")
    monkeypatch.setattr(leanrun, "_run", fake)
    r = leanrun.run_lean(tmp_path, tmp_path / "a.lean", "M", 100.0)
    assert r.status == "ok" and len(seen) == 2 and seen[1] < seen[0]



EXPLOIT = ("  linarith\n"
           "  @[command_elab Lean.Parser.Command.eoi] def evil : Lean.Elab.Command.CommandElab := fun _ => do\n"
           "    Lean.logInfo m!\"\x46CREPORT {}\"\n")


def test_exploit_fails_hygiene(tmp_path):
    v = check_claim(stage(tmp_path, "fx_pass", EXPLOIT), REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["stage"] == "hygiene"


@pytest.mark.parametrize("proof", ["  macro_rules | x => y\n", "  elab_rules : tactic | x => y\n",
                                   '  exact foo "s"\n', "  attribute [x] y\n", "  by_elab x\n",
                                   "  notation x\n", "  infixl x\n", "  exact a \\x46\n", "  @[simp] x\n",
                                   "  # x\n"])
def test_structural_rejects(proof):
    assert hygiene(proof) is not None


@pytest.mark.parametrize("proof", [
    "  run_meta foo\n",
    "  set_option debug.skipKernelTC true in\n  linarith\n",
    "  exact addDecl x\n",
    "  exact unsafeIO x\n",
    "  open Lean in linarith\n",
    "  exact Lean.Meta.foo\n",
    "  exact compileDecl x\n",
])
def test_kernel_bypass_rejected(proof):
    assert hygiene(proof) is not None


NMAX = "(100000000000000000000000000000 : ℝ)"
SMAX = "(1 / 200000000000000000000000000000 : ℝ)"
F = "(91 / 20 : ℝ)"
REAL_PROOFS = {
    "geom": ("  rw [ClaimCert.cylinderFitsInSphere_iff (by norm_num) (by norm_num)]\n"
             "  norm_num\n"),
    "range": ("  unfold A_bm_fit_linear at h_bm_fit_linear\n"
              "  have hx : x ∈ Set.Icc (1 : ℝ) (6 : ℝ) := ⟨by linarith [dom_x.1], by linarith [dom_x.2]⟩\n"
              "  have hy := h_bm_fit_linear hx\n"
              "  linarith [dom_x.2]\n"),
    "power": ("  unfold A_bm_power_balance at h_bm_power_balance\n"
              "  unfold A_bm_source_min at h_bm_source_min\n"
              "  unfold A_bm_loss_b at h_bm_loss_b\n"
              "  unfold A_bm_loss_c at h_bm_loss_c\n"
              "  linarith\n"),
    "floor": ("  unfold A_bm_max_density at h_bm_max_density\n"
              "  unfold A_bm_max_sigma at h_bm_max_sigma\n"
              "  have hpos : 0 < n * s := mul_pos dom_n dom_s\n"
              f"  have hle : n * s ≤ {NMAX} * {SMAX} :=\n"
              "    mul_le_mul h_bm_max_density h_bm_max_sigma dom_s.le (by norm_num)\n"
              f"  have key : {F} * ({NMAX} * {SMAX}) ≤ (1 : ℝ) * Real.log (10 : ℝ) := by\n"
              "    leancert\n"
              "  rw [ge_iff_le, le_div_iff₀ hpos]\n"
              f"  calc {F} * (n * s) ≤ {F} * ({NMAX} * {SMAX}) :=\n"
              "        mul_le_mul_of_nonneg_left hle (by norm_num)\n"
              f"    _ ≤ (1 : ℝ) * Real.log (10 : ℝ) := key\n"),
}


@pytest.mark.parametrize("name", list(REAL_PROOFS))
def test_real_proofs_pass_hygiene(name):
    assert hygiene(REAL_PROOFS[name]) is None


@pytest.mark.parametrize("proof,token", [
    ("  simproc foo\n", "simproc"), ("  dsimproc foo\n", "dsimproc"),
    ("  exact register_foo x\n", "register_foo"), ("  exact declare_foo x\n", "declare_foo"),
    ("  exact modifyEnv x\n", "modifyEnv"), ("  exact addAndCompile x\n", "addAndCompile"),
    ("  exact Compile x\n", "Compile"),
])
def test_more_bypass_bans(proof, token):
    reason = hygiene(proof)
    assert reason is not None and repr(token) in reason


def lake_copy(tmp_path) -> Path:
    """A lake root holding only the generated test module, as LEAN_ROOT has it."""
    root = tmp_path / "lake"
    (root / "ClaimCertTest").mkdir(parents=True)
    shutil.copy(LEAN_ROOT / "ClaimCertTest" / "Assumptions.lean", root / "ClaimCertTest" / "Assumptions.lean")
    return root


def test_edited_assumption_module_fails(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    root = lake_copy(tmp_path)
    mod = root / "ClaimCertTest" / "Assumptions.lean"
    mod.write_text(mod.read_text(encoding="utf-8").replace("z ≤ (3 : ℝ)", "z ≤ (4 : ℝ)"), encoding="utf-8")
    v = check_claim(p, REG, root, lake="lake-does-not-exist")
    assert v["status"] == "FAIL" and v["stage"] == "assumptions"


def test_missing_assumption_module_fails(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    root = lake_copy(tmp_path)
    (root / "ClaimCertTest" / "Assumptions.lean").unlink()
    v = check_claim(p, REG, root, lake="lake-does-not-exist")
    assert v["stage"] == "assumptions"


def test_module_with_crlf_still_matches(tmp_path):
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    root = lake_copy(tmp_path)
    mod = root / "ClaimCertTest" / "Assumptions.lean"
    mod.write_bytes(mod.read_bytes().replace(b"\n", b"\r\n"))
    assert check_claim(p, REG, root, lake="lake-does-not-exist")["stage"] == "toolchain"


def fake_pass(monkeypatch):
    from claimcert import check as chk
    from claimcert.leanrun import LeanRun

    def run(*a, nonce, **k):
        rep = {"theorem": "fx_pass", "axioms": ["propext"],
               "binders": [{"name": "z", "prop": False, "head": "", "used": True},
                           {"name": "h_fx_cap", "prop": True, "head": "ClaimCertTest.A_fx_cap", "used": True},
                           {"name": "h_fx_unused_cap", "prop": True, "head": "ClaimCertTest.A_fx_unused_cap",
                            "used": False}]}
        return LeanRun("ok", f"CCREPORT {nonce} {json.dumps(rep)}", 0.1)
    monkeypatch.setattr(chk, "run_lean", run)


def test_audit_mismatch_fails_the_claim(tmp_path, monkeypatch):
    from claimcert.audit import audit_record
    from claimcert.claims import load_claim
    from claimcert.registry import load_registry
    fake_pass(monkeypatch)
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    reg = load_registry(REG)
    audit_record(load_claim(p, reg), reg, False, "operator", "says 4 m, intent says 3 m")
    v = check_claim(p, REG, LEAN_ROOT)
    assert v["status"] == "FAIL" and v["stage"] == "audit" and v["audit"] == "MISMATCH"


def test_audit_stale_is_shown_and_keeps_status(tmp_path, monkeypatch):
    from claimcert.audit import audit_record
    from claimcert.claims import load_claim
    from claimcert.registry import load_registry
    fake_pass(monkeypatch)
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    reg = load_registry(REG)
    audit_record(load_claim(p, reg), reg, True, "operator", "matches")
    assert check_claim(p, REG, LEAN_ROOT)["audit"] == "MATCH"
    p.write_text(p.read_text(encoding="utf-8").replace('"400 cm"', '"500 cm"'), encoding="utf-8")
    write_new(p, REG, force=True)
    v = check_claim(p, REG, LEAN_ROOT)
    assert v["status"] == "PASS" and v["audit"] == "STALE"
    assert "audit: STALE" in p.with_suffix(".verdict.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("output,expected", [
    ("a.lean:9:0: error: (kernel) declaration has metavariables 'fx_pass'", "kernel"),
    ("a.lean:10:2: error: unsolved goals\n⊢ False", "elaboration"),
])
def test_lean_error_stage_split(tmp_path, monkeypatch, output, expected):
    from claimcert import check as chk
    from claimcert.leanrun import LeanRun
    monkeypatch.setattr(chk, "run_lean", lambda *a, **k: LeanRun("error", output, 0.1))
    p = stage(tmp_path, "fx_pass", "  unfold A_fx_cap at h_fx_cap\n  linarith\n")
    v = check_claim(p, REG, LEAN_ROOT)
    assert v["status"] == "FAIL" and v["stage"] == expected


@pytest.mark.parametrize("text,stage_name", [
    ("name: [fx_bad\n", "schema"),
    ("name: fx_bad\ntype: [bound]\nintent: x\ngoals: ['1 <= 2']\n", "schema"),
    ("name: fx_bad\ntype: point\nintent: x\nconstants: {C: 'inf m'}\ngoals: ['C <= C']\n", "schema"),
])
def test_malformed_claim_writes_fail_verdict(tmp_path, text, stage_name):
    p = tmp_path / "fx_bad.yaml"
    p.write_text(text, encoding="utf-8")
    v = check_claim(p, REG, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["status"] == "FAIL" and v["stage"] == stage_name
    assert p.with_suffix(".verdict.json").exists()


def test_malformed_registry_writes_fail_verdict(tmp_path):
    reg = tmp_path / "reg.yaml"
    reg.write_text("lean_namespace: [x\n", encoding="utf-8")
    p = tmp_path / "fx_pass.yaml"
    shutil.copy(FIX / "claims" / "fx_pass.yaml", p)
    v = check_claim(p, reg, LEAN_ROOT, lake="lake-does-not-exist")
    assert v["status"] == "FAIL" and v["stage"] == "registry"


GRANDCHILD_SPAWNER = """import pathlib, subprocess, sys, time
g = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(40)"], stdout=sys.stdout, stderr=sys.stderr)
pathlib.Path("grandchild.pid").write_text(str(g.pid))
time.sleep(40)
"""


def _alive(pid: int) -> bool:
    import subprocess
    import sys
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out.split()
    import os
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_timeout_kills_the_whole_process_tree(tmp_path):
    """The fake 'lake build' starts a sleeper that holds the output pipes, as lake.exe does with lean.exe."""
    import sys
    import time
    from claimcert.leanrun import run_lean
    (tmp_path / "build").write_text(GRANDCHILD_SPAWNER, encoding="utf-8")
    t0 = time.perf_counter()
    r = run_lean(tmp_path, tmp_path / "a.lean", "M", 3.0, lake=sys.executable)
    elapsed = time.perf_counter() - t0
    assert r.status == "timeout"
    assert elapsed < 20, elapsed
    pid = int((tmp_path / "grandchild.pid").read_text())
    deadline = time.time() + 5
    while _alive(pid) and time.time() < deadline:
        time.sleep(0.2)
    assert not _alive(pid)


def test_hygiene_message_does_not_claim_column_rule_is_a_defense():
    reason = hygiene("  linarith\nexample : True := trivial\n")
    assert reason is not None and "new command" not in reason and "indented" in reason


@pytest.mark.lean
def test_sorryax_fails_at_axioms_even_without_hygiene(tmp_path):
    """Calls the runner directly, as if the screen were skipped: the axiom check alone must refuse sorryAx."""
    import secrets
    from claimcert.claims import load_claim
    from claimcert.leanrun import run_lean
    from claimcert.registry import load_registry
    from claimcert.report import parse_report
    from claimcert.verdict import assemble
    proof = "  exact sorryAx _ false\n"
    assert hygiene(proof) is None  # the screen lets it through; the axiom check must not
    p = stage(tmp_path, "fx_pass", proof)
    reg = load_registry(REG)
    nonce = secrets.token_hex(16)
    run = run_lean(LEAN_ROOT, p.with_suffix(".lean"), reg.lean_module, 600, nonce=nonce)
    assert run.status == "ok", run.output[-2000:]
    report = parse_report(run.output, nonce)
    assert report is not None, run.output[-2000:]
    v = assemble(load_claim(p, reg), reg, report, run.seconds)
    assert v["status"] == "FAIL" and v["stage"] == "axioms" and "sorryAx" in v["reason"]
