"""Parts and instances: *PART ... *ENDPART, INST, EXPLODE, the part library,
and turning history steps into a part (HIST, PART)."""

import math
import os

import pytest

from modeler.commands import Processor
from modeler.gui import forms as F

BOLT = """*PART, bolt, D=8, L=30, K=0.7*D
  CYL, 0, 0, 0, D, K        ! head
  CYL, 0, 0, -L, D/2, L     ! shank
  UNION, 1, 2
*ENDPART"""


def bolt_volume(d=8, length=30, k=None):
    k = 0.7 * d if k is None else k
    return math.pi * d * d * k + math.pi * (d / 2) ** 2 * length


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
    assert not r.ok
    return r.message


def vol(p, b):
    return p.evaluate(f"VOL({b})")


def test_define_and_place(p):
    r = ok(p, BOLT)
    assert "part bolt(D=8, L=30, K=0.7*D) defined: 1 solid" in r.message
    ok(p, "INST, bolt, 0, 0, 0\nINST, bolt, 30, 0, 0, D=10\nINST, bolt, 0, 40, 0, L=50, K=2")
    assert vol(p, 1) == pytest.approx(bolt_volume())
    assert vol(p, 2) == pytest.approx(bolt_volume(10))  # K follows D: its default uses it
    assert vol(p, 3) == pytest.approx(bolt_volume(8, 50, 2))
    assert p.evaluate("BBOX(2).xmin") == pytest.approx(30 - 10)
    assert "bolt(D=8, L=30, K=0.7*D): 3 instances" in p.run("LIST, PARTS").message
    assert "[instance of bolt (D=10)]" in p.run("LIST, BODIES").message


def test_same_values_build_once(p):
    ok(p, BOLT)
    ok(p, "*DO, i, 1, 8\n  INST, bolt, i*20, 0, 0, D=6\n*ENDDO")
    assert len(p.model.bodies) == 8
    assert len(p.part_cache) == 2  # the trial build with defaults, and D=6


def test_placement_turns_then_moves(p):
    ok(p, BOLT)
    ok(p, "INST, bolt, 100, 0, 0, 90, 0, 1, 0")  # shank turned from -Z to -X, then moved
    assert p.evaluate("BBOX(1).xmin") == pytest.approx(100 - 30)
    assert p.evaluate("BBOX(1).xmax") == pytest.approx(100 + 0.7 * 8)
    ok(p, "PLANE, side, YZ, 50\nWORKPLANE, side\nINST, bolt, 0, 0, 0")
    assert p.evaluate("BBOX(2).xmin") == pytest.approx(50 - 30)  # the shank points into the plane


def test_bad_uses_say_what_to_do(p):
    ok(p, BOLT)
    assert "has no parameter Q (it has D, L, K)" in err(p, "INST, bolt, 0, 0, 0, Q=3")
    assert "no part named 'nut'; parts: bolt" in err(p, "INST, nut, 0, 0, 0")
    assert "BLOCK is a built-in" in err(p, "*PART, block\n  SPHERE, 0,0,0, 1\n*ENDPART")
    msg = err(p, "*PART, plate, T=2\n  BLOCK, 0,0,0, W, 10, T\n*ENDPART")
    assert "a part sees only its own parameters" in msg
    assert "makes no bodies" in err(p, "*PART, empty\n  X = 1\n*ENDPART")
    assert "places itself" in err(p, "*PART, loop, N=2\n  INST, loop, 0,0,0\n*ENDPART")
    ok(p, "*PART, washer, D\n  TUBE, 0,0,0, D, D/2, 1.5\n*ENDPART")  # no default: built when placed
    assert "needs a value for d" in err(p, "INST, washer, 0, 0, 0")
    ok(p, "INST, washer, 0, 0, 0, D=8")


def test_parts_use_parts(p):
    ok(p, BOLT)
    ok(p, "*PART, joint, N=4\n  BLOCK, -20,-20,0, 40, 40, 5\n  *DO, i, 1, N\n"
          "    INST, bolt, 12*cos(90*i), 12*sin(90*i), 5, D=4, L=10\n  *ENDDO\n*ENDPART")
    ok(p, "INST, joint, 0, 0, 0")
    assert len(p.model.bodies) == 1
    assert vol(p, 1) == pytest.approx(40 * 40 * 5 + 4 * bolt_volume(4, 10), rel=1e-6)


def test_editing_the_part_updates_every_instance(p):
    ok(p, BOLT)
    ok(p, "*DO, i, 0, 7\n  INST, bolt, i*25, 0, 0\n*ENDDO")
    new = BOLT.replace("D=8", "D=12")
    r = p.run(f'HIST, EDIT, 1, "{new}"'.replace("\n", "\\n"))
    assert r.ok, r.message
    assert len(p.model.bodies) == 8
    for b in p.model.bodies:
        assert vol(p, b) == pytest.approx(bolt_volume(12))


def test_a_parameter_passed_in_drives_every_instance(p):
    ok(p, "SIZE = 8\n" + BOLT + "\n*DO, i, 0, 7\n  INST, bolt, i*25, 0, 0, D=SIZE\n*ENDDO")
    assert p.run('HIST, EDIT, 1, "SIZE = 6"').ok
    assert {round(vol(p, b), 6) for b in p.model.bodies} == {round(bolt_volume(6), 6)}


