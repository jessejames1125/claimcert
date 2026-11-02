from pathlib import Path

import pytest
import yaml

from claimcert.claims import ClaimError, header, load_claim, render, statement_block, write_new
from claimcert.registry import load_registry
from claimcert.units import DimensionError, UnitError

FIX = Path(__file__).parent / "fixtures"
REG = load_registry(FIX / "registry.yaml")


def claim_file(tmp_path, name, **over) -> Path:
    data = {"name": name, "type": "bound", "intent": "test",
            "variables": {"z": {"unit": "m", "domain": "real"}},
            "assumptions": {"fx_cap": ["z"]}, "constants": {"C": "4 m"}, "goals": ["z <= C"]}
    data.update(over)
    p = tmp_path / f"{name}.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_statement_for_fixture():
    block = statement_block(load_claim(FIX / "claims" / "fx_pass.yaml", REG), REG)
    assert "theorem fx_pass (z : ℝ) (h_fx_cap : A_fx_cap z) (h_fx_unused_cap : A_fx_unused_cap z) :" in block
    assert "    z ≤ (4 : ℝ) := by" in block


def test_header_has_markers_and_kernel_trust():
    h = header(load_claim(FIX / "claims" / "fx_pass.yaml", REG), REG)
    assert h.startswith("import ClaimCert\nimport ClaimCertTest.Assumptions\n")
    assert 'set_option leancert.trust "kernel"' in h
    assert h.rstrip().endswith("-- CC-END")


def test_domains_and_conditions(tmp_path):
    p = claim_file(tmp_path, "c_dom", variables={"z": {"unit": "m", "domain": ["0 m", "1 m"]},
                                                 "y": {"unit": "m", "domain": "positive"}},
                   conditions=["y <= z"], assumptions={"fx_cap": ["z"]})
    block = statement_block(load_claim(p, REG), REG)
    assert "(dom_z : z ∈ Set.Icc (0 : ℝ) (1 : ℝ))" in block
    assert "(dom_y : 0 < y)" in block
    assert "(dom_c1 : y ≤ z)" in block


def test_dimension_obligations_emitted(tmp_path):
    block = statement_block(load_claim(claim_file(tmp_path, "c_obl"), REG), REG)
    assert "example : (ClaimCert.Dim.mk 1 0 0 0 0 0 0 0) = (ClaimCert.Dim.mk 1 0 0 0 0 0 0 0) := by decide" in block


def test_cylinder_claim(tmp_path):
    p = claim_file(tmp_path, "c_cyl", type="not_fits_in_sphere", variables={}, assumptions={},
                   constants={}, goals=[], cylinder={"r": "5 cm", "h": "4 cm", "R": "6 cm"})
    block = statement_block(load_claim(p, REG), REG)
    assert "¬ ClaimCert.CylinderFitsInSphere (1 / 20 : ℝ) (1 / 25 : ℝ) (3 / 50 : ℝ) := by" in block


@pytest.mark.parametrize("bad", ["neutron-floor", "2fast", "theorem"])
def test_bad_names_rejected(tmp_path, bad):
    with pytest.raises(ClaimError):
        load_claim(claim_file(tmp_path, bad), REG)


def test_name_must_match_stem(tmp_path):
    p = claim_file(tmp_path, "c_stem")
    p2 = p.with_name("other.yaml")
    p.rename(p2)
    with pytest.raises(ClaimError):
        load_claim(p2, REG)


def test_goal_dimension_mismatch(tmp_path):
    with pytest.raises(DimensionError):
        load_claim(claim_file(tmp_path, "c_dim", constants={"C": "4 s"}), REG)


def test_assumption_arg_dimension_mismatch(tmp_path):
    p = claim_file(tmp_path, "c_arg", variables={"z": {"unit": "s", "domain": "real"}}, constants={"C": "4 s"})
    with pytest.raises(DimensionError):
        load_claim(p, REG)


def test_unknown_assumption(tmp_path):
    with pytest.raises(ClaimError):
        load_claim(claim_file(tmp_path, "c_unk", assumptions={"nope": ["z"]}), REG)


