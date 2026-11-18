"""A nicer picture of the model than the working view: OCCT's ray tracing
with shadows, reflections and smoothed edges, a floor that catches the
shadows, a sun light and a soft fill light, and a look for each body from
its MATERIAL (steel and aluminium shine, brass and copper are warm, glass
is clear, plastics and wood are matte).

``render`` changes the view only while it draws: the camera, lights,
materials, rendering settings and edges are put back afterwards. A
turntable turns the camera round the model's upright axis and saves one
picture per step (and an animated GIF when Pillow is installed).
"""

from __future__ import annotations

import math
import os

LOOKS = {  # MATERIAL -> (OCCT material, reflective)
    "STEEL": ("STEEL", True), "STAINLESS": ("CHROME", True), "CASTIRON": ("PEWTER", False),
    "ALUMINIUM": ("ALUMINIUM", True), "TITANIUM": ("PEWTER", True), "COPPER": ("COPPER", True),
    "BRASS": ("BRASS", True), "ABS": ("PLASTIC", False), "NYLON": ("PLASTIC", False),
    "PLA": ("SHINY_PLASTIC", False), "RUBBER": ("PLASTER", False), "WOOD": ("PLASTER", False),
    "GLASS": ("GLASS", True),
}


class RenderError(RuntimeError):
    pass


def _material(name: str):
    from OCP.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial

    return Graphic3d_MaterialAspect(getattr(Graphic3d_NameOfMaterial, "Graphic3d_NOM_" + name))


def _bounds(shapes):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    for s in shapes:
        (getattr(BRepBndLib, "Add_s", None) or BRepBndLib.Add)(s, box)
    if box.IsVoid():
        raise RenderError("there is nothing shown to render")
    a, b = box.CornerMin(), box.CornerMax()
    return (a.X(), a.Y(), a.Z()), (b.X(), b.Y(), b.Z())


