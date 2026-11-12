"""Sketch mode by mouse: turn clicks on the sketch plane into sketch commands.

No Qt here, so it is tested headless. The viewport tells the controller
where the mouse is on the sketch plane (u, v) and how big a few pixels are
there (``tol``); the controller answers with command lines to run and with
a preview of what is being drawn. Everything that changes the sketch goes
through those commands, exactly as if they were typed.

Tools: SELECT (click to select, drag a point to move it), LINE (a chain of
lines; click the first point again, or press Esc, to finish), RECT, CIRCLE,
ARC (start, end, then a point it passes through), SLOT, POINT, and the
editing tools TRIM (click the piece to cut away), EXTEND (click near an
end) and FILLET (click a corner).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..commands import Processor
from ..lang.expr import fmt_num
from ..sketch import edit as sedit
from ..sketch.sketch import Sketch, SketchError

TOOLS = ("SELECT", "LINE", "RECT", "CIRCLE", "ARC", "SLOT", "POINT", "TRIM", "EXTEND", "FILLET")
HINTS = {
    "SELECT": "Click to select sketch geometry (Ctrl adds); drag a point to move it; double-click a size to change it",
    "LINE": "Click the start, then each next point; click the first point again or press Esc to finish",
    "RECT": "Click one corner, then the opposite corner",
    "CIRCLE": "Click the centre, then a point on the circle",
    "ARC": "Click the start, then the end, then a point the arc passes through",
    "SLOT": "Click the first centre, then the second, then a point on the side",
    "POINT": "Click to place a point",
    "TRIM": "Click the piece of a curve to cut away (up to the curves crossing it)",
    "EXTEND": "Click near the end of a line or arc to make it reach the next curve",
    "FILLET": "Click a corner where two lines meet to round it (double-click the radius to change it)",
}
SNAP_ANGLE = 3.0  # degrees: a line this close to level or upright is made horizontal or vertical


def _r(v: float) -> str:
    return fmt_num(round(v, 4) + 0.0)


def _uv(p) -> str:
    return f"{_r(p[0])}, {_r(p[1])}"


@dataclass
class Preview:
    """What to draw while a tool is in use, in sketch (u, v) coordinates."""

    lines: list[tuple[tuple[float, float], tuple[float, float]]] = field(default_factory=list)
    circles: list[tuple[tuple[float, float], float]] = field(default_factory=list)
    arcs: list[list[tuple[float, float]]] = field(default_factory=list)  # polylines
    snap: tuple[float, float] | None = None  # a point the cursor snaps to
    sketch: Sketch | None = None  # a moved copy of the sketch (while dragging)


def nice_step(tol: float) -> float:
    """A round step for clicked positions, about half the snap distance:
    1, 2 or 5 times a power of ten (so clicks give 12.5, not 12.4873)."""
    target = max(tol * 0.6, 1e-9)
    k = math.floor(math.log10(target))
    best = 10.0 ** k
    for m in (1, 2, 5, 10):
        if m * 10.0 ** k <= target:
            best = m * 10.0 ** k
    return best


def _snapped(at, snap) -> str:
    """A point argument: the snapped point's name, or u, v."""
    return snap if snap else _uv(at)


