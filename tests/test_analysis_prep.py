"""Getting parts ready for analysis (PLAN items 80-82): MIDSURFACE, BEAMS, FLUIDVOLUME, ENCLOSURE,
SHAREFACES, IMPRINT, MERGEFACES."""

import math

import pytest

from modeler.commands.processor import Processor
from modeler.core.model import Model


def run(p, text):
    out = []
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
        out.append(r)
    last = out[-1]
    name = last.line.split(",")[0].strip().upper()
    last.report = p.reports.get(name)  # the newest answer of that command, as data
    return last


@pytest.fixture
def p():
    return Processor(Model())


def body(p, name):
    return p.model.body_by_name(name)


def area(p, b):
    return p.evaluate(f'AREA({b.id}, "BODY")')


BRACKET = """BLOCK, 0,0,0, 100,50,2
NAME, LAST, bracket
BLOCK, 0,0,0, 2,50,40
UNION, bracket, LAST"""


def test_midsurface_of_a_bent_bracket_meets_at_the_corner(p, tmp_path):
    run(p, BRACKET)
    r = run(p, "MIDSURFACE, bracket")
    mid = body(p, "bracket_mid")
    assert "walls meet" in r.message and r.report["joined"] and r.report["thickness"] == 2
    assert area(p, mid) == pytest.approx(99 * 50 + 39 * 50, rel=1e-6)
    assert set(p.model.thickness[mid.id].values()) == {2}
    assert len(r.report["rims"]) == 4 and not r.report["left_out"]
    f = tmp_path / "mid.step"
    run(p, f'EXPORT, STEP, "{f}", bracket_mid')
    assert f.read_text().count("'thickness 2'") == 2


def test_midsurface_of_a_stepped_plate_and_a_tube(p):
    run(p, """BLOCK, 0,0,0, 50,50,2
NAME, LAST, step
BLOCK, 50,0,0, 50,50,4
UNION, step, LAST
CYL, 200,0,0, 10, 80
NAME, LAST, tube
CYL, 200,0,0, 8, 80
SUBTRACT, tube, LAST""")
    r = run(p, "MIDSURFACE, step")
    assert sorted(r.report["thickness"]) == [2, 4] and not r.report["joined"]
    assert sorted(x["thickness"] for x in r.report["faces"]) == [2, 2, 4]  # the step strip is 2
    assert r.report["gaps_closed"] == 1 and "1 gap closed" in r.message
    assert area(p, body(p, "step_mid")) == pytest.approx(2 * 2500 + 50)
    assert r.report["free_edges"] == 8  # the outline only: the two levels and the step are one sheet
    r = run(p, "MIDSURFACE, tube")
    assert area(p, body(p, "tube_mid")) == pytest.approx(2 * math.pi * 9 * 80, rel=1e-6)


def test_midsurface_joins_walls_of_two_thicknesses(p):
    run(p, """BLOCK, 0,0,0, 100,50,3
NAME, LAST, ell
BLOCK, 0,0,0, 5,50,40
UNION, ell, LAST
BLOCK, 0,100,0, 100,50,4
NAME, LAST, tee
BLOCK, 48,100,4, 3,50,30
UNION, tee, LAST""")
    r = run(p, "MIDSURFACE, ell")  # the middles cross near the corner: the ends past it are cut off
    assert area(p, body(p, "ell_mid")) == pytest.approx(97.5 * 50 + 38.5 * 50)
    assert r.report["free_edges"] == 6
    r = run(p, "MIDSURFACE, tee")  # the plate's two halves and the rib carried on to one line
    assert area(p, body(p, "tee_mid")) == pytest.approx(100 * 50 + 32 * 50)
    assert r.report["gaps_closed"] == 3 and r.report["free_edges"] == 15
    ts = sorted(x["thickness"] for x in r.report["faces"])
    assert ts.count(3) == 2 and ts.count(4) == 4


def test_midsurface_refuses_a_block(p):
    run(p, "BLOCK, 0,0,0, 10,10,10")
    r = p.run("MIDSURFACE, 1")
    assert not r.ok and "no thin walls" in r.message


def test_beams_of_a_frame(p):
    run(p, """POLYLINE, (0,0,0), (400,0,0), (400,0,300), (0,0,300)
NAME, LAST, path
MEMBER, path, SQUARE, 40x3""")
    r = run(p, 'BEAMS, "member_1 member_2 member_3"')
    d = r.report
    assert len(d["beams"]) == 3 and len(d["joints"]) == 2 and d["free_ends"] == 2
    b = d["beams"][0]
    assert b["profile"] == "SQUARE" and b["area"] == pytest.approx(40 ** 2 - 34 ** 2)
    assert b["iy"] == pytest.approx((40 ** 4 - 34 ** 4) / 12, rel=1e-6)
    assert b["j"] == pytest.approx(4 * 37 ** 4 * 3 / 148, rel=0.03)  # thin wall
    lines = body(p, "beams")
    assert len(lines.entity_ids["EDGE"]) == 3 and len(lines.entity_ids["VERTEX"]) == 4  # joined


