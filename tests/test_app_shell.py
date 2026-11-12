"""The desktop-app parts of the window: File and Help menus, unsaved-work
prompt, title bar, recent files, export, and error reporting."""

import os
import sys

import pytest

from modeler.crash import CrashGuard

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler import __version__  # noqa: E402
from modeler.gui.app_shell import examples_dir  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def pump(app, n=10):
    for _ in range(n):
        app.processEvents()


@pytest.fixture
def win(app, tmp_path):
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.IniFormat)
    w = MainWindow(autosave="off", settings=settings)
    w.resize(1000, 700)
    w.show()
    pump(app, 20)
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def menu_titles(win):
    return [a.text().replace("&", "") for a in win.menuBar().actions()]


def test_menus_in_order(win):
    assert menu_titles(win) == ["File", "Commands", "Help"]
    labels = [a.text().replace("&", "") for a in win.shell.file_menu.actions() if a.text()]
    for want in ("New", "Open…", "Open recent", "Open example", "Save", "Save as…", "Import…", "Export…", "Quit"):
        assert want in labels


def test_title_shows_file_and_unsaved_marker(win, app, tmp_path):
    assert win.windowTitle().startswith("Untitled")
    assert not win.isWindowModified()
    win.execute("BLOCK, 0,0,0, 10,10,10")
    assert win.isWindowModified()
    path = str(tmp_path / "part.m3d").replace("\\", "/")
    assert win.execute(f'SAVE, "{path}"').ok
    assert win.windowTitle().startswith("part.m3d")
    assert not win.isWindowModified()
    assert win.shell.recent_files()[0] == os.path.abspath(path)
    win.execute("UNDO")
    assert win.isWindowModified()
    win.execute("REDO")
    assert not win.isWindowModified()  # back to what is saved


def test_close_asks_about_unsaved_work(win, tmp_path):
    asked = []
    win.execute("SPHERE, 0,0,0, 5")
    win.shell.ask_unsaved = lambda title, text: asked.append(text) or "cancel"
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert asked and not ev.isAccepted()

    path = str(tmp_path / "keep.m3d")
    win.shell.save_as = lambda: win.execute(f'SAVE, "{path.replace(chr(92), "/")}"').ok
    win.shell.ask_unsaved = lambda *_: "save"
    ev = QCloseEvent()
    win.closeEvent(ev)
    assert ev.isAccepted() and os.path.isfile(path)


def test_new_and_open_ask_first(win, tmp_path):
    win.execute("BLOCK, 0,0,0, 1,1,1")
    win.shell.ask_unsaved = lambda *_: "cancel"
    win.shell.new()
    assert len(win.processor.model.bodies) == 1
    win.shell.ask_unsaved = lambda *_: "discard"
    win.shell.new()
    assert not win.processor.model.bodies and not win.isWindowModified()


def test_open_recent_and_missing_file(win, tmp_path, monkeypatch):
    path = str(tmp_path / "a.m3d").replace("\\", "/")
    win.execute("CYL, 0,0,0, 2, 5")
    win.execute(f'SAVE, "{path}"')
    win.shell.ask_unsaved = lambda *_: "discard"
    win.shell.new()
    win.shell.open(os.path.abspath(path))
    assert len(win.processor.model.bodies) == 1
    assert not win.isWindowModified()
    gone = str(tmp_path / "gone.m3d")
    win.shell._remember_recent(gone)
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    win.shell.open(gone)
    assert os.path.abspath(gone) not in win.shell.recent_files()


def test_export_by_extension(win, tmp_path):
    win.execute("BLOCK, 0,0,0, 10,10,10")
    for ext in ("step", "stl", "brep"):
        path = str(tmp_path / f"out.{ext}")
        win.shell.export_file(path)
        assert os.path.getsize(path) > 100, ext
    win.shell.export_file(str(tmp_path / "noext"), "STL")
    assert os.path.isfile(str(tmp_path / "noext.stl"))


def test_examples_open_as_new_model(win):
    d = examples_dir()
    assert d is not None
    win.shell.ask_unsaved = lambda *_: "discard"
    win.shell.open_example(os.path.join(d, "flange.cmd"))
    assert win.processor.model.bodies
    assert all(e.ok for e in win.processor.history)


def test_help_dialogs(win, app):
    ref = win.shell.show_command_reference()
    assert "BLOCK" in ref.view.toPlainText()
    ref.search_box.setText("fillet")
    pump(app)
    text = ref.view.toPlainText()
    assert "FILLET" in text and "SPHERE," not in text
    ref.close()
    about = win.shell.show_about()
    assert __version__ in about.view.toPlainText()
    about.close()
    win.shell.show_getting_started().close()


def test_error_in_a_slot_is_reported_not_fatal(win, app, tmp_path):
    guard = CrashGuard(str(tmp_path / "logs"), install=False)
    win.shell.guard = guard
    guard.on_error = win.shell.show_error
    try:
        raise RuntimeError("boom in a button")
    except RuntimeError:
        guard.excepthook(*sys.exc_info())
    assert "boom in a button" in open(guard.errors_path, encoding="utf-8").read()
    assert "INTERNAL ERROR" in win.output.toPlainText()
    assert win.shell.last_error_box.isVisible()
    win.shell.last_error_box.close()
    guard.clean_exit()