class SketchController:
    def __init__(self, processor: Processor) -> None:
        self.p = processor
        self.tool = "SELECT"
        self.clicks: list[tuple[tuple[float, float], str | None]] = []  # (where, snapped point name)
        self.chain_end: str | None = None  # LINE: the name of the last line's end
        self.chain_start: tuple[tuple[float, float], str | None] | None = None
        self.drag: str | None = None  # SELECT: the point being dragged
        self.drag_at: tuple[float, float] | None = None
        self.preview = Preview()

    # ---- state -------------------------------------------------------------
    @property
    def sketch(self) -> Sketch | None:
        m = self.p.model
        return m.sketches.get(m.active_sketch) if m.active_sketch else None

    def set_tool(self, tool: str) -> None:
        self.tool = tool.upper()
        self.reset()

    def reset(self) -> None:
        self.clicks = []
        self.chain_end = None
        self.chain_start = None
        self.drag = None
        self.drag_at = None
        self.preview = Preview()

    # ---- finding things under the mouse -----------------------------------------
    def snap(self, u: float, v: float, tol: float) -> tuple[tuple[float, float], str | None]:
        """The nearest sketch point within tol (its position and name), else (u, v)."""
        sk = self.sketch
        best, name = None, None
        if sk is None:
            step = nice_step(tol)
            return (round(u / step) * step + 0.0, round(v / step) * step + 0.0), None
        cands = [("ORIGIN", (0.0, 0.0))]
        for g in sk.geos.values():
            for role, i in g.pts.items():
                cands.append((f"{g.n}.{role}", sk.pt(i)))
        for nm, q in cands:
            d = math.hypot(q[0] - u, q[1] - v)
            if d <= tol and (best is None or d < best):
                best, name, at = d, nm, q
        if name is None:
            step = nice_step(tol)
            return (round(u / step) * step + 0.0, round(v / step) * step + 0.0), None
        return at, name

    def hit(self, u: float, v: float, tol: float) -> str | None:
        """What a click selects: a point (preferred), a size label, a curve, or an axis."""
        sk = self.sketch
        if sk is None:
            return None
        _, name = self.snap(u, v, tol)
        if name:
            return name
        best, what = None, None
        for c in sk.cons.values():
            if c.is_dim:
                q = label_position(sk, c)
                d = math.hypot(q[0] - u, q[1] - v)
                if d <= 2 * tol and (best is None or d < best):
                    best, what = d, c.label
        if what:
            return what
        for g in sk.geos.values():
            if g.kind == "POINT":
                continue
            d = _distance_to(sk, g, (u, v))
            if d <= tol and (best is None or d < best):
                best, what = d, str(g.n)
        if what:
            return what
        for axis, d in (("H", abs(v)), ("V", abs(u))):
            if d <= tol * 0.6 and (best is None or d < best):
                best, what = d, axis
        return what

    # ---- mouse --------------------------------------------------------------------
    def press(self, u: float, v: float, tol: float, add: bool = False) -> list[str]:
        """Left button down. SELECT on a point starts a drag."""
        if self.tool == "SELECT":
            name = self.hit(u, v, tol)
            if name and ("." in name) and self.sketch is not None:
                self.drag, self.drag_at = name, None
        return []

    def move(self, u: float, v: float, tol: float) -> Preview:
        """The mouse moved: update the preview."""
        pv = Preview()
        at, snap = self.snap(u, v, tol)
        if snap:
            pv.snap = at
        if self.tool == "SELECT" and self.drag:
            self.drag_at = (u, v)
            sk = self.sketch.copy()
            try:
                sk.move(self.drag, u, v)
                pv.sketch = sk
            except SketchError:
                pass
        elif self.tool == "TRIM":
            piece = self.trim_preview(u, v, tol)
            if piece:
                pv.arcs.append(piece)
            pv.snap = None
        elif self.clicks or (self.tool == "LINE" and self.chain_end):
            pv = self._rubber(at, pv)
        self.preview = pv
        return pv

    # ---- trim, extend, fillet ------------------------------------------------------
    def curve_at(self, u: float, v: float, tol: float) -> int | None:
        sk = self.sketch
        if sk is None:
            return None
        best, n = None, None
        for g in sk.geos.values():
            if g.kind == "POINT":
                continue
            d = _distance_to(sk, g, (u, v))
            if d <= 1.5 * tol and (best is None or d < best):
                best, n = d, g.n
        return n

    def trim_preview(self, u: float, v: float, tol: float):
        """The piece a TRIM click here would cut away, as a polyline."""
        n = self.curve_at(u, v, tol)
        if n is None:
            return None
        sk = self.sketch
        g = sk.geos[n]
        try:
            lo, hi, _, _ = sedit.trim_piece(sk, n, (u, v))
        except SketchError:
            return None
        if g.kind == "CIRCLE" and hi <= lo:
            hi += 360.0
        k = 2 if g.kind == "LINE" else 33
        return [sedit._point_at(sk, g, lo + (hi - lo) * i / (k - 1)) for i in range(k)]

    def _edit_click(self, u: float, v: float, tol: float) -> list[str]:
        sk = self.sketch
        if sk is None:
            return []
        t = self.tool
        if t == "FILLET":
            _, name = self.snap(u, v, tol)
            if not name or "." not in name:
                return []
            g = sk.ref(name).geo
            if g is None or g.kind != "LINE":
                return []
            try:
                l1, a, l2, b = sedit._corner(sk, name)
            except SketchError:
                return []
            short = min(math.dist(sk.pt(ln.pts["S"]), sk.pt(ln.pts["E"])) for ln in (l1, l2))
            step = nice_step(short * 0.25)
            return [f"SFILLET, {name}, {_r(max(step, round(short * 0.2 / step) * step))}"]
        n = self.curve_at(u, v, tol)
        if n is None:
            return []
        g = sk.geos[n]
        if t == "TRIM":
            return [f"STRIM, {n}, {_uv((u, v))}"]
        if g.kind == "CIRCLE":
            return []
        ends = {r: sk.pt(g.pts[r]) for r in ("S", "E")}
        role = min(ends, key=lambda r: math.hypot(ends[r][0] - u, ends[r][1] - v))
        return [f"SEXTEND, {n}.{role}"]

    def release(self, u: float, v: float, tol: float) -> list[str]:
        """Left button up after a drag (SELECT): move the point for real."""
        if self.drag and self.drag_at is not None:
            name, self.drag, self.drag_at = self.drag, None, None
            self.preview = Preview()
            return [f"SMOVE, {name}, {_uv((u, v))}"]
        self.drag = None
        return []

    def click(self, u: float, v: float, tol: float, add: bool = False) -> list[str]:
        """A left click (press and release without moving)."""
        self.drag = None
        at, snap = self.snap(u, v, tol)
        t = self.tool
        if t == "SELECT":
            name = self.hit(u, v, tol)
            if name is None:
                return ["SSEL, NONE"] if self.p.model.sketch_selection else []
            mode = "A, " if add else ""
            if add and name in self.p.model.sketch_selection:
                mode = "U, "
            return [f"SSEL, {mode}{name}"]
        if t == "POINT":
            return [f"SPOINT, {_snapped(at, snap)}"]
        if t in ("TRIM", "EXTEND", "FILLET"):
            return self._edit_click(u, v, tol)
        if t == "LINE":
            return self._line_click(at, snap, tol)
        self.clicks.append((at, snap))
        if t == "RECT" and len(self.clicks) == 2:
            (a, sa), (b, sb) = self.clicks
            self.clicks = []
            if abs(a[0] - b[0]) < 1e-9 or abs(a[1] - b[1]) < 1e-9:
                return []
            return [f"SRECT, {_snapped(a, sa)}, {_snapped(b, sb)}"]
        if t == "CIRCLE" and len(self.clicks) == 2:
            (c, sc), (b, _) = self.clicks
            self.clicks = []
            step = nice_step(tol)
            r = max(step, round(math.hypot(b[0] - c[0], b[1] - c[1]) / step) * step)
            return [f"SCIRCLE, {_snapped(c, sc)}, {_r(r)}"] if r > 0 else []
        if t == "ARC" and len(self.clicks) == 3:
            (a, sa), (b, sb), (m, _) = self.clicks
            self.clicks = []
            return [f"SARC3, {_snapped(a, sa)}, {_uv(m)}, {_snapped(b, sb)}"]
        if t == "SLOT" and len(self.clicks) == 3:
            (a, sa), (b, sb), (s, _) = self.clicks
            self.clicks = []
            step = nice_step(tol)
            r = max(step, round(_point_line_distance(s, a, b) / step) * step)
            return [f"SSLOT, {_snapped(a, sa)}, {_snapped(b, sb)}, {_r(r)}"] if r > 0 else []
        return []

    def finish(self) -> list[str]:
        """Esc or a right click: stop the current drawing."""
        self.reset()
        return []

    # ---- LINE chains --------------------------------------------------------------
    def _line_click(self, at, snap, tol) -> list[str]:
        if self.chain_end is None and not self.clicks:
            self.clicks = [(at, snap)]
            self.chain_start = (at, snap)
            return []
        if self.chain_end is not None:
            start_name = self.chain_end
            start_at = self.sketch.pt(self.sketch.ref(start_name).point) if self.sketch else at
        else:
            start_at, start_name = self.clicks[0]
        if math.hypot(at[0] - start_at[0], at[1] - start_at[1]) < 1e-9:
            return []
        closing = False
        first_at, first_name = self.chain_start or (None, None)
        if self.chain_end is not None and first_at is not None and math.hypot(
                at[0] - first_at[0], at[1] - first_at[1]) <= tol:
            closing = True
            end_arg = first_name or f"{self._first_line()}.S"
        else:
            end_arg = snap
        flag = ""
        ang = math.degrees(math.atan2(at[1] - start_at[1], at[0] - start_at[0])) % 180
        if min(ang, 180 - ang) <= SNAP_ANGLE:
            flag = ", H"
            at = (at[0], start_at[1]) if not end_arg else at
        elif abs(ang - 90) <= SNAP_ANGLE:
            flag = ", V"
            at = (start_at[0], at[1]) if not end_arg else at
        a = start_name if start_name else _uv(start_at)
        b = end_arg if end_arg else _uv(at)
        n = self._next_geo()
        cmds = [f"SLINE, {a}, {b}{flag}"]
        if closing:
            self.reset()
            return cmds
        if self.chain_end is None:
            self._first = n
        self.clicks = []
        self.chain_end = f"{n}.E"
        return cmds

    def _first_line(self) -> int:
        return getattr(self, "_first", 0)

    def _next_geo(self) -> int:
        sk = self.sketch
        return sk._next_geo if sk is not None else 1

    # ---- preview ----------------------------------------------------------------------
    def _rubber(self, at, pv: Preview) -> Preview:
        t = self.tool
        pts = [c[0] for c in self.clicks]
        if t == "LINE":
            if self.chain_end and self.sketch is not None:
                start = self.sketch.pt(self.sketch.ref(self.chain_end).point)
            else:
                start = pts[0]
            pv.lines.append((start, at))
        elif t == "RECT":
            a = pts[0]
            c = [a, (at[0], a[1]), at, (a[0], at[1])]
            pv.lines += [(c[i], c[(i + 1) % 4]) for i in range(4)]
        elif t == "CIRCLE":
            pv.circles.append((pts[0], math.hypot(at[0] - pts[0][0], at[1] - pts[0][1])))
        elif t == "ARC":
            if len(pts) == 1:
                pv.lines.append((pts[0], at))
            else:
                arc = _arc_polyline(pts[0], at, pts[1])
                pv.arcs.append(arc) if arc else pv.lines.append((pts[0], pts[1]))
        elif t == "SLOT":
            if len(pts) == 1:
                pv.lines.append((pts[0], at))
            else:
                r = _point_line_distance(at, pts[0], pts[1])
                pv.circles += [(pts[0], r), (pts[1], r)]
                pv.lines.append((pts[0], pts[1]))
        return pv


