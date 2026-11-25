"""The window in other languages (PLAN item 76).

Every text a person reads in the window (menus, buttons, tabs, form labels, dialog texts,
tooltips) can be shown in another language. Commands, their keywords and what they print stay
in English, so a script or a saved project works in every language and the assistant reads
the same words everywhere.

How it works:

* Language files are Qt Linguist files (``modeler/i18n/<lang>.ts``), so translators can use
  Qt Linguist or any text editor. ``python -m modeler.i18n update`` adds every new text of the
  window to each file (as *unfinished*), and the tests fail when a text is missing from them.
* :func:`retranslate` walks a window and swaps each text for its translation, keeping the
  English one on the widget, so switching language again (or back) works at once. An event
  filter does it for every window and menu as it opens, so dialogs and menus built later are
  translated too. Text that holds data (a body's name, a number, what a command printed) is
  never in a language file, so it is never changed.
* :func:`tr` is for texts code makes itself (message boxes, status bar messages).
* A :class:`Translator` is put on the application, so Qt's own texts (OK, Cancel, Close ...)
  come from Qt's language files and anything using ``QCoreApplication.translate`` finds ours.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONTEXT = "modeler"
LANGUAGES = {"en": "English", "de": "Deutsch", "es": "Español"}
SETTING = "language"
SHORT = 80  # longer texts (tooltips, help) may stay unfinished in a language file

_table: dict[str, str] = {}
_lang = "en"
_SRC = "i18n_src"  # widget/action property names that keep the English text
_filter = None
_qt_translator = None
_our_translator = None


# ---- language files ----------------------------------------------------------------------------

def path(lang: str) -> Path:
    return HERE / f"{lang}.ts"


def read(lang: str) -> dict[str, tuple[str, bool]]:
    """A language file: English text -> (translation, finished)."""
    p = path(lang)
    if not p.exists():
        return {}
    out: dict[str, tuple[str, bool]] = {}
    for msg in ET.parse(p).getroot().iter("message"):
        src = msg.findtext("source") or ""
        t = msg.find("translation")
        text = (t.text or "") if t is not None else ""
        done = t is not None and t.get("type") not in ("unfinished", "obsolete", "vanished") and bool(text)
        out[src] = (text, done)
    return out


def write(lang: str, entries: dict[str, tuple[str, bool]]) -> None:
    root = ET.Element("TS", version="2.1", language=lang)
    ctx = ET.SubElement(root, "context")
    ET.SubElement(ctx, "name").text = CONTEXT
    for src in sorted(entries, key=lambda s: (s.lower(), s)):
        text, done = entries[src]
        m = ET.SubElement(ctx, "message")
        ET.SubElement(m, "source").text = src
        t = ET.SubElement(m, "translation")
        t.text = text
        if not done:
            t.set("type", "unfinished")
    ET.indent(root, "    ")
    body = ET.tostring(root, encoding="unicode")
    path(lang).write_text('<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE TS>\n' + body + "\n", encoding="utf-8")


def update(sources: set[str]) -> dict[str, int]:
    """Add every text in ``sources`` to each language file (unfinished), drop texts no longer used.
    Returns language -> how many texts were added."""
    added = {}
    for lang in LANGUAGES:
        if lang == "en":
            continue
        have = read(lang)
        new = {s: have.get(s, ("", False)) for s in sources}
        added[lang] = len(set(sources) - set(have))
        write(lang, new)
    return added


# ---- the language in use -----------------------------------------------------------------------

def language() -> str:
    return _lang


def set_language(lang: str) -> None:
    """Use a language (one of LANGUAGES) for :func:`tr` and :func:`retranslate`."""
    global _lang, _table
    if lang not in LANGUAGES:
        lang = "en"
    _lang = lang
    _table = {} if lang == "en" else {s: t for s, (t, done) in read(lang).items() if done}
    _install_qt(lang)


def tr(text: str) -> str:
    """``text`` in the language in use (itself when there is no translation)."""
    if not _table or not text:
        return text
    hit = _table.get(text)
    if hit is not None:
        return hit
    core, tail = _split_tail(text)
    if core != text and core in _table:
        return _table[core] + tail
    return text


def _split_tail(text: str) -> tuple[str, str]:
    """'Save as…' -> ('Save as', '…'), 'Theme:' -> ('Theme', ':'); the ending is kept."""
    m = re.match(r"^(.*?)(\s*(?:…|\.\.\.|:))$", text, re.S)
    return (m.group(1), m.group(2)) if m and m.group(1) else (text, "")


def _install_qt(lang: str) -> None:
    """Qt's own texts (standard buttons, the key sequence box ...) in the same language."""
    global _qt_translator, _our_translator
    try:
        from PySide6.QtCore import QCoreApplication, QLibraryInfo, QTranslator
    except ImportError:  # pragma: no cover - headless use without Qt
        return
    app = QCoreApplication.instance()
    if app is None:
        return
    for t in (_qt_translator, _our_translator):
        if t is not None:
            app.removeTranslator(t)
    _qt_translator = _our_translator = None
    if lang == "en":
        return
    qt = QTranslator()
    if qt.load(f"qtbase_{lang}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(qt)
        _qt_translator = qt

    class Translator(QTranslator):
        def translate(self, context, source, disambiguation=None, n=-1):  # noqa: ARG002
            return _table.get(source) or None

        def isEmpty(self) -> bool:
            return not _table

    ours = Translator()
    app.installTranslator(ours)
    _our_translator = ours


# ---- the window --------------------------------------------------------------------------------

def _texts(obj):
    """(name, get, set) for every text on a widget or action that a person reads."""
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (QAbstractButton, QComboBox, QDockWidget, QGroupBox, QLabel, QLineEdit, QMenu,
                                   QTableWidget, QTabWidget, QToolBar, QTreeWidget, QWidget)

    if isinstance(obj, QAction):
        yield "text", obj.text, obj.setText
        yield "icon", obj.iconText, obj.setIconText  # what toolbar buttons show (when set apart from text)
        yield "tip", obj.toolTip, obj.setToolTip
        yield "status", obj.statusTip, obj.setStatusTip
        return
    if not isinstance(obj, QWidget):
        return
    if isinstance(obj, QMenu):
        yield "title", obj.title, obj.setTitle
    elif isinstance(obj, (QAbstractButton, QLabel)):
        yield "text", obj.text, obj.setText
    elif isinstance(obj, QGroupBox):
        yield "title", obj.title, obj.setTitle
    elif isinstance(obj, QLineEdit):
        yield "placeholder", obj.placeholderText, obj.setPlaceholderText
    if isinstance(obj, (QDockWidget, QToolBar)) or obj.isWindow():
        yield "window", obj.windowTitle, obj.setWindowTitle
    if not isinstance(obj, QAction):
        yield "wtip", obj.toolTip, obj.setToolTip
    if isinstance(obj, QTabWidget):
        for i in range(obj.count()):
            yield f"tab{i}", (lambda i=i: obj.tabText(i)), (lambda v, i=i: obj.setTabText(i, v))
    if isinstance(obj, QComboBox):  # only combos that show labels for keys (item data) are words to read
        for i in range(obj.count()):
            if obj.itemData(i) is not None:
                yield f"item{i}", (lambda i=i: obj.itemText(i)), (lambda v, i=i: obj.setItemText(i, v))
    if isinstance(obj, QTableWidget):
        for i in range(obj.columnCount()):
            it = obj.horizontalHeaderItem(i)
            if it is not None:
                yield f"head{i}", it.text, it.setText
    if isinstance(obj, QTreeWidget):
        h = obj.headerItem()
        for i in range(obj.columnCount()):
            yield f"head{i}", (lambda i=i: h.text(i)), (lambda v, i=i: h.setText(i, v))


def _objects(root):
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QWidget

    yield root
    if isinstance(root, QWidget):
        yield from root.findChildren(QWidget)
        yield from root.findChildren(QAction)


def english(obj, name: str, now: str) -> str:
    """The English text behind a translated one (``now`` when it was never translated)."""
    kept = obj.property(f"{_SRC}_{name}")
    return str(kept) if kept is not None and obj.property(f"{_SRC}_{name}_as") == now else now


def _keep(obj, name: str, src: str, shown: str) -> None:
    obj.setProperty(f"{_SRC}_{name}", src)
    obj.setProperty(f"{_SRC}_{name}_as", shown)
    # Qt copies some texts to an action of its own: a menu's entry in its parent menu, and a
    # dock's or toolbar's entry in the View menu. They keep the same English text.
    if name == "title" and hasattr(obj, "menuAction"):
        _keep(obj.menuAction(), "text", src, shown)
    elif name == "window" and hasattr(obj, "toggleViewAction"):
        _keep(obj.toggleViewAction(), "text", src, shown)


def retranslate(root) -> int:
    """Put every text under ``root`` in the language in use. Returns how many changed."""
    changed = 0
    for obj in _objects(root):
        try:
            for name, get, put in _texts(obj):
                now = get()
                if not now:
                    continue
                src = english(obj, name, now)
                want = tr(src)
                if want != now:
                    put(want)
                    changed += 1
                _keep(obj, name, src, want)
        except RuntimeError:  # deleted while walking
            continue
    return changed


NOTE_KINDS = {"tip", "status", "wtip"}  # tooltips: notes, not labels


def collect(root, kinds: bool = False) -> set:
    """Every English text under ``root`` (what :func:`retranslate` would look up); with ``kinds``,
    (kind, text) pairs, where a kind in NOTE_KINDS is a tooltip."""
    out: set = set()
    for obj in _objects(root):
        try:
            for name, get, _put in _texts(obj):
                now = get()
                if now:
                    t = english(obj, name, now)
                    out.add(("tip" if name in NOTE_KINDS else "text", t) if kinds else t)
        except RuntimeError:
            continue
    return out


def watch(app) -> None:
    """Translate every window and menu as it opens (dialogs and menus made later included)."""
    global _filter
    from PySide6.QtCore import QEvent, QObject

    if _filter is not None:
        return

    class _Filter(QObject):
        def eventFilter(self, obj, ev):  # noqa: N802 - Qt name
            if _table and ev.type() == QEvent.Show and getattr(obj, "isWindow", lambda: False)():
                retranslate(obj)
            return False

    _filter = _Filter(app)
    app.installEventFilter(_filter)
