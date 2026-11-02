from fractions import Fraction

import pytest

from claimcert.units import ONE, Dim, DimensionError, UnitError, parse_quantity, parse_unit


def test_cm_minus_three_is_exact():
    factor, dim = parse_unit("cm^-3")
    assert factor == Fraction(10**6)
    assert dim.exps == (-3, 0, 0, 0, 0, 0, 0, 0)


def test_barn_is_area():
    factor, dim = parse_unit("b")
    assert factor == Fraction(1, 10**28)
    assert dim == parse_unit("m^2")[1]


def test_compound_unit_with_slash():
    factor, dim = parse_unit("W/m^2")
    assert factor == 1
    assert dim.exps == (0, 1, -3, 0, 0, 0, 0, 0)


def test_mev_is_exact_si():
    factor, _ = parse_unit("MeV")
    assert factor == Fraction(1602176634, 10**28) * 10**6


def test_quantity_converts_to_si_exactly():
    q = parse_quantity("1.25e23 cm^-3")
    assert q.si_value == Fraction(125) * 10**27
    assert q.dim == parse_unit("m^-3")[1]


def test_dimensionless_quantity():
    q = parse_quantity("6")
    assert q.si_value == 6 and q.dim == ONE


def test_unknown_unit_rejected():
    with pytest.raises(UnitError):
        parse_unit("furlong")


def test_two_slashes_rejected():
    with pytest.raises(UnitError):
        parse_unit("m/s/s")


def test_bad_number_rejected():
    with pytest.raises(UnitError):
        parse_quantity("abc m")


def test_root_of_odd_exponent_raises():
    with pytest.raises(DimensionError):
        parse_unit("m^3")[1].root(2)


def test_dim_algebra():
    length = parse_unit("m")[1]
    assert (length**2 / length) == length
    assert (length / length).is_dimensionless


def test_bytes_and_bits_share_a_dimension_with_exact_factors():
    gib, dim = parse_unit("GiB")
    gb, dim2 = parse_unit("GB")
    assert gib == 8 * 2**30 and gb == 8 * 10**9
    assert dim == dim2 == parse_unit("bit")[1]
    assert not dim.is_dimensionless


def test_bits_per_second_is_not_bytes():
    assert parse_quantity("1 Gbit/s").si_value == 10**9
    assert parse_quantity("1 GB/s").si_value == 8 * 10**9
    assert parse_quantity("1 GB/s").dim != parse_quantity("1 GB").dim


def test_pound_force_and_days_are_exact():
    assert parse_quantity("1 lbf s").si_value == Fraction(44482216152605, 10**13)
    assert parse_quantity("1 lbf s").dim == parse_quantity("1 N s").dim
    assert parse_quantity("1 day").si_value == 86400
