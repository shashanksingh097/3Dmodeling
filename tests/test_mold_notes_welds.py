"""PARTING, MOLD, FITS, NOTE, WELD (PLAN items 34 to 36)."""

import math

import pytest

from modeler.commands import Processor
from modeler.geometry import fits as ft
from modeler.geometry import molding as mo
from modeler.geometry import robust


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def fails(p, line, text):
    r = p.run(line)
    assert not r.ok and text in r.message, r.message


# ---- moulds ----------------------------------------------------------------------------


def _cover(p):
    run(p, "BLOCK, 0,0,0, 40,30,10", "CYL, 20,15,10, 8, 10", "UNION, 1, 2", "NAME, LAST, cover")


def test_parting_flat_part():
    p = Processor()
    _cover(p)
    r = run(p, "PARTING, cover")
    assert "needs draft" in r.message and "parting line: 4 edges, flat, at 0" in r.message
    r = run(p, "PARTING, cover, 0,0,1, 0")
    assert "ready for a two-part mould" in r.message
    assert p.analysis.mode == "DRAFT"


def test_parting_undercut_and_round():
    p = Processor()
    # a T lying on its side: pulled along Z the stem's sides are under the bar
    run(p, "BLOCK, 0,0,0, 10,10,30", "BLOCK, 0,-10,20, 10,30,5", "UNION, 1, 2")
    r = run(p, "PARTING, LAST, 0,0,1, 0")
    assert "UNDERCUTS" in r.message
    run(p, "SPHERE, 100,0,0, 10")
    r = run(p, "PARTING, LAST")
    assert "crosses faces" in r.message
    part = mo.parting(p.model.bodies[p.model.last_body].shape, (0, 0, 1))
    level, why = mo.default_level(p.model.bodies[p.model.last_body].shape, part)
    assert abs(level) < 0.5 and "widest" in why


def test_mold_halves():
    p = Processor()
    _cover(p)
    r = run(p, "MOLD, cover, 5, 0.5")
    assert "cover_top" in r.message and "cover_bottom" in r.message
    top = p.model.body_by_name("cover_top").shape
    bottom = p.model.body_by_name("cover_bottom").shape
    part = p.model.body_by_name("cover").shape
    block = 50 * 40 * 30 * 1.005 ** 0  # the block grows with the shrunk part, roughly
    assert robust.is_valid(top) and robust.is_valid(bottom)
    total = robust.volume(top) + robust.volume(bottom)
    assert total < block * 1.02 and total > block * 0.98 - robust.volume(part) * 1.1
    # the cavity is bigger than the part by the shrink
    run(p, "MOLD, cover, 5, 0, 0,0,1, 5")
    t2, b2 = p.model.body_by_name("cover_top2").shape, p.model.body_by_name("cover_bottom2").shape
    assert math.isclose(robust.volume(t2) + robust.volume(b2), 50 * 40 * 30 - robust.volume(part), rel_tol=1e-6)
    fails(p, "MOLD, cover, 5, 0, 0,0,1, 80", "outside the part")


# ---- fits ------------------------------------------------------------------------------


@pytest.mark.parametrize("spec,size,upper,lower", [
    ("H7", 25, 21, 0), ("g6", 25, -7, -20), ("f7", 25, -20, -41), ("k6", 25, 15, 2), ("n6", 25, 28, 15),
    ("p6", 25, 35, 22), ("d9", 25, -65, -117), ("H7", 10, 15, 0), ("K7", 25, 6, -15), ("N7", 25, -7, -28),
    ("P7", 25, -14, -35), ("js6", 25, 6.5, -6.5), ("H8", 50, 39, 0), ("g6", 100, -12, -34),
])
def test_iso_286_values(spec, size, upper, lower):
    lim = ft.limits(spec, size)
    assert (lim.upper, lim.lower) == (upper, lower)


