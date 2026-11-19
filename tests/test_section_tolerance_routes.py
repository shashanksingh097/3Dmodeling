"""SECTION planes, STACKUP and geometric tolerance notes, ROUTE pipes and cables (PLAN items 37 to 39)."""

import math

import pytest

from modeler.commands import Processor
from modeler.geometry import robust
from modeler.geometry import routing as rt
from modeler.geometry import tolerances as tl


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def fails(p, line, text):
    r = p.run(line)
    assert not r.ok and text in r.message, r.message


# ---- section view ----------------------------------------------------------------------


def test_section_planes_and_cut_areas():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 60,40,20", "CYL, 100,0,0, 10, 30")
    n = p.cursor
    r = run(p, "SECTION, XY, ABOVE, 10")
    assert "moved 10" in r.message and "body 1: area 2400, centre (30, 20, 10)" in r.message
    assert "body 2: area 314.159" in r.message
    r = run(p, "SECTION, YZ, BELOW, 100, ADD")
    assert "(2 planes)" in r.message and "plane 2 cuts body 2: area 600" in r.message
    run(p, "SECTION, ZX, BELOW, 20, ADD")
    assert len(p.section) == 3 and p.cursor == n  # a view setting: no history
    fails(p, "SECTION, ZX, BELOW, 0, ADD", "at most 3")
    r = run(p, "SECTION, XY, BELOW, 500")
    assert "cuts no solid" in r.message and len(p.section) == 1
    fails(p, "SECTION, XY, SIDEWAYS", "ABOVE or BELOW")
    fails(p, "SECTION, XY, BELOW, 0, MORE", "NEW or ADD")
    run(p, "SECTION, OFF")
    assert p.section is None


# ---- stack-ups -------------------------------------------------------------------------


def test_stack_math():
    links = [tl.parse_link(t, float) for t in ("+100 ±0.1", "-60 +0/-0.05", "-39.8 ±0.05")]
    st = tl.Stack(links)
    assert math.isclose(st.nominal, 0.2, abs_tol=1e-12)
    lo, hi = st.worst
    assert math.isclose(lo, 0.05, abs_tol=1e-12) and math.isclose(hi, 0.4, abs_tol=1e-12)
    rlo, rhi = st.rss
    half = math.sqrt(0.1 ** 2 + 0.025 ** 2 + 0.05 ** 2)
    assert math.isclose((rlo + rhi) / 2, 0.225, abs_tol=1e-12) and math.isclose(rhi - rlo, 2 * half)
    assert math.isclose(sum(st.shares()), 100.0)
    fit = tl.parse_link("+25 H7", float)
    assert (fit.upper, fit.lower) == (0.021, 0.0)
    with pytest.raises(tl.ToleranceError):
        tl.parse_link("+25 Z7", float)


def test_stackup_command():
    p = Processor()
    r = run(p, "STACKUP, +25 H7, -25 g6")
    assert "worst case: 0.007 to 0.041" in r.message
    run(p, "W = 50")
    r = run(p, "STACKUP, +W ±0.1, -(W - 0.5) ±0.05, MIN=0.1, MAX=0.8")
    assert "the gap is 0.5 nominal" in r.message and "worst case always within" in r.message
    r = run(p, "STACKUP, +10 ±0.2, -10 ±0.1, MIN=0")
    assert "sometimes outside" in r.message and "link 1" in r.message and "overlap" in r.message
    fails(p, "STACKUP, +abc", "not a number or a parameter")
    fails(p, "STACKUP, +10, MIN=x", "must be a number")


# ---- geometric tolerances --------------------------------------------------------------


def test_gdt_notes_and_drawing(tmp_path):
    p = Processor()
    run(p, "BLOCK, 0,0,0, 100,60,20", "HOLE, 1, 30,30,20, 12", "SEL, S, FACE, LOC, Z, 0")
    assert "[A]" in run(p, "NOTE, DATUM, A").message
    fails(p, "NOTE, DATUM, A", "already on the model")
    run(p, "SEL, S, FACE, LOC, Z, 20")
    assert "| 0.05" in run(p, "NOTE, GDT, FLATNESS, 0.05").message
    fails(p, "NOTE, GDT, FLAT, 0.05, A", "takes no datum")
    fails(p, "NOTE, GDT, WOBBLE, 1", "not a geometric tolerance")
    fails(p, "NOTE, GDT, FLATNESS, -1", "more than 0")
    run(p, "SEL, S, FACE, TYPE, CYLINDER")
    r = run(p, "NOTE, GDT, POS, D0.1, A, B")
    assert "ø0.1 | A | B" in r.message and "datum B is not on the model" in r.message
    n = p.model.notes[-1]
    assert n.frame.kind == "POSITION" and n.frame.datums == ("A", "B")
    run(p, "NOTE, GDT, PERPENDICULARITY, 0.02, A")  # a second note on the same face sits higher
    assert p.model.notes[-1].at[2] > n.at[2]
    out = tmp_path / "g.svg"
    r = run(p, f"DRAWING, {out}")
    assert "4 notes placed" in r.message
    svg = out.read_text(encoding="utf-8")
    assert "ø0.1" in svg and ">A<" in svg
    run(p, "UNDO")
    assert len(p.model.notes) == 3


