"""Editing a sketch that features already use, in place (SKETCH, name on a used sketch)."""

import os

from modeler.commands import Processor

PLATE = """
SKETCH, s1, XY
SRECT, 0, 0, 60, 40
ENDSKETCH
EXTRUDE, s1, 10
MOVE, LAST, 0, 0, 5
"""


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs


def vol(p):
    return p.evaluate("VOL(LAST)")


def test_reopen_used_sketch_adds_lines_in_place_and_rebuilds():
    p = Processor()
    ok(p, PLATE)
    v0 = vol(p)
    n0 = p.cursor
    r = p.run("SKETCH, s1")
    assert r.ok, r.message
    assert "later step" in r.message
    assert p.sketch_edit is not None and p.cursor == 4  # the EXTRUDE and the FILLET wait
    assert p.model.active_sketch == "S1"
    assert p.run("SCIRCLE, (30, 20), 5").ok
    r = p.run("ENDSKETCH")
    assert r.ok, r.message
    assert "ran again" in r.message
    assert p.sketch_edit is None
    texts = [e.text for e in p.history[:p.cursor]]
    assert texts[3:6] == ["SKETCH, s1", "SCIRCLE, (30, 20), 5", "ENDSKETCH"]
    assert texts[6].startswith("EXTRUDE") and texts[7].startswith("MOVE")
    assert p.cursor == n0 + 3
    assert all(e.ok for e in p.history[:p.cursor]), [e.message for e in p.history]
    assert vol(p) < v0 - 700  # the hole went through the plate


def test_one_undo_takes_back_the_whole_edit():
    p = Processor()
    ok(p, PLATE)
    v0 = vol(p)
    before = [e.text for e in p.history]
    for line in ("SKETCH, s1", "SCIRCLE, (30, 20), 5", "ENDSKETCH"):
        assert p.run(line).ok
    assert p.run("UNDO").ok
    assert [e.text for e in p.history[:p.cursor]] == before
    assert abs(vol(p) - v0) < 1e-6
    assert p.run("REDO").ok
    assert p.cursor == len(before) + 3


def test_undoing_the_reopen_cancels_the_edit():
    p = Processor()
    ok(p, PLATE)
    before = [e.text for e in p.history]
    assert p.run("SKETCH, s1").ok
    r = p.run("UNDO")
    assert r.ok
    assert "cancelled" in r.message
    assert p.sketch_edit is None
    assert [e.text for e in p.history[:p.cursor]] == before


def test_save_during_an_edit_writes_the_history_before_it(tmp_path):
    p = Processor()
    ok(p, PLATE)
    assert p.run("SKETCH, s1").ok
    assert p.run("SCIRCLE, (30, 20), 5").ok
    path = str(tmp_path / "a.m3d")
    r = p.run(f"SAVE, {path}")
    assert r.ok and "still being edited" in r.message
    assert "SCIRCLE" not in p.script()
    q = Processor()
    assert q.run(f"OPEN, {path}").ok
    assert [e.text for e in q.history] == [e.text for e in p.sketch_edit.before["history"]]
    assert os.path.isfile(path)


def test_new_sketch_and_unused_reopen_are_unchanged():
    p = Processor()
    ok(p, "SKETCH, s1, XY\nSRECT, 0, 0, 10, 10\nENDSKETCH")
    r = p.run("SKETCH, s1")
    assert r.ok and p.sketch_edit is None
    assert p.run("ENDSKETCH").ok
