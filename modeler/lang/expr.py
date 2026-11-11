"""Safe expression evaluation for the command language.

Expressions are parsed with Python's ``ast`` module and walked by a small
evaluator that only knows numbers, strings, points/vectors, a fixed set of
math functions and the model queries the processor registers. Nothing is
passed to ``eval``, so a script cannot reach Python itself.

Names are case-insensitive: ``W``, ``w`` and ``sin``/``SIN`` are the same.
"""

from __future__ import annotations

import ast
import math
from typing import Any, Callable, Mapping


class ExprError(Exception):
    """A bad expression: syntax, unknown name, wrong type, division by zero."""


class Vec(tuple):
    """An immutable point or vector, written ``(x, y, z)`` in scripts.

    Supports ``+``/``-`` with another vector of the same size, ``*``/``/`` by
    a number, ``.x .y .z`` and indexing (``P[0]``).
    """

    def __new__(cls, items):
        return super().__new__(cls, (float(v) for v in items))

    def _same(self, other):
        if not isinstance(other, Vec) or len(other) != len(self):
            raise ExprError(f"cannot combine a {len(self)}-vector with {_kind(other)}")
        return other

    def __add__(self, other):
        return Vec(a + b for a, b in zip(self, self._same(other)))

    def __sub__(self, other):
        return Vec(a - b for a, b in zip(self, self._same(other)))

    def __mul__(self, k):
        if not _is_num(k):
            raise ExprError("a vector can only be multiplied by a number")
        return Vec(a * k for a in self)

    __rmul__ = __mul__

    def __truediv__(self, k):
        if not _is_num(k):
            raise ExprError("a vector can only be divided by a number")
        if k == 0:
            raise ExprError("division by zero")
        return Vec(a / k for a in self)

    def __neg__(self):
        return Vec(-a for a in self)

    def _axis(self, i: int) -> float:
        if i >= len(self):
            raise ExprError(f"a {len(self)}-vector has no component {'xyz'[i]}")
        return self[i]

    @property
    def x(self):
        return self._axis(0)

    @property
    def y(self):
        return self._axis(1)

    @property
    def z(self):
        return self._axis(2)

    def __repr__(self) -> str:
        return "(" + ", ".join(fmt_num(v) for v in self) + ")"


class Record:
    """A read-only result with named fields, e.g. ``BBOX(1).zmax``."""

    def __init__(self, kind: str, **fields: float) -> None:
        self._kind = kind
        self._fields = {k.lower(): v for k, v in fields.items()}

    def get(self, name: str):
        try:
            return self._fields[name.lower()]
        except KeyError:
            raise ExprError(f"{self._kind} has no field {name!r} (has {', '.join(self._fields)})") from None

    def __repr__(self) -> str:
        return f"{self._kind}(" + ", ".join(f"{k}={format_value(v)}" for k, v in self._fields.items()) + ")"


def _is_num(v) -> bool:
    return isinstance(v, (int, float))


def _kind(v) -> str:
    if isinstance(v, Vec):
        return f"a {len(v)}-vector"
    if isinstance(v, str):
        return "a string"
    if isinstance(v, Record):
        return v._kind
    return "a number"


