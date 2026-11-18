"""M6c: sketch splines (SSPLINE, the Freehand tool) and knife cuts (KNIFE,
the Knife tool's commands)."""

import math

import pytest

from modeler.commands import Processor
from modeler.geometry import meshbody as mb
from modeler.geometry import robust
from modeler.gui import knife_tool as kt
from modeler.gui import sketch_tools as st


def run(*lines):
    p = Processor()
    for line in lines:
        r = p.run(line)
        assert r.ok, f"{line}: {r.message}"
    return p


def vol(p, b):
    s = p.model.bodies[b].shape
    return mb.info(s).volume if mb.is_mesh(s) else robust.volume(s)


# ---- sketch splines -----------------------------------------------------------------


def test_closed_sketch_spline_extrudes_and_cuts():
    p = run("BLOCK, 0, 0, 0, 60, 40, 10", "SKETCH, s, FACE, 6",
            "SSPLINE, 10,10, 25,30, 45,25, 50,8, 30,5, CLOSE", "ENDSKETCH", "EXTRUDE, s, -4, CUT")
    (b,) = p.model.bodies
    assert 60 * 40 * 10 - 4 * 400 < vol(p, b) < 60 * 40 * 10 - 4 * 250  # a pocket of about 310 mm2


def test_open_spline_closes_with_a_line_and_its_points_are_named():
    p = run("SKETCH, s, XY", "SSPLINE, 0,0, 10,10, 20,0", "SLINE, 1.E, 1.S", "ENDSKETCH", "EXTRUDE, s, 5")
    (b,) = p.model.bodies
    assert vol(p, b) == pytest.approx(2 / 3 * 20 * 10 * 5, rel=1e-3)  # a parabola through the three points
    sk = p.model.sketches["S"]
    assert sk.ref("1.K1").is_point and sk.pt(sk.ref("1.K1").point) == (10, 10)


def test_spline_points_drag_and_take_constraints():
    p = run("SKETCH, s, XY", "SSPLINE, 0,0, 10,10, 20,0, 30,5", "SCON, FIX, 1.K2", "SMOVE, 1.K1, 10, 15")
    sk = p.model.sketches["S"]
    assert sk.pt(sk.ref("1.K1").point) == pytest.approx((10, 15))
    assert sk.pt(sk.ref("1.K2").point) == pytest.approx((20, 0))
    r = p.run("STRIM, 1, 5, 5")  # splines trim now: nothing crosses it, so all of it goes
    assert r.ok and "deleted spline 1" in r.message
    assert p.run("UNDO").ok
    assert p.run("SMIRROR, H, 1").ok


def test_spline_needs_points():
    p = run("SKETCH, s, XY")
    assert "at least two" in p.run("SSPLINE, 0, 0").message
    assert "same" in p.run("SSPLINE, 0,0, 0,0, 5,5").message
    assert "1.K9" not in p.run("SSPLINE, 0,0, 5,5, 10,0").message
    assert "K1" in p.run("SCON, FIX, 1.K9").message


def test_freehand_commands():
    circle = [(10 * math.cos(a / 50 * 2 * math.pi), 10 * math.sin(a / 50 * 2 * math.pi)) for a in range(51)]
    (cmd,) = st.freehand_commands(circle, 0.3)
    assert cmd.startswith("SSPLINE, 10, 0,") and cmd.endswith("CLOSE")
    assert cmd.count(",") < 2 * st.MAX_STROKE_POINTS + 2
    assert st.freehand_commands([(i * 0.5, 0.01 * (i % 2)) for i in range(40)], 0.3) == ["SLINE, 0, 0, 19.5, 0.01"]
    wave = [(i * 0.5, 3 * math.sin(i * 0.2)) for i in range(60)]
    (cmd,) = st.freehand_commands(wave, 0.3, "1.E", "2.S")
    assert cmd.startswith("SSPLINE, 1.E,") and cmd.endswith(", 2.S")
    assert st.freehand_commands([(0, 0), (0.1, 0)], 0.3) == []  # a slip


def test_freehand_spline_runs_and_closes():
    circle = [(10 * math.cos(a / 50 * 2 * math.pi), 10 * math.sin(a / 50 * 2 * math.pi)) for a in range(51)]
    (cmd,) = st.freehand_commands(circle, 0.3)
    p = run("SKETCH, s, XY", cmd, "ENDSKETCH", "EXTRUDE, s, 2")
    (b,) = p.model.bodies
    assert vol(p, b) == pytest.approx(math.pi * 100 * 2, rel=5e-3)


# ---- KNIFE --------------------------------------------------------------------------------


def test_open_stroke_splits_a_block():
    p = run("BLOCK, 0,0,0, 40,20,10", "SPLINE, (10,-5,20), (22,10,20), (30,25,20)", "KNIFE, 1, 2, 0, 0,0,-1")
    assert sorted(p.model.bodies) == [1, 2, 3]
    assert vol(p, 1) + vol(p, 3) == pytest.approx(8000)
    assert vol(p, 1) >= vol(p, 3) > 1000  # the biggest piece keeps the ID
    assert 2 in p.model.hidden  # the stroke
    assert p.model.last_body == 1


