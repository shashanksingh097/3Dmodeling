"""Pick fingerprints: what a picked entity looks like, so it can be found again.

A pick is written as ``PICK, FACE, 12``. The ID is the fast, exact way to
find the face again, and the model works hard to keep IDs stable. But an ID
can still disappear: an earlier step was rewritten, a face was rebuilt by
the kernel, or the script is replayed without its saved IDs. For that case
every pick in the history also remembers a *fingerprint* of what was picked
(which history step made it, which body it is on, what kind of surface or
curve, where it is, how big, which way it points). When the ID is gone, or
now belongs to something made by a different step, the fingerprint is used
to find the entity again; the history entry is then marked with a warning so the user can see
that a reference was repaired and check it.

The matching is deliberately strict. A repaired pick is only accepted when
exactly one entity fits; a guess between several look-alikes is refused,
because a silently wrong reference is worse than a failed entry.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_CurveType, GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_REVERSED
from OCP.TopoDS import TopoDS

if TYPE_CHECKING:
    from .model import Model


def _static(cls, name):
    return getattr(cls, name + "_s", None) or getattr(cls, name)


_as_edge = _static(TopoDS, "Edge")
_as_face = _static(TopoDS, "Face")
_as_vertex = _static(TopoDS, "Vertex")

_SURF = {
    GeomAbs_SurfaceType.GeomAbs_Plane: "PLANE",
    GeomAbs_SurfaceType.GeomAbs_Cylinder: "CYLINDER",
    GeomAbs_SurfaceType.GeomAbs_Cone: "CONE",
    GeomAbs_SurfaceType.GeomAbs_Sphere: "SPHERE",
    GeomAbs_SurfaceType.GeomAbs_Torus: "TORUS",
}
_CURVE = {
    GeomAbs_CurveType.GeomAbs_Line: "LINE",
    GeomAbs_CurveType.GeomAbs_Circle: "CIRCLE",
    GeomAbs_CurveType.GeomAbs_Ellipse: "ELLIPSE",
}


def _xyz(v) -> list[float]:
    return [v.X(), v.Y(), v.Z()]


def _describe(kind: str, shape) -> dict[str, Any]:
    """Type, centre, size, direction and radius of one shape."""
    typ, direction, radius = kind, None, None
    if kind == "VERTEX":
        return {"type": "VERTEX", "c": _xyz(BRep_Tool.Pnt_s(_as_vertex(shape))), "size": 0.0, "dir": None, "r": None}
    g = GProp_GProps()
    if kind == "FACE":
        BRepGProp.SurfaceProperties_s(shape, g)
        face = _as_face(shape)
        s = BRepAdaptor_Surface(face)
        typ = _SURF.get(s.GetType(), "FREEFORM")
        if typ == "PLANE":
            direction = _xyz(s.Plane().Axis().Direction())
            if face.Orientation() == TopAbs_REVERSED:
                direction = [-v for v in direction]
        elif typ == "CYLINDER":
            direction, radius = _xyz(s.Cylinder().Axis().Direction()), s.Cylinder().Radius()
        elif typ == "CONE":
            direction = _xyz(s.Cone().Axis().Direction())
        elif typ == "SPHERE":
            radius = s.Sphere().Radius()
        elif typ == "TORUS":
            direction, radius = _xyz(s.Torus().Axis().Direction()), s.Torus().MajorRadius()
    elif kind == "EDGE":
        BRepGProp.LinearProperties_s(shape, g)
        c = BRepAdaptor_Curve(_as_edge(shape))
        typ = _CURVE.get(c.GetType(), "FREEFORM")
        if typ == "LINE":
            direction = _xyz(c.Line().Direction())
        elif typ == "CIRCLE":
            direction, radius = _xyz(c.Circle().Axis().Direction()), c.Circle().Radius()
    else:  # BODY
        BRepGProp.VolumeProperties_s(shape, g)
        if abs(g.Mass()) < 1e-12:  # a curve or a sheet: measure it by its box
            box = Bnd_Box()
            BRepBndLib.Add_s(shape, box, False)
            if not box.IsVoid():
                lo, hi = box.CornerMin(), box.CornerMax()
                centre = [(a + b) / 2 for a, b in zip(_xyz(lo), _xyz(hi))]
                return {"type": "BODY", "c": centre, "size": lo.Distance(hi), "dir": None, "r": None}
    return {"type": typ, "c": _xyz(g.CentreOfMass()), "size": abs(g.Mass()), "dir": direction, "r": radius}


def fingerprint(model: "Model", kind: str, gid: int) -> dict[str, Any]:
    """A small, JSON-friendly description of one entity (see the module text)."""
    if kind == "BODY":
        body = model.body(gid)
    else:
        body = model.bodies[model.entity_owner(kind, gid)[0]]
    fp = _describe(kind, model.entity_shape(kind, gid))
    fp["kind"] = kind
    fp["body"] = body.name
    fp["origin"] = model.origin(kind, gid)
    fp["id"] = gid
    return fp


def same_entity(model: "Model", kind: str, gid: int, fp: dict[str, Any]) -> bool:
    """Is ``gid`` still the entity the fingerprint was taken from?

    An ID can be handed out again after the step that owned it was deleted.
    The entity is the same one only if the same history step made it.
    """
    return "origin" not in fp or model.origin(kind, gid) == fp["origin"]


def _close(a: float, b: float, rel: float = 1e-6) -> bool:
    return abs(a - b) <= rel * max(1.0, abs(a), abs(b))


def _same_dir(kind: str, a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    dot = sum(x * y for x, y in zip(a, b))
    if kind == "EDGE":
        dot = abs(dot)  # an edge has no front and back
    return dot >= 1 - 1e-9


def find(model: "Model", fp: dict[str, Any]) -> tuple[int | None, str]:
    """Find the entity a fingerprint describes.

    Returns ``(id, how)``: ``how`` is "same place" when an entity of the same
    type and size sits exactly where the picked one was, or "moved" when the
    only entity of that type, size and direction is somewhere else. Returns
    ``(None, reason)`` when nothing fits or when several entities fit equally.
    """
    kind = fp["kind"]
    cands: list[tuple[int, dict[str, Any]]] = []
    for gid in model.entity_ids(kind):
        d = _describe(kind, model.entity_shape(kind, gid))
        if d["type"] != fp["type"] or not _close(d["size"], fp["size"]):
            continue
        if (d["r"] is None) != (fp["r"] is None) or (d["r"] is not None and not _close(d["r"], fp["r"])):
            continue
        if not _same_dir(kind, d["dir"], fp["dir"]):
            continue
        d["body"] = (model.body(gid) if kind == "BODY" else model.bodies[model.entity_owner(kind, gid)[0]]).name
        cands.append((gid, d))
    if not cands:
        return None, "nothing with the same shape and size is left"
    scale = max(1.0, *(abs(v) for v in fp["c"]))
    here = [(g, d) for g, d in cands if math.dist(d["c"], fp["c"]) <= 1e-6 * scale]
    for group, how in ((here, "same place"), (cands, "moved")):
        if len(group) > 1:  # prefer the body it was on
            named = [(g, d) for g, d in group if d["body"] == fp.get("body")]
            if len(named) == 1:
                group = named
        if len(group) == 1:
            return group[0][0], how
        if group:
            return None, f"{len(group)} entities look the same, so the choice is not safe"
    return None, "nothing fits"


class RefLog:
    """Fingerprints of the picks one history entry made, in the order it made them.

    While the entry runs again, each pick reads its old fingerprint with
    :meth:`take` and stores the new one with :meth:`record`.
    """

    def __init__(self, previous: list[dict[str, Any] | None] | None = None) -> None:
        self.previous = list(previous or [])
        self.used: list[dict[str, Any] | None] = []

    def take(self) -> dict[str, Any] | None:
        i = len(self.used)
        return self.previous[i] if i < len(self.previous) else None

    def record(self, fp: dict[str, Any] | None) -> None:
        self.used.append(fp)

    def merged(self) -> list[dict[str, Any] | None]:
        """What to remember: this run's picks, then older ones this run did not reach."""
        return self.used + self.previous[len(self.used):]
