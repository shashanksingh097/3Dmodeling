"""Flaws in imported models, found against a tolerance, and repaired step by step.

Files from other programs often arrive with small faults that the kernel's own validity test
does not name: faces that do not quite meet (gaps), faces left loose instead of joined into a
skin, a face turned the wrong way, very narrow faces (slivers), edges far shorter than the
part, and the same face twice. ``inspect`` lists each kind with the faces and edges involved;
``repair`` runs the fixes that apply, one after another, and says what each one did. What
cannot be fixed safely is left and listed, so the user can decide (often by deleting a face
and patching the hole).

Everything is measured against one tolerance: flaws smaller than it are taken as accidents of
the file, larger ones as the design. Without one, a thousandth of the part's size is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.ShapeAnalysis import ShapeAnalysis_Shell
from OCP.ShapeFix import ShapeFix_Shape, ShapeFix_Solid, ShapeFix_Wireframe
from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape

from . import robust

# past this many free edges the gap sizes are not measured one by one (sewing still runs)
_GAP_MEASURE_LIMIT = 400


def _cast(kind):
    return getattr(TopoDS, f"{kind}_s", None) or getattr(TopoDS, kind)


_FACE, _EDGE, _SHELL = _cast("Face"), _cast("Edge"), _cast("Shell")


def default_tolerance(shape: TopoDS_Shape) -> float:
    return max(1e-3 * robust.diagonal(shape), 1e-6)


def _map(shape: TopoDS_Shape, what):
    m = robust._ShapeMap()
    TopExp.MapShapes_s(shape, what, m)
    return m


def _indexed(shape: TopoDS_Shape, what) -> list[TopoDS_Shape]:
    m = _map(shape, what)
    return [m.FindKey(i) for i in range(1, m.Extent() + 1)]


def _area(face) -> float:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return abs(g.Mass())


def _length(shape) -> float:
    g = GProp_GProps()
    BRepGProp.LinearProperties_s(shape, g)
    return g.Mass()


def _centre(face) -> tuple[float, float, float]:
    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    c = g.CentreOfMass()
    return c.X(), c.Y(), c.Z()


def _free_edges(shape: TopoDS_Shape) -> list[tuple[int, TopoDS_Shape]]:
    """Edges used by one face only (seams excluded): (0-based index in edge-map order, its face)."""
    m = robust._EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, m)
    order = _map(shape, TopAbs_EDGE)
    out = []
    for i in range(1, m.Extent() + 1):
        faces = m.FindFromIndex(i)
        size = faces.Size() if hasattr(faces, "Size") else faces.Extent()
        edge = _EDGE(m.FindKey(i))
        if size == 1 and not BRep_Tool.Degenerated_s(edge):
            face = robust._first_face(faces)
            if not BRep_Tool.IsClosed_s(edge, face):
                out.append((order.FindIndex(edge) - 1, face))
    return sorted(out, key=lambda t: t[0])


def _gap_sizes(free: list[tuple[int, TopoDS_Shape]], edges: list) -> list[float]:
    """For each free edge, how far it is from the nearest free edge of another face (the one a
    sew would join it to)."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    out = []
    for i, fi in free:
        best = float("inf")
        for j, fj in free:
            if j == i or fj.IsSame(fi):
                continue
            d = BRepExtrema_DistShapeShape(edges[i], edges[j])
            if d.IsDone() and d.NbSolution():
                # the far point matters too: two edges that only touch at a corner do not pair up
                best = min(best, max(d.Value(), _far(edges[i], edges[j])))
        out.append(best)
    return out


def _far(a, b) -> float:
    """The largest distance from a few points of edge ``a`` to edge ``b``."""
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    c = BRepAdaptor_Curve(_EDGE(a))
    t0, t1 = c.FirstParameter(), c.LastParameter()
    worst = 0.0
    for k in (0.0, 0.5, 1.0):
        v = BRepBuilderAPI_MakeVertex(c.Value(t0 + k * (t1 - t0))).Vertex()
        d = BRepExtrema_DistShapeShape(v, b)
        if d.IsDone() and d.NbSolution():
            worst = max(worst, d.Value())
    return worst


