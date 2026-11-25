"""The start page (PLAN item 88): how a new piece of work begins.

Shown when the app starts with nothing to open (Preferences, or the box at
its foot, turns that off) and from File > New. Three columns:

* New: one card per template (New part, New assembly, New sheet metal part,
  New drawing, then the user's own), and an empty project. A card runs
  ``NEW, name``: the template's steps become the first history entries.
* Recent projects, with a small picture of each taken when it was saved.
* Examples to open, and the quick start.

Like the rest of the window it only writes command text (or calls the File
menu's own actions).
"""

from __future__ import annotations

import hashlib
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..commands import template_handlers as th
from . import icons

SETTING = "view/startPage"
THUMB = QSize(160, 110)
_TEMPLATE_ICONS = {"part": "block", "assembly": "mate", "sheet_metal": "sm_sheet", "drawing": "front"}


def thumbs_dir() -> str:
    return os.path.join(os.path.dirname(th.user_dir()), "thumbs")


def thumb_path(project: str) -> str:
    key = hashlib.sha1(os.path.abspath(project).replace("\\", "/").lower().encode("utf-8")).hexdigest()[:16]
    return os.path.join(thumbs_dir(), key + ".png")


def save_thumb(win, project: str) -> str | None:
    """A small picture of the view for the start page's recent list (after SAVE)."""
    vp = getattr(win, "viewport", None)
    if vp is None or not project:
        return None
    try:
        png = vp.snapshot(THUMB.width() * 2, THUMB.height() * 2)
    except Exception:  # noqa: BLE001 - no picture is no harm
        return None
    if not png:
        return None
    path = thumb_path(project)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(png)
    except OSError:
        return None
    return path


def enabled(win) -> bool:
    shell = getattr(win, "shell", None)
    if shell is None:
        return True
    v = shell.settings.value(SETTING, True)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def set_enabled(win, on: bool) -> None:
    shell = getattr(win, "shell", None)
    if shell is not None:
        shell.settings.setValue(SETTING, bool(on))


def example_picture(path: str) -> str | None:
    """The picture the user guide shows for an example script, when there is one."""
    base = os.path.splitext(os.path.basename(path))[0]
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for d in (os.path.dirname(path), os.path.join(here, "docs", "examples")):
        cand = os.path.join(d, base + ".png")
        if os.path.isfile(cand):
            return cand
    return None


