"""PLAN item 113: FreeCAD documents (.FCStd) read without FreeCAD."""

import os
import tempfile
import zipfile

import pytest
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.BRepTools import BRepTools

from modeler.commands import Processor
from modeler.commands.queries import bbox


def _brep(shape) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".brp", delete=False) as fh:
        tmp = fh.name
    (getattr(BRepTools, "Write_s", None) or BRepTools.Write)(shape, tmp)
    data = open(tmp, "rb").read()
    os.unlink(tmp)
    return data


def _obj_data(name, label, shape_file=None, placement=None, group=None):
    props = [f'<Property name="Label" type="App::PropertyString"><String value="{label}"/></Property>']
    if placement:
        px, py, pz = placement
        props.append('<Property name="Placement" type="App::PropertyPlacement">'
                     f'<PropertyPlacement Px="{px}" Py="{py}" Pz="{pz}" Q0="0" Q1="0" Q2="0" Q3="1" A="0" '
                     'Ox="0" Oy="0" Oz="1"/></Property>')
    if shape_file:
        props.append(f'<Property name="Shape" type="Part::PropertyPartShape"><Part file="{shape_file}"/></Property>')
    if group:
        links = "".join(f'<Link value="{g}"/>' for g in group)
        props.append(f'<Property name="Group" type="App::PropertyLinkList"><LinkList count="{len(group)}">{links}'
                     '</LinkList></Property>')
    return f'<Object name="{name}"><Properties Count="{len(props)}">{"".join(props)}</Properties></Object>'


def make_fcstd(path):
    """A small document the way FreeCAD writes it: a plate with a hole (Part Cut of a Box and a hidden
    Cylinder), and an App::Part "Wheel assembly" moved 100 along X holding a PartDesign Body (its Pad
    hidden inside it)."""
    box = BRepPrimAPI_MakeBox(40, 20, 5).Shape()
    cyl = BRepPrimAPI_MakeCylinder(4, 5).Shape()
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

    cut = BRepAlgoAPI_Cut(box, cyl).Shape()
    disc = BRepPrimAPI_MakeCylinder(10, 3).Shape()
    objects = [("Box", "Part::Box"), ("Cylinder", "Part::Cylinder"), ("Cut", "Part::Cut"),
               ("Part", "App::Part"), ("Body", "PartDesign::Body"), ("Pad", "PartDesign::Pad")]
    data = [_obj_data("Box", "Box", "PartShape.brp"), _obj_data("Cylinder", "Cylinder", "PartShape1.brp"),
            _obj_data("Cut", "Plate with hole", "PartShape2.brp"),
            _obj_data("Part", "Wheel assembly", placement=(100, 0, 0), group=["Body"]),
            _obj_data("Body", "Wheel", "PartShape3.brp", group=["Pad"]),
            _obj_data("Pad", "Pad", "PartShape4.brp")]
    doc = ('<?xml version="1.0" encoding="utf-8"?><Document SchemaVersion="4" ProgramVersion="1.0" FileVersion="1">'
           f'<Objects Count="{len(objects)}">' + "".join(f'<Object type="{t}" name="{n}"/>' for n, t in objects)
           + f'</Objects><ObjectData Count="{len(data)}">' + "".join(data) + "</ObjectData></Document>")

    def vp(name, visible, colour=None):
        props = [f'<Property name="Visibility" type="App::PropertyBool"><Bool value="{str(visible).lower()}"/></Property>']
        if colour is not None:
            props.append(f'<Property name="ShapeColor" type="App::PropertyColor"><PropertyColor value="{colour}"/>'
                         '</Property>')
        return f'<ViewProvider name="{name}"><Properties Count="{len(props)}">{"".join(props)}</Properties></ViewProvider>'

    red = (255 << 24) | (0 << 16) | (0 << 8)
    gui = ('<?xml version="1.0" encoding="utf-8"?><Document SchemaVersion="1"><ViewProviderData Count="6">'
           + vp("Box", False) + vp("Cylinder", False) + vp("Cut", True, red) + vp("Part", True) + vp("Body", True)
           + vp("Pad", False) + "</ViewProviderData></Document>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("Document.xml", doc)
        z.writestr("GuiDocument.xml", gui)
        for i, s in enumerate((box, cyl, cut, disc, disc)):
            z.writestr("PartShape.brp" if i == 0 else f"PartShape{i}.brp", _brep(s))
    return path


def test_import_freecad_document(tmp_path):
    f = make_fcstd(str(tmp_path / "plate.FCStd"))
    p = Processor()
    r = p.run(f'IMPORT, FCSTD, "{f}"')
    assert r.ok, r.message
    m = p.model
    names = {b.name for b in m.bodies.values()}
    assert names == {"Plate_with_hole", "Wheel"}
    assert "2 hidden shapes left out" in r.message
    plate = m.body_by_name("Plate_with_hole")
    assert m.display_color(plate.id) == pytest.approx((1.0, 0.0, 0.0))
    wheel = m.body_by_name("Wheel")
    x0, _y0, _z0, x1, _y1, _z1 = bbox(wheel.shape)
    assert (x0 + x1) / 2 == pytest.approx(100.0, abs=1e-6)  # the App::Part's placement
    assert m.layer_of(wheel.id).name.upper() == "WHEEL_ASSEMBLY"
    rep = p.reports.get("import")
    assert rep and rep["format"] == "FCSTD" and rep["hidden"] == 2


def test_import_all_and_errors(tmp_path):
    f = make_fcstd(str(tmp_path / "plate.FCStd"))
    p = Processor()
    r = p.run(f'IMPORT, FCSTD, "{f}", , ALL')
    assert r.ok and len(p.model.bodies) == 4
    assert sum(1 for b in p.model.bodies if not p.model.is_shown(b)) == 2
    bad = tmp_path / "bad.FCStd"
    bad.write_text("not a zip")
    r = p.run(f'IMPORT, FCSTD, "{bad}"')
    assert not r.ok and "not a FreeCAD document" in r.message
    assert not p.run(f'IMPORT, FCSTD, "{f}", , MESH').ok


def test_saved_project_keeps_the_import(tmp_path):
    f = make_fcstd(str(tmp_path / "plate.FCStd"))
    p = Processor()
    assert p.run(f'IMPORT, FCSTD, "{f}"').ok
    proj = str(tmp_path / "a.m3d")
    assert p.run(f'SAVE, "{proj}"').ok
    os.remove(f)
    q = Processor()
    assert q.run(f'OPEN, "{proj}"').ok and len(q.model.bodies) == 2
