"""PLAN item 111: 3D mouse support (viewport/spacemouse.py, gui/spacemouse_input.py, SPACEMOUSE)."""

import os

import numpy as np
import pytest

from modeler.commands import Processor
from modeler.viewport import spacemouse as sm


@pytest.fixture(autouse=True)
def fresh():
    sm.settings = sm.Settings()
    yield
    sm.settings = sm.Settings()


CAM = ((0.0, 0.0, 100.0), (0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 50.0)  # looking down -Z, Y up


def test_pan_moves_the_model_with_the_cap():
    eye, c, up, sc = sm.step(*CAM, (1, 0, 0, 0, 0, 0), 0.1)
    # the cap pushed right: the model goes right, so the camera goes left (-X)
    assert c[0] < 0 and eye[0] == pytest.approx(c[0]) and sc == 50.0
    assert c[0] == pytest.approx(-(1 - 0.06) / (1 - 0.06) * 0.5 * 50 * 0.1)


def test_zoom_and_turn():
    _e, _c, _u, sc = sm.step(*CAM, (0, 0, 1, 0, 0, 0), 1.0)  # pulled toward you: shows more
    assert sc == pytest.approx(100.0)
    _e, _c, _u, sc = sm.step(*CAM, (0, 0, -1, 0, 0, 0), 1.0)
    assert sc == pytest.approx(25.0)
    eye, c, up, _sc = sm.step(*CAM, (0, 0, 0, 0, 1, 0), 1.0)  # a full spin for a second: 90 degrees
    assert np.linalg.norm(eye - c) == pytest.approx(100.0)
    assert abs(eye[2]) < 1e-6 and abs(eye[0]) == pytest.approx(100.0)
    assert up == pytest.approx([0, 1, 0])


def test_settings_shape_the_motion():
    s = sm.Settings(rotate=False, dominant=True, invert={"TY"})
    m = sm.shape((0.5, 0.8, 0.0, 1.0, 0, 0), s)
    assert list(m[:3]) == [0, pytest.approx(-(0.8 - 0.06) / 0.94), 0] and not np.any(m[3:])
    assert not np.any(sm.shape((0.05, -0.05, 0, 0, 0, 0.03), sm.Settings()))  # inside the dead zone
    s2 = sm.Settings.from_dict(s.to_dict())
    assert s2.to_dict() == s.to_dict()


def test_spacemouse_command():
    p = Processor()
    r = p.run("SPACEMOUSE")
    assert r.ok and "no 3D mouse found" in r.message
    assert p.run("SPACEMOUSE, SPEED, 2").ok and sm.settings.speed == 2
    assert p.run("SPACEMOUSE, ROTATE, OFF").ok and not sm.settings.rotate
    assert p.run("SPACEMOUSE, INVERT, RY TZ").ok and sm.settings.invert == {"RY", "TZ"}
    assert p.run('SPACEMOUSE, BUTTON, 2, "VIEW, TOP"').ok and sm.settings.buttons[2] == "VIEW, TOP"
    assert not p.run("SPACEMOUSE, SPEED, 9").ok
    assert not p.run("SPACEMOUSE, INVERT, QQ").ok
    assert p.run("SPACEMOUSE, RESET").ok and sm.settings.speed == 1.0
    assert not p.history  # settings of the app, not steps of the project


@pytest.mark.skipif(not hasattr(__import__("socket"), "AF_UNIX"), reason="spacenavd's socket is a Unix socket (Linux)")
def test_spnav_packets(tmp_path, monkeypatch):
    import socket
    import struct
    import threading

    import tempfile

    # a Unix socket path must be short (104 bytes on macOS); pytest's tmp_path there is too long
    short = tempfile.mkdtemp(prefix="sn", dir="/tmp")
    path = os.path.join(short, "spnav.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)
    monkeypatch.setattr(sm, "SPNAV_SOCKET", path)
    got = []

    def serve():
        c, _ = srv.accept()
        c.sendall(struct.pack("<8i", 0, 350, 0, -175, 0, 0, 0, 16) + struct.pack("<8i", 1, 0, 0, 0, 0, 0, 0, 0))
        got.append(c)

    t = threading.Thread(target=serve)
    t.start()
    dev, _notes = sm.find_device()
    t.join()
    import time

    time.sleep(0.05)
    ev = dev.read()
    assert ev[0][0] == "motion" and ev[0][1][0] == pytest.approx(1.0) and ev[0][1][2] == pytest.approx(0.5)
    assert ev[1] == ("button", 1, True)
    dev.close()
    got[0].close()
    srv.close()
