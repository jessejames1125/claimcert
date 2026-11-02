"""Assumption registry: every hypothesis a claim may use, typed by kind, with its source."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from pathlib import Path

import yaml

from . import expr as E
from .units import Dim, Quantity, UnitError, parse_quantity, parse_unit

NAME = re.compile(r"^[a-z][a-z0-9_]*$")
LEAN_DOTTED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")


class Kind(str, Enum):
    LAW = "LAW"
    FIT = "FIT"
    TECH = "TECH"
    NUMBER = "NUMBER"


class RegistryError(ValueError):
    pass


@dataclass
class Assumption:
    name: str
    kind: Kind
    args: dict[str, Dim]
    statement: E.Cmp
    constants: dict[str, Quantity]
    source: str
    range: str | None = None
    valid_when: dict[str, tuple[Fraction, Fraction]] = field(default_factory=dict)
    date: str | None = None
    produced_by: str | None = None


@dataclass
class Registry:
    lean_namespace: str
    lean_module: str
    assumptions: dict[str, Assumption]


def si_dim(unit: str, where: str) -> Dim:
    factor, dim = parse_unit(str(unit))
    if factor != 1:
        raise UnitError(f"{where}: variables must use coherent SI units, got {unit!r}")
    return dim


def _load_one(raw: dict) -> Assumption:
    if not isinstance(raw, dict):
        raise RegistryError(f"each assumption must be a mapping, got {raw!r}")
    name = raw.get("name", "")
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise RegistryError(f"assumption name {name!r} must match {NAME.pattern}")
    try:
        kind = Kind(raw.get("kind"))
    except ValueError as e:
        raise RegistryError(f"{name}: kind must be one of LAW, FIT, TECH, NUMBER") from e
    if not raw.get("source"):
        raise RegistryError(f"{name}: source is required (write UNSOURCED if there is none)")
    if kind is Kind.FIT and not (raw.get("range") and raw.get("date")):
        raise RegistryError(f"{name}: a FIT needs range and date")
    if kind is Kind.TECH and not raw.get("date"):
        raise RegistryError(f"{name}: a TECH limit needs date")
    if kind is Kind.NUMBER and not raw.get("produced_by"):
        raise RegistryError(f"{name}: a NUMBER needs produced_by")
    if not isinstance(raw.get("args") or {}, dict) or not isinstance(raw.get("constants") or {}, dict):
        raise RegistryError(f"{name}: args and constants must be mappings")
    args = {k: si_dim(v, f"{name}.args.{k}") for k, v in (raw.get("args") or {}).items()}
    constants = {k: parse_quantity(v) for k, v in (raw.get("constants") or {}).items()}
    if set(args) & set(constants):
        raise RegistryError(f"{name}: names used as both arg and constant: {set(args) & set(constants)}")
    statement = E.parse(str(raw.get("statement", "")))
    if not isinstance(statement, E.Cmp):
        raise RegistryError(f"{name}: statement must be one comparison")
    unknown = E.symbols(statement) - set(args) - set(constants)
    if unknown:
        raise RegistryError(f"{name}: unknown symbols in statement: {sorted(unknown)}")
    E.check_dims(statement, args | {k: q.dim for k, q in constants.items()})
    valid_when = {}
    if not isinstance(raw.get("valid_when") or {}, dict):
        raise RegistryError(f"{name}: valid_when must be a mapping of arg to [lo, hi]")
    for var, bounds in (raw.get("valid_when") or {}).items():
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise RegistryError(f"{name}: valid_when for {var!r} must be a two-item list [lo, hi]")
        if var not in args:
            raise RegistryError(f"{name}: valid_when names {var!r}, which is not an arg")
        lo, hi = (parse_quantity(b) for b in bounds)
        if lo.dim != args[var] or hi.dim != args[var]:
            raise RegistryError(f"{name}: valid_when bounds for {var} have the wrong dimension")
        if lo.si_value > hi.si_value:
            raise RegistryError(f"{name}: valid_when lower bound above upper bound for {var}")
        valid_when[var] = (lo.si_value, hi.si_value)
    return Assumption(name, kind, args, statement, constants, raw["source"], raw.get("range"),
                      valid_when, raw.get("date"), raw.get("produced_by"))


def load_registry(path) -> Registry:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RegistryError(f"registry {path}: top level must be a mapping")
    for key in ("lean_namespace", "lean_module", "assumptions"):
        if key not in data:
            raise RegistryError(f"registry {path}: missing {key}")
    for key in ("lean_namespace", "lean_module"):
        if not isinstance(data[key], str) or not LEAN_DOTTED.fullmatch(data[key]):
            raise RegistryError(f"registry {path}: {key} must be a dotted Lean identifier, got {data[key]!r}")
    out: dict[str, Assumption] = {}
    if not isinstance(data["assumptions"], list):
        raise RegistryError(f"registry {path}: assumptions must be a list")
    for raw in data["assumptions"]:
        a = _load_one(raw)
        if a.name in out:
            raise RegistryError(f"duplicate assumption {a.name}")
        out[a.name] = a
    return Registry(data["lean_namespace"], data["lean_module"], out)


def lean_assumption_def(a: Assumption) -> str:
    doc = f"{a.kind.value}. Range: {a.range or 'n/a'}. Source: {a.source}".replace("-/", "- /").replace("/-", "/ -")
    binders = f" ({' '.join(a.args)} : ℝ)" if a.args else ""
    body = E.lean(a.statement, {k: q.si_value for k, q in a.constants.items()})
    premises = [f"{v} ∈ Set.Icc {E.lean_number(lo)} {E.lean_number(hi)}" for v, (lo, hi) in a.valid_when.items()]
    if premises:
        body = " → ".join(premises + [body])
    return f"/-- {doc} -/\ndef A_{a.name}{binders} : Prop :=\n  {body}\n"


def lean_assumptions(reg: Registry) -> str:
    parts = ["import ClaimCert", "", "-- generated by claimcert gen-assumptions; do not edit", "",
             f"namespace {reg.lean_namespace}", ""]
    parts += [lean_assumption_def(a) for a in reg.assumptions.values()]
    parts.append(f"end {reg.lean_namespace}")
    return "\n".join(parts) + "\n"
