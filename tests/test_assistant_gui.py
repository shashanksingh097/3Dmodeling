"""The Assistant panel: proposals with a Run button, and model reads on the GUI thread.
Copilot itself is not started here (that needs a GitHub sign-in)."""

import os
import sys
import threading

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.ai import copilot as cp  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def win(app, tmp_path):
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    w.resize(1000, 700)
    w.show()
    pump(app, 20)
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_panel_is_there_and_starts_nothing(win, app):
    panel = win.assistant_panel
    win.shell.show_assistant()
    pump(app)
    assert win.assistant_dock.isVisible()
    assert panel.thread is None  # Copilot starts only when the user signs in or asks
    labels = [a.text().replace("&", "") for a in win.shell.help_menu.actions()]
    assert "Ask the assistant" in labels
    if not cp.sdk_available():
        assert not panel.send_button.isEnabled()


def test_run_a_proposal(win, app):
    panel = win.assistant_panel
    panel.show_proposal(cp.Proposal("BLOCK, 0,0,0, 10,10,10\nCYL, 5,5,0, 2, 15", "a block and a pin"))
    pump(app)
    assert panel.proposal_box.isVisibleTo(panel)
    assert "2 commands" in panel.proposal_label.text()
    n = len(win.processor.history)
    panel.run_proposal()
    pump(app)
    assert len(win.processor.history) == n + 2
    assert len(win.processor.model.bodies) == 2
    assert not panel.proposal_box.isVisibleTo(panel)
    win.execute("UNDO")
    assert len(win.processor.model.bodies) == 1


def test_dismiss_a_proposal(win, app):
    panel = win.assistant_panel
    panel.show_proposal(cp.Proposal("SPHERE, 0,0,0, 3", ""))
    panel.clear_proposal()
    assert panel.proposal is None and not win.processor.model.bodies


def test_model_reads_run_on_the_gui_thread(win, app):
    win.execute("BLOCK, 0,0,0, 2,3,4")
    where, answer = [], []

    def read():
        where.append(threading.current_thread() is threading.main_thread())
        return win.processor.evaluate("VOL(1)")

    t = threading.Thread(target=lambda: answer.append(win.assistant_panel.calls.run(read)))
    t.start()
    for _ in range(200):
        pump(app, 1)
        if answer:
            break
        t.join(0.01)
    t.join(5)
    assert answer == [pytest.approx(24.0)] and where == [True]


def test_answers_show_code(win):
    panel = win.assistant_panel
    panel._on_event("message", "Try `BLOCK, 0,0,0, 1,1,1`:\n```\nCYL, 0,0,0, 1, 2\n```")
    html = panel.transcript.toHtml()
    assert "BLOCK, 0,0,0, 1,1,1" in html and "CYL, 0,0,0, 1, 2" in html
    panel._on_event("tool", "describe_body")
    assert "describe_body" in panel.transcript.toPlainText()
