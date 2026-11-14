"""MATE: placing copies by faces, edges and axes (COINCIDENT, CONCENTRIC,
DISTANCE, ANGLE), on the bolted plate example and simple blocks."""

import math

import pytest

from modeler.commands import Processor
from modeler.geometry import features as ft

BOLT = """*PART, bolt, D=8, L=30
  CYL, 0, 0, 0, D, 5        ! head (bottom face at z=0, looking down)
  CYL, 0, 0, -L, D/2, L     ! shank
  UNION, 1, 2
*ENDPART"""


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, line):
    r = p.run(line)
    assert not r.ok, r.message
    return r.message


def faces(p, bid):
    m = p.model
    return list(m.bodies[bid].entity_ids["FACE"])


def flat_face(p, bid, normal, where=None):
    """The flat face of body bid whose outward normal is ``normal`` (and centre near ``where``)."""
    best = None
    for g in faces(p, bid):
        got = ft.face_plane(p.model.entity_shape("FACE", g))
        if got and all(abs(a - b) < 1e-6 for a, b in zip(got[1], normal)):
            d = 0 if where is None else math.dist(got[0], where)
            if best is None or d < best[0]:
                best = (d, g)
    assert best, f"no face looking {normal} on body {bid}"
    return best[1]


def round_face(p, bid, radius):
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    for g in faces(p, bid):
        s = BRepAdaptor_Surface(ft.as_face(p.model.entity_shape("FACE", g)))
        if ft.face_axis(p.model.entity_shape("FACE", g)) and abs(s.Cylinder().Radius() - radius) < 1e-6:
            return g
    raise AssertionError(f"no round face of radius {radius} on body {bid}")


def underside(p, bid):
    """The bolt head's underside: the flat ring of area pi*(8^2 - 4^2)."""
    from modeler.commands.queries import props

    want = math.pi * (64 - 16)
    for g in faces(p, bid):
        shape = p.model.entity_shape("FACE", g)
        if ft.face_plane(shape) and abs(props("FACE", shape).Mass() - want) < 1e-6:
            return g
    raise AssertionError("no head underside")


def box(p, bid):
    from modeler.commands.queries import bbox

    return bbox(p.model.bodies[bid].shape)


@pytest.fixture
def plate():
    """A plate with a hole at (20, 0) and a bolt placed far off, turned on its side."""
    p = Processor()
    ok(p, BOLT + "\nBLOCK, -10, -30, -12, 60, 60, 12\nNAME, LAST, plate\nHOLE, plate, 20, 0, 0, 8.5\n"
               "INST, bolt, 100, 40, 25, 90, 1, 0, 0")
    return p


def test_concentric_then_coincident_seats_the_bolt(plate):
    p = plate
    pl = p.model.body_by_name("plate").id
    bolt = max(p.model.instances)
    hole = round_face(p, pl, 4.25)
    shank = round_face(p, bolt, 4.0)
    r = p.run(f"MATE, CONCENTRIC, FACE, {hole}, FACE, {shank}")
    assert r.ok, r.message
    assert "axes in line" in r.message
    x0, y0, z0, x1, y1, z1 = box(p, bolt)
    assert abs((x0 + x1) / 2 - 20) < 1e-6 and abs((y0 + y1) / 2) < 1e-6
    top = flat_face(p, pl, (0, 0, 1))
    under = flat_face(p, bolt, (0, 0, -1), where=(20, 0, 100))  # the head's underside, after the turn
    r = p.run(f"MATE, COINCIDENT, FACE, {top}, FACE, {under}")
    assert r.ok, r.message
    assert "distance now 0" in r.message
    x0, y0, z0, x1, y1, z1 = box(p, bolt)
    assert abs(z0 + 30) < 1e-6 and abs(z1 - 5) < 1e-6  # head on the plate, shank down the hole
    assert abs((x0 + x1) / 2 - 20) < 1e-6  # still in the hole
    # the bolt is still an instance, and the plate never moved
    assert bolt in p.model.instances
    assert box(p, pl) == pytest.approx((-10, -30, -12, 50, 30, 0))
    c = p.run(f"CLEARANCE, {pl}, {bolt}")
    assert c.ok