def test_beam_of_a_plain_rod_without_a_member_record(p):
    run(p, "CYL, 0,0,0, 5, 100")
    b = run(p, "BEAMS, 1").report["beams"][0]
    assert b["length"] == pytest.approx(100) and b["j"] == pytest.approx(math.pi / 2 * 5 ** 4, rel=1e-6)
    assert abs(b["p1"][2] - b["p0"][2]) == pytest.approx(100)


def test_fluid_volume_of_a_tee_and_a_closed_housing(p):
    run(p, """CYL, 0,0,0, 12, 100
NAME, LAST, tee
CYL, 0,0,50, 12, 50, 1,0,0
UNION, tee, LAST
CYL, 0,0,0, 10, 100
SUBTRACT, tee, LAST
CYL, 0,0,50, 10, 50, 1,0,0
SUBTRACT, tee, LAST""")
    r = run(p, "FLUIDVOLUME, tee")
    d = r.report
    assert len(d["openings"]) == 3 and len(d["volumes"]) == 1
    assert len(d["volumes"][0]["openings"]) == 3
    fluid = body(p, "tee_fluid")
    assert p.evaluate(f"VOL({fluid.id})") == pytest.approx(d["volumes"][0]["volume"])
    assert 31416 + 12566 < d["volumes"][0]["volume"] < 31416 + 12566 + 1500
    run(p, """BLOCK, 200,0,0, 50,50,50
NAME, LAST, box
BLOCK, 205,5,5, 40,40,40
SUBTRACT, box, LAST""")
    r = run(p, "FLUIDVOLUME, box")
    assert not r.report["openings"] and r.report["volumes"][0]["volume"] == pytest.approx(64000)


def test_fluid_volume_with_picked_end_faces(p):
    run(p, """CYL, 0,0,0, 10, 80
NAME, LAST, pipe
CYL, 0,0,0, 8, 80
SUBTRACT, pipe, LAST
SEL, S, FACE, NORMAL, 0,0,1""")
    r = p.run("FLUIDVOLUME, pipe, SEL")  # one end closed: the inside still reaches the outside
    assert not r.ok and "pick the end faces" in r.message
    run(p, "SEL, A, FACE, NORMAL, 0,0,-1")
    r = run(p, "FLUIDVOLUME, pipe, SEL")
    assert len(r.report["openings"]) == 2
    assert r.report["volumes"][0]["volume"] == pytest.approx(math.pi * 64 * 80, rel=1e-6)


def test_enclosure_box_names_its_faces(p):
    run(p, "BLOCK, 0,0,0, 30,20,10\nNAME, LAST, part")
    d = run(p, 'ENCLOSURE, part, BOX, "20 60 20 20 0 20"').report
    assert d["volume"] == pytest.approx(110 * 60 * 30 - 30 * 20 * 10)
    assert set(d["faces"]) == {"XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX", "WALLS"}
    assert len(d["faces"]["WALLS"]) == 5  # the bottom sits on ZMIN
    d = run(p, "ENCLOSURE, part, SPHERE, 5").report
    assert set(d["faces"]) == {"OUTER", "WALLS"}
    assert body(p, "enclosure_2") is not None


def test_sharefaces_check_then_share(p):
    run(p, "BLOCK, 0,0,0, 20,20,20\nBLOCK, 20,5,5, 10,10,10\nBLOCK, 100,0,0, 5,5,5")
    d = run(p, "SHAREFACES, ALL, CHECK").report
    assert d["apart"] == 1 and d["pairs"][0]["touching"] == pytest.approx(100)
    n = len(p.model.history) if hasattr(p.model, "history") else None
    r = run(p, "SHAREFACES, ALL")
    assert "1 touching pair" in r.message and r.report["new_faces"][1] == 1
    d = run(p, "SHAREFACES, ALL, CHECK").report
    assert d["apart"] == 0 and d["pairs"][0]["shared"] == pytest.approx(100)
    del n


