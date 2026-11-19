"""GEAR, FASTENER, SCALE, two-size FILLET/CHAMFER, BOSS, SNAP, VENT (PLAN items 31 to 33)."""

import math

import pytest

from modeler.commands import Processor
from modeler.geometry import fasteners as fs
from modeler.geometry import gears as gr
from modeler.geometry import robust


def run(p, *lines):
    for line in lines:
        r = p.run(line)
        assert r.ok, (line, r.message)
    return r


def fails(p, line, text):
    r = p.run(line)
    assert not r.ok and text in r.message, r.message


def bounds(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    a, b = box.CornerMin(), box.CornerMax()
    return (a.X(), a.Y(), a.Z()), (b.X(), b.Y(), b.Z())


# ---- gears -----------------------------------------------------------------------------


def test_gear_sizes():
    g = gr.size(2, 20)
    assert math.isclose(g.pitch_r, 20) and math.isclose(g.tip_r, 22) and math.isclose(g.root_r, 17.5)
    assert math.isclose(g.base_r, 20 * math.cos(math.radians(20)))
    h = gr.size(2, 20, helix_deg=15)
    assert math.isclose(h.module, 2 / math.cos(math.radians(15)))
    with pytest.raises(gr.GearError):
        gr.size(2, 4)


def test_spur_gear_and_mesh():
    p = Processor()
    r = run(p, "GEAR, 0,0,0, 2, 20, 10")
    assert "pitch diameter 40" in r.message and "centre distance 20 + 1 x z" in r.message
    s = p.model.bodies[1].shape
    assert robust.is_valid(s)
    lo, hi = bounds(s)
    assert math.isclose(hi[0], 22, abs_tol=1e-3) and math.isclose(hi[2], 10, abs_tol=1e-6)
    # area between the root and tip circles, about half of the ring is teeth
    ring = math.pi * (22 ** 2 - 17.5 ** 2) * 10
    root = math.pi * 17.5 ** 2 * 10
    assert root + 0.35 * ring < robust.volume(s) < root + 0.65 * ring
    run(p, "GEAR, 50,0,0, 2, 30, 10", "ROTATE, 2, 6, 50,0,0")
    assert "touch (no overlap)" in run(p, "CLASH, 1, 2").message
    run(p, "ROTATE, 2, -6, 50,0,0")
    assert "OVERLAP" in run(p, "CLASH, 1, 2").message


def test_helical_internal_and_rack():
    p = Processor()
    r = run(p, "GEAR, 0,0,0, 2, 20, 10, , 15, 8")
    assert "helical" in r.message and "bore 8" in r.message
    assert robust.is_valid(p.model.bodies[1].shape)
    run(p, "GEAR, 0,0,30, 2, 60, 10, INTERNAL", "GEAR, 40,0,30, 2, 20, 10")
    assert robust.is_valid(p.model.bodies[2].shape)
    assert "touch (no overlap)" in run(p, "CLASH, 2, 3").message
    r = run(p, "GEAR, 0,100,0, 2, 12, 10, RACK")
    assert "12 teeth" in r.message
    lo, hi = bounds(p.model.bodies[4].shape)
    assert math.isclose(hi[0] - lo[0], 12 * math.pi * 2, rel_tol=1e-6)
    fails(p, "GEAR, 0,0,0, 2, 20, 10, WORMY", "EXTERNAL, INTERNAL, RACK")
    fails(p, "GEAR, 0,0,0, 2, 20.5, 10", "whole number")
    fails(p, "GEAR, 0,0,0, 2, 20, 10, , , 50", "smaller than the root circle")


def test_gear_on_axis():
    p = Processor()
    run(p, "GEAR, 0,0,0, 1, 24, 5, , , , , 1,0,0")
    lo, hi = bounds(p.model.bodies[1].shape)
    assert math.isclose(hi[0] - lo[0], 5, abs_tol=1e-3)


# ---- fasteners -------------------------------------------------------------------------


def test_fastener_tables_and_names():
    assert fs.size_of("m8") == 8 and fs.size_of("10") == 10
    with pytest.raises(fs.FastenerError):
        fs.size_of("M7")
    assert fs.thread_length(8, 100) == 28 and fs.thread_length(8, 20) == 20
    p = Processor()
    r = run(p, "FASTENER, CAP, M8, 0,0,10, 25")
    assert "'M8x25_CAP_1'" in r.message and "ISO 4762" in r.message
    b = p.model.body_by_name("M8x25_CAP_1")
    assert b.material == "STEEL"
    lo, hi = bounds(b.shape)
    assert math.isclose(lo[2], -15, abs_tol=1e-3) and math.isclose(hi[2], 18, abs_tol=1e-3)
    run(p, "FASTENER, CAP, M8, 30,0,10, 25")
    assert p.model.body_by_name("M8x25_CAP_2") is not None
    run(p, "FASTENER, NUT, M8, 0,0,-12", "FASTENER, WASHER, M8, 0,0,10")
    lo, hi = bounds(p.model.body_by_name("M8_NUT_1").shape)
    assert math.isclose(hi[2] - lo[2], 6.8, abs_tol=1e-3)
    # a nut hangs under its seat, along the screw
    assert math.isclose(hi[2], -12, abs_tol=1e-3)
    lo, hi = bounds(p.model.body_by_name("M8_WASHER_1").shape)
    assert math.isclose(lo[2], 10, abs_tol=1e-3)
    fails(p, "FASTENER, NUT, M8, 0,0,0, 5", "has no length")
    fails(p, "FASTENER, CAP, M8", "length")
    fails(p, "FASTENER, RIVET, M8, 0,0,0, 5", "kind")


def test_threaded_fastener():
    p = Processor()
    run(p, "FASTENER, CAP, M3, 0,0,0, 8, PLAIN")
    plain = robust.volume(p.model.bodies[1].shape)
    run(p, "FASTENER, CAP, M3, 20,0,0, 8, REAL")
    threaded = p.model.bodies[2].shape
    assert robust.is_valid(threaded) and robust.volume(threaded) < plain


# ---- shape edits ---------------------------------------------------------------------


def test_scale():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 10,10,10", "SCALE, 1, 2")
    assert math.isclose(robust.volume(p.model.bodies[1].shape), 8000, rel_tol=1e-9)
    run(p, "BLOCK, 0,0,0, 10,10,10", "SCALE, 2, 1, 0,0,0, 1, 3")
    lo, hi = bounds(p.model.bodies[2].shape)
    assert math.isclose(hi[2], 30, abs_tol=1e-5) and math.isclose(hi[1], 10, abs_tol=1e-5)
    run(p, "CYL, 0,0,0, 5, 10", "SCALE, 3, 1, 0,0,0, 2, 1")
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(p.model.bodies[3].shape, g, 1e-7)  # (splines now: ask for precision)
    assert math.isclose(g.Mass(), math.pi * 25 * 10 * 2, rel_tol=1e-5)
    run(p, "SPHERE, 0,0,0, 5", "TOMESH, 4", "SCALE, 4, 2")
    fails(p, "SCALE, 1, 0", "positive")
    run(p, "UNDO")


def test_fillet_and_chamfer_two_sizes():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 20,20,20")
    edge = sorted(p.model.bodies[1].entity_ids["EDGE"])[0]
    r = run(p, f"PICK, EDGE, {edge}", "FILLET, 1, 4")
    assert "FILLET 1 to 4" in r.message
    run(p, "BLOCK, 50,0,0, 20,20,20")
    full = robust.volume(p.model.bodies[max(p.model.bodies)].shape)
    edge = sorted(p.model.bodies[max(p.model.bodies)].entity_ids["EDGE"])[0]
    r = run(p, f"PICK, EDGE, {edge}", "CHAMFER, 1, 3")
    assert "CHAMFER 1 and 3" in r.message
    cut = full - robust.volume(p.model.bodies[max(p.model.bodies)].shape)
    assert math.isclose(cut, 0.5 * 1 * 3 * 20, rel_tol=1e-6)


# ---- plastic part features --------------------------------------------------------------


def test_boss_and_snap():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 80,60,2", "NAME, LAST, base")
    before = robust.volume(p.model.bodies[1].shape)
    r = run(p, "BOSS, base, 20,15,2, 10, 7, 2.5")
    assert "4 ribs" in r.message
    s = p.model.bodies[1].shape
    assert robust.is_valid(s) and len(robust.solids(s)) == 1
    tube = math.pi * (3.5 ** 2 - 1.25 ** 2) * 10
    assert robust.volume(s) - before > tube
    lo, hi = bounds(s)
    assert math.isclose(hi[2], 12, abs_tol=1e-6)
    r = run(p, "SNAP, base, 40,50,2, 12, 6, 1.5")
    assert "bending strain" in r.message
    assert len(robust.solids(p.model.bodies[1].shape)) == 1
    assert "more than the 2 to 5%" in run(p, "SNAP, base, 60,50,2, 5, 6, 2, 1.5").message
    fails(p, "BOSS, base, 20,15,2, 10, 7, 8", "smaller than the outside")
    fails(p, "SNAP, base, 0,0,2, 3, 6, 1, 3", "too big")


def test_vent():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 80,60,30", "SEL, S, FACE, LOC, Z, 0", "SHELL, 2", "SEL, S, FACE, LOC, Z, 30")
    before = robust.volume(p.model.bodies[1].shape)
    r = run(p, "VENT, 6, 30, 2")
    assert "2 deep" in r.message
    slot = (28 * 2 + math.pi) * 2
    assert math.isclose(before - robust.volume(p.model.bodies[1].shape), 6 * slot, rel_tol=1e-3)
    run(p, "SEL, S, FACE, LOC, X, 80")
    fails(p, "VENT, 40, 20, 2", "run off the face")
    run(p, "VENT, 4, 15, 2, 4, 90")
    fails(p, "VENT, 3, 1, 2", "at least the width")
