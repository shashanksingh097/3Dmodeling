"""Typed values while sketching (PLAN item 87), without Qt.

While a line, rectangle, circle, arc, slot or polygon is being drawn, boxes
next to the cursor show its sizes as the mouse moves: a line's length and
angle, a rectangle's width and height, a circle's radius. Typing a number
fixes the first box (Tab goes on to the next one), and the shape then follows
the mouse only in what is not fixed. Enter (or a click) places it, and each
fixed value becomes a size on the sketch (an ordinary SDIM step) as if it had
been added by hand. A typed value can be any expression, so a parameter name
(``W``) keeps the size tied to the parameter.

``SketchController`` (gui/sketch_tools.py) holds one ``Typed`` and asks it:
``fields`` (the boxes now, with their live values), ``constrain`` (where the
fixed values put the next click) and ``sizes`` (the SDIM lines once the
geometry is made).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..lang.expr import fmt_num

# tool -> stage (clicks so far) -> boxes, as (key, label)
_LA = (("L", "length"), ("A", "angle"))
FIELDS: dict[str, dict[int, tuple[tuple[str, str], ...]]] = {
    "LINE": {1: _LA},
    "CENTRELINE": {1: _LA},
    "RECT": {1: (("W", "width"), ("H", "height"))},
    "CRECT": {1: (("W", "width"), ("H", "height"))},
    "CIRCLE": {1: (("R", "radius"),)},
    "POLYGON": {1: (("R", "radius"), ("A", "angle"))},
    "ARC": {1: _LA, 2: (("R", "radius"),)},
    "SLOT": {1: _LA, 2: (("R", "radius"),)},
}
TOOLS = tuple(FIELDS)
SNAP_ANGLE = 3.0  # as sketch_tools: a line this close to level or upright gets H or V instead of an angle


class TypedError(ValueError):
    pass


@dataclass
class Field:
    key: str
    label: str
    value: float  # what the shape has now (the fixed value, or what the mouse gives)
    fixed: bool = False
    text: str = ""  # what was typed (an expression), when fixed
    unit: str = ""
    editing: bool = False  # the box being typed into
    buffer: str = ""  # its text while typing

    def shown(self) -> str:
        if self.editing:
            return self.buffer
        return self.text if self.fixed else fmt_num(round(self.value, 3) + 0.0)


def _unit(v) -> tuple[float, float]:
    n = math.hypot(v[0], v[1])
    return (v[0] / n, v[1] / n) if n > 1e-12 else (1.0, 0.0)


def _square(u: tuple[float, float]) -> tuple[float, float]:
    ang = math.degrees(math.atan2(u[1], u[0])) % 360
    for k in (0, 90, 180, 270, 360):
        if abs(ang - k) <= SNAP_ANGLE:
            r = math.radians(k)
            return (round(math.cos(r)), round(math.sin(r)))
    return u


def _sign(x: float) -> float:
    return -1.0 if x < 0 else 1.0


def is_number(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


@dataclass
class Typed:
    evaluate: object = None  # text -> number (the processor's evaluate), set by the controller
    values: dict[str, tuple[str, float]] = field(default_factory=dict)  # key -> (text, value) for this stage
    done: list[tuple[str, str, float]] = field(default_factory=list)  # earlier stages: (key, text, value)
    focus: int = -1  # which box is being typed into (-1: none)
    buffer: str = ""

    # ---- state ----------------------------------------------------------------------
    def clear(self) -> None:
        self.values = {}
        self.done = []
        self.focus = -1
        self.buffer = ""

    def next_stage(self) -> None:
        """A click placed a point: what was fixed now waits for the geometry."""
        self.done += [(k, t, v) for k, (t, v) in self.values.items()]
        self.values = {}
        self.focus = -1
        self.buffer = ""

    @property
    def active(self) -> bool:
        return bool(self.values) or self.focus >= 0

    def keys(self, tool: str, stage: int) -> tuple[tuple[str, str], ...]:
        return FIELDS.get(tool, {}).get(stage, ())

    # ---- typing ----------------------------------------------------------------------
    def type_key(self, tool: str, stage: int, text: str) -> bool:
        """A key typed in the view while drawing. Digits, '.', '-' and letters
        (a parameter name) and + - * / ( ) build the value; Backspace takes one off.
        True when it was used."""
        boxes = self.keys(tool, stage)
        if not boxes:
            return False
        if text == "\b":
            if self.focus < 0:
                return False
            self.buffer = self.buffer[:-1]
            return True
        if not text or len(text) != 1:
            return False
        if self.focus < 0:
            if not (text.isdigit() or text in ".-"):
                return False  # letters alone are shortcuts; a value starts with a digit
            self.focus = self._first_open(boxes)
            self.buffer = ""
        if text.isalnum() or text in ".-+*/()_^ ":
            self.buffer += text
            return True
        return False

    def _first_open(self, boxes) -> int:
        for i, (k, _) in enumerate(boxes):
            if k not in self.values:
                return i
        return 0

    def commit(self, tool: str, stage: int) -> bool:
        """Fix the box being typed into (Tab, Enter). False when nothing was typed."""
        boxes = self.keys(tool, stage)
        if self.focus < 0 or not boxes:
            return False
        text = self.buffer.strip()
        key = boxes[self.focus][0]
        self.focus, self.buffer = -1, ""
        if not text:
            return False
        self.fix(key, text, tool)
        return True

    def fix(self, key: str, text: str, tool: str = "") -> float:
        try:
            v = float(self.evaluate(text)) if self.evaluate is not None else float(text)
        except Exception as exc:  # noqa: BLE001 - a bad expression: say so, keep the old value
            raise TypedError(f"{text}: {exc}") from None
        if key in ("L", "W", "H", "R") and v <= 0:
            raise TypedError(f"the {dict(_names()).get(key, key)} must be more than 0")
        self.values[key] = (text, v)
        return v

    def tab(self, tool: str, stage: int) -> None:
        """Tab: fix what is typed and go on to the next box (round to the first)."""
        boxes = self.keys(tool, stage)
        if not boxes:
            return
        at = self.focus
        self.commit(tool, stage)
        nxt = ((at if at >= 0 else -1) + 1) % len(boxes)
        self.focus = nxt
        self.buffer = ""

    def unfix(self, key: str) -> None:
        self.values.pop(key, None)

    def value(self, key: str) -> float | None:
        got = self.values.get(key)
        return got[1] if got else None

    # ---- geometry --------------------------------------------------------------------
    def constrain(self, tool: str, pts: list, at: tuple[float, float]) -> tuple[float, float]:
        """Where the fixed values put the next point, the mouse being at ``at``."""
        stage = len(pts)
        if not self.values or not self.keys(tool, stage):
            return at
        L, A, W, H, R = (self.value(k) for k in "LAWHR")
        if tool in ("LINE", "CENTRELINE", "ARC", "SLOT", "POLYGON") and stage == 1:
            a = pts[0]
            d = (at[0] - a[0], at[1] - a[1])
            ln = R if tool == "POLYGON" else L
            if A is not None:
                u = (math.cos(math.radians(A)), math.sin(math.radians(A)))
                if ln is None:
                    t = d[0] * u[0] + d[1] * u[1]
                    ln = t if t > 1e-9 else math.hypot(*d)
            else:
                u = _unit(d)
                if tool != "POLYGON":  # nearly level or upright: exactly, as a click would draw it
                    u = _square(u)
            if ln is None:
                return at
            return (a[0] + u[0] * ln, a[1] + u[1] * ln)
        if tool == "RECT" and stage == 1:
            a = pts[0]
            u = a[0] + _sign(at[0] - a[0]) * W if W is not None else at[0]
            v = a[1] + _sign(at[1] - a[1]) * H if H is not None else at[1]
            return (u, v)
        if tool == "CRECT" and stage == 1:
            c = pts[0]
            u = c[0] + _sign(at[0] - c[0]) * W / 2 if W is not None else at[0]
            v = c[1] + _sign(at[1] - c[1]) * H / 2 if H is not None else at[1]
            return (u, v)
        if tool == "CIRCLE" and stage == 1 and R is not None:
            c = pts[0]
            u = _unit((at[0] - c[0], at[1] - c[1]))
            return (c[0] + u[0] * R, c[1] + u[1] * R)
        if tool == "ARC" and stage == 2 and R is not None:
            return arc_middle(pts[0], pts[1], R, at)
        if tool == "SLOT" and stage == 2 and R is not None:
            a, b = pts
            t = _unit((b[0] - a[0], b[1] - a[1]))
            nrm = (-t[1], t[0])
            side = _sign((at[0] - a[0]) * nrm[0] + (at[1] - a[1]) * nrm[1])
            along = (at[0] - a[0]) * t[0] + (at[1] - a[1]) * t[1]
            return (a[0] + t[0] * along + nrm[0] * side * R, a[1] + t[1] * along + nrm[1] * side * R)
        return at

    def live(self, tool: str, pts: list, at: tuple[float, float]) -> list[Field]:
        """The boxes for the shape the mouse at ``at`` would make now (after ``constrain``)."""
        stage = len(pts)
        boxes = self.keys(tool, stage)
        if not boxes:
            return []
        now: dict[str, float] = {}
        a = pts[0]
        if stage == 1 and tool in ("LINE", "CENTRELINE", "ARC", "SLOT", "POLYGON"):
            d = (at[0] - a[0], at[1] - a[1])
            now["L"] = now["R"] = math.hypot(*d)
            now["A"] = math.degrees(math.atan2(d[1], d[0])) % 360
        elif stage == 1 and tool == "RECT":
            now["W"], now["H"] = abs(at[0] - a[0]), abs(at[1] - a[1])
        elif stage == 1 and tool == "CRECT":
            now["W"], now["H"] = 2 * abs(at[0] - a[0]), 2 * abs(at[1] - a[1])
        elif stage == 1 and tool == "CIRCLE":
            now["R"] = math.hypot(at[0] - a[0], at[1] - a[1])
        elif stage == 2 and tool == "ARC":
            now["R"] = circle_radius(pts[0], pts[1], at)
        elif stage == 2 and tool == "SLOT":
            b = pts[1]
            t = _unit((b[0] - a[0], b[1] - a[1]))
            now["R"] = abs((at[0] - a[0]) * -t[1] + (at[1] - a[1]) * t[0])
        out = []
        for i, (k, label) in enumerate(boxes):
            fixed = k in self.values
            f = Field(k, label, self.values[k][1] if fixed else now.get(k, 0.0), fixed,
                      self.values[k][0] if fixed else "", "deg" if k == "A" else "")
            if i == self.focus:
                f.editing, f.buffer = True, self.buffer
            out.append(f)
        return out

    # ---- the sizes it leaves ---------------------------------------------------------
    def all_fixed(self) -> dict[str, tuple[str, float]]:
        out = {k: (t, v) for k, t, v in self.done}
        out.update(self.values)
        return out

    def exact(self, key: str) -> str | None:
        """The typed text for ``key`` (this stage or an earlier one), for a step's own argument."""
        got = self.all_fixed().get(key)
        return got[0] if got else None

    def sizes(self, tool: str, n: int, fixed: dict[str, tuple[str, float]] | None = None) -> list[str]:
        """SDIM lines that keep the typed sizes on the geometry made from number ``n``."""
        fx = self.all_fixed() if fixed is None else fixed
        out: list[str] = []

        def text(k: str) -> str:
            return fx[k][0]

        if tool in ("LINE", "CENTRELINE"):
            if "L" in fx:
                out.append(f"SDIM, LENGTH, {n}, {text('L')}")
            if "A" in fx and not level_or_upright(fx["A"][1]):
                out.append(f"SDIM, ANGLE, {n}, {line_angle_text(*fx['A'])}")
        elif tool in ("RECT", "CRECT"):
            if "W" in fx:
                out.append(f"SDIM, LENGTH, {n}, {text('W')}")
            if "H" in fx:
                out.append(f"SDIM, LENGTH, {n + 1}, {text('H')}")
        elif tool == "CIRCLE":
            if "R" in fx:
                out.append(f"SDIM, RADIUS, {n}, {text('R')}")
        elif tool == "ARC":
            if "L" in fx:
                out.append(f"SDIM, DIST, {n}.S, {n}.E, {text('L')}")
            if "R" in fx:
                out.append(f"SDIM, RADIUS, {n}, {text('R')}")
        elif tool == "SLOT":
            if "L" in fx:
                out.append(f"SDIM, DIST, {n}.C, {n + 1}.C, {text('L')}")
            if "R" in fx:
                out.append(f"SDIM, RADIUS, {n}, {text('R')}")
        # POLYGON: the typed radius and angle go into SNGON itself
        return out


