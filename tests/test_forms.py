"""Fill-in forms (gui/forms.py): every command can be built without typing.

These run headless: a form is plain data plus functions that turn field
values into command text, and command text back into field values.
"""

import os

import pytest

from modeler.commands import REGISTRY, Processor
from modeler.gui import forms as F

HERE = os.path.dirname(__file__)
SCRIPTS = os.path.join(HERE, "..", "scripts")


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def test_every_model_command_has_a_form_or_another_gui_route():
    assert F.missing_forms() == []
    # and the exceptions are real commands, so the list cannot go stale silently
    assert F.NO_FORM <= set(REGISTRY)


def test_every_form_is_in_the_menu_once():
    names = [n for _cat, ns in F.CATEGORIES for n in ns]
    assert len(names) == len(set(names))
    assert set(F.specs()) == set(names)


def test_fresh_solid_forms_make_a_part_with_ok_alone(p):
    for name in ("BLOCK", "CYL", "TUBE", "SPHERE", "CONE", "TORUS", "WEDGE"):
        sp = F.spec(name)
        text = F.build(sp, F.initial(p, sp))
        ok(p, text)
    assert len(p.model.bodies) == 7
    assert p.history[0].text == "BLOCK, 0, 0, 0, 20, 10, 5"


def test_trailing_defaults_are_left_out_and_gaps_kept(p):
    sp = F.spec("HOLE")
    vals = {"b": "plate", "x": "20, 10, 5", "d": "6", "depth": "", "kind": "CSINK", "d2": "12", "dx": "0, 0, 0"}
    assert F.build(sp, vals) == "HOLE, plate, 20, 10, 5, 6, , CSINK, 12"
    vals = {"b": "plate", "x": "20, 10, 5", "d": "6", "kind": "SIMPLE", "tip": "118"}
    assert F.build(sp, vals) == "HOLE, plate, 20, 10, 5, 6, , SIMPLE, , , 118"
    cyl = F.spec("CYL")
    assert F.build(cyl, {"x": "0,0,0", "r": "R", "h": "2*R", "dx": "0, 0, 1"}) == "CYL, 0, 0, 0, R, 2*R"
    assert F.build(cyl, {"x": "0,0,0", "r": "4", "h": "9", "dx": "1, 0, 0"}) == "CYL, 0, 0, 0, 4, 9, 1, 0, 0"


def test_required_values_are_asked_for(p):
    with pytest.raises(F.FormError, match="Radius: needed"):
        F.build(F.spec("SPHERE"), {"x": "0,0,0"})
    with pytest.raises(F.FormError, match="three numbers"):
        F.build(F.spec("SPHERE"), {"x": "1, 2", "r": "3"})


def test_keyword_variants(p):
    plane = F.spec("PLANE")
    assert F.build(plane, {"name": "top", "id": "6", "offset": ""}, "FACE") == "PLANE, top, FACE, 6"
    assert F.build(plane, {"name": "m", "f": "1, 2"}, "MID") == "PLANE, m, MID, 1, 2"
    assert F.build(plane, {"name": "q", "p": "0,0,5", "n": "0,1,1"}, "PN") == "PLANE, q, PN, 0, 0, 5, 0, 1, 1"
    assert F.build(F.spec("AXIS"), {"name": "a"}, "Z") == "AXIS, a, Z"
    arr = F.spec("ARRAY")
    assert F.build(arr, {"b": "1", "n": "4", "d": "20, 0, 0", "fuse": "1"}, "LINEAR") == \
        "ARRAY, LINEAR, 1, 4, 20, 0, 0, FUSE"
    assert F.build(arr, {"b": "1", "n": "6", "angle": "360", "p": "", "d": "0, 0, 1"}, "POLAR") == "ARRAY, POLAR, 1, 6"
    sel = F.spec("SEL")
    assert F.build(sel, {"mode": "S", "kind": "FACE", "crit": "NORMAL", "d": "0,0,-1"}, "NORMAL") == \
        "SEL, S, FACE, NORMAL, 0, 0, -1"
    assert F.build(sel, {"mode": "NONE"}, "NONE") == "SEL, NONE"
    assert F.build(F.spec("SKETCH"), {"name": "s1", "id": "6"}, "FACE") == "SKETCH, s1, FACE, 6"
    assert F.build(F.spec("SKETCH"), {"name": "s1", "on": "top"}, "PLANE") == "SKETCH, s1, top"


def test_lists_and_flags(p):
    pts = "0, 0, 0\n10, 0, 0\n(10, 10, 5)\ncorner"
    assert F.build(F.spec("POLYLINE"), {"pts": pts, "close": "1"}) == \
        "POLYLINE, (0, 0, 0), (10, 0, 0), (10, 10, 5), corner, CLOSE"
    assert F.build(F.spec("LOFT"), {"s": "a, b, c", "ruled": "1", "surface": ""}) == "LOFT, a, b, c, RULED"
    assert F.build(F.spec("SUBTRACT"), {"a": "plate", "b": "4, 5, 6"}) == "SUBTRACT, plate, 4, 5, 6"
    assert F.build(F.spec("EXPORT"), {"format": "STEP", "file": "C:\\work\\part one.step"}) == \
        'EXPORT, STEP, "C:\\work\\part one.step"'
    assert F.build(F.spec("MIRROR"), {"b": "1", "copy": "0"}) == "MIRROR, 1, , , , , , , 0"
    assert F.build(F.spec("="), {"name": "W", "value": "40"}) == "W = 40"


