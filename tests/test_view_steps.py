"""The view's own steps (FADE, UNFADE, DISPLAY) and the right-click menu model.

View steps change only how bodies are drawn. They are not history entries,
undo and rebuilds keep them, and they are saved with the project.
"""

import pytest

from modeler.commands import Processor
from modeler.gui import body_menu as bm
from modeler.gui import forms as F


@pytest.fixture
def p():
    p = Processor()
    for line in ("BLOCK, 0,0,0, 10,10,10", "BLOCK, 20,0,0, 10,10,10", "CYL, 40,5,0, 4, 12"):
        ok(p, line)
    return p


def ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r.message


def bad(p, line):
    r = p.run(line)
    assert not r.ok, f"{line} should fail, got: {r.message}"
    return r.message


def shown(p):
    return [p.model.is_shown(b) for b in sorted(p.model.bodies)]


def test_view_steps_are_not_history_entries(p):
    n = len(p.history)
    ok(p, "FADE, 1")
    ok(p, "DISPLAY, HIDE, 2")
    ok(p, "UNFADE")
    ok(p, "DISPLAY, ALL")
    assert len(p.history) == n


def test_fade_and_unfade(p):
    m = p.model
    ok(p, "FADE, 1")
    assert m.display_transparency(1) == pytest.approx(0.8)
    ok(p, "FADE, 2 3, 0.4")
    assert m.display_transparency(3) == pytest.approx(0.4)
    assert "solid again" in ok(p, "UNFADE, 2")
    assert m.display_transparency(2) == 0 and m.display_transparency(3) == pytest.approx(0.4)
    ok(p, "UNFADE")
    assert not m.faded
    assert "0.95" in bad(p, "FADE, 1, 2")
    assert "number" in bad(p, "FADE, 1, lots")


def test_fade_others_keeps_the_named_or_selected_bodies_solid(p):
    m = p.model
    ok(p, "FADE, ALL")
    assert "2 other bodies" in ok(p, "FADE, OTHERS, , 3")
    assert m.display_transparency(3) == 0
    assert m.display_transparency(1) > 0 and m.display_transparency(2) > 0
    ok(p, "PICK, BODY, 1")
    ok(p, "FADE, OTHERS")
    assert m.display_transparency(1) == 0 and m.display_transparency(3) > 0


def test_fade_and_glass_take_the_more_see_through(p):
    ok(p, "MATERIAL, 1, GLASS")
    glass = p.model.display_transparency(1)
    ok(p, "FADE, 1, 0.1")
    assert p.model.display_transparency(1) == glass
    ok(p, "FADE, 1, 0.95")
    assert p.model.display_transparency(1) == pytest.approx(0.95)


def test_display_hide_show_only_all_model(p):
    ok(p, "DISPLAY, HIDE, 2")
    assert shown(p) == [True, False, True]
    ok(p, "DISPLAY, ONLY, 3")
    assert shown(p) == [False, False, True]
    ok(p, "DISPLAY, SHOW, 1")
    assert shown(p) == [True, False, True]
    ok(p, "HIDE, 1")  # a history step names body 1 again: it decides
    assert shown(p) == [False, False, True]
    ok(p, "FADE, 3")
    assert "solid" in ok(p, "DISPLAY, ALL")
    assert shown(p) == [True, True, True] and not p.model.faded
    assert "history" in ok(p, "DISPLAY, MODEL")
    assert shown(p) == [False, True, True]  # HIDE, 1 is in the history
    assert "use one of" in bad(p, "DISPLAY, WOBBLE")


def test_show_all_and_isolate_clear_the_view_overrides(p):
    ok(p, "DISPLAY, HIDE, 1")
    ok(p, "SHOW, ALL")
    assert shown(p) == [True, True, True]
    ok(p, "DISPLAY, HIDE, 2")
    ok(p, "ISOLATE, 2")
    assert shown(p) == [False, True, False]