# =============================================================================
# what the constraint buttons send, from the sketch selection
# =============================================================================


class NeedSelection(Exception):
    pass


def _kinds(sk: Sketch, names: list[str]) -> list[str]:
    out = []
    for n in names:
        if n.startswith("C") and n[1:].isdigit():
            out.append("CON")
            continue
        r = sk.ref(n)
        out.append("P" if r.is_point else ("L" if r.geo.kind == "LINE" else "R"))
    return out


_NEEDS = {
    "COINCIDENT": "two points, or a point and a curve",
    "HORIZONTAL": "a line, or two points", "VERTICAL": "a line, or two points",
    "PARALLEL": "two lines", "PERPENDICULAR": "two lines",
    "TANGENT": "a line and an arc/circle, or two arcs/circles",
    "EQUAL": "two lines, or two arcs/circles", "MIDPOINT": "a point and a line",
    "SYMMETRIC": "two points and a line", "CONCENTRIC": "two arcs or circles", "FIX": "points or geometry",
}


def constraint_command(p: Processor, kind: str) -> list[str]:
    """SCON lines for the selected sketch geometry."""
    m = p.model
    sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
    if sk is None:
        raise NeedSelection("open a sketch first")
    sel = [s for s in m.sketch_selection if not (s.startswith("C") and s[1:].isdigit())]
    k = _kinds(sk, sel)
    need = f"{kind.title()}: select {_NEEDS[kind]} first (click, then Ctrl+click)"
    if kind == "COINCIDENT":
        if k == ["P", "P"]:
            return [f"SCON, COINCIDENT, {sel[0]}, {sel[1]}"]
        if sorted(k) in (["L", "P"], ["P", "R"]):
            pt, cv = (sel[0], sel[1]) if k[0] == "P" else (sel[1], sel[0])
            return [f"SCON, ON, {pt}, {cv}"]
        raise NeedSelection(need)
    if kind in ("HORIZONTAL", "VERTICAL"):
        if k and all(x == "L" for x in k):
            return [f"SCON, {kind}, {s}" for s in sel]
        if k == ["P", "P"]:
            return [f"SCON, {kind}, {sel[0]}, {sel[1]}"]
        raise NeedSelection(need)
    if kind in ("PARALLEL", "PERPENDICULAR"):
        if len(k) >= 2 and all(x == "L" for x in k):
            if kind == "PARALLEL":
                return [f"SCON, PARALLEL, {sel[0]}, {s}" for s in sel[1:]]
            if len(k) == 2:
                return [f"SCON, PERPENDICULAR, {sel[0]}, {sel[1]}"]
        raise NeedSelection(need)
    if kind == "EQUAL":
        if len(k) >= 2 and (all(x == "L" for x in k) or all(x == "R" for x in k)):
            return [f"SCON, EQUAL, {sel[0]}, {s}" for s in sel[1:]]
        raise NeedSelection(need)
    if kind == "TANGENT":
        if len(k) == 2 and "P" not in k and k != ["L", "L"]:
            return [f"SCON, TANGENT, {sel[0]}, {sel[1]}"]
        raise NeedSelection(need)
    if kind == "CONCENTRIC":
        if k == ["R", "R"]:
            return [f"SCON, CONCENTRIC, {sel[0]}, {sel[1]}"]
        raise NeedSelection(need)
    if kind == "MIDPOINT":
        if sorted(k) == ["L", "P"]:
            pt, ln = (sel[0], sel[1]) if k[0] == "P" else (sel[1], sel[0])
            return [f"SCON, MIDPOINT, {pt}, {ln}"]
        raise NeedSelection(need)
    if kind == "SYMMETRIC":
        if sorted(k) == ["L", "P", "P"]:
            pts = [s for s, x in zip(sel, k) if x == "P"]
            ln = next(s for s, x in zip(sel, k) if x == "L")
            return [f"SCON, SYMMETRIC, {pts[0]}, {pts[1]}, {ln}"]
        raise NeedSelection(need)
    if kind == "FIX":
        if sel:
            return [f"SCON, FIX, {s}" for s in sel]
        raise NeedSelection(need)
    raise NeedSelection(f"unknown constraint {kind}")


