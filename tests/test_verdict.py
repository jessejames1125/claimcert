import shutil
from pathlib import Path

from claimcert.claims import load_claim
from claimcert.registry import load_registry
from claimcert.verdict import assemble

FIX = Path(__file__).parent / "fixtures"
REG = load_registry(FIX / "registry.yaml")


def claim(tmp_path):
    dst = tmp_path / "fx_pass.yaml"
    shutil.copy(FIX / "claims" / "fx_pass.yaml", dst)
    return load_claim(dst, REG)


def rep(binders=None, axioms=None, theorem="fx_pass"):
    return {"theorem": theorem, "axioms": axioms if axioms is not None else ["propext"],
            "binders": binders if binders is not None else []}


def b(name, used=True, head=None, prop=True):
    return {"name": name, "prop": prop, "head": head or f"A_{name[2:]}", "used": used}


def test_nonstandard_axiom(tmp_path):
    v = assemble(claim(tmp_path), REG, rep(axioms=["propext", "Lean.ofReduceBool"]), 1.0)
    assert v["status"] == "FAIL" and v["stage"] == "axioms"


def test_wrong_theorem(tmp_path):
    assert assemble(claim(tmp_path), REG, rep(theorem="other_fx_pass"), 1.0)["stage"] == "report"


def test_unregistered_hypothesis(tmp_path):
    v = assemble(claim(tmp_path), REG, rep([b("h_bogus", head="LE.le")]), 1.0)
    assert v["stage"] == "assumptions"


def test_used_and_unused_sorting(tmp_path):
    v = assemble(claim(tmp_path), REG, rep([b("h_fx_cap"), b("h_fx_unused_cap", used=False),
                                            {"name": "x", "prop": False, "head": "", "used": True}]), 1.0)
    assert v["status"] == "PASS"
    assert v["assumptions"]["FIT"] == ["fx_cap"] and v["unused_assumptions"] == ["fx_unused_cap"]


def test_bad_shapes_fail_not_raise(tmp_path):
    c = claim(tmp_path)
    for bad in [{"foo": 1}, {"theorem": "fx_pass", "binders": "x", "axioms": []},
                {"theorem": "fx_pass", "binders": [{"name": "h"}], "axioms": []},
                {"theorem": "fx_pass", "binders": [], "axioms": [1]},
                {"theorem": 5, "binders": [], "axioms": []}]:
        assert assemble(c, REG, bad, 1.0)["stage"] == "report"


PREMISE_CLAIM = """name: fx_prem
type: floor
intent: "z is at least 1 m when z is at least 1 m."
variables:
  z: {unit: "m", domain: positive}
  w: {unit: "1", domain: ["1", "6"]}
  y: {unit: "1", domain: real}
conditions:
  - "z >= C"
assumptions:
  fx_cap: [z]
constants:
  C: "1 m"
goals:
  - "z >= C"
"""


def test_every_premise_is_on_the_verdict(tmp_path):
    from claimcert.claims import statement_block
    from claimcert.verdict import summary_text
    p = tmp_path / "fx_prem.yaml"
    p.write_text(PREMISE_CLAIM, encoding="utf-8")
    c = load_claim(p, REG)
    v = assemble(c, REG, rep([b("h_fx_cap", used=False), {"name": "dom_z", "prop": True, "head": "LT.lt", "used": True},
                              {"name": "dom_c1", "prop": True, "head": "GE.ge", "used": True}], theorem="fx_prem"), 1.0)
    assert v["status"] == "PASS"
    assert [(x["name"], x["kind"]) for x in v["premises"]] == [
        ("dom_z", "domain"), ("dom_w", "interval"), ("dom_c1", "condition")]
    assert v["premises"][0]["statement"] == "0 < z"
    block = statement_block(c, REG)
    for x in v["premises"]:
        assert f"({x['name']} : {x['statement']})" in block
    text = summary_text(v)
    assert "dom_w" in text and "w ∈ Set.Icc" in text and "dom_c1" in text


def test_no_premises_says_none(tmp_path):
    from claimcert.verdict import summary_text
    v = assemble(claim(tmp_path), REG, rep([b("h_fx_cap")]), 1.0)
    assert v["premises"] == []
    assert "premises from the claim: none" in summary_text(v)


NUMBER_REG = """lean_namespace: NS
lean_module: NS.Assumptions
assumptions:
  - name: n_cap
    kind: NUMBER
    args: {z: "m"}
    statement: "z <= Zc"
    constants: {Zc: "3 m"}
    source: "UNSOURCED (test)"
    produced_by: "calc.py at commit abc123, inputs in.csv"
"""


def test_number_provenance_reaches_the_verdict(tmp_path):
    from claimcert.verdict import summary_text
    rp = tmp_path / "reg.yaml"
    rp.write_text(NUMBER_REG, encoding="utf-8")
    reg = load_registry(rp)
    cp = tmp_path / "n_claim.yaml"
    cp.write_text("name: n_claim\ntype: bound\nintent: x\nvariables:\n  z: {unit: m, domain: real}\n"
                  "assumptions:\n  n_cap: [z]\nconstants:\n  C: 4 m\ngoals:\n  - z <= C\n", encoding="utf-8")
    v = assemble(load_claim(cp, reg), reg, rep([b("h_n_cap", head="NS.A_n_cap")], theorem="n_claim"), 1.0)
    assert v["details"]["n_cap"]["produced_by"] == "calc.py at commit abc123, inputs in.csv"
    assert "produced by: calc.py at commit abc123" in summary_text(v)
