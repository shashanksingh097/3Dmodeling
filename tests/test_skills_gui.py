"""Help > Guides (the skill files shown in the help browser) and Help > Assistant skills…"""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings, Qt, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from modeler.ai import skills as sk  # noqa: E402
from modeler.gui import help_browser as hb  # noqa: E402
from modeler.gui.main_window import MainWindow  # noqa: E402
from modeler.gui.skills_dialog import DIRS, OFF  # noqa: E402


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
    sk.configure([], [])
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()


def test_guide_pages_link_commands_both_ways():
    md = hb.guide_markdown("sheet-metal")
    assert "(cmd:FLANGE)" in md and "Commands in this guide" in md and "Example script" in md
    assert any(s.name == "sheet-metal" for s in hb.guides_for("FLANGE"))
    assert "guide:sheet-metal" in hb.page_html("FLANGE")


def test_help_browser_guides(win, app):
    dlg = win.shell.show_guides("enclosure")
    pump(app)
    top = dlg.tree.topLevelItem(0)
    assert top.text(0).startswith(hb.GUIDES) and top.childCount() == len(hb.guides())
    assert dlg.guide == "enclosure" and "SHELL" in dlg.view.toPlainText()
    assert dlg.example_button.isVisible() and dlg.example_button.isEnabled()
    assert not dlg.form_button.isVisible()
    # a command link leaves the guide and brings the command buttons back
    dlg.view.anchorClicked.emit(QUrl("cmd:SHELL"))
    pump(app)
    assert dlg.current == "SHELL" and dlg.guide == "" and dlg.form_button.isVisible()
    assert not dlg.example_button.isVisible()
    dlg.view.anchorClicked.emit(QUrl("guide:enclosure"))
    assert dlg.guide == "enclosure"
    # searching keeps only the guides that match
    dlg.search_box.setText("snap")
    pump(app)
    top = dlg.tree.topLevelItem(0)
    names = [top.child(i).data(0, Qt.UserRole) for i in range(top.childCount())]
    assert "guide:enclosure" in names and "guide:sheet-metal" not in names
    # Open example runs the guide's script in a new model
    dlg.show_guide("modeling-basics")
    win.shell.ask_unsaved = lambda *_: "discard"
    dlg.open_example()
    pump(app, 30)
    assert win.processor.model.bodies
    dlg.close()


def test_ask_the_assistant_names_the_skill(win, app):
    panel = getattr(win, "assistant_panel", None)
    if panel is None:
        win.shell.show_assistant()
        pump(app)
        panel = getattr(win, "assistant_panel", None)
    dlg = win.shell.show_guides("gears-and-cams")
    if panel is None:
        assert not dlg.ask_button.isEnabled()
    else:
        dlg._buttons()
        dlg.ask_assistant()
        assert panel.input.text() == "Using the gears-and-cams skill: "
    dlg.close()


def test_skills_dialog_folders_and_switching_off(win, app, tmp_path):
    mine = tmp_path / "mine" / "my-bracket"
    mine.mkdir(parents=True)
    (mine / "SKILL.md").write_text("---\nname: my-bracket\ndescription: Our bracket. Use for brackets.\n---\n"
                                   "# Bracket\n\n```cmd\nBLOCK, 0, 0, 0, 1, 1, 1\n```\n", encoding="utf-8")
    dlg = win.shell.show_skills()
    pump(app)
    n = dlg.tree.topLevelItemCount()
    assert n == len(sk.discover())
    dlg.add_folder(str(tmp_path / "mine"))
    assert dlg.tree.topLevelItemCount() == n + 1
    rows = {dlg.tree.topLevelItem(i).text(0): dlg.tree.topLevelItem(i) for i in range(n + 1)}
    assert rows["my-bracket"].text(1) == "user"
    rows["sculpting"].setCheckState(0, Qt.Unchecked)
    assert dlg.switched_off() == ["sculpting"]
    assert "All" in dlg.check_text()
    # nothing changes until OK
    assert "my-bracket" not in sk.discover()
    dlg.accept()
    assert win.shell.settings.value(OFF) in (["sculpting"], "sculpting")
    assert str(tmp_path / "mine") in str(win.shell.settings.value(DIRS))
    found = sk.discover()
    assert "my-bracket" in found and "sculpting" not in found
    # the next dialog remembers both, and Remove folder drops the folder
    dlg = win.shell.show_skills()
    assert dlg.folders() == [str(tmp_path / "mine")]
    dlg.dirs.setCurrentRow(0)
    dlg.remove_folder()
    assert dlg.tree.topLevelItemCount() == n
    dlg.close()


def test_why_on_a_failed_step_runs_a_fix(win, app, monkeypatch):
    lines = ["R = 0.3 ! edge radius", "BLOCK, 0,0,0, 20,20,10", "NAME, LAST, box", "SEL, S, FACE, NORMAL, 0, 0, 1",
             "SHELL, 1", "SEL, S, EDGE, BODY, box", "FILLET, R"]
    for line in lines:
        assert win.execute(line).ok
    win.execute('HIST, EDIT, 1, "R = 3 ! edge radius"')
    pump(app)
    p = win.processor
    assert not p.history[6].ok
    dlg = win.history_panel.why(6)
    pump(app)
    assert dlg.windowTitle() == "Why did step 7 fail?"
    assert "largest radius" in dlg.text.toPlainText() and dlg.fix_buttons and dlg.guide_buttons
    dlg.fix_buttons[0].click()
    pump(app)
    assert all(e.ok for e in p.history[:p.cursor]) and not dlg.isVisible()
    # Help > Why did it fail? when nothing failed says so, without a window
    from PySide6.QtWidgets import QMessageBox

    told = []
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: told.append(a[2])))
    assert win.shell.show_why() is None and "no step has failed" in told[0].lower()
    # ... and on a failed typed line it opens
    assert not win.execute("FILET, 2").ok
    dlg = win.shell.show_why()
    assert dlg is not None and "FILLET instead of FILET" in dlg.text.toPlainText()
    g = dlg.guide_buttons[0]
    g.click()
    pump(app)
    dlg.close()


def test_short_first_message_setting(win, app):
    from modeler.gui.skills_dialog import SMALL

    dlg = win.shell.show_skills()
    assert not dlg.small.isChecked()
    dlg.small.setChecked(True)
    dlg.accept()
    assert win.shell.settings.value(SMALL) == "true"
    assert win.shell.show_skills().small.isChecked()