def test_mates_follow_a_rebuild(plate):
    """Mates are history steps: change the part, and the mated copy is placed again."""
    p = plate
    pl = p.model.body_by_name("plate").id
    bolt = max(p.model.instances)
    ok(p, f"MATE, CONCENTRIC, FACE, {round_face(p, pl, 4.25)}, FACE, {round_face(p, bolt, 4.0)}")
    ok(p, f"MATE, COINCIDENT, FACE, {flat_face(p, pl, (0, 0, 1))}, "
          f"FACE, {flat_face(p, bolt, (0, 0, -1), where=(20, 0, 100))}")
    row = next(j for j, e in enumerate(p.history) if e.text.startswith("*PART"))
    from modeler.lang.expr import format_value

    r = p.run(f'HIST, EDIT, {row + 1}, {format_value(BOLT.replace("L=30", "L=50"))}')
    assert r.ok, r.message
    assert all(e.ok for e in p.history), [e.message for e in p.history if not e.ok]
    x0, _y0, z0, x1, _y1, z1 = box(p, bolt)
    assert abs(z0 + 50) < 1e-6 and abs(z1 - 5) < 1e-6
    assert abs((x0 + x1) / 2 - 20) < 1e-6


def test_distance_and_flip():
    p = Processor()
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nBLOCK, 30, 5, 7, 4, 4, 4")
    a_top = flat_face(p, 1, (0, 0, 1))
    b_side = flat_face(p, 2, (1, 0, 0))
    r = p.run(f"MATE, DISTANCE, FACE, {a_top}, FACE, {b_side}, 3")
    assert r.ok, r.message
    _x0, _y0, z0, _x1, _y1, z1 = box(p, 2)
    assert abs(z0 - 13) < 1e-6 and abs(z1 - 17) < 1e-6  # the side now looks down, 3 above the top
    # FLIP: the same face looks the same way as the top, so the block sits 3 below the top plane
    r = p.run(f"MATE, DISTANCE, FACE, {a_top}, FACE, {b_side}, 3, FLIP")
    assert r.ok, r.message
    assert abs(box(p, 2)[5] - 13) < 1e-6 and abs(box(p, 2)[2] - 9) < 1e-6
    assert "cannot be negative" in err(p, f"MATE, DISTANCE, FACE, {a_top}, FACE, {b_side}, -1")


def test_angle_between_faces():
    p = Processor()
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nBLOCK, 30, 0, 0, 10, 10, 2")
    a = flat_face(p, 1, (0, 0, 1))
    b = flat_face(p, 2, (0, 0, 1))
    r = p.run(f"MATE, ANGLE, FACE, {a}, FACE, {b}, 30")
    assert r.ok, r.message
    assert "angle 30 deg" in r.message
    got = ft.face_plane(p.model.entity_shape("FACE", b))[1]
    assert math.degrees(math.acos(got[2])) == pytest.approx(30)


def test_points_planes_and_datums():
    p = Processor()
    ok(p, "BLOCK, 5, 5, 5, 10, 10, 10")
    under = flat_face(p, 1, (0, 0, -1))
    r = p.run(f"MATE, COINCIDENT, XY, FACE, {under}, FLIP")  # FLIP: the underside looks up, like XY
    assert r.ok, r.message
    assert abs(box(p, 1)[5]) < 1e-6  # turned over, hanging below XY
    # XY's normal is +Z; the underside (now facing up) is turned to face XY again and sits on it
    r = p.run(f"MATE, COINCIDENT, XY, FACE, {under}")
    assert r.ok, r.message
    assert abs(box(p, 1)[2]) < 1e-6 and abs(box(p, 1)[5] - 10) < 1e-6
    ok(p, "POINT, tip, XYZ, 50, 0, 0")
    v = min(p.model.bodies[1].entity_ids["VERTEX"])
    r = p.run(f"MATE, COINCIDENT, DATUM, tip, VERTEX, {v}")
    assert r.ok, r.message
    from modeler.commands.queries import centre

    assert tuple(centre("VERTEX", p.model.entity_shape("VERTEX", v))) == pytest.approx((50, 0, 0))


