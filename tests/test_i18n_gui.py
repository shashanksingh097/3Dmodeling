"""PLAN item 76: the window in other languages. The first test is the "no text is left out"
check: every text of the window must be in each language file, and every label translated.
When it fails after a new button or form: run ``python -m modeler.i18n update`` and translate
what ``python -m modeler.i18n missing`` lists."""

import os
import sys

import pytest

if os.environ.get("MODELER_GUI_TESTS") == "0":
    pytest.skip("GUI tests disabled", allow_module_level=True)
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no X display (run under xvfb-run)", allow_module_level=True)

from PySide6.QtCore import QSettings  # noqa: E402

from modeler import i18n  # noqa: E402


def test_no_text_is_left_out():
    from modeler.i18n.sources import labels_and_notes

    labels, notes = labels_and_notes()
    assert len(labels) > 900
    for lang in i18n.LANGUAGES:
        if lang == "en":
            continue
        have = i18n.read(lang)
        missing = sorted((labels | notes) - set(have))
        assert not missing, f"{lang}.ts lacks {len(missing)} texts, e.g. {missing[:5]} (python -m modeler.i18n update)"
        untranslated = sorted(t for t in labels if not have[t][1])
        assert not untranslated, f"{lang}.ts: {len(untranslated)} labels not translated, e.g. {untranslated[:5]}"


@pytest.fixture
def win(tmp_path):
    from PySide6.QtWidgets import QApplication

    from modeler.gui.main_window import MainWindow

    QApplication.instance() or QApplication([])
    w = MainWindow(autosave="off", settings=QSettings(str(tmp_path / "s.ini"), QSettings.IniFormat))
    yield w
    w.shell.ask_unsaved = lambda *_: "discard"
    w.close()
    i18n.set_language("en")


def _menu_titles(w):
    return [a.text() for a in w.menuBar().actions()]


def test_switching_language_and_back(win):
    from modeler.gui import prefs, shortcuts

    before = _menu_titles(win)
    keys_before = set(shortcuts.current(win))
    prefs.apply_language(win, "de")
    assert "&Datei" in _menu_titles(win)
    assert win.shell.save_action.text() == "&Speichern"
    # names in code and settings stay English: shortcut ids and ribbon tabs
    assert set(shortcuts.current(win)) == keys_before
    rb = win.ribbon
    assert "Home" in rb.visible_titles() and rb.tabText(rb.tab_index("Home")) == "Start"
    rb.select("Model")
    assert rb.current_title() == "Model"
    assert win.statusBar().currentMessage().startswith("Links ziehen: drehen")
    prefs.apply_language(win, "en")
    assert _menu_titles(win) == before
    assert win.statusBar().currentMessage().startswith("Left drag: orbit")


def test_language_is_kept_and_forms_follow(win, tmp_path):
    from modeler.gui import form_dialog as fd
    from modeler.gui import prefs
    from PySide6.QtWidgets import QLabel

    dlg = prefs.open_dialog(win)
    dlg.language.setCurrentIndex(dlg.language.findData("es"))
    assert prefs.current(win, i18n.SETTING, "en") == "es"
    assert dlg.tabs.tabText(0) == "Aspecto"
    dlg.close()
    form = fd.open_form(win, "CYL")
    form.show()
    texts = {lab.text() for lab in form.findChildren(QLabel)}
    assert "Radio" in texts and "Altura" in texts and "Ejecuta:" in texts
    form.close()
