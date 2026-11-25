"""Drag handles in the 3D view (PLAN item 68): move, turn and pull with the mouse.

No Qt here, so it is tested headless. With the handles on, a picked body shows
three arrows (move along X, Y, Z) and three rings (turn about X, Y, Z) at its
middle; picked faces of a solid show a pull arrow along their normal and three
small arrows to move them. A drag follows the mouse with a live preview, snaps
to the grid (``step`` for lengths, ``angle_step`` for turns; Shift drags
freely), snaps to the corners, edge middles, circle centres and flat-face middles of
the other bodies when a corner or face of what is dragged comes within a few pixels
of being level with one of them (PLAN item 108: a marker shows the point), takes a
typed value (type a number while dragging, Enter puts it in),
and Esc cancels. Letting go writes one ordinary step:

    MOVE, b, dx, dy, dz              an arrow on a body
    ROTATE, b, a, cx,cy,cz, nx,ny,nz a ring on a body (about its middle)
    PUSHPULL, d                      the pull arrow on picked faces
    MOVEFACE, dx, dy, dz             a small arrow on picked faces

A body held by joints is moved the same way; the joint solver then moves the
rest of the linkage (commands/joint_handlers.py). ``HANDLES`` lists the same
handles as text and data, so the assistant needs nothing new.

The viewport gives two functions: ``to_pixel(xyz) -> (x, y)`` and
``ray(x, y) -> (origin, direction)``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from ..lang.expr import fmt_num

P3 = tuple[float, float, float]
AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
COLOURS = {"X": (0.9, 0.2, 0.2), "Y": (0.2, 0.75, 0.25), "Z": (0.25, 0.45, 0.95), "N": (1.0, 0.7, 0.1)}
PICK_PX = 9.0  # how near the mouse must be to a handle, in pixels
SNAP_PX = 10.0  # how near (in pixels along the arrow) a drag must come to a snap point
MAX_SNAP_POINTS = 4000  # snap points taken from the other bodies (more are thinned out)
RING_SEGMENTS = 48


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b) -> P3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b, k: float = 1.0) -> P3:
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _cross(a, b) -> P3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a) -> P3:
    n = _norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-15 else (0.0, 0.0, 1.0)


def _across(n) -> tuple[P3, P3]:
    """Two unit directions square to n and to each other."""
    h = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _unit(_cross(n, h))
    return u, _cross(n, u)


def snap(v: float, step: float) -> float:
    return round(v / step) * step if step > 0 else v


@dataclass
class Handle:
    name: str  # "X", "Y", "Z" (arrows and rings) or "N" (the pull arrow)
    kind: str  # MOVE, TURN (bodies), PULL, SLIDE (faces)
    origin: P3
    direction: P3  # the arrow's direction or the ring's axis
    size: float  # the arrow's length or the ring's radius

    def segments(self) -> list[tuple[P3, P3]]:
        """What to draw (and to pick by): line pieces in model space."""
        if self.kind == "TURN":
            u, w = _across(self.direction)
            pts = []
            for k in range(RING_SEGMENTS + 1):
                a = 2 * math.pi * k / RING_SEGMENTS
                pts.append(_add(_add(self.origin, u, self.size * math.cos(a)), w, self.size * math.sin(a)))
            return list(zip(pts, pts[1:]))
        tip = _add(self.origin, self.direction, self.size)
        return [(self.origin, tip)]

    @property
    def tip(self) -> P3:
        return _add(self.origin, self.direction, self.size)


@dataclass
class Drag:
    handle: Handle
    start: float  # where the drag began along the arrow (length) or round the ring (radians)
    value: float = 0.0  # how far it has gone: a length, or degrees
    typed: str = ""  # a number typed while dragging
    free: bool = False  # Shift: no snapping
    snapped: tuple | None = None  # (point, what it is) when the drag snapped to other geometry


@dataclass
class Handles:
    """The handles for what is picked now, and the drag in progress."""

    mode: str = ""  # BODY, FACES or "" (nothing to drag)
    body: int = 0
    label: str = ""  # how the body is named in commands
    faces: list[int] = field(default_factory=list)
    items: list[Handle] = field(default_factory=list)
    centre: P3 = (0.0, 0.0, 0.0)
    step: float = 1.0
    angle_step: float = 5.0
    drag: Drag | None = None
    jointed: bool = False  # the body is held by joints: the linkage follows a drag
    anchors: list = field(default_factory=list)  # points of what is dragged that snap
    targets: list = field(default_factory=list)  # (point, what it is) on the other bodies

    # ---- what to show ----------------------------------------------------------------
    @classmethod
    def for_model(cls, model, step: float = 1.0, angle_step: float = 5.0) -> "Handles":
        """Handles for the model's selection: one body, or faces of one solid."""
        h = cls(step=step, angle_step=angle_step)
        kind, sel = model.selection_kind, list(model.selection)
        if kind == "BODY" and len(sel) == 1 and sel[0] in model.bodies:
            h._body(model, sel[0])
        elif kind == "FACE" and sel:
            owners = {model.entity_owner("FACE", g)[0] for g in sel if _known(model, g)}
            if len(owners) == 1:
                h._faces(model, owners.pop(), sel)
        if h.mode:
            try:
                h.anchors, h.targets = snap_points(model, h)
            except Exception:  # noqa: BLE001 - no snapping rather than no handles
                h.anchors, h.targets = [], []
        return h

    def _body(self, model, bid: int) -> None:
        lo, hi = _bbox(model.body(bid).shape)
        c = tuple((a + b) / 2 for a, b in zip(lo, hi))
        size = max(_norm(_sub(hi, lo)) * 0.45, 1e-3)
        self.mode, self.body, self.centre = "BODY", bid, c  # type: ignore[assignment]
        self.label = _name(model, bid)
        self.items = [Handle(n, "MOVE", c, d, size) for n, d in AXES.items()]  # type: ignore[arg-type]
        self.items += [Handle(n, "TURN", c, d, size * 0.55) for n, d in AXES.items()]  # type: ignore[arg-type]
        self.jointed = any(bid in (j.fixed, j.moving) for j in getattr(model, "joints", []) if j.a)

    def _faces(self, model, bid: int, faces: list[int]) -> None:
        from ..geometry import recognize as rc
        from ..geometry import robust

        if not robust.solids(model.body(bid).shape):
            return
        pts, ns = [], []
        for g in faces:
            p, n = rc.face_normal_at_middle(model.entity_shape("FACE", g))
            pts.append(p)
            ns.append(n)
        total = tuple(sum(v[k] for v in ns) for k in range(3))
        if _norm(total) >= 0.9 * len(ns):  # faces that look one way: the arrow at their middle
            c = tuple(sum(p[k] for p in pts) / len(pts) for k in range(3))
            n = _unit(total)
        else:  # hole walls, rounds ...: the arrow on the first face, along its own normal
            c, n = pts[0], _unit(ns[0])
        lo, hi = _bbox(model.body(bid).shape)
        size = max(_norm(_sub(hi, lo)) * 0.3, 1e-3)
        self.mode, self.body, self.faces, self.centre = "FACES", bid, list(faces), c  # type: ignore[assignment]
        self.label = _name(model, bid)
        self.items = [Handle("N", "PULL", c, n, size)]  # type: ignore[arg-type]
        self.items += [Handle(k, "SLIDE", c, d, size * 0.5) for k, d in AXES.items()]  # type: ignore[arg-type]

    # ---- the mouse ---------------------------------------------------------------------
    def hit(self, x: float, y: float, to_pixel: Callable[[P3], tuple[float, float]]) -> Handle | None:
        best, best_d = None, PICK_PX
        for h in self.items:
            for a, b in h.segments():
                d = _seg_px(x, y, to_pixel(a), to_pixel(b))
                if d < best_d:
                    best, best_d = h, d
        return best

    def press(self, x: float, y: float, to_pixel, ray) -> bool:
        h = self.hit(x, y, to_pixel)
        if h is None:
            return False
        at = self._where(h, ray(x, y))
        if at is None:
            return False
        self.drag = Drag(h, at)
        return True

    def _where(self, h: Handle, r) -> float | None:
        """Along the arrow (a length) or round the ring (radians) where the mouse ray points."""
        o, d = r
        if h.kind == "TURN":
            den = _dot(d, h.direction)
            if abs(den) < 1e-9:
                return None
            t = _dot(_sub(h.origin, o), h.direction) / den
            q = _sub(_add(o, d, t), h.origin)
            u, w = _across(h.direction)
            return math.atan2(_dot(q, w), _dot(q, u))
        # the point on the arrow's line nearest to the ray
        a = h.direction
        w0 = _sub(h.origin, o)
        b = _dot(a, d)
        dd = _dot(d, d)
        den = dd - b * b  # (a is a unit direction)
        if abs(den) < 1e-12:
            return None
        return (b * _dot(d, w0) - dd * _dot(a, w0)) / den

    def move(self, ray, free: bool = False, to_pixel=None) -> None:
        g = self.drag
        if g is None:
            return
        at = self._where(g.handle, ray)
        if at is None:
            return
        g.free = free
        g.snapped = None
        if g.handle.kind == "TURN":
            deg = math.degrees(at - g.start)
            deg = (deg + 180.0) % 360.0 - 180.0
            g.value = deg if free else snap(deg, self.angle_step)
        else:
            v = at - g.start
            hit = None if free or to_pixel is None else self.snap_to(g.handle, v, to_pixel)
            if hit is not None:
                g.value, g.snapped = hit[0], (hit[1], hit[2])
            else:
                g.value = v if free else snap(v, self.step)

    def snap_to(self, h: Handle, v: float, to_pixel) -> tuple[float, P3, str] | None:
        """(value, point, what) when moving by ``v`` along the arrow comes within SNAP_PX of putting
        a point of what is dragged level with a snap point (square to the arrow); else None."""
        if not self.anchors or not self.targets:
            return None
        import numpy as np

        d = h.direction
        a = np.asarray(self.anchors, dtype=float) @ np.asarray(d)
        t = np.asarray([q for q, _ in self.targets], dtype=float) @ np.asarray(d)
        cand = (t[None, :] - a[:, None]).ravel()  # each value that puts an anchor level with a target
        k = int(np.argmin(np.abs(cand - v)))
        c = float(cand[k])
        here = to_pixel(_add(h.origin, d, v))
        there = to_pixel(_add(h.origin, d, c))
        if math.hypot(here[0] - there[0], here[1] - there[1]) > SNAP_PX:
            return None
        q, what = self.targets[k % len(self.targets)]
        return c, q, what

    def type_key(self, text: str) -> bool:
        """A key typed while dragging: digits, a point and a minus build a value;
        Backspace takes one off. True when it was used."""
        g = self.drag
        if g is None:
            return False
        if text == "\b":
            g.typed = g.typed[:-1]
            return True
        if text and all(ch in "0123456789.-" for ch in text):
            g.typed += text
            return True
        return False

    @property
    def amount(self) -> float:
        """The drag's value now: the typed one when there is one."""
        g = self.drag
        if g is None:
            return 0.0
        if g.typed:
            try:
                return float(g.typed)
            except ValueError:
                pass
        return g.value

    def readout(self) -> str:
        """What the drag will do, for a label next to the mouse."""
        g = self.drag
        if g is None:
            return ""
        unit = " deg" if g.handle.kind == "TURN" else ""
        what = {"MOVE": "move", "TURN": "turn", "PULL": "pull", "SLIDE": "move faces"}[g.handle.kind]
        axis = "" if g.handle.name == "N" else f" {g.handle.name}"
        typed = " (typed)" if g.typed else ""
        snapped = f" (to {g.snapped[1]})" if g.snapped and not g.typed else ""
        return f"{what}{axis} {fmt_num(round(self.amount, 4))}{unit}{typed}{snapped}"

    def preview(self):
        """(kind, value) for the view to show: ("MOVE", (dx,dy,dz)), ("TURN", (deg, centre, axis)),
        or None."""
        g = self.drag
        if g is None:
            return None
        h, v = g.handle, self.amount
        if h.kind == "TURN":
            return "TURN", (v, h.origin, h.direction)
        return "MOVE", tuple(c * v for c in h.direction)

    def release(self) -> str | None:
        """The command for the drag (None when it did not move)."""
        g, self.drag = self.drag, None
        if g is None:
            return None
        h = g.handle
        v = _amount(g)
        if abs(v) < 1e-9:
            return None
        return command_for(self, h, v)

    def cancel(self) -> None:
        self.drag = None