def dimension_for(p: Processor, which: str = "AUTO") -> tuple[str, list[str], float]:
    """(kind, names, current size) for a dimension on the selection.

    AUTO picks the obvious size: a line's length, a circle's diameter, an
    arc's radius, the distance between two points or from a point to a line,
    the angle between two lines (or their distance when parallel). HDIST and
    VDIST measure across or up."""
    m = p.model
    sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
    if sk is None:
        raise NeedSelection("open a sketch first")
    sel = [s for s in m.sketch_selection if not (s.startswith("C") and s[1:].isdigit())]
    k = _kinds(sk, sel)
    if which in ("HDIST", "VDIST"):
        if k == ["P", "P"] or k == ["L"]:
            return which, sel, sk.measure(which, tuple(sel))
        if k == ["P"]:  # from the origin
            return which, ["ORIGIN", sel[0]], sk.measure(which, ("ORIGIN", sel[0]))
        raise NeedSelection(f"{'Horizontal' if which == 'HDIST' else 'Vertical'} distance: select two points or a line")
    if k == ["L"]:
        return "LENGTH", sel, sk.measure("LENGTH", tuple(sel))
    if k == ["R"]:
        kind = "DIAMETER" if sk.ref(sel[0]).geo.kind == "CIRCLE" else "RADIUS"
        return kind, sel, sk.measure(kind, tuple(sel))
    if k == ["P", "P"] or sorted(k) == ["L", "P"]:
        return "DIST", sel, sk.measure("DIST", tuple(sel))
    if k == ["P"]:
        return "DIST", ["ORIGIN", sel[0]], sk.measure("DIST", ("ORIGIN", sel[0]))
    if k == ["L", "L"]:
        ang = sk.measure("ANGLE", tuple(sel))
        if min(ang, 180 - ang) < 1e-6:
            return "DIST", sel, sk.measure("DIST", tuple(sel))
        return "ANGLE", sel, ang
    raise NeedSelection("Dimension: select a line, a circle or arc, two points, a point and a line, or two lines")


