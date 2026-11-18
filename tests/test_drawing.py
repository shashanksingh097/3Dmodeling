"""DRAWING (2D drawings to SVG and DXF), and the drawing math on its own."""

import math
import xml.etree.ElementTree as ET

import pytest

from modeler.commands import Processor
from modeler.geometry import drawing as dr


@pytest.fixture
def p():
    p = Processor()
    rs = p.run_script("BLOCK, 0, 0, 0, 40, 20, 10\nCYL, 20, 10, 0, 5, 10\nSUBTRACT, 1, 2")
    assert all(r.ok for r in rs), [r.message for r in rs if not r.ok]
    return p


def dxf_pairs(text):
    lines = text.splitlines()
    return [(int(lines[i]), lines[i + 1]) for i in range(0, len(lines) - 1, 2)]


def test_standard_sheet_as_svg(p, tmp_path):
    f = tmp_path / "block.svg"
    r = p.run(f'DRAWING, "{f}"')
    assert r.ok, r.message
    assert "front, top, right, iso views" in r.message
    root = ET.parse(f).getroot()
    assert root.get("width").endswith("mm")
    groups = {g.get("id") for g in root.iter("{http://www.w3.org/2000/svg}g")}
    assert groups == {"front", "top", "right", "iso", "front-dims", "top-dims"}
    # the hole is hidden in the front view: a dashed path there
    front = next(g for g in root.iter("{http://www.w3.org/2000/svg}g") if g.get("id") == "front")
    assert any(pth.get("stroke-dasharray") for pth in front.iter("{http://www.w3.org/2000/svg}path"))
    assert not p.history or all("DRAWING" not in e.text for e in p.history)  # not kept in the history


def test_views_are_true_size_and_placed_third_angle(p):
    shape = p.model.bodies[3].shape
    front = dr.project(shape, "FRONT", 0.01)
    top = dr.project(shape, "TOP", 0.01)
    right = dr.project(shape, "RIGHT", 0.01)
    x0, y0, x1, y1 = front.bounds()
    assert (x1 - x0, y1 - y0) == pytest.approx((40, 10))
    x0, y0, x1, y1 = top.bounds()
    assert (x1 - x0, y1 - y0) == pytest.approx((40, 20))
    x0, y0, x1, y1 = right.bounds()
    assert (x1 - x0, y1 - y0) == pytest.approx((20, 10))
    circles = [pl for pl in top.visible if len(pl) > 2]
    assert circles  # the hole, seen from above
    dr.layout([front, top, right])
    fb = [b + d for b, d in zip(front.bounds(), (front.dx, front.dy) * 2)]
    tb = [b + d for b, d in zip(top.bounds(), (top.dx, top.dy) * 2)]
    rb = [b + d for b, d in zip(right.bounds(), (right.dx, right.dy) * 2)]
    assert tb[0] == pytest.approx(fb[0]) and tb[1] > fb[3]  # top above front, lined up
    assert rb[1] == pytest.approx(fb[1]) and rb[0] > fb[2]  # right beside front, same height


def test_dxf_has_layers_and_true_size_lines(p, tmp_path):
    f = tmp_path / "block.dxf"
    r = p.run(f'DRAWING, "{f}", TOP+FRONT')
    assert r.ok, r.message
    pairs = dxf_pairs(f.read_text())
    assert pairs[0] == (0, "SECTION") and pairs[-1] == (0, "EOF")
    layers = [v for i, (c, v) in enumerate(pairs) if c == 2 and pairs[i - 1] == (0, "LAYER")]
    assert layers == ["VISIBLE", "HIDDEN", "TEXT", "DIMS"]
    ents = [v for c, v in pairs if c == 0]
    assert ents.count("LINE") >= 8 and "POLYLINE" in ents
    # two view names, then the sizes: 40 and 10 on the front, 20 and the hole on the top
    texts = []
    for i, q in enumerate(pairs):
        if q == (0, "TEXT"):
            j = i + 1
            while pairs[j][0] != 0:
                j += 1
            texts.append(dict(pairs[i + 1:j]))
    assert [t[1] for t in texts if t[8] == "TEXT"] == ["TOP", "FRONT"]
    assert sorted(t[1] for t in texts if t[8] == "DIMS") == sorted(["40", "10", "20", "%%c10"])
    assert ents.count("SOLID") == 7  # arrows: two per size, one per diameter
    # the longest line is the block's 40 long edge
    lines, i = [], 0
    while i < len(pairs):
        if pairs[i] == (0, "LINE"):
            d = dict(pairs[i + 1:i + 9])
            lines.append(((float(d[10]), float(d[20])), (float(d[11]), float(d[21]))))
        i += 1
    import math

    assert max(math.dist(a, b) for a, b in lines) == pytest.approx(40)
    assert ("$INSUNITS" in f.read_text())


