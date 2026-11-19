"""2D drawings: bodies seen from the standard directions, with hidden lines,
written as SVG or DXF at true size (1 drawing unit = 1 model unit).

Each view is OCCT's hidden-line removal (HLRBRep) of the shape, looking
along one direction. Visible edges and outlines are solid; hidden ones
dashed. Edges where faces meet smoothly (a fillet's edges) are left out,
as on a usual drawing. A mesh body is projected with the faster polygon
algorithm on its triangles.

The standard sheet places the views the third-angle way: the front view,
the top view above it, the right view beside it, and an isometric view in
the free corner.

Sizes (``dimension``): each model direction gets one overall size, on the
first flat view that shows it (on the standard sheet: width and height on
the front view, depth on the top view), placed outside the view. Whole
circles seen face-on get a diameter, with equal ones counted ("4x  D8"),
each diameter written once on the sheet. Sizes are lines, arrows and text
in their own layer (DIMS in DXF, a "dims" group in SVG).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from html import escape

# view name -> (direction towards the viewer, the drawing's x axis in the model)
VIEWS = {
    "TOP": ((0, 0, 1), (1, 0, 0)),
    "BOTTOM": ((0, 0, -1), (1, 0, 0)),
    "FRONT": ((0, -1, 0), (1, 0, 0)),
    "BACK": ((0, 1, 0), (-1, 0, 0)),
    "RIGHT": ((1, 0, 0), (0, 1, 0)),
    "LEFT": ((-1, 0, 0), (0, -1, 0)),
    "ISO": ((1, -1, 1), (1, 1, 0)),
}
STANDARD = ("FRONT", "TOP", "RIGHT", "ISO")

Poly = list[tuple[float, float]]


# view name -> the model axes along the drawing's x and y (None: not a flat view)
AXES = {"TOP": ("X", "Y"), "BOTTOM": ("X", "Y"), "FRONT": ("X", "Z"), "BACK": ("X", "Z"),
        "RIGHT": ("Y", "Z"), "LEFT": ("Y", "Z"), "ISO": None}
SIZES = ("NONE", "OVERALL", "HOLES", "ALL")


@dataclass
class Dims:
    """Sizes as plain drawing pieces, in the view's own coordinates."""
    lines: list[tuple[tuple[float, float], tuple[float, float]]] = field(default_factory=list)
    arrows: list[tuple[tuple[float, float], tuple[float, float]]] = field(default_factory=list)  # tip, direction
    texts: list[tuple[tuple[float, float], float, str]] = field(default_factory=list)  # centre, degrees, text
    height: float = 1.0  # text height

    def extent(self):
        pts = [q for ln in self.lines for q in ln] + [t[0] for t in self.texts]
        if not pts:
            return None
        h = self.height
        return (min(q[0] for q in pts) - h, min(q[1] for q in pts) - h,
                max(q[0] for q in pts) + h, max(q[1] for q in pts) + h)


@dataclass
class View:
    name: str
    visible: list[Poly] = field(default_factory=list)
    hidden: list[Poly] = field(default_factory=list)
    dx: float = 0.0  # where the view sits on the sheet
    dy: float = 0.0
    circles: list[tuple[float, float, float, float]] = field(default_factory=list)  # visible: cx, cy, r, span
    dims: Dims = field(default_factory=Dims)
    thin: list[Poly] = field(default_factory=list)  # hatching, detail circles: thin solid lines
    notes: list[tuple[float, float, float, str]] = field(default_factory=list)  # x, y, text height, text
    label: str = ""  # the name written under it (default: the view's name)

    @property
    def title(self) -> str:
        return self.label or self.name

    def bounds(self):
        pts = [q for pl in self.visible + self.hidden + self.thin for q in pl]
        if not pts:
            return 0.0, 0.0, 0.0, 0.0
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def placed(self, which: str) -> list[Poly]:  # "visible", "hidden" or "thin"
        return [[(x + self.dx, y + self.dy) for x, y in pl] for pl in getattr(self, which)]


def parse_views(text: str) -> list[str]:
    """'STANDARD', 'FRONT', 'TOP+FRONT+RIGHT' or 'TOP FRONT' -> view names."""
    words = [w for w in text.replace("+", " ").replace("/", " ").upper().split() if w]
    out: list[str] = []
    for w in words or ["STANDARD"]:
        if w in ("STANDARD", "ALL", "SHEET"):
            out += [v for v in STANDARD if v not in out]
        elif w in VIEWS:
            if w not in out:
                out.append(w)
        else:
            raise ValueError(f"unknown view {w}: use STANDARD or {', '.join(VIEWS)} (joined with +)")
    return out