def _amount(g: Drag) -> float:
    if g.typed:
        try:
            return float(g.typed)
        except ValueError:
            pass
    return g.value


def _num(v: float) -> str:
    return fmt_num(round(v, 6) + 0.0)


def command_for(hs: Handles, h: Handle, v: float) -> str:
    """The one step a drag of handle h by v writes."""
    if h.kind == "MOVE":
        return f"MOVE, {hs.label}, " + ", ".join(_num(c * v) for c in h.direction)
    if h.kind == "TURN":
        c = ", ".join(_num(x) for x in h.origin)
        n = ", ".join(_num(x) for x in h.direction)
        return f"ROTATE, {hs.label}, {_num(v)}, {c}, {n}"
    if h.kind == "PULL":
        return f"PUSHPULL, {_num(v)}"
    return "MOVEFACE, " + ", ".join(_num(c * v) for c in h.direction)


def describe(hs: Handles) -> dict:
    """The handles as data (HANDLES): what each one is and the command a drag writes."""
    rows = []
    for h in hs.items:
        rows.append({"handle": h.name, "kind": h.kind, "origin": [round(c, 6) for c in h.origin],
                     "direction": [round(c, 9) for c in h.direction],
                     "writes": command_for(hs, h, 1.0)})  # for a drag of 1 (mm, or degree for a ring)
    return {"mode": hs.mode, "body": hs.body, "faces": list(hs.faces), "centre": [round(c, 6) for c in hs.centre],
            "step": hs.step, "angle_step": hs.angle_step, "jointed": hs.jointed, "handles": rows}


