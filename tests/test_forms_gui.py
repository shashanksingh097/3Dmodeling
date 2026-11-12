"""GUI test of the fill-in forms: a part made by forms alone, the Commands
menu, "← Selection", editing a history entry in its form, and the Form
button next to the command line."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.commands import Processor  # noqa: E402
from modeler.gui import forms as F  # noqa: E402
from modeler.gui.form_dialog import FormDialog  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def win(app):
    w = MainWindow()
    w.resize(1000, 700)
    w.show()
    pump(app, 30)
    yield w
    w.close()


def form(win, app, name, variant="") -> FormDialog:
    dlg = win.open_form(name)
    assert dlg is not None
    if variant:
        dlg.variant_box.setCurrentIndex(dlg.variant_box.findData(variant))
    pump(app)
    return dlg


def test_menu_has_every_form(win):
    menu = [a for a in win.menuBar().actions() if a.text().replace("&", "") == "Commands"][0].menu()
    subs = {a.text(): a.menu() for a in menu.actions()}
    assert list(subs) == [cat for cat, _ in F.CATEGORIES]
    count = sum(len(m.actions()) for m in subs.values())
    assert count == len(F.specs())


def test_a_part_by_forms_alone_replays_the_same(app, win):
    p = win.processor
    toolbar_block = [a for a in win.findChildren(type(win.undo_action)) if a.text() == "Block…"][0]
    toolbar_block.trigger()
    pump(app)
    dlg = [d for d in win.findChildren(FormDialog) if d.isVisible()][-1]
    dlg.fields["dx"].set_value("60, 40, 10")
    assert dlg.preview.text() == "BLOCK, 0, 0, 0, 60, 40, 10"
    assert dlg.submit(close=True)

    dlg = form(win, app, "NAME")
    dlg.fields["name"].set_value("plate")
    assert dlg.submit(close=True)

    win.execute("PICK, FACE, 6")  # what clicking the top face sends
    dlg = form(win, app, "HOLE")
    assert dlg.fields["x"].value() == "30, 20, 10"
    dlg.fields["d"].set_value("12")
    assert dlg.submit(close=True)

    dlg = form(win, app, "CYL")
    dlg.fields["x"].set_value("8, 8, 0")
    dlg.fields["r"].set_value("2.5")
    dlg.fields["h"].set_value("10")
    assert dlg.submit(close=True)
    dlg = form(win, app, "ARRAY", "LINEAR")
    dlg.fields["b"].set_value(str(p.model.last_body))  # the post just made
    dlg.fields["n"].set_value("2")
    dlg.fields["d"].set_value("44, 0, 0")
    dlg.fields["n2"].set_value("2")
    dlg.fields["d2"].set_value("0, 24, 0")
    dlg.fields["fuse"].set_value("1")
    assert dlg.preview.text() == f"ARRAY, LINEAR, {p.model.last_body}, 2, 44, 0, 0, 2, 0, 24, 0, FUSE"
    assert dlg.submit(close=True)

    pins = p.model.last_body
    win.execute(f"PICK, BODY, {p.model.body_by_name('plate').id}")  # click the plate, Ctrl+click the pins
    win.execute(f"PICK, BODY, {pins}, A")
    dlg = form(win, app, "SUBTRACT")
    assert (dlg.fields["a"].value(), dlg.fields["b"].value()) == ("plate", str(pins))
    assert dlg.submit(close=True)
    assert len(p.model.bodies) == 1

    vol = p.evaluate("VOL(plate)")
    import math
    assert vol == pytest.approx(60 * 40 * 10 - math.pi * 36 * 10 - 4 * math.pi * 2.5 ** 2 * 10, rel=1e-6)
    # the log the forms wrote rebuilds the same part
    again = Processor()
    assert all(r.ok for r in again.run_script(p.script()))
    assert again.evaluate("VOL(plate)") == pytest.approx(vol)


def test_bad_values_are_shown_before_running(app, win):
    dlg = form(win, app, "SPHERE")
    dlg.fields["r"].set_value("NOPE*2")
    pump(app)
    assert "Radius" in dlg.error.text()
    assert not dlg.ok_button.isEnabled()
    dlg.fields["r"].set_value("")
    assert "needed" in dlg.error.text()
    dlg.fields["r"].set_value("4")
    assert dlg.ok_button.isEnabled() and dlg.error.text() == ""
    # an error from the command itself keeps the form open, with the message
    dlg = form(win, app, "MOVE")
    dlg.fields["b"].set_value("99")
    assert not dlg.ok_button.isEnabled()
    dlg.close()


def test_selection_button_and_variants(app, win):
    win.execute("BLOCK, 0,0,0, 10,10,10")
    win.execute("PICK, FACE, 6")
    dlg = form(win, app, "PLANE", "FACE")
    assert dlg.preview.text() == "PLANE, P1, FACE, 6"
    win.execute("PICK, FACE, 1")
    dlg.fields["id"].use_selection()
    assert dlg.preview.text() == "PLANE, P1, FACE, 1"
    dlg.submit(close=False)  # Run keeps it open and offers the next free name
    assert dlg.isVisible() and dlg.fields["name"].value() == "P2"
    assert "P1" in win.processor.model.datums
    dlg.close()


def test_edit_a_history_entry_in_its_form(app, win):
    p = win.processor
    win.execute("! the base\nCYL, 0, 0, 0, 5, 12   ! a post")
    win.execute("COPY, 1, 20")
    dlg = win.open_form("", p.history[0].text, 0)
    pump(app)
    assert dlg.fields["r"].value() == "5"
    dlg.fields["r"].set_value("7")
    assert dlg.submit(close=True)
    assert p.history[0].text == "! the base\nCYL, 0, 0, 0, 7, 12    ! a post"
    assert len(p.history) == 2


def test_form_button_reads_the_typed_line(app, win):
    win.cmdline.setText("TORUS, 0, 0, 5, 12")
    win.form_for_typed()
    pump(app)
    dlg = [d for d in win.findChildren(FormDialog) if d.isVisible()][-1]
    assert dlg.fields["r1"].value() == "12" and dlg.fields["r2"].value() == ""
    assert win.cmdline.text() == ""
    dlg.fields["r2"].set_value("3")
    assert dlg.preview.text() == "TORUS, 0, 0, 5, 12, 3"
    dlg.close()
