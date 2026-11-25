"""Every English text of the window, for the language files (PLAN item 76).

Three places are looked at, so a text is not left out because nobody opened its dialog:

* the window itself as it starts (menus, toolbars, docks, ribbon tabs) and the dialogs every
  session has (Preferences, Keyboard shortcuts, a command form);
* every command form: titles, the "How:" choices and field labels (and their help);
* the source code of the window: every plain text given to a label, button, check box, group,
  tab, window title, placeholder or ``i18n.tr`` in ``modeler/gui``.

Commands, keywords and texts with no letters are not words to translate, so they are left out.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

GUI = Path(__file__).resolve().parent.parent / "gui"

# calls whose first (or given) plain-text argument a person reads
_CALLS = {"QLabel": 0, "QPushButton": 0, "QCheckBox": 0, "QGroupBox": 0, "QRadioButton": 0, "QToolButton": -1,
          "QAction": 0, "setWindowTitle": 0, "setPlaceholderText": 0, "setText": 0, "setTitle": 0,
          "setToolTip": 0, "addTab": 1, "addRow": 0, "addButton": 0, "tr": 0, "addMenu": 0, "QDockWidget": 0,
          "QToolBar": 0, "showMessage": 0}


def words(text: str) -> bool:
    """Is it something to translate? (Has letters, and is not a command or keyword in capitals,
    an argument's short name like ``dx`` or ``l2``, a file name or a web address.)"""
    t = text.strip()
    if not re.search(r"[A-Za-z]", t):
        return False
    if re.fullmatch(r"[a-z][a-z0-9_]{0,4}", t) or re.fullmatch(r"\S*[/\\]\S*", t) or t.startswith("http"):
        return False
    if re.fullmatch(r"[A-Z0-9_ ,.()*+\-/=]+", t) and not re.search(r"[a-z]", t) and len(t.split()) <= 3:
        return t in {"OK"}  # BLOCK, SEL, XY ... stay English
    return True


def short(text: str) -> bool:
    from . import SHORT

    return len(text) <= SHORT and "\n" not in text


# what each kind of text is: a label (read at a glance; every language file translates it) or a
# note (tooltips and help; translated when someone has the time, English until then)
_NOTES = {"setToolTip", "showMessage"}


def from_code(root: Path = GUI) -> tuple[set[str], set[str]]:
    out: set[str] = set()
    notes: set[str] = set()
    for f in sorted(root.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else ""
            at = _CALLS.get(name)
            if at is None or at < 0 or len(node.args) <= at:
                continue
            arg = node.args[at]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                (notes if name in _NOTES or not short(arg.value) else out).add(arg.value)
    return {t for t in out if words(t)}, {t for t in notes if words(t)}


def from_forms() -> tuple[set[str], set[str]]:
    from ..gui import forms as F

    out = {"(optional)"}
    notes: set[str] = set()
    for sp in F.specs().values():
        out.add(sp.title)
        notes.add(sp.help)
        for v in sp.variants:
            out.add(v.label)
            notes.add(v.help)
            for f in v.fields:
                out.add(f.label)
                notes.add(f.help)
    return {t for t in out if t and words(t)}, {t for t in notes if t and words(t)}


def from_window() -> tuple[set[str], set[str]]:
    """Start a window (in English, with no plug-ins) and read every text in it and its dialogs."""
    import tempfile

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    from .. import i18n

    app = QApplication.instance() or QApplication([])
    i18n.set_language("en")
    from ..gui import form_dialog as fd
    from ..gui import prefs, shortcuts
    from ..gui.main_window import MainWindow

    with tempfile.TemporaryDirectory() as d:
        w = MainWindow(autosave="off", settings=QSettings(str(Path(d) / "s.ini"), QSettings.IniFormat))
        try:
            found = i18n.collect(w, kinds=True)
            dialogs = [prefs.PreferencesDialog(w), shortcuts.ShortcutDialog(w)]
            dialogs += [fd.FormDialog(w, F_spec(cmd)) for cmd in ("BLOCK", "PLANE")]
            for dlg in dialogs:
                found |= i18n.collect(dlg, kinds=True)
                dlg.deleteLater()
        finally:
            w.shell.ask_unsaved = lambda *_: "discard"
            w.close()
            app.processEvents()
    out = {t for kind, t in found if kind not in i18n.NOTE_KINDS and short(t)}
    notes = {t for kind, t in found if t not in out}
    keep = lambda ts: {t for t in ts if words(t) and not _data(t)}  # noqa: E731
    return keep(out), keep(notes)


def F_spec(cmd):  # noqa: N802
    from ..gui import forms as F

    return F.specs()[cmd]


def _data(text: str) -> bool:
    """Texts that show data, not words: shortcut lists, file names, 'Runs: …' tooltips with commands."""
    return bool(re.search(r"\.(m3d|py|step|stl)\b", text)) or text.startswith(("Form / ",))


def labels_and_notes() -> tuple[set[str], set[str]]:
    """(labels every language file must translate, notes that may stay English for now)."""
    from ..viewport import mouse_styles as ms

    labels: set[str] = set(ms.PHRASES)
    notes: set[str] = set()
    for lab, note in (from_code(), from_forms(), from_window()):
        labels |= lab
        notes |= note
    return labels, notes - labels


def all_sources() -> set[str]:
    labels, notes = labels_and_notes()
    return labels | notes
