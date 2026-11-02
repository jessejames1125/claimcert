import json
import shutil
import sys
from pathlib import Path

import pytest

from claimcert.agent import AgentError, run_agent
from claimcert.audit import audit_agent, audit_status
from claimcert.claims import load_claim
from claimcert.leanrun import LeanRun
from claimcert.prove import build_prompt, extract_proof, prove
from claimcert.registry import load_registry

FIX = Path(__file__).parent / "fixtures"
REG_PATH = FIX / "registry.yaml"
REG = load_registry(REG_PATH)
LEAN_ROOT = Path(__file__).resolve().parents[1] / "lean"


def agent_script(tmp_path, *replies: str) -> str:
    """A stand-in agent: answers from a list, one reply per call, and saves each prompt it saw."""
    (tmp_path / "replies.json").write_text(json.dumps(list(replies)), encoding="utf-8")
    script = tmp_path / "agent.py"
    script.write_text(
        "import json, pathlib, sys\n"
        f"state = pathlib.Path({str(tmp_path)!r})\n"
        "replies = json.loads((state / 'replies.json').read_text(encoding='utf-8'))\n"
        "n = len(list(state.glob('prompt*.txt')))\n"
        "(state / f'prompt{n}.txt').write_text(sys.stdin.buffer.read().decode('utf-8'), encoding='utf-8')\n"
        "print(replies[min(n, len(replies) - 1)])\n", encoding="utf-8")
    return f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}"'


def claim_file(tmp_path) -> Path:
    dst = tmp_path / "fx_pass.yaml"
    shutil.copy(FIX / "claims" / "fx_pass.yaml", dst)
    return dst


def test_extract_proof_takes_the_last_block():
    assert extract_proof("text\n```lean\n  a\n```\nthen\n```lean4\n  b\n```") == "  b\n"


def test_extract_proof_none_when_the_agent_gives_up_or_sends_prose():
    assert extract_proof("UNPROVABLE: 14 is more than 13") is None
    assert extract_proof("I think linarith would work") is None


def test_prompt_shows_the_statement_and_hides_the_intent(tmp_path):
    claim = load_claim(claim_file(tmp_path), REG)
    prompt = build_prompt(claim, REG)
    assert "theorem fx_pass" in prompt and "z ≤ (4 : ℝ)" in prompt and "A_fx_cap" in prompt
    assert str(claim.intent) not in prompt


def test_prompt_carries_the_lean_error_on_a_retry(tmp_path):
    claim = load_claim(claim_file(tmp_path), REG)
    assert "linarith failed" in build_prompt(claim, REG, "linarith failed")


def pass_only_for(monkeypatch, marker: str):
    """Fake kernel: passes when the proof on disk contains marker."""
    from claimcert import check as chk

    def run(_root, lean_file, *a, nonce, **k):
        if marker not in Path(lean_file).read_text(encoding="utf-8"):
            return LeanRun("error", "x.lean:1:1: error: linarith failed", 0.1)
        rep = {"theorem": "fx_pass", "axioms": [],
               "binders": [{"name": "h_fx_cap", "prop": True, "head": "A_fx_cap", "used": True},
                           {"name": "h_fx_unused_cap", "prop": True, "head": "A_fx_unused_cap", "used": False}]}
        return LeanRun("ok", f"CCREPORT {nonce} {json.dumps(rep)}", 0.1)
    monkeypatch.setattr(chk, "run_lean", run)


def test_prove_retries_with_the_error_then_passes(tmp_path, monkeypatch):
    pass_only_for(monkeypatch, "good_proof")
    agent = agent_script(tmp_path, "```lean\n  bad_proof\n```", "```lean\n  good_proof\n```")
    v, log = prove(claim_file(tmp_path), REG_PATH, LEAN_ROOT, agent)
    assert v["status"] == "PASS" and [t.status for t in log] == ["FAIL", "PASS"]
    assert "linarith failed" in (tmp_path / "prompt1.txt").read_text(encoding="utf-8")


