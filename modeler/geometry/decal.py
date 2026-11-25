"""Pictures on faces: decals (DECAL, a logo or a label on one face) and textures (TEXTURE, a picture
tiled over every face of a body), PLAN item 116.

A decal is drawn as a thin patch just off its face: a rectangle on a flat face, turned by its angle,
or a piece of a slightly bigger cylinder on a round face, so the picture wraps round it. Its middle
is the face's middle moved by dx, dy along the face's own x and y (``frame`` tells which way those
point); the picture keeps its proportions. A texture is drawn face by face, with the picture
repeated so that one tile is ``size`` mm on every face, whatever the face's size.
"""

from __future__ import annotations

import math

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepClass import BRepClass_FaceClassifier
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.Geom import Geom_CylindricalSurface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_ON, TopAbs_REVERSED
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Face
from OCP.gp import gp_Ax1, gp_Ax3, gp_Dir, gp_Pln, gp_Pnt, gp_Pnt2d

_as_face = getattr(TopoDS, "Face_s", None) or TopoDS.Face
_uv_bounds = getattr(BRepTools, "UVBounds_s", None) or BRepTools.UVBounds
_surface_props = getattr(BRepGProp, "SurfaceProperties_s", None) or BRepGProp.SurfaceProperties

PICTURE_TYPES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff")
MAX_TEXTURED_FACES = 1500  # a body with more faces (a mesh) is drawn without its texture


class DecalError(ValueError):
    pass


def image_size(path: str) -> tuple[int, int]:
    """A picture's width and height in pixels; DecalError if it cannot be read."""
    try:
        from OCP.Image import Image_AlienPixMap
        from OCP.TCollection import TCollection_AsciiString

        img = Image_AlienPixMap()
        if img.Load(TCollection_AsciiString(path)) and img.SizeX() and img.SizeY():
            return int(img.SizeX()), int(img.SizeY())
    except Exception:  # noqa: BLE001  (OCCT built without image support: try Pillow)
        pass
    try:
        from PIL import Image

        with Image.open(path) as im:
            return im.size
    except Exception as exc:  # noqa: BLE001
        raise DecalError(f"cannot read the picture {path} ({exc})") from None


def _vec(d) -> tuple[float, float, float]:
    return (d.X(), d.Y(), d.Z())


def frame(face: TopoDS_Face) -> dict:
    """Where a decal on this face goes: {kind (FLAT or ROUND), centre, x, y, normal (outward), radius}.
    x and y are the directions dx and dy move along (on a round face x goes round, y along the axis)."""
    s = BRepAdaptor_Surface(face)
    reversed_ = face.Orientation() == TopAbs_REVERSED
    props = GProp_GProps()
    _surface_props(face, props)
    c = props.CentreOfMass()
    if s.GetType() == GeomAbs_Plane:
        pos = s.Plane().Position()
        z, x = pos.Direction(), pos.XDirection()
        if reversed_:
            z = z.Reversed()
        ax = gp_Ax3(gp_Pnt(c.X(), c.Y(), c.Z()), z, x)
        return {"kind": "FLAT", "centre": (c.X(), c.Y(), c.Z()), "x": _vec(ax.XDirection()),
                "y": _vec(ax.YDirection()), "normal": _vec(z), "radius": 0.0}
    if s.GetType() == GeomAbs_Cylinder:
        cyl = s.Cylinder()
        u0, u1, v0, v1 = _uv_bounds(face)
        um, vm = (u0 + u1) / 2, (v0 + v1) / 2
        p = s.Value(um, vm)
        ax = cyl.Position()
        o, a = ax.Location(), ax.Direction()
        # outward: from the axis to the middle point (a hole's face looks inward)
        t = (p.X() - o.X()) * a.X() + (p.Y() - o.Y()) * a.Y() + (p.Z() - o.Z()) * a.Z()
        foot = (o.X() + a.X() * t, o.Y() + a.Y() * t, o.Z() + a.Z() * t)
        n = [p.X() - foot[0], p.Y() - foot[1], p.Z() - foot[2]]
        ln = math.sqrt(sum(q * q for q in n)) or 1.0
        n = [q / ln for q in n]
        if reversed_:
            n = [-q for q in n]
        xdir = (a.Y() * n[2] - a.Z() * n[1], a.Z() * n[0] - a.X() * n[2], a.X() * n[1] - a.Y() * n[0])
        return {"kind": "ROUND", "centre": (p.X(), p.Y(), p.Z()), "x": xdir, "y": _vec(a), "normal": tuple(n),
                "radius": cyl.Radius(), "u": um, "v": vm, "inside": reversed_}
    raise DecalError("a decal goes on a flat or a round (cylindrical) face")