def _names():
    return (("L", "length"), ("W", "width"), ("H", "height"), ("R", "radius"), ("A", "angle"))


def level_or_upright(deg: float) -> bool:
    a = deg % 180
    return min(a, 180 - a) <= SNAP_ANGLE or abs(a - 90) <= SNAP_ANGLE


def line_angle_text(text: str, deg: float) -> str:
    """A line's ANGLE size, as the sketch measures it (0 to 180 from H, either way
    round: a line at 225 degrees is at 135); an expression is kept."""
    if is_number(text):
        return fmt_num(round(abs(((deg + 180.0) % 360.0) - 180.0), 6) + 0.0)
    return text


def circle_radius(a, b, m) -> float:
    """Radius of the circle through a, b and m (huge when they are in a line)."""
    ax, ay = a
    bx, by = b
    cx, cy = m
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        return 0.0
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return math.hypot(ax - ux, ay - uy)


def arc_middle(a, b, r: float, at) -> tuple[float, float]:
    """The middle of the arc of radius ``r`` from a to b that bulges towards ``at``
    (the short way round, or the long way when the mouse is further out than r)."""
    half = math.dist(a, b) / 2
    r = max(r, half)
    mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    t = _unit((b[0] - a[0], b[1] - a[1]))
    nrm = (-t[1], t[0])
    off = (at[0] - mid[0]) * nrm[0] + (at[1] - mid[1]) * nrm[1]
    side = _sign(off)
    h = math.sqrt(max(r * r - half * half, 0.0))
    bulge = r + h if abs(off) > r else r - h  # past the radius: the long way round
    return (mid[0] + nrm[0] * side * bulge, mid[1] + nrm[1] * side * bulge)
