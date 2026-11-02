"""SI dimensions plus information (bits), and exact unit conversion."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

BASE = ("L", "M", "T", "I", "Th", "N", "J", "Bit")


class DimensionError(ValueError):
    pass


class UnitError(ValueError):
    pass


@dataclass(frozen=True)
class Dim:
    exps: tuple[int, ...] = (0, 0, 0, 0, 0, 0, 0, 0)

    def __mul__(self, other: Dim) -> Dim:
        return Dim(tuple(a + b for a, b in zip(self.exps, other.exps)))

    def __truediv__(self, other: Dim) -> Dim:
        return Dim(tuple(a - b for a, b in zip(self.exps, other.exps)))

    def __pow__(self, k: int) -> Dim:
        return Dim(tuple(a * k for a in self.exps))

    def root(self, n: int) -> Dim:
        if any(a % n for a in self.exps):
            raise DimensionError(f"cannot take root {n} of dimension {self}")
        return Dim(tuple(a // n for a in self.exps))

    @property
    def is_dimensionless(self) -> bool:
        return all(a == 0 for a in self.exps)

    def __str__(self) -> str:
        return " ".join(f"{b}^{e}" for b, e in zip(BASE, self.exps) if e) or "1"


ONE = Dim()


def _d(**kw: int) -> Dim:
    return Dim(tuple(kw.get(b, 0) for b in BASE))


EV = Fraction(1602176634, 10**28)  # joules, exact by the 2019 SI definition
_ENERGY = _d(L=2, M=1, T=-2)
_POWER = _d(L=2, M=1, T=-3)
_PRESSURE = _d(L=-1, M=1, T=-2)
_FORCE = _d(L=1, M=1, T=-2)
_BIT = _d(Bit=1)
LBF = Fraction(44482216152605, 10**13)  # newtons, exact by the international pound and standard gravity

UNITS: dict[str, tuple[Fraction, Dim]] = {
    "m": (Fraction(1), _d(L=1)),
    "cm": (Fraction(1, 100), _d(L=1)),
    "mm": (Fraction(1, 1000), _d(L=1)),
    "km": (Fraction(1000), _d(L=1)),
    "ft": (Fraction(3048, 10000), _d(L=1)),
    "b": (Fraction(1, 10**28), _d(L=2)),
    "s": (Fraction(1), _d(T=1)),
    "ms": (Fraction(1, 10**3), _d(T=1)),
    "us": (Fraction(1, 10**6), _d(T=1)),
    "ns": (Fraction(1, 10**9), _d(T=1)),
    "min": (Fraction(60), _d(T=1)),
    "h": (Fraction(3600), _d(T=1)),
    "day": (Fraction(86400), _d(T=1)),
    "kg": (Fraction(1), _d(M=1)),
    "g": (Fraction(1, 1000), _d(M=1)),
    "A": (Fraction(1), _d(I=1)),
    "MA": (Fraction(10**6), _d(I=1)),
    "K": (Fraction(1), _d(Th=1)),
    "mol": (Fraction(1), _d(N=1)),
    "cd": (Fraction(1), _d(J=1)),
    "T": (Fraction(1), _d(M=1, T=-2, I=-1)),
    "J": (Fraction(1), _ENERGY),
    "eV": (EV, _ENERGY),
    "keV": (EV * 10**3, _ENERGY),
    "MeV": (EV * 10**6, _ENERGY),
    "W": (Fraction(1), _POWER),
    "kW": (Fraction(10**3), _POWER),
    "MW": (Fraction(10**6), _POWER),
    "N": (Fraction(1), _FORCE),
    "lbf": (LBF, _FORCE),
    "Pa": (Fraction(1), _PRESSURE),
    "MPa": (Fraction(10**6), _PRESSURE),
    "bit": (Fraction(1), _BIT),
    "kbit": (Fraction(10**3), _BIT),
    "Mbit": (Fraction(10**6), _BIT),
    "Gbit": (Fraction(10**9), _BIT),
    "B": (Fraction(8), _BIT),
    "kB": (Fraction(8 * 10**3), _BIT),
    "MB": (Fraction(8 * 10**6), _BIT),
    "GB": (Fraction(8 * 10**9), _BIT),
    "TB": (Fraction(8 * 10**12), _BIT),
    "KiB": (Fraction(8 * 2**10), _BIT),
    "MiB": (Fraction(8 * 2**20), _BIT),
    "GiB": (Fraction(8 * 2**30), _BIT),
    "TiB": (Fraction(8 * 2**40), _BIT),
}

_TOKEN = re.compile(r"^([A-Za-z]+)(?:\^(-?\d+))?$")


def parse_unit(text: str) -> tuple[Fraction, Dim]:
    """'cm^-3', 'W/m^2', 'kg m^-3', '1' or '' -> (factor to SI, dimension)."""
    text = text.strip()
    if text in ("", "1"):
        return Fraction(1), ONE
    if text.count("/") > 1:
        raise UnitError(f"at most one '/' is allowed in unit {text!r}")
    num, _, den = text.partition("/")
    factor, dim = Fraction(1), ONE
    for part, sign in ((num, 1), (den, -1)):
        for tok in part.replace("*", " ").split():
            m = _TOKEN.match(tok)
            if not m or m.group(1) not in UNITS:
                raise UnitError(f"unknown unit token {tok!r} in {text!r}")
            f, d = UNITS[m.group(1)]
            k = sign * int(m.group(2) or 1)
            factor *= f**k
            dim = dim * d**k
    return factor, dim


@dataclass(frozen=True)
class Quantity:
    si_value: Fraction
    dim: Dim


def parse_quantity(text: str) -> Quantity:
    """'2.5 cm' -> Quantity(Fraction(1, 40), length). The number is read exactly."""
    num, _, unit = str(text).strip().partition(" ")
    try:
        value = Fraction(Decimal(num))
    except (InvalidOperation, ValueError, OverflowError) as e:
        raise UnitError(f"bad number in quantity {text!r}") from e
    factor, dim = parse_unit(unit)
    return Quantity(value * factor, dim)
