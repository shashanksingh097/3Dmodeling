"""PLAN item 70: features found on bodies without history, changed or removed in bulk."""

import pytest

from modeler.commands import Processor
from modeler.geometry import found as fd
from modeler.geometry import robust

PART = """BLOCK, 0,0,0, 100,60,10
SEL, S, EDGE, LOC, Z, 10
SEL, R, EDGE, LOC, X, 0
FILLET, 3
SEL, S, EDGE, LOC, Z, 10
SEL, R, EDGE, LOC, X, 100
CHAMFER, 2
SEL, S, FACE, LOC, Z, 10
HOLE, LAST, 20,30,10, 6
HOLE, LAST, 40,30,10, 6
HOLE, LAST, 60,30,10, 6
HOLE, LAST, 80,15,10, 8, 4
"""


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1]


def err(p, line):
    r = p.run(line)
    assert not r.ok, r.message
    return r.message


@pytest.fixture
def p():
    p = Processor()
    ok(p, PART)
    return p


def _imported(p, tmp_path):
    """The part through STEP and back: one body with no history."""
    f = tmp_path / "part.step"
    ok(p, f'EXPORT, STEP, "{f}"')
    q = Processor()
    ok(q, f'IMPORT, STEP, "{f}"')
    return q, max(q.model.bodies)


def test_features_lists_every_kind(p):
    b = max(p.model.bodies)
    r = ok(p, f"FEATURES, {b}")
    rows = r.report["features"]
    kinds = [x["kind"] for x in rows]
    assert kinds.count("HOLE") == 4 and kinds.count("FILLET") == 1 and kinds.count("CHAMFER") == 1
    pat = [x for x in rows if x["kind"] == "PATTERN"]
    assert len(pat) == 1 and pat[0]["pattern"] == "LINEAR" and pat[0]["count"] == 3
    assert pat[0]["step"] == pytest.approx(20)
    blind = next(x for x in rows if x["kind"] == "HOLE" and not x["through"])
    assert blind["size"] == pytest.approx(8) and blind["depth"] == pytest.approx(4)
    assert len(blind["faces"]) == 2  # the wall and the bottom
    ch = next(x for x in rows if x["kind"] == "CHAMFER")
    assert ch["size"] == pytest.approx(2) and ch["leg"] == pytest.approx(2)
    assert "row of 3 holes" in r.message
    assert ok(p, f"FEATURES, {b}, FILLETS").report["features"][0]["size"] == pytest.approx(3)


def test_on_an_imported_step_part(p, tmp_path):
    q, b = _imported(p, tmp_path)
    assert len(q.model.bodies[b].entity_ids["FACE"]) > 6
    rows = ok(q, f"FEATURES, {b}").report["features"]
    assert sorted(x["kind"] for x in rows) == ["CHAMFER", "FILLET", "HOLE", "HOLE", "HOLE", "HOLE", "PATTERN"]
    v0 = robust.volume(q.model.body(b).shape)
    ok(q, f"DEFEATURE, {b}, FILLET")
    ok(q, f"DEFEATURE, {b}, HOLE, EQ, 8")
    kinds = [x["kind"] for x in ok(q, f"FEATURES, {b}").report["features"]]
    assert "FILLET" not in kinds and kinds.count("HOLE") == 3
    assert robust.volume(q.model.body(b).shape) > v0


def test_defeature_everything_gives_the_block(p):
    b = max(p.model.bodies)
    ok(p, f"DEFEATURE, {b}, HOLE\nDEFEATURE, {b}, FILLET\nDEFEATURE, {b}, CHAMFER")
    s = p.model.body(b).shape
    assert robust.volume(s) == pytest.approx(100 * 60 * 10, rel=1e-6)
    assert len(p.model.body(b).entity_ids["FACE"]) == 6
    assert "no hole" in err(p, f"DEFEATURE, {b}, HOLE")


def test_defeature_by_size_says_what_sizes_there_are(p):
    b = max(p.model.bodies)
    msg = err(p, f"DEFEATURE, {b}, HOLE, LT, 2")
    assert "sizes found: 6, 8" in msg