def _edges_2d(compound, deflection: float, circles: list | None = None) -> list[Poly]:
    """The edges of an HLR result (flat, in the view's x, y) as polylines;
    circle arcs are also added to ``circles`` (cx, cy, r, span) if given."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    out: list[Poly] = []
    if compound is None or compound.IsNull():
        return out
    ex = TopExp_Explorer(compound, TopAbs_EDGE)
    while ex.More():
        try:
            e = TopoDS.Edge_s(ex.Current())
        except AttributeError:
            e = TopoDS.Edge(ex.Current())
        ex.Next()
        try:
            c = BRepAdaptor_Curve(e)
        except Exception:  # an edge without a curve: nothing to draw
            continue
        if circles is not None and c.GetType() == GeomAbs_Circle:
            ci = c.Circle()
            circles.append((ci.Location().X(), ci.Location().Y(), ci.Radius(),
                            abs(c.LastParameter() - c.FirstParameter())))
        if c.GetType() == GeomAbs_Line:
            a, b = c.Value(c.FirstParameter()), c.Value(c.LastParameter())
            pl = [(a.X(), a.Y()), (b.X(), b.Y())]
        else:
            d = GCPnts_QuasiUniformDeflection(c, deflection)
            if not d.IsDone() or d.NbPoints() < 2:
                continue
            pl = []
            for i in range(1, d.NbPoints() + 1):
                q = d.Value(i)
                pl.append((q.X(), q.Y()))
        if len(pl) >= 2 and any(math.dist(pl[0], q) > 1e-9 for q in pl[1:]):
            out.append(pl)
    return out


def _projector(name: str):
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.HLRAlgo import HLRAlgo_Projector

    z, x = VIEWS[name]
    return HLRAlgo_Projector(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*z), gp_Dir(*x)))


def project(shape, name: str, deflection: float, mesh: bool = False) -> View:
    """One view of a shape: its visible and hidden edges, flat."""
    v = View(name)
    if mesh:
        from OCP.HLRBRep import HLRBRep_PolyAlgo, HLRBRep_PolyHLRToShape

        algo = HLRBRep_PolyAlgo()
        algo.Load(shape)
        algo.Projector(_projector(name))
        algo.Update()
        to = HLRBRep_PolyHLRToShape()
        to.Update(algo)
    else:
        from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape

        algo = HLRBRep_Algo()
        algo.Add(shape)
        algo.Projector(_projector(name))
        algo.Update()
        algo.Hide()
        to = HLRBRep_HLRToShape(algo)
    v.visible = (_edges_2d(to.VCompound(), deflection, v.circles)
                 + _edges_2d(to.OutLineVCompound(), deflection, v.circles))
    v.hidden = _edges_2d(to.HCompound(), deflection) + _edges_2d(to.OutLineHCompound(), deflection)
    return v


def _n(v: float) -> str:
    """A size as written on the drawing: at most two decimals."""
    return f"{v:.2f}".rstrip("0").rstrip(".") or "0"


def _whole_circles(v: View, tol: float) -> list[tuple[float, float, float]]:
    """The view's visible circles that go all the way round (arcs of one circle joined)."""
    span: dict[tuple[int, int, int], list] = {}
    for cx, cy, r, a in v.circles:
        k = (round(cx / tol), round(cy / tol), round(r / tol))
        got = span.setdefault(k, [cx, cy, r, 0.0])
        got[3] += a
    return [(cx, cy, r) for cx, cy, r, a in span.values() if a >= 2 * math.pi * 0.99]


