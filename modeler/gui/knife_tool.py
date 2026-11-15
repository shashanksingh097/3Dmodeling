"""The Knife tool in the 3D view (M6c): draw a stroke across a body, and it
is cut along the view direction.

The stroke is recorded in screen pixels, thinned to the points that matter,
laid on a plane across the view through the body's middle, and sent as two
plain commands: a SPLINE (or LINE) for the stroke and KNIFE with the view
direction. So a knife cut is in the history like anything typed, and its
stroke can be edited there.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import Callable

from ..lang.expr import fmt_num
from .sketch_tools import simplify_stroke

MIN_PIXELS = 12  # a shorter stroke is taken as a slip
CLOSE_PIXELS = 14  # ending this near the start closes the stroke (a cookie cutter)
MAX_POINTS = 40


def _n(v: float) -> str:
    return fmt_num(round(v, 4) + 0.0)


def _pt(p) -> str:
    return f"({_n(p[0])}, {_n(p[1])}, {_n(p[2])})"


def target_body(pixels, body_at: Callable[[int, int], int | None], selected: int | None) -> int | None:
    """The body to cut: the one picked, else the one the stroke crosses most."""
    if selected:
        return selected
    hits = Counter()
    step = max(1, len(pixels) // 60)
    for x, y in pixels[::step]:
        b = body_at(int(x), int(y))
        if b:
            hits[b] += 1
    return hits.most_common(1)[0][0] if hits else None


def knife_commands(pixels, ray: Callable[[int, int], tuple], centre, body: int, width: float = 0.0) -> list[str]:
    """The commands for a stroke drawn over ``body``.

    ``ray(x, y)`` gives (point, direction) of the line of sight through a
    pixel; ``centre`` is the middle of the body: the stroke is laid on the
    plane through it, across the view."""
    pts = [pixels[0]]
    for q in pixels[1:]:
        if q != pts[-1]:
            pts.append(q)
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if length < MIN_PIXELS:
        return []
    closed = len(pts) > 6 and math.dist(pts[0], pts[-1]) <= CLOSE_PIXELS and length > 6 * CLOSE_PIXELS
    if closed:
        pts = pts[:-1] + [pts[0]]
    eps = 2.0
    simple = simplify_stroke(pts, eps)
    while len(simple) > MAX_POINTS:
        eps *= 1.5
        simple = simplify_stroke(pts, eps)
    if closed:
        simple = simple[:-1]
        if len(simple) < 3:
            return []
    _, d = ray(*simple[0])
    dn = math.sqrt(sum(c * c for c in d)) or 1.0
    d = tuple(c / dn for c in d)
    world = []
    for x, y in simple:
        o, v = ray(x, y)
        den = sum(v[i] * d[i] for i in range(3))
        t = sum((centre[i] - o[i]) * d[i] for i in range(3)) / den if abs(den) > 1e-12 else 0.0
        world.append(tuple(o[i] + t * v[i] for i in range(3)))
    if closed:
        stroke = "SPLINE, " + ", ".join(_pt(q) for q in world) + ", CLOSE"
    elif len(world) == 2:
        a, b = world
        stroke = f"LINE, {_n(a[0])}, {_n(a[1])}, {_n(a[2])}, {_n(b[0])}, {_n(b[1])}, {_n(b[2])}"
    else:
        stroke = "SPLINE, " + ", ".join(_pt(q) for q in world)
    return [stroke, f"KNIFE, {body}, LAST, {_n(width)}, {_n(d[0])}, {_n(d[1])}, {_n(d[2])}"]