def dimension_command(kind: str, names: list[str], value_text: str) -> str:
    return f"SDIM, {kind}, {', '.join(names)}, {value_text.strip()}"


def _selected_geos(p: Processor, what: str, kinds=("LINE", "ARC", "CIRCLE", "POINT")) -> list[str]:
    m = p.model
    sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
    if sk is None:
        raise NeedSelection("open a sketch first")
    out = [s for s in m.sketch_selection if s.isdigit() and int(s) in sk.geos and sk.geos[int(s)].kind in kinds]
    if not out:
        raise NeedSelection(f"{what}: select sketch geometry first (click, then Ctrl+click)")
    return out


def offset_command(p: Processor, d_text: str) -> list[str]:
    geos = _selected_geos(p, "Offset", ("LINE", "ARC", "CIRCLE"))
    return [f"SOFFSET, {d_text.strip()}, {', '.join(geos)}"]


def mirror_axes(p: Processor) -> list[str]:
    """Lines the selection could be mirrored about: selected lines first, then H and V."""
    sk = p.model.sketches.get(p.model.active_sketch) if p.model.active_sketch else None
    sel = [s for s in p.model.sketch_selection if s.isdigit()]
    lines = [s for s in sel if sk is not None and int(s) in sk.geos and sk.geos[int(s)].kind == "LINE"]
    return lines[::-1] + ["V", "H"]


