"""Do parts touch? CONTACT, CLEARANCE, the TOUCH / OVERLAP / CONTACTAREA / GROUPS / CLEARANCE
queries and the assistant's contact, assembly_check and fit_check tools."""

import pytest

from modeler.ai import contact as cx
from modeler.ai.tools import Toolbox
from modeler.commands import Processor

SCENE = """
BLOCK, 0,0,0, 100,100,10
NAME, LAST, plate
CYL, 30,30,-1, 5, 12
SUBTRACT, plate, LAST
CYL, 60,30,-1, 5, 12
SUBTRACT, plate, LAST
BLOCK, 10,60,10, 10,10,20
NAME, LAST, onit
BLOCK, 50,50,5, 10,10,15
NAME, LAST, into
BLOCK, 70,70,12, 10,10,8
NAME, LAST, above
CYL, 10,90,15, 5, 30, 1,0,0
NAME, LAST, roller
SPHERE, 85,20,15, 5
NAME, LAST, ball
CYL, 30,30,-5, 5, 20
NAME, LAST, pin
CYL, 60,30,-5, 4.8, 20
NAME, LAST, loose
"""


@pytest.fixture(scope="module")
def scene():
    p = Processor()
    bad = [r.message for r in p.run_script(SCENE) if not r.ok]
    assert not bad, bad
    return p


def test_touch_on_faces_with_area(scene):
    out = cx.contact(scene, "plate", "onit")
    assert out["state"] == "touch" and out["touch"] == "face"
    assert out["area"] == pytest.approx(100)
    top = scene.model.body_by_name("plate").entity_ids["FACE"]
    assert len(out["faces_a"]) == 1 and out["faces_a"][0] in top


def test_touch_along_a_line_and_at_a_point(scene):
    line = cx.contact(scene, "plate", "roller")
    assert (line["state"], line["touch"]) == ("touch", "line")
    assert line["length"] == pytest.approx(30)
    point = cx.contact(scene, "ball", "plate")
    assert (point["state"], point["touch"]) == ("touch", "point")
    assert point["at"] == pytest.approx([85, 20, 10], abs=1e-4)


def test_gap_with_nearest_points(scene):
    out = cx.contact(scene, "plate", "above")
    assert out["state"] == "apart" and out["gap"] == pytest.approx(2)
    assert out["delta"] == pytest.approx([0, 0, 2])
    assert out["faces_a"] and out["faces_b"]


def test_overlap_volume_and_box(scene):
    out = cx.contact(scene, "plate", "into")
    assert out["state"] == "overlap"
    assert out["volume"] == pytest.approx(500)
    assert out["overlap_box"]["size"] == pytest.approx([10, 10, 5])
    assert out["fraction_of_smaller"] == pytest.approx(1 / 3, abs=1e-3)


def test_buried_body_is_an_overlap():
    p = Processor()
    assert p.run("BLOCK, 0,0,0, 10,10,10\nNAME, LAST, big\nBLOCK, 4,4,4, 2,2,2\nNAME, LAST, small").ok
    out = cx.contact(p, "big", "small")
    assert out["state"] == "overlap" and out["volume"] == pytest.approx(8)
    assert out["fraction_of_smaller"] == pytest.approx(1)


def test_pin_in_own_size_hole_touches_all_round(scene):
    out = cx.contact(scene, "plate", "pin")
    assert out["touch"] == "face" and out["area"] == pytest.approx(2 * 3.14159265 * 5 * 10, rel=1e-6)


def test_assembly_groups_floating_and_near(scene):
    out = cx.assembly(scene, near=3)
    plate = scene.model.body_by_name("plate").id
    above, loose = scene.model.body_by_name("above").id, scene.model.body_by_name("loose").id
    assert len(out["overlaps"]) == 1 and len(out["touching"]) == 4
    assert sorted(out["floating"]) == sorted([above, loose])
    assert plate in out["groups"][0] and len(out["groups"]) == 3
    assert sorted(r["gap"] for r in out["near"]) == pytest.approx([0.2, 2])
    one = cx.assembly(scene, against="ball")
    assert len(one["touching"]) == 1 and "groups" not in one