def _linear(d: Dims, a, b, vertical: bool, at: float, text: str) -> None:
    """A size between points a and b, its line at x = at (vertical) or y = at."""
    h = d.height
    i = 0 if vertical else 1  # the coordinate the extension lines run along
    for q in (a, b):
        sgn = 1.0 if at > q[i] else -1.0
        p0, p1 = list(q), list(q)
        p0[i] += sgn * 0.4 * h
        p1[i] = at + sgn * 0.6 * h
        d.lines.append((tuple(p0), tuple(p1)))
    pa, pb = list(a), list(b)
    pa[i] = pb[i] = at
    d.lines.append((tuple(pa), tuple(pb)))
    j = 1 - i
    sgn = 1.0 if pb[j] > pa[j] else -1.0
    da, db = [0.0, 0.0], [0.0, 0.0]
    da[j], db[j] = -sgn, sgn
    d.arrows += [(tuple(pa), tuple(da)), (tuple(pb), tuple(db))]
    mid = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2]
    out = 1.0 if at > a[i] else -1.0
    mid[i] += out * 0.75 * h
    d.texts.append((tuple(mid), 90.0 if vertical else 0.0, text))


LEADER_ANGLES = (45, 135, 30, 150, 60, 120, 15, 165)


def _diameter(d: Dims, circle, k: int, text: str, taken: list) -> None:
    """A short leader from the circle to a label on a shoulder. Each size of
    circle in a view leaves at its own angle, so leaders of circles around one
    centre do not lie on top of each other; a label that would cover another
    one moves further out."""
    cx, cy, r = circle
    h = d.height
    ang = math.radians(LEADER_ANGLES[k % len(LEADER_ANGLES)])
    ux, uy = math.cos(ang), math.sin(ang)
    tip = (cx + r * ux, cy + r * uy)
    w = 0.62 * h * len(text)
    side = 1.0 if ux >= 0 else -1.0
    for j in range(10):
        reach = (2.0 + 1.3 * j) * h
        knee = (tip[0] + reach * ux, tip[1] + reach * uy)
        lo, hi = sorted((knee[0], knee[0] + side * w))
        rect = (lo, knee[1] - 0.1 * h, hi, knee[1] + 1.2 * h)
        if not any(rect[0] < t[2] and t[0] < rect[2] and rect[1] < t[3] and t[1] < rect[3] for t in taken):
            break
    taken.append(rect)
    end = (knee[0] + side * w, knee[1])
    d.lines += [(tip, knee), (knee, end)]
    d.arrows.append((tip, (-ux, -uy)))
    d.texts.append(((knee[0] + side * w / 2, knee[1] + 0.6 * h), 0.0, text))


def dimension(views: list[View], which: str = "ALL", extent: dict[str, float] | None = None) -> int:
    """Add sizes to the views (see the module notes); returns how many.
    ``extent`` gives the exact model size along X, Y and Z, written in place
    of the drawn size (curves are drawn as short lines, a few hundredths short)."""
    which = which.upper()
    if which not in SIZES:
        raise ValueError(f"unknown sizes {which}: use {', '.join(SIZES)}")
    boxes = [v.bounds() for v in views]
    size = max([max(b[2] - b[0], b[3] - b[1]) for b in boxes] + [1e-9])
    h = size / 30
    tol = size * 1e-6
    axes_done: set[str] = set()
    dia_done: set[int] = set()
    count = 0
    for v, (x0, y0, x1, y1) in zip(views, boxes):
        v.dims = d = Dims(height=h)
        axes = AXES.get(v.name)
        if not axes or not (v.visible or v.hidden):
            continue
        if which in ("OVERALL", "ALL"):
            ax, ay = axes
            if ax not in axes_done and x1 - x0 > tol:
                _linear(d, (x0, y0), (x1, y0), False, y0 - 2.5 * h, _n((extent or {}).get(ax, x1 - x0)))
                axes_done.add(ax)
                count += 1
            if ay not in axes_done and y1 - y0 > tol:
                _linear(d, (x0, y0), (x0, y1), True, x0 - 2.5 * h, _n((extent or {}).get(ay, y1 - y0)))
                axes_done.add(ay)
                count += 1
        if which in ("HOLES", "ALL"):
            by_r: dict[int, list[tuple[float, float, float]]] = {}
            for cx, cy, r in _whole_circles(v, tol):
                by_r.setdefault(round(2 * r / max(tol, 1e-9) / 1000), []).append((cx, cy, r))
            k = 0
            taken: list = []
            for key in sorted(by_r, key=lambda q: -by_r[q][0][2]):
                if key in dia_done or k >= 12:
                    continue
                dia_done.add(key)
                ang = math.radians(LEADER_ANGLES[k % len(LEADER_ANGLES)])
                pts = sorted(by_r[key], key=lambda q: q[0] * math.cos(ang) + q[1] * math.sin(ang))
                n = len(pts)
                _diameter(d, pts[-1], k, (f"{n}x " if n > 1 else "") + "\u00d8" + _n(2 * pts[-1][2]), taken)
                k += 1
                count += 1
    return count


