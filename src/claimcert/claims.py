"""Claims: YAML in, a Lean file with a generated, frozen statement out."""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import yaml

from . import expr as E
from .registry import Registry, load_registry, si_dim
from .units import Dim, DimensionError, Quantity, parse_quantity

NAME = re.compile(r"^[a-z][a-z0-9_]*$")
LEAN_KEYWORDS = {"theorem", "lemma", "def", "fun", "let", "have", "show", "by", "at", "from", "in",
                 "open", "end", "namespace", "section", "variable", "example", "instance", "structure",
                 "class", "where", "do", "then", "else", "if", "match", "with", "import", "axiom"}
TYPES = {"bound", "floor", "point", "fits_in_sphere", "not_fits_in_sphere"}
CYLINDER_TYPES = {"fits_in_sphere", "not_fits_in_sphere"}
BEGIN, END = "-- CC-BEGIN", "-- CC-END"


class ClaimError(ValueError):
    pass


@dataclass
class Variable:
    name: str
    dim: Dim
    domain: object


@dataclass
class Claim:
    name: str
    type: str
    intent: str
    variables: list[Variable]
    conditions: list
    assumptions: dict[str, list[str]]
    constants: dict[str, Quantity]
    goals: list
    cylinder: tuple[Fraction, Fraction, Fraction] | None
    path: Path


def lean_path(claim_path) -> Path:
    return Path(claim_path).with_suffix(".lean")


def _domain(name: str, raw, dim: Dim):
    if raw in ("real", "positive"):
        return raw
    if isinstance(raw, list) and len(raw) == 2:
        lo, hi = (parse_quantity(b) for b in raw)
        if lo.dim != dim or hi.dim != dim:
            raise DimensionError(f"domain bounds of {name} have the wrong dimension")
        if lo.si_value > hi.si_value:
            raise ClaimError(f"domain of {name}: lower bound above upper bound")
        return (lo.si_value, hi.si_value)
    raise ClaimError(f"domain of {name} must be real, positive, or [lo, hi]")


def load_claim(path, reg: Registry) -> Claim:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ClaimError(f"{path.name}: top level must be a mapping")
    name = raw.get("name", "")
    if not isinstance(name, str) or not NAME.fullmatch(name) or name in LEAN_KEYWORDS:
        raise ClaimError(f"claim name {name!r} must match {NAME.pattern} and not be a Lean keyword")
    if name != path.stem:
        raise ClaimError(f"claim name {name!r} must equal the file name {path.stem!r}")
    ctype = raw.get("type")
    if not isinstance(ctype, str) or ctype not in TYPES:
        raise ClaimError(f"{name}: type must be one of {sorted(TYPES)}")
    if not raw.get("intent"):
        raise ClaimError(f"{name}: intent is required")
    variables = []
    if not isinstance(raw.get("variables") or {}, dict):
        raise ClaimError(f"{name}: variables must be a mapping")
    for vname, spec in (raw.get("variables") or {}).items():
        if not isinstance(vname, str) or not NAME.fullmatch(vname.lower()) or vname in LEAN_KEYWORDS:
            raise ClaimError(f"{name}: bad variable name {vname!r}")
        if re.fullmatch(r"c\d+|(dom|h)_.*", vname):
            # dom_c1 names condition 1 and dom_x / h_x are generated binders; a variable must not collide
            raise ClaimError(f"{name}: variable name {vname!r} is reserved (c1, c2, ..., dom_*, h_*)")
        if not isinstance(spec, dict):
            raise ClaimError(f"{name}: variable {vname} must be a mapping with unit and domain")
        dim = si_dim(spec.get("unit", ""), f"{name}.variables.{vname}")
        variables.append(Variable(vname, dim, _domain(vname, spec.get("domain"), dim)))
    if not isinstance(raw.get("constants") or {}, dict):
        raise ClaimError(f"{name}: constants must be a mapping")
    constants = {k: parse_quantity(v) for k, v in (raw.get("constants") or {}).items()}
    env = {v.name: v.dim for v in variables}
    if set(env) & set(constants):
        raise ClaimError(f"{name}: names used as both variable and constant: {set(env) & set(constants)}")
    env |= {k: q.dim for k, q in constants.items()}

    assumptions = {}
    if not isinstance(raw.get("assumptions") or {}, dict):
        raise ClaimError(f"{name}: assumptions must be a mapping of registry name to argument list")
    for aname, args in (raw.get("assumptions") or {}).items():
        if args is not None and not isinstance(args, list):
            raise ClaimError(f"{name}: arguments of {aname} must be a list of variable names")
        if aname not in reg.assumptions:
            raise ClaimError(f"{name}: assumption {aname!r} is not in the registry")
        a = reg.assumptions[aname]
        args = list(args or [])
        if len(args) != len(a.args):
            raise ClaimError(f"{name}: {aname} takes {len(a.args)} arguments ({', '.join(a.args)}), got {len(args)}")
        for given, (formal, fdim) in zip(args, a.args.items()):
            if given not in {v.name for v in variables}:
                raise ClaimError(f"{name}: {aname} argument {given!r} is not a variable")
            if env[given] != fdim:
                raise DimensionError(f"{name}: {aname} expects {formal} with dimension {fdim}, got {given} with {env[given]}")
        assumptions[aname] = args

    def comparisons(key: str) -> list:
        out = []
        if not isinstance(raw.get(key) or [], list):
            raise ClaimError(f"{name}: {key} must be a list of comparisons")
        for text in raw.get(key) or []:
            node = E.parse(str(text))
            if not isinstance(node, E.Cmp):
                raise ClaimError(f"{name}: each entry of {key} must be one comparison")
            unknown = E.symbols(node) - set(env)
            if unknown:
                raise ClaimError(f"{name}: unknown symbols in {key}: {sorted(unknown)}")
            E.check_dims(node, env)
            out.append(node)
        return out

    conditions, goals, cylinder = comparisons("conditions"), comparisons("goals"), None
    if ctype in CYLINDER_TYPES:
        if variables or goals or assumptions or conditions:
            raise ClaimError(f"{name}: a cylinder claim takes only cylinder: {{r, h, R}}")
        cyl = raw.get("cylinder") or {}
        if not isinstance(cyl, dict) or not {"r", "h", "R"} <= set(cyl):
            raise ClaimError(f"{name}: cylinder needs r, h and R")
        qs = [parse_quantity(cyl[k]) for k in ("r", "h", "R")]
        length = si_dim("m", "cylinder")
        if any(q.dim != length for q in qs):
            raise DimensionError(f"{name}: cylinder r, h, R must be lengths")
        if qs[0].si_value < 0 or qs[1].si_value < 0:
            raise ClaimError(f"{name}: cylinder r and h must be non-negative")
        cylinder = tuple(q.si_value for q in qs)
    elif not goals:
        raise ClaimError(f"{name}: goals is required")
    if ctype == "point" and variables:
        raise ClaimError(f"{name}: a point claim has no variables; put the design values in constants")
    return Claim(name, ctype, raw["intent"], variables, conditions, assumptions, constants, goals, cylinder, path)


