"""Editing in a cross-section (PLAN item 96): SECTIONEDIT lists the cut lines with their faces; a
change is PICK, FACE and PUSHPULL; drawing on the cut starts a sketch on the plane."""

import pytest

from modeler.commands import section_edit_handlers as seh
from modeler.commands.processor import Processor
from modeler.core.model import Model
from modeler.geometry import robust
from modeler.geometry import section_edit as se


def run(p, text):
    for line in text.strip().splitlines():
        r = p.run(line.strip())
        assert r.ok, (line, r.message)
    return r


@pytest.fixture
def p():
    return Processor(Model())


PLATE = """BLOCK, 0,0,0, 40,20,10
CYL, 20,10,0, 4, 10
SUBTRACT, 1, 2
NAME, LAST, plate"""


def test_lines_with_faces_and_push(p):
    run(p, PLATE)
    r = run(p, "SECTIONEDIT, XY, 5")
    d = p.reports["SECTIONEDIT"]
    assert d["origin"] == [0, 0, 5] and d["normal"] == [0, 0, 1]
    lines = d["bodies"][0]["lines"]
    assert len(lines) == 5 and "5 lines" in r.message
    kinds = sorted(ln["kind"] for ln in lines)
    assert kinds == ["arc", "line", "line", "line", "line"]
    arc = next(ln for ln in lines if ln["kind"] == "arc")
    assert arc["radius"] == pytest.approx(4) and arc["centre"][:2] == pytest.approx([20, 10])
    xmax = next(ln for ln in lines if ln["kind"] == "line" and ln["from"][0] == pytest.approx(40)
                and ln["to"][0] == pytest.approx(40))
    assert xmax["push"] == pytest.approx([1, 0, 0]) and xmax["length"] == pytest.approx(20)
    assert all(ln["face"] for ln in lines)  # every line knows its face
    assert p.section is not None and p.section_edit is not None


def test_pull_a_line_writes_ordinary_steps(p):
    run(p, PLATE)
    run(p, "SECTIONEDIT, XY, 5")
    lines = p.reports["SECTIONEDIT"]["bodies"][0]["lines"]
    xmax = next(ln for ln in lines if ln.get("push") == [1.0, 0.0, 0.0] and ln["kind"] == "line")
    n0 = len(p.history)
    run(p, f"PICK, FACE, {xmax['face']}\nPUSHPULL, 5")
    assert [e.text.split(",")[0] for e in p.history[n0:]] == ["PICK", "PUSHPULL"]
    b = p.model.body_by_name("plate")
    assert robust.volume(b.shape) == pytest.approx(45 * 20 * 10 - 3.14159265 * 16 * 10, rel=1e-6)
    seh.refresh(p.model, p.section_edit)
    longest = max(ln.length for _b, ln in p.section_edit.all_lines() if ln.kind == "line")
    assert longest == pytest.approx(45)
    run(p, "SECTIONEDIT, OFF")
    assert p.section is None and p.section_edit is None


def test_draw_on_the_cut(p):
    run(p, PLATE)
    run(p, "SECTIONEDIT, XY, 5")
    draw = p.reports["SECTIONEDIT"]["draw"]
    assert draw == ["PLANE, cut1_plane, XY, 5", "SKETCH, cut1, cut1_plane"]
    for line in draw:
        run(p, line)
    run(p, "SRECT, 40, 5, 50, 15\nENDSKETCH\nEXTRUDE, cut1, 5, ADD, plate")
    b = p.model.body_by_name("plate")
    assert robust.volume(b.shape) == pytest.approx(40 * 20 * 10 - 3.14159265 * 16 * 10 + 10 * 10 * 5, rel=1e-6)
    run(p, "PLANE, mid, ZX, 10\nSECTIONEDIT, mid")  # no offset: the sketch goes straight on the plane
    assert p.reports["SECTIONEDIT"]["draw"] == ["SKETCH, cut2, mid"]


def test_misses_and_meshes(p):
    run(p, "BLOCK, 0,0,0, 10,10,10")
    r = p.run("SECTIONEDIT, XY, 50")
    assert not r.ok and "cuts no solid" in r.message
    assert p.section_edit is None


def test_nearest_line_in_pixels(p):
    run(p, "BLOCK, 0,0,0, 10,10,10")
    lines = se.cut_lines(p.model.body(1).shape, (0, 0, 5), (0, 0, 1), (1, 0, 0))
    to_px = lambda q: (q[0] * 10, q[1] * 10)  # noqa: E731 - looking down Z, 10 px per mm
    hit = se.nearest(lines, 50, 2, to_px)
    assert hit is not None and hit.start[1] == pytest.approx(0) and hit.end[1] == pytest.approx(0)
    assert se.nearest(lines, 50, 50, to_px) is None


# ---- the real 3D view (needs a display: run under xvfb-run) -----------------------------
import os  # noqa: E402
import sys  # noqa: E402

gui = pytest.mark.skipif(os.environ.get("MODELER_GUI_TESTS") == "0"
                         or (sys.platform.startswith("linux") and not os.environ.get("DISPLAY")),
                         reason="needs a display (run under xvfb-run)")


@pytest.fixture
def win():
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.resize(1200, 800)
    w.show()
    for _ in range(30):
        app.processEvents()
        if w.viewport._initialized:
            break
    assert w.viewport._initialized
    yield w, app
    w.close()


@gui
def test_click_a_cut_line_picks_its_face_and_the_arrow_pulls_it(win):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    w, app = win
    for line in PLATE.splitlines():
        assert w.execute(line).ok
    w.execute("VIEW, TOP")
    w.execute("FIT")
    dlg = w.open_section_edit()
    dlg.plane.setCurrentText("XY")
    app.processEvents()
    vp = w.viewport
    assert w.processor.section_edit is not None and vp._se_ais and w.handles_action.isChecked()
    assert dlg.draw_btn.isEnabled() and not dlg.add_btn.isEnabled()
    xmax = next(ln for _b, ln in vp._se.all_lines() if ln.kind == "line" and ln.push == pytest.approx((1, 0, 0)))
    x, y = vp.view.Convert(*xmax.mid)
    r = vp.devicePixelRatioF()
    at = QPoint(int(round(x / r)), int(round(y / r)))
    assert vp.section_line_at(x, y) is not None
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, at)
    app.processEvents()
    gid = w.processor.model.find_entity(w.processor.model.body_by_name("plate").id, "FACE", xmax.face)
    assert w.processor.history[-1].text == f"PICK, FACE, {gid}"
    hd = vp.handles
    assert hd is not None and any(h.kind == "PULL" for h in hd.items)
    # the cut follows the change
    assert w.execute("PUSHPULL, 5").ok
    for _ in range(5):
        app.processEvents()
    longest = max(ln.length for _b, ln in vp._se.all_lines() if ln.kind == "line")
    assert longest == pytest.approx(45)
    lines = dlg.draw()
    assert lines and w.processor.model.active_sketch
    w.execute("ENDSKETCH")
    dlg.close()
    app.processEvents()
    assert w.processor.section_edit is None and not vp._se_ais
