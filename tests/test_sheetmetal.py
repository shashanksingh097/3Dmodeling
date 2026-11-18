"""Sheet metal: SHEET, FLANGE, UNFOLD (geometry/sheetmetal.py, commands/sheet_handlers.py)."""

from __future__ import annotations

import math

import pytest

from modeler.commands import Processor
from modeler.geometry import robust

PLATE = ["SKETCH, s1, XY", "SRECT, 0, 0, 60, 40", "SCIRCLE, 30, 20, 6", "ENDSKETCH"]


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, f"{line}: {r.message}"
    return r


def plate(t=2, r=2, k=0.5):
    p = Processor()
    run(p, *PLATE, f"SHEET, s1, {t}, {r}, {k}")
    return p


def test_sheet_is_a_plate_with_the_sketch_holes():
    p = plate()
    v = robust.volume(p.model.body(1).shape)
    assert v == pytest.approx((60 * 40 - math.pi * 36) * 2, rel=1e-6)
    assert 1 in p.model.sheets
    assert "0 flanges" in p.run("SHEETINFO, 1").message


def test_flanges_keep_the_volume_when_unfolded_with_k_one_half():
    p = plate()
    run(p, "SEL, S, EDGE, AT, 30, 0, 2", "FLANGE, , 20",  # up
        "SEL, S, EDGE, AT, 60, 20, 0", "FLANGE, , 15, 45",  # down
        "SEL, S, EDGE, AT, 30, 40, 2", "FLANGE, , 10, 120, 1")
    part = p.model.body(1).shape
    assert robust.checked_ok(part, True)
    assert len(p.model.sheets[1].flanges) == 3
    msg = run(p, "UNFOLD, 1").message
    blank = p.model.body(2).shape
    # with K = 0.5 the neutral line is the middle of the sheet, so bending keeps the volume exactly
    assert robust.volume(blank) == pytest.approx(robust.volume(part), rel=1e-6)
    w = 60 + math.radians(45) * (2 + 1) + 15
    h = 40 + math.radians(90) * (2 + 1) + 20 + math.radians(120) * (1 + 1) + 10
    assert f"{w:.2f} × {h:.2f}" in msg


def test_flange_up_rises_and_down_drops():
    p = plate()
    run(p, "SEL, S, EDGE, AT, 30, 0, 2", "FLANGE, , 20")
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    def zr(shape):
        b = Bnd_Box()
        (getattr(BRepBndLib, "Add_s", None) or BRepBndLib.Add)(shape, b, True)
        lo, hi = b.CornerMin(), b.CornerMax()
        return lo.Z(), hi.Z(), lo.Y()

    z0, z1, y0 = zr(p.model.body(1).shape)
    assert z1 == pytest.approx(2 + 2 + 20, abs=1e-3)  # thickness + radius + wall
    assert y0 == pytest.approx(-(2 + 2), abs=1e-3)  # grows past the edge by r + t
    q = plate()
    run(q, "SEL, S, EDGE, AT, 30, 0, 0", "FLANGE, , 20")
    z0, z1, _ = zr(q.model.body(1).shape)
    assert z0 == pytest.approx(-(2 + 20), abs=1e-3)


def test_flat_length_uses_the_k_factor():
    p = plate(t=2, r=3, k=0.3)
    run(p, "SEL, S, EDGE, AT, 0, 20, 2", "FLANGE, , 10")
    msg = run(p, "UNFOLD, 1").message
    w = 60 + math.radians(90) * (3 + 0.3 * 2) + 10
    assert f"{w:.2f} × 40.00" in msg


def test_dxf_has_outline_bend_lines_and_notes(tmp_path):
    p = plate()
    run(p, "SEL, S, EDGE, AT, 30, 0, 2", "FLANGE, , 20", "SEL, S, EDGE, AT, 60, 20, 0", "FLANGE, , 15, 45")
    path = tmp_path / "blank.dxf"
    msg = run(p, f'UNFOLD, 1, "{path.as_posix()}", NO').message
    assert "written to" in msg and len(p.model.bodies) == 1
    text = path.read_text(encoding="ascii").splitlines()  # R12: plain ANSI, no UTF-8
    pairs = list(zip(text[0::2], text[1::2]))
    layers = [v for c, v in pairs if c.strip() == "8"]
    assert layers.count("BEND") == 2
    assert layers.count("OUTLINE") > 8  # the rectangle, its two strips and the circle as short lines
    notes = [v for c, v in pairs if c.strip() == "1" and "%%d" in v]
    assert sorted(notes) == ["DOWN 45%%d R2", "UP 90%%d R2"]  # %%d is the DXF degree sign
    assert pairs[-1] == ("0", "EOF")


def test_holes_after_flanging_keep_it_sheet_metal_and_show_flat():
    p = plate()
    run(p, "SEL, S, EDGE, AT, 30, 0, 2", "FLANGE, , 20")
    run(p, "CYL, 10, 10, -1, 3, 5", "SUBTRACT, 1, LAST")
    bid = max(p.model.sheets)
    assert len(p.model.sheets[bid].flanges) == 1
    run(p, f"UNFOLD, {bid}")
    flat = p.model.body(max(p.model.bodies)).shape
    v = (60 * (40 + math.radians(90) * 3 + 20) - math.pi * 36 - math.pi * 9) * 2
    assert robust.volume(flat) == pytest.approx(v, rel=1e-6)


def test_rebuild_and_undo_keep_the_record():
    p = plate()
    run(p, "SEL, S, EDGE, AT, 30, 0, 2", "FLANGE, , 20")
    run(p, "UNDO")
    assert p.model.sheets[1].flanges == ()
    run(p, "REDO")
    assert len(p.model.sheets[1].flanges) == 1
    n = len(p.history)
    run(p, f'HIST, EDIT, {n}, "FLANGE, , 30"')
    assert p.model.sheets[1].flanges[0].length == 30


@pytest.mark.parametrize("line, words", [
    ("FLANGE, 1, 10", "not straight"),  # the circle's edge
    ("FLANGE, , 10", "select edges"),
    ("UNFOLD, 2", "not sheet metal"),
])
def test_plain_errors(line, words):
    p = plate()
    run(p, "BLOCK, 100, 0, 0, 5, 5, 5")
    circle = None
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_CurveType
    from OCP.TopoDS import TopoDS

    for gid in p.model.entity_ids("EDGE"):
        c = BRepAdaptor_Curve((getattr(TopoDS, "Edge_s", None) or TopoDS.Edge)(p.model.entity_shape("EDGE", gid)))
        if c.GetType() == GeomAbs_CurveType.GeomAbs_Circle:
            circle = gid
            break
    line = line.replace("FLANGE, 1,", f"FLANGE, {circle},")
    r = p.run(line)
    assert not r.ok and words in r.message


def test_an_edge_on_the_side_is_refused():
    p = plate()
    run(p, "SEL, S, EDGE, AT, 0, 0, 1")
    r = p.run("FLANGE, , 10")
    assert not r.ok and "top or bottom" in r.message
