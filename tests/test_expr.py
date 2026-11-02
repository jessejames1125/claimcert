from fractions import Fraction

import pytest

from claimcert import expr as E
from claimcert.units import ONE, DimensionError, parse_unit

L = parse_unit("m")[1]
ENV = {"N": L**-3, "sigma": L**2, "x": L, "F": L}


def test_parse_comparison_and_exact_number():
    node = E.parse("x >= 2.5")
    assert isinstance(node, E.Cmp) and node.op == "≥"
    assert node.right == E.Num(Fraction(25, 10))


def test_scientific_literal_is_exact():
    assert E.parse("1e29") == E.Num(Fraction(10**29))


def test_dims_of_attenuation_length():
    assert E.check_dims(E.parse("log(10) / (N * sigma)"), ENV) == L


def test_adding_unlike_dims_raises():
    with pytest.raises(DimensionError):
        E.check_dims(E.parse("x + N"), ENV)


def test_log_of_dimensional_raises():
    with pytest.raises(DimensionError):
        E.check_dims(E.parse("log(x)"), ENV)


def test_comparison_of_unlike_dims_raises():
    with pytest.raises(DimensionError):
        E.check_dims(E.parse("x >= N"), ENV)


def test_sqrt_halves_dims():
    assert E.check_dims(E.parse("sqrt(sigma)"), ENV) == L


def test_unknown_symbol_raises():
    with pytest.raises(E.ExprError):
        E.check_dims(E.parse("y"), ENV)


def test_non_integer_exponent_rejected():
    with pytest.raises(E.ExprError):
        E.parse("x ** 0.5")


def test_two_comparisons_rejected():
    with pytest.raises(E.ExprError):
        E.parse("0 < x < 1")


def test_lean_emission_substitutes_constants():
    node = E.parse("x >= F")
    assert E.lean(node, {"F": Fraction(1, 40)}) == "x ≥ (1 / 40 : ℝ)"


def test_lean_emission_of_functions_and_powers():
    out = E.lean(E.parse("phi0 * exp(-(N * sigma * x)) + x ** -2"), {})
    assert out == "((phi0 * (Real.exp (-((N * sigma) * x)))) + (x ^ (-2 : ℤ)))"


def test_lean_number_integer_and_fraction():
    assert E.lean_number(Fraction(10)) == "(10 : ℝ)"
    assert E.lean_number(Fraction(1, 2)) == "(1 / 2 : ℝ)"


def test_dim_literal_parenthesises_negatives():
    assert E.lean_dim_literal(L**-3) == "(ClaimCert.Dim.mk (-3) 0 0 0 0 0 0 0)"


def test_obligations_for_comparison_and_log():
    obs = E.dim_obligations(E.parse("log(10) / (N * sigma) >= F"), ENV)
    assert ("ClaimCert.Dim.one", "ClaimCert.Dim.one") in obs
    lhs, rhs = obs[-1]
    assert lhs.startswith("(ClaimCert.Dim.div ") and rhs == E.lean_dim_literal(L)


def test_symbols():
    assert E.symbols(E.parse("log(10) / (N * sigma) >= F")) == {"N", "sigma", "F"}


def test_sin_cos_parse_dims_and_lean():
    env = {"th": ONE, "r": L}
    node = E.parse("r * cos(th) + r * sin(th) >= r")
    assert E.check_dims(node, env) == ONE
    assert "Real.cos th" in E.lean(node, {}) and "Real.sin th" in E.lean(node, {})


def test_sin_of_dimensional_raises():
    with pytest.raises(DimensionError):
        E.check_dims(E.parse("sin(r)"), {"r": L})
