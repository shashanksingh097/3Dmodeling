"""Trust, but verify: checks and repairs around kernel operations.

The kernel can report success and still hand back a shape that is empty,
not closed, or self-intersecting (an oversized fillet is the classic case).
Nothing here makes the kernel smarter; it makes sure a bad result is caught
at the command that produced it, with a message that says what to change,
instead of surfacing three steps later as a mystery.
"""

from __future__ import annotations

import time

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.ShapeFix import ShapeFix_Shape
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopAbs import (
    TopAbs_COMPOUND,
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS_Iterator, TopoDS_Shape

try:  # OCP 7.x
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape as _EdgeFaceMap
    from OCP.TopTools import TopTools_IndexedMapOfShape as _ShapeMap
except ImportError:  # OCP 8.x
    from OCP.collections import (  # type: ignore[no-redef]
        IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher as _EdgeFaceMap,
    )
    from OCP.collections import (  # type: ignore[no-redef]
        IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as _ShapeMap,
    )

# A full validity check is cheap on a small part but slow on a big one (a
# plate with 300 holes takes 0.1 s per check, as long as the cut itself).
# Fillets, chamfers and the CHECK command always pay for it. Booleans, which
# run in long loops, always get the quick tests (not empty, still a solid, no
# open edges) and the full check when the result is small or when checking
# has used less than a tenth of the time spent in the kernel so far.
ALWAYS_CHECK_FACES = 60
CHECK_SHARE = 0.1


class _Budget:
    def __init__(self) -> None:
        self.work = 0.0  # seconds spent in kernel operations
        self.checks = 0.0  # seconds spent in full checks
        self.last = 0.0  # how long the last full check took

    def allows(self) -> bool:
        return self.checks + self.last <= CHECK_SHARE * self.work

    def timed_check(self, shape: TopoDS_Shape) -> bool:
        start = time.perf_counter()
        try:
            return is_valid(shape)
        finally:
            self.last = time.perf_counter() - start
            self.checks += self.last


BUDGET = _Budget()


def quick_ok(shape: TopoDS_Shape, must_be_closed: bool) -> bool:
    """The cheap tests: something is there, and a solid has no open edges."""
    if is_empty(shape):
        return False
    return not must_be_closed or open_edges(shape) == 0


def checked_ok(shape: TopoDS_Shape, must_be_closed: bool) -> bool:
    """Quick tests always; the full validity check when it is affordable."""
    if not quick_ok(shape, must_be_closed):
        return False
    if count(shape, TopAbs_FACE) <= ALWAYS_CHECK_FACES or BUDGET.allows():
        return BUDGET.timed_check(shape)
    return True


def count(shape: TopoDS_Shape, what) -> int:
    m = _ShapeMap()
    TopExp.MapShapes_s(shape, what, m)
    return m.Extent()


def solids(shape: TopoDS_Shape) -> list[TopoDS_Shape]:
    out = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def is_empty(shape: TopoDS_Shape) -> bool:
    return shape is None or shape.IsNull() or (count(shape, TopAbs_VERTEX) == 0 and count(shape, TopAbs_EDGE) == 0)


def is_valid(shape: TopoDS_Shape) -> bool:
    return bool(BRepCheck_Analyzer(shape).IsValid())


def volume(shape: TopoDS_Shape) -> float:
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    return g.Mass()


def diagonal(shape: TopoDS_Shape) -> float:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box, False)
    if box.IsVoid():
        return 0.0
    return box.CornerMin().Distance(box.CornerMax())


def unwrap(shape: TopoDS_Shape) -> TopoDS_Shape:
    """A compound that holds exactly one thing is that thing.

    Booleans always answer with a compound; a body that is one solid should
    be a solid, so that later steps (and exports) see what the user sees.
    """
    while not shape.IsNull() and shape.ShapeType() == TopAbs_COMPOUND:
        it = TopoDS_Iterator(shape)
        if not it.More():
            break
        only = it.Value()
        it.Next()
        if it.More():
            break
        shape = only
    return shape