def mirror_command(p: Processor, axis: str) -> list[str]:
    geos = [g for g in _selected_geos(p, "Mirror") if g != axis]
    if not geos:
        raise NeedSelection("Mirror: select the geometry to mirror as well as the line to mirror about")
    return [f"SMIRROR, {axis}, {', '.join(geos)}"]


def pattern_command(p: Processor, kind: str, values: str) -> list[str]:
    """values: "n, du, dv" (LINEAR) or "n, angle, centre" (POLAR; centre a point name or u, v)."""
    geos = _selected_geos(p, "Pattern")
    return [f"SPATTERN, {kind}, {values.strip()}, {', '.join(geos)}"]


def project_default(p: Processor) -> str:
    """What the Project button offers: the picked edges or faces, as SPROJECT arguments."""
    m = p.model
    if m.selection and m.selection_kind == "EDGE":
        return ", ".join(map(str, m.selection))
    if m.selection and m.selection_kind == "FACE":
        return "FACE, " + ", ".join(map(str, m.selection))
    return ""


def delete_command(p: Processor) -> list[str]:
    sel = list(p.model.sketch_selection)
    geos = [s for s in sel if "." not in s and s not in ("ORIGIN", "H", "V")]
    if not geos:
        raise NeedSelection("Delete: select sketch geometry or a size first (points at line ends go with their line)")
    return [f"SDEL, {', '.join(geos)}"]


def construction_command(p: Processor) -> list[str]:
    m = p.model
    sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
    sel = [s for s in m.sketch_selection if s.isdigit()]
    if sk is None or not sel:
        raise NeedSelection("Construction: select sketch lines, arcs or circles first")
    return [f"SCONSTRUCT, {s}, {'OFF' if sk.geos[int(s)].construction else 'ON'}" for s in sel]


def edit_dimension_entry(p: Processor, label: str, value_text: str) -> str | None:
    """HIST, EDIT for the history entry that made dimension ``label`` (C4),
    with the new size; None if that entry cannot be found."""
    m = p.model
    sk = m.sketches.get(m.active_sketch) if m.active_sketch else None
    sketches = [sk] if sk is not None else []
    sketches += [s for s in m.sketches.values() if s is not sk]
    for s in sketches:
        c = s.cons.get(int(label[1:])) if label[1:].isdigit() else None
        if c is None or not c.is_dim:
            continue
        return dimension_edit(p, c.uid, value_text)
    return None


def dimension_edit(p: Processor, uid: int, value_text: str) -> str | None:
    from ..lang.script import split_args

    for i, e in enumerate(p.history[: p.cursor]):
        if e.uid != uid:
            continue
        line = e.text.strip()
        if not _sized(line) or "\n" in line:
            return None
        parts = split_args(line)
        parts[-1] = value_text.strip()
        new = ", ".join(x.strip() for x in parts)
        return f'HIST, EDIT, {i + 1}, "{new}"'
    return None


