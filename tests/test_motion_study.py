"""PLAN item 105: motion studies - points' position, speed and acceleration, and the drive torque or force."""

import math

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.geometry import kinematics as kn


def ok(p, text):
    r = None
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
    return r


ARM = """A = 0
BLOCK, 0, -5, -5, 100, 10, 10
NAME, LAST, arm
MATERIAL, arm, STEEL
ROTATE, arm, -A, 0, 0, 0, 0, 1, 0"""


def test_rotation_vector_and_angular_velocity():
    c, s = math.cos(0.3), math.sin(0.3)
    r = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    assert kn.rotation_vector(r) == pytest.approx([0, 0, 0.3])
    rs = [np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
          for a in np.linspace(0, 1, 11)]
    w = kn.angular_velocity(rs, np.linspace(0, 2, 11))
    assert w[5] == pytest.approx([0, 0, 0.5])


def test_arm_tip_speed_and_drive_torque(tmp_path):
    p = Processor()
    ok(p, ARM)
    # a quarter turn up in 1 s: the tip (100 from the pivot) moves at 100 * (pi/2) mm/s
    r = ok(p, 'MOTION, A, 0, 90, 30, "arm 100,0,0", 1')
    st = p.reports["MOTION"]["study"]
    assert st["kind"] == "ANGLE"
    speed = st["points"]["arm"]["speed"]
    assert speed[15] == pytest.approx(100 * math.pi / 2, rel=1e-3)
    # the tip goes up to z = 100
    assert st["points"]["arm"]["pos"][-1][2] == pytest.approx(100, abs=1e-3)
    # centripetal acceleration in the middle: r w^2
    assert st["points"]["arm"]["accel"][15] == pytest.approx(100 * (math.pi / 2) ** 2, rel=2e-2)
    # the torque to hold the steel arm up: m g L/2 cos(angle), largest while level
    mass = 7850 * 100 * 10 * 10 * 1e-9
    grav = st["drive"]["gravity"]
    assert grav[0] == pytest.approx(mass * 9.81 * 0.05, rel=2e-2)
    assert abs(grav[-1]) < 0.1 * grav[0]
    assert st["drive"]["unit"] == "N m"
    assert "drive torque" in r.message
    # the parameter is back where it was
    assert p.model.body(1).shape is not None and "A" not in p.drive
    # the table and the plots
    f = tmp_path / "arm.csv"
    ok(p, f'MOTION, A, 0, 90, 10, "arm 100,0,0", 1, , "{f}"')
    rows = f.read_text().splitlines()
    assert rows[0].startswith("A,time_s,arm_x") and len(rows) == 12
    g = tmp_path / "arm.svg"
    ok(p, f'MOTION, A, 0, 90, 10, "arm 100,0,0", 1, ANGLE, "{g}"')
    assert g.read_text().count("<polyline") == 3


def test_slider_force_and_errors():
    p = Processor()
    ok(p, """D = 0
BLOCK, 0, 0, 0, 10, 10, 10
NAME, LAST, block
MATERIAL, block, STEEL
MOVE, block, 0, 0, D""")
    ok(p, 'MOTION, D, 0, 50, 10, "block 5,5,10", 2')
    st = p.reports["MOTION"]["study"]
    assert st["kind"] == "LENGTH" and st["drive"]["unit"] == "N"
    mass = 7850 * 1000e-9
    assert st["drive"]["gravity"][5] == pytest.approx(mass * 9.81, rel=1e-3)  # lifting it straight up
    assert st["points"]["block"]["speed"][5] == pytest.approx(25, rel=1e-6)  # 50 mm in 2 s
    assert not p.run('MOTION, D, 0, 50, 10, "block"').ok
    assert not p.run('MOTION, D, 0, 50, 10, "nobody 1,2,3"').ok
    assert not p.run('MOTION, D, 0, 50, 10, "block 1,2,3", 0').ok
    assert not p.run('MOTION, D, 0, 50, 10, "block 1,2,3", 1, SIDEWAYS').ok
    assert not p.run('MOTION, D, 0, 50, 10, "block 1,2,3", 1, , "x.png"').ok


def test_no_material_means_no_force():
    p = Processor()
    ok(p, ARM.replace("MATERIAL, arm, STEEL", "MATERIAL, arm, NONE"))
    r = ok(p, 'MOTION, A, 0, 90, 6, "arm 100,0,0"')
    assert "drive" not in p.reports["MOTION"]["study"] and "no drive force" in r.message
