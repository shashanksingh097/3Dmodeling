"""EDITCHECK and the direct change: what a change of a step breaks, and the same change made on the
finished model instead (commands/edit_impact.py, gui/edit_guard.py)."""

from modeler.commands import Processor
from modeler.commands import edit_impact as ei
from modeler.gui import edit_guard as eg

PLATE = ["SKETCH, s1, XY", "SRECT, 0, 0, 80, 40", "ENDSKETCH", "EXTRUDE, s1, 10", "HOLE, LAST, 30, 20, 10, 8"]


def make(lines):
    p = Processor()
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return p


def vol(p):
    return p.evaluate("VOL(LAST)")


def test_direct_change_for_a_hole_size_matches_the_history_edit():
    p = make(PLATE + ["MOVE, LAST, 5, 0, 0"])
    d = ei.direct(p, 5, "HOLE, LAST, 30, 20, 10, 12")
    assert d is not None and "PUSHPULL, -2" in d
    q = make(PLATE + ["MOVE, LAST, 5, 0, 0"])
    q.run_script(d)
    r = make(PLATE + ["MOVE, LAST, 5, 0, 0"])
    assert r.run('HIST, EDIT, 5, "HOLE, LAST, 30, 20, 10, 12"').ok
    assert abs(vol(q) - vol(r)) < 1e-3 * vol(r)


def test_direct_change_for_an_extrude_moves_the_far_face():
    p = make(PLATE)
    d = ei.direct(p, 4, "EXTRUDE, s1, 20")
    assert d is not None and d.endswith("PUSHPULL, 10")


def test_a_joined_body_is_not_moved_as_a_direct_change():
    p = make(["BLOCK, 0, 0, 0, 40, 40, 10", "NAME, LAST, plate", "CYL, 20, 20, -5, 5, 20", "NAME, LAST, pin",
              "MOVE, pin, 5, 0, 0", "SUBTRACT, plate, pin"])
    assert ei.direct(p, 5, "MOVE, pin, 100, 0, 0") is None


def test_a_loose_body_move_is_found():
    p = make(["BLOCK, 0, 0, 0, 10, 10, 10", "MOVE, LAST, 5, 0, 0", "COLOR, LAST, RED"])
    assert ei.direct(p, 2, "MOVE, LAST, 5, 7, 0") == "MOVE, 1, 0, 7, 0"


def test_editcheck_names_the_steps_that_would_break_and_changes_nothing():
    p = make(PLATE + ["PICK, EDGE, 14", "FILLET, 3"])
    before = [e.text for e in p.history]
    r = p.run('EDITCHECK, 4, "EXTRUDE, s1, 2"')
    assert r.ok, r.message
    assert "would fail" in r.message and "7: FILLET, 3" in r.message
    assert r.report["breaks"][0]["n"] == 7
    assert [e.text for e in p.history] == before
    assert all(e.ok for e in p.history)


def test_editcheck_when_all_follows():
    p = make(PLATE)
    r = p.run('EDITCHECK, 4, "EXTRUDE, s1, 20"')
    assert "every later step follows" in r.message
    assert r.report["breaks"] == []


def test_edit_line_reads_hist_edit():
    assert ei.edit_line('HIST, EDIT, 4, "EXTRUDE, s1, 20"') == (4, "EXTRUDE, s1, 20")
    assert ei.edit_line("HIST, DELETE, 4") is None
    assert ei.edit_line("BLOCK, 0,0,0, 1,1,1") is None


class _Win:
    def __init__(self, p):
        self.processor = p


def test_guard_asks_and_cancel_keeps_everything(monkeypatch):
    p = make(PLATE + ["PICK, EDGE, 14", "FILLET, 3"])
    asked = []
    monkeypatch.setattr(eg, "choose", lambda win, q: asked.append(q) or eg.CANCEL)
    res = eg.check(_Win(p), 'HIST, EDIT, 4, "EXTRUDE, s1, 2"')
    assert asked and asked[0].breaks[0]["n"] == 7 and asked[0].direct is None
    assert res is not None and not res.ok
    assert p.history[3].text == "EXTRUDE, s1, 10"


def test_guard_lets_a_safe_edit_through():
    p = make(PLATE)
    assert eg.check(_Win(p), 'HIST, EDIT, 4, "EXTRUDE, s1, 20"') is None


def test_guard_direct_choice_adds_steps_and_one_undo_takes_them_back(monkeypatch):
    p = make(PLATE)
    n0 = p.cursor
    q = eg.Question(5, "HOLE", [{"n": 9, "label": "x", "message": "y"}], "PICK, FACE, 7\nPUSHPULL, -2")
    monkeypatch.setattr(eg, "question_for", lambda p_, n, t: q)
    monkeypatch.setattr(eg, "choose", lambda win, q_: eg.DIRECT)
    v0 = vol(p)
    res = eg.check(_Win(p), 'HIST, EDIT, 5, "HOLE, LAST, 30, 20, 10, 12"')
    assert res.ok, res.message
    assert p.cursor == n0 + 2 and p.history[4].text == PLATE[4]
    assert vol(p) < v0
    p.run("UNDO")
    assert p.cursor == n0
    assert "would break 1 later step" in eg.text_of(q)