def _sized(line: str) -> bool:
    """An entry whose last argument is the size of the dimension it made
    (SDIM, and SFILLET with its radius)."""
    word = line.split(",", 1)[0].strip().upper()
    return word in ("SDIM", "SFILLET")


def sketch_dimensions(p: Processor, name: str) -> list[tuple[str, str, int, str]]:
    """(label, what it measures, history entry number, size as written) for every dimension of a sketch."""
    from ..lang.script import split_args

    sk = p.model.sketch(name)
    by_uid = {e.uid: (i + 1, e) for i, e in enumerate(p.history[: p.cursor])}
    out = []
    for c in sk.cons.values():
        if not c.is_dim or c.uid not in by_uid:
            continue
        n, e = by_uid[c.uid]
        if not _sized(e.text.strip()):
            continue
        out.append((c.label, f"{c.kind.lower()} {', '.join(c.refs)}", n, split_args(e.text.strip())[-1].strip()))
    return out


# =============================================================================
# geometry helpers
# =============================================================================


def label_position(sk: Sketch, c) -> tuple[float, float]:
    """Where a dimension's size is written, in (u, v)."""
    return dimension_geometry(sk, c)[1]


def dimension_geometry(sk: Sketch, c):
    """(segments to draw, label position) for a dimension, in (u, v):
    the measuring line with its extension lines, and where the size goes."""
    rs = [sk.ref(r) for r in c.refs]
    off = 0.06 * sk.extent()
    segs = []

    def pt(r):
        if r.is_point:
            return sk.pt(r.point)
        a, b = sk.pt(r.geo.pts["S"]), sk.pt(r.geo.pts["E"])
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    k = c.kind
    if k == "LENGTH":  # a level or upright line is measured like HDIST / VDIST, in the same rows
        s0, e0 = sk.pt(rs[0].geo.pts["S"]), sk.pt(rs[0].geo.pts["E"])
        if abs(s0[1] - e0[1]) < 1e-9 * sk.extent():
            k = "HDIST"
        elif abs(s0[0] - e0[0]) < 1e-9 * sk.extent():
            k = "VDIST"
    if k in ("HDIST", "VDIST"):
        if len(rs) == 1:
            p, q = sk.pt(rs[0].geo.pts["S"]), sk.pt(rs[0].geo.pts["E"])
        else:
            p, q = pt(rs[0]), pt(rs[1])
        # baseline style: stacked below (across) or left (up) of the sketch, one row each
        row = sorted(x.n for x in sk.cons.values() if _row_kind(sk, x) == k).index(c.n) if c.n in sk.cons else 0
        lo_u, lo_v, _, _ = _bounds(sk)
        if k == "HDIST":
            lv = lo_v - off * (1 + 0.7 * row)
            segs += [(p, (p[0], lv)), (q, (q[0], lv)), ((p[0], lv), (q[0], lv))]
            return segs, ((p[0] + q[0]) / 2, lv + off * 0.2)
        lu = lo_u - off * (1 + 0.7 * row)
        segs += [(p, (lu, p[1])), (q, (lu, q[1])), ((lu, p[1]), (lu, q[1]))]
        return segs, (lu - off * 0.45, (p[1] + q[1]) / 2)
    if k == "LENGTH":
        s, e = sk.pt(rs[0].geo.pts["S"]), sk.pt(rs[0].geo.pts["E"])
        dx, dy = e[0] - s[0], e[1] - s[1]
        L = math.hypot(dx, dy) or 1.0
        n = (-dy / L * off, dx / L * off)
        lo_u, lo_v, hi_u, hi_v = _bounds(sk)
        mid = ((lo_u + hi_u) / 2, (lo_v + hi_v) / 2)
        if n[0] * ((s[0] + e[0]) / 2 - mid[0]) + n[1] * ((s[1] + e[1]) / 2 - mid[1]) < 0:
            n = (-n[0], -n[1])  # outside the sketch, not across it
        a, b = (s[0] + n[0], s[1] + n[1]), (e[0] + n[0], e[1] + n[1])
        segs += [(s, a), (e, b), (a, b)]
        return segs, ((a[0] + b[0]) / 2 + n[0] * 0.3, (a[1] + b[1]) / 2 + n[1] * 0.3)
    if k in ("RADIUS", "DIAMETER"):
        g = rs[0].geo
        cc = sk.pt(g.pts["C"])
        r = sk.radius(g)
        ang = math.radians(45.0)
        if g.kind == "ARC":
            a1, a2 = sk.arc_angles(g)
            ang = math.radians((a1 + a2) / 2)
        rim = (cc[0] + r * math.cos(ang), cc[1] + r * math.sin(ang))
        start = cc if k == "RADIUS" else (cc[0] - r * math.cos(ang), cc[1] - r * math.sin(ang))
        segs.append((start, rim))
        return segs, (rim[0] + off * 0.4 * math.cos(ang), rim[1] + off * 0.4 * math.sin(ang))
    if k == "DIST":
        if rs[0].is_point and rs[1].is_point:
            p, q = sk.pt(rs[0].point), sk.pt(rs[1].point)
        else:
            if rs[0].is_point or rs[1].is_point:
                pr, ln = (rs[0], rs[1]) if rs[0].is_point else (rs[1], rs[0])
                p = sk.pt(pr.point)
            else:
                ln, p = rs[0], sk.pt(rs[1].geo.pts["S"])
            a, b = sk.pt(ln.geo.pts["S"]), sk.pt(ln.geo.pts["E"])
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy or 1e-12
            t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2
            q = (a[0] + t * dx, a[1] + t * dy)
        segs.append((p, q))
        dx, dy = q[0] - p[0], q[1] - p[1]
        L = math.hypot(dx, dy) or 1.0
        return segs, ((p[0] + q[0]) / 2 - dy / L * off * 0.3, (p[1] + q[1]) / 2 + dx / L * off * 0.3)
    pts = [pt(r) for r in rs if not r.fixed] or [(0.0, 0.0)]
    u = sum(q[0] for q in pts) / len(pts)
    v = sum(q[1] for q in pts) / len(pts)
    return segs, (u + off * 0.3, v + off * 0.3)


