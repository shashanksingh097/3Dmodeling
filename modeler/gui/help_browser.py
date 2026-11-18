"""Help browser: every command, grouped like the form menu, searchable.

The left side lists the commands under the same headings as the command menu
(gui/forms.CATEGORIES), with "Other" for the rest. The right side shows the
picked command: how to type it, what each argument means, real lines from the
example scripts, and the other commands under the same heading. Command names
on the page are links. "Open form" opens the command's fill-in form and
"Put in command line" types the command name there, ready to finish.

With text in the search box, the right side lists every match instead, the way
the plain command reference did, so a search shows everything at once.
"""

from __future__ import annotations

import glob
import os
import re
from html import escape
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from .main_window import MainWindow

OTHER = "Other"
# headings for commands that have no form, after the command menu's own;
# an empty tuple takes the sketch commands (S..., ENDSKETCH)
EXTRA: list[tuple[str, tuple[str, ...]]] = [
    ("Files and history", ("NEW", "OPEN", "SAVE", "RUN", "NEWPART", "OPENPART", "SAVEPART", "RELOAD",
                           "UNDO", "REDO", "HIST", "STEPS")),
    ("View and picking", ("VIEW", "FIT", "PICK", "PICKMODE", "CPOINTS", "HELP")),
    ("Inside a sketch", ()),
]
MAX_EXAMPLES = 4

_EXAMPLES: dict[str, list[tuple[str, str]]] | None = None


def _commands():
    from ..commands.processor import REGISTRY

    return REGISTRY


def groups() -> list[tuple[str, list[str]]]:
    """(heading, command names) in menu order; every registered command appears once."""
    from .forms import CATEGORIES

    reg = _commands()
    seen: set[str] = set()
    out = []
    for cat, names in CATEGORIES:
        got = [n for n in names if n in reg and n not in seen]
        seen.update(got)
        if got:
            out.append((cat, got))
    rest = sorted(n for n in reg if n not in seen)
    for cat, names in EXTRA:
        got = [n for n in rest if (n in names if names else n.startswith("S") or n == "ENDSKETCH")]
        rest = [n for n in rest if n not in got]
        if got:
            out.append((cat, got))
    if rest:
        out.append((OTHER, rest))
    return out


def heading_of(name: str) -> str:
    for cat, names in groups():
        if name in names:
            return cat
    return OTHER


def examples() -> dict[str, list[tuple[str, str]]]:
    """Command name -> [(script file, line)] from the bundled example scripts."""
    global _EXAMPLES
    if _EXAMPLES is not None:
        return _EXAMPLES
    from .app_shell import examples_dir

    reg = _commands()
    out: dict[str, list[tuple[str, str]]] = {}
    d = examples_dir()
    for path in sorted(glob.glob(os.path.join(d, "*.cmd"))) if d else []:
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for line in lines:
            text = line.split("!")[0].rstrip()
            m = re.match(r"\s*([*/]?[A-Za-z][A-Za-z0-9_]*)\s*(,|$)", text)
            if not m:
                continue
            name = m.group(1).upper()
            if name not in reg:
                continue
            got = out.setdefault(name, [])
            if len(got) < MAX_EXAMPLES and all(t != text.strip() for _, t in got):
                got.append((os.path.basename(path), text.strip()))
    _EXAMPLES = out
    return out


def signature(c) -> str:
    return ", ".join([c.name] + [x.name if x.default is None else f"[{x.name}]" for x in c.args])


def _link(name: str) -> str:
    return f'<a href="cmd:{escape(name)}"><code>{escape(name)}</code></a>'


def matches(c, low: str) -> bool:
    return (not low or low in c.name.lower() or low in c.help.lower()
            or any(low in x.name.lower() or low in (x.help or "").lower() for x in c.args))


def list_html(filt: str = "") -> str:
    """Every command (or every match), each with its signature and help."""
    reg = _commands()
    low = filt.strip().lower()
    parts = []
    for name in sorted(reg):
        c = reg[name]
        if not matches(c, low):
            continue
        args = "".join(f"<li><code>{escape(x.name)}</code>: {escape(x.help)}</li>" for x in c.args if x.help)
        parts.append(f'<h3><a href="cmd:{escape(name)}"><code>{escape(signature(c))}</code></a></h3>'
                     f"<p>{escape(c.help).replace(' · ', '<br>')}</p>"
                     + (f"<ul>{args}</ul>" if args else ""))
    head = (f"<p>{len(parts)} commands. Square brackets mark optional arguments. Click a name for "
            "examples and its form. Type <code>HELP, name</code> in the command line for the same "
            "text, or press F2 with a command typed to fill it in a form.</p>")
    return head + ("".join(parts) or "<p>No command matches.</p>")


