"""Direct face editing: push or pull faces, and delete faces.

These change a body's faces without any history of how it was made, so they
work on imported STEP parts as well as on parts built here.

* Push/pull moves each chosen face along its own normal and lets the faces
  around it stretch to meet it (an offset of just those faces). A flat face
  moves flat, a hole's wall changes the hole's radius, a fillet changes its
  radius.
* Delete removes faces and lets the faces around them grow to close the gap:
  a hole, a boss, a pocket, a fillet or a chamfer goes away and the part is
  as if it had never been there.
"""

from __future__ import annotations

from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing
from OCP.BRepOffset import BRepOffset_MakeOffset, BRepOffset_Skin
from OCP.GeomAbs import GeomAbs_Intersection
from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID

from . import robust
from .features import Renamed, as_face
from .surfaces import _as_shell, _solid


class DirectError(Exception):
    pass


def push_pull(shape, faces: list, distances: list[float]):
    """(new shape, history) with each face moved by its distance along its
    outward normal: positive adds material, negative takes it away."""
    mk = BRepOffset_MakeOffset()
    mk.Initialize(shape, 0.0, 1e-6, BRepOffset_Skin, False, False, GeomAbs_Intersection, False, False)
    for f, d in zip(faces, distances):
        mk.SetOffsetOnFace(as_face(f), float(d))
    try:
        mk.MakeOffsetShape()
    except Exception:  # noqa: BLE001 - OCCT throws on faces it cannot offset
        raise DirectError("the kernel could not move these faces") from None
    if not mk.IsDone():
        raise DirectError("the kernel could not move these faces")
    out = mk.Shape()
    if out.IsNull():
        raise DirectError("the kernel could not move these faces that far")
    if out.ShapeType() == TopAbs_SHELL:
        out = _solid(_as_shell(out))
    elif out.ShapeType() != TopAbs_SOLID:
        solids = robust.solids(out)
        if len(solids) == 1:
            out = solids[0]

    def new_of(old):
        # the offset maker reports each face and edge as "generated" anew
        return [s for s in list(mk.Modified(old)) + list(mk.Generated(old)) if s.ShapeType() == old.ShapeType()]

    return out, Renamed(new_of)


def delete_faces(shape, faces: list):
    """(new shape, history) with the faces removed and the gap closed."""
    mk = BRepAlgoAPI_Defeaturing()
    mk.SetShape(shape)
    for f in faces:
        mk.AddFaceToRemove(as_face(f))
    mk.SetRunParallel(True)
    mk.SetToFillHistory(True)
    mk.Build()
    if not mk.IsDone():
        raise DirectError("the kernel could not close the gap these faces leave")
    return mk.Shape(), mk