@dataclass
class Flaws:
    tol: float
    faces: int = 0
    solids: int = 0
    shells: int = 0
    loose_faces: int = 0  # faces that are not part of any shell
    free_edges: list[int] = field(default_factory=list)  # edge indexes
    gaps: list[tuple[int, float]] = field(default_factory=list)  # free edges a sew within tol would close
    holes: int = 0  # free edges with nothing to join to within tol
    flipped: list[int] = field(default_factory=list)  # edge indexes where faces disagree on direction
    inside_out: int = 0  # solids with negative volume
    slivers: list[tuple[int, float]] = field(default_factory=list)  # face index, width
    tiny_edges: list[tuple[int, float]] = field(default_factory=list)  # edge index, length
    duplicates: list[tuple[int, int]] = field(default_factory=list)  # face index, the face it repeats
    valid: bool = True

    @property
    def count(self) -> int:
        """How many things are wrong (each gap, sliver, ... counts once)."""
        return (len(self.gaps) + self.holes + len(self.flipped) + self.inside_out + len(self.slivers)
                + len(self.tiny_edges) + len(self.duplicates) + (0 if self.valid else 1)
                + (1 if self.loose_faces else 0))

    def as_dict(self, face_ids=None, edge_ids=None) -> dict[str, Any]:
        fid = (lambda i: face_ids[i]) if face_ids else (lambda i: i + 1)
        eid = (lambda i: edge_ids[i]) if edge_ids else (lambda i: i + 1)
        return {"tolerance": self.tol, "valid": self.valid, "solids": self.solids, "shells": self.shells,
                "faces": self.faces, "loose_faces": self.loose_faces,
                "gaps": [{"edge": eid(i), "size": s} for i, s in self.gaps], "open_edges": self.holes,
                "flipped": [eid(i) for i in self.flipped], "inside_out": self.inside_out,
                "slivers": [{"face": fid(i), "width": w} for i, w in self.slivers],
                "tiny_edges": [{"edge": eid(i), "length": n} for i, n in self.tiny_edges],
                "duplicates": [{"face": fid(i), "same_as": fid(j)} for i, j in self.duplicates],
                "problems": self.count}


def inspect(shape: TopoDS_Shape, tol: float = 0.0) -> Flaws:
    """Every flaw of ``shape`` against ``tol`` (0: a thousandth of the part's size)."""
    tol = tol or default_tolerance(shape)
    faces = _indexed(shape, TopAbs_FACE)
    edges = _indexed(shape, TopAbs_EDGE)
    f = Flaws(tol=tol, faces=len(faces), solids=robust.count(shape, TopAbs_SOLID),
              shells=robust.count(shape, TopAbs_SHELL), valid=robust.is_valid(shape))
    in_shell = robust._ShapeMap()
    ex = TopExp_Explorer(shape, TopAbs_SHELL)
    while ex.More():
        TopExp.MapShapes_s(ex.Current(), TopAbs_FACE, in_shell)
        ex.Next()
    f.loose_faces = len(faces) - in_shell.Extent()
    # gaps and holes: free edges, and whether each has a partner within the tolerance
    free = _free_edges(shape)
    f.free_edges = [i for i, _ in free]
    if free:
        if len(free) <= _GAP_MEASURE_LIMIT:
            for (i, _), d in zip(free, _gap_sizes(free, edges)):
                if d <= tol:
                    f.gaps.append((i, d))
                else:
                    f.holes += 1
        else:
            f.holes = len(free)
    # faces turned the wrong way: neighbours that use a shared edge in the same direction
    a = ShapeAnalysis_Shell()
    a.LoadShells(shape)
    if a.CheckOrientedShells(shape, True) and a.HasBadEdges():
        order = _map(shape, TopAbs_EDGE)
        f.flipped = sorted({order.FindIndex(e) - 1 for e in _indexed(a.BadEdges(), TopAbs_EDGE)} - {-1})
    for s in robust.solids(shape):
        if robust.volume(s) < 0:
            f.inside_out += 1
    # slivers: faces whose mean width (twice the area over the perimeter) is below the tolerance
    for i, face in enumerate(faces):
        area, perimeter = _area(face), _length(face)
        if perimeter > 0:
            width = 2 * area / perimeter
            if width < tol:
                f.slivers.append((i, width))
    for i, e in enumerate(edges):
        if BRep_Tool.Degenerated_s(_EDGE(e)):
            continue
        n = _length(e)
        if n < tol:
            f.tiny_edges.append((i, n))
    # the same face twice: same area and centre (within the tolerance), same kind of surface
    seen: dict[tuple, int] = {}
    q = max(tol, 1e-9)
    for i, face in enumerate(faces):
        area = _area(face)
        if area <= 0:
            continue
        c = _centre(face)
        kind = BRep_Tool.Surface_s(_FACE(face)).DynamicType().Name()
        key = (kind, round(math.log(area) * 1000), *(round(x / q) for x in c))  # area to 0.1%
        if key in seen and not faces[seen[key]].IsSame(face):
            f.duplicates.append((i, seen[key]))
        else:
            seen.setdefault(key, i)
    return f


