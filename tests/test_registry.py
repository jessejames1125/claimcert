from pathlib import Path

import pytest
import yaml

from claimcert.registry import Kind, RegistryError, lean_assumptions, load_registry
from claimcert.units import DimensionError, UnitError

FIX = Path(__file__).parent / "fixtures"


def write(tmp_path, data) -> Path:
    p = tmp_path / "reg.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def base(**over):
    a = {"name": "cap", "kind": "FIT", "args": {"z": "m"}, "statement": "z <= Zmax",
         "constants": {"Zmax": "3 m"}, "range": "r", "source": "s", "date": "2026-10-13"}
    a.update(over)
    return {"lean_namespace": "NS", "lean_module": "NS.Assumptions", "assumptions": [a]}


def test_fixture_loads(tmp_path):
    reg = load_registry(FIX / "registry.yaml")
    assert reg.assumptions["fx_cap"].kind is Kind.FIT
    assert reg.assumptions["fx_fit_linear"].valid_when["u"] == (1, 6)


def test_dimension_mismatch_in_statement_rejected(tmp_path):
    with pytest.raises(DimensionError):
        load_registry(write(tmp_path, base(statement="z <= 10", constants={})))


def test_fit_needs_range_and_date(tmp_path):
    with pytest.raises(RegistryError):
        load_registry(write(tmp_path, base(range=None)))
    with pytest.raises(RegistryError):
        load_registry(write(tmp_path, base(date=None)))


def test_number_needs_produced_by(tmp_path):
    with pytest.raises(RegistryError):
        load_registry(write(tmp_path, base(kind="NUMBER")))


def test_unknown_kind_rejected(tmp_path):
    with pytest.raises(RegistryError):
        load_registry(write(tmp_path, base(kind="GUESS")))


def test_args_must_be_coherent_si(tmp_path):
    with pytest.raises(UnitError):
        load_registry(write(tmp_path, base(args={"z": "cm"})))


def test_unknown_symbol_in_statement_rejected(tmp_path):
    with pytest.raises(RegistryError):
        load_registry(write(tmp_path, base(statement="q <= Zmax")))


def test_lean_defs(tmp_path):
    text = lean_assumptions(load_registry(write(tmp_path, base())))
    assert "def A_cap (z : ℝ) : Prop :=" in text
    assert "z ≤ (3 : ℝ)" in text
    assert text.startswith("import ClaimCert\n")


def test_valid_when_becomes_premise(tmp_path):
    data = base(args={"u": "1", "w": "1"}, statement="w <= 3 * u + 2", constants={},
                valid_when={"u": ["1", "6"]})
    text = lean_assumptions(load_registry(write(tmp_path, data)))
    assert "u ∈ Set.Icc (1 : ℝ) (6 : ℝ) → w ≤ (((3 : ℝ) * u) + (2 : ℝ))" in text


@pytest.mark.parametrize("data", [["not", "a", "dict"], "text"])
def test_top_level_must_be_mapping(tmp_path, data):
    p = tmp_path / "reg.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(RegistryError):
        load_registry(p)


@pytest.mark.parametrize("name", [123, None, "cap\n"])
def test_bad_assumption_names_rejected(tmp_path, name):
    with pytest.raises(RegistryError):
        load_registry(write(tmp_path, base(name=name)))


def test_valid_when_bounds_must_be_pair(tmp_path):
    data = base(args={"u": "1", "w": "1"}, statement="w <= u", constants={}, valid_when={"u": ["1"]})
    with pytest.raises(RegistryError, match="valid_when"):
        load_registry(write(tmp_path, data))


def test_unquoted_numbers_are_accepted(tmp_path):
    data = base(args={"u": 1, "w": "1"}, statement="w <= 3 * u + C", constants={"C": 2},
                valid_when={"u": [1, 6]})
    reg = load_registry(write(tmp_path, data))
    assert reg.assumptions["cap"].valid_when["u"] == (1, 6)


def test_block_comment_opener_neutralised(tmp_path):
    text = lean_assumptions(load_registry(write(tmp_path, base(source="a /- b -/ c"))))
    doc = text.split("/-- ", 1)[1].split(" -/\n", 1)[0]
    assert "/-" not in doc and "-/" not in doc


@pytest.mark.parametrize("key,value", [("lean_module", "NS.Assumptions\nimport Evil"), ("lean_module", "NS..A"),
                                       ("lean_namespace", "NS Evil"), ("lean_namespace", "1NS"),
                                       ("lean_module", ["NS"])])
def test_lean_names_must_be_dotted_identifiers(tmp_path, key, value):
    data = base()
    data[key] = value
    with pytest.raises(RegistryError):
        load_registry(write(tmp_path, data))
