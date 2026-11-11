"""Sketches: the solver, the sketch commands, profiles, EXTRUDE and REVOLVE,
and what the GUI's sketch tools send (headless)."""

import math

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.core import datum as dt
from modeler.gui import sketch_tools as st
from modeler.sketch import profile as prof
from modeler.sketch import solver
from modeler.sketch.sketch import Sketch, SketchError


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1].message


def err(p, line):
    r = p.run(line)
    assert not r.ok, r.message
    return r.message


def sk_xy():
    return Sketch("s", dt.plane((0, 0, 0), (0, 0, 1)))


PLATE = """
SKETCH, s1, XY
SRECT, 0, 0, 78, 42
SCON, COINCIDENT, 1.S, ORIGIN
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, 40
SCIRCLE, 20, 20, 5
SDIM, DIAMETER, 5, 10
SDIM, HDIST, ORIGIN, 5.C, 20
SDIM, VDIST, ORIGIN, 5.C, 20
ENDSKETCH
"""


# ---- solver -------------------------------------------------------------------------
def test_solver_moves_as_little_as_possible():
    # one point pulled onto x = 5: y stays where it was
    x = np.array([1.0, 7.0])
    c = solver.Constraint(1, (0,), lambda v: [v[0] - 5])
    rep = solver.solve(x, [c])
    assert rep.ok and rep.dof == 1 and x[1] == 7.0 and abs(x[0] - 5) < 1e-12
    assert rep.free == {1}


def test_solver_names_conflicting_and_redundant():
    x = np.array([0.0])
    a = solver.Constraint(1, (0,), lambda v: [v[0] - 1])
    b = solver.Constraint(2, (0,), lambda v: [v[0] - 2])
    rep = solver.solve(x, [a, b])
    assert not rep.ok and rep.conflicting == [2]
    x = np.array([0.0])
    rep = solver.solve(x, [a, solver.Constraint(3, (0,), lambda v: [2 * v[0] - 2])])
    assert rep.ok and rep.redundant == [3] and rep.dof == 0


def test_rectangle_dof_and_full_definition():
    s = sk_xy()
    s.add_rect((0.2, 0.1), (38, 22))
    s.solve()
    assert s.dof == 4  # where it is (2) and how big (2)
    s.add_con("COINCIDENT", ("1.S", "ORIGIN"))
    s.add_con("LENGTH", ("1",), 40)
    s.add_con("LENGTH", ("2",), 20)
    assert s.dof == 0 and all(s.fully_defined(g) for g in s.geos.values())
    assert s.pt(s.geos[2].pts["E"]) == pytest.approx((40, 20), abs=1e-9)


def test_over_constraint_is_refused_and_names_the_others():
    s = sk_xy()
    s.add_rect((0, 0), (40, 20))
    s.add_con("LENGTH", ("1",), 40)
    with pytest.raises(SketchError) as e:
        s.add_con("LENGTH", ("3",), 30)
    assert "over-constrained" in str(e.value) and "C" in str(e.value)
    assert len(s.cons) == 9  # the refused one is not kept


def test_dimensions_keep_the_side_they_were_drawn_on():
    s = sk_xy()
    s.add_line((0, 0), (10, 0))
    s.add_point((5, -3))
    s.add_con("DIST", ("2", "1"), 8)
    # both move a little (least change), but the point stays below the line
    assert s.pt(s.geos[2].pts["P"])[1] - s.pt(s.geos[1].pts["S"])[1] == pytest.approx(-8)
    s.add_line((0, 0), (10, 2))
    s.add_con("ANGLE", ("1", "3"), 30)
    assert s.measure("ANGLE", ("1", "3")) == pytest.approx(30)


def test_slot_has_five_degrees_of_freedom():
    s = sk_xy()
    s.add_slot((0, 0), (20, 0), 4)
    s.solve()
    assert s.dof == 5 and not s.redundant  # two centres and a radius


def test_tangent_line_and_circle():
    s = sk_xy()
    s.add_circle((0, 0), 5)
    s.add_line((-10, 7), (10, 6))
    s.add_con("TANGENT", ("2", "1"))
    a, b = s.pt(s.geos[2].pts["S"]), s.pt(s.geos[2].pts["E"])
    c = s.pt(s.geos[1].pts["C"])
    d = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / math.hypot(b[0] - a[0], b[1] - a[1])
    assert d == pytest.approx(s.radius(s.geos[1]))


def test_drag_follows_the_constraints():
    s = sk_xy()
    s.add_line((0, 0), (10, 0))
    s.add_con("COINCIDENT", ("1.S", "ORIGIN"))
    s.add_con("HORIZONTAL", ("1",))
    s.move("1.E", 25, 9)  # it can only slide along H
    assert s.pt(s.geos[1].pts["E"]) == pytest.approx((25, 0), abs=1e-6)


