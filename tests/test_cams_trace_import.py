"""PLAN items 40-42: TRACE, CAM/CAMLIFT, bevel/worm gears, helical racks, SDXF, STRACE, IMAGE and
TOPOPT."""

import math

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import cams, dxfread
from modeler.geometry import meshbody as mb
from modeler.geometry import robust

DXF = """0
SECTION
2
ENTITIES
0
LWPOLYLINE
8
OUTLINE
90
5
70
1
10
0
20
0
10
80
20
0
42
0.4142135623
10
100
20
20
10
100
20
50
10
0
20
50
0
CIRCLE
8
HOLES
10
25
20
25
40
8
0
SPLINE
8
OTHER
71
3
11
0
21
60
11
10
21
70
11
20
21
60
0
ENDSEC
0
EOF
"""


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def fails(p, line, text):
    r = p.run(line)
    assert not r.ok, line
    assert text.lower() in r.message.lower(), r.message


# ---- TRACE -------------------------------------------------------------------------------------
def test_trace_follows_a_point_round_a_turn():
    p = Processor()
    run(p, "A = 0", "BLOCK, 0, -2, 0, 40, 4, 4", "NAME, LAST, arm", "ROTATE, arm, A, 0, 0, 0, 0, 0, 1")
    msg = run(p, "TRACE, A, 0, 360, 24, arm, 40, 0, 2").message
    assert "closed loop" in msg and "trace_1" in msg
    curve = p.model.body_by_name("trace_1")
    assert curve is not None
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(curve.shape, box)
    lo, hi = box.CornerMin(), box.CornerMax()
    assert hi.X() == pytest.approx(40, abs=0.5) and lo.X() == pytest.approx(-40, abs=0.5)
    assert p.drive.get("A") is None  # put back
    # a quarter turn is an open arc
    assert "open path" in run(p, "TRACE, A, 0, 90, 6, arm, 40, 0, 2").message


def test_trace_refuses_bad_input():
    p = Processor()
    run(p, "A = 0", "BLOCK, 0, 0, 0, 10, 10, 10", "NAME, LAST, b", "MOVE, b, 0, 0, 0")
    fails(p, "TRACE, B, 0, 1, 4, b, 0, 0, 0", "not set by the history")
    fails(p, "TRACE, A, 0, 1, 99, b, 0, 0, 0", "steps")
    fails(p, "TRACE, A, 0, 1, 4, b, 0, 0, 0", "does not move")
    run(p, "C = 10", "BLOCK, 20, 0, 0, C, 5, 5", "NAME, LAST, grows")
    fails(p, "TRACE, C, 10, 20, 4, grows, 20, 0, 0", "shape")


# ---- cams -------------------------------------------------------------------------------------
def test_lift_law_parses_and_checks():
    law = cams.parse("R10/120 D60 F10/120 D60")
    assert cams.stroke(law) == pytest.approx(10)
    assert cams.lift(law, 0)[0] == pytest.approx(0)
    assert cams.lift(law, 120)[0] == pytest.approx(10)
    assert cams.lift(law, 150)[0] == pytest.approx(10)
    assert cams.lift(law, 60)[0] == pytest.approx(5)  # half way through a cycloidal rise
    assert cams.lift(law, 0)[1] == pytest.approx(0)  # cycloidal: starts at rest
    for bad, words in (("R10/120 D60", "360"), ("R10/180 F5/180", "differ"), ("F5/180 R5/180", "below"),
                       ("X5", "not a piece"), ("R10 D350", "lift / its angle")):
        with pytest.raises(cams.CamError, match=words):
            cams.parse(bad)


def test_disc_cam_roller_never_overlaps_or_leaves_the_cam():
    p = Processor()
    run(p, "A = 0", 'LAW = "R12/150 D30 F12/150 D30"', "CAM, 0, 0, 0, LAW, 30, 8, 12, DISC, 10",
        "ROTATE, cam_1, A, 0, 0, 0, 0, 0, 1", "MOVE, cam_1_roller, CAMLIFT(LAW, A), 0, 0")
    cam, roller = p.model.body_by_name("cam_1"), p.model.body_by_name("cam_1_roller")
    assert robust.volume(cam.shape) > 0
    for a in (0, 47, 75, 150, 200, 260):
        run(p, f"DRIVE, A, {a}")
        cam, roller = p.model.body_by_name("cam_1"), p.model.body_by_name("cam_1_roller")
        assert mb.overlap_volume(cam.shape, roller.shape, 0.05) < 0.05
        from OCP.BRepExtrema import BRepExtrema_DistShapeShape

        assert BRepExtrema_DistShapeShape(cam.shape, roller.shape).Value() < 0.05  # touching
    run(p, "DRIVE, A")


