"""FreeCAD documents (.FCStd) read without FreeCAD (PLAN item 113).

An .FCStd file is a zip: Document.xml lists the objects and their properties, each shape is a
BREP file beside it (PartShape.brp, PartShape1.brp ...; FreeCAD's own BREP is OCCT's, so it reads
exactly), and GuiDocument.xml holds what the window showed: each object's visibility and colour.

What comes in: the shapes of the objects that were shown (a PartDesign Body's result, a Part
feature's shape, an imported solid ...), with their labels as names and their colours, placed
where FreeCAD had them, inside App::Part containers too. The containers and groups they sat in
come back as the path of labels ("Assembly/Wheel"), which IMPORT turns into layers. Shapes that
were hidden (the tools a boolean used, the features inside a Body) are left out unless asked for.
"""

from __future__ import annotations

import math
import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

from OCP.BRep import BRep_Builder
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Quaternion, gp_Trsf, gp_Vec
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Shape


class FcstdError(Exception):
    pass


@dataclass
class Obj:
    name: str
    type: str
    label: str = ""
    shape_file: str = ""
    placement: gp_Trsf | None = None
    group: list = field(default_factory=list)  # names of the objects it holds (App::Part, groups)
    visible: bool | None = None
    colour: tuple | None = None


@dataclass
class Piece:
    shape: TopoDS_Shape
    name: str
    label: str
    type: str
    path: str  # the containers it sat in: "Assembly/Wheel" (empty: none)
    colour: tuple | None
    visible: bool


CONTAINERS = ("App::Part", "App::DocumentObjectGroup", "App::DocumentObjectGroupPython", "App::LinkGroup")


def _placement(el) -> gp_Trsf | None:
    pp = el.find("PropertyPlacement")
    if pp is None:
        return None
    try:
        px, py, pz = (float(pp.get(k, "0")) for k in ("Px", "Py", "Pz"))
        q = [float(pp.get(k, "0")) for k in ("Q0", "Q1", "Q2", "Q3")]
    except ValueError:
        return None
    t = gp_Trsf()
    if any(q) and not (q[0] == q[1] == q[2] == 0 and abs(q[3]) == 1):
        n = math.sqrt(sum(c * c for c in q)) or 1.0
        t.SetRotation(gp_Quaternion(q[0] / n, q[1] / n, q[2] / n, q[3] / n))
    move = gp_Trsf()
    move.SetTranslation(gp_Vec(px, py, pz))
    return move.Multiplied(t)


def _colour(value: str) -> tuple | None:
    """FreeCAD packs a colour as one 32-bit number: red, green, blue, alpha (alpha 0 is opaque)."""
    try:
        v = int(value) & 0xFFFFFFFF
    except ValueError:
        return None
    return (round(((v >> 24) & 255) / 255, 4), round(((v >> 16) & 255) / 255, 4), round(((v >> 8) & 255) / 255, 4))


