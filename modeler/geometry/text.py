"""Text as geometry: font outlines turned into flat letters or solid letters.

The outlines come from the font file through OCCT's font builder, so curves
stay exact (the letters are B-spline faces, not polygons). A font is given by
name (``sans-serif``, ``serif``, ``monospace``, ``DejaVu Sans`` ...) and found
through the system's font list, or by a path to a .ttf/.otf file.
"""

from __future__ import annotations

import os

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.Font import (
    Font_FontAspect_Bold,
    Font_FontAspect_BoldItalic,
    Font_FontAspect_Italic,
    Font_FontAspect_Regular,
)
from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.Graphic3d import (
    Graphic3d_HTA_CENTER,
    Graphic3d_HTA_LEFT,
    Graphic3d_HTA_RIGHT,
    Graphic3d_VTA_BOTTOM,
)
from OCP.StdPrs import StdPrs_BRepFont, StdPrs_BRepTextBuilder
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer

from .curves import CurveError, plane_axes

try:  # OCP 8.x
    from OCP.NCollection import NCollection_String
except ImportError:  # OCP 7.x
    from OCP.NCollection import NCollection_Utf8String as NCollection_String  # type: ignore[no-redef]

ALIGNS = {"LEFT": Graphic3d_HTA_LEFT, "CENTER": Graphic3d_HTA_CENTER, "RIGHT": Graphic3d_HTA_RIGHT}
STYLES = {"REGULAR": Font_FontAspect_Regular, "BOLD": Font_FontAspect_Bold, "ITALIC": Font_FontAspect_Italic,
          "BOLDITALIC": Font_FontAspect_BoldItalic}

_fonts: dict[tuple, StdPrs_BRepFont] = {}


def _font(name: str, style: str, size: float) -> StdPrs_BRepFont:
    key = (name, style, size)
    if key in _fonts:
        return _fonts[key]
    f = StdPrs_BRepFont()
    if os.path.splitext(name)[1].lower() in (".ttf", ".otf", ".ttc", ".pfb"):
        if not os.path.isfile(name):
            raise CurveError(f"no font file {name!r}")
        ok = f.Init(NCollection_String(name), size, 0)
    else:
        ok = f.Init(NCollection_String(name), STYLES[style], size)
    if not ok:
        raise CurveError(f"font {name!r} was not found; give a font name such as sans-serif, serif or monospace, "
                         "or the path to a .ttf file")
    _fonts[key] = f
    return f


def faces(shape) -> int:
    ex, n = TopExp_Explorer(shape, TopAbs_FACE), 0
    while ex.More():
        n += 1
        ex.Next()
    return n


def text_shape(text: str, origin, size: float, depth: float = 0.0, font: str = "sans-serif", normal=(0, 0, 1),
               angle: float = 0.0, align: str = "LEFT", style: str = "REGULAR"):
    """Letters of ``text`` standing on ``origin``: baseline along profile X,
    upwards along profile Y, font size ``size``. Flat faces when depth is 0,
    else solid letters ``depth`` thick along the normal (negative: below)."""
    if not text.strip():
        raise CurveError("the text is empty")
    if size <= 0:
        raise CurveError("the size must be positive")
    if align not in ALIGNS:
        raise CurveError(f"align must be one of {', '.join(ALIGNS)}")
    if style not in STYLES:
        raise CurveError(f"style must be one of {', '.join(STYLES)}")
    f = _font(font, style, float(size))
    shape = StdPrs_BRepTextBuilder().Perform(f, NCollection_String(text), gp_Ax3(), ALIGNS[align], Graphic3d_VTA_BOTTOM)
    if shape.IsNull() or faces(shape) == 0:
        raise CurveError(f"the font has no outlines for {text!r}")
    if depth:
        shape = BRepPrimAPI_MakePrism(shape, gp_Vec(0, 0, depth)).Shape()
    x, _, z = plane_axes(normal, angle)
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(gp_Pnt(*map(float, origin)), gp_Dir(*z), gp_Dir(*x)), gp_Ax3())
    return BRepBuilderAPI_Transform(shape, t, True).Shape()