def test_cam_warns_and_refuses():
    p = Processor()
    r = run(p, 'CAM, 0, 0, 0, "R30/60 D120 F30/60 D120", 15, 5, 10')
    assert "pressure angle" in r.message.lower() and r.warning
    fails(p, 'CAM, 0, 0, 0, "R10/120 D60 F10/120 D60", 30, 8, 12, PLATE', "DISC or BARREL")
    fails(p, 'CAM, 0, 0, 0, "R10/100", 30, 8, 12', "360")
    r = run(p, 'CAM, 0, 0, 0, "R30/180H F30/180H", 30, 6, 80, BARREL, 12')
    assert "barrel" in r.message
    assert p.run('CAMLIFT_TEST = CAMLIFT("R30/180H F30/180H", 90)').ok
    assert p.run("ECHO, CAMLIFT_TEST").message.strip().endswith("15")


# ---- gears -------------------------------------------------------------------------------------
def test_bevel_pair_meshes_at_right_angles():
    p = Processor()
    r = run(p, "GEAR, 0, 0, 0, 2, 20, 10, BEVEL, 0, 8, 20, 0, 0, 1, 30")
    assert "pitch cone 33.69" in r.message
    run(p, "GEAR, 20.1, 0, 30, 2, 30, 10, BEVEL, 0, 10, 20, -1, 0, 0, 20", "ROTATE, LAST, 6, 20.1, 0, 30, -1, 0, 0")
    assert mb.overlap_volume(p.model.body(1).shape, p.model.body(2).shape, 0.05) < 1.0
    fails(p, "GEAR, 0, 0, 0, 2, 20, 30, BEVEL", "face width")


def test_worm_and_wheel_mesh():
    p = Processor()
    r = run(p, "GEAR, 0, 0, 0, 2, 1, 60, WORM, 0, 0, 20, 1, 0, 0")
    assert "lead angle 5.71" in r.message
    run(p, "GEAR, 30, -8, 40.15, 2, 30, 16, WORMWHEEL, 0, 10, 20, 0, 1, 0", "ROTATE, LAST, 8, 30, -8, 40.15, 0, 1, 0")
    assert mb.overlap_volume(p.model.body(1).shape, p.model.body(2).shape, 0.05) < 1.0
    assert robust.volume(p.model.body(1).shape) > 0


def test_helical_rack_meshes_with_its_gear():
    p = Processor()
    run(p, "GEAR, 0, 0, 0, 2, 20, 10, EXTERNAL, 15", "GEAR, 300-5*PI*2/COS(15), -20.70552-0.05, 0, 2, 30, 10, RACK, 15")
    assert mb.overlap_volume(p.model.body(1).shape, p.model.body(2).shape, 0.05) < 0.05


# ---- DXF and pictures into a sketch -------------------------------------------------------------
def test_dxf_reader_keeps_the_entities():
    ents, notes = dxfread.read(DXF)
    kinds = [e.kind for e in ents]
    assert kinds == ["POLY", "CIRCLE", "SPLINE"]
    poly = ents[0]
    assert poly.closed and len(poly.pts) == 5 and poly.pts[1][2] == pytest.approx(0.4142135623)
    mid = dxfread.bulge_arc((80, 0), (100, 20), 0.4142135623)  # a quarter circle about (80, 20)
    assert math.dist(mid, (80, 20)) == pytest.approx(20, rel=1e-6)
    with pytest.raises(dxfread.DxfError, match="ENTITIES"):
        dxfread.read("0\nSECTION\n2\nHEADER\n0\nENDSEC\n")


