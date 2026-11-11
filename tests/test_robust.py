"""References that survive heavy history edits, and kernel results that can be trusted."""

import json
import zipfile

import pytest
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_SOLID

from modeler.commands import Processor


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
    assert not r.ok, r.message
    return r.message


def cent(p, kind, gid):
    return tuple(round(p.evaluate(f"CENT({gid}, '{kind}').{a}"), 3) for a in "xyz")


PLATE = """N = 4
BLOCK, 0,0,0, 100,20,5
NAME, LAST, plate
*DO, i, 1, N
  CYL, i*20, 10, -1, 3, 10
  SUBTRACT, plate, LAST
*ENDDO
"""


def top_circle(p, x):
    """ID of the hole edge on the top face of the plate at this x."""
    ok(p, f"SEL, S, EDGE, AT, {x}, 13, 5")
    gid = p.model.selection[0]
    p.run("UNDO")
    return gid


def cones(p):
    ok(p, "SEL, S, FACE, TYPE, CONE")
    out = sorted(cent(p, "FACE", g)[0] for g in p.model.selection)
    p.run("UNDO")
    return out


# ---- IDs through history edits ---------------------------------------------------
def test_pick_comes_back_when_a_loop_count_goes_down_and_up_again(p):
    ok(p, PLATE)
    edge = top_circle(p, 60)  # hole 3
    ok(p, f"PICK, EDGE, {edge}\nCHAMFER, 0.5")
    assert cones(p) == [60.0]
    msg = p.run('HIST, EDIT, 1, "N = 2"').message  # hole 3 is gone: the pick must fail, not move
    assert "2 failed" in msg and cones(p) == []
    msg = p.run('HIST, EDIT, 1, "N = 4"').message  # and come back with the hole
    assert "failed" not in msg, msg
    assert cones(p) == [60.0]


def test_more_loop_passes_keep_earlier_ids(p):
    ok(p, PLATE)
    edge = top_circle(p, 60)
    ok(p, f"PICK, EDGE, {edge}\nCHAMFER, 0.5")
    assert "failed" not in p.run('HIST, EDIT, 1, "N = 6"').message
    assert cones(p) == [60.0]  # still hole 3, although two holes were added


def test_ids_are_the_same_after_save_and_open(p, tmp_path):
    # an inserted step gets high IDs, so a plain replay would number the model differently
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 6\nCM, top")
    p.run('HIST, INSERT, 1, "CYL, 50,0,0, 2, 5"')
    assert cent(p, "FACE", 6) == (5, 5, 10)
    before = {k: {g: cent(p, k, g) for g in p.model.entity_ids(k)} for k in ("FACE", "EDGE", "VERTEX")}
    bodies = sorted(p.model.bodies)
    path = str(tmp_path / "a.m3d")
    assert p.run(f'SAVE, "{path}"').ok
    q = Processor()
    r = q.run(f'OPEN, "{path}"')
    assert r.ok, r.message
    assert sorted(q.model.bodies) == bodies
    after = {k: {g: cent(q, k, g) for g in q.model.entity_ids(k)} for k in ("FACE", "EDGE", "VERTEX")}
    assert after == before
    assert q.model.named_set("top")[1] == [6] and cent(q, "FACE", 6) == (5, 5, 10)
    # new work after opening does not collide with the saved IDs
    ok(q, "SPHERE, 0,0,50, 3")
    assert len(set(q.model.entity_ids("FACE"))) == len(q.model.entity_ids("FACE"))
    with zipfile.ZipFile(path) as z:
        meta = json.loads(z.read("project.json"))
    assert len(meta["history"]) == 4 and meta["history"][2]["refs"][0]["type"] == "PLANE"


def test_old_project_files_without_saved_ids_still_open(p, tmp_path):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 6")
    path = str(tmp_path / "old.m3d")
    p.run(f'SAVE, "{path}"')
    with zipfile.ZipFile(path) as z:
        meta, script = json.loads(z.read("project.json")), z.read("script.cmd")
    del meta["history"]
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("project.json", json.dumps(meta))
        z.writestr("script.cmd", script)
    q = Processor()
    assert q.run(f'OPEN, "{path}"').ok and q.model.selection == [6]