def test_short_stroke_is_carried_through_the_body():
    p = run("BLOCK, 0,0,0, 40,20,10", "LINE, 20,8,5, 20,12,5", "KNIFE, 1, 2, 0, 0,0,1")
    assert vol(p, 1) == pytest.approx(4000) and vol(p, 3) == pytest.approx(4000)


def test_slot():
    p = run("BLOCK, 0,0,0, 40,20,10", "LINE, 20,-5,5, 20,25,5", "KNIFE, 1, 2, 2, 0,0,1")
    assert vol(p, 1) == pytest.approx(3800) and vol(p, 3) == pytest.approx(3800)
    p = run("BLOCK, 0,0,0, 40,20,10", "LINE, 20,-5,5, 20,25,5", "KNIFE, 1, 2, 2, 1,0,0")
    # seen from the side the stroke runs level at mid-height: a slot right through, two slabs
    assert vol(p, 1) == pytest.approx(3200) and vol(p, 3) == pytest.approx(3200)


def test_closed_stroke_is_a_cookie_cutter():
    p = run("BLOCK, 0,0,0, 40,20,10", "CIRCLE, 20,10,30, 5", "KNIFE, 1, 2")
    assert vol(p, 3) == pytest.approx(math.pi * 25 * 10, rel=1e-6)
    assert vol(p, 1) == pytest.approx(8000 - math.pi * 25 * 10, rel=1e-6)
    p = run("BLOCK, 0,0,0, 40,20,10", "CIRCLE, 20,10,30, 5", "KNIFE, 1, 2, 1")
    assert vol(p, 3) == pytest.approx(math.pi * 4.5 ** 2 * 10, rel=1e-6)  # the core inside the ring slot


@pytest.mark.parametrize("closed", [False, True])
def test_mesh_bodies(closed):
    stroke = "CIRCLE, 20,10,30, 5" if closed else "SPLINE, (10,-5,20), (22,10,20), (30,25,20)"
    p = run("BLOCK, 0,0,0, 40,20,10", "TOMESH, 1", stroke, "KNIFE, 1, 2, 0, 0,0,-1")
    assert all(mb.is_mesh(p.model.bodies[b].shape) for b in (1, 3))
    assert vol(p, 1) + vol(p, 3) == pytest.approx(8000, rel=2e-3)


def test_knife_refusals():
    p = run("BLOCK, 0,0,0, 40,20,10", "LINE, 20,-5,5, 20,25,5", "BLOCK, 50,0,0, 5,5,5")
    assert "direction" in p.run("KNIFE, 1, 2").message
    assert "not a curve" in p.run("KNIFE, 1, 3, 0, 0,0,1").message
    assert "single point" in p.run("KNIFE, 1, 2, 0, 0,1,0").message  # seen along itself
    assert "negative" in p.run("KNIFE, 1, 2, -1, 0,0,1").message
    p.run("CIRCLE, 100,100,0, 2")
    assert "does not cut" in p.run("KNIFE, 1, 4").message


def test_knife_is_history():
    p = run("BLOCK, 0,0,0, 40,20,10", "LINE, 20,-5,5, 20,25,5", "KNIFE, 1, 2, 0, 0,0,1")
    r = p.run('HIST, EDIT, 2, "LINE, 10,-5,5, 10,25,5"')
    assert r.ok, r.message
    assert sorted(round(vol(p, b)) for b in (1, 3)) == [2000, 6000]


# ---- the Knife tool's commands --------------------------------------------------------------


def _top_view_ray(x, y):
    """A view from above: pixel (x, y) is world (x / 10, -y / 10)."""
    return (x / 10, -y / 10, 100.0), (0.0, 0.0, -1.0)


def test_knife_tool_commands():
    px = [(100 + i, -150 + 15 * i) for i in range(21)]  # world (10, 15) to (12, -15), across the block
    cmds = kt.knife_commands(px, _top_view_ray, (20, 10, 5), 1)
    assert cmds[0].startswith("LINE, 10, 15, 5, 12, -15, 5")
    assert cmds[1] == "KNIFE, 1, LAST, 0, 0, 0, -1"
    p = run("BLOCK, 0,0,0, 40,20,10", *cmds)
    assert sorted(p.model.bodies) == [1, 2, 3] and vol(p, 1) + vol(p, 3) == pytest.approx(8000)


def test_knife_tool_closed_stroke_and_slips():
    ring = [(200 + 50 * math.cos(a / 40 * 2 * math.pi), -100 + 50 * math.sin(a / 40 * 2 * math.pi)) for a in range(41)]
    cmds = kt.knife_commands(ring, _top_view_ray, (20, 10, 5), 1)
    assert cmds[0].startswith("SPLINE, (") and cmds[0].endswith("CLOSE")
    p = run("BLOCK, 0,0,0, 40,20,10", *cmds)
    assert vol(p, 3) == pytest.approx(math.pi * 25 * 10, rel=2e-2)
    assert kt.knife_commands([(0, 0), (3, 0)], _top_view_ray, (0, 0, 0), 1) == []


def test_knife_tool_target_body():
    hits = {(5, 5): 2, (6, 6): 2, (7, 7): 3}
    assert kt.target_body(list(hits), lambda x, y: hits.get((x, y)), None) == 2
    assert kt.target_body(list(hits), lambda x, y: hits.get((x, y)), 7) == 7
    assert kt.target_body([(0, 0)], lambda x, y: None, None) is None
