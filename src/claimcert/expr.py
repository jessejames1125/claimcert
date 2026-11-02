"""A small expression language for claims and assumptions.

Python expression syntax restricted to numbers, names, + - * /, integer powers, unary minus,
log/exp/sqrt/sin/cos (sin and cos take an angle in radians, which is dimensionless), and at most one comparison (<, <=, >, >=, ==) at the top level."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from .units import ONE, Dim, DimensionError


class ExprError(ValueError):
    pass


@dataclass(frozen=True)
class Num:
    value: Fraction


@dataclass(frozen=True)
class Sym:
    name: str


@dataclass(frozen=True)
class Bin:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class Pow:
    base: object
    k: int


@dataclass(frozen=True)
class Neg:
    arg: object


@dataclass(frozen=True)
class Call:
    fn: str
    arg: object


@dataclass(frozen=True)
class Cmp:
    op: str
    left: object
    right: object


FUNCS = {"log": "Real.log", "exp": "Real.exp", "sqrt": "Real.sqrt", "sin": "Real.sin", "cos": "Real.cos"}
_BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_CMPOPS = {ast.Lt: "<", ast.LtE: "≤", ast.Gt: ">", ast.GtE: "≥", ast.Eq: "="}
DIM_ONE = "ClaimCert.Dim.one"


def parse(text: str):
    src = str(text).strip()
    try:
        tree = ast.parse(src, mode="eval").body
    except SyntaxError as e:
        raise ExprError(f"cannot parse {src!r}: {e.msg}") from e
    if isinstance(tree, ast.Compare):
        if len(tree.ops) != 1 or type(tree.ops[0]) not in _CMPOPS:
            raise ExprError(f"{src!r}: exactly one comparison (<, <=, >, >=, ==) is allowed")
        return Cmp(_CMPOPS[type(tree.ops[0])], _conv(tree.left, src), _conv(tree.comparators[0], src))
    return _conv(tree, src)


def _int_exponent(node, src: str) -> int:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_int_exponent(node.operand, src)
    raise ExprError(f"{src!r}: exponents must be integer literals")


def _conv(node, src: str):
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        segment = ast.get_source_segment(src, node)
        try:
            return Num(Fraction(Decimal(segment)))
        except (InvalidOperation, TypeError, ValueError) as e:
            raise ExprError(f"{src!r}: bad number {segment!r}") from e
    if isinstance(node, ast.Name):
        return Sym(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return Neg(_conv(node.operand, src))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
        return Pow(_conv(node.left, src), _int_exponent(node.right, src))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return Bin(_BINOPS[type(node.op)], _conv(node.left, src), _conv(node.right, src))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCS:
        if len(node.args) != 1 or node.keywords:
            raise ExprError(f"{src!r}: {node.func.id} takes exactly one argument")
        return Call(node.func.id, _conv(node.args[0], src))
    raise ExprError(f"{src!r}: unsupported syntax ({type(node).__name__})")


def symbols(node) -> set[str]:
    match node:
        case Sym(name):
            return {name}
        case Num():
            return set()
        case Neg(arg) | Call(_, arg) | Pow(arg, _):
            return symbols(arg)
        case Bin(_, left, right) | Cmp(_, left, right):
            return symbols(left) | symbols(right)
    raise ExprError(f"unknown node {node!r}")


def check_dims(node, env: dict[str, Dim]) -> Dim:
    """Dimension of node; raises DimensionError on any inconsistency, ExprError on unknown names."""
    match node:
        case Num():
            return ONE
        case Sym(name):
            if name not in env:
                raise ExprError(f"unknown symbol {name!r}")
            return env[name]
        case Neg(arg):
            return check_dims(arg, env)
        case Bin(op, left, right):
            a, b = check_dims(left, env), check_dims(right, env)
            if op in "+-":
                if a != b:
                    raise DimensionError(f"cannot {'add' if op == '+' else 'subtract'} {a} and {b}")
                return a
            return a * b if op == "*" else a / b
        case Pow(base, k):
            return check_dims(base, env) ** k
        case Call("sqrt", arg):
            return check_dims(arg, env).root(2)
        case Call(fn, arg):
            d = check_dims(arg, env)
            if not d.is_dimensionless:
                raise DimensionError(f"{fn} needs a dimensionless argument, got {d}")
            return ONE
        case Cmp(_, left, right):
            a, b = check_dims(left, env), check_dims(right, env)
            if a != b:
                raise DimensionError(f"cannot compare {a} with {b}")
            return ONE
    raise ExprError(f"unknown node {node!r}")


def lean_number(q: Fraction) -> str:
    if q.denominator == 1:
        return f"({q.numerator} : ℝ)"
    return f"({q.numerator} / {q.denominator} : ℝ)"


def lean(node, consts: dict[str, Fraction]) -> str:
    match node:
        case Num(value):
            return lean_number(value)
        case Sym(name):
            return lean_number(consts[name]) if name in consts else name
        case Neg(arg):
            return f"(-{lean(arg, consts)})"
        case Bin(op, left, right):
            return f"({lean(left, consts)} {op} {lean(right, consts)})"
        case Pow(base, k):
            exponent = str(k) if k >= 0 else f"({k} : ℤ)"
            return f"({lean(base, consts)} ^ {exponent})"
        case Call(fn, arg):
            return f"({FUNCS[fn]} {lean(arg, consts)})"
        case Cmp(op, left, right):
            return f"{lean(left, consts)} {op} {lean(right, consts)}"
    raise ExprError(f"cannot emit {node!r}")


def lean_dim_literal(d: Dim) -> str:
    parts = " ".join(f"({e})" if e < 0 else str(e) for e in d.exps)
    return f"(ClaimCert.Dim.mk {parts})"


def _lean_dim(node, env: dict[str, Dim]) -> str:
    match node:
        case Num():
            return DIM_ONE
        case Sym(name):
            return lean_dim_literal(env[name])
        case Neg(arg):
            return _lean_dim(arg, env)
        case Bin("+" | "-", left, _):
            return _lean_dim(left, env)
        case Bin(op, left, right):
            fn = "mul" if op == "*" else "div"
            return f"(ClaimCert.Dim.{fn} {_lean_dim(left, env)} {_lean_dim(right, env)})"
        case Pow(base, k):
            return f"(ClaimCert.Dim.pow {_lean_dim(base, env)} ({k}))"
        case Call("sqrt", _):
            return lean_dim_literal(check_dims(node, env))
        case Call():
            return DIM_ONE
    raise ExprError(f"no dimension for {node!r}")


def dim_obligations(node, env: dict[str, Dim]) -> list[tuple[str, str]]:
    """Equalities of Lean Dim terms that must hold; Lean re-checks them with `decide`."""
    out: list[tuple[str, str]] = []
    match node:
        case Num() | Sym():
            pass
        case Neg(arg) | Pow(arg, _):
            out += dim_obligations(arg, env)
        case Bin(op, left, right):
            out += dim_obligations(left, env) + dim_obligations(right, env)
            if op in "+-":
                out.append((_lean_dim(left, env), _lean_dim(right, env)))
        case Call("sqrt", arg):
            out += dim_obligations(arg, env)
            half = lean_dim_literal(check_dims(node, env))
            out.append((f"(ClaimCert.Dim.pow {half} (2))", _lean_dim(arg, env)))
        case Call(_, arg):
            out += dim_obligations(arg, env)
            out.append((_lean_dim(arg, env), DIM_ONE))
        case Cmp(_, left, right):
            out += dim_obligations(left, env) + dim_obligations(right, env)
            out.append((_lean_dim(left, env), _lean_dim(right, env)))
    return out
