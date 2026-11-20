"""Reference stability (PLAN item 50): picks keep pointing at what was picked when the history
is edited upstream, saved and opened again; SEL by IDs is kept like PICK; REFS lists every
reference and its state.

Most tests compare against a second model that reaches the same part by another route (the
upstream change made at the end instead, or the edges picked by where they are), so they check
that the picked entities are the right ones, not only that the steps still run."""

import os

import pytest

from modeler.commands import Processor


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    results = p.run_script(text)
    bad = [r for r in results if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return results[-1]


def failed(p):
    return [(i + 1, e.text, e.message) for i, e in enumerate(p.history[: p.cursor]) if not e.ok]


def shape_of(p, b=None):
    """Volume, area and face count of the last (or the given) body."""
    b = b or max(p.model.bodies)
    return (round(p.evaluate(f"VOL({b})"), 3), round(p.evaluate(f"AREA({b}, 'BODY')"), 3),
            len(p.model.bodies[b].entity_ids["FACE"]))


def cent(p, kind, gid):
    return tuple(round(p.evaluate(f"CENT({gid}, '{kind}').{a}"), 6) for a in "xyz")


def edge_ids_at_z(p, z):
    p.run(f"SEL, S, EDGE, LOC, Z, {z}")
    return list(p.model.selection)


def pick_lines(kind, ids):
    lines = [f"PICK, {kind}, {ids[0]}"]
    lines += [f"PICK, {kind}, {i}, A" for i in ids[1:]]
    return "\n".join(lines)


# ---- SEL by IDs is kept like PICK -----------------------------------------------------------------

def test_sel_id_range_is_found_again_when_its_ids_move(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, ID, 5, 6\nCM, caps")
    caps = sorted(cent(p, "FACE", g) for g in p.model.named_set("caps")[1])
    p.run("HIST, DELETE, 1")
    p.run('HIST, INSERT, 1, "SPHERE, 50,0,0, 3"')
    p.run('HIST, INSERT, 2, "BLOCK, 0,0,0, 10,10,10"')  # numbered differently now
    e = p.history[2]
    assert e.ok and "picked the same faces by their shape" in e.warning, (e.message, e.warning)
    assert sorted(cent(p, "FACE", g) for g in p.model.named_set("caps")[1]) == caps


def test_sel_id_range_is_not_repaired_by_guessing(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, EDGE, ID, 1")
    p.run("HIST, DELETE, 1")
    p.run('HIST, INSERT, 1, "SPHERE, 80,0,0, 3"')
    p.run('HIST, INSERT, 2, "BLOCK, 50,0,0, 10,10,10"')  # four edges look like the picked one
    e = p.history[2]
    assert not e.ok and "could not be found again" in e.message and "look the same" in e.message


def test_sel_id_range_with_a_new_parameter_value_starts_afresh(p):
    ok(p, "N = 5\nBLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, ID, N")
    assert p.model.selection == [5]
    p.run('HIST, EDIT, 1, "N = 6"')
    assert p.model.selection == [6] and not p.history[2].warning


def test_sel_id_range_keeps_its_faces_when_the_range_now_covers_more(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, ID, 1, 99\nCM, all_faces")
    assert len(p.model.named_set("all_faces")[1]) == 6
    p.run('HIST, INSERT, 2, "CYL, 50,0,0, 2, 5"')  # faces 7..9 now fall in the range too
    e = p.history[2]
    assert e.ok and "kept the 6 picked before" in e.warning
    assert len(p.model.named_set("all_faces")[1]) == 6


# ---- long histories edited upstream ------------------------------------------------------------

PLATE = """W = 40
BLOCK, 0,0,0, W, 20, 10
NAME, LAST, plate
CYL, 10, 10, -1, 3, 12
SUBTRACT, plate, LAST
"""


def test_upstream_hole_does_not_move_a_picked_fillet(p):
    """Picked top edges filleted, then a second hole inserted upstream: the result must equal
    the part with that hole cut at the end (the hole is away from the rounded edges)."""
    q = Processor()
    ok(q, PLATE)
    top = edge_ids_at_z(q, 10)
    ok(p, PLATE + pick_lines("EDGE", top) + "\nFILLET, 1\n")
    p.run('HIST, INSERT, 4, "CYL, 30, 10, -1, 2, 12"')
    p.run('HIST, INSERT, 5, "SUBTRACT, plate, LAST"')
    assert not failed(p), failed(p)
    ref = Processor()
    ok(ref, PLATE + pick_lines("EDGE", top) + "\nFILLET, 1\nCYL, 30, 10, -1, 2, 12\nSUBTRACT, plate, LAST\n")
    assert shape_of(p) == shape_of(ref)


def test_upstream_size_edit_keeps_picked_edges(p):
    """The block gets wider after the edges were picked: the same edges (by meaning) are rounded."""
    q = Processor()
    ok(q, PLATE)
    top = edge_ids_at_z(q, 10)
    ok(p, PLATE + pick_lines("EDGE", top) + "\nFILLET, 1\nASSERT, VALID(plate)\n")
    p.run('HIST, EDIT, 1, "W = 70"')
    assert not failed(p), failed(p)
    ref = Processor()
    ok(ref, PLATE.replace("W = 40", "W = 70") + "SEL, S, EDGE, LOC, Z, 10\nFILLET, 1\n")
    assert shape_of(p) == shape_of(ref)


def test_pattern_count_change_keeps_a_picked_outer_edge(p):
    base = ("N = 3\nBLOCK, 0,0,0, 80, 20, 10\nNAME, LAST, bar\n"
            "CYL, 10, 10, -1, 2, 12\nARRAY, LINEAR, LAST, N, 15, 0, 0, CUT, bar\n")
    q = Processor()
    ok(q, base)
    q.run("SEL, S, EDGE, LOC, Z, 10\nSEL, R, EDGE, TYPE, LINE")
    outer = sorted(q.model.selection)
    assert len(outer) == 4
    ok(p, base + pick_lines("EDGE", outer) + "\nCHAMFER, 1\n")
    p.run('HIST, EDIT, 1, "N = 5"')
    assert not failed(p), failed(p)
    ref = Processor()
    ok(ref, base.replace("N = 3", "N = 5") + "SEL, S, EDGE, LOC, Z, 10\nSEL, R, EDGE, TYPE, LINE\nCHAMFER, 1\n")
    assert shape_of(p) == shape_of(ref)


def test_saved_project_edited_after_opening(p, tmp_path):
    q = Processor()
    ok(q, PLATE)
    top = edge_ids_at_z(q, 10)
    path = os.path.join(tmp_path, "plate.m3d").replace("\\", "/")
    ok(p, PLATE + pick_lines("EDGE", top) + "\nFILLET, 1\n" + f'SAVE, "{path}"')
    before = shape_of(p)
    r = Processor()
    ok(r, f'OPEN, "{path}"')
    assert shape_of(r) == before
    r.run('HIST, INSERT, 4, "CYL, 30, 10, -1, 2, 12"')
    r.run('HIST, INSERT, 5, "SUBTRACT, plate, LAST"')
    assert not failed(r), failed(r)
    ref = Processor()
    ok(ref, PLATE + pick_lines("EDGE", top) + "\nFILLET, 1\nCYL, 30, 10, -1, 2, 12\nSUBTRACT, plate, LAST\n")
    assert shape_of(r) == shape_of(ref)
    assert "broken" not in r.run("REFS").message


def test_a_picked_face_that_is_deleted_upstream_is_reported_broken(p):
    ok(p, PLATE)
    p.run("SEL, S, FACE, TYPE, CYLINDER")
    wall = p.model.selection[0]
    ok(p, f"PICK, FACE, {wall}\nCM, wall")
    p.run("HIST, DELETE, 4")  # the subtract that made the hole wall
    p.run("HIST, DELETE, 3")  # and the cylinder
    rows = p.run("REFS, PROBLEMS").message
    assert "broken" in rows and f"PICK, FACE, {wall}" in rows, rows


# ---- REFS --------------------------------------------------------------------------------------

def test_refs_lists_every_pick_and_its_state(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, ID, 5, 6\nPICK, EDGE, 1")
    msg = p.run("REFS").message
    assert msg.splitlines()[0] == "3 references: 3 ok"
    assert "step 2 SEL, S, FACE, ID, 5, 6: FACE 5 (plane on " in msg and "made by step 1) ok" in msg
    p.run("HIST, DELETE, 1")
    p.run('HIST, INSERT, 1, "SPHERE, 50,0,0, 3"')
    p.run('HIST, INSERT, 2, "BLOCK, 0,0,0, 10,10,10"')
    msg = p.run("REFS").message
    assert "repaired" in msg.splitlines()[0], msg


def test_refs_json(p):
    import json

    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 6")
    rows = json.loads(p.run("REFS, ALL, JSON").message)
    assert rows == [{"step": 2, "text": "PICK, FACE, 6", "kind": "FACE", "id": 6, "type": "PLANE",
                     "body": rows[0]["body"], "made_by": 1, "state": "ok"}]


# ---- names from parents (PLAN item 51) ---------------------------------------------------------

def test_fillet_faces_remember_the_edge_they_round(p):
    ok(p, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, b\nSEL, S, EDGE, LOC, Z, 10\nFILLET, 2")
    made = [g for g in p.model.entity_ids("FACE") if p.model.origin("FACE", g) == p.history[3].uid]
    assert len(made) == 4
    assert sorted(p.model.parent("FACE", g) for g in made) == [("EDGE", 2), ("EDGE", 6), ("EDGE", 10), ("EDGE", 12)]


def test_split_face_pieces_remember_the_face(p):
    # a slot cuts the top face in two: the big piece keeps FACE 6, the other piece comes from it
    ok(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, b\nBLOCK, 7,-1,8, 1,12,5\nSUBTRACT, b, LAST")
    kids = [g for g in p.model.entity_ids("FACE") if p.model.parent("FACE", g) == ("FACE", 6)]
    assert len(kids) == 1 and kids[0] != 6
    assert p.evaluate(f"CENT({kids[0]}, 'FACE').z") == pytest.approx(10)


def test_a_face_whose_size_changed_is_found_by_how_it_was_made(p):
    from modeler.core import refs

    ok(p, "BLOCK, 0,0,0, 40,20,10\nNAME, LAST, b\nPICK, EDGE, 10\nFILLET, 2")
    face = next(g for g in p.model.entity_ids("FACE") if p.model.parent("FACE", g) == ("EDGE", 10))
    fp = refs.fingerprint(p.model, "FACE", face)
    old = dict(fp, id=999, size=fp["size"] * 2, c=[0.0, 0.0, 0.0])  # as if the radius had been different
    assert refs.find(p.model, old) == (face, "made by the same step from the same edge")
    assert refs.find(p.model, dict(old, origin=12345))[0] is None  # another step: no guess


def test_look_alikes_are_told_apart_by_the_step_that_made_them(p):
    from modeler.core import refs

    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 0,0,0, 10,10,10")
    fp = refs.fingerprint(p.model, "FACE", 12)  # the top of the second block, exactly on the first's
    assert refs.find(p.model, dict(fp, id=999, body="")) == (12, "same place")


# ---- picking a step again ----------------------------------------------------------------------

def test_hist_repick_rewrites_a_broken_pick(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nCYL, 50,0,0, 2, 5\nPICK, FACE, 9\nCM, f")
    p.run("HIST, DELETE, 2")
    assert not p.history[1].ok
    r = p.run('HIST, REPICK, 2, "FACE, 6"')
    assert r.ok and p.history[1].text == "PICK, FACE, 6" and all(e.ok for e in p.history)
    assert "broken" not in p.run("REFS").message
    p.run("UNDO")
    assert not p.history[1].ok


def test_hist_repick_keeps_the_mode_and_takes_several(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 1\nSEL, A, FACE, ID, 2\nCM, two")
    r = p.run('HIST, REPICK, 3, "FACE, 5, 6"')
    assert r.ok and [e.text for e in p.history[2:4]] == ["PICK, FACE, 5, A", "PICK, FACE, 6, A"]
    assert sorted(p.model.named_set("two")[1]) == [1, 5, 6]


def test_hist_repick_refuses_a_step_that_does_not_pick(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, FACE, LOC, Z, 10")
    assert "does not pick by ID" in p.run('HIST, REPICK, 2, "FACE, 6"').message
