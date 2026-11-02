"""The committed results must match the committed files, on any machine, without Lean."""
import json
import re
from pathlib import Path

import pytest

from claimcert.replay import demo, replay_claim

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted(p for p in (ROOT / "examples").rglob("*.yaml") if p.name != "registry.yaml")
PLANTED = json.loads((ROOT / "evals" / "planted" / "expected.json").read_text(encoding="utf-8"))
TRANSLATION = json.loads((ROOT / "evals" / "translation" / "expected.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("claim", EXAMPLES, ids=lambda p: p.stem)
def test_example_replays_and_has_the_expected_status(claim):
    result = replay_claim(claim, ROOT / "examples" / "registry.yaml", ROOT / "lean")
    assert result.ok, result.detail
    assert result.verdict["status"] == ("PASS" if claim.stem.endswith("_true") else "FAIL")


@pytest.mark.parametrize("name", sorted(PLANTED))
def test_planted_benchmark_replays(name):
    claim = ROOT / "evals" / "planted" / "claims" / f"{name}.yaml"
    result = replay_claim(claim, ROOT / "evals" / "planted" / "registry.yaml", ROOT / "lean")
    assert result.ok, result.detail
    assert result.verdict["status"] == PLANTED[name]


@pytest.mark.parametrize("name", sorted(TRANSLATION))
def test_translation_set_replays(name):
    claim = ROOT / "evals" / "translation" / f"{name}.yaml"
    result = replay_claim(claim, ROOT / "evals" / "translation" / "registry.yaml", ROOT / "lean")
    assert result.ok, result.detail
    # every statement is true mathematics, so the kernel passed it; the audit alone decides the verdict
    row = json.loads((ROOT / "evals" / "results" / "translation.json").read_text(encoding="utf-8"))["rows"][name]
    assert row["kernel"] == "PASS"
    assert result.verdict["status"] == ("PASS" if row["audit_match"] else "FAIL")
    assert result.verdict["status"] == "PASS" or result.verdict["stage"] == "audit"


def test_every_true_example_has_a_planted_partner():
    names = {p.stem for p in EXAMPLES}
    for name in names:
        if name.endswith("_true"):
            assert name.replace("_true", "_planted") in names


def test_results_match_the_recorded_verdicts():
    results = json.loads((ROOT / "evals" / "results" / "planted.json").read_text(encoding="utf-8"))
    assert results["claims"] == 40 and results["planted_that_passed"] == 0 and results["true_that_failed"] == 0
    for name, row in results["rows"].items():
        verdict = json.loads((ROOT / "evals" / "planted" / "claims" / f"{name}.verdict.json").read_text(encoding="utf-8"))
        assert (row["status"], row["stage"]) == (verdict["status"], verdict["stage"])


def test_readme_demo_output_is_what_the_command_prints():
    text, ok = demo(ROOT)
    assert ok
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(r"```text\n(.*?)```", readme, re.DOTALL).group(1)
    assert block.strip() in text


def test_demo_image_shows_the_real_output():
    svg = (ROOT / "docs" / "demo.svg").read_text(encoding="utf-8")
    text, _ = demo(ROOT)
    for line in ("gpu_memory_planted: FAIL", "gpu_memory_true: PASS"):
        assert line in text and line in svg


def test_no_absolute_path_in_any_recorded_verdict():
    for path in [*ROOT.joinpath("examples").rglob("*.verdict.*"), *ROOT.joinpath("evals").rglob("*.verdict.*")]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"[A-Za-z]:[\\/]|/home/|/Users/|/tmp/", text), path