def add_notes(views: list[View], notes, size: float) -> int:
    """Put the model's notes (NOTE) on the plain views: the text where its point falls in the view, a thin
    leader to its anchor, and a size's line with end marks. Sections and details are left alone.
    Returns how many notes were placed in at least one view."""
    from OCP.gp import gp_Pnt, gp_Pnt2d

    placed: set[int] = set()
    sized = [v.dims.height for v in views if v.dims.lines or v.dims.texts]
    h = max(sized) if sized else size / 70  # one text height on every view
    for v in views:
        if v.name not in VIEWS:
            continue
        pr = _projector(v.name)

        def flat(q):
            out = gp_Pnt2d()
            pr.Project(gp_Pnt(*q), out)
            return out.X(), out.Y()

        boxes: list[tuple[float, float, float, float]] = []  # what is placed on this view so far
        dh = v.dims.height
        for (cx, cy), deg, text in v.dims.texts:  # keep clear of the sizes' numbers
            tw, th = 0.55 * dh * len(text) + 0.4 * dh, 1.3 * dh
            if abs(deg) > 45:
                tw, th = th, tw
            boxes.append((cx - tw / 2, cy - th / 2, cx + tw / 2, cy + th / 2))

        def clear_spot(x, y, w, hh):
            """Move (x, y) up until a w x hh box there misses the boxes placed so far."""
            for _ in range(40):
                box = (x - w / 2, y - hh / 2, x + w / 2, y + hh / 2)
                if not any(box[0] < o[2] and o[0] < box[2] and box[1] < o[3] and o[1] < box[3] for o in boxes):
                    boxes.append(box)
                    return x, y
                y += 0.6 * hh
            boxes.append((x - w / 2, y - hh / 2, x + w / 2, y + hh / 2))
            return x, y

        def from_edge(x, y, w, hh, tx, ty):
            """Where a leader from the box at (x, y) towards (tx, ty) leaves the box."""
            dx, dy = tx - x, ty - y
            t = min([abs(w / 2 / dx) if abs(dx) > 1e-12 else math.inf,
                     abs(hh / 2 / dy) if abs(dy) > 1e-12 else math.inf, 1.0])
            return x + dx * t, y + dy * t

        for k, n in enumerate(notes):
            x, y = flat(n.at)
            fr = getattr(n, "frame", None)
            if n.span is not None:
                a, b = flat(n.span[0]), flat(n.span[1])
                if math.dist(a, b) < 1e-9 * max(size, 1.0):
                    continue  # seen end on: the size says nothing in this view
                v.thin.append([a, b])
                dx, dy = b[0] - a[0], b[1] - a[1]
                ln = math.hypot(dx, dy)
                tx, ty = -dy / ln * h * 0.6, dx / ln * h * 0.6
                for e in (a, b):
                    v.thin.append([(e[0] - tx, e[1] - ty), (e[0] + tx, e[1] + ty)])
                x, y = (a[0] + b[0]) / 2 + tx, (a[1] + b[1]) / 2 + ty
            if fr is not None:
                from . import tolerances as tl

                w, hh = tl.frame_size(fr, h)
            else:
                rows = n.text.split("\n")
                w, hh = 0.55 * h * max(len(r) for r in rows) + 0.4 * h, 1.3 * h * len(rows)
            if n.anchor is not None and n.span is None and math.dist((x, y), flat(n.anchor)) < 0.02 * size:
                continue  # its leader runs straight at the eye: this view does not show the note
            x, y = clear_spot(x, y, w, hh)
            if n.anchor is not None:
                ax, ay = flat(n.anchor)
                v.thin.append([from_edge(x, y, w, hh, ax, ay), (ax, ay)])
            if fr is not None:
                lines, texts = tl.frame_lines(fr, x, y, h)
                v.thin.extend(lines)
                v.notes.extend((tx, ty, h, t) for tx, ty, t in texts)
                if fr.kind == "DATUM" and n.anchor is not None:  # the datum triangle on the face
                    ax, ay = flat(n.anchor)
                    dx, dy = ax - x, ay - y
                    ln = math.hypot(dx, dy)
                    if ln > 1e-12:
                        ux, uy = dx / ln, dy / ln
                        s = 0.6 * h
                        b0 = (ax - ux * s * 1.2 - uy * s, ay - uy * s * 1.2 + ux * s)
                        b1 = (ax - ux * s * 1.2 + uy * s, ay - uy * s * 1.2 - ux * s)
                        v.thin.append([(ax, ay), b0, b1, (ax, ay)])
                placed.add(k)
                continue
            v.notes.append((x, y, h, n.text))
            placed.add(k)
    return len(placed)


