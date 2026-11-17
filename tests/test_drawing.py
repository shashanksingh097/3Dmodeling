"""DRAWING (2D drawings to SVG and DXF), and the drawing math on its own."""

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
    assert groups == {"front", "top", "right", "iso"}
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
    assert layers == ["VISIBLE", "HIDDEN", "TEXT"]
    ents = [v for c, v in pairs if c == 0]
    assert ents.count("LINE") >= 8 and "POLYLINE" in ents and ents.count("TEXT") == 2
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


def test_parse_views():
    assert dr.parse_views("STANDARD") == ["FRONT", "TOP", "RIGHT", "ISO"]
    assert dr.parse_views("top+front") == ["TOP", "FRONT"]
    assert dr.parse_views("ISO STANDARD") == ["ISO", "FRONT", "TOP", "RIGHT"]