def test_resize_holes_keeps_position_and_depth(p):
    b = max(p.model.bodies)
    ok(p, f"RESIZE, {b}, HOLE, EQ, 6, 5")
    rows = ok(p, f"FEATURES, {b}, HOLE").report["features"]
    sizes = sorted(round(x["size"], 6) for x in rows)
    assert sizes == [5, 5, 5, 8]
    assert sorted(round(x["at"][0], 6) for x in rows if x["size"] < 6) == [20, 40, 60]
    ok(p, f"RESIZE, {b}, HOLE, GT, 7, 9")
    blind = next(x for x in ok(p, f"FEATURES, {b}, HOLE").report["features"] if not x["through"])
    assert blind["size"] == pytest.approx(9) and blind["depth"] == pytest.approx(4)


def test_resize_fillet_and_chamfer(p):
    b = max(p.model.bodies)
    ok(p, f"RESIZE, {b}, FILLET, EQ, 3, 5")
    ok(p, f"RESIZE, {b}, CHAMFER, ALL, , 1")
    rows = ok(p, f"FEATURES, {b}").report["features"]
    assert next(x for x in rows if x["kind"] == "FILLET")["size"] == pytest.approx(5)
    assert next(x for x in rows if x["kind"] == "CHAMFER")["size"] == pytest.approx(1)
    assert robust.is_valid(p.model.body(b).shape)


def test_select_like_and_feature(p):
    b = max(p.model.bodies)
    rows = ok(p, f"FEATURES, {b}, HOLE").report["features"]
    small = [x for x in rows if x["size"] == pytest.approx(6)]
    ok(p, f"SEL, S, FACE, LIKE, {small[0]['faces'][0]}")
    assert sorted(p.model.selection) == sorted(f for x in small for f in x["faces"])
    ok(p, "SEL, S, FACE, FEATURE, HOLE, GT, 7")
    big = next(x for x in rows if x["size"] == pytest.approx(8))
    assert sorted(p.model.selection) == sorted(big["faces"])
    ok(p, "SEL, S, FACE, FEATURE, FILLET")
    assert len(p.model.selection) == 1
    # a plain face: same type and size
    ok(p, "SEL, S, FACE, NORMAL, 0,1,0")
    side = sorted(p.model.selection)[0]
    ok(p, f"SEL, S, FACE, LIKE, {side}")
    assert len(p.model.selection) == 2  # front and back are the same size


def test_history_replays_and_edits(p):
    b = max(p.model.bodies)
    ok(p, f"RESIZE, {b}, HOLE, EQ, 6, 4")
    n = len(p.history)
    p.rebuild()
    assert all(e.ok for e in p.history) and len(p.history) == n
    assert sorted(round(x["size"], 6) for x in ok(p, f"FEATURES, {b}, HOLE").report["features"]) == [4, 4, 4, 8]


def test_finder_on_plain_shapes():
    p = Processor()
    ok(p, "CYL, 0,0,0, 5, 20")
    assert ok(p, "FEATURES, LAST").report["features"] == []  # a whole cylinder is not a round
    assert fd.compare("LT", 2, 1.9) and not fd.compare("LT", 2, 2.0)


def test_right_click_menu_offers_similar_resize_remove(p):
    from modeler.gui import body_menu as bm

    b = max(p.model.bodies)
    hole = next(x for x in ok(p, f"FEATURES, {b}, HOLE").report["features"] if x["size"] == pytest.approx(6))
    ok(p, f"SEL, S, FACE, ID, {hole['faces'][0]}")
    items = bm.body_items(p.model, b)
    labels = [i.label for i in items]
    assert "Select similar" in labels and "List its holes, rounds and chamfers" in labels
    rm = next(i for i in items if i.label.startswith("Remove every 6"))
    rs = next(i for i in items if i.label.startswith("Change the size of every 6"))
    assert rs.form == "RESIZE" and rs.commands == [f"RESIZE, {b}, HOLE, EQ, 6, 6"]
    sim = next(i for i in items if i.label == "Select similar")
    ok(p, sim.commands[0])
    assert len(p.model.selection) == 3
    ok(p, rm.commands[0])
    assert [x["size"] for x in ok(p, f"FEATURES, {b}, HOLE").report["features"]] == [8]