def test_fit_clearance_line_to_line_and_interference(scene):
    loose = cx.fit(scene, "loose", "plate")["fits"]
    assert len(loose) == 1 and loose[0]["state"] == "clearance"
    assert loose[0]["clearance"] == pytest.approx(0.4) and loose[0]["engaged"] == pytest.approx(10)
    assert cx.fit(scene, "plate", "pin")["fits"][0]["state"] == "line to line"
    p = Processor()
    assert p.run("BLOCK, 0,0,0, 20,20,5\nNAME, LAST, bush\nCYL, 10,10,-1, 3, 7\nSUBTRACT, bush, LAST\n"
                 "CYL, 10.5,10,-3, 3.1, 10\nNAME, LAST, shaft").ok
    f = cx.fit(p, "shaft", "bush")["fits"][0]
    assert f["state"] == "interference" and f["clearance"] == pytest.approx(-0.2)
    assert f["axis_offset"] == pytest.approx(0.5) and f["tightest_gap"] == pytest.approx(-0.6)
    assert cx.fit(scene, "onit", "plate")["fits"] == []


def test_commands_and_queries(scene):
    assert "touch on faces, area 100" in scene.run("CONTACT, plate, onit").message
    assert "OVERLAP: 500" in scene.run("CONTACT, plate, into").message
    whole = scene.run("CONTACT").message
    assert "3 groups" in whole and "touching nothing" in whole
    assert "clearance 0.4" in scene.run("CLEARANCE, loose, plate").message
    for text in ("ASSERT, TOUCH(plate, onit)", "ASSERT, OVERLAP(plate, into), EQ, 500, 1e-6",
                 "ASSERT, CONTACTAREA(plate, onit), EQ, 100, 1e-6", "ASSERT, GROUPS(), EQ, 3",
                 "ASSERT, CLEARANCE(loose, plate), EQ, 0.2, 1e-6", "ASSERT, OVERLAP(plate, onit), EQ, 0"):
        r = scene.run(text)
        assert r.ok, (text, r.message)
    assert not scene.run("ASSERT, TOUCH(plate, above)").ok
    assert not scene.run("CONTACT, plate, plate").ok


def test_tools(scene):
    box = Toolbox(scene)
    assert {"contact", "assembly_check", "fit_check"} <= set(box.tools)
    assert box.call("contact", {"a": "plate", "b": "onit"})["touch"] == "face"
    assert box.call("assembly_check", {"near": 0.5})["summary"].startswith("pairs: 1 overlapping, 4 touching")
    assert box.call("fit_check", {"a": "loose", "b": "plate"})["fits"][0]["state"] == "clearance"
    assert "error" in box.call("contact", {"a": "plate", "b": "nothing"})


def test_bolted_plate_example_holds_together():
    from pathlib import Path

    p = Processor()
    p.run_script((Path(__file__).resolve().parent.parent / "scripts" / "bolted_plate.cmd").read_text())
    out = cx.assembly(p, near=0.5)
    assert not out["overlaps"] and len(out["groups"]) == 1 and not out["floating"]
    assert len(out["near"]) == 6  # each bolt's shank is 0.25 clear of its hole


def test_threaded_bolt_in_nut_is_a_thread_not_a_fit():
    from pathlib import Path

    p = Processor()
    p.run_script((Path(__file__).resolve().parent.parent / "scripts" / "threaded_bolts.cmd").read_text())
    bolt, nut = sorted(p.model.bodies)[:2]
    rows = cx.fit(p, bolt, nut)["fits"]
    assert [r["state"] for r in rows] == ["thread"] and "note" in rows[0]
    plain = cx.fit(p, bolt, "plate")["fits"]  # the threaded bolt in its plain 9 mm hole
    assert [r["state"] for r in plain] == ["clearance"] and plain[0]["per_side"] == pytest.approx(0.5)
