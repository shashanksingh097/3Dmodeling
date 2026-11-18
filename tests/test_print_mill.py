"""PRINTCHECK (geometry/printing.py) and MILL (geometry/milling.py)."""

import math

import numpy as np

from modeler.commands import Processor
from modeler.geometry import milling as ml


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def test_slot_roof_overhangs_and_lying_on_its_side_needs_none():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 40,30,20", "NAME, LAST, box", "BLOCK, 10,-1,5, 20,32,10", "SUBTRACT, box, LAST")
    msg = run(p, "PRINTCHECK, box").message
    assert "bed: 1200 of flat face" in msg
    assert "overhangs: 600 " in msg and "lowest 15 above" in msg  # the slot's roof, 20 x 30
    best = run(p, "PRINTCHECK, box, BEST").message
    assert "built along +Y" in best or "built along -Y" in best
    assert "ready to print" in best
    assert p.analysis.mode == "PRINT"


def test_thin_walls_hollows_and_round_bottoms_are_reported():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 40,30,20", "NAME, LAST, box", "BLOCK, 10,-1,5, 20,32,10", "SUBTRACT, box, LAST")
    assert "walls: thinnest 5, under 6" in run(p, "PRINTCHECK, box, +Y, 45, 6").message
    run(p, "SPHERE, 100, 0, 0, 10", "NAME, LAST, ball", "SPHERE, 100, 0, 0, 6", "SUBTRACT, ball, LAST")
    msg = run(p, "PRINTCHECK, ball").message
    assert "touches the bed only at points" in msg
    hollow = float(msg.split("hollows: 1 closed inside (")[1].split(")")[0])
    assert math.isclose(hollow, 4 / 3 * math.pi * 6 ** 3, rel_tol=1e-3)


def test_printcheck_errors():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 10,10,10")
    for bad in ("PRINTCHECK, 1, sideways", "PRINTCHECK, 1, +Z, 95", "PRINTCHECK, 1, 0 0 0"):
        assert not p.run(bad).ok


def _pocket_plate(p):
    run(p, "BLOCK, 0,0,0, 80,60,16", "NAME, LAST, plate", "BLOCK, 12,12,6, 48,36,20", "SUBTRACT, plate, LAST",
        "CYL, 36, 30, 6, 7, 10", "UNION, plate, LAST", "SEL, S, FACE, LOC, Z, 6", "CM, floor, FACE", "SEL, NONE")


def test_pocket_rings_stay_a_tool_radius_off_the_walls_and_the_boss(tmp_path):
    p = Processor()
    _pocket_plate(p)
    out = tmp_path / "pk"
    msg = run(p, f"MILL, plate, POCKET, floor, 6, 4, 0, {out}").message
    assert "x 15 to 57, y 15 to 45" in msg  # the walls at 12/60 and 12/48, less the radius 3
    code = (tmp_path / "pk.nc").read_text()
    assert code.startswith("%") and "M30" in code
    moves = np.array([[float(w[1:]) for w in line.split()[1:4]] for line in code.splitlines()
                      if line.startswith("G1 X")])
    assert sorted(set(np.round(moves[:, 2], 3))) == [6.0, 9.333, 12.667]  # 10 deep, no more than 4 a cut: 3 equal cuts
    r = np.hypot(moves[:, 0] - 36, moves[:, 1] - 30)
    assert r.min() >= 7 + 3 - 0.02  # never into the boss
    assert p.toolpath is not None


def test_pocket_levels_and_outline_and_facing():
    assert ml.levels(16, 6, 4) == [16 - 10 / 3, 16 - 20 / 3, 6]
    p = Processor()
    _pocket_plate(p)
    run(p, "SEL, S, FACE, LOC, Z, 0", "CM, bottom, FACE", "SEL, S, FACE, LOC, Z, 16", "CM, top, FACE", "SEL, NONE")
    msg = run(p, "MILL, plate, OUTLINE, bottom, 6, 8").message
    assert "2 passes" in msg and "x -3 to 83, y -3 to 63" in msg and "z 0 up" in msg
    msg = run(p, "MILL, plate, FACE, top, 20, 5, 8").message
    assert "x -10 to 90, y 0 to 60" in msg
    assert not p.run("MILL, plate, POCKET, floor, 40").ok  # the tool does not fit
    assert not p.run("MILL, plate, POCKET, bottom, 6").ok  # faces down
    assert not p.run("MILL, plate, POCKET, floor, 6, 2, 8").ok  # stepover wider than the tool
    assert run(p, "MILL, OFF").message == "milling path hidden" and p.toolpath is None