def test_sdxf_makes_a_plate_with_a_hole(tmp_path):
    f = tmp_path / "plate.dxf"
    f.write_text(DXF)
    p = Processor()
    run(p, "SKETCH, s, XY")
    msg = run(p, f'SDXF, "{f}", 1, 0, 0, OUTLINE').message
    assert "1 " in msg or "geometr" in msg
    run(p, f'SDXF, "{f}", 1, 0, 0, HOLES', "ENDSKETCH", "EXTRUDE, s, 5")
    area = 100 * 50 - 20 * 20 + math.pi * 20 ** 2 / 4 - math.pi * 8 ** 2
    assert robust.volume(p.model.body(1).shape) == pytest.approx(area * 5, rel=1e-4)
    fails(p, f'SDXF, "{f}"', "sketch")  # not sketching any more


def _picture(path, h=200, w=300):
    try:  # reading and writing pictures needs Qt's GUI library, which needs libEGL; CI's plain runners lack it
        from PySide6.QtGui import QImage
    except ImportError as exc:
        pytest.skip(f"Qt pictures cannot load here ({exc})")

    a = np.full((h, w), 255, np.uint8)
    yy, xx = np.mgrid[:h, :w]
    ring = ((xx - 80) ** 2 + (yy - 100) ** 2 <= 60 ** 2) & ((xx - 80) ** 2 + (yy - 100) ** 2 >= 22 ** 2)
    a[ring] = 0
    a[60:140, 180:270] = 0  # a rectangle
    img = QImage(a.tobytes(), w, h, w, QImage.Format_Grayscale8)
    assert img.save(str(path))


def test_strace_outlines_a_picture(tmp_path):
    f = tmp_path / "shapes.png"
    _picture(f)
    p = Processor()
    run(p, "SKETCH, s, XY")
    msg = run(p, f'STRACE, "{f}", 300, 128, 0, 0').message
    assert "traced 3 outlines" in msg
    run(p, "ENDSKETCH", "EXTRUDE, s, 2")
    expected = (math.pi * (60 ** 2 - 22 ** 2) + 90 * 80) * 2
    assert robust.volume(p.model.body(1).shape) == pytest.approx(expected, rel=0.03)
    p2 = Processor()
    run(p2, "SKETCH, s, XY")
    assert "traced 3" in run(p2, f'STRACE, "{f}", 300, 128, 0, 0, LINES').message
    fails(p2, f'STRACE, "{tmp_path / "missing.png"}", 300', "no such file")


def test_image_underlay_is_kept_and_cleared(tmp_path):
    f = tmp_path / "shapes.png"
    _picture(f)
    p = Processor()
    run(p, f'IMAGE, "{f}", XY, 150')
    assert len(p.model.pictures) == 1
    pic = p.model.pictures[0]
    assert pic.width == pytest.approx(150) and pic.height == pytest.approx(100)
    run(p, "UNDO")
    assert p.model.pictures == []
    run(p, "REDO")
    assert len(p.model.pictures) == 1
    run(p, "IMAGE, CLEAR")
    assert p.model.pictures == []


# ---- TOPOPT -----------------------------------------------------------------------------------
def test_topopt_keeps_the_share_and_a_load_path():
    pytest.importorskip("scipy")
    p = Processor()
    run(p, "BLOCK, 0, 0, 0, 80, 6, 30")
    run(p, "SEL, S, FACE, NORMAL, -1, 0, 0", "CM, wall, FACE", "SEL, S, FACE, NORMAL, 1, 0, 0", "CM, tip, FACE",
        "SEL, NONE")
    msg = run(p, "TOPOPT, 1, wall, tip, FORCE, 0, 0, -500, 0.35, 20, 3").message
    assert "kept" in msg and "topo_1" in msg
    topo = p.model.body_by_name("topo_1")
    assert mb.is_mesh(topo.shape)
    pts, t = mb.arrays(topo.shape)
    share = mb.volume(pts, t) / (80 * 6 * 30)
    assert 0.25 < share < 0.45
    assert 1 in p.model.hidden
    assert mb.pieces(pts, t) == 1  # one connected part from wall to tip
    fails(p, "TOPOPT, 1, wall, tip, FORCE, 0, 0, -500, 1.5", "share")
    fails(p, "TOPOPT, 1, wall, tip, FORCE, 0, 0, 0", "zero")
