"""Help > Assistant skills…: which skill files the assistant may use, and the user's own folders.

Built-in skills ship with the app (modeler/skills/). A user adds their own in the app's skills folder
(Open my skills folder) or in folders added here; a project's own ``skills`` folder next to its file
counts too. Each skill can be switched off. Kept in the settings as ``assistant/skill_dirs`` and
``assistant/skills_off``; :func:`apply_settings` hands them to ai/skills.py.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..ai import skills as sk

DIRS = "assistant/skill_dirs"
OFF = "assistant/skills_off"


def _list(settings: QSettings, key: str) -> list[str]:
    v = settings.value(key, [])
    if isinstance(v, str):
        v = [v] if v else []
    return [str(x) for x in (v or [])]


def apply_settings(settings: QSettings) -> None:
    sk.configure(_list(settings, DIRS), _list(settings, OFF))


class SkillsDialog(QDialog):
    def __init__(self, parent: QWidget | None, settings: QSettings, project_dir: str = "") -> None:
        super().__init__(parent)
        self.settings = settings
        self.project_dir = project_dir
        self.setWindowTitle("Assistant skills")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Skills are short guides to whole workflows (sheet metal, enclosures, fixing a failed step ...). "
            "The assistant sees their names and loads the one that fits a request. They are only text: "
            "they cannot run anything, and the assistant still proposes every change for you to run."))
        lay.itemAt(0).widget().setWordWrap(True)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Skill", "From", "When to use it"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 190)
        self.tree.setColumnWidth(1, 80)
        lay.addWidget(self.tree, 3)
        lay.addWidget(QLabel("Your own skill folders (each skill is a folder with a SKILL.md):"))
        self.dirs = QListWidget()
        lay.addWidget(self.dirs, 1)
        row = QHBoxLayout()
        self.add_button = QPushButton("Add folder…")
        self.add_button.clicked.connect(self.add_folder)
        self.remove_button = QPushButton("Remove folder")
        self.remove_button.clicked.connect(self.remove_folder)
        self.open_button = QPushButton("Open my skills folder")
        self.open_button.setToolTip(sk.user_dir())
        self.open_button.clicked.connect(self.open_user_dir)
        self.check_button = QPushButton("Check skills")
        self.check_button.setToolTip("Look for mistakes in the skill files (front matter, commands, size)")
        self.check_button.clicked.connect(self.check)
        for b in (self.add_button, self.remove_button, self.open_button, self.check_button):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        for d in _list(settings, DIRS):
            self.dirs.addItem(d)
        self._off = set(_list(settings, OFF))
        self.fill()

    def folders(self) -> list[str]:
        return [self.dirs.item(i).text() for i in range(self.dirs.count())]

    def fill(self) -> None:
        sk.configure(self.folders(), set())
        found = sk.discover(self.project_dir, include_disabled=True)
        sk.configure(_list(self.settings, DIRS), _list(self.settings, OFF))  # until OK
        self.tree.clear()
        for s in found.values():
            it = QTreeWidgetItem([s.name, s.source, s.description])
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Unchecked if s.name in self._off else Qt.Checked)
            it.setToolTip(2, s.description)
            it.setToolTip(0, s.path)
            it.setData(0, Qt.UserRole, s.name)
            self.tree.addTopLevelItem(it)

    def switched_off(self) -> list[str]:
        out = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) != Qt.Checked:
                out.append(it.data(0, Qt.UserRole))
        return out

    def add_folder(self, path: str | None = None) -> None:
        if path is None:
            path = QFileDialog.getExistingDirectory(self, "A folder of skills", os.path.expanduser("~"))
        if path and path not in self.folders():
            self._off = set(self.switched_off())
            self.dirs.addItem(path)
            self.fill()

    def remove_folder(self) -> None:
        row = self.dirs.currentRow()
        if row >= 0:
            self._off = set(self.switched_off())
            self.dirs.takeItem(row)
            self.fill()

    def open_user_dir(self) -> None:
        d = sk.user_dir()
        os.makedirs(d, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def check_text(self) -> str:
        sk.configure(self.folders(), set())
        try:
            found = sk.check_all(self.project_dir, run_example=False)
        finally:
            sk.configure(_list(self.settings, DIRS), _list(self.settings, OFF))
        bad = {k: v for k, v in found.items() if v}
        if not bad:
            return f"All {len(found)} skills read correctly."
        return "\n\n".join(f"{k}:\n  " + "\n  ".join(v) for k, v in bad.items())

    def check(self) -> None:
        QMessageBox.information(self, "Check skills", self.check_text())

    def accept(self) -> None:
        self.settings.setValue(DIRS, self.folders())
        self.settings.setValue(OFF, self.switched_off())
        apply_settings(self.settings)
        super().accept()