# ---- profiles -----------------------------------------------------------------------
def test_profile_nesting_holes_and_islands():
    s = sk_xy()
    s.add_rect((0, 0), (100, 100))
    s.add_rect((10, 10), (90, 90))
    s.add_circle((50, 50), 10)
    regs = prof.regions(s)
    assert len(regs) == 2  # the frame (with the inner square as hole) and the disc (an island)
    assert sorted(len(h) for _, h in regs) == [0, 1]


def test_profile_errors_name_the_place():
    s = sk_xy()
    s.add_poly([(0, 0), (10, 0), (10, 10)], False)
    with pytest.raises(SketchError, match="not closed"):
        prof.loops(s)
    s = sk_xy()
    s.add_rect((0, 0), (10, 10))
    s.add_line((10, 10), (20, 20))
    with pytest.raises(SketchError):
        prof.loops(s)


def test_construction_is_left_out():
    s = sk_xy()
    s.add_rect((0, 0), (10, 10))
    s.add_line((0, 0), (10, 10), construction=True)
    assert len(prof.regions(s)) == 1


# ---- commands -----------------------------------------------------------------------
def test_sketch_extrude_and_edit_a_size(p):
    ok(p, "W = 80" + PLATE + "EXTRUDE, s1, 10\nNAME, LAST, plate")
    v = p.evaluate("VOL(plate)")
    assert v == pytest.approx(80 * 40 * 10 - math.pi * 25 * 10, rel=1e-6)
    # the size of a sketch is a history entry: change it and the extrude follows
    n = next(i for i, e in enumerate(p.history) if e.text.startswith("SDIM, LENGTH, 2")) + 1
    ok(p, f'HIST, EDIT, {n}, "SDIM, LENGTH, 2, 50"')
    assert p.evaluate("VOL(plate)") == pytest.approx(80 * 50 * 10 - math.pi * 25 * 10, rel=1e-6)
    # and through a parameter
    k = p.entry_for_param("W")
    ok(p, f'HIST, EDIT, {k}, "W = 100"')
    assert p.evaluate("VOL(plate)") == pytest.approx(100 * 50 * 10 - math.pi * 25 * 10, rel=1e-6)


def test_sketch_on_face_add_and_cut(p):
    ok(p, "BLOCK, 0,0,0, 60,40,10\nNAME, LAST, base\nSEL, S, FACE, NORMAL, 0,0,1")
    ok(p, "SKETCH, top, FACE, SEL\nSCIRCLE, 0, 0, 5\nEXTRUDE, top, 8, ADD")
    v1 = p.evaluate("VOL(base)")
    assert v1 == pytest.approx(60 * 40 * 10 + math.pi * 25 * 8, rel=1e-6)
    assert p.evaluate("BBOX(base).zmax") == pytest.approx(18)
    ok(p, "SKETCH, pocket, XY, \nSRECT, 5, 5, 15, 15\nEXTRUDE, pocket, 0, CUT, base")  # through all
    assert p.evaluate("VOL(base)") == pytest.approx(v1 - 100 * 10, rel=1e-6)
    msg = err(p, "SKETCH, top, XY")
    assert "already a sketch" in msg


def test_extrude_both_ways_and_errors(p):
    ok(p, "SKETCH, s, XY\nSRECT, 0,0, 10,10\nEXTRUDE, s, 5, NEW, , 5")
    assert p.evaluate("BBOX(LAST).zmin") == pytest.approx(-5)
    ok(p, "SKETCH, open, XY\nSLINE, 0,0, 10,0")
    assert "not closed" in err(p, "EXTRUDE, open, 5")
    assert "only with CUT" in err(p, "EXTRUDE, s, 0")


def test_revolve_about_a_construction_line(p):
    ok(p, "SKETCH, r, ZX\nSRECT, 10, 0, 20, 30\nSLINE, 0, -5, 0, 40, V, CONSTR\nREVOLVE, r, 5")
    assert p.evaluate("VOL(LAST)") == pytest.approx(math.pi * (20 ** 2 - 10 ** 2) * 30, rel=1e-6)
    ok(p, "SKETCH, q, XY\nSCIRCLE, 30, 0, 5\nREVOLVE, q, V, 90")
    assert p.evaluate("VOL(LAST)") == pytest.approx(math.pi * 25 * 2 * math.pi * 30 / 4, rel=1e-6)


