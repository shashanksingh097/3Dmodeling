"""TEXT, SPINELOFT, SURFACE, PUSHPULL and DELFACE (the rest of M4)."""

import math

import pytest

from modeler.commands import Processor
from modeler.gui import forms as F


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, text):
    rs = p.run_script(text)
    assert not rs[-1].ok, rs[-1].message
    return rs[-1].message


def box(p, b, k):
    return p.evaluate(f"BBOX({b}).{k}")


# ---- TEXT ------------------------------------------------------------------------

def test_text_solid_letters_stand_on_the_point(p):
    ok(p, "TEXT, HELLO, 10,20,5, 10, 2")
    assert p.evaluate("VOL(LAST)") > 50
    assert box(p, "LAST", "zmin") == pytest.approx(5, abs=1e-6)
    assert box(p, "LAST", "zmax") == pytest.approx(7, abs=1e-6)
    assert box(p, "LAST", "xmin") >= 10 - 1e-6
    assert box(p, "LAST", "ymin") == pytest.approx(20, abs=0.5)  # baseline (H, E, L, O sit on it)
    assert 6 < box(p, "LAST", "ymax") - 20 < 8.5  # capitals about 0.7 of the font size


def test_text_flat_letters_and_alignment(p):
    ok(p, "TEXT, ABC, 0,0,0, 10")
    assert "flat letters" in p.run_script("TEXT, ABC, 0,0,0, 10, 0, , , , , CENTER")[-1].message
    assert abs(box(p, "LAST", "xmin") + box(p, "LAST", "xmax")) < 1.0  # centred on x = 0
    ok(p, "TEXT, ABC, 0,0,0, 10, 0, , , , , RIGHT")
    assert box(p, "LAST", "xmax") <= 1e-6


def test_text_on_a_side_plane_and_engraved(p):
    ok(p, "BLOCK, 0,0,0, 60,30,10\nNAME, LAST, plate\nV0 = VOL(plate)")
    ok(p, 'TEXT, "No 5", 5,5,9, 8, 1')
    ok(p, "SUBTRACT, plate, LAST")
    assert p.evaluate("VOL(plate)") < p.evaluate("V0") - 5
    ok(p, "TEXT, SIDE, 0,0,0, 5, 1, 0,-1,0")  # standing in the XZ plane, thick along -Y
    assert box(p, "LAST", "ymin") == pytest.approx(-1, abs=1e-6)
    assert box(p, "LAST", "zmax") > 3


def test_text_errors(p):
    assert "font" in err(p, "TEXT, A, 0,0,0, 5, 0, , , , , LEFT, nosuchfont.ttf")
    assert "size" in err(p, "TEXT, A, 0,0,0, 0")
    assert "align" in err(p, "TEXT, A, 0,0,0, 5, 0, , , , , MIDDLE")


# ---- SPINELOFT ------------------------------------------------------------------

def _bend(p):
    c, s = math.cos(math.pi / 4), math.sin(math.pi / 4)
    mid = (50 * (1 - c), 0, 50 * s)
    ok(p, f"""ARC, 0,0,0, {mid[0]},0,{mid[2]}, 50,0,50
NAME, LAST, spine
CIRCLE, 0,0,0, 8
NAME, LAST, a
RECT, {mid[0]},0,{mid[2]}, 14, 10, 2, {s},0,{c}
NAME, LAST, b
CIRCLE, 50,0,50, 4, 1,0,0
NAME, LAST, c""")


def test_spineloft_follows_the_spine_through_its_sections(p):
    _bend(p)
    r = ok(p, "SPINELOFT, spine, c, a, b")  # any order: sorted along the spine
    assert "t = 0, 0.5, 1" in r.message
    v = p.evaluate("VOL(LAST)")
    # between the end areas times the spine length, well inside the bend
    length = 50 * math.pi / 2
    assert math.pi * 16 * length < v < math.pi * 64 * length
    # the ends sit where the end sections were drawn
    assert box(p, "LAST", "zmin") == pytest.approx(0, abs=1e-3)
    assert box(p, "LAST", "xmax") == pytest.approx(50, abs=1e-3)
    assert box(p, "LAST", "zmax") == pytest.approx(54, abs=0.05)


def test_spineloft_two_sections_on_a_straight_spine_is_a_cone(p):
    ok(p, "LINE, 0,0,0, 0,0,30\nCIRCLE, 0,0,0, 10\nCIRCLE, 0,0,30, 5\nSPINELOFT, 1, 2, 3")
    assert p.evaluate("VOL(LAST)") == pytest.approx(math.pi * 30 / 3 * (100 + 50 + 25), rel=2e-3)


def test_spineloft_surface_and_errors(p):
    _bend(p)
    ok(p, "SPINELOFT, spine, a, b, c, SURFACE")
    from modeler.geometry import robust
    assert not robust.solids(p.model.body(p.evaluate("LAST")).shape)
    assert "at least 2" in err(p, "SPINELOFT, spine, a")
    assert "twice" in err(p, "SPINELOFT, spine, a, a")
    assert "same place" in err(p, "CIRCLE, 0,0,0, 3\nSPINELOFT, spine, a, LAST")
    assert "one of" in err(p, "SPINELOFT, spine, a, c, FRENET, FIXED")


# ---- SURFACE ---------------------------------------------------------------------

def test_surface_closed_torus_and_sphere_are_solids(p):
    r = ok(p, "SURFACE, PARAM, (20+6*cos(v))*cos(u), (20+6*cos(v))*sin(u), 6*sin(v), 0, 360, 0, 360")
    assert "solid" in r.message
    assert p.evaluate("VOL(LAST)") == pytest.approx(2 * math.pi**2 * 20 * 36, rel=1e-3)
    ok(p, "R = 10\nSURFACE, PARAM, R*cos(v)*cos(u), R*cos(v)*sin(u), R*sin(v), 0, 360, -90, 90")
    assert p.evaluate("VOL(LAST)") == pytest.approx(4 / 3 * math.pi * 1000, rel=1e-3)