def test_move_and_copy_keep_an_instance_but_a_boolean_does_not(p):
    ok(p, BOLT + "\nINST, bolt, 0, 0, 0\nMOVE, 1, 10\nCOPY, 1, 0, 30")
    assert set(p.model.instances) == {1, 2}
    ok(p, "BLOCK, -20, -20, -5, 40, 70, 3\nSUBTRACT, 3, 1, 2")
    assert p.model.instances == {}
    assert "0 instances" in p.run("LIST, PARTS").message


def test_explode(p):
    ok(p, "*PART, pair\n  SPHERE, 0,0,0, 2\n  SPHERE, 10,0,0, 2\n*ENDPART\nINST, pair, 0, 0, 0\nNAME, LAST, pp")
    assert "split into 2 bodies" in ok(p, "EXPLODE, pp").message
    assert sorted(b.name for b in p.model.bodies.values()) == ["pp_1", "pp_2"]
    ok(p, BOLT + "\nINST, bolt, 0, 0, 0")
    bid = p.model.last_body
    assert "now plain geometry" in ok(p, f"EXPLODE, {bid}").message
    assert bid not in p.model.instances
    assert "one solid already" in err(p, f"EXPLODE, {bid}")


def test_undo_forgets_the_part(p):
    ok(p, BOLT)
    ok(p, "UNDO")
    assert "BOLT" not in p.parts
    ok(p, "REDO")
    assert "BOLT" in p.parts


def test_library_round_trip_and_projects(p, tmp_path, monkeypatch):
    monkeypatch.setenv("MODELER_LIBRARY", str(tmp_path / "lib"))
    ok(p, BOLT)
    assert "bolt.cmd" in ok(p, "LIBSAVE, bolt").message
    assert p.history[-1].text.startswith("*PART")  # LIBSAVE is not kept in the history
    q = Processor()
    r = ok(q, "LIB, LOAD, bolt\nINST, bolt, 0, 0, 0, D=10")
    assert q.evaluate("VOL(1)") == pytest.approx(bolt_volume(10))
    assert "no part file 'nope'" in err(q, "LIB, LOAD, nope")
    # a saved project carries the part file, so it opens where there is no library
    proj = tmp_path / "joint.m3d"
    ok(q, f'SAVE, "{proj}"')
    os.remove(tmp_path / "lib" / "bolt.cmd")
    w = Processor()
    assert ok(w, f'OPEN, "{proj}"').ok
    assert w.evaluate("VOL(1)") == pytest.approx(bolt_volume(10))
    del r


def test_a_library_file_holds_only_parts(p, tmp_path):
    f = tmp_path / "mixed.cmd"
    f.write_text("BLOCK, 0,0,0, 1,1,1\n")
    assert "only *PART blocks" in err(p, f'LIB, LOAD, "{f}"')


def test_steps_become_a_part_placed_where_they_were(p):
    ok(p, "T = 6\nW = 40\nBLOCK, 0,0,0, W, 30, T\nNAME, LAST, bracket\nR = 5\n"
          "HOLE, bracket, W/2, 15, T, 2*R\nSPHERE, 100, 0, 0, 3")
    before = vol(p, "bracket")
    r = p.run('HIST, PART, 3, "6, brk"')
    assert r.ok, r.message
    texts = [e.text for e in p.history]
    assert texts[2].startswith("*PART, brk, T=6, W=40, R=5")
    assert texts[3:5] == ["INST, brk, T=T, W=W", "NAME, LAST, bracket"]
    assert vol(p, "bracket") == pytest.approx(before)
    # outside parameters still drive it, and the part places again with other values
    assert p.run('HIST, EDIT, 2, "W = 60"').ok
    assert vol(p, "bracket") == pytest.approx(60 * 30 * 6 - math.pi * 25 * 6)
    ok(p, "INST, brk, 0, 50, 0, W=80, R=10")


def test_steps_that_need_outside_bodies_stay_as_they_are(p):
    ok(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, base\nHOLE, base, 5, 5, 10, 3")
    texts = [e.text for e in p.history]
    msg = err(p, 'HIST, PART, 3, "3, drill"')
    assert "part drill" in msg
    assert [e.text for e in p.history] == texts


def test_place_a_part_form(p):
    ok(p, BOLT)
    sp = F.spec("INST")
    vals = F.initial(p, sp)
    assert vals["part"] == "bolt"
    vals.update(x="10, 0, 0", values="D=10, L=40")
    text, problems = F.check(p, sp, vals)
    assert (text, problems) == ("INST, bolt, 10, 0, 0, D=10, L=40", {})
    ok(p, text)
    sp2, variant, back = F.parse(text)
    assert back["values"] == "D=10, L=40" and back["x"] == "10, 0, 0"
    vals["values"] = "Q=1"
    assert "has no Q" in F.check(p, sp, vals)[1]["values"]
    assert F.build(F.spec("LIB"), {"file": "bolt"}) == 'LIB, LOAD, "bolt"'
    assert F.part_params(p, "bolt") == [("D", "8"), ("L", "30"), ("K", "0.7*D")]


def test_the_bolted_plate_example(p):
    here = os.path.dirname(__file__)
    with open(os.path.join(here, "..", "scripts", "bolted_plate.cmd"), encoding="utf-8") as fh:
        ok(p, fh.read())
    assert "bolt(D=8, L=30, K=0.7*D): 6 instances" in p.run("LIST, PARTS").message
    assert len(p.part_cache) == 2  # one bolt and one washer, each built once
    assert p.run('HIST, EDIT, 2, "N = 8"').ok
    assert "bolt(D=8, L=30, K=0.7*D): 8 instances" in p.run("LIST, PARTS").message