def fmt_num(v: float) -> str:
    """Short, exact-enough text for a number: 3 not 3.0, 0.1 not 0.1000000001."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if math.isfinite(v) and v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return f"{v:.10g}"


def format_value(v: Any) -> str:
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    if isinstance(v, (int, float)):
        return fmt_num(v)
    return repr(v)


# ---- functions and constants -------------------------------------------------

def _num(name: str, fn: Callable[..., float], nargs: tuple[int, ...]):
    def wrapper(*args):
        if len(args) not in nargs:
            want = " or ".join(map(str, nargs))
            raise ExprError(f"{name}() takes {want} argument(s), got {len(args)}")
        for a in args:
            if not _is_num(a):
                raise ExprError(f"{name}() needs numbers, got {_kind(a)}")
        try:
            return fn(*args)
        except (ValueError, OverflowError, ZeroDivisionError) as exc:
            raise ExprError(f"{name}(): {exc}") from None

    return wrapper


def _minmax(name, fn):
    def wrapper(*args):
        if len(args) == 1 and isinstance(args[0], Vec):
            args = tuple(args[0])
        if not args:
            raise ExprError(f"{name}() needs at least one number")
        for a in args:
            if not _is_num(a):
                raise ExprError(f"{name}() needs numbers, got {_kind(a)}")
        return fn(args)

    return wrapper


def _str(v=None, digits=None):
    if v is None:
        raise ExprError("str() needs a value")
    if digits is not None and _is_num(v):
        return f"{v:.{int(digits)}f}"
    return v if isinstance(v, str) else format_value(v)


def _vec(*args):
    if len(args) not in (2, 3):
        raise ExprError("VEC() takes 2 or 3 numbers")
    return Vec(args)


def _length(v):
    if not isinstance(v, Vec):
        raise ExprError("NORM() needs a vector")
    return math.sqrt(sum(a * a for a in v))


def _dist(a, b):
    if not isinstance(a, Vec):
        raise ExprError("DISTANCE() needs two points")
    return _length(a - b)


FUNCTIONS: dict[str, Callable] = {
    "SIN": _num("sin", lambda a: math.sin(math.radians(a)), (1,)),
    "COS": _num("cos", lambda a: math.cos(math.radians(a)), (1,)),
    "TAN": _num("tan", lambda a: math.tan(math.radians(a)), (1,)),
    "ASIN": _num("asin", lambda a: math.degrees(math.asin(a)), (1,)),
    "ACOS": _num("acos", lambda a: math.degrees(math.acos(a)), (1,)),
    "ATAN": _num("atan", lambda a: math.degrees(math.atan(a)), (1,)),
    "ATAN2": _num("atan2", lambda y, x: math.degrees(math.atan2(y, x)), (2,)),
    "SQRT": _num("sqrt", math.sqrt, (1,)),
    "EXP": _num("exp", math.exp, (1,)),
    "LOG": _num("log", lambda a, b=math.e: math.log(a, b), (1, 2)),
    "LOG10": _num("log10", math.log10, (1,)),
    "ABS": _num("abs", abs, (1,)),
    "FLOOR": _num("floor", math.floor, (1,)),
    "CEIL": _num("ceil", math.ceil, (1,)),
    "ROUND": _num("round", lambda a, n=0: round(a, int(n)) if n else round(a), (1, 2)),
    "INT": _num("int", int, (1,)),
    "SIGN": _num("sign", lambda a: (a > 0) - (a < 0), (1,)),
    "RAD": _num("rad", math.radians, (1,)),
    "DEG": _num("deg", math.degrees, (1,)),
    "HYPOT": _num("hypot", math.hypot, (2, 3)),
    "MIN": _minmax("min", min),
    "MAX": _minmax("max", max),
    "STR": _str,
    "VEC": _vec,
    "NORM": _length,
    "DISTANCE": _dist,
}

CONSTANTS: dict[str, float] = {"PI": math.pi, "E": math.e, "TRUE": 1, "FALSE": 0}

_BINOPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: a**b,
}
_CMPOPS = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
}


class Evaluator:
    """Evaluates expression text.

    ``lookup(NAME)`` returns a parameter's value or raises KeyError.
    ``functions`` are extra callables (model queries), keyed by upper-case name.
    """

    def __init__(
        self,
        lookup: Callable[[str], Any],
        functions: Mapping[str, Callable] | None = None,
        constants: Mapping[str, Any] | None = None,
    ) -> None:
        self.lookup = lookup
        self.functions = {**FUNCTIONS, **(functions or {})}
        self.constants = {**CONSTANTS, **(constants or {})}

    def eval(self, text: str) -> Any:
        src = text.strip()
        if not src:
            raise ExprError("empty expression")
        if "^" in src.replace('"', "").replace("'", ""):
            raise ExprError("use ** for powers (2**3), not ^")
        try:
            tree = ast.parse(src, mode="eval")
        except SyntaxError as exc:
            raise ExprError(f"cannot read {src!r}: {exc.msg}") from None
        return self._node(tree.body)

    def is_name(self, name: str) -> bool:
        n = name.upper()
        return n in self.constants or n in self.functions

    # ---- tree walk ---------------------------------------------------------
    def _node(self, n: ast.AST) -> Any:
        method = getattr(self, "_" + type(n).__name__, None)
        if method is None:
            raise ExprError(f"{type(n).__name__} is not allowed in expressions")
        return method(n)

    def _Constant(self, n: ast.Constant):
        if isinstance(n.value, (int, float, str)) and not isinstance(n.value, complex):
            return n.value
        raise ExprError(f"unsupported value {n.value!r}")

    def _Name(self, n: ast.Name):
        key = n.id.upper()
        try:
            return self.lookup(key)
        except KeyError:
            pass
        if key in self.constants:
            return self.constants[key]
        if key in self.functions:
            raise ExprError(f"{key} is a function: write {key}(...)")
        raise ExprError(f"unknown name {n.id!r}")

    def _Tuple(self, n: ast.Tuple):
        vals = [self._node(e) for e in n.elts]
        if not 2 <= len(vals) <= 3 or not all(_is_num(v) for v in vals):
            raise ExprError("a point is 2 or 3 numbers in parentheses, e.g. (10, 0, 5)")
        return Vec(vals)

    def _UnaryOp(self, n: ast.UnaryOp):
        v = self._node(n.operand)
        if isinstance(n.op, ast.Not):
            return int(not v)
        if isinstance(n.op, ast.USub):
            if isinstance(v, Vec) or _is_num(v):
                return -v
        elif isinstance(n.op, ast.UAdd):
            if isinstance(v, Vec) or _is_num(v):
                return v
        raise ExprError(f"cannot negate {_kind(v)}")

    def _BinOp(self, n: ast.BinOp):
        a, b = self._node(n.left), self._node(n.right)
        fn = _BINOPS.get(type(n.op))
        if fn is None:
            raise ExprError("unsupported operator")
        if isinstance(a, str) or isinstance(b, str):
            if isinstance(n.op, ast.Add) and isinstance(a, str) and isinstance(b, str):
                return a + b
            raise ExprError("strings can only be joined with +, e.g. \"part\" + STR(i)")
        if isinstance(a, Record) or isinstance(b, Record):
            raise ExprError(f"use a field of {_kind(a if isinstance(a, Record) else b)}, e.g. .x")
        if isinstance(n.op, ast.Pow) and _is_num(b) and abs(b) > 1000:
            raise ExprError("exponent too large")
        if (isinstance(a, Vec) or isinstance(b, Vec)) and not isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            raise ExprError("vectors support + - * / only")
        try:
            return fn(a, b)
        except ZeroDivisionError:
            raise ExprError("division by zero") from None
        except OverflowError:
            raise ExprError("number too large") from None

    def _BoolOp(self, n: ast.BoolOp):
        if isinstance(n.op, ast.And):
            for e in n.values:
                if not self._node(e):
                    return 0
            return 1
        for e in n.values:
            if self._node(e):
                return 1
        return 0

    def _Compare(self, n: ast.Compare):
        left = self._node(n.left)
        for op, right_node in zip(n.ops, n.comparators):
            right = self._node(right_node)
            fn = _CMPOPS.get(type(op))
            if fn is None:
                raise ExprError("unsupported comparison")
            if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) and not (_is_num(left) and _is_num(right)):
                raise ExprError("only numbers can be ordered with < > <= >=")
            if not fn(left, right):
                return 0
            left = right
        return 1

    def _IfExp(self, n: ast.IfExp):
        return self._node(n.body) if self._node(n.test) else self._node(n.orelse)

    def _Call(self, n: ast.Call):
        if not isinstance(n.func, ast.Name):
            raise ExprError("only named functions can be called, e.g. SQRT(2)")
        if n.keywords:
            raise ExprError("functions take positional arguments only")
        key = n.func.id.upper()
        fn = self.functions.get(key)
        if fn is None:
            raise ExprError(f"unknown function {n.func.id!r}")
        args = [self._node(a) for a in n.args]
        return fn(*args)

    def _Attribute(self, n: ast.Attribute):
        v = self._node(n.value)
        attr = n.attr.lower()
        if isinstance(v, Vec) and attr in ("x", "y", "z"):
            return getattr(v, attr)
        if isinstance(v, Record):
            return v.get(attr)
        raise ExprError(f"{_kind(v)} has no field {n.attr!r}")

    def _Subscript(self, n: ast.Subscript):
        v = self._node(n.value)
        i = self._node(n.slice)
        if not isinstance(v, Vec):
            raise ExprError(f"cannot index {_kind(v)}")
        if not _is_num(i) or int(i) != i:
            raise ExprError("index must be a whole number")
        try:
            return v[int(i)]
        except IndexError:
            raise ExprError(f"index {int(i)} out of range for a {len(v)}-vector") from None