def test_surface_open_and_thickened(p):
    ok(p, "SURFACE, PARAM, u, v, 3*sin(6*u)*cos(6*v), 0, 60, 0, 40")
    assert p.evaluate("VOL(LAST)") == pytest.approx(0, abs=1e-6)
    assert p.evaluate("AREA(1)") > 60 * 40  # wavy, so more than the flat area
    assert box(p, "LAST", "zmax") == pytest.approx(3, abs=0.05)
    ok(p, "SURFACE, PARAM, u, v, 0, 0, 60, 0, 40, 4, 4, 2")
    assert p.evaluate("VOL(LAST)") == pytest.approx(60 * 40 * 2, rel=1e-6)


def test_surface_errors(p):
    assert "PARAM" in err(p, "SURFACE, MESH, u, v, 0")
    assert "greater" in err(p, "SURFACE, PARAM, u, v, 0, 1, 0")
    assert "no size" in err(p, "SURFACE, PARAM, 1, 1, 1")
    assert "must give a number" in err(p, "SURFACE, PARAM, u, v, (1,2,3)")
    assert "already a solid" in err(p, "SURFACE, PARAM, 5*cos(v)*cos(u), 5*cos(v)*sin(u), 5*sin(v), 0, 360, -90, 90, "
                                       "16, 16, 1")


# ---- PUSHPULL and DELFACE ---------------------------------------------------------

def _plate(p):
    ok(p, "BLOCK, 0,0,0, 40,30,10\nNAME, LAST, plate\nCYL, 20,15,-1, 4, 12\nSUBTRACT, plate, LAST")


def test_pushpull_moves_a_flat_face_and_keeps_ids(p):
    _plate(p)
    ok(p, "SEL, S, FACE, BODY, plate\nSEL, R, FACE, NORMAL, 0,0,1")
    top = p.model.selection[0]
    bid = p.model.entity_owner("FACE", top)[0]
    others = sorted(p.model.body(bid).entity_ids["FACE"])
    v0 = p.evaluate("VOL(plate)")
    r = ok(p, "PUSHPULL, 5")
    assert "volume +" in r.message
    assert p.evaluate("VOL(plate)") == pytest.approx(v0 * 1.5, rel=1e-9)
    assert box(p, "plate", "zmax") == pytest.approx(15)
    # face IDs survive: the same faces, the same numbers
    assert sorted(p.model.body(bid).entity_ids["FACE"]) == others


def test_pushpull_on_a_hole_changes_its_radius(p):
    _plate(p)
    ok(p, "SEL, S, FACE, BODY, plate\nSEL, R, FACE, TYPE, CYLINDER\nV0 = VOL(plate)\nPUSHPULL, -1")
    assert p.evaluate("V0 - VOL(plate)") == pytest.approx(math.pi * (25 - 16) * 10, rel=1e-6)


def test_delface_removes_a_hole(p):
    _plate(p)
    r = ok(p, "SEL, S, FACE, BODY, plate\nSEL, R, FACE, TYPE, CYLINDER\nDELFACE")
    assert "1 fewer faces" in r.message
    assert p.evaluate("VOL(plate)") == pytest.approx(40 * 30 * 10)


def test_delface_removes_a_fillet(p):
    ok(p, "BLOCK, 0,0,0, 20,20,20")
    edge = p.model.body(1).entity_ids["EDGE"][0]
    ok(p, f"SEL, S, EDGE, ID, {edge}\nFILLET, 3")
    assert p.evaluate("VOL(LAST)") < 8000 - 1
    ok(p, "SEL, S, FACE, TYPE, CYLINDER\nDELFACE")
    assert p.evaluate("VOL(LAST)") == pytest.approx(8000)


def test_direct_editing_errors(p):
    assert "select faces" in err(p, "BLOCK, 0,0,0, 1,1,1\nPUSHPULL, 1")
    _plate(p)
    assert "cannot be 0" in err(p, "SEL, S, FACE, BODY, plate\nPUSHPULL, 0")
    ok(p, "SEL, S, FACE, BODY, plate\nSEL, R, FACE, NORMAL, 0,0,1")
    assert "PUSHPULL" in err(p, "PUSHPULL, -20")  # through the bottom
    assert p.evaluate("VOL(plate)") > 0  # unchanged


# ---- forms -------------------------------------------------------------------------

def test_forms_write_the_commands(p):
    sp = F.spec("SPINELOFT")
    text = F.build(sp, {"spine": "spine", "s": "a, b, c", "fixed": "1"})
    assert text == "SPINELOFT, spine, a, b, c, FIXED"
    assert F.parse(text)[2]["s"] == "a, b, c"
    sp = F.spec("TEXT")
    assert F.build(sp, {"text": "M8", "x": "0, 0, 0", "size": "6", "align": "CENTER"}).startswith("TEXT, M8, 0, 0, 0, 6")
    assert F.build(F.spec("PUSHPULL"), {"d": "-1"}) == "PUSHPULL, -1"
    assert F.build(F.spec("DELFACE"), {}) == "DELFACE"
    sp = F.spec("SURFACE")
    text = F.build(sp, {"kind": "PARAM", "fx": "u", "fy": "v", "fz": "u*v/40", "u1": "20", "v1": "20"})
    assert text == "SURFACE, PARAM, u, v, u*v/40, , 20, , 20"
    ok(p, text)
