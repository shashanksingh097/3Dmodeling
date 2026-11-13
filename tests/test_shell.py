"""M2 usable shell: KEEP, ARRAY, IMPORT, projects (SAVE/OPEN/NEW), command-line assist."""

import math
import os

import pytest

from modeler.commands import Processor
from modeler.gui import assist


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, line):
    r = p.run(line)
    assert not r.ok
    return r.message


# ---- KEEP -------------------------------------------------------------------------
def test_keep_off_uses_up_inputs(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSPHERE, 10,10,10, 4\nSUBTRACT, 1, 2")
    assert sorted(p.model.bodies) == [3]


def test_keep_on_keeps_inputs_hidden_and_reusable(p):
    r = ok(p, "KEEP, ON\nBLOCK, 0,0,0, 10,10,10\nNAME, LAST, base\nSPHERE, 10,10,10, 4\nSUBTRACT, base, LAST")
    assert "kept the inputs" in r.message
    m = p.model
    result = m.body_by_name("base")
    kept = sorted(set(m.bodies) - {result.id})
    assert len(kept) == 2 and set(kept) <= m.hidden
    assert p.evaluate("LAST") == result.id
    assert p.evaluate(f"VOL({kept[0]})") == pytest.approx(1000)
    # face IDs stay with the result: the block's top face (6) is still on 'base'
    assert m.entity_owner("FACE", 6)[0] == result.id
    ok(p, f"COPY, {kept[1]}, 30, 0, 0")  # the kept sphere can be used again
    ok(p, "UNDO, 2\nKEEP, OFF")
    assert not p.model.keep


# ---- ARRAY ------------------------------------------------------------------------
def test_linear_and_grid(p):
    ok(p, "CYL, 0,0,0, 1, 5\nARRAY, LINEAR, 1, 4, 10,0,0")
    assert len(p.model.bodies) == 4
    assert p.evaluate("CENT(4).x") == pytest.approx(30)
    ok(p, "CLEAR\nSPHERE, 0,0,0, 1\nARRAY, LINEAR, 1, 3, (5,0,0), 2, (0,5,0)")
    assert len(p.model.bodies) == 6
    assert p.evaluate("BBOX(6).ymax") == pytest.approx(6)


def test_polar_full_circle_and_partial(p):
    ok(p, "BLOCK, 20,-1,0, 4,2,2\nARRAY, POLAR, 1, 6")
    assert len(p.model.bodies) == 6
    c = p.evaluate("CENT(3)")
    assert math.degrees(math.atan2(c[1], c[0])) == pytest.approx(120, abs=1e-6)
    ok(p, "CLEAR\nSPHERE, 10,0,0, 1\nARRAY, POLAR, 1, 3, 90, 0,0,0, 0,0,1")
    assert p.evaluate("CENT(3)")[1] == pytest.approx(10)  # the last one at 90 degrees


def test_array_fuse(p):
    ok(p, "BLOCK, 0,0,0, 10,2,2\nNAME, LAST, bar\nARRAY, LINEAR, bar, 3, 0,1.5,0, FUSE")
    assert len(p.model.bodies) == 1
    assert p.evaluate("BBOX(bar).ymax") == pytest.approx(5)


def test_array_along_path_follows_the_curve(p):
    ok(p, "CIRCLE, 0,0,0, 30\nNAME, LAST, ring\nBLOCK, 28,-1,-1, 4,2,2\nARRAY, PATH, LAST, ring, 8")
    blocks = [b for b in p.model.bodies if b != p.model.body_by_name("ring").id]
    assert len(blocks) == 8
    for b in blocks:  # every copy stays on the ring, turned with it
        c = p.evaluate(f"CENT({b})")
        assert math.hypot(c[0], c[1]) == pytest.approx(30, abs=1e-6)
        assert p.evaluate(f"VOL({b})") == pytest.approx(16)


def test_array_path_with_scale_law(p):
    ok(p, "LINE, 0,0,0, 0,0,40\nSPHERE, 0,0,0, 4\nARRAY, PATH, LAST, 1, 5, 0, 1 - 0.5*t")
    assert p.evaluate("VOL(LAST)") == pytest.approx(4 / 3 * math.pi * 8, rel=1e-6)
    assert p.evaluate("CENT(LAST).z") == pytest.approx(40)


def test_array_errors(p):
    ok(p, "SPHERE, 0,0,0, 1")
    assert "LINEAR, POLAR or PATH" in err(p, "ARRAY, SIDEWAYS, 1, 3")
    assert "step" in err(p, "ARRAY, LINEAR, 1, 3")
    assert "whole number" in err(p, "ARRAY, LINEAR, 1, 2.5, 1,0,0")
    assert "path" in err(p, "ARRAY, PATH, 1")


# ---- IMPORT and projects ------------------------------------------------------------
@pytest.mark.parametrize("fmt", ["STEP", "BREP", "STL"])
def test_export_then_import(p, tmp_path, fmt):
    f = tmp_path / f"part.{fmt.lower()}"
    ok(p, f'BLOCK, 0,0,0, 10,20,30\nEXPORT, {fmt}, "{f}"\nCLEAR\nIMPORT, {fmt}, "{f}", part')
    assert p.evaluate("VOL(part)") == pytest.approx(6000, rel=1e-6)


def test_import_errors(p, tmp_path):
    assert "no such file" in err(p, f'IMPORT, STEP, "{tmp_path}/none.step"')
    assert "format" in err(p, 'IMPORT, DXF, "x.dxf"')


def test_project_round_trip_carries_imported_files(p, tmp_path):
    part = tmp_path / "cube.brep"
    proj = tmp_path / "work" / "job.m3d"
    ok(p, f'BLOCK, 0,0,0, 5,5,5\nEXPORT, BREP, "{part}"\nCLEAR')
    q = Processor()
    ok(q, f'D = 2\nIMPORT, BREP, "{part}", cube\nCYL, 2.5,2.5,-1, D/2, 7\nSUBTRACT, cube, LAST\nSAVE, "{proj}"')
    v = q.evaluate("VOL(cube)")
    os.remove(part)  # the project holds its own copy
    r = Processor()
    res = r.run(f'OPEN, "{proj}"')
    assert res.ok, res.message
    assert r.evaluate("VOL(cube)") == pytest.approx(v)
    assert len(r.history) == len(q.history)
    ok(r, 'HIST, EDIT, 1, "D = 1"')  # the replayed history is editable
    assert r.evaluate("VOL(cube)") > v
    assert r.run("SAVE").ok  # saves back to the opened file, still with the import
    s = Processor()
    assert s.run(f'OPEN, "{proj}"').ok
    assert s.evaluate("VOL(cube)") == pytest.approx(r.evaluate("VOL(cube)"))


def test_open_bad_file_and_new(p, tmp_path):
    bad = tmp_path / "x.m3d"
    bad.write_text("not a zip")
    assert "not a project" in err(p, f'OPEN, "{bad}"')
    assert "no autosave" in err(p, "OPEN, AUTOSAVE")
    ok(p, "W = 3\nBLOCK, 0,0,0, W,W,W")
    ok(p, "NEW")
    assert not p.model.bodies and not p.history and not p.params


def test_save_adds_extension_and_open_is_not_history(p, tmp_path):
    ok(p, "SPHERE, 0,0,0, 2")
    assert p.run(f'SAVE, "{tmp_path}/ball"').ok
    assert (tmp_path / "ball.m3d").exists()
    assert len(p.history) == 1


# ---- command-line assist ---------------------------------------------------------------
def test_completion_words_fit_the_position(p):
    ok(p, "W = 4\nCYL, 0,0,0, 1, 2\nNAME, LAST, shaft\n*MACRO, bolt, d\n  CYL, 0,0,0, d, 10\n*END")
    assert assist.completions(p, "SWE") == ["SWEEP", "SWEEPVOL"]
    assert "BOLT" in assist.completions(p, "BO")
    assert assist.completions(p, "ARRAY, P") == ["POLAR", "PATH"]
    assert assist.completions(p, "SWEEP, sh") == ["shaft"]
    assert "MINTWIST" in assist.completions(p, "SWEEP, a, b, 0, 1, M")
    assert assist.completions(p, "CYL, 0,0,0, ") == []  # nothing typed yet
    assert assist.completions(p, "BLOCK, 1 ! sp") == []  # inside a comment
    assert assist.completions(p, "CYL, max(1, W") == []  # W is complete already


def test_signature_marks_the_current_argument(p):
    sig = assist.signature(p, "CYL, 0, 0, 0, ")
    assert "<b><u>r</u></b>" in sig
    assert "<b><u>[mode]</u></b>" in assist.signature(p, "SWEEP, a, b, 0, 1, ")
    assert "MINTWIST" in assist.signature(p, "SWEEP, a, b, 0, 1, ")
    ok(p, "*MACRO, bolt, d, l=10\n  CYL, 0,0,0, d, l\n*END")
    assert "<b>[l=10]</b>" in assist.signature(p, "bolt, 3, ")
    assert assist.signature(p, "NOSUCH, 1") == ""
    # commas inside parentheses do not start a new argument
    assert "<b><u>[n]</u></b>" in assist.signature(p, 'CURVE, PARAM, cos(t), sin(t), max(t, 1), 0, 1, ')


def test_keep_tool_keeps_its_name(p):
    ok(p, "KEEP, ON\nBLOCK, 0,0,0, 10,10,10\nNAME, LAST, base\nSPHERE, 10,10,10, 4\nNAME, LAST, ball\nSUBTRACT, base, ball")
    assert p.model.body_by_name("ball").id in p.model.hidden
    ok(p, "SHOW, ball\nMOVE, ball, 0,0,20")


def test_demo_script(p):
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "scripts" / "m2_shell_demo.cmd").read_text()
    rs = p.run_script(text)
    assert all(r.ok for r in rs), [r.message for r in rs if not r.ok]