def test_selection_fills_the_form(p):
    ok(p, "BLOCK, 0,0,0, 40,30,8\nNAME, LAST, plate\nBLOCK, 50,0,0, 5,5,5\nPICK, FACE, 6")
    hole = F.spec("HOLE")
    vals = F.initial(p, hole)
    assert vals["b"] == "plate"
    assert vals["x"] == "20, 15, 8"  # the middle of the picked top face
    ok(p, F.build(hole, vals))
    assert len(p.model.body_by_name("plate").maps["FACE"]) == 7
    # bodies picked in the view become the boolean's inputs, in order
    plate = p.model.body_by_name("plate").id
    ok(p, f"PICK, BODY, 2\nPICK, BODY, {plate}, A")
    vals = F.initial(p, F.spec("UNION"))
    assert (vals["a"], vals["b"]) == ("2", "plate")
    # a datum name is offered fresh
    assert F.initial(p, F.spec("PLANE"), "FACE")["name"] == "P1"


def test_options_list_what_the_model_has(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, base\nPLANE, top, XY, 10\nAXIS, up, Z\nSKETCH, s1, XY\nSRECT, 0,0, 5,5\nENDSKETCH")
    body = F.Field("b", "", "body", required=True)
    assert F.options(p, body) == ["base", "LAST"]
    sp = F.spec("REVOLVE")
    axis = [f for f in sp.variants[0].fields if f.key == "axis"][0]
    assert F.options(p, axis, "REVOLVE")[:3] == ["V", "H", "up"]
    assert "top" in F.options(p, F.Field("plane", "", "datum"), "WORKPLANE")
    assert F.initial(p, F.spec("EXTRUDE"))["sketch"] == "s1"


@pytest.mark.parametrize("line", [
    "BLOCK, 0, 0, 0, 40, 30, 8",
    "CYL, 10, 10, 0, 3, 20, 1, 0, 0",
    "HOLE, housing, -25, 0, 0, 8, 0, CBORE, 13, 1.5",
    "PLANE, mid, MID, 1, 2",
    "AXIS, centre, PLANES, mid, side",
    "POINT, corner, VERTEX, 1",
    "SEL, S, FACE, ID, 1, 4",
    "SEL, S, FACE, NORMAL, 0, 0, -1",
    "SEL, ALL, EDGE",
    "ARRAY, POLAR, 1, 6, 180, 5, 0, 0, FUSE",
    "ARRAY, LINEAR, 1, 3, 10, 0, 0, 2, 0, 10, 0",
    "LOFT, a, b, c, CLOSED",
    "LOFT, a, b, c, SURFACE, GUIDE, g1, g2",
    "SWEEP, rib, path, , , NORMAL, , , , , , 1, hull",
    "ANALYZE, part, DRAFT, 0, 0, 1, 2",
    "PROJECT, c, dome, 0, 0, -1",
    "SPLINE, (0, 0, 0), (10, 5, 0), (20, 0, 4), CLOSE",
    "SWEEP, prof, path, 40 - 32*t, 1 - 0.5*t",
    "EXTRUDE, s1, 0, CUT, part",
    "SKETCH, s1, FACE, 6",
    "UNION, a, b, c",
    "W = 2*H + 1",
    'EXPORT, STEP, "out.step"',
])
def test_a_line_reads_back_into_its_form(line):
    sp, variant, values = F.parse(line)
    assert F.build(sp, values, variant) == line


def test_lines_without_a_form():
    for text in ("*DO, i, 1, 3\nBLOCK, i*10, 0, 0, 5, 5, 5\n*ENDDO", "SLINE, 0, 0, 10, 0", "NOSUCH, 1"):
        assert not F.has_form(text)
    assert F.has_form("! a comment\nBLOCK, 0,0,0, 1,1,1   ! box")


def test_a_whole_script_rebuilds_through_forms(p):
    """Every line of the housing example, read into its form and written out
    again, builds the same part: nothing in it needs typing."""
    with open(os.path.join(SCRIPTS, "bracket_features.cmd"), encoding="utf-8") as fh:
        script = fh.read()
    direct = Processor()
    ok(direct, script)
    lines = [ln for ln in (F.strip_comment(raw).strip() for raw in script.splitlines()) if ln]
    for line in lines:
        sp, variant, values = F.parse(line)
        ok(p, F.build(sp, values, variant))
    vol = lambda q: q.evaluate("VOL(housing)")  # noqa: E731
    assert vol(p) == pytest.approx(vol(direct))
