"""Healing imported models (PLAN item 53): CHECK FLAWS on imperfect files, HEAL saying what it
fixed and what is left, and STEP part names and colours kept both ways."""

import json
import os

import pytest

import flawed_files as ff
from modeler.commands import Processor


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    assert not bad, f"{bad[0].line}: {bad[0].message}"
    return res[-1]


def imported(p, path):
    fmt = "BREP" if path.endswith(".brep") else "STEP"
    ok(p, f'IMPORT, {fmt}, "{path}"')
    return max(p.model.bodies)


def flaws(p, b, tol=0.05):
    return json.loads(p.run(f"CHECK, {b}, FLAWS, {tol}, JSON").message)


def test_loose_faces_become_a_solid(p, tmp_path):
    b = imported(p, ff.loose_faces(str(tmp_path)))
    f = flaws(p, b)
    assert f["solids"] == 0 and len(f["gaps"]) == 24 and f["problems"] > 0
    r = ok(p, f"HEAL, {b}, 0.05")
    assert "now 1 solid" in r.message and "joined 24 open edges" in r.message and "left:" not in r.message
    assert p.evaluate(f"VOL({b})") == pytest.approx(1000)
    assert flaws(p, b)["problems"] == 0


def test_gaps_are_measured_and_closed(p, tmp_path):
    b = imported(p, ff.gaps(str(tmp_path), gap=0.02))
    f = flaws(p, b)
    assert max(g["size"] for g in f["gaps"]) == pytest.approx(0.02, abs=1e-6)
    # a tolerance below the gap leaves those edges as holes
    small = flaws(p, b, 0.01)
    assert small["open_edges"] == 8
    msg = p.run(f"CHECK, {b}, FLAWS, 0.01").message
    assert "8 open edges with nothing within 0.01 to join to" in msg
    r = ok(p, f"HEAL, {b}, 0.05")
    assert "gaps up to 0.02" in r.message and "now 1 solid" in r.message
    assert p.evaluate(f"VOL({b})") == pytest.approx(1000, rel=0.01)


def test_flipped_face_is_turned(p, tmp_path):
    b = imported(p, ff.flipped(str(tmp_path)))
    f = flaws(p, b)
    assert f["flipped"] and not f["valid"]
    r = ok(p, f"HEAL, {b}")
    assert "turned faces that faced the wrong way" in r.message
    assert p.run(f"CHECK, {b}").message.endswith("OK (1 solid, 6 faces)")
    assert p.evaluate(f"VOL({b})") == pytest.approx(1000)


def test_duplicate_face_is_removed(p, tmp_path):
    b = imported(p, ff.duplicate(str(tmp_path)))
    f = flaws(p, b)
    assert len(f["duplicates"]) == 1
    r = ok(p, f"HEAL, {b}, 0.05")
    assert "removed 1 duplicate face" in r.message and "now 1 solid, 6 faces" in r.message


def test_slivers_are_listed_and_left(p, tmp_path):
    b = imported(p, ff.slivers(str(tmp_path), step=0.002))
    f = flaws(p, b)
    assert len(f["slivers"]) == 4 and all(s["width"] < 0.003 for s in f["slivers"])
    assert len(f["tiny_edges"]) == 4
    # the slivers are listed by the body's own face IDs, which SEL and DELFACE take
    faces = set(p.model.bodies[b].entity_ids["FACE"])
    assert {s["face"] for s in f["slivers"]} <= faces
    # at the default tolerance (a thousandth of the size, 0.017) the step is a flaw, at 0.001 it is not
    assert flaws(p, b, 0.001)["problems"] == 0
    msg = p.run(f"CHECK, {b}, FLAWS").message
    assert "4 sliver faces narrower than 0.017" in msg and "DELFACE" in msg


def test_a_clean_body_has_no_flaws(p):
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nCYL, 20, 0, 0, 3, 10")
    msg = p.run("CHECK, , FLAWS").message
    assert msg.count("no flaws larger than") == 2
    assert p.run("HEAL, 1").message == "body 1 is already OK; nothing to repair"


def test_step_names_and_colours_round_trip(p, tmp_path):
    out = str(tmp_path / "parts.step")
    ok(p, "BLOCK, 0, 0, 0, 10, 10, 10\nNAME, 1, Bracket\nCOLOR, 1, 255, 0, 0\n"
          "CYL, 20, 0, 0, 3, 10\nNAME, 2, Pin\nCOLOR, 2, 0, 128, 255\nBLOCK, 40, 0, 0, 1, 1, 1")
    ok(p, f'EXPORT, STEP, "{out}"')
    q = Processor()
    r = ok(q, f'IMPORT, STEP, "{out}"')
    assert "3 bodies" in r.message
    by_name = {b.name: b for b in q.model.bodies.values()}
    assert by_name["Bracket"].color == pytest.approx(p.model.bodies[1].color, abs=2e-3)
    assert by_name["Pin"].color == pytest.approx(p.model.bodies[2].color, abs=2e-3)
    # the plain box had no name of its own and keeps the plain one
    assert sorted(by_name) == ["Bracket", "Pin", "body3"]
    # names already in use get a number
    ok(q, f'IMPORT, STEP, "{out}"')
    assert {"Bracket_2", "Pin_2"} <= {b.name for b in q.model.bodies.values()}


def test_step_names_from_other_programs_are_made_usable(p, tmp_path):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

    from modeler.geometry import stepdoc

    out = str(tmp_path / "theirs.step")
    a, b = BRepPrimAPI_MakeBox(5, 5, 5).Shape(), BRepPrimAPI_MakeBox(5, 6, 7).Shape()
    assert stepdoc.write(out, [stepdoc.Part(a, "Pin 4 (M3)", (0.2, 0.4, 0.6)), stepdoc.Part(b, "2nd plate", None)])
    ok(p, f'IMPORT, STEP, "{out}"')
    names = [b.name for b in p.model.bodies.values()]
    assert names == ["Pin_4_M3", "P_2nd_plate"]
    assert p.model.bodies[1].color == pytest.approx((0.2, 0.4, 0.6), abs=2e-3)
    assert p.model.bodies[2].color is None


def test_imported_surface_warns(p, tmp_path):
    path = ff.loose_faces(str(tmp_path))
    res = p.run_script(f'IMPORT, STEP, "{path}"')
    assert res[-1].ok
    text = res[-1].warning or ""
    assert "CHECK, 1, FLAWS" in text and "HEAL, 1" in text


def test_heal_is_kept_in_a_saved_project(p, tmp_path):
    path = ff.gaps(str(tmp_path), gap=0.02)
    ok(p, f'IMPORT, STEP, "{path}", part\nHEAL, part, 0.05')
    proj = str(tmp_path / "healed.m3d")
    ok(p, f'SAVE, "{proj}"')
    os.remove(path)  # the project keeps its own copy of the file
    q = Processor()
    ok(q, f'OPEN, "{proj}"')
    assert q.evaluate("VOL(part)") == pytest.approx(1000, rel=0.01)
    assert q.run("CHECK, part").message.startswith("body 1 'part': OK (1 solid")
