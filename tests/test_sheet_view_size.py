"""PLAN item 110: views moved on a drawing sheet (SHEETVIEW) and sizes of single edges (SHEETNOTE SIZE)."""

import pytest
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Line

from modeler.commands import Processor
from modeler.commands.drawsheet_handlers import render
from modeler.geometry.features import as_edge


def _part():
    p = Processor()
    for line in ("BLOCK, 0, 0, 0, 40, 20, 10", "CYL, 20, 10, 10, 4, 5", "UNION, 1, 2",
                 "DRAWSHEET, front, STANDARD, 0, NONE, A4"):
        assert p.run(line).ok, line
    return p


def _edges(p, kind):
    m = p.model
    return [g for g in m.entity_ids("EDGE") if BRepAdaptor_Curve(as_edge(m.entity_shape("EDGE", g))).GetType() == kind]


def test_sheetview_moves_a_view_and_resets():
    p = _part()
    _o, page, _pl, _n = render(p, p.model.drawsheets["FRONT"])
    before = {b[0]: b[1:] for b in page.boxes}
    r = p.run("SHEETVIEW, front, TOP, 0, 15")
    assert r.ok and "moved by (0, 15)" in r.message
    _o, page2, _pl, _n = render(p, p.model.drawsheets["FRONT"])
    after = {b[0]: b[1:] for b in page2.boxes}
    k = page2.scale
    assert after["TOP"][1] - before["TOP"][1] == pytest.approx(15 * k, abs=1e-6)
    assert after["FRONT"] == pytest.approx(before["FRONT"])
    assert not p.run("SHEETVIEW, front, BOTTOM, 1, 1").ok
    assert not p.run("SHEETVIEW, back, TOP, 1, 1").ok
    assert p.run("SHEETVIEW, front, TOP, RESET").ok
    assert not p.model.drawsheets["FRONT"]["moves"]
    # undo of a move is one step
    p.run("SHEETVIEW, front, ISO, 5, 0")
    p.run("UNDO")
    assert not p.model.drawsheets["FRONT"]["moves"]


def test_size_of_a_straight_and_a_round_edge():
    p = _part()
    circ, line = _edges(p, GeomAbs_Circle), _edges(p, GeomAbs_Line)
    assert p.run(f"SHEETNOTE, front, SIZE, EDGE {circ[0]}").ok
    assert p.run(f"SHEETNOTE, front, SIZE, {line[0]}").ok  # a bare number is an edge
    assert not p.run("SHEETNOTE, front, SIZE, FACE 1").ok
    _o, page, placed, _n = render(p, p.model.drawsheets["FRONT"])
    texts = [d["text"] for d in placed]
    assert "Ø8" in texts
    assert any(t in ("10", "20", "40") for t in texts)
    assert all(d["kind"] == "size" for d in placed)