class _Card(QFrame):
    """A template: its icon, its title in bold and a line or two on what it is for.
    A frame rather than a button, so the text wraps and the card grows to fit it."""

    clicked = Signal()

    def __init__(self, title: str, about: str, icon: str, tip: str) -> None:
        super().__init__()
        self.setObjectName("start_card")
        self.setFrameShape(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("QFrame#start_card { border: 1px solid palette(mid); border-radius: 6px; }"
                           "QFrame#start_card:hover, QFrame#start_card:focus { border: 1px solid palette(highlight);"
                           " background: palette(alternate-base); }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)
        pic = QLabel()
        pic.setPixmap(icons.icon(icon).pixmap(32, 32))
        pic.setAlignment(Qt.AlignTop)
        lay.addWidget(pic)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(f"<b>{title}</b>")
        a = QLabel(about)
        a.setWordWrap(True)
        a.setEnabled(False)
        for w in (pic, t, a):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            w.setStyleSheet("border: none; background: transparent;")
        col.addWidget(t)
        col.addWidget(a)
        lay.addLayout(col, 1)
        self.setToolTip(tip)
        self.title_label, self.about_label = t, a

    def click(self) -> None:
        self.clicked.emit()

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(e)


class StartPage(QDialog):
    def __init__(self, win) -> None:
        super().__init__(win)
        self.setObjectName("start_page")
        self.setWindowTitle("Start")
        self.win = win
        self.shell = win.shell
        self.resize(1180, 680)
        outer = QVBoxLayout(self)
        head = QLabel("<h2 style='margin:0'>What would you like to make?</h2>")
        outer.addWidget(head)
        cols = QHBoxLayout()
        cols.setSpacing(16)
        outer.addLayout(cols, 1)

        # ---- new, from a template
        newcol = QVBoxLayout()
        newcol.addWidget(QLabel("<b>New</b>"))
        box = QWidget()
        grid = QVBoxLayout(box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.cards: dict[str, _Card] = {}
        for t in th.all_templates():
            sets = th._setup_text(t.sets())
            card = _Card(t.title + (" (yours)" if t.source == "user" else ""), t.about or sets,
                         _TEMPLATE_ICONS.get(t.name, "commands"), f"Sets {sets}\nRuns: NEW, {t.name}")
            card.clicked.connect(lambda _=False, n=t.name: self.new_from(n))
            grid.addWidget(card)
            self.cards[t.name] = card
        empty = _Card("Empty project", "Nothing set up: millimetres and the three base planes.", "clear",
                      "Runs: NEW")
        empty.clicked.connect(lambda: self.new_from(""))
        grid.addWidget(empty)
        self.cards[""] = empty
        grid.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(box)
        newcol.addWidget(scroll, 1)
        own = QLabel("Your own: set a project up, then <i>TEMPLATE, SAVE, name</i> (or the button below).")
        own.setWordWrap(True)
        own.setEnabled(False)
        newcol.addWidget(own)
        save_t = QPushButton("Save this project as a template…")
        save_t.setToolTip("Keep the steps of the project open now as a template for new ones.\n"
                          "Runs: TEMPLATE, SAVE, name")
        save_t.clicked.connect(self.save_template)
        save_t.setEnabled(self.win.processor.cursor > 0)
        newcol.addWidget(save_t)
        cols.addLayout(newcol, 6)

        # ---- recent projects
        rec = QVBoxLayout()
        rec.addWidget(QLabel("<b>Recent projects</b>"))
        self.recent = QListWidget()
        self.recent.setObjectName("start_recent")
        self.recent.setViewMode(QListWidget.IconMode)
        self.recent.setIconSize(THUMB)
        self.recent.setGridSize(QSize(THUMB.width() + 24, THUMB.height() + 40))
        self.recent.setResizeMode(QListWidget.Adjust)
        self.recent.setMovement(QListWidget.Static)
        self.recent.setWordWrap(True)
        self.recent.itemActivated.connect(self._open_recent)
        self.recent.itemClicked.connect(self._open_recent)
        self._fill_recent()
        rec.addWidget(self.recent, 1)
        cols.addLayout(rec, 5)

        # ---- examples and help
        ex = QVBoxLayout()
        ex.addWidget(QLabel("<b>Examples</b>"))
        self.examples = QListWidget()
        self.examples.setObjectName("start_examples")
        self.examples.setIconSize(QSize(48, 34))
        self.examples.itemActivated.connect(self._open_example)
        self.examples.itemClicked.connect(self._open_example)
        self._fill_examples()
        ex.addWidget(self.examples, 1)
        quick = QPushButton("Quick start")
        quick.setToolTip("The first steps: views, picking, sketching and the command line")
        quick.clicked.connect(self._quick_start)
        ex.addWidget(quick)
        cols.addLayout(ex, 4)

        foot = QHBoxLayout()
        self.show_at_start = QCheckBox("Show this page when the app starts")
        self.show_at_start.setChecked(enabled(win))
        self.show_at_start.toggled.connect(lambda on: set_enabled(win, on))
        foot.addWidget(self.show_at_start)
        foot.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        foot.addWidget(buttons)
        outer.addLayout(foot)

    # ---- filling -------------------------------------------------------------------
    def _fill_recent(self) -> None:
        self.recent.clear()
        for path in self.shell.recent_files():
            it = QListWidgetItem(os.path.splitext(os.path.basename(path))[0])
            it.setData(Qt.UserRole, path)
            it.setToolTip(path + ("" if os.path.isfile(path) else "\n(the file is not there any more)"))
            pic = thumb_path(path)
            if os.path.isfile(pic):
                it.setIcon(QIcon(QPixmap(pic)))
            else:
                it.setIcon(icons.icon("open"))
            if not os.path.isfile(path):
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
            self.recent.addItem(it)
        if not self.recent.count():
            it = QListWidgetItem("No recent projects yet: saved projects show up here")
            it.setFlags(Qt.NoItemFlags)
            self.recent.setViewMode(QListWidget.ListMode)
            self.recent.addItem(it)

    def _fill_examples(self) -> None:
        from .app_shell import examples_dir

        d = examples_dir()
        names = sorted(n for n in os.listdir(d) if n.endswith(".cmd")) if d else []
        for n in names:
            path = os.path.join(d, n)
            it = QListWidgetItem(os.path.splitext(n)[0].replace("_", " "))
            it.setData(Qt.UserRole, path)
            it.setToolTip(path)
            pic = example_picture(path)
            if pic:
                it.setIcon(QIcon(QPixmap(pic).scaled(96, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.examples.addItem(it)
        if not names:
            it = QListWidgetItem("No examples found")
            it.setFlags(Qt.NoItemFlags)
            self.examples.addItem(it)

    # ---- actions -------------------------------------------------------------------
    def new_from(self, name: str) -> None:
        if not self.shell.confirm_discard("start a new project"):
            return
        self.accept()
        self.win.execute(f"NEW, {name}" if name else "NEW")
        self.win.execute("FIT")

    def _open_recent(self, it: QListWidgetItem) -> None:
        path = it.data(Qt.UserRole)
        if not path or not os.path.isfile(path):
            return
        self.accept()
        self.shell.open(path)

    def _open_example(self, it: QListWidgetItem) -> None:
        path = it.data(Qt.UserRole)
        if not path:
            return
        self.accept()
        self.shell.open_example(path)

    def _quick_start(self) -> None:
        self.accept()
        self.shell.show_getting_started()

    def save_template(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self, "Save as a template",
                                        "Template name (a word, e.g. my_bracket):")
        if not ok or not name.strip():
            return
        res = self.win.execute(f'TEMPLATE, SAVE, {name.strip()}')
        if res is not None and getattr(res, "ok", False):
            self.accept()
            self.shell.show_start_page()


def show(win) -> StartPage:
    page = StartPage(win)
    page.setModal(True)
    page.show()
    page.raise_()
    return page


