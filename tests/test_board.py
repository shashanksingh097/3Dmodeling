"""PLAN item 103: circuit boards from IDF and KiCad files (geometry/board.py, BOARD)."""

import math
import os
import shutil

import pytest

from modeler.commands.processor import Processor
from modeler.geometry import board as bd

FILES = os.path.join(os.path.dirname(__file__), "..", "docs", "site", "example-files")
KICAD = os.path.join(FILES, "controller.kicad_pcb")
IDF = os.path.join(FILES, "sensor.emn")


def run(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r


def test_arc_mid_and_chain():
    m = bd.arc_mid((1, 0), (0, 1), 90)
    assert m == pytest.approx((math.sqrt(0.5), math.sqrt(0.5)))
    m = bd.arc_mid((1, 0), (0, 1), -270)  # the long way round
    assert m == pytest.approx((-math.sqrt(0.5), -math.sqrt(0.5)))
    sq = [bd.Seg("LINE", (0, 0), (10, 0)), bd.Seg("LINE", (10, 10), (10, 0)),  # one is backwards
          bd.Seg("LINE", (10, 10), (0, 10)), bd.Seg("LINE", (0, 10), (0, 0)), bd.Seg("CIRCLE", (5, 5), r=1)]
    loops = bd.chain(sq)
    assert len(loops) == 2 and bd.loop_area(loops[0]) == pytest.approx(100)
    with pytest.raises(bd.BoardError, match="not closed"):
        bd.chain(sq[:3])


def test_kicad_board():
    p = Processor()
    r = run(p, f"BOARD, {KICAD}, pcb")
    assert "80 x 50" in r.message
    rep = p.reports["BOARD"]
    assert rep["format"] == "KICAD" and rep["thickness"] == 1.6 and rep["size"] == [80, 50]
    assert len(rep["mounting_holes"]) == 4 and rep["holes_cut"] == 4
    assert {h["x"] for h in rep["mounting_holes"]} == {4.0, 76.0}
    parts = {pt["ref"]: pt for pt in rep["parts"]}
    assert set(parts) >= {"J1", "U1", "SW1", "C1", "R1", "J2", "BT1"}
    assert parts["J2"]["height"] == 8.5 and parts["J2"]["height_from"] == "file"
    assert parts["U1"]["height_from"] == "guess"
    assert parts["BT1"]["side"] == "BOTTOM" and parts["BT1"]["box"][1][2] == pytest.approx(0)
    assert parts["U1"]["box"][0][2] == pytest.approx(1.6)  # stands on the top face
    # the box of a part turned 90 degrees is turned too
    j1 = parts["J1"]["box"]
    assert j1[1][0] - j1[0][0] == pytest.approx(7.4) and j1[1][1] - j1[0][1] == pytest.approx(9.0)
    m = p.model
    assert m.body_by_name("pcb") is not None and m.body_by_name("U1").layer.upper() == "PCB_PARTS"
    assert run(p, "ASSERT, VALID(pcb), EQ, 1")
    # four holes through the plate: the volume is the plate's less four 3.2 holes
    run(p, "MASSPROP, pcb")
    hole = math.pi * 1.6 ** 2 * 1.6
    assert p.reports["MASSPROP"]["volume"] < 80 * 50 * 1.6 - 4 * hole + 1


def test_idf_board_with_library_and_cutout():
    p = Processor()
    run(p, f"BOARD, {IDF}, sensor, ALL")
    rep = p.reports["BOARD"]
    assert rep["format"] == "IDF" and rep["cutouts"] == 1 and rep["holes_cut"] == 5
    parts = {pt["ref"]: pt for pt in rep["parts"]}
    assert parts["J1"]["height"] == 13.5 and parts["C2"]["side"] == "BOTTOM"
    assert rep["tallest_top"] == 13.5 and rep["tallest_bottom"] == 10.5
    # the RJ45 stands over the board's edge: the envelope says so
    assert rep["envelope"]["min"][0] < 0
    # a round part from a 360-degree loop
    c1 = parts["C1"]["box"]
    assert c1[1][0] - c1[0][0] == pytest.approx(8, abs=1e-3)


def test_options_and_errors(tmp_path):
    p = Processor()
    run(p, f"BOARD, {KICAD}, b1, NONE, 2, , FILE")
    rep = p.reports["BOARD"]
    assert rep["holes_cut"] == 0 and rep["min"] == [100, -150]
    assert all(pt["height_from"] in ("file", "given") for pt in rep["parts"])
    run(p, f"BOARD, {KICAD}, b2, MOUNT, 0, , CENTRE")
    assert p.reports["BOARD"]["min"] == [-40, -25]
    assert not p.run(f"BOARD, {KICAD}, b2").ok  # the name is taken
    assert not p.run(f"BOARD, {KICAD}, b3, SOME").ok
    bad = tmp_path / "open.kicad_pcb"
    bad.write_text('(kicad_pcb (general (thickness 1.6)) (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts")))')
    r = p.run(f"BOARD, {bad}")
    assert not r.ok and "not closed" in r.message
    assert not p.run(f"BOARD, {tmp_path / 'none.emn'}").ok
    # IDF without its library: squares of a guessed height, and a note
    shutil.copy(IDF, tmp_path / "alone.emn")
    run(p, f"BOARD, {tmp_path / 'alone.emn'}, alone")
    assert any("library" in n for n in p.reports["BOARD"]["notes"])


def test_inches_and_units(tmp_path):
    emn = tmp_path / "thou.emn"
    emn.write_text(".HEADER\nBOARD_FILE 3.0 x 1\nb THOU\n.END_HEADER\n.BOARD_OUTLINE\n62\n"
                   "0 0 0 0\n0 1000 0 0\n0 1000 1000 0\n0 0 1000 0\n0 0 0 0\n.END_BOARD_OUTLINE\n")
    p = Processor()
    run(p, f"BOARD, {emn}")
    assert p.reports["BOARD"]["size"] == [25.4, 25.4]
    assert p.reports["BOARD"]["thickness"] == pytest.approx(1.5748)


def test_project_keeps_board_files(tmp_path):
    for n in ("sensor.emn", "sensor.emp"):
        shutil.copy(os.path.join(FILES, n), tmp_path / n)
    p = Processor()
    run(p, f"BOARD, {tmp_path / 'sensor.emn'}, s")
    f = str(tmp_path / "box.m3d")
    run(p, f"SAVE, {f}")
    os.remove(tmp_path / "sensor.emn")
    os.remove(tmp_path / "sensor.emp")
    q = Processor()
    run(q, f"OPEN, {f}")
    assert q.model.body_by_name("J1") is not None
    assert q.reports["BOARD"]["parts"][1]["height"] == 13.5  # the library came along


def test_import_menu_and_form():
    try:
        from modeler.gui import app_shell, forms
    except ImportError:
        pytest.skip("no Qt here")
    assert ".kicad_pcb" in app_shell.BOARD_EXTS and "kicad_pcb" in app_shell.IMPORT_FILTER
    from modeler.commands.processor import REGISTRY

    arg = next(a for a in REGISTRY["BOARD"].args if a.name == "holes")
    assert forms._choices("BOARD", arg) == ("MOUNT", "ALL", "NONE")
