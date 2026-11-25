"""PLAN item 79: CLASHFIX cuts a clash out or moves a part clear, with a preview first."""

import pytest

from modeler.commands import Processor


def ok(p, line):
    r = p.run(line)
    assert r.ok, r.message
    return r


@pytest.fixture
def p():
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 40, 30, 20")
    ok(p, "NAME, LAST, box")
    ok(p, "CYL, 35, 15, 5, 8, 30")
    ok(p, "NAME, LAST, pin")
    return p


def test_clash_says_how_to_fix(p):
    assert "CLASHFIX, a, b, CUT" in ok(p, "CLASH, box, pin").message


def test_preview_changes_nothing_and_is_not_kept(p):
    n, rev = len(p.history), p.model.revision
    r = ok(p, "CLASHFIX, box, pin, CUT, 0, AUTO, PREVIEW")
    assert r.message.startswith("CLASHFIX preview: would cut 2624") and len(p.history) == n
    r = ok(p, "CLASHFIX, pin, box, MOVE, 0, AUTO, PREVIEW")
    assert "would move body 2 by (13, 0, 0)" in r.message and len(p.history) == n
    assert p.model.revision == rev and p.reports["CLASHFIX"]["preview"]


def test_cut_with_clearance(p):
    r = ok(p, "CLASHFIX, box, pin, CUT, 0.5")
    assert "cut 299" in r.message and "-> body 1 'box'" in r.message
    assert "clear: gap 0.5" in ok(p, "CLASH, box, pin").message
    assert 2 in p.model.bodies  # the pin stays
    ok(p, "UNDO")
    assert "OVERLAP" in ok(p, "CLASH, box, pin").message


def test_move_shortest_and_along_a_direction(p):
    ok(p, "CLASHFIX, pin, box, MOVE, 1")
    assert "clear: gap 1" in ok(p, "CLASH, box, pin").message
    assert abs(p.reports["CLASHFIX"]["move"][0] - 14) < 1e-3
    ok(p, "UNDO")
    ok(p, "CLASHFIX, pin, box, MOVE, 0, -Z")
    assert abs(p.reports["CLASHFIX"]["move"][2] + 35) < 1e-3
    assert "touch" in ok(p, "CLASH, box, pin").message


def test_nothing_to_fix_and_refusals(p):
    ok(p, "MOVE, pin, 100, 0, 0")
    assert "nothing to fix" in ok(p, "CLASHFIX, box, pin").message
    assert "CUT or MOVE" in p.run("CLASHFIX, box, pin, SHAVE").message
    assert "different" in p.run("CLASHFIX, box, box").message


def test_right_click_offers_the_fixes(p):
    from modeler.gui import body_menu as bm

    p.model.select("BODY", [1, 2])
    labels = {i.label: i.commands for i in bm.body_items(p.model, 2)}
    assert labels["Clash: see pin (body 2) cut out of box (body 1)".replace("see pin (body 2) cut out of box (body 1)",
                                                                            "see box (body 1) cut out of pin (body 2)")] \
        == ["CLASHFIX, 2, 1, CUT, 0, AUTO, PREVIEW"]
    assert labels["Clash: move pin (body 2) clear of box (body 1)"] == ["CLASHFIX, 2, 1, MOVE"]
