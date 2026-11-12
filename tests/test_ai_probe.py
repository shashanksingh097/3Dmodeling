"""Seeing without pictures (docs/M9-ai-tools.md, step M9b): PROBE, PROFILE,
THICK and MINWALL, and the vary and round_trip experiments."""

from pathlib import Path

import pytest

from modeler.ai import experiments as ex
from modeler.ai import probe as pb
from modeler.ai.tools import Toolbox
from modeler.commands import Processor
from modeler.commands.feature_handlers import plane_ref

FLANGE = (Path(__file__).resolve().parent.parent / "scripts" / "flange.cmd").read_text()


@pytest.fixture(scope="module")
def flange():
    p = Processor()
    bad = [r.message for r in p.run_script(FLANGE) if not r.ok]
    assert not bad, bad
    return p


@pytest.fixture
def p():
    return Processor()


def ok(p, text):
    rs = p.run_script(text)
    bad = [r.message for r in rs if not r.ok]
    assert not bad, bad
    return rs[-1].message if rs else ""


def test_ray_through_walls_and_holes(flange):
    out = pb.probe_ray(flange, (-50, 0, 5), (1, 0, 0))
    assert [(s["from"], s["to"]) for s in out["material"]] == [(10, 16), (24, 38), (62, 76), (84, 90)]
    assert [("enters" in h) for h in out["hits"]] == [True, False] * 4
    assert pb.probe_ray(flange, (0, 0, -5), (0, 0, 1))["hits"] == []  # straight up the bore
    down = pb.probe_ray(flange, (35, 0, 50), (0, 0, -1))
    assert down["material"] == [{"body": down["material"][0]["body"], "from": 40.0, "to": 50.0, "length": 10.0}]
    inside = pb.probe_ray(flange, (37, 0, 5), (1, 0, 0))  # starting in material
    assert inside["material"][0]["from"] == 0.0 and inside["material"][0]["to"] == 3.0


def test_points_inside_on_outside(flange):
    rows = pb.probe_point(flange, [(37, 0, 5), (30, 0, 5), (40, 0, 5), (0, 0, 100)])["points"]
    assert [r["state"] for r in rows] == ["inside", "outside", "on", "outside"]
    assert rows[0]["distance"] == 3.0 and rows[1]["distance"] == 4.0
    hole_wall = rows[1]["face"]
    assert pb.probe_point(flange, [(34, 0, 5)])["points"][0]["face"] == hole_wall


def test_section_profile_reads_like_a_drawing(flange):
    out = pb.section_profile(flange, "flange", plane_ref(flange, "XY", "t"), [5, 25])
    low, high = out["cuts"]
    assert low["loops"] == [
        {"outer": True, "circle": {"c": [0.0, 0.0], "r": 40.0}},
        {"outer": False, "circles": {"n": 6, "r": 4.0, "on": {"c": [0.0, 0.0], "r": 30.0, "step_deg": 60.0}}},
        {"outer": False, "circle": {"c": [0.0, 0.0], "r": 12.0}},
    ]
    assert high["area"] == pytest.approx(804.248, abs=1e-3)
    side = pb.section_profile(flange, "flange", plane_ref(flange, "ZX", "t"))
    kinds = sorted(next(iter(k for k in lp if k != "outer")) for lp in side["loops"])
    assert kinds == ["rect", "rect", "segments", "segments"]  # two rims, two halves of the hub
    arcs = [s for lp in side["loops"] if "segments" in lp for s in lp["segments"] if "arc" in s]
    assert {a["arc"]["r"] for a in arcs} == {3.0}  # the fillet


def test_a_cut_on_a_flat_face_says_so(flange):
    out = pb.section_profile(flange, "flange", plane_ref(flange, "XY", "t"), [10])
    cut = out["cuts"][0]
    assert "flat face" in cut["note"] and len(cut["loops"]) == 3


def test_profile_and_probe_commands(flange):
    text = flange.run("PROFILE, flange, XY, 5").message
    assert "hole: circles n 6 r 4 on c (0, 0) r 30 step_deg 60" in text
    assert "material of body" in flange.run("PROBE, RAY, (35,0,50), (0,0,-1)").message
    assert flange.run("PROBE, POINT, 37, 0, 5").message.startswith("(37, 0, 5): inside body")
    assert "stack of cuts needs a step" in flange.run("PROFILE, flange, XY, 0, 0, 3").message


def test_wall_thickness_of_a_shelled_box(p):
    ok(p, "BLOCK, 0,0,0, 40,30,20\nNAME, LAST, box\nSEL, S, FACE, LOC, Z, 20\nSHELL, 2")
    out = pb.wall_thickness(p, "box")
    assert out["min"] == 2.0 and len(out["thinnest"]) == 5
    assert p.evaluate("MINWALL(box)") == pytest.approx(2)
    ok(p, "ASSERT, MINWALL(box), GE, 1.99")
    assert "thinnest wall 2" in p.run("THICK, box").message
    assert "no wall thinner than 1" in p.run("THICK, box, 1").message


def test_flange_walls(flange):
    assert flange.evaluate("MINWALL(flange)") == pytest.approx(6)  # bolt hole to the rim


def test_vary_finds_values_that_break_the_model(flange):
    out = ex.vary(flange, "N_BOLTS", [3, 8], ["HOLES(flange, D_BOLT), EQ, N_BOLTS"])
    assert out["all_ok"], out
    out = ex.vary(flange, "D_BOLT", [30])
    bad = out["results"][0]
    assert not bad["ok"] and any("CHAMFER" in f["text"] for f in bad["failed"])
    assert flange.evaluate("N_BOLTS") == 6 and flange.evaluate("HOLES(flange)") == 7  # untouched


def test_round_trip_brings_every_id_back(flange):
    out = ex.round_trip(flange, [{"param": "N_BOLTS", "value": 8}, {"param": "D_HUB", "value": 50}])
    assert out["ok"], out


def test_round_trip_reports_a_lost_pick(p):
    ok(p, "W = 40\nBLOCK, 0,0,0, W, 20, 10\nPICK, FACE, 6\nCM, top, FACE")
    out = ex.round_trip(p, [{"entry": 2, "text": "CYL, 0,0,0, 10, 10"}])
    # the face that was picked does not exist on a cylinder: the edit fails there
    assert out["during"][0]["failed"]
    assert out["ok"]  # ... and everything is back after editing it back


def test_tools_for_probing(flange):
    box = Toolbox(flange)
    assert box.call("probe_ray", {"origin": [35, 0, 50], "dir": [0, 0, -1]})["material"][0]["length"] == 10
    assert box.call("section_profile", {"body": "flange", "plane": "XY"})["area"] > 0
    assert "error" in box.call("section_profile", {"body": "flange", "plane": "nope"})
    assert box.call("wall_thickness", {"body": "flange", "limit": 1})["min"] == 6
    assert box.call("vary", {"param": "N_BOLTS", "values": [4]})["all_ok"]
    assert box.call("round_trip", {"edits": [{"param": "N_BOLTS", "value": 5}]})["ok"]