def page_html(name: str) -> str:
    """One command: signature, help, arguments, example lines, related commands."""
    from . import forms as F

    reg = _commands()
    c = reg.get(name)
    if c is None:
        return f"<p>No command {escape(name)}.</p>"
    cat = heading_of(name)
    rows = "".join(
        f"<tr><td><code>{escape(x.name)}</code></td>"
        f"<td>{'' if x.default is None else 'optional, default ' + escape(str(x.default))}</td>"
        f"<td>{escape(x.help or '')}</td></tr>" for x in c.args)
    out = [f"<h2><code>{escape(c.name)}</code></h2>",
           f"<p><i>{escape(cat)}</i></p>",
           f"<p><code>{escape(signature(c))}</code></p>",
           f"<p>{escape(c.help).replace(' · ', '<br>')}</p>"]
    if rows:
        out.append('<h3>Arguments</h3><table cellspacing="0" cellpadding="3" border="1">'
                   "<tr><th>Name</th><th>Default</th><th>Meaning</th></tr>" + rows + "</table>")
    ex = examples().get(name, [])
    if ex:
        out.append("<h3>From the examples</h3>"
                   + "".join(f"<pre>{escape(t)}</pre><p><small>{escape(f)}</small></p>" for f, t in ex))
    try:
        F.spec(name)
        out.append("<p>Press <b>Open form</b> to fill it in with the mouse.</p>")
    except F.FormError:
        out.append("<p>This command has no form: the window does it another way, or you type it.</p>")
    sib = [n for g, names in groups() if g == cat for n in names if n != name]
    if sib:
        out.append(f"<h3>Also under {escape(cat)}</h3><p>" + " &nbsp; ".join(_link(n) for n in sib) + "</p>")
    return "".join(out)


class HelpBrowser(QDialog):
    def __init__(self, win: MainWindow | None = None, parent: QWidget | None = None):
        super().__init__(parent or win)
        self.win = win
        self.setWindowTitle("Command reference")
        self.resize(940, 660)
        self.current = ""
        lay = QVBoxLayout(self)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Type to search names, help and arguments, e.g. fillet, hole, sweep")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.textChanged.connect(self.search)
        lay.addWidget(self.search_box)
        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._picked)
        self.tree.itemActivated.connect(self._picked)
        split.addWidget(self.tree)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        split.addWidget(self.view)
        split.setSizes([240, 700])
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        self.form_button = QPushButton("Open form")
        self.form_button.clicked.connect(self.open_form)
        self.type_button = QPushButton("Put in command line")
        self.type_button.clicked.connect(self.put_in_command_line)
        row.addWidget(self.form_button)
        row.addWidget(self.type_button)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        row.addWidget(buttons)
        lay.addLayout(row)
        self._fill_tree("")
        self.view.setHtml(list_html())
        self._buttons()

    # ---- left side ------------------------------------------------------------
    def _fill_tree(self, filt: str) -> None:
        reg = _commands()
        low = filt.strip().lower()
        self.tree.clear()
        for cat, names in groups():
            hits = [n for n in names if matches(reg[n], low)]
            if not hits:
                continue
            top = QTreeWidgetItem([f"{cat} ({len(hits)})"])
            top.setFlags(top.flags() & ~Qt.ItemIsSelectable)
            for n in hits:
                it = QTreeWidgetItem([n])
                it.setData(0, Qt.UserRole, n)
                it.setToolTip(0, reg[n].help.split(". ")[0])
                top.addChild(it)
            self.tree.addTopLevelItem(top)
            top.setExpanded(bool(low))

    def _picked(self, item: QTreeWidgetItem, _col: int = 0) -> None:
        name = item.data(0, Qt.UserRole)
        if name:
            self.show_command(name)
        else:
            item.setExpanded(not item.isExpanded())

    def _link(self, url: QUrl) -> None:
        s = url.toString()
        if s.startswith("cmd:"):
            self.show_command(s[4:])
        else:
            from PySide6.QtGui import QDesktopServices

            QDesktopServices.openUrl(url)

    # ---- right side -----------------------------------------------------------
    def search(self, text: str) -> None:
        self._fill_tree(text)
        self.current = ""
        self.view.setHtml(list_html(text))
        self._buttons()

    def show_command(self, name: str) -> None:
        name = name.upper()
        if name not in _commands():
            return
        self.current = name
        self.view.setHtml(page_html(name))
        self._buttons()
        it = self._item(name)
        if it is not None:
            self.tree.blockSignals(True)
            it.parent().setExpanded(True)
            self.tree.setCurrentItem(it)
            self.tree.blockSignals(False)

    def _item(self, name: str) -> QTreeWidgetItem | None:
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                if top.child(j).data(0, Qt.UserRole) == name:
                    return top.child(j)
        return None

    def _buttons(self) -> None:
        from . import forms as F

        has_form = False
        if self.current:
            try:
                F.spec(self.current)
                has_form = True
            except F.FormError:
                pass
        self.form_button.setEnabled(has_form and self.win is not None)
        self.type_button.setEnabled(bool(self.current) and self.win is not None)

    def open_form(self):
        if self.win is None or not self.current:
            return None
        return self.win.open_form(self.current)

    def put_in_command_line(self) -> None:
        if self.win is None or not self.current:
            return
        self.win.cmdline.setText(f"{self.current}, ")
        self.win.cmdline.setFocus()