def test_undo_and_history_edits_keep_the_view(p):
    ok(p, "FADE, 1")
    ok(p, "DISPLAY, HIDE, 3")
    ok(p, 'HIST, EDIT, 1, "BLOCK, 0,0,0, 12,10,10"')
    assert 1 in p.model.faded and shown(p) == [True, True, False]
    ok(p, "UNDO")  # takes back the CYL (body 3)
    assert 1 in p.model.faded and shown(p) == [True, True]
    ok(p, "REDO")  # body 3 comes back with the same ID, still hidden by the view
    assert shown(p) == [True, True, False]


def test_the_view_is_saved_with_the_project(p, tmp_path):
    ok(p, "FADE, OTHERS, 0.5, 2")
    ok(p, "DISPLAY, HIDE, 3")
    f = tmp_path / "v.m3d"
    ok(p, f'SAVE, "{f}"')
    q = Processor()
    ok(q, f'OPEN, "{f}"')
    assert q.model.faded == {1: 0.5, 3: 0.5}
    assert [q.model.is_shown(b) for b in sorted(q.model.bodies)] == [True, True, False]
    assert "faded" in ok(q, "LIST, BODIES")


def test_fit_takes_bodies(p):
    assert "2 bodies" in ok(p, "FIT, 1 3")
    ok(p, "FIT")
    bad(p, "FIT, 9")


def test_view_commands_have_forms():
    assert F.missing_forms() == []
    for n in ("FADE", "UNFADE", "DISPLAY"):
        F.spec(n)


# ---- the right-click menu (what it offers and sends) ---------------------------------

def labels(items):
    return [i.label for i in items if i.label]


def item(items, label):
    return next(i for i in items if i.label == label)


def test_body_menu_on_one_body(p):
    items = bm.body_items(p.model, 2)
    assert items[0].title and "body 2" in items[0].label
    assert item(items, "Hide this").commands == ["DISPLAY, HIDE, 2"]
    assert item(items, "Fade all others").commands == ["FADE, OTHERS, , 2"]
    assert item(items, "Zoom to").commands == ["FIT, 2"]
    for it in items:  # every command it would send runs
        if it.commands and not it.form and not it.ask and not it.commands[0].startswith("DELETE"):
            ok(p, it.commands[0])
    ok(p, "FADE, 2")
    assert "Make this solid" in labels(bm.body_items(p.model, 2))
    assert "Back to the model's own view" in labels(bm.body_items(p.model, 2))


def test_body_menu_acts_on_the_selection_when_clicked_on_it(p):
    ok(p, "PICK, BODY, 1")
    ok(p, "PICK, BODY, 3, A")
    items = bm.body_items(p.model, 3)
    assert "2 selected" in items[0].label
    assert item(items, "Fade these 2").commands == ["FADE, 1 3"]
    assert item(items, "Delete 2 bodies").commands == ["DELETE, 1", "DELETE, 3"]
    items = bm.body_items(p.model, 2)  # not on the selection: just that body
    assert item(items, "Hide this").commands == ["DISPLAY, HIDE, 2"]


def test_body_menu_rename_find_step_and_instances(p):
    items = bm.body_items(p.model, 1)
    ren = item(items, "Rename…")
    assert ren.ask and ren.commands == ["NAME, 1, {}"]
    find = item(items, "Find the step that made it")
    assert find.find_entry == p.history[0].uid
    ok(p, "*PART, peg, D=4\nCYL, 0,0,0, D/2, 10\n*ENDPART")
    ok(p, "INST, peg, 60,0,0")
    bid = p.model.last_body
    explode = [i for i in bm.body_items(p.model, bid) if i.label.startswith("Explode")]
    assert explode and explode[0].commands == [f"EXPLODE, {bid}"]


def test_empty_space_and_history_row_menus(p):
    assert labels(bm.empty_items(p.model)) == ["Show everything", "Fit all"]
    ok(p, "FADE, 1")
    assert "Make all solid" in labels(bm.empty_items(p.model))
    assert bm.entry_bodies(p, 1) == [2]
    rows = bm.entry_items(p, 2)
    assert item(rows, "Hide this").commands == ["DISPLAY, HIDE, 3"]
    assert bm.entry_items(p, 99) == []
