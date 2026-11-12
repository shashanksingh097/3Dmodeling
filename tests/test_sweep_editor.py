"""Law tables (TABLE) and the sweep editor's model; the editor window itself
is tested in test_forms_gui.py."""

import math

import pytest

from modeler.commands import Processor
from modeler.geometry import robust
from modeler.gui.sweep_edit import SweepEdit, SweepEditError
from modeler.lang import table

BAR = """LINE, 0,0,0, 0,0,40
NAME, LAST, axis
RECT, 0,0,0, 10, 4
NAME, LAST, bar
SWEEP, bar, axis, 90*t, 1 - 0.5*t
"""


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


# ---- TABLE -------------------------------------------------------------------------

def test_table_goes_through_its_stations_and_holds_the_ends(p):
    f = "TABLE({}, 0, 40, 0.6, 20, 1, 8)"
    assert [p.evaluate(f.format(t)) for t in (0, 0.6, 1)] == [40, 20, 8]
    assert p.evaluate(f.format(-1)) == 40 and p.evaluate(f.format(2)) == 8
    # monotone stations: no overshoot anywhere between them
    vals = [p.evaluate(f.format(i / 100)) for i in range(101)]
    assert all(8 <= v <= 40 for v in vals)
    assert all(b <= a + 1e-12 for a, b in zip(vals, vals[1:]))


def test_table_is_smooth_and_straight_through_two_stations(p):
    assert p.evaluate("TABLE(0.25, 0, 0, 1, 8)") == pytest.approx(2)
    # a peak in the middle stays a peak (flat top, no overshoot)
    vals = [table.value([(0, 0), (0.5, 10), (1, 0)], i / 200) for i in range(201)]
    assert max(vals) == pytest.approx(10)


def test_table_errors(p):
    from modeler.lang.expr import ExprError

    for bad in ("TABLE(0.5, 0, 1, 1)", "TABLE(0.5, 1, 1, 0, 2)", "TABLE(0.5)"):
        with pytest.raises(ExprError):
            p.evaluate(bad)


def test_table_text_round_trip():
    st = [(0.0, 40.0), (0.35, 12.5), (1.0, -8.0)]
    assert table.text(st) == "TABLE(t, 0, 40, 0.35, 12.5, 1, -8)"
    assert table.parse(table.text(st)) == st
    assert table.parse('"TABLE(t, 0, 1, 1, 2)"') == [(0, 1), (1, 2)]
    assert table.parse("40 - 32*t") is None
    assert table.parse("TABLE(t, 0, W, 1, 2)") is None  # not plain numbers: stays a formula


def test_sweep_with_a_table_law(p):
    ok(p, BAR.replace("90*t, 1 - 0.5*t", "TABLE(t, 0, 0, 0.5, 90, 1, 90)"))
    assert p.evaluate("VOL(LAST)") == pytest.approx(10 * 4 * 40, rel=2e-3)  # twist keeps the area


# ---- the editor's model --------------------------------------------------------------

def test_sweep_edit_reads_the_entry_and_turns_formulas_into_stations(p):
    ok(p, BAR)
    e = SweepEdit(p, 4)
    assert e.formula == {"twist": "90*t", "scale": "1 - 0.5*t"}
    assert e.value("twist", 0.5) == pytest.approx(45)
    st = e.law_stations("twist")
    assert st == [(0, 0), (0.25, 22.5), (0.5, 45), (0.75, 67.5), (1, 90)]
    assert "twist" not in e.formula
    assert e.command() == "SWEEP, bar, axis, TABLE(t, 0, 0, 0.25, 22.5, 0.5, 45, 0.75, 67.5, 1, 90), 1 - 0.5*t"


def test_sweep_edit_handles_move_add_and_remove(p):
    ok(p, BAR)
    e = SweepEdit(p, 4)
    e.law_stations("twist")
    e.set_station("twist", 2, t=0.9, v=10)  # t is kept between its neighbours
    assert e.stations["twist"][2] == (0.74, 10)
    e.set_station("twist", 0, t=0.5, v=5)  # the ends stay at t = 0 and 1
    assert e.stations["twist"][0] == (0, 5)
    i = e.add_station("twist", 0.6)
    assert e.stations["twist"][i][0] == 0.6
    e.remove_station("twist", i)
    with pytest.raises(SweepEditError):
        e.remove_station("twist", 0)
    e.set_station("scale", 0, v=-3)  # the scale stays above 0
    assert e.stations["scale"][0][1] > 0


def test_sweep_edit_section_and_preview_match_the_command(p):
    ok(p, BAR)
    e = SweepEdit(p, 4)
    sec = e.section(1.0)
    # the end section: half size, turned 90 degrees, at the top of the path
    assert robust.volume(sec) == 0
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    bb = Bnd_Box()
    BRepBndLib.Add_s(sec, bb)
    (x0, y0, z0), (x1, y1, z1) = bb.CornerMin().Coord(), bb.CornerMax().Coord()
    assert (x1 - x0, y1 - y0) == (pytest.approx(2, abs=1e-6), pytest.approx(5, abs=1e-6))
    assert z0 == pytest.approx(40, abs=1e-6)
    v_preview = robust.volume(e.preview())
    e.law_stations("twist")
    e.set_station("twist", 4, v=0)
    p.run(f'HIST, EDIT, 5, "{e.command()}"')
    assert p.history[4].text.startswith("SWEEP, bar, axis, TABLE(t,")
    e2 = SweepEdit(p, 4)
    assert e2.stations["twist"][-1] == (1, 0)
    assert robust.volume(e2.preview()) == pytest.approx(p.evaluate("VOL(LAST)"), rel=1e-6)
    assert v_preview == pytest.approx(10 * 4 * 40 * (1 + 0.5 + 0.25) / 3, rel=5e-3)  # scale^2 averaged


def test_sweep_edit_uses_the_curves_as_they_were_before_the_step(p):
    ok(p, BAR + "MOVE, bar, 100,0,0")  # moving the profile later does not matter
    e = SweepEdit(p, 4)
    assert robust.volume(e.preview()) > 0
    with pytest.raises(SweepEditError):
        SweepEdit(p, 0)  # not a SWEEP


def test_sweep_edit_keeps_comments(p):
    ok(p, BAR.replace("SWEEP, bar, axis, 90*t, 1 - 0.5*t", "! the twisted bar\nSWEEP, bar, axis, 90*t  ! quarter turn"))
    e = SweepEdit(p, 4)
    e.law_stations("twist")
    text = e.entry_text()
    assert text.startswith("! the twisted bar\nSWEEP, bar, axis, TABLE(") and text.endswith("! quarter turn")
    assert math.isfinite(e.value("scale", 0.3))
