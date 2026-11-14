"""Placement, design rules and same shape: RELATE, DESIGNCHECK, COMPARE, the
SAMESHAPE and PROBLEMS queries and the placement, check_design and
compare_bodies tools."""

import pytest

from modeler.ai import relate as rl
from modeler.ai.tools import Toolbox
from modeler.commands import Processor

SCENE = """
BLOCK, 0,0,0, 40,40,20
NAME, LAST, box
BLOCK, 5,5,20, 30,30,4
NAME, LAST, lid
BLOCK, 100,0,0, 40,40,20
NAME, LAST, box2
CYL, 20,20,24, 3, 10
NAME, LAST, knob
BLOCK, 0,60,0, 20,10,10
NAME, LAST, ell
BLOCK, 0,60,10, 5,10,10
UNION, ell, LAST
MIRROR, ell, 50,0,0
NAME, LAST, mirrored
BLOCK, 0,100,0, 10,10,0.0005
NAME, LAST, thin
"""


@pytest.fixture(scope="module")
def scene():
    p = Processor()
    bad = [r.message for r in p.run_script(SCENE) if not r.ok]
    assert not bad, bad
    return p


def test_lid_rests_centred_on_box(scene):
    out = rl.placement(scene, "lid", "box")
    assert out["axes"]["Z"] == {"a_is": "on the + side", "gap": 0}
    assert out["axes"]["X"]["a_is"] == "within" and out["centred_on"] == ["X", "Y"]
    assert out["contact"] == "touch (face)" and out["rests"][0].startswith("a rests on top of b")
    knob = rl.placement(scene, "knob", "lid")
    assert knob["centre_offset"][:2] == pytest.approx([0, 0])


def test_side_by_side_gap_and_flush_faces(scene):
    out = rl.placement(scene, "box2", "box")
    assert out["axes"]["X"] == {"a_is": "on the + side", "gap": 60}
    assert out["contact"] == "apart" and len(out["flush"]) == 4  # top, bottom, front, back in line


def test_compare_moved_copy_mirror_and_different(scene):
    moved = rl.compare(scene, "box", "box2")
    assert moved["same"] and moved["how"] == "moved copy" and moved["move"] == pytest.approx([100, 0, 0])
    mir = rl.compare(scene, "ell", "mirrored")
    assert mir["same"] and mir["how"] == "mirror image" and mir["mirror_normal"] == "X"
    assert mir["plane_at"] == pytest.approx(50)
    diff = rl.compare(scene, "box", "lid")
    assert not diff["same"] and diff["differs"]["volume"]["b_minus_a"] == pytest.approx(3600 - 32000)


def test_design_check(scene):
    assert rl.design_check(scene, "box")["ok"]
    thin = rl.design_check(scene, "thin")
    assert {pr["rule"] for pr in thin["problems"]} == {"small_edges", "slivers"}
    walls = rl.design_check(scene, "box", min_wall=25)
    assert [pr["rule"] for pr in walls["problems"]] == ["min_wall"]


def test_design_check_loose_pieces():
    p = Processor()
    assert p.run("BLOCK, 0,0,0, 1,1,1\nNAME, LAST, a\nBLOCK, 5,0,0, 1,1,1\nUNION, a, LAST").ok
    out = rl.design_check(p, "a")
    assert "pieces" in {pr["rule"] for pr in out["problems"]}


def test_commands_queries_and_tools(scene):
    assert "a rests on top of b" in scene.run("RELATE, lid, box").message
    assert "mirror images across the plane x = 50" in scene.run("COMPARE, ell, mirrored").message
    assert "no problems" in scene.run("DESIGNCHECK, box").message
    assert "2 problems" in scene.run("DESIGNCHECK, thin").message
    for text in ("ASSERT, SAMESHAPE(box, box2)", "ASSERT, PROBLEMS(box), EQ, 0", "ASSERT, PROBLEMS(thin), EQ, 2"):
        r = scene.run(text)
        assert r.ok, (text, r.message)
    assert not scene.run("ASSERT, SAMESHAPE(box, lid)").ok
    box = Toolbox(scene)
    assert box.call("placement", {"a": "lid", "b": "box"})["centred_on"] == ["X", "Y"]
    assert box.call("check_design", {"body": "box"})["ok"] is True
    assert box.call("compare_bodies", {"a": "box", "b": "box2"})["how"] == "moved copy"
