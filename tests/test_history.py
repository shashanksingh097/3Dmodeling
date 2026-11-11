"""History: atomic entries, undo/redo, editing old steps, stable IDs on replay."""

import math

import pytest

from modeler.commands import Processor

PLATE = """\
W = 40
BLOCK, 0,0,0, W, 20, 5
NAME, LAST, plate
CYL, 10, 10, -1, 3, 7
SUBTRACT, plate, LAST
PICK, FACE, 6
"""


@pytest.fixture
def p():
    q = Processor()
    assert all(r.ok for r in q.run_script(PLATE))
    return q


def vol(p):
    return p.evaluate("VOL(plate)")


def test_each_top_level_statement_is_one_entry(p):
    assert [e.label for e in p.history] == [
        "W = 40", "BLOCK, 0,0,0, W, 20, 5", "NAME, LAST, plate",
        "CYL, 10, 10, -1, 3, 7", "SUBTRACT, plate, LAST", "PICK, FACE, 6",
    ]
    assert p.script() == PLATE


def test_failed_entries_change_nothing_and_are_not_kept(p):
    before = (dict(p.model.bodies), len(p.history))
    r = p.run("*DO, i, 1, 2\n  SPHERE, 100*i, 0, 0, 1\n  SPHERE, 0, 0, 0, i - 2\n*ENDDO")
    assert not r.ok
    assert (dict(p.model.bodies), len(p.history)) == before


def test_view_and_query_commands_are_not_history(p):
    for line in ("LIST", "HELP", "VIEW, TOP", "FIT", "PICKMODE, EDGE", "ECHO, (W*2)", "HIST"):
        assert p.run(line).ok
    assert len(p.history) == 6
    assert p.run("ECHO, (W*2)").message == "80"


def test_undo_redo(p):
    v = vol(p)
    assert p.run("UNDO, 2").ok  # back before SUBTRACT
    assert sorted(p.model.bodies) == [1, 2]
    assert p.run("REDO").ok
    assert vol(p) == pytest.approx(v)
    assert p.model.selection == []  # PICK is still undone
    assert p.run("REDO").ok and p.model.selection == [6]
    assert not p.run("REDO").ok
    # a new command after undo drops the redo tail
    p.run("UNDO")
    p.run("SPHERE, 0,0,50, 1")
    assert len(p.history) == 6 and not p.run("REDO").ok
    assert p.run("UNDO, 99").ok and p.model.bodies == {} and p.params == {}


def test_undo_also_restores_parameters_and_macros(p):
    p.run("W = 99")
    p.run_script("*MACRO, m\n*END")
    p.run("UNDO, 2")
    assert p.params["W"] == 40 and "M" not in p.macros


def test_edit_a_parameter_rebuilds_the_model(p):
    v = vol(p)
    r = p.run('HIST, EDIT, 1, "W = 60"')
    assert r.ok, r.message
    assert vol(p) == pytest.approx(v + 20 * 20 * 5)
    assert p.model.selection == [6]  # the PICK still finds the top face
    assert p.evaluate("CENT(6, 'FACE').z") == pytest.approx(5)


def test_edit_block_text_with_newlines(p):
    r = p.run('HIST, EDIT, 4, "*DO, i, 1, 2\\n  CYL, 10*i, 10, -1, 3, 7\\n*ENDDO"')
    assert r.ok, r.message
    # entry 5 subtracts LAST, which is now the second cylinder; the first one stays
    assert len(p.model.bodies) == 2


def test_failing_entries_after_an_edit_are_marked_and_skipped(p):
    r = p.run('HIST, EDIT, 3, "NAME, LAST, base"')  # entry 5 refers to 'plate'
    assert r.ok and "1 failed" in r.message and "entry 5" in r.message
    assert not p.history[4].ok and p.history[5].ok
    p.run('HIST, EDIT, 3, "NAME, LAST, plate"')
    assert all(e.ok for e in p.history)


def test_insert_delete_suppress_move(p):
    v = vol(p)
    assert p.run('HIST, INSERT, 4, "SPHERE, 0, 50, 0, 2"').ok
    assert len(p.history) == 7 and len(p.model.bodies) == 2
    assert p.model.selection == [6]  # IDs of later entries did not shift
    assert vol(p) == pytest.approx(v)
    assert p.run("HIST, DELETE, 4").ok and len(p.model.bodies) == 1
    assert p.run("HIST, SUPPRESS, 5").ok  # no subtraction
    assert vol(p) == pytest.approx(40 * 20 * 5)
    assert p.script().count("! [suppressed] SUBTRACT") == 1
    assert p.run("HIST, RESUME, 5").ok and vol(p) == pytest.approx(v)
    assert p.run("HIST, MOVE, 6, 4").ok
    assert p.history[3].label == "PICK, FACE, 6" and all(e.ok for e in p.history)
    assert not p.run("HIST, EDIT, 99, \"W = 1\"").ok
    assert not p.run('HIST, EDIT, 1, "*DO, i, 1, 2"').ok  # incomplete block
    assert not p.run('HIST, EDIT, 1, "LIST"').ok  # not a history command


def test_ids_are_pinned_per_entry_when_an_earlier_entry_adds_bodies():
    p = Processor()
    p.run_script("BLOCK, 0,0,0, 1,1,1\nCYL, 5,0,0, 1, 2\nPICK, FACE, 8")
    top_of_cyl = p.evaluate("CENT(8, 'FACE')")
    # an early new entry makes 6 faces; without pinning, the cylinder's faces would become 13..15
    assert p.run('HIST, INSERT, 2, "BLOCK, 20,0,0, 1,1,1"').ok
    assert p.model.bodies[2].entity_ids["FACE"] == [7, 8, 9]
    assert p.evaluate("CENT(8, 'FACE')") == pytest.approx(top_of_cyl)
    # the inserted block got fresh IDs above every pinned one
    assert min(p.model.bodies[3].entity_ids["FACE"]) > 9
    # and new work after the edit keeps counting from there
    p.run("SPHERE, 0,0,9, 1")
    assert p.model.last_body == 4


def test_param_entry_lookup(p):
    assert p.entry_for_param("w") == 1
    assert p.entry_for_param("nope") is None


def test_saved_log_replays_to_the_same_model(p):
    p.run('HIST, EDIT, 1, "W = 55"')
    q = Processor()
    assert all(r.ok for r in q.run_script(p.script()))
    assert q.evaluate("VOL(plate)") == pytest.approx(vol(p))
    assert q.model.selection == p.model.selection


def test_overrides_fix_parameters(tmp_path):
    p = Processor(overrides={"w": 30})
    p.run_script(PLATE)
    assert p.params["W"] == 30
    assert p.evaluate("VOL(plate)") == pytest.approx(30 * 20 * 5 - math.pi * 9 * 5, rel=1e-6)


def test_run_command_and_batch_runner(tmp_path, capsys):
    from modeler.__main__ import main

    script = tmp_path / "plate.cmd"
    script.write_text(PLATE + f'EXPORT, STEP, "{tmp_path / "plate.step"}"\n')
    p = Processor()
    r = p.run(f'RUN, "{script}"')
    assert r.ok, r.message
    assert len(p.history) == 6  # EXPORT ran but is not history
    assert (tmp_path / "plate.step").stat().st_size > 1000
    assert main(["run", str(script), "-D", "W=20", "-q"]) == 0
    assert "done: 6 history entries, 1 bodies" in capsys.readouterr().out
    assert main(["run", str(script), "-D", "nonsense"]) == 2