def test_mates_that_cannot_be_met_say_why():
    p = Processor()
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nCYL, 30, 0, 0, 3, 10")
    a = flat_face(p, 1, (0, 0, 1))
    other = flat_face(p, 1, (1, 0, 0))
    cyl = round_face(p, 2, 3)
    assert "CONCENTRIC needs two axes" in err(p, f"MATE, CONCENTRIC, FACE, {a}, FACE, {cyl}")
    assert f"FACE {a} is a flat face" in err(p, f"MATE, CONCENTRIC, FACE, {a}, FACE, {cyl}")
    assert "on the same body" in err(p, f"MATE, COINCIDENT, FACE, {a}, FACE, {other}")
    assert "the kind is one of" in err(p, f"MATE, GLUE, FACE, {a}, FACE, {cyl}")
    assert "must be a FACE, EDGE or VERTEX of a body" in err(p, f"MATE, COINCIDENT, FACE, {a}, XY")
    assert "takes no value" in err(p, f"MATE, COINCIDENT, FACE, {a}, FACE, {flat_face(p, 2, (0, 0, 1))}, 4")
    assert "pick two faces" in err(p, "MATE, COINCIDENT")
    # a failed mate moves nothing
    assert box(p, 2)[0] == pytest.approx(27)


def test_coincident_faces_that_miss_each_other_warn():
    p = Processor()
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nBLOCK, 50, 0, 20, 4, 4, 4")
    r = p.run(f"MATE, COINCIDENT, FACE, {flat_face(p, 1, (0, 0, 1))}, FACE, {flat_face(p, 2, (0, 0, -1))}")
    assert r.ok
    assert "do not overlap" in r.warning


def test_mate_the_two_selected():
    p = Processor()
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nBLOCK, 30, 0, 20, 4, 4, 4")
    a, b = flat_face(p, 1, (0, 0, 1)), flat_face(p, 2, (0, 0, -1))
    ok(p, f"PICK, FACE, {a}\nPICK, FACE, {b}, A")
    r = p.run("MATE, DISTANCE, 2")
    assert r.ok, r.message
    assert abs(box(p, 2)[2] - 12) < 1e-6


def test_round_edges_coincident():
    p = Processor()
    ok(p, "CYL, 0, 0, 0, 10, 5\nCYL, 40, 10, 30, 3, 8")
    from OCP.BRepAdaptor import BRepAdaptor_Curve

    def top_edge(bid, z):
        for g in p.model.bodies[bid].entity_ids["EDGE"]:
            c = ft.edge_circle(p.model.entity_shape("EDGE", g))
            if c and abs(c[0][2] - z) < 1e-6:
                return g
        raise AssertionError

    r = p.run(f"MATE, COINCIDENT, EDGE, {top_edge(1, 5)}, EDGE, {top_edge(2, 30)}")
    assert r.ok, r.message
    x0, _y0, z0, x1, _y1, _z1 = box(p, 2)
    assert (x0 + x1) / 2 == pytest.approx(0, abs=1e-6) and z0 == pytest.approx(5)
    del BRepAdaptor_Curve


def test_mate_form_round_trip():
    from modeler.gui import forms as F

    p = Processor()
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nBLOCK, 30, 0, 20, 4, 4, 4")
    a, b = flat_face(p, 1, (0, 0, 1)), flat_face(p, 2, (0, 0, -1))
    ok(p, f"PICK, FACE, {a}\nPICK, FACE, {b}, A")
    sp = F.spec("MATE")
    assert sp.category == "Parts"
    vals = F.initial(p, sp, "DISTANCE")
    assert (vals["k1"], vals["i1"], vals["k2"], vals["i2"]) == ("FACE", str(a), "FACE", str(b))
    vals["value"] = "2"
    text, problems = F.check(p, sp, vals, "DISTANCE")
    assert not problems and text == f"MATE, DISTANCE, FACE, {a}, FACE, {b}, 2"
    ok(p, text)
    assert F.parse(text)[1:] == ("DISTANCE", {"k1": "FACE", "i1": str(a), "k2": "FACE", "i2": str(b), "value": "2"})
    # XY needs no ID: the form keeps the empty place, and typed text without it opens too
    t2 = F.build(sp, {"k1": "XY", "k2": "FACE", "i2": str(b), "flip": "1"}, "COINCIDENT")
    assert t2 == f"MATE, COINCIDENT, XY, , FACE, {b}, FLIP"
    ok(p, t2)
    assert F.parse(f"MATE, COINCIDENT, XY, FACE, {b}")[2]["i2"] == str(b)


