"""Mould tools: which faces come out of which half of a mould (PARTING) and
the two mould halves themselves (MOLD).

For a pull direction d, each face of the part is judged from a fine mesh
(analysis.mesh): it comes out with the + half (its normal leans along d by
at least the least draft angle), with the - half (leans against d), or it
is too steep (it needs draft). A face with both + and - areas is crossed
by the parting line (a round side lying down, for example). A + area is an
undercut when the way out along +d is blocked by the part itself (a ray
from it along +d hits material), and the same for - along -d.

The parting line is where + faces meet - faces, or where a face is crossed
by the change. When it is flat (all at one level along d) the mould halves
can be split there.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import analysis as an
from . import robust


class MoldError(ValueError):
    pass


@dataclass
class FaceVerdict:
    index: int  # in the mesh's face order
    side: str  # "+", "-", "steep", "both"
    area: float
    undercut: float = 0.0  # undercut area


@dataclass
class Parting:
    direction: np.ndarray
    faces: list[FaceVerdict]
    edges: list  # TopoDS_Edge on the parting line (between + and - faces)
    levels: tuple[float, float] | None  # the parting edges' lowest and highest level along d
    split_faces: list[int] = field(default_factory=list)  # faces crossed by the parting line
    mesh: object = None

    def area(self, side: str) -> float:
        return sum(f.area for f in self.faces if f.side == side)

    @property
    def flat(self) -> bool:
        return self.levels is not None and self.levels[1] - self.levels[0] < 1e-6 * max(1.0, abs(self.levels[0]))


def _unit(d) -> np.ndarray:
    v = np.asarray(d, float)
    n = np.linalg.norm(v)
    if n < 1e-12:
        raise MoldError("the pull direction cannot be (0, 0, 0)")
    return v / n


def parting(shape, direction, min_draft: float = 0.0, undercuts: bool = True) -> Parting:
    """Judge every face of a solid for a mould pulled along +/- direction."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp

    from .probe import Rays

    if not robust.solids(shape):
        raise MoldError("the part must be a solid")
    d = _unit(direction)
    m = an.mesh(shape)
    cls = an.draft_classes(m, d, min_draft)
    tcls = cls[m.tris]
    areas = m.tri_areas()
    up = (tcls == 1).all(axis=1)
    down = (tcls == -1).all(axis=1)
    nf = len(m.faces)
    face_area = np.bincount(m.face_of_tri, weights=areas, minlength=nf)
    up_area = np.bincount(m.face_of_tri, weights=areas * up, minlength=nf)
    down_area = np.bincount(m.face_of_tri, weights=areas * down, minlength=nf)
    blocked = np.zeros(len(m.tris), bool)
    if undercuts:
        rays = Rays(shape)
        size = max(robust.diagonal(shape), 1e-9)
        cent = m.nodes[m.tris].mean(axis=1)
        for side, mask in ((1.0, up), (-1.0, down)):
            idx = np.nonzero(mask)[0]
            if len(idx) > 4000:  # a sample is enough to find undercut faces
                idx = idx[np.linspace(0, len(idx) - 1, 4000).astype(int)]
            for t in idx:
                start = cent[t] + side * d * 1e-4 * size
                hits = rays.hits(tuple(start), tuple(side * d))
                if any(h["state"] == "in" and h["t"] > 1e-6 * size and not h.get("grazing") for h in hits):
                    blocked[t] = True
    under_area = np.bincount(m.face_of_tri, weights=areas * blocked, minlength=nf)
    verdicts = []
    for i in range(nf):
        a = float(face_area[i])
        if a <= 0:
            continue
        u, dn = float(up_area[i]) / a, float(down_area[i]) / a
        if u > 0.02 and dn > 0.02:
            side = "both"
        elif u >= 0.5:
            side = "+"
        elif dn >= 0.5:
            side = "-"
        else:
            side = "steep"
        verdicts.append(FaceVerdict(i, side, a, float(under_area[i])))
    # parting edges: shared by a + face and a - face
    side_of = {v.index: v.side for v in verdicts}
    emap = robust._EdgeFaceMap()
    TopExp.MapShapesAndAncestors_s(shape, TopAbs_EDGE, TopAbs_FACE, emap)
    index_of = {}
    for i, f in enumerate(m.faces):
        index_of.setdefault(an._hash(f), []).append((f, i))

    def face_index(f):
        for g, i in index_of.get(an._hash(f), ()):
            if g.IsSame(f):
                return i
        return None

    from OCP.TopoDS import TopoDS

    as_edge = getattr(TopoDS, "Edge_s", None) or TopoDS.Edge
    pairs = []
    for k in range(1, emap.Extent() + 1):
        e = as_edge(emap.FindKey(k))
        if not BRep_Tool.Degenerated_s(e):
            pairs.append((e, {side_of.get(face_index(f)) for f in emap.FindFromIndex(k)}))
    # where + meets -; with steep walls in between, where the walls meet the - side (the part then sits
    # in the + half, and the walls need draft)
    edges = [e for e, sd in pairs if "+" in sd and "-" in sd]
    if not edges:
        edges = [e for e, sd in pairs if "steep" in sd and "-" in sd]
    levels = []
    for e in edges:
        c = BRepAdaptor_Curve(e)
        for t in np.linspace(c.FirstParameter(), c.LastParameter(), 5):
            q = c.Value(float(t))
            levels.append(float(np.dot(d, (q.X(), q.Y(), q.Z()))))
    split = [v.index for v in verdicts if v.side == "both"]
    lv = (min(levels), max(levels)) if levels else None
    return Parting(d, verdicts, edges, lv, split, m)


