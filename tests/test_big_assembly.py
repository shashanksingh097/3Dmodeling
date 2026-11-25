"""PLAN item 112: big assemblies stay fast (shared meshes for part copies, one redraw per burst, DETAIL)."""

import os
import sys
import time

import pytest

from modeler.commands import Processor

BOLTS = """*PART, bolt, D=8, L=30
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, 0.7*D, D*0.9, 6
  LOFT, 1, 2, RULED
  CYL, 0, 0, -L, D/2, L
  UNION, 3, 4
*ENDPART
*DO, i, 1, {n}
INST, bolt, (i-1-20*FLOOR((i-1)/20))*20, FLOOR((i-1)/20)*20, 0
*ENDDO
"""


def test_copies_of_a_part_share_their_geometry():
    p = Processor()
    p.run_script(BOLTS.format(n=3))
    a, b = (p.model.bodies[i].shape for i in (1, 2))
    assert a.TShape() == b.TShape() and not a.Location().IsEqual(b.Location())
    p.run("FILLET, 1, 0.5")  # a step on one copy makes a shape of its own
    assert p.model.bodies[2].shape.TShape() == b.TShape()


def test_detail_command_without_a_window():
    p = Processor()
    r = p.run("DETAIL")
    assert r.ok and "detail auto" in r.message
    assert not p.run("DETAIL, BLURRY").ok
    assert not p.history


@pytest.mark.skipif(os.environ.get("MODELER_GUI_TESTS") == "0" or
                    (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")), reason="no display")
def test_hundreds_of_copies_show_quickly_and_detail_switches(tmp_path):
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.show()
    w.offload.enabled = False
    app.processEvents()
    t = time.perf_counter()
    w.execute(BOLTS.format(n=320))
    app.processEvents()
    took = time.perf_counter() - t
    assert len(w.processor.model.bodies) == 320
    assert took < 20  # about 1 s here; it was about 7 s before the copies shared one mesh
    st = w.viewport.detail_state()
    assert st["mode"] == "AUTO" and st["fast"]
    r = w.execute("DETAIL, FINE")
    assert r.ok and "drawing fine" in r.message and not w.viewport.detail_fast()
    r = w.execute("DETAIL, FAST, 6")
    assert r.ok and "under 6 px" in r.message
    w.detail_actions["AUTO"].trigger()
    assert w.viewport.detail_mode == "AUTO"
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()