def test_imprint_and_mergefaces(p):
    run(p, """BLOCK, 0,0,0, 60,40,5
NAME, LAST, plate
BLOCK, 20,10,5, 20,20,10
NAME, LAST, pad""")
    r = run(p, "IMPRINT, plate, pad")
    assert r.report["area"] == pytest.approx(400) and len(r.report["faces"]) == 1
    assert len(body(p, "plate").entity_ids["FACE"]) == 7
    assert p.evaluate(f'AREA({r.report["faces"][0]})') == pytest.approx(400)
    r = run(p, "MERGEFACES, plate")
    assert r.report["joined"] == 1 and len(body(p, "plate").entity_ids["FACE"]) == 6


def test_mergefaces_removes_slivers(p):
    run(p, """BLOCK, 0,0,0, 50,40,20
NAME, LAST, part
BLOCK, 0,0,20, 50.05,40,0.05
UNION, part, LAST""")
    r = run(p, "MERGEFACES, part, SMALL, 0.2")
    assert r.report["removed"] == 2 and not r.report["left"]
    assert p.evaluate("VALID(part)")
    r = run(p, "MERGEFACES, part")
    assert "nothing to merge" in r.message


def test_menu_offers_middle_surface_only_for_walls(p):
    from modeler.gui import body_menu as bm

    run(p, BRACKET)
    run(p, "BLOCK, 200,0,0, 30,30,30\nNAME, LAST, cube")
    labels = lambda b: [i.label for i in bm.analysis_items(p.model, [b], b)]  # noqa: E731
    assert "Analysis: middle surface" in labels(body(p, "bracket").id)
    cube = labels(body(p, "cube").id)
    assert "Analysis: middle surface" not in cube and "Analysis: merge faces on one surface" in cube


LAP = """BLOCK, 0,0,0, 100,40,2
NAME, LAST, lower
BLOCK, 0,20,2, 100,40,2
NAME, LAST, upper"""


def _edge_at(p, name, x, y, z):
    from modeler.commands.queries import centre

    b = body(p, name)
    for g in b.entity_ids["EDGE"]:
        c = centre("EDGE", p.model.entity_shape("EDGE", g))
        if max(abs(c[0] - x), abs(c[1] - y), abs(c[2] - z)) < 1e-6:
            return g
    raise AssertionError("no such edge")


def test_spot_places_are_centred_on_the_edge():
    from modeler.geometry import analysis_prep as ap

    assert ap.spot_places(100, 25, 12.5) == [12.5, 37.5, 62.5, 87.5]
    assert ap.spot_places(100, 30, 10) == [20, 50, 80]  # a fourth would come within 10 of an end
    assert ap.spot_places(10, 25, 5) == [5]  # one in the middle of a short edge
    with pytest.raises(ap.PrepError):
        ap.spot_places(10, 25, 6)


def test_spotweld_along_a_lap(p, tmp_path):
    run(p, LAP)
    e = _edge_at(p, "upper", 50, 20, 2)
    r = run(p, f"SPOTWELD, upper, lower, {e}, 25")
    d = r.report
    assert d["count"] == 4 and "4 welds joining upper and lower" in r.message
    assert [w["at"] for w in d["welds"]] == [[12.5, 20, 2], [37.5, 20, 2], [62.5, 20, 2], [87.5, 20, 2]]
    pts = body(p, "spotwelds")
    assert len(pts.entity_ids["VERTEX"]) == 4 and p.model.named_set("spotwelds")[1] == pts.entity_ids["VERTEX"]
    f = tmp_path / "welds.step"
    run(p, f'EXPORT, STEP, "{f}"')
    text = f.read_text()
    assert text.count("spot weld ") == 4 and "'spotwelds; spot weld 2; joins upper + lower; nugget 5'" in text
    # the far edge of the upper plate is not over the lower one
    far = _edge_at(p, "upper", 50, 60, 2)
    bad = p.run(f"SPOTWELD, upper, lower, {far}, 25")
    assert not bad.ok and "not close" in bad.message
    assert p.run("UNDO").ok and not p.model.spotwelds


def test_spotweld_from_the_edge_menu_and_form(p):
    from modeler.gui import body_menu as bm
    from modeler.gui import forms

    run(p, LAP)
    e = _edge_at(p, "upper", 50, 20, 2)
    p.model.select("EDGE", [e])
    items = [i for i in bm.pick_tools(p) if i.form == "SPOTWELD"]
    assert items and items[0].label == "Spot welds along it to lower (body 1)…"
    assert items[0].commands == [f"SPOTWELD, 2, 1, {e}, 25"]
    sp = forms.spec("SPOTWELD")
    assert [f.key for f in sp.variants[0].fields][:4] == ["a", "b", "edge", "pitch"]
    vals = forms.initial(p, sp)
    assert vals["a"] == "upper" and vals["b"] == "lower" and vals["edge"] == str(e)
