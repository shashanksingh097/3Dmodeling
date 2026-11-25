"""Drawing sheets: section and detail views, and a paper sheet with a frame
and a title block, written as PDF or SVG (geometry/drawing.py makes the views).

* Section ``X 30``: the part cut by the plane x = 30. The part on the near
  side is taken away and the rest is seen square-on, its cut faces hatched
  at 45 degrees. X cuts are seen from +X (as the right view), Y cuts from
  -Y (as the front view), Z cuts from +Z (as the top view).
* Detail ``FRONT 20 0 5 8 3``: the front view around the model point
  (20, 0, 5), within 8 of it, drawn 3 times bigger, with a circle and a
  letter where it was taken.
* Paper: A4 to A0 landscape. The views keep their places from
  drawing.layout and are scaled by the largest usual scale (10:1 ... 1:100)
  that fits above the title block. The title block shows the properties set
  with PROPERTY (TITLE, NUMBER, MATERIAL, AUTHOR, COMPANY, REVISION, DATE)
  with the scale, the units and the projection.

The PDF is written by hand (PDF 1.4, a page per sheet, lines and Helvetica text), so
nothing beyond the standard library is needed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import drawing as dr

PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0),
         "A0": (1189.0, 841.0)}
SCALES = [10, 5, 2, 1, 1 / 2, 1 / 5, 1 / 10, 1 / 20, 1 / 50, 1 / 100, 1 / 200, 1 / 500, 1 / 1000]
MARGIN = 10.0
TITLE_W, TITLE_H = 180.0, 40.0
CUT_VIEW = {"X": "RIGHT", "Y": "FRONT", "Z": "TOP"}  # the view a section on that axis is seen as


class SheetError(ValueError):
    pass


def scale_text(s: float) -> str:
    return f"{round(s):g}:1" if s >= 1 else f"1:{round(1 / s):g}"


def parse_scale(text: str) -> float:
    """'1:2', '2:1', '0.5', '' (0: choose) -> the factor."""
    t = text.strip().strip('"')
    if not t or t.upper() == "AUTO":
        return 0.0
    try:
        if ":" in t:
            a, b = (float(x) for x in t.split(":"))
            v = a / b
        else:
            v = float(t)
    except (ValueError, ZeroDivisionError):
        raise SheetError(f"the scale is like 1:2 or 2:1, got {text!r}") from None
    if v <= 0:
        raise SheetError("the scale must be positive")
    return v


# ---- a view's frame ------------------------------------------------------------------------


def _axes(name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    z, x = dr.VIEWS[name]
    z = np.array(z, float) / np.linalg.norm(z)
    x = np.array(x, float) / np.linalg.norm(x)
    return x, np.cross(z, x), z


def to_view(name: str, p) -> tuple[float, float]:
    x, y, _ = _axes(name)
    p = np.asarray(p, float)
    return float(p @ x), float(p @ y)


# ---- sections ------------------------------------------------------------------------------


def parse_cut(text: str) -> tuple[str, float]:
    w = text.replace(",", " ").replace("=", " ").split()
    if len(w) != 2 or w[0].upper() not in CUT_VIEW:
        raise SheetError(f"a section is an axis and a place, like \"X 30\" or \"Y=0\"; got {text!r}")
    try:
        return w[0].upper(), float(w[1])
    except ValueError:
        raise SheetError(f"a section is an axis and a place, like \"X 30\"; got {text!r}") from None


def _half_space(shape, axis: str, value: float):
    """The solid part of the model kept for a section along ``axis`` at ``value``."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    from . import contact as ct

    b = ct.box_of(shape)
    big = 2 * max(b[3] - b[0], b[4] - b[1], b[5] - b[2]) + 10
    lo = [b[0] - big, b[1] - big, b[2] - big]
    hi = [b[3] + big, b[4] + big, b[5] + big]
    k = "XYZ".index(axis)
    if axis == "Y":  # seen from -Y: keep y >= value
        lo[k] = value
    else:  # seen from +X / +Z: keep the part below the plane
        hi[k] = value
    if hi[k] <= b[k] or lo[k] >= b[k + 3]:
        raise SheetError(f"the plane {axis} = {value:g} misses the part ({axis} from {b[k]:.4g} to {b[k + 3]:.4g})")
    box = BRepPrimAPI_MakeBox(gp_Pnt(*lo), gp_Pnt(*hi)).Shape()
    op = BRepAlgoAPI_Common(shape, box)
    if not op.IsDone():
        raise SheetError("could not cut the part")
    return op.Shape()


