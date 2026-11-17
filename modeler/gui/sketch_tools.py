"""Sketch mode by mouse: turn clicks on the sketch plane into sketch commands.

No Qt here, so it is tested headless. The viewport tells the controller
where the mouse is on the sketch plane (u, v) and how big a few pixels are
there (``tol``); the controller answers with command lines to run and with
a preview of what is being drawn. Everything that changes the sketch goes
through those commands, exactly as if they were typed.

Tools: SELECT (click to select, drag a point to move it), LINE (a chain of
lines; click the first point again, or press Esc, to finish), CENTRELINE,
RECT, CRECT (centre and corner), RECT3 (at an angle), CIRCLE, CIRCLE3,
ARC (start, end, then a point it passes through), TARC (on from an end),
SLOT, ARCSLOT, POLYGON, POINT, FREEHAND, and the editing tools TRIM (click
the piece to cut away, or drag across pieces), EXTEND (click near an end),
FILLET and CHAMFER (click a corner), SPLIT (click where) and CORNER (click
the two curves).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..commands import Processor
from ..lang.expr import fmt_num
from ..sketch import edit as sedit
from ..sketch.sketch import Sketch, SketchError

TOOLS = ("SELECT", "LINE", "CENTRELINE", "RECT", "CRECT", "RECT3", "CIRCLE", "CIRCLE3", "ARC", "TARC", "SLOT",
         "ARCSLOT", "POLYGON", "POINT", "FREEHAND", "TRIM", "EXTEND", "FILLET", "CHAMFER", "SPLIT", "CORNER")
DRAW_TOOLS = TOOLS[1:TOOLS.index("TRIM")]
EDIT_TOOLS = TOOLS[TOOLS.index("TRIM"):]
HINTS = {
    "SELECT": "Click to select sketch geometry (Ctrl adds); drag a point to move it; double-click a size to change it",
    "LINE": "Click the start, then each next point; click the first point again or press Esc to finish",
    "CENTRELINE": "Click the start, then the end of a construction line (an axis to revolve about or mirror in)",
    "RECT": "Click one corner, then the opposite corner",
    "CRECT": "Click the centre, then a corner",
    "RECT3": "Click two corners for the first side, then a point on the far side",
    "CIRCLE": "Click the centre, then a point on the circle",
    "CIRCLE3": "Click three points the circle passes through",
    "ARC": "Click the start, then the end, then a point the arc passes through",
    "TARC": "Click the end of a line or arc, then where the arc that carries on smoothly from it should end",
    "SLOT": "Click the first centre, then the second, then a point on the side",
    "ARCSLOT": "Click the centre of the bend, then the start of the slot's middle, then its end, then a point on the side",
    "POLYGON": "Click the centre, then a corner (the number of sides is set on the toolbar)",
    "POINT": "Click to place a point",
    "FREEHAND": "Hold the left button and draw; let go to finish. End where you started for a closed shape to extrude",
    "TRIM": "Click the piece of a curve to cut away (up to the curves crossing it), or drag across pieces to cut "
            "every one the mouse passes over",
    "EXTEND": "Click near the end of a line or arc to make it reach the next curve",
    "FILLET": "Click a corner where two curves (lines or arcs) meet to round it (double-click the radius to change it)",
    "CHAMFER": "Click a corner where two lines meet to cut it straight (double-click a size to change it)",
    "SPLIT": "Click a curve where it should be split in two (a circle: click two places)",
    "CORNER": "Click the part of one curve to keep, then the part of another: both are trimmed or extended to meet",
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
        self.stroke: list[tuple[float, float]] | None = None  # FREEHAND: the points drawn so far
        self.stroke_snap: str | None = None  # FREEHAND: the point the stroke started on
        self.trim_axes = False  # TRIM: the H and V axes cut too (STRIM ... AXES)
        self.polygon_sides = 6  # POLYGON: how many sides
        self.picked: list[tuple[int, tuple[float, float]]] = []  # SPLIT (circle) and CORNER: curves clicked so far
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
        self.stroke = None
        self.stroke_snap = None
        self.picked = []
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
        elif self.tool == "FREEHAND" and self.sketch is not None:
            at, self.stroke_snap = self.snap(u, v, tol)
            self.stroke = [at if self.stroke_snap else (u, v)]
        elif self.tool == "TRIM" and self.sketch is not None:
            self.stroke = [(u, v)]  # a drag across curves is a power trim
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
        elif self.tool == "FREEHAND":
            if self.stroke is not None:
                if math.dist(self.stroke[-1], (u, v)) > tol * 0.25:
                    self.stroke.append((u, v))
                pv.arcs.append(list(self.stroke))
        elif self.tool == "TRIM":
            if self.stroke is not None:
                if math.dist(self.stroke[-1], (u, v)) > tol * 0.25:
                    self.stroke.append((u, v))
                pv.lines += [(a, b) for a, b in zip(self.stroke, self.stroke[1:])]
                for n, at in self.power_picks(self.stroke, tol):
                    piece = self.trim_preview(*at, tol, n)
                    if piece:
                        pv.arcs.append(piece)
            else:
                piece = self.trim_preview(u, v, tol)
                if piece:
                    pv.arcs.append(piece)
            pv.snap = None
        elif self.tool in ("SPLIT", "CORNER", "CHAMFER", "FILLET", "EXTEND"):
            pv = self._edit_preview(u, v, tol, pv)
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

    def trim_preview(self, u: float, v: float, tol: float, n: int | None = None):
        """The piece a TRIM click here would cut away, as a polyline."""
        n = self.curve_at(u, v, tol) if n is None else n
        if n is None:
            return None
        sk = self.sketch
        g = sk.geos[n]
        try:
            lo, hi, _, _ = sedit.trim_piece(sk, n, (u, v), self.trim_axes)
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
            if g is None or g.kind not in ("LINE", "ARC"):
                return []
            try:
                l1, a, l2, b = sedit._corner(sk, name)
            except SketchError:
                return []
            short = min(math.dist(sk.pt(ln.pts["S"]), sk.pt(ln.pts["E"])) for ln in (l1, l2))
            step = nice_step(short * 0.25)
            return [f"SFILLET, {name}, {_r(max(step, round(short * 0.2 / step) * step))}"]
        if t == "CHAMFER":
            _, name = self.snap(u, v, tol)
            if not name or "." not in name:
                return []
            try:
                l1, a, l2, b = sedit._corner(sk, name)
            except SketchError:
                return []
            if l1.kind != "LINE" or l2.kind != "LINE":
                return []
            short = min(math.dist(sk.pt(ln.pts["S"]), sk.pt(ln.pts["E"])) for ln in (l1, l2))
            step = nice_step(short * 0.25)
            return [f"SCHAMFER, {name}, {_r(max(step, round(short * 0.2 / step) * step))}"]
        n = self.curve_at(u, v, tol)
        if n is None:
            return []
        g = sk.geos[n]
        if t == "SPLIT":
            if g.kind == "SPLINE":
                return []
            at = _uv(_foot_on(sk, g, (u, v)))
            if g.kind != "CIRCLE":
                return [f"SSPLIT, {n}, {at}"]
            if self.picked and self.picked[0][0] == n:
                first = _uv(self.picked[0][1])
                self.picked = []
                return [f"SSPLIT, {n}, {first}, {at}"]
            self.picked = [(n, _foot_on(sk, g, (u, v)))]
            return []
        if t == "CORNER":
            if g.kind not in ("LINE", "ARC"):
                return []
            if self.picked and self.picked[0][0] != n:
                (n1, p1), self.picked = self.picked[0], []
                return [f"SCORNER, {n1}, {n}, {_uv(p1)}, {_uv((u, v))}"]
            self.picked = [(n, (u, v))]
            return []
        if t == "TRIM":
            return [f"STRIM, {n}, {_uv((u, v))}" + (", AXES" if self.trim_axes else "")]
        if g.kind == "CIRCLE":
            return []
        ends = {r: sk.pt(g.pts[r]) for r in ("S", "E")}
        role = min(ends, key=lambda r: math.hypot(ends[r][0] - u, ends[r][1] - v))
        return [f"SEXTEND, {n}.{role}"]

    def release(self, u: float, v: float, tol: float) -> list[str]:
        """Left button up after a drag: move the point for real (SELECT), or
        turn the drawn stroke into a spline (FREEHAND)."""
        if self.tool == "FREEHAND" and self.stroke is not None:
            stroke, start = self.stroke + [(u, v)], self.stroke_snap
            self.stroke, self.stroke_snap = None, None
            self.preview = Preview()
            _, end = self.snap(u, v, tol)
            return freehand_commands(stroke, tol, start, end)
        if self.tool == "TRIM" and self.stroke is not None:
            stroke = self.stroke + [(u, v)]
            self.stroke = None
            self.preview = Preview()
            return power_trim_command(self.power_picks(stroke, tol), self.trim_axes)
        if self.drag and self.drag_at is not None:
            name, self.drag, self.drag_at = self.drag, None, None
            self.preview = Preview()
            return [f"SMOVE, {name}, {_uv((u, v))}"]
        self.drag = None
        return []

    def click(self, u: float, v: float, tol: float, add: bool = False) -> list[str]:
        """A left click (press and release without moving)."""
        self.drag = None
        self.stroke = None
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
        if t in EDIT_TOOLS:
            return self._edit_click(u, v, tol)
        if t == "LINE":
            return self._line_click(at, snap, tol)
        if t == "TARC" and not self.clicks:
            g = self.sketch.ref(snap).geo if (snap and "." in snap and self.sketch is not None) else None
            if g is None or g.kind not in ("LINE", "ARC") or snap.split(".")[1] not in ("S", "E"):
                return []  # it starts at the end of a line or arc
        self.clicks.append((at, snap))
        done = self._draw_more(t)
        if done is not None:
            return done
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

    def _draw_more(self, t: str) -> list[str] | None:
        """The newer drawing tools, once they have all their clicks (None: not one of them)."""
        if t not in ("CENTRELINE", "CRECT", "RECT3", "CIRCLE3", "TARC", "ARCSLOT", "POLYGON"):
            return None
        need = {"CENTRELINE": 2, "CRECT": 2, "RECT3": 3, "CIRCLE3": 3, "TARC": 2, "ARCSLOT": 4, "POLYGON": 2}[t]
        if len(self.clicks) < need:
            return []
        clicks, self.clicks = self.clicks, []
        pts = [c[0] for c in clicks]
        names = [_snapped(a, s) for a, s in clicks]
        if any(math.dist(pts[i], pts[j]) < 1e-9 for i in range(len(pts)) for j in range(i)) and t != "ARCSLOT":
            return []
        if t == "CENTRELINE":
            ang = math.degrees(math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0])) % 180
            flag = ", H" if min(ang, 180 - ang) <= SNAP_ANGLE else (", V" if abs(ang - 90) <= SNAP_ANGLE else "")
            return [f"SLINE, {names[0]}, {names[1]}, CONSTR{flag}"]
        if t == "CRECT":
            if abs(pts[0][0] - pts[1][0]) < 1e-9 or abs(pts[0][1] - pts[1][1]) < 1e-9:
                return []
            return [f"SRECTC, {names[0]}, {names[1]}"]
        if t == "RECT3":
            return [f"SRECT3, {names[0]}, {names[1]}, {_uv(pts[2])}"]
        if t == "CIRCLE3":
            return [f"SCIRCLE3, {names[0]}, {names[1]}, {names[2]}"]
        if t == "TARC":
            return [f"SARCT, {clicks[0][1]}, {names[1]}"]
        if t == "POLYGON":
            r = math.dist(pts[0], pts[1])
            ang = math.degrees(math.atan2(pts[1][1] - pts[0][1], pts[1][0] - pts[0][0]))
            return [f"SNGON, {names[0]}, {self.polygon_sides}, {_r(r)}, {_r(round(ang, 2))}"]
        # ARCSLOT: centre, start of the middle, its end, a point on the side
        c, a, b, w = pts
        r = math.dist(c, a)
        if r < 1e-9 or math.dist(c, b) < 1e-9:
            return []
        a1 = math.degrees(math.atan2(a[1] - c[1], a[0] - c[0]))
        a2 = math.degrees(math.atan2(b[1] - c[1], b[0] - c[0]))
        half = abs(math.dist(c, w) - r)
        step = nice_step(r * 0.05)
        half = max(step, round(half / step) * step)
        if half >= r or abs((a2 - a1) % 360) < 1e-6:
            return []
        return [f"SSLOTARC, {names[0]}, {_r(r)}, {_r(round(a1, 2))}, {_r(round(a2, 2))}, {_r(half)}"]

    def power_picks(self, stroke, tol: float) -> list[tuple[int, tuple[float, float]]]:
        """Where a drag across curves passes over a piece of a curve: one
        (curve, point) per piece, in the order the mouse reached them."""
        sk = self.sketch
        if sk is None or len(stroke) < 2:
            return []
        dense = [stroke[0]]
        for a, b in zip(stroke, stroke[1:]):
            k = max(1, int(math.dist(a, b) / (0.4 * tol)))
            dense += [(a[0] + (b[0] - a[0]) * i / k, a[1] + (b[1] - a[1]) * i / k) for i in range(1, k + 1)]
        seen, out = set(), []
        for q in dense:
            n = self.curve_at(q[0], q[1], tol / 1.5)
            if n is None:
                continue
            try:
                lo, hi, _, _ = sedit.trim_piece(sk, n, q, self.trim_axes)
            except SketchError:
                continue
            key = (n, round(lo, 6), round(hi, 6))
            if key not in seen:
                seen.add(key)
                out.append((n, q))
        return out

    def _edit_preview(self, u: float, v: float, tol: float, pv: Preview) -> Preview:
        """Show what an edit tool would act on: the corner, or the curve under the mouse."""
        sk = self.sketch
        if sk is None:
            return pv
        if self.tool in ("FILLET", "CHAMFER"):
            return pv  # the snap mark on the corner says it
        n = self.curve_at(u, v, tol)
        if self.tool == "SPLIT" and n is not None and sk.geos[n].kind != "SPLINE":
            pv.snap = _foot_on(sk, sk.geos[n], (u, v))
        if self.tool == "CORNER" and self.picked:
            n1, p1 = self.picked[0]
            if n1 in sk.geos:
                pv.arcs.append(_curve_polyline(sk, sk.geos[n1]))
        if n is not None and self.tool in ("CORNER", "EXTEND"):
            pv.arcs.append(_curve_polyline(sk, sk.geos[n]))
        return pv

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
        elif t == "CENTRELINE":
            pv.lines.append((pts[0], at))
        elif t == "CRECT":
            c = pts[0]
            du, dv = at[0] - c[0], at[1] - c[1]
            q = [(c[0] - du, c[1] - dv), (c[0] + du, c[1] - dv), (c[0] + du, c[1] + dv), (c[0] - du, c[1] + dv)]
            pv.lines += [(q[i], q[(i + 1) % 4]) for i in range(4)]
        elif t == "RECT3":
            if len(pts) == 1:
                pv.lines.append((pts[0], at))
            else:
                a, b = pts
                L = math.dist(a, b) or 1.0
                nrm = (-(b[1] - a[1]) / L, (b[0] - a[0]) / L)
                w = (at[0] - a[0]) * nrm[0] + (at[1] - a[1]) * nrm[1]
                q = [a, b, (b[0] + nrm[0] * w, b[1] + nrm[1] * w), (a[0] + nrm[0] * w, a[1] + nrm[1] * w)]
                pv.lines += [(q[i], q[(i + 1) % 4]) for i in range(4)]
        elif t == "CIRCLE3":
            if len(pts) == 1:
                pv.lines.append((pts[0], at))
            else:
                ring = _circle_through(pts[0], pts[1], at)
                if ring:
                    pv.circles.append(ring)
        elif t == "TARC":
            arc = _tangent_polyline(self.sketch, self.clicks[0][1], at) if self.sketch is not None else None
            if arc:
                pv.arcs.append(arc)
        elif t == "POLYGON":
            c = pts[0]
            r = math.dist(c, at)
            a0 = math.atan2(at[1] - c[1], at[0] - c[0])
            n = max(3, int(self.polygon_sides))
            q = [(c[0] + r * math.cos(a0 + 2 * math.pi * i / n), c[1] + r * math.sin(a0 + 2 * math.pi * i / n))
                 for i in range(n)]
            pv.lines += [(q[i], q[(i + 1) % n]) for i in range(n)]
            pv.circles.append((c, r))
        elif t == "ARCSLOT":
            c = pts[0]
            if len(pts) == 1:
                pv.lines.append((c, at))
            else:
                r = math.dist(c, pts[1])
                a1 = math.atan2(pts[1][1] - c[1], pts[1][0] - c[0])
                end = at if len(pts) == 2 else pts[2]
                a2 = math.atan2(end[1] - c[1], end[0] - c[0])
                span = (a2 - a1) % (2 * math.pi)
                half = abs(math.dist(c, at) - r) if len(pts) == 3 else 0.0
                for rr in ({r} if half == 0 else {r - half, r + half}):
                    pv.arcs.append([(c[0] + rr * math.cos(a1 + span * i / 32), c[1] + rr * math.sin(a1 + span * i / 32))
                                    for i in range(33)])
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


def transform_command(p: Processor, kind: str, values: str, copy: bool = False) -> list[str]:
    """STRANSFORM for the selected geometry. values: "du, dv" (MOVE), or
    "angle, centre" / "factor, centre" (ROTATE / SCALE; the centre a point
    name like O or 3.C, or u, v)."""
    geos = _selected_geos(p, "Move / copy", ("LINE", "ARC", "CIRCLE", "POINT", "SPLINE"))
    return [f"STRANSFORM, {kind}, {values.strip()}, {', '.join(geos)}" + (", COPY" if copy else "")]


def power_trim_command(picks, axes: bool = False) -> list[str]:
    if not picks:
        return []
    return ["STRIM, " + ", ".join(f"{n}, {_uv(q)}" for n, q in picks) + (", AXES" if axes else "")]


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
        return dimension_edit(p, c.uid, value_text, c.data.get("arg", -1))
    return None


def dimension_edit(p: Processor, uid: int, value_text: str, arg: int = -1) -> str | None:
    """HIST, EDIT for entry ``uid`` with the size at ``arg`` (counted from
    the end: -1 is the last argument) changed to value_text."""
    from ..lang.script import split_args

    for i, e in enumerate(p.history[: p.cursor]):
        if e.uid != uid:
            continue
        line = e.text.strip()
        if not _sized(line) or "\n" in line:
            return None
        parts = split_args(line)
        if not -len(parts) < arg < 0:
            return None
        parts[arg] = value_text.strip()
        new = ", ".join(x.strip() for x in parts)
        return f'HIST, EDIT, {i + 1}, "{new}"'
    return None


def _sized(line: str) -> bool:
    """An entry whose last argument is the size of the dimension it made
    (SDIM, SFILLET with its radius, SCHAMFER with its sizes; which one is in
    the dimension's data["arg"])."""
    word = line.split(",", 1)[0].strip().upper()
    return word in ("SDIM", "SFILLET", "SCHAMFER")


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
        out.append((c.label, f"{c.kind.lower()} {', '.join(c.refs)}", n,
                    split_args(e.text.strip())[c.data.get("arg", -1)].strip()))
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
    if g.kind == "SPLINE":
        from ..sketch.profile import spline_samples

        pts = spline_samples(sk, g)
        return min(_segment_distance(q, pts[i], pts[i + 1]) for i in range(len(pts) - 1))
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


def _foot_on(sk: Sketch, g, q) -> tuple[float, float]:
    """The point of curve g nearest q (on its line or circle)."""
    if g.kind == "LINE":
        a, b = sk.pt(g.pts["S"]), sk.pt(g.pts["E"])
        dx, dy = b[0] - a[0], b[1] - a[1]
        L2 = dx * dx + dy * dy or 1e-12
        t = ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2
        return (a[0] + t * dx, a[1] + t * dy)
    c, r = sk.pt(g.pts["C"]), sk.radius(g)
    d = math.dist(c, q) or 1e-12
    return (c[0] + (q[0] - c[0]) * r / d, c[1] + (q[1] - c[1]) * r / d)


def _curve_polyline(sk: Sketch, g) -> list[tuple[float, float]]:
    if g.kind == "LINE":
        return [sk.pt(g.pts["S"]), sk.pt(g.pts["E"])]
    if g.kind == "SPLINE":
        from ..sketch.profile import spline_samples

        return list(spline_samples(sk, g))
    c, r = sk.pt(g.pts["C"]), sk.radius(g)
    a1, a2 = (0.0, 360.0) if g.kind == "CIRCLE" else sk.arc_angles(g)
    return [(c[0] + r * math.cos(math.radians(a1 + (a2 - a1) * i / 48)),
             c[1] + r * math.sin(math.radians(a1 + (a2 - a1) * i / 48))) for i in range(49)]


def _circle_through(a, b, c):
    (x1, y1), (x2, y2), (x3, y3) = a, b, c
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return None
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    return ((ux, uy), math.hypot(x1 - ux, y1 - uy))


def _tangent_polyline(sk: Sketch, end: str, q, n: int = 32):
    """The arc SARCT, end, q would draw, as points (None if it is a line)."""
    from ..sketch import edit as ed

    try:
        g = sk.ref(end).geo
        role = end.split(".")[1]
        P = sk.pt(g.pts[role])
        back = ed._away(sk, g, role)
    except (SketchError, KeyError, IndexError, AttributeError):
        return None
    t = (-back[0], -back[1])
    w = (q[0] - P[0], q[1] - P[1])
    nrm = (-t[1], t[0])
    side = w[0] * nrm[0] + w[1] * nrm[1]
    if abs(side) < 1e-9 * max(1.0, math.hypot(*w)):
        return [P, q]
    s = (w[0] * w[0] + w[1] * w[1]) / (2 * side)
    C = (P[0] + nrm[0] * s, P[1] + nrm[1] * s)
    a0 = math.atan2(P[1] - C[1], P[0] - C[0])
    a1 = math.atan2(q[1] - C[1], q[0] - C[0])
    span = (a1 - a0) % (2 * math.pi) if s > 0 else -((a0 - a1) % (2 * math.pi))
    r = abs(s)
    return [(C[0] + r * math.cos(a0 + span * i / n), C[1] + r * math.sin(a0 + span * i / n)) for i in range(n + 1)]


def simplify_stroke(pts, eps: float) -> list[tuple[float, float]]:
    """Douglas-Peucker: the fewest of the drawn points that keep the stroke
    within eps."""
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    todo = [(0, len(pts) - 1)]
    while todo:
        i, j = todo.pop()
        best, k = -1.0, -1
        for m in range(i + 1, j):
            d = _segment_distance(pts[m], pts[i], pts[j])
            if d > best:
                best, k = d, m
        if k > 0 and best > eps:
            keep[k] = True
            todo += [(i, k), (k, j)]
    return [q for q, kp in zip(pts, keep) if kp]


MAX_STROKE_POINTS = 60


def freehand_commands(stroke, tol: float, start: str | None = None, end: str | None = None) -> list[str]:
    """A drawn stroke as a sketch command: a closed SSPLINE when it ends near
    where it started, else an open one (SLINE when it is nearly straight).
    Ends drawn on a sketch point are tied to it."""
    pts = [stroke[0]]
    for q in stroke[1:]:
        if math.dist(q, pts[-1]) > 1e-9:
            pts.append(q)
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
    if len(pts) < 2 or length < 3 * tol:
        return []
    closed = len(pts) > 4 and math.dist(pts[0], pts[-1]) <= 2 * tol and length > 8 * tol
    if closed:
        ring = pts[:-1] + [pts[0]]  # the end snaps onto the start; simplify the loop as a whole
    else:
        ring = pts
    eps = tol * 0.4
    simple = simplify_stroke(ring, eps)
    while len(simple) > MAX_STROKE_POINTS:
        eps *= 1.5
        simple = simplify_stroke(ring, eps)
    if closed:
        simple = simple[:-1]
        if len(simple) < 3:
            return []
        first = start or _uv(simple[0])
        return [f"SSPLINE, {first}, " + ", ".join(_uv(q) for q in simple[1:]) + ", CLOSE"]
    a = start or _uv(simple[0])
    b = end if (end and end != start) else _uv(simple[-1])
    if len(simple) == 2:
        return [f"SLINE, {a}, {b}"]
    return [f"SSPLINE, {a}, " + ", ".join(_uv(q) for q in simple[1:-1]) + f", {b}"]


def _segment_distance(q, a, b) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy or 1e-12
    t = max(0.0, min(1.0, ((q[0] - a[0]) * dx + (q[1] - a[1]) * dy) / L2))
    return math.hypot(q[0] - a[0] - t * dx, q[1] - a[1] - t * dy)


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