def premises(c: Claim) -> list[dict]:
    """The claim's own hypotheses, in statement order: variable domains, then conditions.

    kind: domain (positive), interval (a bounded domain), condition. The statement is the Lean text."""
    consts = {k: q.si_value for k, q in c.constants.items()}
    out = []
    for v in c.variables:
        if v.domain == "positive":
            out.append({"name": f"dom_{v.name}", "kind": "domain", "statement": f"0 < {v.name}"})
        elif isinstance(v.domain, tuple):
            lo, hi = v.domain
            out.append({"name": f"dom_{v.name}", "kind": "interval",
                        "statement": f"{v.name} ∈ Set.Icc {E.lean_number(lo)} {E.lean_number(hi)}"})
    for i, cond in enumerate(c.conditions, 1):
        out.append({"name": f"dom_c{i}", "kind": "condition", "statement": E.lean(cond, consts)})
    return out


def statement_block(c: Claim, reg: Registry) -> str:
    env = {v.name: v.dim for v in c.variables} | {k: q.dim for k, q in c.constants.items()}
    consts = {k: q.si_value for k, q in c.constants.items()}
    lines, seen = [], set()
    for node in [*c.conditions, *c.goals]:
        for ob in E.dim_obligations(node, env):
            if ob not in seen:
                seen.add(ob)
                lines.append(f"example : {ob[0]} = {ob[1]} := by decide")
    binders = []
    if c.variables:
        binders.append("(" + " ".join(v.name for v in c.variables) + " : ℝ)")
    binders += [f"({p['name']} : {p['statement']})" for p in premises(c)]
    for aname, args in c.assumptions.items():
        binders.append(f"(h_{aname} : " + " ".join([f"A_{aname}", *args]) + ")")
    if c.cylinder is not None:
        r, h, R = (E.lean_number(x) for x in c.cylinder)
        goal = f"ClaimCert.CylinderFitsInSphere {r} {h} {R}"
        if c.type == "not_fits_in_sphere":
            goal = f"¬ {goal}"
    elif len(c.goals) == 1:
        goal = E.lean(c.goals[0], consts)
    else:
        goal = " ∧ ".join(f"({E.lean(g, consts)})" for g in c.goals)
    lines.append(" ".join([f"theorem {c.name}", *binders]) + " :")
    lines.append(f"    {goal} := by")
    return "\n".join(lines)


def header(c: Claim, reg: Registry) -> str:
    return "\n".join([
        "import ClaimCert",
        f"import {reg.lean_module}",
        "",
        f"-- generated by claimcert from {c.name}.yaml; everything down to CC-END is checked",
        'set_option leancert.trust "kernel"',
        f"open {reg.lean_namespace}",
        "",
        BEGIN,
        statement_block(c, reg),
        END,
    ]) + "\n"


def render(c: Claim, reg: Registry, proof: str) -> str:
    return header(c, reg) + proof.rstrip("\n") + "\n\n" + f"#cc_report {c.name}\n"


def _old_proof(text: str, name: str) -> str | None:
    start = text.find(END + "\n")
    stop = text.rfind(f"#cc_report {name}")
    if start < 0 or stop < 0:
        return None
    return text[start + len(END) + 1: stop]


def write_new(claim_path, registry_path, proof_path=None, force: bool = False) -> Path:
    reg = load_registry(registry_path)
    claim = load_claim(claim_path, reg)
    out = lean_path(claim_path)
    proof = None
    if out.exists():
        if not force:
            raise FileExistsError(f"{out} exists; use --force")
        proof = _old_proof(out.read_text(encoding="utf-8"), claim.name)
    if proof_path:
        proof = Path(proof_path).read_text(encoding="utf-8")
    out.write_text(render(claim, reg, proof or "  sorry\n"), encoding="utf-8", newline="\n")
    return out