def patch(face: TopoDS_Face, width: float, height: float, dx: float = 0.0, dy: float = 0.0, angle: float = 0.0,
          lift: float = 0.0) -> TopoDS_Face:
    """The thin patch a decal is drawn on (its picture spans it exactly: u across, v up)."""
    if width <= 0 or height <= 0:
        raise DecalError("the decal's size must be more than 0")
    f = frame(face)
    if f["kind"] == "FLAT":
        c = [f["centre"][i] + f["x"][i] * dx + f["y"][i] * dy + f["normal"][i] * lift for i in range(3)]
        a = math.radians(angle)
        x = [f["x"][i] * math.cos(a) + f["y"][i] * math.sin(a) for i in range(3)]
        pln = gp_Pln(gp_Ax3(gp_Pnt(*c), gp_Dir(*f["normal"]), gp_Dir(*x)))
        return BRepBuilderAPI_MakeFace(pln, -width / 2, width / 2, -height / 2, height / 2).Face()
    if abs(math.remainder(angle, 180.0)) > 1e-6:
        raise DecalError("on a round face the angle is 0 or 180 (the picture wraps round the face)")
    s = BRepAdaptor_Surface(face)
    cyl = s.Cylinder()
    r = cyl.Radius()
    if width >= 2 * math.pi * r:
        raise DecalError(f"the decal is wider than the way round the face ({2 * math.pi * r:.4g})")
    rr = r - lift if f["inside"] else r + lift
    ax = cyl.Position()
    flip = abs(math.remainder(angle, 360.0)) > 90
    if flip:  # upside down: the same cylinder with its axis the other way
        ax = ax.Mirrored(gp_Ax1(ax.Location(), ax.XDirection()))
    surf = Geom_CylindricalSurface(ax, rr)
    centre = s.Value(f["u"], f["v"])
    # the middle point's (u, v) on the (maybe flipped) cylinder
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

    pr = GeomAPI_ProjectPointOnSurf(centre, surf)
    um, vm = pr.LowerDistanceParameters()
    du = width / rr
    sign = -1.0 if f["inside"] else 1.0  # seen from inside a hole, round is the other way
    um += sign * dx / rr * (-1.0 if flip else 1.0)
    vm += dy * (-1.0 if flip else 1.0)
    face_out = BRepBuilderAPI_MakeFace(surf, um - du / 2, um + du / 2, vm - height / 2, vm + height / 2, 1e-7).Face()
    if f["inside"]:
        face_out.Reverse()
    return face_out


def overhangs(face: TopoDS_Face, patch_face: TopoDS_Face) -> bool:
    """True when a corner or edge middle of the patch lies off the face (the decal hangs over its border)."""
    s = BRepAdaptor_Surface(patch_face)
    u0, u1, v0, v1 = _uv_bounds(patch_face)
    surf = BRep_Tool.Surface_s(face) if hasattr(BRep_Tool, "Surface_s") else BRep_Tool.Surface(face)
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

    for fu, fv in ((0, 0), (1, 0), (1, 1), (0, 1), (0.5, 0), (1, 0.5), (0.5, 1), (0, 0.5)):
        q = s.Value(u0 + (u1 - u0) * fu, v0 + (v1 - v0) * fv)
        pr = GeomAPI_ProjectPointOnSurf(q, surf)
        if not pr.NbPoints():
            return True
        u, v = pr.LowerDistanceParameters()
        state = BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), 1e-6).State()
        if state not in (TopAbs_IN, TopAbs_ON):
            return True
    return False


def tiles(face: TopoDS_Face, size: float) -> tuple[float, float]:
    """How many times a texture of tiles ``size`` mm repeats across a face, along u and along v."""
    s = BRepAdaptor_Surface(face)
    u0, u1, v0, v1 = _uv_bounds(face)

    def length(along_u: bool) -> float:
        tot = 0.0
        for iso in (0.25, 0.5, 0.75):  # the mean of three iso lines: a cone's or sphere's ends differ
            prev = None
            run = 0.0
            for k in range(13):
                t = k / 12
                q = s.Value(u0 + (u1 - u0) * t, v0 + (v1 - v0) * iso) if along_u else \
                    s.Value(u0 + (u1 - u0) * iso, v0 + (v1 - v0) * t)
                if prev is not None:
                    run += q.Distance(prev)
                prev = q
            tot += run
        return tot / 3

    return max(length(True) / size, 1e-3), max(length(False) / size, 1e-3)


def size_of(shape) -> float:
    """The biggest side of a shape's bounding box (at least 1e-6)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    (getattr(BRepBndLib, "Add_s", None) or BRepBndLib.Add)(shape, box)
    if box.IsVoid():
        return 1e-6
    a, b = box.CornerMin(), box.CornerMax()
    return max(b.X() - a.X(), b.Y() - a.Y(), b.Z() - a.Z(), 1e-6)


def faces(shape) -> list[TopoDS_Face]:
    out = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        out.append(_as_face(ex.Current()))
        ex.Next()
    return out