def test_prove_stops_at_the_attempt_limit(tmp_path, monkeypatch):
    pass_only_for(monkeypatch, "never_written")
    agent = agent_script(tmp_path, "```lean\n  bad_proof\n```")
    v, log = prove(claim_file(tmp_path), REG_PATH, LEAN_ROOT, agent, attempts=2)
    assert v["status"] == "FAIL" and len(log) == 2


def test_a_cheating_agent_is_stopped_by_the_screen(tmp_path, monkeypatch):
    pass_only_for(monkeypatch, "sorry")  # the fake kernel would pass it; the screen runs first
    agent = agent_script(tmp_path, "```lean\n  sorry\n```")
    v, log = prove(claim_file(tmp_path), REG_PATH, LEAN_ROOT, agent, attempts=1)
    assert v["status"] == "FAIL" and v["stage"] == "hygiene"


def test_an_agent_that_gives_up_ends_the_loop(tmp_path, monkeypatch):
    pass_only_for(monkeypatch, "x")
    v, log = prove(claim_file(tmp_path), REG_PATH, LEAN_ROOT, agent_script(tmp_path, "UNPROVABLE because"))
    assert v is None and [t.status for t in log] == ["GAVE-UP"]


def test_missing_agent_command():
    with pytest.raises(AgentError, match="not found"):
        run_agent("no-such-agent-command --flag", "hello")


def test_failing_agent_reports_its_exit_code(tmp_path):
    script = tmp_path / "bad.py"
    script.write_text("import sys\nprint('nope', file=sys.stderr)\nsys.exit(3)\n", encoding="utf-8")
    with pytest.raises(AgentError, match="exited 3"):
        run_agent(f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}"', "hello")


def test_agent_runs_outside_the_repo(tmp_path):
    script = tmp_path / "cwd.py"
    script.write_text("import os\nprint(os.getcwd())\n", encoding="utf-8")
    out = run_agent(f'"{Path(sys.executable).as_posix()}" "{script.as_posix()}"', "")
    assert "claimcert-agent-" in out


def test_audit_agent_is_blind_and_records_a_mismatch(tmp_path):
    claim = load_claim(claim_file(tmp_path), REG)
    agent = agent_script(tmp_path, "It says z is at most 4.", "MISMATCH\nThe intent names a different number.")
    match, reason = audit_agent(claim, REG, agent)
    assert match is False and reason == "The intent names a different number."
    assert audit_status(claim, REG) == "MISMATCH"
    reader = (tmp_path / "prompt0.txt").read_text(encoding="utf-8")
    judge = (tmp_path / "prompt1.txt").read_text(encoding="utf-8")
    assert str(claim.intent).strip() not in reader and "theorem fx_pass" in reader
    assert str(claim.intent).strip() in judge and "It says z is at most 4." in judge and "theorem" not in judge


def test_audit_agent_fails_closed_on_an_unclear_reply(tmp_path):
    claim = load_claim(claim_file(tmp_path), REG)
    match, _ = audit_agent(claim, REG, agent_script(tmp_path, "reading", "It looks fine to me"))
    assert match is False and audit_status(claim, REG) == "MISMATCH"


def test_unbalanced_quote_is_a_clean_agent_error():
    with pytest.raises(AgentError, match="could not read"):
        run_agent('claude -p "unclosed', "hello")


def test_windows_paths_keep_their_backslashes(monkeypatch):
    from claimcert import agent
    monkeypatch.setattr(agent.sys, "platform", "win32")
    assert agent.split_command(r'"C:\Tools\my agent.exe" -p --model x') == [r"C:\Tools\my agent.exe", "-p", "--model", "x"]
    assert agent.split_command(r"C:\Tools\agent.exe -p") == [r"C:\Tools\agent.exe", "-p"]