def test_exit_test_eight_linked_bolts_mated_then_lengthened(tmp_path):
    """PLAN 5.10 exit test, headless: a bolt part file, an assembly that links
    it, eight copies seated on a plate by CONCENTRIC and COINCIDENT mates; the
    part file changes and every copy updates and stays seated."""
    bolt_file = tmp_path / "bolt.cmd"
    bolt_file.write_text(BOLT + "\n", encoding="utf-8")
    p = Processor()
    ok(p, f'LIB, LINK, "{bolt_file}"\nCYL, 0, 0, -12, 60, 12\nNAME, LAST, plate\n'
          "*DO, i, 1, 8\n  HOLE, plate, 45*cos(45*i), 45*sin(45*i), 0, 8.5\n*ENDDO\n"
          "*DO, i, 1, 8\n  INST, bolt, 150 + 20*i, 80, 40, 30*i, 0, 1, 0\n*ENDDO")
    pl = p.model.body_by_name("plate").id
    bolts = sorted(p.model.instances)
    assert len(bolts) == 8
    holes = [g for g in faces(p, pl) if ft.face_axis(p.model.entity_shape("FACE", g))
             and abs(ft.face_axis(p.model.entity_shape("FACE", g))[0][0] ** 2
                     + ft.face_axis(p.model.entity_shape("FACE", g))[0][1] ** 2 - 45 ** 2) < 1e-3]
    assert len(holes) == 8
    top = flat_face(p, pl, (0, 0, 1))
    for b, h in zip(bolts, holes):
        ok(p, f"MATE, CONCENTRIC, FACE, {h}, FACE, {round_face(p, b, 4.0)}")
        # the head's underside: the ring where the shank starts (it may look up or down by now;
        # COINCIDENT turns it to face the plate, keeping the bolt on the hole's axis)
        ok(p, f"MATE, COINCIDENT, FACE, {top}, FACE, {underside(p, b)}")

    def seated(length):
        for b, h in zip(bolts, holes):
            cx, cy = ft.face_axis(p.model.entity_shape("FACE", h))[0][:2]
            x0, y0, z0, x1, y1, z1 = box(p, b)
            assert (x0 + x1) / 2 == pytest.approx(cx, abs=1e-6) and (y0 + y1) / 2 == pytest.approx(cy, abs=1e-6)
            assert z0 == pytest.approx(-length, abs=1e-6) and z1 == pytest.approx(5, abs=1e-6)

    seated(30)
    for b in bolts:
        assert p.run(f"CONTACT, {pl}, {b}").ok
    bolt_file.write_text(BOLT.replace("L=30", "L=40") + "\n", encoding="utf-8")
    r = p.run("RELOAD")
    assert r.ok and "bolt updated from bolt.cmd: 8 copies" in r.message, r.message
    assert all(e.ok for e in p.history), [e.message for e in p.history if not e.ok]
    seated(40)


def test_right_click_offers_a_mate_for_two_picked_faces():
    from modeler.gui import body_menu as bm

    p = Processor()
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nBLOCK, 30, 0, 20, 4, 4, 4")
    a, b = flat_face(p, 1, (0, 0, 1)), flat_face(p, 2, (0, 0, -1))
    ok(p, f"PICK, FACE, {a}")
    assert not any(i.form == "MATE" for i in bm.body_items(p.model, 1))
    ok(p, f"PICK, FACE, {flat_face(p, 1, (1, 0, 0))}, A")  # two faces of one body: no mate
    assert not any(i.form == "MATE" for i in bm.body_items(p.model, 1))
    ok(p, f"PICK, FACE, {a}\nPICK, FACE, {b}, A")
    item = next(i for i in bm.body_items(p.model, 2) if i.form == "MATE")
    assert item.label == "Mate the two picked…"