def test_wrong_arity(tmp_path):
    with pytest.raises(ClaimError):
        load_claim(claim_file(tmp_path, "c_ar", assumptions={"fx_cap": []}), REG)


def test_variable_units_must_be_si(tmp_path):
    with pytest.raises(UnitError):
        load_claim(claim_file(tmp_path, "c_si", variables={"z": {"unit": "cm", "domain": "real"}}), REG)


def test_point_claim_rejects_variables(tmp_path):
    with pytest.raises(ClaimError):
        load_claim(claim_file(tmp_path, "c_pt", type="point"), REG)


def test_render_and_utf8_round_trip(tmp_path):
    claim = load_claim(FIX / "claims" / "fx_pass.yaml", REG)
    text = render(claim, REG, "  sorry\n")
    out = tmp_path / "fx.lean"
    out.write_text(text, encoding="utf-8", newline="\n")
    assert out.read_bytes().decode("utf-8") == text
    assert "ℝ" in text and text.rstrip().endswith("#cc_report fx_pass")


def test_write_new_keeps_old_proof_on_force(tmp_path):
    src = FIX / "claims" / "fx_pass.yaml"
    dst = tmp_path / "fx_pass.yaml"
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    reg_path = FIX / "registry.yaml"
    lean = write_new(dst, reg_path, FIX / "claims" / "fx_pass.proof.lean")
    assert "linarith" in lean.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_new(dst, reg_path)
    write_new(dst, reg_path, force=True)
    assert "linarith" in lean.read_text(encoding="utf-8")


def test_top_level_must_be_mapping(tmp_path):
    p = tmp_path / "c_list.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ClaimError):
        load_claim(p, REG)


@pytest.mark.parametrize("bad", [123, None])
def test_non_string_name_rejected(tmp_path, bad):
    p = tmp_path / "c_nm.yaml"
    p.write_text(yaml.safe_dump({"name": bad, "type": "bound", "intent": "t", "goals": ["1 <= 2"]}),
                 encoding="utf-8")
    with pytest.raises(ClaimError):
        load_claim(p, REG)


def test_variable_spec_must_be_mapping(tmp_path):
    with pytest.raises(ClaimError, match="z"):
        load_claim(claim_file(tmp_path, "c_vs", variables={"z": "m"}), REG)


def test_cylinder_missing_key_named(tmp_path):
    p = claim_file(tmp_path, "c_cy2", type="fits_in_sphere", variables={}, assumptions={},
                   constants={}, goals=[], cylinder={"r": "5 cm", "R": "6 cm"})
    with pytest.raises(ClaimError, match="h"):
        load_claim(p, REG)


def test_assumption_args_must_be_list(tmp_path):
    with pytest.raises(ClaimError):
        load_claim(claim_file(tmp_path, "c_al", assumptions={"fx_cap": "z"}), REG)


def test_variable_name_with_newline_rejected(tmp_path):
    with pytest.raises(ClaimError):
        load_claim(claim_file(tmp_path, "c_nl", variables={"z\n": {"unit": "m", "domain": "real"}}), REG)


def test_unquoted_constant_number(tmp_path):
    p = claim_file(tmp_path, "c_num", variables={"z": {"unit": "1", "domain": "real"}},
                   assumptions={}, constants={"C": 4})
    assert "z ≤ (4 : ℝ)" in statement_block(load_claim(p, REG), REG)


@pytest.mark.parametrize("vname", ["c1", "c12", "dom_z", "h_fx_cap"])
def test_variable_names_that_would_collide_with_generated_binders_are_refused(tmp_path, vname):
    p = claim_file(tmp_path, "c_clash", variables={vname: {"unit": "m", "domain": "positive"}},
                   conditions=[f"{vname} <= C"], assumptions={}, goals=[f"{vname} <= C"])
    with pytest.raises(ClaimError, match="reserved"):
        load_claim(p, REG)


def test_header_names_the_claim_not_the_file_on_disk(tmp_path):
    p = claim_file(tmp_path, "c_head")
    odd = p.with_name("c_head.YAML")
    p.rename(odd)
    assert "from c_head.yaml;" in header(load_claim(odd, REG), REG)