def layout(views: list[View]) -> tuple[float, float, float, float]:
    """Place the views on one sheet (third-angle: top above front, right
    beside it, iso in the free corner, others in a row after), and return
    the sheet's bounds."""
    size = max([max(b[2] - b[0], b[3] - b[1]) for b in (v.bounds() for v in views)] + [1.0])
    gap = 0.2 * size + max([4 * v.dims.height for v in views if v.dims.lines] + [0.0])
    by = {v.name: v for v in views}

    def put(v, left, bottom):
        x0, y0, _, _ = v.bounds()
        v.dx, v.dy = left - x0, bottom - y0

    def w(v):
        b = v.bounds()
        return b[2] - b[0]

    def h(v):
        b = v.bounds()
        return b[3] - b[1]

    front = by.get("FRONT")
    placed = set()
    if front is not None:
        put(front, 0.0, 0.0)
        placed.add("FRONT")
        fx0, fy0, fx1, fy1 = (b + d for b, d in zip(front.bounds(), (front.dx, front.dy, front.dx, front.dy)))
        if "TOP" in by:  # above the front view, lined up with it
            t = by["TOP"]
            x0, y0, _, _ = t.bounds()
            t.dx, t.dy = front.dx, fy1 + gap - y0
            placed.add("TOP")
        if "RIGHT" in by:  # beside it, at the same height
            r = by["RIGHT"]
            x0, y0, _, _ = r.bounds()
            r.dx, r.dy = fx1 + gap - x0, front.dy
            placed.add("RIGHT")
        if "ISO" in by and "TOP" in by and "RIGHT" in by:
            i = by["ISO"]
            put(i, by["RIGHT"].bounds()[0] + by["RIGHT"].dx, by["TOP"].bounds()[1] + by["TOP"].dy)
            placed.add("ISO")
    # the rest in a row to the right, along the bottom: past the views that reach down into that row
    band = max([h(v) for v in views if v.name not in placed] + [0.0])

    def low_enough(v):
        b = v.bounds()
        return b[1] + v.dy < band + gap / 2

    right = max([v.bounds()[2] + v.dx for v in views if v.name in placed and low_enough(v)] + [-gap])
    for v in views:
        if v.name not in placed:
            put(v, right + gap, 0.0)
            right += gap + w(v)
            placed.add(v.name)
    pts = [(v.bounds()[0] + v.dx, v.bounds()[1] + v.dy, v.bounds()[2] + v.dx, v.bounds()[3] + v.dy) for v in views]
    pts += [(e[0] + v.dx, e[1] + v.dy, e[2] + v.dx, e[3] + v.dy) for v in views
            for e in [v.dims.extent()] if e is not None]
    return (min(p[0] for p in pts) - gap / 2, min(p[1] for p in pts) - gap, max(p[2] for p in pts) + gap / 2,
            max(p[3] for p in pts) + gap / 2)


def _f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


def _arrow_shapes(d: Dims):
    """Each arrow as (tip, (wing, wing)): a filled triangle, one text height long."""
    out = []
    for (tx, ty), (ux, uy) in d.arrows:
        ln = d.height
        bx, by = tx - ux * ln, ty - uy * ln
        px, py = -uy * 0.3 * ln, ux * 0.3 * ln
        out.append(((tx, ty), ((bx + px, by + py), (bx - px, by - py))))
    return out


