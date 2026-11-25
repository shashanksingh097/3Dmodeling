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
    assert menu_titles(win) == ["File", "Commands", "View", "Help"]
    labels = [a.text().replace("&", "") for a in win.shell.file_menu.actions() if a.text()]
    for want in ("New…", "New empty project", "Open…", "Open recent", "Open example", "Save", "Save as…", "Import…", "Export…", "Quit"):
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


def test_help_browser_pages_examples_and_form(win, app):
    from PySide6.QtCore import QUrl

    from modeler.commands.processor import REGISTRY
    from modeler.gui import help_browser as hb

    # every command sits under exactly one heading
    listed = [n for _, names in hb.groups() for n in names]
    assert sorted(listed) == sorted(REGISTRY)
    assert hb.heading_of("FILLET") == "Features"
    # examples come from the bundled scripts
    assert hb.examples()["CYL"] and all(f.endswith(".cmd") for f, _ in hb.examples()["CYL"])
    ref = win.shell.show_command_reference("fillet")
    text = ref.view.toPlainText()
    assert "Arguments" in text and "Also under Features" in text and "CHAMFER" in text
    assert ref.form_button.isEnabled()
    dlg = ref.open_form()
    assert dlg is not None and dlg.isVisible()
    dlg.close()
    ref.put_in_command_line()
    assert win.cmdline.text() == "FILLET, "
    # links on the page move to another command; a command with no form disables the button
    ref.view.anchorClicked.emit(QUrl("cmd:UNDO"))
    assert ref.current == "UNDO" and not ref.form_button.isEnabled()
    # search fills the tree with matching headings only, expanded
    ref.search_box.setText("thread")
    pump(app)
    heads = [ref.tree.topLevelItem(i).text(0) for i in range(ref.tree.topLevelItemCount())]
    assert any(h.startswith("Features") for h in heads) and not any(h.startswith("Sculpt") for h in heads)
    ref.close()
    win.cmdline.setText("HOLE, B1")
    ref = win.shell.help_for_typed()
    assert ref.current == "HOLE"
    ref.close()
    win.cmdline.clear()


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


def test_new_part_save_and_open_part(win, app, tmp_path):
    labels = [a.text().replace("&", "") for a in win.shell.file_menu.actions() if a.text()]
    assert "New part…" in labels and "Open part…" in labels
    win.shell.new_part("peg")
    assert win.windowTitle().startswith("part peg (not saved)")
    win.execute("D = 4")
    win.execute("CYL, 0,0,0, D/2, 10")
    assert win.isWindowModified()
    pump(app)
    key = win.param_panel.item(0, 0)
    assert key.text() == "D" and key.font().bold()  # a part input
    path = str(tmp_path / "peg.cmd").replace("\\", "/")
    assert win.execute(f'SAVEPART, "{path}"').ok
    assert win.windowTitle().startswith("part peg (peg.cmd)") and not win.isWindowModified()
    win.execute('HIST, EDIT, 1, "D = 6"')
    assert win.shell.save()  # File > Save writes the part file again
    assert "*PART, peg, D=6" in open(path, encoding="utf-8").read()
    win.shell.new()
    win.shell.open_part(path)
    assert win.processor.part_doc.name == "peg" and win.processor.log[0] == "D = 6"


def test_edit_part_from_a_project_writes_back(win, app):
    win.execute("*PART, peg, D=4\n  CYL, 0,0,0, D/2, 10\n*ENDPART")
    win.execute("INST, peg, 0,0,0")
    win.execute("INST, peg, 20,0,0")
    bid = max(win.processor.model.bodies)
    from modeler.gui import body_menu as bm

    item = next(i for i in bm.body_items(win.processor.model, bid) if i.edit_part)
    assert item.label == "Edit part peg…"
    pw = win.edit_part(item.edit_part)
    assert pw is not None and pw.processor.part_doc.sink is not None
    assert pw.windowTitle().startswith("part peg (step 1 of")
    assert pw.execute('HIST, EDIT, 2, "CYL, 0,0,0, D/2, 25"').ok
    assert pw.shell.save()
    assert "D/2, 25" in win.processor.history[0].text
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    for b in win.processor.model.bodies.values():  # both copies follow
        box = Bnd_Box()
        BRepBndLib.Add_s(b.shape, box)
        assert abs(box.CornerMax().Z() - box.CornerMin().Z() - 25) < 0.1
    pw.shell.ask_unsaved = lambda *_: "discard"
    pw.close()


def test_open_linked_part_updates_every_copy(win, app, tmp_path):
    """The M11 exit test without mates: link a bolt file, place copies, open the
    part from one copy, change it, save, and see every copy follow."""
    f = tmp_path / "bolt.cmd"
    f.write_text("*PART, bolt, D=8, L=30\n  CYL, 0, 0, 0, D, 5\n  CYL, 0, 0, -L, D/2, L\n  UNION, 1, 2\n*ENDPART\n",
                 encoding="utf-8")
    win.shell.link_part(str(f))
    for i in range(4):
        assert win.execute(f"INST, bolt, {20 * i}, 0, 0").ok
    p = win.processor
    assert str(f) in win.link_watch.paths()
    bid = max(p.model.bodies)
    from modeler.gui import body_menu as bm

    item = next(i for i in bm.body_items(p.model, bid, p.part_files) if i.edit_part)
    assert item.label == "Open part bolt (bolt.cmd)…"
    pump(app)
    tree_items = win.model_tree.menu_items("part:BOLT")
    assert any(i.label == "Open part bolt (bolt.cmd)…" for i in tree_items)
    win.processor.run(f"PICK, BODY, {bid}")
    pump(app)
    win.item_panel.refresh()
    assert win.item_panel.part_button.text() == "Open part…"
    assert "linked to" in win.item_panel.note.text()

    pw = win.edit_part(item.edit_part)
    assert pw is not None and pw.processor.part_doc.file == str(f)
    q = pw.processor
    row = next(j for j, e in enumerate(q.history) if e.text.startswith("L ="))
    assert pw.execute(f'HIST, EDIT, {row + 1}, "L = 50"').ok
    assert pw.shell.save()
    assert "L=50" in f.read_text(encoding="utf-8")
    pump(app, 20)  # the window re-reads the file after the save
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    assert len(p.model.instances) == 4
    for b in p.model.bodies.values():
        box = Bnd_Box()
        BRepBndLib.Add_s(b.shape, box)
        assert abs(box.CornerMax().Z() - box.CornerMin().Z() - 55) < 0.1
    assert "bolt updated from bolt.cmd" in win.output.toPlainText()
    pw.close()

    # a change made outside the app is picked up when the watcher fires
    f.write_text(f.read_text(encoding="utf-8").replace("L=50", "L=20"), encoding="utf-8")
    assert win.link_watch.check()
    box = Bnd_Box()
    BRepBndLib.Add_s(p.model.bodies[bid].shape, box)
    assert abs(box.CornerMax().Z() - box.CornerMin().Z() - 25) < 0.1
    assert not win.link_watch.check()  # nothing new
