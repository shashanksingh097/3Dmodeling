"""More standard parts (PLAN item 98): the new kinds, inch sizes, FASTENER ... HOLE and the BOM."""

import math

import pytest

from modeler.commands.processor import Processor
from modeler.commands.queries import bbox
from modeler.core.model import Model
from modeler.geometry import fasteners as fs
from modeler.geometry import robust


def run(p, text):
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
    return r


@pytest.fixture
def p():
    return Processor(Model())


@pytest.mark.parametrize("kind,size,length", [
    ("CSK", "M6", 20), ("BUTTON", "M5", 12), ("SET", "M4", 8), ("DOWEL", "6", 20), ("SPRINGPIN", "4", 16),
    ("INSERT", "M3", 0), ("BEARING", "608", 0), ("BEARING", "6201-2RS", 0), ("CIRCLIP", "20", 0),
    ("KEY", "20", 30), ("KEY", "8x7", 40), ("CAP", "1/4-20", 25.4), ("HEXBOLT", "#10-24", 12.7),
    ("NUT", "3/8", 0), ("WASHER", "#8-32", 0), ("SET", "5/16-18", 10)])
def test_every_kind_builds_a_clean_solid(kind, size, length):
    m = fs.make(kind, size, length)
    assert robust.report(m.shape)["ok"] and robust.volume(m.shape) > 0
    assert m.name and m.label


def test_sizes_from_the_tables():
    m = fs.make("BEARING", "608", 0)
    assert m.d == 8 and m.fit_hole == 22 and m.length == 7
    assert fs.make("CAP", "1/4-20", 25.4).d == pytest.approx(6.35)
    assert fs.make("CAP", "1/4-20", 25.4).pitch == pytest.approx(25.4 / 20)
    assert fs.make("KEY", "20", 30).d == 6  # a 20 shaft takes a 6 x 6 key
    with pytest.raises(fs.FastenerError):
        fs.make("CSK", "M24", 30)  # ISO 10642 stops at M20
    with pytest.raises(fs.FastenerError):
        fs.make("DOWEL", "1/4-20", 10)  # inch sizes are for screws, nuts, washers
    with pytest.raises(fs.FastenerError):
        fs.make("BEARING", "9999", 0)


def test_matching_holes(p):
    run(p, "BLOCK, 0,0,0, 80,40,10\nNAME, LAST, plate")
    v0 = 80 * 40 * 10
    r = run(p, "FASTENER, CSK, M5, 10,10,10, 16, , , , , plate")
    assert "countersink 11.2" in r.message and p.reports["FASTENER"]["hole"]["kind"] == "CSINK"
    run(p, "FASTENER, CAP, M6, 30,10,10, 20, , , , , plate, CBORE")
    cap = p.model.body_by_name("M6x20_CAP_1")
    # the head sits in the counterbore: its top 0.5 under the plate's top
    assert bbox(cap.shape)[5] == pytest.approx(10 - 0.5, abs=1e-6)
    run(p, "FASTENER, DOWEL, 6, 50,10,10, 8, , , , , plate")
    run(p, "FASTENER, CAP, M4, 70,10,10, 6, , , , , plate, TAP")
    run(p, "FASTENER, BEARING, 608, 40,26,10, , , , , , plate")
    plate = p.model.body_by_name("plate")
    assert robust.report(plate.shape)["ok"]
    assert p.evaluate("HOLES(plate, 6.6, 1)") == 1 and p.evaluate("HOLES(plate, 6, 0)") == 1
    assert p.evaluate("HOLES(plate, 3.3, 0)") == 1 and p.evaluate("HOLES(plate, 22, 0)") == 1
    assert robust.volume(plate.shape) < v0 - math.pi * 11 ** 2 * 7  # the bearing's bore alone
    assert not p.run("FASTENER, NUT, M8, 0,0,0, , , , , , plate").ok  # a nut needs no hole
    assert not p.run("FASTENER, DOWEL, 6, 5,35,10, 12, , , , , plate, CBORE").ok
    assert not p.run("FASTENER, CAP, M6, 5,35,10, 20, , , , , , CBORE").ok  # a fit with no body


def test_bom_counts_the_same_parts_together(p):
    run(p, "BLOCK, 0,0,0, 80,40,10\nNAME, LAST, plate")
    for x in (10, 30, 50):
        run(p, f"FASTENER, CAP, M6, {x},10,10, 20, , , , , plate")
    run(p, "FASTENER, CAP, M6, 70,10,10, 25, , , , , plate")
    run(p, "BOM")
    rows = p.reports["BOM"]["rows"]
    caps = {r["name"]: r["qty"] for r in rows if "CAP" in r["name"]}
    assert caps == {"M6x20_CAP": 3, "M6x25_CAP": 1}
    assert all(r["values"] == "ISO 4762 socket head cap screw" for r in rows if "CAP" in r["name"])
