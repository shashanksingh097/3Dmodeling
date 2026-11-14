"""Implicit shapes and lattices (M6 part 2): IMPLICIT, SMIN blends, LATTICE."""

import math

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import implicit as im
from modeler.geometry import meshbody as mb


def run(p, text):
    out = p.run_script(text)
    bad = [r for r in out if not r.ok]
    assert not bad, bad[0].message
    return out[-1].message


def err(p, text):
    r = p.run_script(text)[-1]
    assert not r.ok, r.message
    return r.message


def info(p, name):
    return mb.info(p.model.body_by_name(name).shape)


def no_params(key):
    raise KeyError(key)


def test_field_compiler_matches_numbers():
    f = im.compile_field("SQRT(x**2 + y**2) - 2 + SIN(90)*z", no_params, {})
    x, y, z = np.array([3.0]), np.array([4.0]), np.array([1.0])
    assert f(x, y, z)[0] == pytest.approx(4.0)
    with pytest.raises(im.FieldError, match="unknown name"):
        im.compile_field("q + 1", no_params, {})
    with pytest.raises(im.FieldError, match=r"\*\*"):
        im.compile_field("x^2", no_params, {})
    with pytest.raises(im.FieldError, match="numbers"):
        im.compile_field("BALL(x, 0, 0, 1)", no_params, {})


@pytest.mark.parametrize("kind", ["sphere", "gyroid", "CUBIC", "BCC", "OCTET", "SCHWARZ", "DIAMOND"])
def test_marching_tetrahedra_give_closed_meshes(kind):
    if kind == "sphere":
        f = im.compile_field("BALL(0,0,0,5)", no_params, {})
    elif kind == "gyroid":
        f = im.compile_field("ABS(GYROID(6)) - 0.5", no_params, {})
    else:
        f = im.lattice_field(kind, 6, 1.2)
    pts, t = im.mesh_field(f, (-7, -7, -7, 7, 7, 7), 0.4)
    assert mb._closed(t)
    assert mb.to_manifold(pts, t).volume() > 0


def test_implicit_ball_volume_and_named_fields_blend():
    p = Processor()
    run(p, "R = 10\nIMPLICIT, a, BALL(0,0,0,R), -11,-11,-11, 11,11,11")
    assert info(p, "a").volume == pytest.approx(4 / 3 * math.pi * 1000, rel=0.01)
    run(p, "IMPLICIT, b, BALL(15,0,0,6), 8,-7,-7, 22,7,7\n"
           "IMPLICIT, hard, MIN(a, b), -11,-11,-11, 22,11,11, 0.4\n"
           "IMPLICIT, soft, SMIN(a, b, 4), -11,-11,-11, 22,11,11, 0.4")
    # the blend adds a fillet where the balls meet
    assert info(p, "soft").volume > info(p, "hard").volume * 1.005
    assert info(p, "soft").closed


def test_implicit_box_clips_and_edit_rebuilds():
    p = Processor()
    run(p, "R = 10\nIMPLICIT, half, BALL(0,0,0,R), -11,-11,0, 11,11,11")
    assert info(p, "half").volume == pytest.approx(2 / 3 * math.pi * 1000, rel=0.02)
    assert info(p, "half").closed  # closed flat where the box cuts it
    run(p, "HIST, EDIT, 1, R = 8")
    assert info(p, "half").volume == pytest.approx(2 / 3 * math.pi * 512, rel=0.02)


def test_implicit_errors():
    p = Processor()
    assert "nowhere below 0" in err(p, "IMPLICIT, n, BALL(100,0,0,1), -5,-5,-5, 5,5,5")
    assert "grid points" in err(p, "IMPLICIT, n, BALL(0,0,0,1), -500,-500,-500, 500,500,500, 0.1")
    assert "not a valid name" in err(p, "IMPLICIT, 2x, BALL(0,0,0,1), -2,-2,-2, 2,2,2")


def test_lattice_fills_a_block_with_and_without_skin():
    p = Processor()
    run(p, "BLOCK, 0,0,0, 30,20,16\nNAME, LAST, plain\nLATTICE, plain, GYROID, 8, 1")
    v = info(p, "plain").volume
    assert 0.05 * 9600 < v < 0.4 * 9600
    msg = run(p, "BLOCK, 50,0,0, 30,20,16\nNAME, LAST, skinned\nLATTICE, skinned, GYROID, 8, 1, 1.5")
    assert "of the volume is left" in msg
    sk = info(p, "skinned")
    assert sk.closed and sk.volume > v  # the skin adds a closed outer wall
    # the outside is the block's: same bounding box
    pts, _ = mb.arrays(p.model.body_by_name("skinned").shape)
    assert pts.min(axis=0) == pytest.approx((50, 0, 0), abs=1e-6)
    assert pts.max(axis=0) == pytest.approx((80, 20, 16), abs=1e-6)


def test_lattice_struts_and_errors():
    p = Processor()
    run(p, "SPHERE, 0,0,0, 10\nLATTICE, 1, OCTET, 5, 1")
    assert info(p, "body1").closed
    run(p, "SPHERE, 30,0,0, 10\nTOMESH, LAST")
    assert "skin needs an exact solid" in err(p, "LATTICE, 2, CUBIC, 5, 1, 1")
    assert "one of" in err(p, "LATTICE, 2, HONEY, 5, 1")
    assert "smaller than the cell" in err(p, "LATTICE, 2, CUBIC, 5, 6")


def test_example_script_runs():
    import os

    here = os.path.join(os.path.dirname(__file__), "..", "scripts", "implicit_lattices.cmd")
    p = Processor()
    with open(here, encoding="utf-8") as f:
        run(p, f.read())
    assert {"blob", "pillow", "gyro", "bracket", "post", "ball"} <= {b.name for b in p.model.bodies.values()}