def _without_faces(shape: TopoDS_Shape, drop: set) -> TopoDS_Shape:
    """All faces of ``shape`` except ``drop`` (0-based indexes), loose in a compound."""
    b = BRep_Builder()
    comp = TopoDS_Compound()
    b.MakeCompound(comp)
    for i, face in enumerate(_indexed(shape, TopAbs_FACE)):
        if i not in drop:
            b.Add(comp, face)
    return comp


def _sew(shape: TopoDS_Shape, tol: float) -> TopoDS_Shape:
    s = BRepBuilderAPI_Sewing(tol)
    s.Add(shape)
    s.Perform()
    return s.SewedShape()


def _solids_from_shells(shape: TopoDS_Shape) -> TopoDS_Shape:
    """Each closed shell becomes a solid (turned outward); open shells and loose faces stay."""
    b = BRep_Builder()
    comp = TopoDS_Compound()
    b.MakeCompound(comp)
    ex = TopExp_Explorer(shape, TopAbs_SHELL)
    shells = []
    while ex.More():
        shells.append(_SHELL(ex.Current()))
        ex.Next()
    if not shells:
        return shape
    for sh in shells:
        if robust.open_edges(sh) == 0:
            fix = ShapeFix_Solid()
            solid = fix.SolidFromShell(sh)
            b.Add(comp, solid if not solid.IsNull() else sh)
        else:
            b.Add(comp, sh)
    return robust.unwrap(comp)


@dataclass
class Repair:
    shape: TopoDS_Shape
    before: Flaws
    after: Flaws
    done: list[str]

    @property
    def changed(self) -> bool:
        return bool(self.done)