def _row_kind(sk: Sketch, c) -> str:
    """HDIST / VDIST for sizes drawn in the rows below / left of the sketch."""
    if c.kind in ("HDIST", "VDIST"):
        return c.kind
    if c.kind == "LENGTH":
        g = sk.ref(c.refs[0]).geo
        s, e = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        if abs(s[1] - e[1]) < 1e-9 * sk.extent():
            return "HDIST"
        if abs(s[0] - e[0]) < 1e-9 * sk.extent():
            return "VDIST"
    return ""


def _bounds(sk: Sketch) -> tuple[float, float, float, float]:
    pts = [sk.pt(i) for g in sk.geos.values() for i in g.pts.values()]
    for g in sk.geos.values():
        if g.kind in ("CIRCLE", "ARC"):
            c, r = sk.pt(g.pts["C"]), sk.radius(g)
            pts += [(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)]
    if not pts:
        return 0.0, 0.0, 0.0, 0.0
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _distance_to(sk: Sketch, g, q) -> float:
    if g.kind == "LINE":
        a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-12
        t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
        return math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)
    c = sk.pt(g.pts["C"])
    r = sk.radius(g)
    d = abs(math.hypot(q[0] - c[0], q[1] - c[1]) - r)
    if g.kind == "ARC":
        a1, a2 = sk.arc_angles(g)
        ang = math.degrees(math.atan2(q[1] - c[1], q[0] - c[0]))
        while ang < a1:
            ang += 360
        if ang > a2:
            ends = [sk.pt(g.pts["S"]), sk.pt(g.pts["E"])]
            return min(math.hypot(q[0] - e[0], q[1] - e[1]) for e in ends)
    return d


def _point_line_distance(q, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy)
    if L < 1e-12:
        return math.hypot(q[0] - a[0], q[1] - a[1])
    return abs(dx * (q[1] - a[1]) - dy * (q[0] - a[0])) / L


def _arc_polyline(a, b, m, n: int = 32):
    """Points along the arc from a through m to b, or None if they are in line."""
    (x1, y1), (x2, y2), (x3, y3) = a, m, b
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return None
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    t1 = math.atan2(y1 - uy, x1 - ux)
    t3 = math.atan2(y3 - uy, x3 - ux)
    if d > 0:
        while t3 <= t1:
            t3 += 2 * math.pi
    else:
        while t3 >= t1:
            t3 -= 2 * math.pi
    return [(ux + r * math.cos(t1 + (t3 - t1) * i / n), uy + r * math.sin(t1 + (t3 - t1) * i / n)) for i in range(n + 1)]
