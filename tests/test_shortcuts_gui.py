"""PLAN item 75: mouse styles in Preferences and the shortcut editor."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402


def _window(path):
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    return MainWindow(autosave="off", settings=QSettings(str(path), QSettings.IniFormat))


def _close(w):
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


@pytest.fixture
def ini(tmp_path):
    return tmp_path / "s.ini"


def test_mouse_style_is_kept_and_put_back(ini):
    from modeler.gui import prefs

    w = _window(ini)
    try:
        dlg = prefs.open_dialog(w)
        i = dlg.mouse.findData("middle-orbit")
        dlg.mouse.setCurrentIndex(i)
        dlg.invert_wheel.setChecked(True)
        assert w.viewport.mouse_style.key == "middle-orbit" and w.viewport.wheel_sign == -1
        assert w.statusBar().currentMessage().startswith("Middle drag: orbit")
        assert "SolidWorks" in dlg.mouse.currentText()
        dlg.close()
    finally:
        _close(w)
    w = _window(ini)
    try:
        assert w.viewport.mouse_style.key == "middle-orbit" and w.viewport.wheel_sign == -1
    finally:
        _close(w)


def test_shortcut_editor_sets_kept_and_reset(ini):
    from modeler.gui import shortcuts

    w = _window(ini)
    try:
        acts = shortcuts.actions(w)
        save_id = "File / Save"
        assert acts[save_id].shortcut() == QKeySequence(QKeySequence.Save)
        shortcuts.set_key(w, save_id, "Ctrl+Shift+F9")
        shortcuts.set_key(w, "Form / BLOCK", "Ctrl+Alt+B")
        assert acts[save_id].shortcut().toString() == "Ctrl+Shift+F9"
        dlg = shortcuts.open_dialog(w)
        dlg.filter.setText("form / block")
        shown = [dlg.table.item(r, 0).text() for r in range(dlg.table.rowCount()) if not dlg.table.isRowHidden(r)]
        assert shown == ["Form / BLOCK"]
        dlg.close()
    finally:
        _close(w)
    w = _window(ini)
    try:
        now = shortcuts.current(w)
        assert now[save_id] == "Ctrl+Shift+F9" and now["Form / BLOCK"] == "Ctrl+Alt+B"
        assert not shortcuts.conflicts(now)
        shortcuts.set_key(w, "Form / CYL", "Ctrl+Alt+B")
        assert shortcuts.conflicts(shortcuts.current(w))["Ctrl+Alt+B"] == ["Form / BLOCK", "Form / CYL"]
        shortcuts.reset(w)
        assert shortcuts.saved(w) == {}
        assert shortcuts.current(w)[save_id] != "Ctrl+Shift+F9"
    finally:
        _close(w)
