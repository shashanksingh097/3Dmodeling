"""DRAWING: 2D drawings of the bodies (SVG or DXF), the standard views with
hidden lines dashed. The work is in ``geometry/drawing.py``."""

from __future__ import annotations

import os

from .processor import Arg, BodyRef, CommandError, Path, Processor, command


def _exact_extent(bodies) -> dict[str, float] | None:
    """The bodies' size along X, Y and Z from their exact geometry (no tolerance gap)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    try:
        for x in bodies:
            BRepBndLib.AddOptimal_s(x.shape, box, False, False)
    except Exception:
        return None
    if box.IsVoid():
        return None
    lo, hi = box.CornerMin(), box.CornerMax()
    return {"X": hi.X() - lo.X(), "Y": hi.Y() - lo.Y(), "Z": hi.Z() - lo.Z()}


@command(
    "DRAWING",
    Arg("file", Path, help="the file to write: .svg or .dxf"),
    Arg("views", str, "STANDARD", "STANDARD (front, top, right and iso), or views joined with +: "
                                  "TOP+FRONT, ISO ..."),
    Arg("b", BodyRef, 0, "body to draw (default: all shown bodies)"),
    Arg("sizes", str, "ALL", "sizes to write: ALL (overall sizes and hole diameters), OVERALL, HOLES or NONE"),
    logged=False,
    help="Write a 2D drawing of the bodies, at true size: DRAWING, \"part.svg\" [, views] [, body] [, sizes]. "
         "STANDARD views are front, top above it, right beside it and an isometric view; or give "
         "TOP, FRONT, RIGHT, LEFT, BACK, BOTTOM, ISO joined with +. Hidden edges are dashed. Sizes: the "
         "overall width, depth and height, each once, and the diameter of every whole circle seen "
         "face-on, equal ones counted (4x D8); sizes NONE leaves them off. .dxf files open in any CAD "
         "program (layers VISIBLE, HIDDEN, TEXT, DIMS). Runs when given; not kept in the history.",
)
def drawing(p: Processor, file, views, b, sizes):
    from ..geometry import drawing as dr
    from ..geometry import meshbody
    from .handlers import _compound

    ext = os.path.splitext(file)[1].lower()
    if ext not in (".svg", ".dxf"):
        raise CommandError("DRAWING: the file must end in .svg or .dxf")
    try:
        names = dr.parse_views(views)
    except ValueError as exc:
        raise CommandError(f"DRAWING: {exc}") from None
    m = p.model
    if b:
        bodies = [m.body(b)]
    else:
        hidden = getattr(m, "hidden", set()) or set()
        bodies = [x for x in m.bodies.values() if x.id not in hidden] or list(m.bodies.values())
    if not bodies:
        raise CommandError("DRAWING: there are no bodies")
    meshes = [x for x in bodies if meshbody.is_mesh(x.shape)]
    solids = [x for x in bodies if not meshbody.is_mesh(x.shape)]
    size = 1.0
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    for x in bodies:
        try:
            BRepBndLib.Add_s(x.shape, box)
        except AttributeError:
            BRepBndLib.Add(x.shape, box)
    if not box.IsVoid():
        size = max(box.CornerMin().Distance(box.CornerMax()), 1e-9)
    exact = _exact_extent(bodies)
    deflection = size / 2000
    out = []
    for name in names:
        v = dr.View(name)
        for group, mesh in ((solids, False), (meshes, True)):
            if group:
                shape = group[0].shape if len(group) == 1 else _compound([x.shape for x in group])
                one = dr.project(shape, name, deflection, mesh)
                v.visible += one.visible
                v.hidden += one.hidden
                v.circles += one.circles
        out.append(v)
    try:
        nsizes = dr.dimension(out, sizes, exact)
    except ValueError as exc:
        raise CommandError(f"DRAWING: {exc}") from None
    sheet = dr.layout(out)
    text = dr.svg(out, sheet, m.units) if ext == ".svg" else dr.dxf(out, sheet, m.units)
    path = os.path.abspath(file)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as exc:
        raise CommandError(f"DRAWING: could not write {file}: {exc.strerror}") from None
    edges = sum(len(v.visible) + len(v.hidden) for v in out)
    return (f"wrote a drawing of {len(bodies)} bod{'y' if len(bodies) == 1 else 'ies'} to {file}: "
            f"{', '.join(n.lower() for n in names)} view{'s' if len(names) > 1 else ''}, {edges} edges, "
            f"{nsizes} size{'' if nsizes == 1 else 's'}, "
            f"{(sheet[2] - sheet[0]):.4g} x {(sheet[3] - sheet[1]):.4g} {m.units.lower()}")
