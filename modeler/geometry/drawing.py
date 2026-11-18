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
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

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


@dataclass
class View:
    name: str
    visible: list[Poly] = field(default_factory=list)
    hidden: list[Poly] = field(default_factory=list)
    dx: float = 0.0  # where the view sits on the sheet
    dy: float = 0.0

    def bounds(self):
        pts = [q for pl in self.visible + self.hidden for q in pl]
        if not pts:
            return 0.0, 0.0, 0.0, 0.0
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def placed(self, which: str) -> list[Poly]:
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


def _edges_2d(compound, deflection: float) -> list[Poly]:
    """The edges of an HLR result (flat, in the view's x, y) as polylines."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_Line
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
    v.visible = _edges_2d(to.VCompound(), deflection) + _edges_2d(to.OutLineVCompound(), deflection)
    v.hidden = _edges_2d(to.HCompound(), deflection) + _edges_2d(to.OutLineHCompound(), deflection)
    return v


def layout(views: list[View]) -> tuple[float, float, float, float]:
    """Place the views on one sheet (third-angle: top above front, right
    beside it, iso in the free corner, others in a row after), and return
    the sheet's bounds."""
    size = max([max(b[2] - b[0], b[3] - b[1]) for b in (v.bounds() for v in views)] + [1.0])
    gap = 0.2 * size
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
    # the rest in a row to the right
    right = max([v.bounds()[2] + v.dx for v in views if v.name in placed] + [-gap])
    for v in views:
        if v.name not in placed:
            put(v, right + gap, 0.0)
            right += gap + w(v)
            placed.add(v.name)
    del h
    pts = [(v.bounds()[0] + v.dx, v.bounds()[1] + v.dy, v.bounds()[2] + v.dx, v.bounds()[3] + v.dy) for v in views]
    return (min(p[0] for p in pts) - gap / 2, min(p[1] for p in pts) - gap, max(p[2] for p in pts) + gap / 2,
            max(p[3] for p in pts) + gap / 2)


def _f(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".") or "0"


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
        bx0, by0, bx1, _ = v.bounds()
        out.append(f'<text x="{_f((bx0 + bx1) / 2 + v.dx - x0)}" y="{_f(y1 - (by0 + v.dy) + stroke * 14)}" '
                   f'font-family="sans-serif" font-size="{_f(stroke * 10)}" text-anchor="middle">{v.name}</text>')
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
    g(0, "TABLE"); g(2, "LAYER"); g(70, 3)
    for name, colour, lt in (("VISIBLE", 7, "CONTINUOUS"), ("HIDDEN", 8, "HIDDEN"), ("TEXT", 7, "CONTINUOUS")):
        g(0, "LAYER"); g(2, name); g(70, 0); g(62, colour); g(6, lt)
    g(0, "ENDTAB")
    g(0, "ENDSEC")
    g(0, "SECTION"); g(2, "ENTITIES")
    for v in views:
        for layer in ("visible", "hidden"):
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
        g(0, "TEXT"); g(8, "TEXT"); g(10, _f((bx0 + bx1) / 2 + v.dx)); g(20, _f(by0 + v.dy - 2 * hgt)); g(30, 0)
        g(40, _f(hgt)); g(1, v.name); g(72, 1); g(11, _f((bx0 + bx1) / 2 + v.dx)); g(21, _f(by0 + v.dy - 2 * hgt))
        g(31, 0)
    g(0, "ENDSEC")
    g(0, "EOF")
    return "\n".join(L) + "\n"