def test_fits_command():
    p = Processor()
    r = run(p, "FITS, H7/g6, 25")
    assert "a clearance fit" in r.message and "clearance from 0.007 to 0.041" in r.message
    assert "an interference fit" in run(p, "FITS, H7/p6, 25").message
    assert "a transition fit" in run(p, "FITS, H7/k6, 25").message
    run(p, "BLOCK, 0,0,0, 60,40,20", "HOLE, 1, 30,20,20, 12", "SEL, S, FACE, TYPE, CYLINDER")
    assert "ø12 H7: +0.018/0" in run(p, "FITS, H7").message
    fails(p, "FITS, H7/g6, 600", "up to 500")
    fails(p, "FITS, Z7, 25", "not covered")
    fails(p, "FITS, g6/H7, 25", "hole first")


# ---- notes -----------------------------------------------------------------------------


def test_notes_and_drawing(tmp_path):
    p = Processor()
    run(p, "BLOCK, 0,0,0, 100,60,20", "HOLE, 1, 30,30,20, 25", "SEL, S, FACE, TYPE, CYLINDER")
    r = run(p, "NOTE, FIT, H7")
    assert "ø25 H7 (+0.021/0)" in r.message
    n = p.model.notes[0]
    assert n.anchor is not None and n.at[2] > 20  # the leader goes up from the rim
    run(p, 'NOTE, "Break edges", 120,0,30, 100,0,20', "NOTE, SIZE, 0,0,0, 100,0,0")
    assert p.model.notes[2].text == "100" and p.model.notes[2].span is not None
    run(p, "SEL, S, FACE, LOC, Z, 0", 'NOTE, "Ground flat"')
    assert len(p.model.notes) == 4
    assert "4: \"Ground flat\"" in run(p, "LIST, NOTES").message
    out = tmp_path / "n.svg"
    r = run(p, f"DRAWING, {out}")
    assert "4 notes placed" in r.message
    svg = out.read_text(encoding="utf-8")
    assert "Break edges" in svg and "H7" in svg
    run(p, "NOTE, DELETE, 2")
    assert len(p.model.notes) == 3
    run(p, "UNDO")
    assert len(p.model.notes) == 4
    fails(p, "NOTE, DELETE, 9", "no note 9")
    run(p, "NOTE, CLEAR")
    assert not p.model.notes
    run(p, "SEL, NONE")
    fails(p, 'NOTE, "free"', "give a point")
    fails(p, "NOTE, SIZE, 1,1,1, 1,1,1", "the same")


def test_notes_follow_history():
    p = Processor()
    run(p, "W = 50", "BLOCK, 0,0,0, W,20,10", "NOTE, SIZE, 0,0,0, W,0,0")
    assert p.model.notes[0].text == "50"
    run(p, 'HIST, EDIT, 1, "W = 80"')
    assert p.model.notes[0].text == "80"


# ---- welds -----------------------------------------------------------------------------


def test_weld_two_parts_and_cutlist():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 100,20,20", "NAME, LAST, beam", "BLOCK, 40,0,20, 20,20,60", "NAME, LAST, post")
    r = run(p, "WELD, post, beam, 5")
    assert "80 long" in r.message and "'weld_1'" in r.message
    s = p.model.body_by_name("weld_1").shape
    assert robust.is_valid(s) and len(robust.solids(s)) == 1
    assert "welds 5: 1 bead, 80 long" in run(p, "CUTLIST").message
    fails(p, "WELD, beam, weld_1", "is a weld bead")
    run(p, "BLOCK, 0,100,0, 10,10,10")
    fails(p, f"WELD, beam, {p.model.last_body}", "do not touch")


def test_weld_all_members():
    p = Processor()
    run(p, "POLYLINE, (0,0,0), (200,0,0), (200,100,0)", "MEMBER, LAST, SQUARE, 20x2, MITRE, rail")
    r = run(p, "WELD, ALL, 3")
    assert "between" in r.message
    assert "welds 3: 1 bead" in run(p, "CUTLIST").message
