"""STEP files with part names and colours (the kernel's document form of STEP).

A plain STEP read gives shapes only. Read as a document, the file also gives each part's name
and colour, and an assembly's tree of parts. ``read`` walks that tree down to the single parts
(placing each where the assembly puts it) and returns them with their names and colours;
``write`` does the reverse for a list of bodies, so a model written and read back keeps both.
"""

from __future__ import annotations

from dataclasses import dataclass

from OCP.Quantity import Quantity_Color, Quantity_TOC_sRGB
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape
from OCP.XCAFDoc import XCAFDoc_ColorCurv, XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_DocumentTool

try:
    from OCP.collections import Sequence_TDF_Label as _Labels
except ImportError:  # OCP 7.x
    from OCP.TDF import TDF_LabelSequence as _Labels  # type: ignore[no-redef]

Colour = tuple[float, float, float]


@dataclass
class Part:
    shape: TopoDS_Shape
    name: str = ""
    color: Colour | None = None


def _doc() -> TDocStd_Document:
    return TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))


def _name(label: TDF_Label) -> str:
    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString().strip()
    return ""


def _rgb(c: Quantity_Color) -> Colour:
    r, g, b = c.Values(Quantity_TOC_sRGB)
    return (round(r, 4), round(g, 4), round(b, 4))


def _colour(ct, *things) -> Colour | None:
    """The first colour set on any of ``things`` (labels or shapes): whole-part, then surface."""
    c = Quantity_Color()
    for kind in (XCAFDoc_ColorGen, XCAFDoc_ColorSurf, XCAFDoc_ColorCurv):
        for t in things:
            if t is None:
                continue
            try:
                if ct.GetColor(t, kind, c):
                    return _rgb(c)
            except TypeError:
                continue
    return None


def _face_colour(ct, shape: TopoDS_Shape) -> Colour | None:
    """The colour of the faces, when they all share one (files that colour faces, not parts)."""
    found: set[Colour] = set()
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    n = 0
    while ex.More() and n < 2000:
        col = _colour(ct, ex.Current())
        if col is None:
            return None
        found.add(col)
        if len(found) > 1:
            return None
        ex.Next()
        n += 1
    return found.pop() if found else None


def read(path: str, pmi: list | None = None) -> list[Part]:
    """Every single part in the file, placed, with its name and colour (None where the file has
    none). An empty list when the file holds no shapes; IOError when it cannot be read.
    With a list for ``pmi``, the sizes, tolerances and datums in the file (AP242) are added to it
    as records (geometry/step_pmi.py)."""
    r = STEPCAFControl_Reader()
    r.SetNameMode(True)
    r.SetColorMode(True)
    r.SetLayerMode(False)
    if pmi is not None:
        from OCP.STEPCAFControl import STEPCAFControl_Controller

        (getattr(STEPCAFControl_Controller, "Init_s", None) or STEPCAFControl_Controller.Init)()
        r.SetGDTMode(True)
    if int(r.ReadFile(path)) != 1:  # IFSelect_RetDone
        raise OSError(f"could not read STEP file {path}")
    doc = _doc()
    if not r.Transfer(doc):
        raise OSError(f"could not read the shapes in {path}")
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    out: list[Part] = []

    def walk(label: TDF_Label, loc: TopLoc_Location, name: str, colour: Colour | None) -> None:
        ref = TDF_Label()
        if st.IsReference_s(label) and st.GetReferredShape_s(label, ref):
            # an instance: its own placement, name and colour win over the part it refers to
            here = st.GetLocation_s(label)
            own = _name(label)
            walk(ref, loc.Multiplied(here), own or name, _colour(ct, label) or colour)
            return
        name = _name(label) if not name or _is_generic(name) else name
        if st.IsAssembly_s(label):
            kids = _Labels()
            st.GetComponents_s(label, kids, False)
            for i in range(1, kids.Length() + 1):
                walk(kids.Value(i), loc, "", _colour(ct, label) or colour)
            return
        shape = st.GetShape_s(label)
        if shape.IsNull():
            return
        col = colour or _colour(ct, label, shape) or _face_colour(ct, shape)
        out.append(Part(shape.Moved(loc) if not loc.IsIdentity() else shape, "" if _is_generic(name) else name, col))

    free = _Labels()
    st.GetFreeShapes(free)
    for i in range(1, free.Length() + 1):
        walk(free.Value(i), TopLoc_Location(), "", None)
    if pmi is not None:
        from . import step_pmi

        try:
            pmi.extend(step_pmi.read(doc))
        except Exception:  # noqa: BLE001 - annotations a file gets wrong must not stop the shapes
            pass
    return out


def _is_generic(name: str) -> bool:
    """Names the writer of a file made up rather than a person (SOLID, Open CASCADE STEP translator ...)."""
    n = name.strip().upper()
    return (not n or n.isdigit() or n in {"SOLID", "SHELL", "FACE", "COMPOUND", "BODY", "PART"}
            or n.startswith("OPEN CASCADE"))


def write(path: str, parts: list[Part], units: str = "MM", pmi: list | None = None, unit_mm: float = 1.0) -> bool:
    """Write ``parts`` as one STEP file, each with its name and colour. With ``pmi`` records (sizes,
    tolerances, datums: geometry/step_pmi.py) the file is AP242 and carries them on the faces."""
    from OCP.Interface import Interface_Static

    setc = getattr(Interface_Static, "SetCVal_s", None) or Interface_Static.SetCVal
    getc = getattr(Interface_Static, "CVal_s", None) or Interface_Static.CVal
    setc("write.step.unit", units)
    doc = _doc()
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    ct = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    labels = []
    for part in parts:
        label = st.AddShape(part.shape, False)
        labels.append((label, part.shape))
        if part.name:
            TDataStd_Name.Set_s(label, TCollection_ExtendedString(part.name))
        if part.color is not None:
            ct.SetColor(label, Quantity_Color(*part.color, Quantity_TOC_sRGB), XCAFDoc_ColorGen)
    schema = None
    if pmi:
        from OCP.STEPCAFControl import STEPCAFControl_Controller

        from . import step_pmi

        # the annotation writer needs the document controller set up: without it, it crashes on
        # datums
        (getattr(STEPCAFControl_Controller, "Init_s", None) or STEPCAFControl_Controller.Init)()
        if step_pmi.add(doc, st, labels, pmi, unit_mm):
            schema = getc("write.step.schema")
            setc("write.step.schema", "AP242DIS")  # the schema that carries annotations
    w = STEPCAFControl_Writer()
    w.SetNameMode(True)
    w.SetColorMode(True)
    if schema is not None:
        w.SetDimTolMode(True)
    try:
        if not w.Transfer(doc):
            return False
        return int(w.Write(path)) == 1
    finally:
        if schema is not None:
            setc("write.step.schema", schema)