def _floor(lo, hi):
    """A wide thin slab just under the model, to catch the shadows."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt

    size = max(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], 1e-6)
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    r = 2.5 * size
    t = 0.01 * size
    return BRepPrimAPI_MakeBox(gp_Pnt(cx - r, cy - r, lo[2] - t - 1e-3 * size), gp_Pnt(cx + r, cy + r,
                                                                                         lo[2] - 1e-3 * size)).Shape()


def render(vp, path: str, width: int, height: int, view: str = "", frames: int = 0, floor: bool = True,
           shadows: bool = True) -> list[str]:
    """Save a ray-traced picture of the shown bodies (frames > 1: a turntable of that many pictures).
    Returns the files written."""
    if not vp._initialized:
        raise RenderError("there is no 3D view to render with")
    from OCP.AIS import AIS_Shape
    from OCP.Graphic3d import (Graphic3d_Camera, Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial,
                               Graphic3d_RenderingMode)
    from OCP.Image import Image_AlienPixMap
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
    from OCP.TCollection import TCollection_AsciiString
    from OCP.V3d import V3d_AmbientLight, V3d_DirectionalLight
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf

    m = vp.model
    ids = [b for b in m.shown_ids() if b in vp._ais]
    if not ids:
        raise RenderError("there is nothing shown to render")
    lo, hi = _bounds([m.bodies[b].shape for b in ids])
    ctx, v = vp.context, vp.view
    cam = v.Camera()
    saved_cam = Graphic3d_Camera()
    saved_cam.Copy(cam)
    rp = v.ChangeRenderingParams()
    # (copies: the bindings hand fields such as Method back by reference, which would change along)
    saved_rp = {k: _copy(getattr(rp, k)) for k in ("Method", "IsShadowEnabled", "IsReflectionEnabled",
                                            "IsAntialiasingEnabled", "IsTransparentShadowEnabled",
                                            "RaytracingDepth")}
    saved_mat = {}
    saved_bounds = {}
    extra = []
    lights = []
    written: list[str] = []
    try:
        # looks
        for b in ids:
            ais = vp._ais[b]
            saved_mat[b] = ais.Material()
            look = LOOKS.get((m.bodies[b].material or "").upper())
            colour = Quantity_Color()
            ais.Color(colour)
            if look:
                ais.SetMaterial(_material(look[0]))
            shade = colour
            if look and look[1] and look[0] != "GLASS":  # metals: a darker base, or the shine burns out white
                shade = Quantity_Color(colour.Red() * 0.55, colour.Green() * 0.55, colour.Blue() * 0.55,
                                       Quantity_TOC_RGB)
            ais.SetColor(shade)  # the body's colour; the material gives the shine
            dr = ais.Attributes()
            saved_bounds[b] = dr.FaceBoundaryDraw()
            dr.SetFaceBoundaryDraw(False)
            ctx.Redisplay(ais, False, True)
        # camera, fitted to the bodies before the floor is there
        name = (view or "").strip().upper()
        if name.count(",") == 2:
            v.SetProj(*(float(q) for q in name.split(",")))
            v.SetUp(0, 0, 1)
        elif name:
            from .occ_view import _VIEWS

            if name not in _VIEWS:
                raise RenderError(f"unknown view {view}")
            v.SetProj(_VIEWS[name])
        if name:
            v.FitAll(0.05, False)
        if floor:
            f = AIS_Shape(_floor(lo, hi))
            f.SetMaterial(_material("PLASTER"))
            f.SetColor(Quantity_Color(0.72, 0.72, 0.71, Quantity_TOC_RGB))
            f.Attributes().SetFaceBoundaryDraw(False)
            ctx.Display(f, 1, -1, False)
            extra.append(f)
        # lights: a sun from above and behind the left shoulder, a soft fill, some ambient
        v.SetLightOff()
        sun = V3d_DirectionalLight(gp_Dir(0.35, 0.55, -1.0), Quantity_Color(1.0, 0.97, 0.92, Quantity_TOC_RGB))
        sun.SetIntensity(0.65)
        if hasattr(sun, "SetCastShadows"):
            sun.SetCastShadows(shadows)
        fill = V3d_DirectionalLight(gp_Dir(-0.6, -0.3, -0.4), Quantity_Color(0.75, 0.8, 0.9, Quantity_TOC_RGB))
        fill.SetIntensity(0.2)
        if hasattr(fill, "SetCastShadows"):
            fill.SetCastShadows(False)
        amb = V3d_AmbientLight(Quantity_Color(0.3, 0.3, 0.31, Quantity_TOC_RGB))
        for light in (sun, fill, amb):
            vp.viewer.AddLight(light)
            v.SetLightOn(light)
            lights.append(light)
        rp.Method = Graphic3d_RenderingMode.Graphic3d_RM_RAYTRACING
        rp.IsShadowEnabled = shadows
        rp.IsReflectionEnabled = True
        rp.IsAntialiasingEnabled = True
        rp.IsTransparentShadowEnabled = True
        rp.RaytracingDepth = 3
        v.TriedronErase()
        n = max(1, frames)
        centre = gp_Pnt((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
        step = gp_Trsf()
        step.SetRotation(gp_Ax1(centre, gp_Dir(0, 0, 1)), 2 * math.pi / n)
        stem, ext = os.path.splitext(path)
        ext = ext or ".png"
        for k in range(n):
            if k:
                cam.Transform(step)
            v.Redraw()
            pix = Image_AlienPixMap()
            out = path if n == 1 else f"{stem}_{k:03d}{ext}"
            os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
            if not (v.ToPixMap(pix, int(width), int(height)) and pix.Save(TCollection_AsciiString(out))):
                raise RenderError(f"could not save {out}")
            written.append(out)
        if n > 1:
            try:
                from PIL import Image

                imgs = [Image.open(q).convert("P", palette=Image.ADAPTIVE) for q in written]
                gif = stem + ".gif"
                imgs[0].save(gif, save_all=True, append_images=imgs[1:], duration=80, loop=0)
                written.append(gif)
            except ImportError:
                pass
        return written
    finally:
        for light in lights:
            v.SetLightOff(light)
            vp.viewer.DelLight(light)
        v.SetLightOn()  # the viewer's own lights again
        for k, val in saved_rp.items():
            setattr(rp, k, val)
        for f in extra:
            ctx.Remove(f, False)
        for b, mat in saved_mat.items():
            ais = vp._ais.get(b)
            if ais is None:
                continue
            colour = Quantity_Color()
            ais.Color(colour)
            ais.SetMaterial(mat if not isinstance(mat, Graphic3d_NameOfMaterial) else Graphic3d_MaterialAspect(mat))
            ais.SetColor(colour)
            ais.Attributes().SetFaceBoundaryDraw(saved_bounds[b])
            ctx.Redisplay(ais, False, True)
        cam.Copy(saved_cam)
        vp._apply_background()  # (also puts the axes marker back)
        v.Redraw()


def _copy(v):
    if isinstance(v, (bool, int, float)):
        return v
    try:
        return type(v)(int(v))  # an enum
    except (TypeError, ValueError):
        return v
