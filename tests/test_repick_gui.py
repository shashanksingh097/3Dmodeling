"""Pick again (PLAN item 51): a pick step whose entity is gone is picked again from the History
menu, with the model rolled back to just before it; clicks then select without adding steps."""

import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QSettings  # noqa: E402

from modeler.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture
def win(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    w = MainWindow(settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat), autosave="off")
    yield w
    w.processor.history.clear()
    w.close()
    app.processEvents()


def test_pick_again_rolls_back_selects_and_rewrites_the_step(win):
    p = win.processor
    for line in ("BLOCK, 0,0,0, 10,10,10", "CYL, 50,0,0, 2, 5", "PICK, FACE, 9", "CM, f"):
        assert win.execute(line).ok
    win.execute("HIST, DELETE, 2")
    assert not p.history[1].ok and "could not be found again" in p.history[1].message
    win.start_repick(2)
    assert p.cursor == 1 and win.repick_step == 2
    win._view_command("PICK, FACE, 6")  # a click: selects, adds no step
    assert p.model.selection == [6] and len(p.history) == 3
    win.finish_repick(True)
    assert win.repick_step is None and p.cursor == 3
    assert p.history[1].text == "PICK, FACE, 6" and all(e.ok for e in p.history)
    assert p.model.named_set("f")[1] == [6]


def test_stop_picking_again_leaves_the_history_as_it_was(win):
    p = win.processor
    for line in ("BLOCK, 0,0,0, 10,10,10", "PICK, FACE, 6", "CM, top"):
        assert win.execute(line).ok
    win.start_repick(2)
    win._view_command("PICK, FACE, 5")
    win.finish_repick(False)
    assert p.cursor == 3 and p.history[1].text == "PICK, FACE, 6"