def test_sketch_steps_undo_and_errors(p):
    ok(p, "SKETCH, s, XY\nSLINE, 0,0, 10,0, H\nSLINE, 1.E, 10, 10, V")
    sk = p.model.sketches["S"]
    assert len(sk.cons) == 3  # level, tied to line 1, upright
    p.undo()
    assert len(p.model.sketches["S"].geos) == 1
    assert "over-constrained" in err(p, "SCON, VERTICAL, 1")
    assert "no geometry 9" in err(p, "SCON, HORIZONTAL, 9")
    assert "is a dimension" in err(p, "SCON, LENGTH, 1")
    ok(p, "ENDSKETCH")
    assert "no sketch is open" in err(p, "SLINE, 0,0, 1,1")


def test_list_sketch_and_sel(p):
    ok(p, "SKETCH, s, XY\nSRECT, 0,0, 10,5")
    text = p.run("LIST, SKETCH").message
    assert "line 1" in text and "C1 coincident" in text
    p.run("SSEL, 1, 2.E")
    assert p.model.sketch_selection == ["1", "2.E"]
    assert len(p.history) == 2  # SSEL is not history


def test_spoly_and_slot_commands(p):
    ok(p, "SKETCH, s, XY\nSPOLY, 0,0, 20,0, (20, 10), 0,10, CLOSE\nSSLOT, 5,5, 15,5, 2\nEXTRUDE, s, 2")
    assert p.evaluate("VOL(LAST)") == pytest.approx((200 - (10 * 4 + math.pi * 4)) * 2, rel=1e-6)


# ---- what the GUI sends -----------------------------------------------------------------
def test_line_tool_chains_and_closes(p):
    p.run("SKETCH, s, XY")
    c = st.SketchController(p)
    c.set_tool("LINE")
    sent = []
    for u, v in [(0.05, 0.02), (40, 0.4), (40, 20), (0, 20.3), (0.1, 0.1)]:
        for cmd in c.click(u, v, 0.8):
            sent.append(cmd)
            assert p.run(cmd).ok
    assert sent[0] == "SLINE, ORIGIN, 40, 0, H"  # snapped to the origin, made level
    assert sent[-1].startswith("SLINE, 3.E, ORIGIN")
    assert len(prof.regions(p.model.sketches["S"])) == 1


def test_select_and_buttons_build_commands(p):
    p.run_script("SKETCH, s, XY\nSRECT, 0,0, 40,20\nSCIRCLE, 10,10, 3")
    c = st.SketchController(p)
    assert c.click(20, 0.1, 0.5) == ["SSEL, 1"]
    p.run("SSEL, 1")
    assert st.dimension_for(p) == ("LENGTH", ["1"], pytest.approx(40))
    p.run("SSEL, 5")
    assert st.dimension_for(p)[0] == "DIAMETER"
    p.run("SSEL, 1")
    p.run("SSEL, A, 3")
    assert st.constraint_command(p, "EQUAL") == ["SCON, EQUAL, 1, 3"]
    with pytest.raises(st.NeedSelection):
        st.constraint_command(p, "TANGENT")
    p.run("SSEL, 5.C")
    assert st.dimension_for(p, "HDIST") == ("HDIST", ["ORIGIN", "5.C"], pytest.approx(10))
    assert p.run(st.dimension_command("HDIST", ["ORIGIN", "5.C"], "12")).ok
    label = next(c.label for c in p.model.sketches["S"].cons.values() if c.is_dim)
    line = st.edit_dimension_entry(p, label, "15")
    assert line.startswith("HIST, EDIT") and p.run(line).ok
    assert p.model.sketches["S"].pt(p.model.sketches["S"].geos[5].pts["C"])[0] == pytest.approx(15)


def test_clicks_are_rounded_and_drag_sends_smove(p):
    p.run_script("SKETCH, s, XY\nSLINE, 0,0, 10,0")
    c = st.SketchController(p)
    c.set_tool("CIRCLE")
    c.click(20.123, 5.04, 2)  # snap distance 2 rounds to whole numbers
    assert c.click(23.31, 5.0, 2) == ["SCIRCLE, 20, 5, 3"]
    c.set_tool("SELECT")
    c.press(10, 0, 0.5)
    assert c.drag == "1.E"
    c.move(12, 3, 0.5)
    assert c.preview.sketch is not None
    assert c.release(12, 3, 0.5) == ["SMOVE, 1.E, 12, 3"]


def test_a_parameter_named_like_a_flag(p):
    # H is also the "make it level" flag; as the last value it is the parameter
    ok(p, "H = 30\nSKETCH, s, XY\nSRECT, 0, 0, 50, H\nSLINE, 0, 40, 10, 41, H")
    sk = p.model.sketches["S"]
    assert sk.pt(sk.geos[2].pts["E"])[1] == pytest.approx(30)
    assert sk.cons[max(sk.cons)].kind == "HORIZONTAL"


def test_example_script_runs(p):
    from pathlib import Path

    text = (Path(__file__).parent.parent / "scripts" / "sketch_bracket.cmd").read_text()
    ok(p, text)
    assert len(p.model.bodies) == 2