# ---- snap points -------------------------------------------------------------------------
def _key_points(shape, label: str) -> list[tuple[P3, str]]:
    """Corners, edge middles, circle centres and flat-face middles of a shape."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Plane
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp

    from ..core.model import TopTools_IndexedMapOfShape
    from ..geometry.features import as_edge, as_face, as_vertex

    out: list[tuple[P3, str]] = []
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_VERTEX, m)
    for i in range(1, m.Extent() + 1):
        q = BRep_Tool.Pnt_s(as_vertex(m.FindKey(i)))
        out.append(((q.X(), q.Y(), q.Z()), f"a corner of {label}"))
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_EDGE, m)
    for i in range(1, m.Extent() + 1):
        c = BRepAdaptor_Curve(as_edge(m.FindKey(i)))
        if c.GetType() == GeomAbs_Circle:
            q = c.Circle().Location()
            out.append(((q.X(), q.Y(), q.Z()), f"a circle centre of {label}"))
        q = c.Value((c.FirstParameter() + c.LastParameter()) / 2)
        out.append(((q.X(), q.Y(), q.Z()), f"an edge middle of {label}"))
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, TopAbs_FACE, m)
    for i in range(1, m.Extent() + 1):
        f = as_face(m.FindKey(i))
        if BRepAdaptor_Surface(f).GetType() == GeomAbs_Plane:
            from ..geometry import recognize as rc

            q, _n = rc.face_normal_at_middle(f)
            out.append((tuple(q), f"a face of {label}"))  # type: ignore[arg-type]
    return out


def snap_points(model, hs: Handles) -> tuple[list[P3], list[tuple[P3, str]]]:
    """(anchors, targets): points of what is dragged, and (point, what) on the other shown bodies."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound

    from ..geometry import meshbody

    if hs.mode == "BODY":
        anchors = [q for q, _ in _key_points(model.body(hs.body).shape, "it")]
    else:
        comp, b = TopoDS_Compound(), BRep_Builder()
        b.MakeCompound(comp)
        for g in hs.faces:
            b.Add(comp, model.entity_shape("FACE", g))
        anchors = [q for q, _ in _key_points(comp, "it")]
    hidden = getattr(model, "hidden", set()) or set()
    targets: list[tuple[P3, str]] = []
    for bid, body in model.bodies.items():
        if bid == hs.body or bid in hidden or meshbody.is_mesh(body.shape):
            continue
        targets += _key_points(body.shape, f"body {_name(model, bid)}")
    if len(targets) > MAX_SNAP_POINTS:
        step = len(targets) / MAX_SNAP_POINTS
        targets = [targets[int(i * step)] for i in range(MAX_SNAP_POINTS)]
    seen, uniq = set(), []
    for q in anchors:
        k = tuple(round(c, 6) for c in q)
        if k not in seen:
            seen.add(k)
            uniq.append(q)
    return uniq[:400], targets


# ---- help ------------------------------------------------------------------------------
def _known(model, gid: int) -> bool:
    try:
        model.entity_owner("FACE", gid)
        return True
    except Exception:  # noqa: BLE001 - a stale pick
        return False


def _name(model, bid: int) -> str:
    from ..lang.script import is_ident

    name = model.bodies[bid].name
    if name and name != f"body{bid}" and is_ident(name):
        return name
    return str(bid)


def _bbox(shape) -> tuple[P3, P3]:
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    lo, hi = box.CornerMin(), box.CornerMax()
    return (lo.X(), lo.Y(), lo.Z()), (hi.X(), hi.Y(), hi.Z())


def _seg_px(x: float, y: float, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll < 1e-12 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ll))
    px, py = ax + t * dx, ay + t * dy
    return math.hypot(x - px, y - py)
