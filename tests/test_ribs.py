"""RIB, LIP, WRAP (geometry/ribs.py, commands/rib_handlers.py)."""

from __future__ import annotations

import math

import pytest

from modeler.commands import Processor


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, f"{line}: {r.message}"
    return r


def vol(p, bid):
    """Volume to 1e-7: the default integration is a few per cent off on faces bounded by splines."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    (getattr(BRepGProp, "VolumeProperties_s", None) or BRepGProp.VolumeProperties)(p.model.body(bid).shape, g, 1e-7)
    return g.Mass()


BOX = ["BLOCK, 0,0,0, 60,40,30", "SEL, S, FACE, AT, 30,20,30", "SHELL, 2", "SEL, NONE"]


def test_rib_fills_down_to_the_floor_between_the_walls():
    p = Processor()
    run(p, *BOX)
    v0 = vol(p, 1)
    run(p, "PLANE, mid, XZ, 20", "SKETCH, r1, mid", "SLINE, -40, 20, -20, 20", "ENDSKETCH", "RIB, r1, 2, 1")
    assert vol(p, 1) - v0 == pytest.approx(56 * 18 * 2, rel=1e-6)  # its ends carry on to the walls
    assert "OK" in p.run("CHECK, 1").message


def test_gusset_in_an_angle():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 40,30,4", "BLOCK, 0,0,0, 4,30,40", "UNION, 1, 2", "PLANE, g, XZ, 15",
        "SKETCH, s, g", "SLINE, -4, 30, -30, 4", "ENDSKETCH")
    b = max(p.model.bodies)
    v0 = vol(p, b)
    run(p, f"RIB, s, 3, {b}")
    assert vol(p, b) - v0 == pytest.approx(26 * 26 / 2 * 3, rel=1e-6)


def test_rib_that_meets_nothing_says_so():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 40,30,4", "PLANE, g, XZ, 15", "SKETCH, s, g", "SLINE, -10, 10, -30, 10", "ENDSKETCH")
    r = p.run("RIB, s, 2, 1, FLIP")  # away from the plate: open sky
    assert not r.ok and "meets no part face" in r.message
    r = p.run("RIB, s, 2, 1")  # down to the plate, but its ends run on past it with nothing to stop them
    assert not r.ok and "meets no part face" in r.message


def test_lip_and_groove_bands():
    p = Processor()
    run(p, *BOX, "SEL, S, FACE, AT, 1, 20, 30")
    v0 = vol(p, 1)
    run(p, "LIP, , 2, 1")
    band = 58 * 38 - (4 - math.pi) - 56 * 36  # the inside edge grown by 1, round at its outer corners
    assert vol(p, 1) - v0 == pytest.approx(2 * band, rel=1e-6)
    q = Processor()
    run(q, *BOX, "SEL, S, FACE, AT, 1, 20, 30")
    v0 = vol(q, 1)
    run(q, "LIP, , 2, 1, GROOVE, 0.2")
    band = 58.4 * 38.4 - (4 - math.pi) * 1.44 - 56 * 36
    assert v0 - vol(q, 1) == pytest.approx(2.2 * band, rel=1e-6)


def test_lip_wants_a_flat_face():
    p = Processor()
    run(p, "CYL, 0,0,0, 10, 20", "SEL, S, FACE, TYPE, CYLINDER")
    r = p.run("LIP, , 2, 1")
    assert not r.ok and "not flat" in r.message


def wrapped(*geos):
    p = Processor()
    run(p, "CYL, 0,0,0, 20, 40", "PLANE, w, XZ, -30", "SKETCH, s, w", *geos, "ENDSKETCH",
        "SEL, S, FACE, TYPE, CYLINDER")
    return p


def test_wrap_keeps_sizes_round_the_cylinder():
    p = wrapped("SRECT, -5, 15, 5, 20", "SCIRCLE, 12, 30, 3")
    v0 = vol(p, 1)
    run(p, "WRAP, s, , 1")
    # an area A raised h on radius R: A h (R + h/2) / R
    assert vol(p, 1) - v0 == pytest.approx((50 + math.pi * 9) * 20.5 / 20, rel=1e-4)
    assert "OK" in p.run("CHECK, 1").message
    q = wrapped("SRECT, -20, 5, 20, 8")
    v0 = vol(q, 1)
    run(q, "WRAP, s, , 0.5, CUT")
    assert v0 - vol(q, 1) == pytest.approx(40 * 3 * 19.75 / 20 * 0.5, rel=1e-4)


def test_wrap_lands_where_the_sketch_faces_the_cylinder():
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    p = wrapped("SRECT, -2, 15, 2, 20")
    run(p, "WRAP, s, , 1")
    b = Bnd_Box()
    (getattr(BRepBndLib, "Add_s", None) or BRepBndLib.Add)(p.model.body(1).shape, b, True)
    assert b.CornerMin().Y() == pytest.approx(-21, abs=1e-2)  # the sketch plane is at y = -30
    assert b.CornerMax().Y() == pytest.approx(20, abs=1e-2)


def test_wrap_refuses_a_plane_across_the_axis():
    p = Processor()
    run(p, "CYL, 0,0,0, 20, 40", "SKETCH, s, XY", "SRECT, 0, 0, 5, 5", "ENDSKETCH", "SEL, S, FACE, TYPE, CYLINDER")
    r = p.run("WRAP, s, , 1")
    assert not r.ok and "parallel" in r.message


def test_wrap_on_a_cylinder_away_from_the_sketch_origin():
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    p = Processor()
    run(p, "CYL, 100, 0, 0, 20, 40", "PLANE, w, XZ, -30", "SKETCH, s, w", "SRECT, -102, 15, -98, 20", "ENDSKETCH",
        "SEL, S, FACE, TYPE, CYLINDER", "WRAP, s, , 1")
    b = Bnd_Box()
    (getattr(BRepBndLib, "Add_s", None) or BRepBndLib.Add)(p.model.body(1).shape, b, True)
    assert b.CornerMin().Y() == pytest.approx(-21, abs=1e-2)  # right in front, facing the sketch plane


def _fine_volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    (getattr(BRepGProp, "VolumeProperties_s", None) or BRepGProp.VolumeProperties)(shape, g, 1e-7, False)
    return g.Mass()


@pytest.mark.parametrize("mode, sign", [("ADD", 1), ("CUT", -1)])
def test_wrap_onto_a_cone_keeps_areas(mode, sign):
    from modeler.commands.rib_handlers import _face
    from modeler.commands.sketch_handlers import _profile
    from modeler.geometry import ribs

    p = Processor()
    run(p, "CONE, 0,0,0, 25, 15, 40", "PLANE, w, XZ, -30", "SKETCH, s, w", "SRECT, -3, 18, 3, 22",
        "SCIRCLE, 8, 10, 2", "ENDSKETCH", "SEL, S, FACE, TYPE, CONE")
    _bid, f = _face(p, p.model.selection[0], "WRAP")
    sk, faces, _ = _profile(p, "s", "WRAP")
    wrapped, _r = ribs.wrap_faces(faces, sk.frame, ribs.cylinder_of(f))
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    areas = []
    for w in wrapped:
        g = GProp_GProps()
        (getattr(BRepGProp, "SurfaceProperties_s", None) or BRepGProp.SurfaceProperties)(w, g)
        areas.append(g.Mass())
    assert sorted(areas) == pytest.approx([4 * math.pi, 24], rel=3e-3)  # laid on the development: sizes kept
    v0 = _fine_volume(p.model.body(1).shape)
    r = p.run(f"WRAP, s, , 0.5, {mode}")
    assert r.ok and "cone" in r.message, r.message
    assert "OK" in p.run("CHECK, 1").message
    dv = _fine_volume(p.model.body(1).shape) - v0
    assert sign * dv == pytest.approx((24 + 4 * math.pi) * 0.5, rel=0.03)
