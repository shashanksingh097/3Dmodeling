"""PLAN item 104: SREPAIR closes gaps, removes duplicates and specks, and refits chains of short lines."""

import math

from modeler.commands import Processor


def ok(p, text):
    r = None
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
    return r


def messy(p):
    """A plate outline with a gap at one corner, a line drawn twice, a speck, and a round end drawn
    as 24 short lines (the way traced or exported drawings come)."""
    ok(p, "SKETCH, s, XY")
    lines = ["SLINE, 0, 0, 60, 0",
             "SLINE, 60, 0, 60, 30",
             "SLINE, 60, 0, 60, 30",  # drawn twice
             "SLINE, 0.03, 0, 0, 30"]  # does not quite meet (0, 0)
    pts = [(60 - 0 + 30 * 0 + 0, 0)]
    # the top: a half circle from (60, 30) to (0, 30), radius 30, centre (30, 30), as 24 lines
    arc = [(30 + 30 * math.cos(math.pi * k / 24), 30 + 30 * math.sin(math.pi * k / 24)) for k in range(25)]
    for a, b in zip(arc, arc[1:]):
        lines.append(f"SLINE, {a[0]:.6f}, {a[1]:.6f}, {b[0]:.6f}, {b[1]:.6f}")
    lines.append("SLINE, 70, 10, 70.00001, 10")  # a speck (away from the rest)
    del pts
    for ln in lines:
        r = p.run(ln)
        if not r.ok:  # SLINE refuses a zero-length line; a speck may be refused as too short
            assert "two different points" in r.message
    # the ends that meet were drawn on top of each other: tie them as an import would
    return p.model.sketches["S"]


def test_scheck_suggests_and_srepair_fixes(monkeypatch):
    p = Processor()
    messy(p)
    r = ok(p, "SCHECK")
    assert "SREPAIR would help" in r.message
    r = ok(p, "SREPAIR, 0.1")
    rep = p.reports["SREPAIR"]
    assert len(rep["duplicates"]) == 1
    assert rep["gaps_closed"] >= 1 and rep["largest_gap"] <= 0.1
    assert rep["lines_refit"] == 24 and len(rep["splines"]) == 1
    sk = p.model.sketches["S"]
    kinds = sorted(g.kind for g in sk.geos.values())
    assert kinds.count("SPLINE") == 1 and kinds.count("LINE") == 3
    ok(p, "ENDSKETCH")
    r = ok(p, "EXTRUDE, s, 5")
    vol = 60 * 30 + math.pi * 30 ** 2 / 2  # rectangle + half disc
    ok(p, "MASSPROP, LAST")
    assert abs(p.reports["MASSPROP"]["volume"] - 5 * vol) / (5 * vol) < 0.01


def test_options():
    p = Processor()
    messy(p)
    ok(p, "SREPAIR, 0.1, 0, NO")
    rep = p.reports["SREPAIR"]
    assert rep["lines_refit"] == 0 and rep["gaps_closed"] >= 1
    # nothing left to do
    r = ok(p, "SREPAIR, 0.1, 0, NO")
    assert "nothing to repair" in r.message
    assert not p.run("SREPAIR, -1").ok
    assert not p.run("SREPAIR, 0, 0, MAYBE").ok
    ok(p, "ENDSKETCH")
    assert not p.run("SREPAIR").ok  # no open sketch


def test_corners_are_kept():
    p = Processor()
    ok(p, "SKETCH, s, XY")
    # a zigzag of 8 short lines with sharp turns: corners, not a curve
    pts = [(i * 2.0, (i % 2) * 2.0) for i in range(9)]
    for a, b in zip(pts, pts[1:]):
        ok(p, f"SLINE, {a[0]}, {a[1]}, {b[0]}, {b[1]}")
    ok(p, "SREPAIR")
    assert p.reports["SREPAIR"]["lines_refit"] == 0


def test_undo_and_rebuild_keep_it():
    p = Processor()
    messy(p)
    ok(p, "SREPAIR, 0.1")
    n = len(p.model.sketches["S"].geos)
    ok(p, "UNDO")
    assert len(p.model.sketches["S"].geos) > n
    ok(p, "REDO")
    p.rebuild(0)
    assert len(p.model.sketches["S"].geos) == n