def svg(views: list[View], sheet, units: str = "mm") -> str:
    """An SVG sheet, sized in the model's units (mm, cm or in; other units as px)."""
    x0, y0, x1, y1 = sheet
    W, H = x1 - x0, y1 - y0
    unit = {"MM": "mm", "CM": "cm", "IN": "in"}.get(units.upper(), "")
    stroke = max(W, H) / 600

    def path(pl):
        return "M" + " L".join(f"{_f(x - x0)},{_f(y1 - y)}" for x, y in pl)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{_f(W)}{unit}" height="{_f(H)}{unit}" '
           f'viewBox="0 0 {_f(W)} {_f(H)}">',
           f'<rect width="{_f(W)}" height="{_f(H)}" fill="white"/>']
    for v in views:
        out.append(f'<g id="{v.name.lower()}">')
        if v.hidden:
            out.append(f'<path d="{" ".join(path(pl) for pl in v.placed("hidden"))}" fill="none" stroke="#777" '
                       f'stroke-width="{_f(stroke * 0.6)}" stroke-dasharray="{_f(stroke * 6)},{_f(stroke * 3)}" '
                       'stroke-linecap="round"/>')
        if v.visible:
            out.append(f'<path d="{" ".join(path(pl) for pl in v.placed("visible"))}" fill="none" stroke="black" '
                       f'stroke-width="{_f(stroke)}" stroke-linecap="round" stroke-linejoin="round"/>')
        if v.thin:
            out.append(f'<path d="{" ".join(path(pl) for pl in v.placed("thin"))}" fill="none" stroke="black" '
                       f'stroke-width="{_f(stroke * 0.4)}"/>')
        for nx, ny, nh, nt in v.notes:
            out.append(f'<text x="{_f(nx + v.dx - x0)}" y="{_f(y1 - (ny + v.dy))}" font-family="sans-serif" '
                       f'font-size="{_f(nh)}" text-anchor="middle" dominant-baseline="middle">{escape(nt)}</text>')
        bx0, by0, bx1, _ = v.bounds()
        label_y = by0 + v.dy - stroke * 14
        e = v.dims.extent()
        if e is not None and e[1] + v.dy < by0 + v.dy:  # below the sizes, not on them
            label_y = e[1] + v.dy - stroke * 10
        out.append(f'<text x="{_f((bx0 + bx1) / 2 + v.dx - x0)}" y="{_f(y1 - label_y)}" '
                   f'font-family="sans-serif" font-size="{_f(stroke * 10)}" text-anchor="middle">{escape(v.title)}</text>')
        out.append("</g>")
        d = v.dims
        if d.lines:
            def at(q, v=v):
                return f"{_f(q[0] + v.dx - x0)},{_f(y1 - (q[1] + v.dy))}"

            out.append(f'<g id="{v.name.lower()}-dims" class="dims">')
            out.append(f'<path d="{" ".join("M" + at(a) + " L" + at(b) for a, b in d.lines)}" fill="none" '
                       f'stroke="#1a4fa0" stroke-width="{_f(stroke * 0.5)}"/>')
            for tip, tri in _arrow_shapes(d):
                out.append(f'<path d="M{at(tip)} L{at(tri[0])} L{at(tri[1])} Z" fill="#1a4fa0"/>')
            for (cx, cy), ang, text in d.texts:
                rot = f' transform="rotate({_f(-ang)} {at((cx, cy)).replace(",", " ")})"' if ang else ""
                out.append(f'<text x="{at((cx, cy)).split(",")[0]}" y="{at((cx, cy)).split(",")[1]}"{rot} '
                           f'font-family="sans-serif" font-size="{_f(d.height)}" fill="#1a4fa0" '
                           f'text-anchor="middle" dominant-baseline="middle">{escape(text)}</text>')
            out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def dxf(views: list[View], sheet, units: str = "mm") -> str:
    """An ASCII DXF (R12 entities, readable by any CAD program) at true size,
    with layers VISIBLE, HIDDEN (dashed) and TEXT."""
    x0, y0, x1, y1 = sheet
    ins = {"MM": 4, "CM": 5, "M": 6, "IN": 1, "FT": 2}.get(units.upper(), 0)
    L: list[str] = []

    def g(code, value):
        L.append(str(code))
        L.append(str(value))

    g(0, "SECTION"); g(2, "HEADER")
    g(9, "$ACADVER"); g(1, "AC1009")
    g(9, "$INSUNITS"); g(70, ins)
    g(9, "$EXTMIN"); g(10, _f(x0)); g(20, _f(y0))
    g(9, "$EXTMAX"); g(10, _f(x1)); g(20, _f(y1))
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "TABLES")
    g(0, "TABLE"); g(2, "LTYPE"); g(70, 2)
    g(0, "LTYPE"); g(2, "CONTINUOUS"); g(70, 0); g(3, "Solid line"); g(72, 65); g(73, 0); g(40, 0.0)
    dash = max(x1 - x0, y1 - y0) / 100
    g(0, "LTYPE"); g(2, "HIDDEN"); g(70, 0); g(3, "Hidden __ __ __"); g(72, 65); g(73, 2)
    g(40, _f(dash * 1.5)); g(49, _f(dash)); g(49, _f(-dash * 0.5))
    g(0, "ENDTAB")
    has_dims = any(v.dims.lines for v in views)
    layers = [("VISIBLE", 7, "CONTINUOUS"), ("HIDDEN", 8, "HIDDEN"), ("TEXT", 7, "CONTINUOUS")]
    if any(v.thin for v in views):
        layers.append(("THIN", 7, "CONTINUOUS"))
    if has_dims:
        layers.append(("DIMS", 5, "CONTINUOUS"))
    g(0, "TABLE"); g(2, "LAYER"); g(70, len(layers))
    for name, colour, lt in layers:
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, colour); g(6, lt)
    g(0, "ENDTAB")
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")
    for v in views:
        for layer in ("visible", "hidden", "thin"):
            name = layer.upper()
            for pl in v.placed(layer):
                if len(pl) == 2:
                    (a, b), (c, d) = pl
                    g(0, "LINE"); g(8, name); g(10, _f(a)); g(20, _f(b)); g(30, 0); g(11, _f(c)); g(21, _f(d)); g(31, 0)
                else:
                    g(0, "POLYLINE"); g(8, name); g(66, 1); g(10, 0); g(20, 0); g(30, 0); g(70, 0)
                    for a, b in pl:
                        g(0, "VERTEX"); g(8, name); g(10, _f(a)); g(20, _f(b)); g(30, 0)
                    g(0, "SEQEND"); g(8, name)
        bx0, by0, bx1, _ = v.bounds()
        hgt = max(x1 - x0, y1 - y0) / 60
        ly = by0 + v.dy - 2 * hgt
        e = v.dims.extent()
        if e is not None and e[1] + v.dy < by0 + v.dy:
            ly = e[1] + v.dy - 1.5 * hgt
        g(0, "TEXT"); g(8, "TEXT"); g(10, _f((bx0 + bx1) / 2 + v.dx)); g(20, _f(ly)); g(30, 0)
        g(40, _f(hgt)); g(1, v.title); g(72, 1); g(11, _f((bx0 + bx1) / 2 + v.dx)); g(21, _f(ly))
        g(31, 0)
        for nx, ny, nh, nt in v.notes:
            g(0, "TEXT"); g(8, "TEXT"); g(10, _f(nx + v.dx)); g(20, _f(ny + v.dy)); g(30, 0)
            g(40, _f(nh)); g(1, nt); g(72, 1); g(73, 2); g(11, _f(nx + v.dx)); g(21, _f(ny + v.dy)); g(31, 0)
        d = v.dims
        for (a, b), (c, e2) in d.lines:
            g(0, "LINE"); g(8, "DIMS"); g(10, _f(a + v.dx)); g(20, _f(b + v.dy)); g(30, 0)
            g(11, _f(c + v.dx)); g(21, _f(e2 + v.dy)); g(31, 0)
        for (tx, ty), ((ax, ay), (bx, by)) in _arrow_shapes(d):
            g(0, "SOLID"); g(8, "DIMS")
            for code, (qx, qy) in ((10, (tx, ty)), (11, (ax, ay)), (12, (bx, by)), (13, (bx, by))):
                g(code, _f(qx + v.dx)); g(code + 10, _f(qy + v.dy)); g(code + 20, 0)
        for (cx, cy), ang, text in d.texts:
            g(0, "TEXT"); g(8, "DIMS"); g(10, _f(cx + v.dx)); g(20, _f(cy + v.dy)); g(30, 0)
            g(40, _f(d.height)); g(1, text.replace("\u00d8", "%%c"))
            if ang:
                g(50, _f(ang))
            g(72, 1); g(73, 2); g(11, _f(cx + v.dx)); g(21, _f(cy + v.dy)); g(31, 0)
    g(0, "ENDSEC")
    g(0, "EOF")
    return "\n".join(L) + "\n"