def read_objects(z: zipfile.ZipFile) -> dict[str, Obj]:
    try:
        doc = ET.fromstring(z.read("Document.xml"))
    except KeyError:
        raise FcstdError("no Document.xml inside: not a FreeCAD document") from None
    except ET.ParseError as exc:
        raise FcstdError(f"Document.xml cannot be read: {exc}") from None
    objs: dict[str, Obj] = {}
    for o in doc.iter("Objects"):
        for el in o.findall("Object"):
            n = el.get("name")
            if n:
                objs[n] = Obj(n, el.get("type", ""))
    for od in doc.iter("ObjectData"):
        for el in od.findall("Object"):
            ob = objs.get(el.get("name", ""))
            if ob is None:
                continue
            for prop in el.iter("Property"):
                pname = prop.get("name")
                if pname == "Label":
                    s = prop.find("String")
                    if s is not None:
                        ob.label = s.get("value", "")
                elif pname == "Shape":
                    part = prop.find("Part")
                    if part is not None and part.get("file"):
                        ob.shape_file = part.get("file")
                elif pname == "Placement" and ob.placement is None:
                    ob.placement = _placement(prop)
                elif pname == "Group":
                    ll = prop.find("LinkList")
                    if ll is not None:
                        ob.group = [lk.get("value") for lk in ll.findall("Link") if lk.get("value")]
                elif pname == "Visibility":
                    b = prop.find("Bool")
                    if b is not None:
                        ob.visible = b.get("value", "true").lower() == "true"
    # the window's side: visibility and colour
    try:
        gui = ET.fromstring(z.read("GuiDocument.xml"))
    except (KeyError, ET.ParseError):
        gui = None
    if gui is not None:
        for vp in gui.iter("ViewProvider"):
            ob = objs.get(vp.get("name", ""))
            if ob is None:
                continue
            for prop in vp.iter("Property"):
                pname = prop.get("name")
                if pname == "Visibility":
                    b = prop.find("Bool")
                    if b is not None:
                        ob.visible = b.get("value", "true").lower() == "true"
                elif pname == "ShapeColor":
                    c = prop.find("PropertyColor")
                    if c is not None:
                        ob.colour = _colour(c.get("value", ""))
    return objs


def _read_brep(z: zipfile.ZipFile, name: str) -> TopoDS_Shape | None:
    try:
        data = z.read(name)
    except KeyError:
        return None
    with tempfile.NamedTemporaryFile("wb", suffix=".brp", delete=False) as fh:
        fh.write(data)
        tmp = fh.name
    try:
        shape = TopoDS_Shape()
        read = getattr(BRepTools, "Read_s", None) or BRepTools.Read
        ok = read(shape, tmp, BRep_Builder())
        return shape if ok and not shape.IsNull() else None
    finally:
        os.unlink(tmp)


def read(path: str, hidden: bool = False) -> tuple[list[Piece], dict]:
    """The document's shapes (only the shown ones unless ``hidden``) and counts for the answer."""
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise FcstdError(f"not a FreeCAD document (an .FCStd file is a zip): {exc}") from None
    with z:
        objs = read_objects(z)
        # each object's containers, outermost first
        parent: dict[str, str] = {}
        for ob in objs.values():
            if ob.type in CONTAINERS or ob.type.startswith("PartDesign::Body"):
                for child in ob.group:
                    parent.setdefault(child, ob.name)

        def chain(n: str) -> list[Obj]:
            out, seen = [], set()
            while n in parent and n not in seen:
                seen.add(n)
                n = parent[n]
                out.append(objs[n])
            return out[::-1]

        pieces, counts = [], {"objects": len(objs), "shapes": 0, "hidden": 0, "unreadable": 0}
        for ob in objs.values():
            if not ob.shape_file or ob.type in CONTAINERS:
                continue
            ups = chain(ob.name)
            # a feature inside a Body is the Body's history: the Body's own shape is the result
            if any(u.type.startswith("PartDesign::Body") for u in ups):
                continue
            counts["shapes"] += 1
            shown = ob.visible is not False and all(u.visible is not False for u in ups if u.type in CONTAINERS)
            if not shown:
                counts["hidden"] += 1
                if not hidden:
                    continue
            shape = _read_brep(z, ob.shape_file)
            if shape is None:
                counts["unreadable"] += 1
                continue
            t = gp_Trsf()
            for u in ups:  # App::Part placements are not in the stored shape
                if u.type == "App::Part" and u.placement is not None:
                    t = t.Multiplied(u.placement)
            if t.TranslationPart().Modulus() > 0 or t.GetRotation().GetRotationAngle() != 0:
                shape = shape.Moved(TopLoc_Location(t))
            path_ = "/".join(u.label or u.name for u in ups if u.type in CONTAINERS)
            pieces.append(Piece(shape, ob.name, ob.label or ob.name, ob.type, path_, ob.colour, shown))
    return pieces, counts