def test_frame_drawing_pieces():
    fr, warn = tl.frame("POSITION", "D0.2", ["A", "B", "C"])
    assert fr.text() == "⌖ | ø0.2 | A | B | C" and not warn
    lines, texts = tl.frame_lines(fr, 0, 0, 2.0)
    assert [t for _x, _y, t in texts] == ["ø0.2", "A", "B", "C"]
    w, h = tl.frame_size(fr, 2.0)
    xs = [q[0] for ln in lines for q in ln]
    assert math.isclose(max(xs) - min(xs), w) and math.isclose(h, 3.4)
    _fr, warn = tl.frame("PARALLELISM", "0.1", [])
    assert warn
    with pytest.raises(tl.ToleranceError):
        tl.frame("POSITION", "0.1", ["I"])


# ---- routes ----------------------------------------------------------------------------


def test_route_pipe_bends_and_list(tmp_path):
    p = Processor()
    run(p, "POLYLINE, (0,0,0), (200,0,0), (200,150,0), (200,150,120)")
    r = run(p, "ROUTE, LAST, PIPE, 22x1.5")
    assert "2 bends of radius 33" in r.message and "'pipe_1'" in r.message
    body = p.model.body_by_name("pipe_1")
    assert robust.is_valid(body.shape) and len(robust.solids(body.shape)) == 1
    rec = p.model.routes[body.id]
    length = 470 - 4 * 33 + 2 * math.pi / 2 * 33
    assert math.isclose(rec.length, length, rel_tol=1e-9)
    ring = math.pi / 4 * (22 ** 2 - 19 ** 2)
    assert math.isclose(robust.volume(body.shape), ring * length, rel_tol=1e-3)
    out = tmp_path / "pipes.csv"
    r = run(p, f"ROUTES, {out}")
    assert "bends 90°, 90° at radius 33" in r.message and out.exists()
    fails(p, "ROUTE, 1, PIPE, 22x1.5, 300", "too big")
    fails(p, "ROUTE, 1, PIPE, 22x12", "no bore")
    fails(p, "ROUTE, 1, PIPE, 22x1.5, 5", "more than half")
    fails(p, "ROUTE, 1, HOSE, 22", "PIPE (or TUBE) or CABLE")


def test_route_tee_and_cable():
    p = Processor()
    run(p, "POLYLINE, (0,0,0), (200,0,0)", "ROUTE, LAST, PIPE, 22x1.5")
    host = p.model.body_by_name("pipe_1")
    v0 = robust.volume(host.shape)
    run(p, "POLYLINE, (100,0,0), (100,-80,0)")
    r = run(p, "ROUTE, LAST, PIPE, 22x1.5")
    assert "tee" in r.message
    joined = p.model.body_by_name("pipe_1")
    assert joined.id == host.id and robust.is_valid(joined.shape) and len(robust.solids(joined.shape)) == 1
    ring = math.pi / 4 * (22 ** 2 - 19 ** 2)
    added = robust.volume(joined.shape) - v0
    hole = math.pi / 4 * 19 ** 2 * 1.5 * 1.1  # the branch's bore opens the main pipe's wall
    assert ring * (80 - 11) - hole < added < ring * 80  # the branch, less what sits inside the main pipe
    assert p.model.routes[joined.id].tees == 1
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    def inside(q):
        return BRepClass3d_SolidClassifier(joined.shape, gp_Pnt(*q), 1e-7).State() == TopAbs_IN

    assert not inside((100, -10.2, 0)) and not inside((50, 0, 0))  # the bores are open through the tee
    assert inside((100, -30, 10.2)) and inside((50, 0, 10.2))
    run(p, "POLYLINE, (0,50,0),(0,200,0),(-100,200,0)")
    r = run(p, "ROUTE, LAST, CABLE, 7x2.5")
    assert "bundle 7.5" in r.message and "radius 45" in r.message
    assert math.isclose(rt.bundle(7, 2.5), 7.5) and rt.bundle(1, 3) == 3
    assert "cable 7x2.5 (bundle 7.5)" in run(p, "ROUTES").message


def test_route_needs_an_open_path():
    p = Processor()
    run(p, "POLYLINE, (0,0,0), (100,0,0), (100,100,0), (0,0,0)")
    fails(p, "ROUTE, LAST, PIPE, 10x1", "closes on itself")
    run(p, "BLOCK, 0,0,0, 10,10,10")
    fails(p, "ROUTE, LAST, PIPE, 10x1", "not a path")
