"""Imperfect exact models, the kind that arrive from other programs, written as STEP files.

Each maker returns the path of a file holding one flaw (or a few), built from a plain box so
the right answer after repair is known: a 10 x 10 x 10 solid.
"""

from __future__ import annotations

import os

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Trsf, gp_Vec
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shell, TopoDS_Solid

_FACE = getattr(TopoDS, "Face_s", None) or TopoDS.Face


def _faces(shape):
    out, ex = [], TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        out.append(_FACE(ex.Current()))
        ex.Next()
    return out


def _box(size=10.0):
    return BRepPrimAPI_MakeBox(size, size, size).Shape()


def _moved(shape, dx=0.0, dy=0.0, dz=0.0):
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(dx, dy, dz))
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _compound(shapes):
    b, c = BRep_Builder(), TopoDS_Compound()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


def write(shape, path: str) -> str:
    (getattr(Interface_Static, "SetCVal_s", None) or Interface_Static.SetCVal)("write.step.unit", "MM")
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    assert int(w.Write(path)) == 1
    return path


def loose_faces(folder: str) -> str:
    """The six faces of a box, not joined: a surface model, not a solid."""
    return write(_compound(_faces(_box())), os.path.join(folder, "loose.step"))


def gaps(folder: str, gap: float = 0.02) -> str:
    """Six loose faces, the top one lifted by ``gap``: they do not meet."""
    fs = _faces(_box())
    top = max(range(6), key=lambda i: _centre_z(fs[i]))
    fs[top] = _FACE(_moved(fs[top], dz=gap))
    return write(_compound(fs), os.path.join(folder, "gaps.step"))


def _centre_z(face):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, g)
    return g.CentreOfMass().Z()


def flipped(folder: str) -> str:
    """A solid whose skin has one face turned inward."""
    sew = BRepBuilderAPI_Sewing(1e-6)
    sew.Add(_box())
    sew.Perform()
    fs = _faces(sew.SewedShape())
    b, sh, so = BRep_Builder(), TopoDS_Shell(), TopoDS_Solid()
    b.MakeShell(sh)
    for i, f in enumerate(fs):
        b.Add(sh, f.Reversed() if i == 0 else f)
    b.MakeSolid(so)
    b.Add(so, sh)
    # BREP, not STEP: reading a STEP file already turns faces the right way
    from OCP.BRepTools import BRepTools

    path = os.path.join(folder, "flipped.brep")
    assert (getattr(BRepTools, "Write_s", None) or BRepTools.Write)(so, path)
    return path


def duplicate(folder: str) -> str:
    """Six loose faces of a box and a second copy of one of them."""
    fs = _faces(_box())
    return write(_compound(fs + [_FACE(_moved(fs[0]))]), os.path.join(folder, "duplicate.step"))


def slivers(folder: str, step: float = 0.002) -> str:
    """Two boxes fused with one raised by ``step``: thin faces and short edges along the step."""
    a = _box()
    b = _moved(_box(5.0), 5, 5, 10 - 5 + step)
    return write(BRepAlgoAPI_Fuse(a, b).Shape(), os.path.join(folder, "slivers.step"))


ALL = {"loose": loose_faces, "gaps": gaps, "flipped": flipped, "duplicate": duplicate, "slivers": slivers}
