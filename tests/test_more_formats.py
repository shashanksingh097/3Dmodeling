"""PLAN item 101: SVG drawings into sketches (SSVG), OpenSCAD files as bodies (IMPORT, SCAD), and
VRML and AMF export."""

import math
import xml.etree.ElementTree as ET

import pytest

from modeler.commands import Processor
from modeler.geometry import scad, svgread


def ok(p, text):
    out = []
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
        out.append(r)
    return out[-1]


PLATE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
     width="100mm" height="60mm" viewBox="0 0 100 60">
  <g inkscape:groupmode="layer" inkscape:label="CUT">
    <rect x="0" y="0" width="100" height="60" rx="5"/>
    <circle cx="20" cy="30" r="6"/>
    <path d="M60,20 h20 a10,10 0 0 1 0,20 h-20 z"/>
  </g>
  <g inkscape:groupmode="layer" inkscape:label="ENGRAVE">
    <path d="M10 50 C 20 40, 30 40, 40 50 S 60 60, 70 50"/>
    <text x="5" y="5">hi</text>
  </g>
</svg>"""


def test_svg_plate_extrudes_to_the_right_volume(tmp_path):
    f = tmp_path / "plate.svg"
    f.write_text(PLATE_SVG)
    p = Processor()
    r = ok(p, f'SKETCH, s, XY\nSSVG, "{f}", 1, 0, 0, CUT')
    assert "100 x 60" in r.message and "1 circle" in r.message and "5 arcs" in r.message
    ok(p, "ENDSKETCH\nEXTRUDE, s, 5")
    want = (100 * 60 - (4 - math.pi) * 25 - math.pi * 36 - (20 * 20 + math.pi * 100 / 2)) * 5
    assert p.evaluate("VOL(LAST)") == pytest.approx(want, rel=1e-9)


def test_svg_reading_details(tmp_path):
    ents, notes, info = svgread.read(PLATE_SVG)
    assert info["width"] == pytest.approx(100) and info["mm_per_unit"] == pytest.approx(1)
    assert notes == ["1 text"] and {e.layer for e in ents} == {"CUT", "ENGRAVE"}
    circle = next(e for e in ents if e.kind == "CIRCLE")
    assert circle.centre == pytest.approx((20, 30)) and circle.r == pytest.approx(6)  # y turned up: 60 - 30
    # pixels without a unit: 96 to the inch; a transform squashing a circle makes it an ellipse
    ents, _, info = svgread.read('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96">'
                                 '<circle cx="48" cy="48" r="10" transform="scale(2,1)"/></svg>')
    assert info["width"] == pytest.approx(25.4) and ents[0].kind == "ELLIPSE"
    assert math.hypot(*ents[0].major) == pytest.approx(20 * 25.4 / 96) and ents[0].ratio == pytest.approx(0.5)
    with pytest.raises(svgread.SvgError):
        svgread.read("<html/>")


def test_ssvg_needs_a_sketch_and_names_layers(tmp_path):
    f = tmp_path / "plate.svg"
    f.write_text(PLATE_SVG)
    p = Processor()
    r = p.run(f'SSVG, "{f}"')
    assert not r.ok
    ok(p, "SKETCH, s, XY")
    r = p.run(f'SSVG, "{f}", 1, 0, 0, HOLES')
    assert not r.ok and "layers: CUT, ENGRAVE" in r.message


BRACKET_SCAD = """
// a bracket with holes
w = 40; t = 3;
module hole(x, y, d=4) { translate([x, y, -1]) cylinder(h = t + 2, d = d); }
difference() {
  union() {
    cube([w, 20, t]);
    cube([t, 20, 25]);
  }
  for (i = [1:2]) hole(i * 12, 10);
  translate([-1, 10, 15]) rotate([0, 90, 0]) cylinder(h = t + 2, r = 2.5);
}
translate([60, 0, 0]) rotate_extrude() translate([10, 0]) circle(r = 2);
translate([0, 40, 0]) linear_extrude(height = 5) polygon([[0,0],[20,0],[10,15]]);
translate([40, 40, 0]) sphere(d = 10);
mirror([1, 0, 0]) translate([10, 60, 0]) cube(5, center = true);
"""


def test_openscad_file_becomes_exact_bodies(tmp_path):
    f = tmp_path / "bracket.scad"
    f.write_text(BRACKET_SCAD)
    p = Processor()
    r = ok(p, f'IMPORT, SCAD, "{f}"')
    assert "5 bodies from OpenSCAD" in r.message
    vols = [p.evaluate(f"VOL({b})") for b in sorted(p.model.bodies)]
    assert vols[0] == pytest.approx(40 * 20 * 3 + 3 * 20 * 22 - 2 * math.pi * 4 * 3 - math.pi * 2.5 ** 2 * 3)
    assert vols[1] == pytest.approx(2 * math.pi ** 2 * 10 * 4)  # a torus
    assert vols[2] == pytest.approx(20 * 15 / 2 * 5) and vols[3] == pytest.approx(math.pi * 5 ** 3 * 4 / 3)
    box = p.evaluate(f"BBOX({sorted(p.model.bodies)[4]})")
    assert box.get("xmin") == pytest.approx(-12.5)  # mirrored in x


def test_openscad_errors_name_the_line():
    with pytest.raises(scad.ScadError, match="line 2: hull"):
        scad.read("cube(1);\nhull() { cube(1); sphere(1); }")
    with pytest.raises(scad.ScadError, match="line 1: .*q has no value"):
        scad.read("cube(q);")
    shapes, counts = scad.read("for (a = [0:90:270]) rotate(a) translate([10,0,0]) cube(2);")
    assert len(shapes) == 4 and counts["cube"] == 4


def test_vrml_and_amf_export(tmp_path):
    p = Processor()
    ok(p, "BLOCK, 0,0,0, 10,10,10\nNAME, LAST, cube\nCOLOR, cube, RED")
    ok(p, f'EXPORT, VRML, "{tmp_path / "c.wrl"}"\nEXPORT, AMF, "{tmp_path / "c.amf"}"')
    wrl = (tmp_path / "c.wrl").read_text()
    assert wrl.startswith("#VRML V2.0 utf8") and "DEF cube Shape" in wrl and wrl.count(", -1,") == 12
    root = ET.parse(tmp_path / "c.amf").getroot()
    assert root.get("unit") == "millimeter"
    obj = root.find("object")
    assert obj.find("metadata").text == "cube" and len(obj.findall("mesh/volume/triangle")) == 12
    assert float(obj.find("color/r").text) > 0.5