def repair(shape: TopoDS_Shape, tol: float = 0.0) -> Repair:
    """Fix what can be fixed, in order: duplicate faces, gaps and loose faces (sewing), faces
    turned the wrong way, tiny edges, then the kernel's general repair. Each fix is kept only
    when it leaves fewer flaws than before it."""
    tol = tol or default_tolerance(shape)
    before = inspect(shape, tol)
    cur, flaws, done = shape, before, []

    def attempt(new, what):
        nonlocal cur, flaws
        if new is None or new.IsNull() or robust.is_empty(new):
            return
        new = robust.unwrap(new)
        after = inspect(new, tol)
        if after.count < flaws.count or (after.count == flaws.count and after.solids > flaws.solids):
            done.append(what(flaws, after))
            cur, flaws = new, after

    if flaws.duplicates:
        drop = {i for i, _ in flaws.duplicates}
        attempt(_solids_from_shells(_sew(_without_faces(cur, drop), tol)),
                lambda a, b: f"removed {len(a.duplicates)} duplicate face{'s' if len(a.duplicates) != 1 else ''}")
    if flaws.gaps or flaws.loose_faces or flaws.flipped or flaws.inside_out or (
            flaws.free_edges and not flaws.solids):
        def said(a, b):
            parts = []
            if len(a.gaps) > len(b.gaps):
                n = len(a.gaps) - len(b.gaps)
                widest = max(s for _, s in a.gaps)
                parts.append(f"joined {n} open edge{'s' if n != 1 else ''} to their neighbours"
                             + (f" (gaps up to {widest:.3g})" if widest > 0 else ""))
            if a.loose_faces and b.loose_faces < a.loose_faces:
                parts.append(f"joined {a.loose_faces - b.loose_faces} loose faces into a skin")
            if len(a.flipped) > len(b.flipped) or a.inside_out > b.inside_out:
                parts.append("turned faces that faced the wrong way")
            if b.solids > a.solids:
                parts.append(f"made {b.solids - a.solids} solid{'s' if b.solids - a.solids != 1 else ''} from closed skins")
            return "; ".join(parts) or "sewed the faces together"

        attempt(_solids_from_shells(_sew(cur, tol)), said)
    if flaws.tiny_edges:
        def small(a, b):
            n = len(a.tiny_edges) - len(b.tiny_edges)
            return f"merged {n} tiny edge{'s' if n != 1 else ''} into their neighbours"

        wf = ShapeFix_Wireframe(cur)
        wf.SetPrecision(tol)
        wf.SetLimitAngle(0.5)
        try:
            wf.FixSmallEdges()
            wf.FixWireGaps()
            attempt(wf.Shape(), small)
        except Exception:  # noqa: BLE001 - the fix itself failed: leave the edges and list them
            pass
    if not flaws.valid:
        fix = ShapeFix_Shape(cur)
        fix.SetPrecision(tol)
        fix.SetMaxTolerance(tol * 10)
        fix.Perform()
        attempt(fix.Shape(), lambda a, b: "fixed faces and edges the kernel found invalid")
    return Repair(cur, before, flaws, done)


def left_text(f: Flaws, face_ids=None, edge_ids=None) -> list[str]:
    """One line per kind of flaw still there, with what to try."""
    d = f.as_dict(face_ids, edge_ids)
    out = []
    if not d["valid"]:
        out.append("the kernel still finds the shape invalid")
    if d["gaps"]:
        widest = max(g["size"] for g in d["gaps"])
        out.append(f"{len(d['gaps'])} edge{'s' if len(d['gaps']) != 1 else ''} not joined to the face next to "
                   f"{'them' if len(d['gaps']) != 1 else 'it'}" + (f" (gaps up to {widest:.3g})" if widest > 0 else "")
                   + f" (edges {_ids([g['edge'] for g in d['gaps']])}); HEAL joins them")
    if d["open_edges"]:
        out.append(f"{d['open_edges']} open edge{'s' if d['open_edges'] != 1 else ''} with nothing within "
                   f"{f.tol:.3g} to join to: a hole; a larger tolerance or a patch (SURFACE) closes it")
    if d["loose_faces"]:
        out.append(f"{d['loose_faces']} loose face{'s' if d['loose_faces'] != 1 else ''} not joined into a skin")
    if d["flipped"]:
        out.append(f"faces turned the wrong way along edges {_ids(d['flipped'])}")
    if d["inside_out"]:
        out.append(f"{d['inside_out']} solid{'s' if d['inside_out'] != 1 else ''} inside out")
    if d["slivers"]:
        out.append(f"{len(d['slivers'])} sliver face{'s' if len(d['slivers']) != 1 else ''} narrower than "
                   f"{f.tol:.3g} (faces {_ids([s['face'] for s in d['slivers']])}); DELFACE removes one and "
                   "lets its neighbours grow over it")
    if d["tiny_edges"]:
        out.append(f"{len(d['tiny_edges'])} edge{'s' if len(d['tiny_edges']) != 1 else ''} shorter than "
                   f"{f.tol:.3g} (edges {_ids([e['edge'] for e in d['tiny_edges']])})")
    if d["duplicates"]:
        out.append(f"{len(d['duplicates'])} duplicate face{'s' if len(d['duplicates']) != 1 else ''} (faces "
                   f"{_ids([x['face'] for x in d['duplicates']])})")
    return out


def _ids(ids: list, most: int = 8) -> str:
    shown = ", ".join(str(i) for i in ids[:most])
    return shown + (f" and {len(ids) - most} more" if len(ids) > most else "")