# ---- picks repaired by fingerprint -----------------------------------------------
def test_pick_is_repaired_when_its_id_now_belongs_to_something_else(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 6\nCM, top")
    p.run("HIST, DELETE, 1")
    assert not p.history[0].ok  # the pick has nothing to pick
    # the block is made again after a new first step, so its faces are numbered differently:
    # FACE 6 exists, but it is now a side face
    p.run('HIST, INSERT, 1, "SPHERE, 50,0,0, 3"')
    msg = p.run('HIST, INSERT, 2, "BLOCK, 0,0,0, 10,10,10"').message
    assert "failed" not in msg and "1 warning" in msg, msg
    e = p.history[2]
    assert e.ok and "FACE 6 is now a different entity" in e.warning and "same place" in e.warning
    assert p.model.selection != [6] and cent(p, "FACE", p.model.selection[0]) == (5, 5, 10)
    assert "!" in p.run("HIST").message.splitlines()[2]
    # replaying keeps the repair and the warning
    p.run("HIST, REPLAY")
    assert p.history[2].warning and cent(p, "FACE", p.model.named_set("top")[1][0]) == (5, 5, 10)


def test_recreated_step_with_the_same_ids_needs_no_warning(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 6")
    p.run("HIST, DELETE, 1")
    msg = p.run('HIST, INSERT, 1, "BLOCK, 0,0,5, 10,10,10"').message  # same block, 5 higher, same numbering
    assert "failed" not in msg and "warning" not in msg
    assert p.model.selection == [6] and cent(p, "FACE", 6) == (5, 5, 15)


def test_pick_follows_a_face_that_moved_if_it_is_the_only_match(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 6")
    p.run("HIST, DELETE, 1")
    p.run('HIST, INSERT, 1, "SPHERE, 50,0,0, 3"')
    p.run('HIST, INSERT, 2, "BLOCK, 0,0,5, 10,10,10"')
    e = p.history[2]
    assert e.ok and "only one" in e.warning
    assert cent(p, "FACE", p.model.selection[0]) == (5, 5, 15)


def test_pick_whose_id_is_gone_is_found_again(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nCYL, 50,0,0, 2, 5\nPICK, FACE, 9")
    where = cent(p, "FACE", 9)
    p.run("HIST, DELETE, 2")
    p.run('HIST, INSERT, 1, "TORUS, 0,0,90, 5, 1"')  # takes FACE 7
    p.run('HIST, INSERT, 2, "TORUS, 0,0,80, 5, 1"')  # takes FACE 8
    assert not p.history[3].ok and "could not be found again" in p.history[3].message
    p.run('HIST, INSERT, 4, "CYL, 50,0,0, 2, 5"')  # back, numbered 10..12
    e = p.history[4]
    assert e.ok and "FACE 9" in e.warning and "instead" in e.warning
    assert cent(p, "FACE", p.model.selection[0]) == where


def test_pick_is_not_repaired_by_guessing(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, EDGE, 1")
    p.run("HIST, DELETE, 1")
    p.run('HIST, INSERT, 1, "SPHERE, 80,0,0, 3"')
    p.run('HIST, INSERT, 2, "BLOCK, 50,0,0, 10,10,10"')  # four edges now look like the picked one
    e = p.history[2]
    assert not e.ok and "look the same" in e.message


def test_new_pick_text_forgets_the_old_fingerprint(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nPICK, FACE, 6")
    r = p.run('HIST, EDIT, 2, "PICK, FACE, 99"')
    assert "no FACE with ID 99" in r.message and not p.history[1].ok


def test_warning_is_reported_on_the_result_and_cleared_when_fixed(p):
    r = ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 30,0,0, 10,10,10\nUNION, 1, 2")
    assert "2 separate pieces" in r.warning and "warning:" in r.message
    assert p.history[2].warning
    p.run('HIST, EDIT, 2, "BLOCK, 5,0,0, 10,10,10"')
    assert not p.history[2].warning


# ---- booleans ----------------------------------------------------------------------
def test_subtracting_everything_is_an_error_and_changes_nothing(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, -1,-1,-1, 20,20,20")
    assert "nothing is left" in err(p, "SUBTRACT, 1, 2")
    assert sorted(p.model.bodies) == [1, 2]


def test_intersecting_bodies_that_do_not_overlap_is_an_error(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 30,0,0, 10,10,10")
    assert "no volume in common" in err(p, "INTERSECT, 1, 2")
    ok(p, "BLOCK, 10,0,0, 10,10,10")  # shares only a face with body 1
    assert "no volume in common" in err(p, "INTERSECT, 1, 3")


def test_union_joins_the_seam_and_gives_one_solid(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 10,0,0, 10,10,10\nUNION, 1, 2")
    body = p.model.bodies[3]
    assert body.shape.ShapeType() == TopAbs_SOLID
    assert len(body.entity_ids["FACE"]) == 6 and len(body.entity_ids["EDGE"]) == 12
    assert p.evaluate("VOL(3)") == pytest.approx(2000)
    # the joined faces keep an ID from the first block: its top face is still 6
    assert cent(p, "FACE", 6) == (10, 5, 10) and p.evaluate("AREA(6)") == pytest.approx(200)
    assert len(set(body.entity_ids["FACE"])) == 6


def test_boolean_results_are_plain_solids_and_valid(p):
    ok(p, "BLOCK, 0,0,0, 20,20,5\nCYL, 10,10,-1, 3, 10\nSUBTRACT, 1, 2\nSEL, S, BODY, ID, 3\nFILLET, 1")
    shape = p.model.bodies[p.model.last_body].shape
    assert shape.ShapeType() == TopAbs_SOLID and BRepCheck_Analyzer(shape).IsValid()


def test_subtract_all_selected_bodies_in_one_step(p):
    ok(p, """BLOCK, 0,0,0, 100,20,5
NAME, LAST, plate
*DO, i, 1, 9
  CYL, i*10, 10, -1, 3, 10
*ENDDO
SEL, S, BODY, SIZE, LT, 1000
SUBTRACT, plate, SEL""")
    assert len(p.model.bodies) == 1
    plate = p.model.body_by_name("plate")
    assert len(plate.entity_ids["FACE"]) == 15
    assert p.evaluate("VOL(plate)") == pytest.approx(10000 - 9 * 3.141592653589793 * 9 * 5)
    assert p.model.selection == []
    # the same model as cutting one at a time
    q = Processor()
    ok(q, "BLOCK, 0,0,0, 100,20,5\nNAME, LAST, pl\n*DO, i, 1, 9\n  CYL, i*10, 10, -1, 3, 10\n  SUBTRACT, pl, LAST\n*ENDDO")
    assert q.evaluate("VOL(pl)") == pytest.approx(p.evaluate("VOL(plate)"))
    assert "SEL needs bodies selected" in err(p, "UNION, plate, SEL")


def test_array_fuse_joins_seams_too(p):
    ok(p, "BLOCK, 0,0,0, 10,2,2\nARRAY, LINEAR, 1, 3, 0,2,0, FUSE")
    body = p.model.bodies[p.model.last_body]
    assert len(body.entity_ids["FACE"]) == 6 and p.evaluate("VOL(LAST)") == pytest.approx(120)


# ---- fillets and chamfers ----------------------------------------------------------
def test_oversized_fillet_is_refused_with_the_size_that_works(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, BODY, ID, 1")
    msg = err(p, "FILLET, 6")
    assert "too large" in msg and "about 4.9" in msg
    assert sorted(p.model.bodies) == [1] and len(p.model.bodies[1].entity_ids["FACE"]) == 6
    ok(p, "FILLET, 4.9")  # the suggested size really works
    assert BRepCheck_Analyzer(p.model.bodies[p.model.last_body].shape).IsValid()


def test_oversized_chamfer_is_refused(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nSEL, S, BODY, ID, 1")
    assert "too large" in err(p, "CHAMFER, 7")


# ---- CHECK, HEAL, CLEAN ------------------------------------------------------------
def test_check_reports_good_bodies(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, cube\nCIRCLE, 0,0,0, 5")
    out = p.run("CHECK").message
    assert "body 1 'cube': OK (1 solid, 6 faces)" in out and "curve" in out and "all OK" in out
    assert p.cursor == 3  # CHECK is not a history entry


def _open_box(tmp_path):
    """A box with one face missing, written as a BREP file."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS_Shell, TopoDS_Solid

    b = BRep_Builder()
    shell = TopoDS_Shell()
    b.MakeShell(shell)
    ex = TopExp_Explorer(BRepPrimAPI_MakeBox(10, 10, 10).Shape(), TopAbs_FACE)
    ex.Next()  # leave one face out
    while ex.More():
        b.Add(shell, ex.Current())
        ex.Next()
    solid = TopoDS_Solid()
    b.MakeSolid(solid)
    b.Add(solid, shell)
    path = str(tmp_path / "open.brep")
    write = getattr(BRepTools, "Write_s", None) or BRepTools.Write
    assert write(solid, path)
    return path


def test_check_finds_an_open_solid_and_heal_says_when_it_cannot_fix_it(p, tmp_path):
    path = _open_box(tmp_path)
    ok(p, f'IMPORT, BREP, "{path}"')
    out = p.run("CHECK, 1").message
    assert "PROBLEM" in out and "HEAL, 1" in out
    r = p.run("HEAL, 1")
    assert not r.ok and "could not be repaired" in r.message  # a missing face cannot be invented
    assert sorted(p.model.bodies) == [1]


def test_heal_leaves_good_bodies_alone(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10")
    assert "already OK" in ok(p, "HEAL, 1").message


def test_clean_joins_faces_and_keeps_ids(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nBLOCK, 3,3,10, 4,4,4\nUNION, 1, 2\nBLOCK, 3,3,10, 4,4,10\nSUBTRACT, 3, 4")
    body = p.model.bodies[p.model.last_body]
    n = len(body.entity_ids["FACE"])
    assert n > 6  # the top face is left in pieces by the cut
    msg = ok(p, f"CLEAN, {body.id}").message
    assert "fewer" in msg
    cleaned = p.model.bodies[body.id]  # same body ID
    assert len(cleaned.entity_ids["FACE"]) == 6 and p.evaluate(f"VOL({body.id})") == pytest.approx(1000)
    assert cent(p, "FACE", 1) == (0, 5, 5)  # side faces keep their IDs
    assert "no faces to join" in ok(p, f"CLEAN, {body.id}").message