def test_one_body_a_mesh_body_and_errors(p, tmp_path):
    ok = p.run("SPHERE, 100, 0, 0, 10")
    assert ok.ok
    r = p.run(f'DRAWING, "{tmp_path / "s.svg"}", ISO, 4')
    assert r.ok and "1 body" in r.message
    assert p.run("TOMESH, 4").ok
    r = p.run(f'DRAWING, "{tmp_path / "m.dxf"}", FRONT, 4')
    assert r.ok, r.message
    assert "must end in .svg or .dxf" in p.run(f'DRAWING, "{tmp_path / "a.pdf"}"').message
    assert "unknown view SIDE" in p.run(f'DRAWING, "{tmp_path / "a.svg"}", SIDE').message


def test_sizes_overall_and_diameters(p, tmp_path):
    f = tmp_path / "sized.svg"
    r = p.run(f'DRAWING, "{f}"')
    assert r.ok and "4 sizes" in r.message, r.message
    root = ET.parse(f).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    dims = {g.get("id"): [t.text for t in g.iter(ns + "text")] for g in root.iter(ns + "g")
            if g.get("class") == "dims"}
    # width and height on the front view, depth and the hole on the top; nothing on right or iso
    assert dims == {"front-dims": ["40", "10"], "top-dims": ["20", "\u00d810"]}
    # the sizes fit on the sheet
    w, h = (float(x) for x in root.get("viewBox").split()[2:])
    for g in root.iter(ns + "g"):
        for t in g.iter(ns + "text"):
            assert 0 <= float(t.get("x")) <= w and 0 <= float(t.get("y")) <= h
    assert "0 sizes" in p.run(f'DRAWING, "{f}", FRONT, 0, NONE').message
    assert "1 size," in p.run(f'DRAWING, "{f}", TOP, 0, HOLES').message
    assert "unknown sizes BIG" in p.run(f'DRAWING, "{f}", TOP, 0, BIG').message


def test_equal_holes_counted_and_sizes_exact(tmp_path):
    p = Processor()
    script = ["CYL, 0, 0, 0, 40, 10", "CYL, 0, 0, 0, 12, 10", "SUBTRACT, 1, 2"]
    body = 3
    for i, (x, y) in enumerate([(30, 0), (-30, 0), (0, 30), (0, -30)]):
        script += [f"CYL, {x}, {y}, 0, 4, 10", f"SUBTRACT, {body}, LAST"]
        body += 2
    assert all(r.ok for r in p.run_script("\n".join(script)))
    views = [dr.project(p.model.bodies[body].shape, n, 0.05) for n in ("FRONT", "TOP")]
    n = dr.dimension(views, "ALL", {"X": 80.0, "Y": 80.0, "Z": 10.0})
    texts = [t[2] for v in views for t in v.dims.texts]
    assert n == 6
    assert texts[:3] == ["80", "10", "80"]  # exact, though the circle is drawn as short lines
    assert sorted(texts[3:]) == sorted(["\u00d880", "\u00d824", "4x \u00d88"])
    # each size of circle has its leader at its own angle
    lead = [ln[0] for ln in views[1].dims.lines[3:] if ln is not None][::2]
    angles = {round(math.degrees(math.atan2(y, x))) for x, y in lead}
    assert len(angles) == 3


def test_parse_views():
    assert dr.parse_views("STANDARD") == ["FRONT", "TOP", "RIGHT", "ISO"]
    assert dr.parse_views("top+front") == ["TOP", "FRONT"]
    assert dr.parse_views("ISO STANDARD") == ["ISO", "FRONT", "TOP", "RIGHT"]
