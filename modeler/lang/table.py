"""Law tables: a law given as values at stations, joined smoothly.

``TABLE(t, t0, v0, t1, v1, ...)`` is an ordinary function, so a table can
stand anywhere a law can: ``SWEEP, foil, span, TABLE(t, 0, 40, 0.6, 20, 1, 8)``.
The values are joined by a monotone cubic (PCHIP): smooth, through every
station, and never overshooting between two stations (a twist that goes
40, 20, 8 never goes below 8 or above 40). Before the first station and
after the last one the end values hold.

This is what the sweep editor's handles edit: each handle is one station.
"""

from __future__ import annotations

import ast
import math

Station = tuple[float, float]


class TableError(ValueError):
    pass


def check(stations: list[Station]) -> list[Station]:
    if len(stations) < 1:
        raise TableError("a table needs at least one station")
    for (a, _), (b, _) in zip(stations, stations[1:]):
        if not b > a:
            raise TableError("the stations must be in order of t, each after the one before")
    return stations


def _slopes(xs: list[float], ys: list[float]) -> list[float]:
    """Fritsch-Carlson slopes for a monotone cubic through (xs, ys)."""
    n = len(xs)
    h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    if n == 2:
        return [d[0], d[0]]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])

    def end(h0, h1, d0, d1):
        s = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
        if s * d0 <= 0:
            return 0.0
        if d0 * d1 <= 0 and abs(s) > abs(3 * d0):
            return 3 * d0
        return s

    m[0] = end(h[0], h[1], d[0], d[1])
    m[-1] = end(h[-1], h[-2], d[-1], d[-2])
    return m


def value(stations: list[Station], t: float) -> float:
    xs = [s[0] for s in stations]
    ys = [s[1] for s in stations]
    if len(xs) == 1 or t <= xs[0]:
        return ys[0]
    if t >= xs[-1]:
        return ys[-1]
    k = max(i for i in range(len(xs) - 1) if xs[i] <= t)
    m = _slopes(xs, ys)
    h = xs[k + 1] - xs[k]
    s = (t - xs[k]) / h
    h00, h10, h01, h11 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, -2 * s**3 + 3 * s**2, s**3 - s**2
    return h00 * ys[k] + h10 * h * m[k] + h01 * ys[k + 1] + h11 * h * m[k + 1]


def function(*args):
    """The TABLE(t, t0, v0, t1, v1, ...) function of the command language."""
    from .expr import ExprError, _is_num

    if len(args) < 3 or len(args) % 2 == 0:
        raise ExprError("TABLE(t, t0, v0, t1, v1, ...) needs t and then pairs of station and value")
    for a in args:
        if not _is_num(a):
            raise ExprError("TABLE() needs numbers")
    st = [(float(args[i]), float(args[i + 1])) for i in range(1, len(args), 2)]
    try:
        check(st)
    except TableError as exc:
        raise ExprError(f"TABLE(): {exc}") from None
    return value(st, float(args[0]))


def _num_text(v: float) -> str:
    v = round(v, 6)
    if v == int(v):
        return str(int(v))
    return f"{v:.6g}"


def text(stations: list[Station], var: str = "t") -> str:
    """Law text for stations: TABLE(t, 0, 40, 1, 8)."""
    check(stations)
    return f"TABLE({var}, " + ", ".join(f"{_num_text(a)}, {_num_text(b)}" for a, b in stations) + ")"


def parse(law: str) -> list[Station] | None:
    """The stations of a law written as TABLE(t, ...) with plain numbers, else None."""
    src = law.strip()
    if len(src) >= 2 and src[0] == src[-1] and src[0] in "\"'":
        src = src[1:-1].strip()
    try:
        node = ast.parse(src, mode="eval").body
    except SyntaxError:
        return None
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.upper() == "TABLE"):
        return None
    args = node.args
    if len(args) < 3 or len(args) % 2 == 0 or not (isinstance(args[0], ast.Name) and args[0].id.upper() == "T"):
        return None
    nums = []
    for a in args[1:]:
        try:
            v = ast.literal_eval(a)
        except ValueError:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        nums.append(float(v))
    st = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
    try:
        return check(st)
    except TableError:
        return None
