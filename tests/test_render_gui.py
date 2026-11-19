"""RENDER (viewport/nice_render.py): a ray-traced picture and a turntable, and the view put back."""

import os
import sys

import pytest

from modeler.commands import Processor

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


def shown(vp):
    try:
        from OCP.collections import List_AIS_InteractiveObject as Lst  # OCP 8
    except ImportError:
        from OCP.AIS import AIS_ListOfInteractive as Lst  # OCP 7

    lst = Lst()
    vp.context.DisplayedObjects(lst)
    return lst.Size() if hasattr(lst, "Size") else lst.Extent()


def test_render_needs_the_view_and_checks_its_arguments():
    p = Processor()
    p.run("BLOCK, 0,0,0, 10,10,10")
    assert "needs the app's 3D view" in p.run("RENDER, a.png").message
    for bad in ("RENDER, a.jpg", "RENDER, a.png, 5, 5", "RENDER, a.png, 100, 100, ISO, 500",
                "RENDER, a.png, 100, 100, ISO, 0, MAYBE"):
        assert not p.run(bad).ok, bad


def test_picture_turntable_and_view_restored(app, tmp_path):
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.resize(900, 600)
    w.show()
    pump(app, 30)
    try:
        for line in ("BLOCK, 0,0,0, 40,30,10", "MATERIAL, 1, ALUMINIUM", "CYL, 20, 15, 10, 6, 20",
                     "MATERIAL, 2, BRASS"):
            assert w.execute(line).ok
        vp = w.viewport
        eye = vp.view.Camera().Eye().XYZ().Coord()
        before = shown(vp)
        lights = vp.view.ActiveLights().Size() if hasattr(vp.view.ActiveLights(), "Size") else None
        f = tmp_path / "one.png"
        r = w.execute(f'RENDER, {f}, 320, 200, "1,-1,0.6"')
        assert r.ok, r.message
        assert f.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        r = w.execute(f"RENDER, {tmp_path / 'spin.png'}, 160, 100, ISO, 4, OFF")
        assert r.ok and "turntable of 4" in r.message, r.message
        assert sorted(x.name for x in tmp_path.glob("spin_*.png")) == [f"spin_00{k}.png" for k in range(4)]
        # the working view is as it was
        assert vp.view.Camera().Eye().XYZ().Coord() == pytest.approx(eye)
        from OCP.Graphic3d import Graphic3d_RenderingMode

        assert vp.view.RenderingParams().Method == Graphic3d_RenderingMode.Graphic3d_RM_RASTERIZATION
        if lights is not None:
            assert vp.view.ActiveLights().Size() == lights
        assert shown(vp) == before  # the floor is gone again
    finally:
        w.shell.ask_unsaved = lambda *_: "discard"
        w.close()
        pump(app)