def open_edges(shape: TopoDS_Shape) -> int:
    """Edges that belong to only one face: holes in the skin of a solid."""
    m = _EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, m)
    from OCP.BRep import BRep_Tool
    from OCP.TopoDS import TopoDS

    as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    n = 0
    for i in range(1, m.Extent() + 1):
        faces = m.FindFromIndex(i)
        size = faces.Size() if hasattr(faces, "Size") else faces.Extent()
        if size == 1 and not BRep_Tool.Degenerated_s(as_edge(m.FindKey(i))):
            edge = as_edge(m.FindKey(i))
            # a seam (the join of a cylinder's side) is listed once but used twice
            if not BRep_Tool.IsClosed_s(edge, _first_face(faces)):
                n += 1
    return n


def _first_face(faces):
    from OCP.TopoDS import TopoDS

    as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
    for f in faces:
        return as_face(f)


def report(shape: TopoDS_Shape) -> dict:
    """Everything CHECK prints about one body."""
    n_solids = len(solids(shape))
    info = {
        "valid": is_valid(shape),
        "solids": n_solids,
        "shells": count(shape, TopAbs_SHELL),
        "faces": count(shape, TopAbs_FACE),
        "edges": count(shape, TopAbs_EDGE),
        "open_edges": open_edges(shape) if count(shape, TopAbs_FACE) else 0,
        "volume": volume(shape) if n_solids else 0.0,
    }
    info["ok"] = info["valid"] and info["open_edges"] == 0 and (not n_solids or info["volume"] > 0)
    return info


def heal(shape: TopoDS_Shape, tolerance: float = 0.0) -> TopoDS_Shape:
    """Run the kernel's general repair on a shape and return the result."""
    fix = ShapeFix_Shape(shape)
    if tolerance > 0:
        fix.SetPrecision(tolerance)
        fix.SetMaxTolerance(tolerance * 10)
    fix.Perform()
    return fix.Shape()


class _Unified:
    """Two steps seen as one maker: ``first`` (a boolean, or nothing) and then
    a face merge. Answers Modified/IsDeleted the way the model expects, so
    face and edge IDs carry through both steps."""

    def __init__(self, first, history) -> None:
        self.first = first
        self.history = history

    def Modified(self, old):
        stage: list = []
        if self.first is not None:
            try:
                stage = list(self.first.Modified(old))
                if not stage and self.first.IsDeleted(old):
                    return []
            except Exception:  # some makers do not track every kind
                stage = []
        out = []
        for s in stage or [old]:
            later = list(self.history.Modified(s))
            if later:
                out.extend(later)
            elif not self.history.IsRemoved(s):
                out.append(s)
        return out

    def IsDeleted(self, old) -> bool:
        if self.first is not None:
            try:
                if not list(self.first.Modified(old)) and self.first.IsDeleted(old):
                    return True
            except Exception:
                pass
        return False


def merge_faces(shape: TopoDS_Shape, first=None):
    """Join neighbouring faces that lie on the same surface (and edges on the
    same line), such as the seam left where two blocks were fused.

    Returns ``(shape, maker, removed)``; ``maker`` carries IDs through
    ``first`` (the operation that made ``shape``, if any) and the merge.
    """
    before = count(shape, TopAbs_FACE)
    u = ShapeUpgrade_UnifySameDomain(shape, True, True, False)
    u.Build()
    out = u.Shape()
    removed = before - count(out, TopAbs_FACE)
    if out.IsNull() or removed <= 0:
        return shape, first, 0
    return out, _Unified(first, u.History()), removed


def largest_working(build, wanted: float, budget: float = 1.5) -> float | None:
    """The largest size below ``wanted`` for which ``build(size)`` gives a
    valid shape, found by trying sizes in between (for at most ``budget``
    seconds). None when even a tiny size fails."""

    def works(size: float) -> bool:
        try:
            shape = build(size)
        except Exception:
            return False
        return shape is not None and not is_empty(shape) and is_valid(shape)

    start = time.monotonic()
    lo = wanted / 64
    if not works(lo):
        return None
    hi = wanted
    for _ in range(12):
        if time.monotonic() - start > budget or (hi - lo) <= 0.02 * hi:
            break
        mid = (lo + hi) / 2
        if works(mid):
            lo = mid
        else:
            hi = mid
    return lo
