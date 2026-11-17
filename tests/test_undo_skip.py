"""Undo for history edits, HIST, ROLLBACK, and skipping unchanged entries on a rebuild."""

import pytest

from modeler.commands import Processor

PARTS = """\
W = 40
D = 6
BLOCK, 0,0,0, W, 20, 5
NAME, LAST, plate
CYL, 100, 0, 0, D/2, 20
NAME, LAST, pin
SPHERE, -50, 0, 0, 8
MOVE, 3, 0, 0, 5
V = VOL(pin)
"""


@pytest.fixture
def p():
    q = Processor()
    assert all(r.ok for r in q.run_script(PARTS))
    return q


def ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r.message


def state(p):
    m = p.model
    return ([(b, m.bodies[b].name, round(p.evaluate(f"VOL({b})"), 6)) for b in sorted(m.bodies)],
            {k: v for k, v in p.params.items()}, [e.text for e in p.history], p.cursor)


# ---- undo of history edits ------------------------------------------------

@pytest.mark.parametrize("edit", [
    'HIST, EDIT, 1, "W = 70"',
    'HIST, INSERT, 3, "BOX = 1"',
    "HIST, DELETE, 7",
    "HIST, SUPPRESS, 9",
    "HIST, MOVE, 7, 3",
    'HIST, PART, 3, "4, slab"',
])
def test_undo_takes_back_a_history_edit_and_redo_puts_it_back(p, edit):
    before = state(p)
    ok(p, edit)
    after = state(p)
    assert after != before
    assert "entry" in ok(p, "UNDO")
    assert state(p) == before
    ok(p, "REDO")
    assert state(p) == after
    ok(p, "UNDO")
    ok(p, "UNDO")  # then the last step, as before
    assert p.cursor == len(p.history) - 1


def test_undo_steps_through_edits_and_new_entries_in_order(p):
    s0 = state(p)
    ok(p, 'HIST, EDIT, 1, "W = 50"')
    s1 = state(p)
    ok(p, "SPHERE, 0, 0, 50, 2")
    s2 = state(p)
    ok(p, 'HIST, EDIT, 2, "D = 8"')
    msg = ok(p, "UNDO, 3")
    assert "1 step" in msg and "edit of entry 2" in msg and "edit of entry 1" in msg
    assert state(p)[0] == s0[0] and p.params["W"] == 40 and p.params["D"] == 6
    ok(p, "REDO")
    assert state(p) == s1
    ok(p, "REDO")
    assert state(p)[0] == s2[0]
    ok(p, "REDO")
    assert p.params["D"] == 8 and p.evaluate("V") == pytest.approx(3.14159265 * 16 * 20)
    assert "nothing to redo" in p.run("REDO").message


def test_a_new_step_after_undo_drops_the_redo_list(p):
    ok(p, 'HIST, EDIT, 1, "W = 50"')
    ok(p, "UNDO")
    ok(p, "SPHERE, 0, 0, 50, 2")
    assert not p.run("REDO").ok
    assert p.params["W"] == 40


def test_a_refused_edit_changes_nothing_and_is_not_an_undo_step(p):
    before = state(p)
    assert not p.run('HIST, EDIT, 99, "W = 1"').ok
    assert not p.run('HIST, EDIT, 1, "*DO, i, 1, 2"').ok
    assert state(p) == before
    ok(p, "UNDO")  # undoes the last real step (V = VOL(pin))
    assert "V" not in p.params


def test_rollback_is_one_step_and_keeps_later_entries(p):
    n = len(p.history)
    msg = ok(p, "HIST, ROLLBACK, 3")
    assert "after entry 3" in msg and p.cursor == 3 and len(p.history) == n
    assert sorted(p.model.bodies) == [1]
    ok(p, "HIST, ROLLBACK, 5")  # forward again, part of the way
    assert sorted(p.model.bodies) == [1, 2]
    ok(p, "UNDO")
    assert p.cursor == 3
    ok(p, "UNDO")
    assert p.cursor == n
    ok(p, "REDO")
    assert p.cursor == 3
    assert not p.run(f"HIST, ROLLBACK, {n + 1}").ok


def test_cancelled_rebuild_is_not_an_undo_step(p):
    before = state(p)
    p.progress = lambda done, total, label: done < 1
    assert "cancelled" in p.run('HIST, EDIT, 1, "W = 70"').message
    p.progress = None
    assert state(p) == before
    ok(p, "UNDO")
    assert "V" not in p.params


# ---- skipping unchanged entries -------------------------------------------

def test_an_edit_reruns_only_what_depends_on_it(p):
    msg = ok(p, 'HIST, EDIT, 1, "W = 60"')
    # W, then the BLOCK that uses it; the NAME looks at body 1, which is new
    assert msg.startswith("re-ran 3 entries from 1") and p.skipped == 6
    assert p.evaluate("VOL(plate)") == pytest.approx(60 * 20 * 5)
    msg = ok(p, 'HIST, EDIT, 2, "D = 10"')
    # D, the CYL and its NAME, and V = VOL(pin) run; the plate and sphere steps are reused
    assert p.skipped == 4 and p.evaluate("V") == pytest.approx(3.14159265358979 * 25 * 20)


def test_skipping_gives_the_same_model_as_running_everything(p):
    for edit in ('HIST, EDIT, 1, "W = 55"', 'HIST, EDIT, 2, "D = 9"', "HIST, SUPPRESS, 5",
                 "HIST, RESUME, 5", 'HIST, INSERT, 5, "SPHERE, 0, 0, 60, 3"', "HIST, MOVE, 7, 3",
                 "HIST, DELETE, 4"):
        ok(p, edit)
        skipped = state(p)
        ok(p, "HIST, REPLAY")  # always runs every entry
        assert p.skipped == 0
        assert state(p) == skipped, edit


def test_entries_that_read_a_changed_name_or_everything_run_again(p):
    ok(p, "SEL, ALL, BODY")  # looks at every body
    ok(p, 'HIST, EDIT, 1, "W = 60"')
    assert p.skipped < len(p.history) - 3
    q = Processor()
    assert all(r.ok for r in q.run_script("BLOCK, 0,0,0, 1,1,1\nNAME, LAST, a\nSPHERE, 5,0,0, 1\nX = VOL(a)"))
    q.run('HIST, EDIT, 2, "NAME, LAST, b"')
    assert not q.history[3].ok  # VOL(a) has nothing to find now: it ran again


def test_failed_and_file_reading_entries_always_run(p, tmp_path):
    f = tmp_path / "lib.cmd"
    f.write_text("*PART, peg, R=2\n  CYL, 0, 0, 0, R, 5\n*ENDPART\n")
    ok(p, f'LIB, LOAD, "{f}"')
    ok(p, "INST, peg")
    n = len(p.history)
    assert p.history[n - 2].reads is None  # LIB reads a file
    f.write_text("*PART, peg, R=3\n  CYL, 0, 0, 0, R, 5\n*ENDPART\n")
    ok(p, 'HIST, EDIT, 1, "W = 51"')
    assert p.evaluate("VOL(LAST)") == pytest.approx(3.14159265358979 * 9 * 5)


def test_skipping_can_be_turned_off(p):
    p.skip_unchanged = False
    ok(p, 'HIST, EDIT, 1, "W = 60"')
    assert p.skipped == 0
