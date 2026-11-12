"""Expectations: a value, a comparison and a tolerance, checked exactly.

The same text works as the arguments of the ASSERT command and as one item
of the ``check`` tool::

    VOL(flange), BETWEEN, 81500, 82200
    BBOX(flange).dz, EQ, 12, 0.01
    HOLES(flange, 8), EQ, 6
    VALID(flange)
    VOL(a) > VOL(b)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..lang.expr import ExprError, Record, Vec, fmt_num, format_value
from ..lang.script import COMPARE_WORDS, ScriptError, split_args

if TYPE_CHECKING:
    from ..commands.processor import Processor

OPS = tuple(COMPARE_WORDS) + ("BETWEEN",)
_PY_OPS = {ast.Eq: "EQ", ast.NotEq: "NE", ast.Lt: "LT", ast.Gt: "GT", ast.LtE: "LE", ast.GtE: "GE"}


class ExpectError(Exception):
    """The expectation itself is wrong (not the model): bad syntax, unknown name."""


@dataclass
class Outcome:
    text: str  # the expectation as written
    passed: bool
    actual: Any  # the value found
    expected: str  # what was wanted, in words: "EQ 12 (± 0.01)"
    expr: str = ""  # the value part alone: "VOL(flange)"

    def as_dict(self) -> dict[str, Any]:
        out = {"check": self.text, "pass": self.passed, "actual": _plain(self.actual)}
        if self.expected:
            out["expected"] = self.expected
        return out

    def sentence(self) -> str:
        what = self.expr or self.text
        got = format_value(self.actual) if not isinstance(self.actual, float) else fmt_num(round(self.actual, 6))
        if self.passed:
            return f"ok: {what} = {got}"
        return f"{what} is {got}, expected {self.expected}" if self.expected else f"{what} is false"


def _plain(v):
    if isinstance(v, Vec):
        return [round(c, 6) for c in v]
    if isinstance(v, Record):
        return repr(v)
    if isinstance(v, float):
        return round(v, 9)
    return v


def _number(p: "Processor", text: str, what: str) -> float:
    v = p.evaluate(text)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ExpectError(f"{what} must be a number, got {format_value(v)}")
    return float(v)


def check(p: "Processor", text: str) -> Outcome:
    """Check one expectation against the model. Raises ExpectError when it cannot be read."""
    try:
        parts = split_args(text)
    except ScriptError as exc:
        raise ExpectError(str(exc)) from None
    while parts and parts[-1] == "":
        parts.pop()
    if not parts or not parts[0]:
        raise ExpectError("give a value to check: ASSERT, VOL(b), EQ, 100 or ASSERT, VALID(b)")
    try:
        if len(parts) == 1:
            return _single(p, text.strip(), parts[0])
        op = parts[1].upper()
        if op not in OPS:
            raise ExpectError(f"unknown comparison {parts[1]!r}: use {', '.join(OPS)}")
        actual = p.evaluate(parts[0])
        out = _compare(p, text.strip(), actual, op, parts[2:])
        out.expr = parts[0]
        return out
    except ExprError as exc:
        raise ExpectError(str(exc)) from None


def _single(p: "Processor", text: str, expr: str) -> Outcome:
    """``VALID(b)`` (true or false) or ``VOL(a) > 100`` (one comparison)."""
    try:
        tree = ast.parse(expr.strip(), mode="eval").body
    except SyntaxError:
        tree = None
    if isinstance(tree, ast.Compare) and len(tree.ops) == 1 and type(tree.ops[0]) in _PY_OPS:
        left = ast.get_source_segment(expr.strip(), tree.left)
        right = ast.get_source_segment(expr.strip(), tree.comparators[0])
        if left and right:
            actual = p.evaluate(left)
            out = _compare(p, text, actual, _PY_OPS[type(tree.ops[0])], [right])
            out.expr = left
            return out
    v = p.evaluate(expr)
    if isinstance(v, (Vec, Record)) or isinstance(v, str):
        raise ExpectError(f"{expr} gives {format_value(v)}; compare it: {expr}, EQ, value")
    return Outcome(text, bool(v), v, "", expr)


def _compare(p: "Processor", text: str, actual, op: str, rest: list[str]) -> Outcome:
    if isinstance(actual, bool) or not isinstance(actual, (int, float)):
        raise ExpectError(f"the value to check is {format_value(actual)}, not a number "
                          "(pick one part, e.g. BBOX(b).dz or CENT(b).x)")
    tol_model = p.model.tolerance
    if op == "BETWEEN":
        if len(rest) < 2:
            raise ExpectError("BETWEEN needs a low and a high value")
        lo, hi = _number(p, rest[0], "the low value"), _number(p, rest[1], "the high value")
        lo, hi = min(lo, hi), max(lo, hi)
        eps = 1e-9 * max(1.0, abs(lo), abs(hi)) + tol_model
        return Outcome(text, lo - eps <= actual <= hi + eps, actual, f"BETWEEN {fmt_num(lo)} and {fmt_num(hi)}")
    if not rest or rest[0] == "":
        raise ExpectError(f"{op} needs a value to compare with")
    ref = _number(p, rest[0], "the value to compare with")
    if len(rest) > 1 and rest[1] != "":
        tol = abs(_number(p, rest[1], "the tolerance"))
        shown = f" (± {fmt_num(tol)})"
    else:
        tol = 1e-6 * max(1.0, abs(ref)) + tol_model
        shown = ""
    if len(rest) > 2:
        raise ExpectError("too many values: value, op, reference [, tolerance]")
    passed = {
        "EQ": abs(actual - ref) <= tol,
        "NE": abs(actual - ref) > tol,
        "LT": actual < ref - tol if shown else actual < ref,
        "GT": actual > ref + tol if shown else actual > ref,
        "LE": actual <= ref + tol,
        "GE": actual >= ref - tol,
    }[op]
    return Outcome(text, passed, actual, f"{op} {fmt_num(ref)}{shown}")