def _cut_loops(kept, axis: str, value: float, name: str, tol: float) -> list[np.ndarray]:
    """The outlines (2D, in the view) of the kept part's faces lying on the cutting plane."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    from . import milling

    as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    as_wire = getattr(TopoDS, "Wire_s", None) or TopoDS.Wire
    k = "XYZ".index(axis)
    loops = []
    ex = TopExp_Explorer(kept, TopAbs_FACE)
    while ex.More():
        f = as_face(ex.Current())
        ex.Next()
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            continue
        pl = s.Plane()
        d, o = pl.Axis().Direction(), pl.Location()
        n = np.array([d.X(), d.Y(), d.Z()])
        if abs(abs(n[k]) - 1) > 1e-7 or abs([o.X(), o.Y(), o.Z()][k] - value) > tol:
            continue
        wx = TopExp_Explorer(f, TopAbs_WIRE)
        while wx.More():
            pts = milling.wire_points(as_wire(wx.Current()), tol=max(tol, 1e-4) * 50)
            wx.Next()
            if len(pts) >= 3:
                loops.append(np.array([to_view(name, q) for q in pts]))
    return loops


def hatch(loops: list[np.ndarray], spacing: float) -> list[dr.Poly]:
    """45-degree lines inside the loops (even-odd: holes stay clear)."""
    if not loops:
        return []
    d = np.array([1.0, 1.0]) / math.sqrt(2)  # along the lines
    nrm = np.array([-1.0, 1.0]) / math.sqrt(2)  # across them
    allp = np.concatenate(loops)
    c0, c1 = float((allp @ nrm).min()), float((allp @ nrm).max())
    segs = [(lp[i], lp[(i + 1) % len(lp)]) for lp in loops for i in range(len(lp))]
    out = []
    c = c0 + spacing / 2
    while c < c1:
        ts = []
        for a, b in segs:
            sa, sb = float(a @ nrm) - c, float(b @ nrm) - c
            if (sa > 0) == (sb > 0) or sa == sb:
                continue
            q = a + (b - a) * (sa / (sa - sb))
            ts.append(float(q @ d))
        ts.sort()
        for t0, t1 in zip(ts[0::2], ts[1::2]):
            if t1 - t0 > 1e-9:
                base = c * nrm
                out.append([tuple(base + t0 * d), tuple(base + t1 * d)])
        c += spacing
    return out


def section_view(shape, axis: str, value: float, letter: str, deflection: float) -> dr.View:
    from . import contact as ct

    name = CUT_VIEW[axis]
    kept = _half_space(shape, axis, value)
    v = dr.project(kept, name, deflection)
    v.name = f"SECTION {letter}-{letter}"
    v.hidden = []  # a section shows what is cut and what is behind, not hidden edges
    b = ct.box_of(shape)
    size = max(b[3] - b[0], b[4] - b[1], b[5] - b[2])
    loops = _cut_loops(kept, axis, value, name, 1e-6 * max(size, 1.0))
    if not loops:
        raise SheetError(f"the plane {axis} = {value:g} does not cut through solid material")
    v.thin = hatch(loops, size / 40)
    return v


def section_line(view: dr.View, axis: str, value: float, letter: str) -> bool:
    """Draw where a section is taken on a view that shows the plane edge-on: a thin line with the
    letters at its ends. False when this view does not show it edge-on."""
    axes = dr.AXES.get(view.name)
    if not axes or axis not in axes:
        return False
    x0, y0, x1, y1 = view.bounds()
    vertical = axes[0] == axis
    # where the plane lies along that drawing axis
    probe = [0.0, 0.0, 0.0]
    probe["XYZ".index(axis)] = value
    u, w = to_view(view.name, probe)
    at = u if vertical else w
    ext = 0.08 * max(x1 - x0, y1 - y0, 1e-9)
    h = 0.06 * max(x1 - x0, y1 - y0, 1e-9)
    if vertical:
        a, b = (at, y0 - ext), (at, y1 + ext)
        view.notes += [(at, y0 - ext - h, h, letter), (at, y1 + ext + h, h, letter)]
    else:
        a, b = (x0 - ext, at), (x1 + ext, at)
        view.notes += [(x0 - ext - h, at, h, letter), (x1 + ext + h, at, h, letter)]
    # a chain line: long dashes as short separate pieces
    n = 15
    for k in range(n):
        t0, t1 = k / n, (k + 0.7) / n
        view.thin.append([(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                          (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)])
    return True


# ---- details -------------------------------------------------------------------------------


def parse_detail(text: str) -> tuple[str, tuple, float, float]:
    w = text.replace(",", " ").split()
    if len(w) != 6 or w[0].upper() not in dr.VIEWS or w[0].upper() == "ISO":
        raise SheetError(f"a detail is a flat view, a model point, a radius and how much bigger: "
                         f"\"FRONT 20 0 5 8 3\"; got {text!r}")
    try:
        x, y, z, r, k = (float(q) for q in w[1:])
    except ValueError:
        raise SheetError(f"a detail is like \"FRONT 20 0 5 8 3\"; got {text!r}") from None
    if r <= 0 or k <= 0:
        raise SheetError("the detail's radius and scale must be positive")
    return w[0].upper(), (x, y, z), r, k


def _clip(pl: dr.Poly, c: np.ndarray, r: float, step: float) -> list[dr.Poly]:
    """The pieces of a polyline inside a circle (split finely enough to follow the circle)."""
    pts = []
    for a, b in zip(pl[:-1], pl[1:]):
        a, b = np.array(a), np.array(b)
        n = max(1, int(np.linalg.norm(b - a) / step))
        pts += [a + (b - a) * t for t in np.linspace(0, 1, n + 1)[:-1]]
    pts.append(np.array(pl[-1]))
    out, run = [], []
    for q in pts:
        if np.linalg.norm(q - c) <= r:
            run.append(tuple(q))
        elif run:
            if len(run) >= 2:
                out.append(run)
            run = []
    if len(run) >= 2:
        out.append(run)
    return out


def detail_view(parent: dr.View, point, r: float, k: float, letter: str) -> dr.View:
    c = np.array(to_view(parent.name, point))
    v = dr.View(f"DETAIL {letter}", label=f"DETAIL {letter} ({scale_text(k)})")
    step = r / 60

    def grow(pl):
        return [tuple((np.array(q) - c) * k) for q in pl]

    for which in ("visible", "hidden"):
        got = [grow(piece) for pl in getattr(parent, which) for piece in _clip(pl, c, r, step)]
        setattr(v, which, got)
    if not v.visible and not v.hidden:
        raise SheetError(f"nothing of the {parent.name.lower()} view lies within {r:g} of that point")
    ring = [(r * k * math.cos(t), r * k * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 97)]
    v.thin.append(ring)
    parent.thin.append([(c[0] + r * math.cos(t), c[1] + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 97)])
    parent.notes.append((c[0] + r * 0.85, c[1] + r * 1.15, r * 0.35, letter))
    return v


# ---- the paper -----------------------------------------------------------------------------


@dataclass
class Page:
    """Everything on the paper, in mm from its bottom-left corner."""

    width: float
    height: float
    thick: list = field(default_factory=list)  # polylines
    thin: list = field(default_factory=list)
    dashed: list = field(default_factory=list)
    dims: list = field(default_factory=list)  # thin blue lines
    fills: list = field(default_factory=list)  # triangles (blue)
    texts: list = field(default_factory=list)  # (x, y, height, text, anchor "l"/"m"/"r", colour "k"/"b", angle)
    scale: float = 1.0
    paper: str = "A4"
    warnings: list = field(default_factory=list)
    boxes: list = field(default_factory=list)  # (view title, x0, y0, x1, y1) on the paper, for the sheet window


def fit(sheet_bounds, paper: str = "AUTO", scale: float = 0.0, side: float = 0.0) -> tuple[str, float]:
    """The paper and scale: the given ones; AUTO is A4 when the drawing fits it at 1:1 or bigger, else A3;
    the scale is the largest usual one that fits. ``side`` is the width the tables take on the right."""
    x0, y0, x1, y1 = sheet_bounds
    W, H = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)

    def room(p):
        pw, ph = PAPER[p]
        return pw - 2 * MARGIN - 10 - side, ph - 2 * MARGIN - TITLE_H - 5

    if paper == "AUTO":
        if scale:
            for p in PAPER:
                w, h = room(p)
                if W * scale <= w and H * scale <= h:
                    return p, scale
            return "A0", scale
        # A4 when it takes the drawing at full size or bigger, else A3 at the scale that fits
        a4 = _best(*room("A4"), W, H)
        return ("A4", a4) if a4 >= 1 else ("A3", _best(*room("A3"), W, H))
    if paper not in PAPER:
        raise SheetError(f"the paper is one of {', '.join(PAPER)} or AUTO")
    if scale:
        return paper, scale
    return paper, _best(*room(paper), W, H)


def _best(w: float, h: float, W: float, H: float) -> float:
    """The largest usual scale that puts W x H inside w x h."""
    most = min(w / W, h / H)
    for s in SCALES:
        if s <= most + 1e-12:
            return s
    return SCALES[-1]


def compose(views: list[dr.View], sheet_bounds, paper: str, scale: float, props: dict, units: str,
            template: Template | None = None, tables: list | None = None, marks: list | None = None) -> Page:
    from . import sheet_tables as st

    pw, ph = PAPER[paper]
    pg = Page(pw, ph, scale=scale, paper=paper)
    x0, y0, x1, y1 = sheet_bounds
    # the drawing area: inside the frame, above the title block, left of the tables
    ax0, ay0 = MARGIN + 10, MARGIN + TITLE_H + 5
    ax1, ay1 = pw - MARGIN - st.side_width(tables or [], TITLE_W), ph - MARGIN
    ox = (ax0 + ax1) / 2 - (x0 + x1) / 2 * scale
    oy = (ay0 + ay1) / 2 - (y0 + y1) / 2 * scale

    def tr(q, v):
        return (ox + (q[0] + v.dx) * scale, oy + (q[1] + v.dy) * scale)

    label_h = 3.5
    for v in views:
        pg.thick += [[tr(q, v) for q in pl] for pl in v.visible]
        pg.dashed += [[tr(q, v) for q in pl] for pl in v.hidden]
        pg.thin += [[tr(q, v) for q in pl] for pl in v.thin]
        for nx, ny, nh, nt in v.notes:
            x, y = tr((nx, ny), v)
            pg.texts.append((x, y - nh * scale / 3, max(nh * scale, 2.5), nt, "m", "k", 0.0))
        d = v.dims
        pg.dims += [[tr(a, v), tr(b, v)] for a, b in d.lines]
        for tip, (w1, w2) in dr._arrow_shapes(d):
            pg.fills.append([tr(tip, v), tr(w1, v), tr(w2, v)])
        th = max(d.height * scale, 2.5)
        for (cx, cy), ang, text in d.texts:
            x, y = tr((cx, cy), v)
            pg.texts.append((x, y - th / 3, th, text, "m", "b", ang))
        bx0, by0, bx1, _ = v.bounds()
        e = d.extent()
        low = min(by0, e[1]) if e is not None else by0
        x, y = tr(((bx0 + bx1) / 2, low), v)
        pg.texts.append((x, y - label_h * 2, label_h, v.title, "m", "k", 0.0))
        lo, hi = tr((bx0, by0), v), tr((bx1, v.bounds()[3]), v)
        pg.boxes.append((v.title, lo[0], min(lo[1], y - label_h * 2), hi[0], hi[1]))
    if marks:
        _marks(pg, views, marks, tr, scale)
    # frame
    pg.thick.append([(MARGIN, MARGIN), (pw - MARGIN, MARGIN), (pw - MARGIN, ph - MARGIN), (MARGIN, ph - MARGIN),
                     (MARGIN, MARGIN)])
    if template is not None:
        _template_block(pg, template, props, units)
    else:
        _title_block(pg, props, units)
    pg.warnings = st.draw(pg, tables or [], MARGIN, TITLE_H)
    return pg


def _marks(pg: Page, views: list[dr.View], marks: list[dict], tr, scale: float) -> None:
    """Balloons (on the iso view, else the first flat one) and hole tags (on every flat view that looks
    down the hole)."""
    from OCP.gp import gp_Pnt, gp_Pnt2d

    from . import sheet_tables as st

    flat = [v for v in views if v.name in dr.VIEWS]
    if not flat:
        return

    def at(v, q):
        out = gp_Pnt2d()
        dr._projector(v.name).Project(gp_Pnt(*map(float, q)), out)
        return tr((out.X(), out.Y()), v)

    def box(v):
        bx0, by0, bx1, by1 = v.bounds()
        a, b = tr((bx0, by0), v), tr((bx1, by1), v)
        return a[0], a[1], b[0], b[1]

    bal = [mk for mk in marks if mk["kind"] == "balloon"]
    if bal:
        v = next((v for v in flat if v.name == "ISO"), flat[0])
        others = [box(o) for o in views if o is not v]
        st.balloons(pg, [(mk["label"], at(v, mk["point"])) for mk in bal], box(v), others)
    for mk in marks:
        if mk["kind"] != "tag":
            continue
        axis = np.asarray(mk["axis"], float)
        for v in flat:
            if v.name == "ISO" or abs(abs(axis @ _axes(v.name)[2]) - 1) > 1e-6:
                continue
            st.tag(pg, at(v, mk["point"]), mk["r"] * scale, mk["label"])


def _title_block(pg: Page, props: dict, units: str) -> None:
    import datetime

    tw = min(TITLE_W, pg.width - 2 * MARGIN)
    x1, y0 = pg.width - MARGIN, MARGIN
    x0, y1 = x1 - tw, y0 + TITLE_H
    pg.thick.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
    rows = [y0 + 10, y0 + 20, y0 + 28]
    for y in rows:
        pg.thin.append([(x0, y), (x1, y)])
    mid = x0 + tw / 2
    pg.thin.append([(mid, y0), (mid, rows[1])])
    get = {k.upper(): v for k, v in props.items()}
    title = get.get("TITLE", "")
    pg.texts.append((x0 + 3, rows[2] + 4, 6.0, title or "(no title: PROPERTY, TITLE, ...)", "l", "k", 0.0))
    pg.texts.append((x0 + 3, rows[1] + 2.5, 3.0, f"NUMBER  {get.get('NUMBER', '-')}", "l", "k", 0.0))
    pg.texts.append((x1 - 3, rows[1] + 2.5, 3.0, f"REV  {get.get('REVISION', '-')}", "r", "k", 0.0))
    pg.texts.append((x0 + 3, rows[0] + 3.5, 2.8, f"MATERIAL  {get.get('MATERIAL', '-')}", "l", "k", 0.0))
    sheet = f"    SHEET {get['SHEET']}" if get.get("SHEET") else ""
    pg.texts.append((mid + 3, rows[0] + 3.5, 2.8, f"SCALE  {scale_text(pg.scale)}    {units.lower()}    "
                                                  f"{pg.paper}{sheet}", "l", "k", 0.0))
    date = get.get("DATE") or datetime.date.today().isoformat()
    pg.texts.append((x0 + 3, y0 + 3.5, 2.8, f"DRAWN  {get.get('AUTHOR', '-')}   {date}", "l", "k", 0.0))
    pg.texts.append((mid + 3, y0 + 3.5, 2.8, f"{get.get('COMPANY', '')}   third-angle projection".strip(),
                     "l", "k", 0.0))


# ---- title block templates ---------------------------------------------------------------------------

@dataclass
class Template:
    """A title block of your own: rows of fields, from the top, and default values.

    The file is plain text, one setting a line (``!`` starts a comment)::

        paper = A3                    ! the paper, when the sheet does not say
        row = TITLE                   ! a row with one field: shown big, without its label
        row = NUMBER, REVISION        ! fields side by side, each with its label
        row = MATERIAL, SCALE, SHEET
        row = AUTHOR, DATE, COMPANY
        COMPANY = Example Ltd         ! a value used when PROPERTY does not set it

    Fields are PROPERTY names, and SCALE, PAPER, UNITS, SHEET ("2 of 3"), DATE (today unless set).
    """

    name: str = ""
    paper: str = ""
    rows: list = field(default_factory=list)  # list of lists of field names
    values: dict = field(default_factory=dict)
    width: float = TITLE_W
    height: float = TITLE_H


def read_template(path: str) -> Template:
    import os

    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise SheetError(f"cannot read the template {path} ({exc.strerror or exc})") from None
    t = Template(os.path.basename(path))
    for n, raw in enumerate(lines, 1):
        line = raw.split("!", 1)[0].strip()
        if not line:
            continue
        key, eq, val = line.partition("=")
        key, val = key.strip().upper(), val.strip()
        if not eq or not key:
            raise SheetError(f"template {t.name}, line {n}: write NAME = value")
        if key == "PAPER":
            if val.upper() not in PAPER:
                raise SheetError(f"template {t.name}, line {n}: the paper is one of {', '.join(PAPER)}")
            t.paper = val.upper()
        elif key == "ROW":
            cells = [c.strip().upper() for c in val.split(",") if c.strip()]
            if not cells:
                raise SheetError(f"template {t.name}, line {n}: a row needs at least one field")
            t.rows.append(cells)
        elif key == "WIDTH":
            t.width = float(val)
        elif key == "HEIGHT":
            t.height = float(val)
        else:
            t.values[key] = val
    if not t.rows:
        raise SheetError(f"template {t.name} has no rows (row = TITLE ...)")
    return t


def _template_block(pg: Page, t: Template, props: dict, units: str) -> None:
    import datetime

    get = {k.upper(): str(v) for k, v in t.values.items()}
    get.update({k.upper(): str(v) for k, v in props.items()})
    get.setdefault("DATE", datetime.date.today().isoformat())
    get.update({"SCALE": scale_text(pg.scale), "PAPER": pg.paper, "UNITS": units.lower()})
    tw = min(t.width, pg.width - 2 * MARGIN)
    x1, y0 = pg.width - MARGIN, MARGIN
    x0, y1 = x1 - tw, y0 + t.height
    pg.thick.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
    rh = t.height / len(t.rows)
    for i, row in enumerate(t.rows):
        top = y1 - i * rh
        if i:
            pg.thin.append([(x0, top), (x1, top)])
        cw = tw / len(row)
        for j, key in enumerate(row):
            cx = x0 + j * cw
            if j:
                pg.thin.append([(cx, top), (cx, top - rh)])
            val = get.get(key, "-")
            if len(row) == 1 and key == "TITLE":
                h = min(6.0, rh * 0.5)
                pg.texts.append((cx + 3, top - rh / 2 - h / 3, h, val, "l", "k", 0.0))
            else:
                h = min(3.0, rh * 0.32)
                pg.texts.append((cx + 2, top - h - 1, h * 0.7, key.title(), "l", "k", 0.0))
                pg.texts.append((cx + 2, top - rh + h * 0.5, h, val, "l", "k", 0.0))


# ---- writers -------------------------------------------------------------------------------


def _esc_pdf(t: str) -> str:
    t = t.replace("Ø", "ø")  # Helvetica (WinAnsi) has o-slash for a diameter sign
    t = t.encode("cp1252", "replace").decode("cp1252")
    return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _text_width(t: str, h: float) -> float:
    return 0.5 * h * len(t)  # Helvetica's average width, near enough to centre text


def pdf(pg: Page) -> bytes:
    return pdf_pages([pg])


def _page_ops(pg: Page) -> bytes:
    k = 72 / 25.4  # mm -> points
    ops = ["1 J 1 j"]

    def poly(pl):
        return " ".join(f"{x * k:.2f} {y * k:.2f} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(pl))

    def stroke(pls, width, rgb="0 0 0", dash=""):
        if not pls:
            return
        ops.append(f"{rgb} RG {width * k:.3f} w {dash or '[] 0'} d")
        for pl in pls:
            ops.append(poly(pl) + " S")

    stroke(pg.thin, 0.18)
    stroke(pg.dashed, 0.25, "0.35 0.35 0.35", f"[{3 * k:.2f} {1.5 * k:.2f}] 0")
    stroke(pg.thick, 0.5)
    stroke(pg.dims, 0.18, "0.1 0.31 0.63")
    if pg.fills:
        ops.append("0.1 0.31 0.63 rg")
        for tri in pg.fills:
            ops.append(poly(tri) + " h f")
    for x, y, h, t, anchor, col, ang in pg.texts:
        w = _text_width(t, h)
        ops.append(("0.1 0.31 0.63" if col == "b" else "0 0 0") + " rg")
        a = math.radians(ang)
        dx = {"l": 0.0, "m": -w / 2, "r": -w}[anchor]
        tx, ty = x + dx * math.cos(a), y + dx * math.sin(a)
        c, s = math.cos(a), math.sin(a)
        ops.append(f"BT /F1 {h * k:.2f} Tf {c:.4f} {s:.4f} {-s:.4f} {c:.4f} {tx * k:.2f} {ty * k:.2f} Tm "
                   f"({_esc_pdf(t)}) Tj ET")
    return "\n".join(ops).encode("latin-1", "replace")


def pdf_pages(pages: list[Page]) -> bytes:
    """A PDF with one page per sheet."""
    k = 72 / 25.4
    n = len(pages)
    # objects: 1 catalog, 2 pages, 3 font, 4 info, then a page and its content per sheet
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n))
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Producer (3Dmodeling) >>",
    ]
    for i, pg in enumerate(pages):
        content = _page_ops(pg)
        W, H = pg.width * k, pg.height * k
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W:.2f} {H:.2f}] /Contents {6 + 2 * i} 0 R "
                    f"/Resources << /Font << /F1 3 0 R >> >> >>".encode())
        objs.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 4 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def svg(pg: Page) -> str:
    from html import escape

    H = pg.height

    def path(pl):
        return "M" + " L".join(f"{x:.3f},{H - y:.3f}" for x, y in pl)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{pg.width:g}mm" height="{pg.height:g}mm" '
           f'viewBox="0 0 {pg.width:g} {pg.height:g}">', f'<rect width="{pg.width:g}" height="{pg.height:g}" '
           'fill="white"/>']
    for pls, attrs in ((pg.thin, 'stroke="black" stroke-width="0.18"'),
                       (pg.dashed, 'stroke="#595959" stroke-width="0.25" stroke-dasharray="3,1.5"'),
                       (pg.thick, 'stroke="black" stroke-width="0.5" stroke-linecap="round" '
                                  'stroke-linejoin="round"'),
                       (pg.dims, 'stroke="#1a4fa0" stroke-width="0.18"')):
        if pls:
            out.append(f'<path d="{" ".join(path(pl) for pl in pls)}" fill="none" {attrs}/>')
    for tri in pg.fills:
        out.append(f'<path d="{path(tri)} Z" fill="#1a4fa0"/>')
    for x, y, h, t, anchor, col, ang in pg.texts:
        rot = f' transform="rotate({-ang:g} {x:.3f} {H - y:.3f})"' if ang else ""
        out.append(f'<text x="{x:.3f}" y="{H - y:.3f}"{rot} font-family="Helvetica, Arial, sans-serif" '
                   f'font-size="{h:g}" fill="{"#1a4fa0" if col == "b" else "black"}" '
                   f'text-anchor="{ {"l": "start", "m": "middle", "r": "end"}[anchor]}">{escape(t)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"