def default_level(shape, part: Parting) -> tuple[float, str]:
    """Where to split the mould along d: a flat parting line's level, else the part's widest place."""
    if part.flat and not part.split_faces:
        return part.levels[0], "at the parting line"
    m = part.mesh
    lv = m.nodes @ part.direction
    lo, hi = float(lv.min()), float(lv.max())
    if hi - lo < 1e-9:
        return lo, "at the part"
    # the widest place: where the surface turns from facing up to facing down (the silhouette of a round
    # side), from the nodes whose normals lie most nearly across the pull
    across = np.abs(m.normals @ part.direction)
    pool = np.arange(len(across))
    if part.split_faces:  # only the faces the parting line crosses (flat walls along the pull say nothing)
        pool = np.unique(m.tris[np.isin(m.face_of_tri, part.split_faces)])
    if len(pool) and (across[pool] < 0.2).any():
        k = max(3, int(0.02 * len(pool)))
        near = pool[np.argsort(across[pool])[:k]]
        return float(np.median(lv[near])), "at the part's widest place (no flat parting line)"
    return (lo + hi) / 2, "half way up the part (no flat parting line)"


def _box_around(shape, margin: float):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    a, b = box.CornerMin(), box.CornerMax()
    return BRepPrimAPI_MakeBox(gp_Pnt(a.X() - margin, a.Y() - margin, a.Z() - margin),
                               gp_Pnt(b.X() + margin, b.Y() + margin, b.Z() + margin)).Shape()


def _half_space(direction, level: float, size: float, above: bool):
    """A big box with one face on the plane at ``level`` along the direction, above or below it."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    d = _unit(direction)
    r = 4 * size
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*d))
    x = np.array([ax.XDirection().X(), ax.XDirection().Y(), ax.XDirection().Z()])
    y = np.cross(d, x)
    corner = d * (level if above else level - 2 * r) - r * x - r * y
    return BRepPrimAPI_MakeBox(gp_Ax2(gp_Pnt(*corner), gp_Dir(*d), gp_Dir(*x)), 2 * r, 2 * r, 2 * r).Shape()


def _bool(kind, a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut

    op = (BRepAlgoAPI_Cut if kind == "cut" else BRepAlgoAPI_Common)(a, b)
    op.Build()
    if not op.IsDone():
        raise MoldError(f"building the mould failed ({kind})")
    return op.Shape()


def halves(shape, direction, level: float, margin: float, shrink_pct: float = 0.0):
    """(the + half, the - half): a block round the part (grown by the shrink) cut by the part, split at
    ``level`` along the direction."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.gp import gp_Trsf

    if margin <= 0:
        raise MoldError("the margin must be positive")
    if not -50 < shrink_pct < 50:
        raise MoldError("the shrink allowance is a percentage, such as 0.5 or 2")
    part = shape
    if shrink_pct:
        g = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, g)
        t = gp_Trsf()
        t.SetScale(g.CentreOfMass(), 1 + shrink_pct / 100.0)
        part = BRepBuilderAPI_Transform(shape, t, True).Shape()
    block = _box_around(part, margin)
    mould = _bool("cut", block, part)
    size = robust.diagonal(block)
    top = _bool("common", mould, _half_space(direction, level, size, True))
    bottom = _bool("common", mould, _half_space(direction, level, size, False))
    if robust.is_empty(top) or robust.is_empty(bottom):
        raise MoldError("the split level is outside the part; the mould would be in one piece")
    return robust.unwrap(top), robust.unwrap(bottom)


def describe_side(side: str) -> str:
    return {"+": "out with the + half", "-": "out with the - half", "steep": "too steep (needs draft)",
            "both": "crossed by the parting line"}[side]


def angle_text(d) -> str:
    return "(" + ", ".join(f"{x:.4g}" for x in _unit(d)) + ")"

