"""The parts of the window that make it a desktop app: the File and Help
menus, recent files, the file name and unsaved-work marker in the title bar,
the question before unsaved work is closed or replaced, window layout kept
between sessions, and the message shown when something goes wrong.

Like every other button, the file actions only build command text (``SAVE``,
``OPEN``, ``NEW``, ``IMPORT``, ``EXPORT``, ``RUN``) and send it to
:meth:`MainWindow.execute`; the dialogs just ask for the file name.
"""

from __future__ import annotations

import os
import platform
import sys
import tempfile
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QMessageBox,
    QTextBrowser,
    QVBoxLayout,
)

from .. import COMMANDS_URL, EXAMPLES_URL, HOME_URL, ISSUES_URL, USER_GUIDE_URL, __version__

if TYPE_CHECKING:
    from ..commands import Result
    from ..crash import CrashGuard
    from .main_window import MainWindow

APP_NAME = "3Dmodeling"
MAX_RECENT = 8
ROOMY_KEY = "layout/roomy"  # set once the window opened with the roomier panels (PLAN item 120)

IMPORT_FILTER = ("All models (*.step *.stp *.iges *.igs *.brep *.scad *.FCStd *.fcstd *.stl *.obj *.3mf *.glb *.gltf *.ply *.off "
                 "*.vtk *.vtu *.msh *.inp *.bdf *.nas *.med *.xdmf *.xyz *.pts *.e57 *.kicad_pcb *.emn *.idf);;"
                 "Circuit boards: KiCad, IDF (*.kicad_pcb *.emn *.idf);;"
                 "Exact shapes (*.step *.stp *.iges *.igs *.brep);;"
                 "OpenSCAD (*.scad);;"
                 "FreeCAD (*.FCStd *.fcstd);;"
                 "Meshes (*.stl *.obj *.3mf *.glb *.gltf *.ply *.off);;"
                 "Point clouds (*.xyz *.pts *.e57 *.ply *.txt *.csv);;"
                 "Simulation meshes (*.vtk *.vtu *.msh *.inp *.bdf *.nas *.med *.xdmf);;All files (*)")
BOARD_EXTS = (".kicad_pcb", ".emn", ".idf")
EXPORT_FILTERS = {
    "STEP (*.step *.stp)": "STEP",
    "IGES (*.iges *.igs)": "IGES",
    "STL mesh (*.stl)": "STL",
    "OBJ mesh (*.obj)": "OBJ",
    "3MF for 3D printing (*.3mf)": "3MF",
    "glTF binary (*.glb)": "GLTF",
    "glTF text (*.gltf)": "GLTF",
    "BREP, Open CASCADE (*.brep)": "BREP",
    "VRML (*.wrl)": "VRML",
    "AMF for 3D printing (*.amf)": "AMF",
    "Web page with a 3D viewer (*.html)": "HTML",
}
_EXT_FORMAT = {".step": "STEP", ".stp": "STEP", ".stl": "STL", ".brep": "BREP",
               ".iges": "IGES", ".igs": "IGES", ".obj": "OBJ", ".3mf": "3MF", ".glb": "GLTF",
               ".gltf": "GLTF", ".ply": "PLY", ".off": "OFF", ".vtk": "VTK", ".vtu": "VTK",
               ".xyz": "XYZ", ".pts": "PTS", ".e57": "E57", ".txt": "XYZ", ".csv": "XYZ",
               ".scad": "SCAD", ".fcstd": "FCSTD", ".wrl": "VRML", ".vrml": "VRML", ".amf": "AMF",
               ".html": "HTML", ".htm": "HTML"}
_DEFAULT_EXT = {"STEP": ".step", "IGES": ".igs", "STL": ".stl", "BREP": ".brep", "OBJ": ".obj",
                "3MF": ".3mf", "GLTF": ".glb", "VRML": ".wrl", "AMF": ".amf", "HTML": ".html"}


def _quote(path: str) -> str:
    return '"' + path.replace("\\", "/") + '"'


def examples_dir() -> str | None:
    """Example scripts: bundled with the package, or the repository's scripts/."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in (os.path.join(here, "examples"), os.path.join(os.path.dirname(here), "scripts")):
        if os.path.isdir(d) and any(n.endswith(".cmd") for n in os.listdir(d)):
            return d
    return None


def versions() -> dict[str, str]:
    from importlib import metadata

    import PySide6

    def dist(name: str) -> str:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            return "unknown"

    return {
        "3Dmodeling": __version__,
        "Python": platform.python_version(),
        "PySide6": PySide6.__version__,
        "Open CASCADE (OCP)": dist("cadquery-ocp"),
        "numpy": dist("numpy"),
        "System": f"{platform.system()} {platform.release()} {platform.machine()}",
    }


class AppShell:
    """File handling, menus and error reporting for one :class:`MainWindow`."""

    def __init__(self, win: "MainWindow", settings: QSettings | None = None,
                 guard: "CrashGuard | None" = None) -> None:
        self.win = win
        self.p = win.processor
        self.guard = guard
        # Without settings from the app (tests, embedding) nothing is kept
        # between sessions: a private file in the temp folder is used.
        self.keep_layout = settings is not None
        self.settings = settings or QSettings(
            os.path.join(tempfile.gettempdir(), f"modeler3d-session-{os.getpid()}.ini"), QSettings.IniFormat)
        self._saved_script = self.p.script()
        # (title, text) -> "save" | "discard" | "cancel". A window made
        # without app settings (scripts, tests) never stops to ask.
        self.ask_unsaved: Callable[[str, str], str] = (
            self._ask_unsaved_dialog if self.keep_layout else (lambda *_: "discard"))
        self.p.listeners.append(self._on_result)
        self.p.history_listeners.append(self.update_title)
        from .skills_dialog import apply_settings

        apply_settings(self.settings)  # the user's own skill folders and the skills switched off
        if guard is not None:
            guard.on_error = self.show_error

    # ---- unsaved work -------------------------------------------------------
    def is_modified(self) -> bool:
        return self.p.script() != self._saved_script

    def mark_saved(self) -> None:
        self._saved_script = self.p.script()
        self.update_title()

    def file_label(self) -> str:
        doc = self.p.part_doc
        if doc is not None:
            where = os.path.basename(doc.file) if doc.file else (doc.where or "not saved")
            return f"part {doc.name} ({where})"
        return os.path.basename(self.p.project_path) if self.p.project_path else "Untitled"

    def update_title(self) -> None:
        self.win.setWindowTitle(f"{self.file_label()}[*] — {APP_NAME}")
        self.win.setWindowModified(self.is_modified())

    def _ask_unsaved_dialog(self, title: str, text: str) -> str:
        box = QMessageBox(QMessageBox.Warning, title, text,
                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self.win)
        box.setDefaultButton(QMessageBox.Save)
        got = box.exec()
        return {QMessageBox.Save: "save", QMessageBox.Discard: "discard"}.get(got, "cancel")

    def confirm_discard(self, doing: str = "continue") -> bool:
        """True when it is fine to throw the current session away (saved,
        unchanged, or the user said so). Offers to save first."""
        if not self.is_modified():
            return True
        answer = self.ask_unsaved(
            "Unsaved changes",
            f"{self.file_label()} has changes that are not saved.\nSave them before you {doing}?")
        if answer == "save":
            return self.save()
        return answer == "discard"

    # ---- file actions ---------------------------------------------------------
    def new(self) -> None:
        if self.confirm_discard("start a new model"):
            self.win.execute("NEW")

    def show_start_page(self):
        """The start page: new from a template, recent projects, examples (PLAN item 88)."""
        from . import start_page

        self.start_page = start_page.show(self.win)
        return self.start_page

    def open(self, path: str | None = None) -> None:
        if not self.confirm_discard("open another project"):
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self.win, "Open project", self._start_dir(),
                                                  "Projects (*.m3d);;All files (*)")
        if path:
            if not os.path.isfile(path):
                self._forget_recent(path)
                QMessageBox.warning(self.win, "Open project", f"The file is no longer there:\n{path}")
                return
            self.win.execute(f"OPEN, {_quote(path)}")

    def save(self) -> bool:
        doc = self.p.part_doc
        if doc is not None:  # a part document: write its *PART block
            if doc.file is None and doc.sink is None:
                return self.save_part_as()
            return self.win.execute("SAVEPART").ok
        if not self.p.project_path:
            return self.save_as()
        return self.win.execute("SAVE").ok

    def save_part_as(self) -> bool:
        doc = self.p.part_doc
        start = doc.file or os.path.join(self._start_dir(), f"{doc.name.lower()}.cmd")
        path, _ = QFileDialog.getSaveFileName(self.win, "Save part as", start, "Part files (*.cmd)")
        if not path:
            return False
        return self.win.execute(f"SAVEPART, {_quote(path)}").ok

    def new_part(self, name: str | None = None) -> None:
        if not self.confirm_discard("start a new part"):
            return
        if name is None:
            name, ok = QInputDialog.getText(self.win, "New part", "Name of the part (for example bolt):")
            if not ok or not name.strip():
                return
        self.win.execute(f"NEWPART, {name.strip()}")

    def link_part(self, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self.win, "Link part file", self._start_dir(),
                                                  "Part files (*.cmd);;All files (*)")
        if path:
            self.win.execute(f'LIB, LINK, "{path}"')

    def open_part(self, path: str | None = None, name: str = "") -> None:
        if not self.confirm_discard("open a part"):
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self.win, "Open part", self._start_dir(),
                                                  "Part files (*.cmd);;All files (*)")
        if not path:
            return
        if not name:
            from ..commands.partdoc_handlers import _source_name, part_blocks

            try:
                with open(path, encoding="utf-8") as fh:
                    blocks = part_blocks(fh.read())
            except Exception:  # noqa: BLE001 - OPENPART below says what is wrong
                blocks = []
            if len(blocks) > 1:
                names = [_source_name(b) for b in blocks]
                name, ok = QInputDialog.getItem(self.win, "Open part", "This file holds several parts. Open:",
                                                names, 0, False)
                if not ok:
                    return
        self.win.execute(f"OPENPART, {_quote(path)}" + (f", {name}" if name else ""))

    def save_as(self) -> bool:
        start = self.p.project_path or os.path.join(self._start_dir(), "model.m3d")
        path, _ = QFileDialog.getSaveFileName(self.win, "Save project as", start, "Projects (*.m3d)")
        if not path:
            return False
        if not os.path.splitext(path)[1]:
            path += ".m3d"
        return self.win.execute(f"SAVE, {_quote(path)}").ok

    def import_file(self, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self.win, "Import", self._start_dir(), IMPORT_FILTER)
        if path and os.path.splitext(path)[1].lower() in BOARD_EXTS:  # a circuit board: BOARD (PLAN 103)
            self.win.execute(f"BOARD, {_quote(path)}")
            return
        if path:
            # any other file goes to meshio by its extension (Gmsh, Abaqus, Nastran, ...)
            fmt = _EXT_FORMAT.get(os.path.splitext(path)[1].lower(), "MESH")
            self.win.execute(f"IMPORT, {fmt}, {_quote(path)}")

    def export_file(self, path: str | None = None, fmt: str | None = None) -> None:
        if not self.p.model.bodies:
            QMessageBox.information(self.win, "Export", "There is nothing to export yet: the model has no bodies.")
            return
        if path is None:
            base = os.path.splitext(self.p.project_path or os.path.join(self._start_dir(), "model"))[0]
            path, chosen = QFileDialog.getSaveFileName(self.win, "Export all bodies", base + ".step",
                                                       ";;".join(EXPORT_FILTERS))
            if not path:
                return
            fmt = _EXT_FORMAT.get(os.path.splitext(path)[1].lower()) or EXPORT_FILTERS.get(chosen, "STEP")
        fmt = fmt or _EXT_FORMAT.get(os.path.splitext(path)[1].lower(), "STEP")
        if fmt not in _DEFAULT_EXT:  # read-only formats (PLY, OFF, VTK, point clouds)
            fmt = "STEP"
        if not os.path.splitext(path)[1]:
            path += _DEFAULT_EXT[fmt]
        self.win.execute(f"EXPORT, {fmt}, {_quote(path)}")

    def export_drawing(self, path: str | None = None, views: str = "STANDARD") -> None:
        if not self.p.model.bodies:
            QMessageBox.information(self.win, "Export drawing", "There is nothing to draw yet: the model has no "
                                                                "bodies.")
            return
        if path is None:
            base = os.path.splitext(self.p.project_path or os.path.join(self._start_dir(), "model"))[0]
            path, chosen = QFileDialog.getSaveFileName(self.win, "Export a 2D drawing", base + ".pdf",
                                                       "PDF sheet with title block (*.pdf);;DXF drawing (*.dxf);;"
                                                       "SVG drawing (*.svg)")
            if not path:
                return
            if not os.path.splitext(path)[1]:
                path += ".svg" if "SVG" in chosen else ".dxf" if "DXF" in chosen else ".pdf"
        self.win.execute(f"DRAWING, {_quote(path)}, {views}")

    def render_picture(self, path: str | None = None) -> None:
        if not self.p.model.bodies:
            QMessageBox.information(self.win, "Render picture", "There is nothing to render yet: the model has no "
                                                                "bodies.")
            return
        if path is None:
            base = os.path.splitext(self.p.project_path or os.path.join(self._start_dir(), "model"))[0]
            path, _ = QFileDialog.getSaveFileName(self.win, "Render a picture", base + ".png", "PNG picture (*.png)")
            if not path:
                return
        self.win.execute(f"RENDER, {_quote(path)}, 1600, 1000")

    def run_script(self, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self.win, "Run command script", self._start_dir(),
                                                  "Command scripts (*.cmd);;All files (*)")
        if path:
            self.win.execute(f"RUN, {_quote(path)}")

    def open_example(self, path: str) -> None:
        """An example starts a new model, so the script's history is the whole model."""
        if not self.confirm_discard("open an example"):
            return
        self.win.execute("NEW")
        self.win.execute(f"RUN, {_quote(path)}")
        self.win.execute("FIT")

    def _start_dir(self) -> str:
        if self.p.project_path:
            return os.path.dirname(self.p.project_path)
        recent = self.recent_files()
        return os.path.dirname(recent[0]) if recent else os.path.expanduser("~")

    # ---- recent files -----------------------------------------------------------
    def recent_files(self) -> list[str]:
        value = self.settings.value("recent", [])
        if isinstance(value, str):
            value = [value]
        return [str(v) for v in (value or [])]

    def _remember_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        items = [path] + [r for r in self.recent_files() if os.path.abspath(r) != path]
        self.settings.setValue("recent", items[:MAX_RECENT])

    def _forget_recent(self, path: str) -> None:
        self.settings.setValue("recent", [r for r in self.recent_files() if r != path])

    def _fill_recent(self) -> None:
        menu = self.recent_menu
        menu.clear()
        items = self.recent_files()
        for i, path in enumerate(items, 1):
            act = menu.addAction(f"&{i}  {os.path.basename(path)}")
            act.setToolTip(path)
            act.setStatusTip(path)
            act.triggered.connect(lambda _=False, f=path: self.open(f))
        if items:
            menu.addSeparator()
            menu.addAction("Clear the list", lambda: self.settings.setValue("recent", []))
        else:
            menu.addAction("No recent projects").setEnabled(False)

    # ---- results ----------------------------------------------------------------
    def _on_result(self, res: "Result") -> None:
        if not res.ok or not res.line:
            return
        words = [w.strip() for w in res.line.split(",")]
        name = words[0].upper()
        if name in ("SAVE", "NEW", "NEWPART", "OPENPART", "SAVEPART"):
            if name == "SAVE" and self.p.project_path:
                self._remember_recent(self.p.project_path)
                from . import start_page

                start_page.save_thumb(self.win, self.p.project_path)  # its picture on the start page
            self.mark_saved()
        elif name == "OPEN" and len(words) > 1:
            if words[1].upper().strip('"') == "AUTOSAVE":
                self.update_title()  # recovered work is not saved anywhere yet
            else:
                if self.p.project_path:
                    self._remember_recent(self.p.project_path)
                self.mark_saved()

    # ---- menus --------------------------------------------------------------------
    def _action(self, menu, label: str, slot, shortcut=None, tip: str = "") -> QAction:
        act = QAction(label, self.win)
        if shortcut is not None:
            act.setShortcut(QKeySequence(shortcut))
        if tip:
            act.setStatusTip(tip)
            act.setToolTip(tip)
        act.triggered.connect(lambda _=False: slot())
        menu.addAction(act)
        return act

    def build_file_menu(self) -> None:
        m = self.win.menuBar().addMenu("&File")
        self.file_menu = m
        a = self._action
        self.new_action = a(m, "&New…", self.show_start_page, QKeySequence.New,
                            "Start a new project from a template (part, assembly, sheet metal, drawing, your own) "
                            "or empty; open a recent project or an example. Runs: NEW, template")
        self.new_empty_action = a(m, "New &empty project", self.new, None, "Start an empty model. Runs: NEW")
        self.open_action = a(m, "&Open…", self.open, QKeySequence.Open, "Open a project (.m3d). Runs: OPEN, file")
        tabs = lambda: self.win.project_tabs  # noqa: E731 - made after the menus' owner
        self.new_tab_action = a(m, "New &tab", lambda: tabs().new_tab(), "Ctrl+T",
                                "Another project in a new tab; each tab has its own history and undo")
        self.open_tab_action = a(m, "Open in new ta&b…", lambda: tabs().open_in_new_tab(), "Ctrl+Shift+O",
                                 "Open a project in a new tab, keeping this one open")
        self.close_tab_action = a(m, "&Close tab", lambda: tabs().close_tab(), "Ctrl+W",
                                  "Close the shown tab (asks to save its changes first)")
        self.next_tab_action = a(m, "Next tab", lambda: tabs().next_tab(1), "Ctrl+Tab", "Show the next tab")
        self.prev_tab_action = a(m, "Previous tab", lambda: tabs().next_tab(-1), "Ctrl+Shift+Tab",
                                 "Show the previous tab")
        self.new_part_action = a(m, "New &part…", self.new_part, None,
                                 "Design one part on its own; Save writes it as a part file. Runs: NEWPART, name")
        self.open_part_action = a(m, "Open p&art…", self.open_part, None,
                                  "Open one part of a part file (.cmd) as its steps. Runs: OPENPART, file")
        self.recent_menu = m.addMenu("Open &recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        self._fill_recent()
        self.examples_menu = m.addMenu("Open &example")
        self._fill_examples()
        m.addSeparator()
        self.save_action = a(m, "&Save", self.save, QKeySequence.Save, "Save the project. Runs: SAVE, file")
        self.save_as_action = a(m, "Save &as…", self.save_as, QKeySequence.SaveAs,
                                "Save the project under a new name. Runs: SAVE, file")
        m.addSeparator()
        self.import_action = a(m, "&Import…", self.import_file, "Ctrl+I",
                               "Read STEP, IGES, BREP, STL, OBJ, 3MF, glTF, PLY, VTK and more. "
                               "Runs: IMPORT, format, file")
        self.export_action = a(m, "&Export…", self.export_file, "Ctrl+E",
                               "Write all bodies as STEP, IGES, STL, OBJ, 3MF, glTF or BREP. "
                               "Runs: EXPORT, format, file")
        self.drawing_action = a(m, "Export &drawing…", self.export_drawing, "Ctrl+Shift+E",
                                "A 2D drawing of the bodies (front, top, right and iso views, hidden edges dashed): "
                                "a PDF sheet with a title block, or SVG or DXF at true size. "
                                "Runs: DRAWING, file, views")
        self.render_action = a(m, "&Render picture…", self.render_picture, None,
                               "A nicer picture of the model as the view shows it: ray traced, with shadows, "
                               "reflections and a look from each body's material. Runs: RENDER, file")
        self.link_part_action = a(m, "&Link part file…", self.link_part, None,
                                  "Use the parts of a part file here, following the file: when it changes, every "
                                  "copy updates. Runs: LIB, LINK, file")
        self.reload_action = a(m, "Reload linked parts", lambda: self.win.execute("RELOAD"), None,
                               "Read linked part files again and update the copies (the window also does this by "
                               "itself when a file changes). Runs: RELOAD")
        m.addSeparator()
        a(m, "Run &script…", self.run_script, None, "Run a .cmd script. Runs: RUN, file")
        a(m, "Save &log…", self.win._save_log, None, "Save the history as a script that rebuilds this model")
        m.addSeparator()
        self.quit_action = a(m, "&Quit", self.win.close, QKeySequence.Quit, "Close the app")

    def build_edit_menu(self) -> None:
        """Edit > Copy, Paste, Duplicate (PLAN item 107)."""
        from . import clipboard as cb

        m = self.win.menuBar().addMenu("&Edit")
        self.edit_menu = m
        a = self._action
        self.copy_action = a(m, "&Copy", lambda: cb.copy(self.win), QKeySequence.Copy,
                             "Copy the picked bodies, faces or sketch geometry (also to paste in another project)")
        self.paste_action = a(m, "&Paste", lambda: cb.paste(self.win), QKeySequence.Paste,
                              "Paste copies under the mouse. Runs: COPY (same project), PASTE (from another "
                              "project or faces), or the sketch commands")
        self.duplicate_action = a(m, "&Duplicate", lambda: cb.duplicate(self.win), "Ctrl+D",
                                  "Copies of the picked bodies, faces or sketch geometry beside them. Runs: COPY")

    def _fill_examples(self) -> None:
        menu = self.examples_menu
        d = examples_dir()
        names = sorted(n for n in os.listdir(d) if n.endswith(".cmd")) if d else []
        for n in names:
            path = os.path.join(d, n)
            act = menu.addAction(os.path.splitext(n)[0].replace("_", " "))
            act.setStatusTip(path)
            act.triggered.connect(lambda _=False, f=path: self.open_example(f))
        if not names:
            menu.addAction("No examples found").setEnabled(False)

    def build_help_menu(self) -> None:
        m = self.win.menuBar().addMenu("&Help")
        self.help_menu = m
        a = self._action
        a(m, "&Getting started", self.show_getting_started, QKeySequence.HelpContents,
          "The basics: mouse, command line, forms, saving")
        a(m, "&Command reference", self.help_for_typed, "Ctrl+F1",
          "Every command with its arguments and examples; opens at the command you are typing")
        a(m, "&Tutorials", self.win.show_tutorials, None,
          "Short lessons that check your model as you go: your first part, sketch to solid, fixing a step")
        a(m, "&Guides", self.show_guides, None,
          "Step-by-step guides to whole jobs (sheet metal, enclosures, gears, fixing a failed step ...), "
          "the same ones the assistant uses")
        a(m, "&Find a command…", self.win.form_for_typed, None, "Search commands by name or purpose (Ctrl+K)")
        a(m, "Ask the &assistant", self.show_assistant, "Ctrl+Shift+A",
          "Chat with GitHub Copilot, signed in with your own GitHub account (Copilot Free works too)")
        a(m, "&Why did it fail?…", self.show_why, None,
          "The first failed step in the history (or the last line that failed): the usual fixes, tried on a copy")
        a(m, "Assistant s&kills…", self.show_skills, None,
          "Which skill files the assistant may use, and folders with your own")
        m.addSeparator()
        a(m, "&User guide (web)", lambda: QDesktopServices.openUrl(QUrl(USER_GUIDE_URL)), None, USER_GUIDE_URL)
        a(m, "Every command with an e&xample (web)", lambda: QDesktopServices.openUrl(QUrl(COMMANDS_URL)), None,
          "The command reference on the user guide website, a tested example for every command")
        a(m, "&Examples with pictures (web)", lambda: QDesktopServices.openUrl(QUrl(EXAMPLES_URL)), None,
          "Every example script with a picture of what it makes")
        a(m, "&Report a problem (web)", self.report_problem, None, "Open a new issue, with your versions filled in")
        a(m, "Open the &log folder", self.open_log_folder, None, "Error and crash logs")
        m.addSeparator()
        a(m, "What's &new in this version", self.show_whats_new, None, "What changed in this version")
        a(m, "Check for a ne&w version…", self.check_for_update, None,
          "Ask GitHub whether a newer version is out (Preferences can check when the app starts)")
        a(m, f"&About {APP_NAME}", self.show_about)

    # ---- help ---------------------------------------------------------------------
    def _text_dialog(self, title: str, html: str) -> QDialog:
        dlg = QDialog(self.win)
        dlg.setWindowTitle(title)
        dlg.resize(760, 640)
        lay = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml(html)
        lay.addWidget(view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        dlg.view = view
        dlg.setModal(False)
        dlg.show()
        return dlg

    def show_whats_new(self, since: str = ""):
        from .updates_ui import show_whats_new

        return show_whats_new(self.win, since)

    def check_for_update(self):
        from .updates_ui import check_now

        return check_now(self.win)

    def show_getting_started(self) -> QDialog:
        return self._text_dialog("Getting started", GETTING_STARTED.format(guide=USER_GUIDE_URL))

    def _reference_html(self, filt: str = "") -> str:
        from .help_browser import list_html

        return list_html(filt)

    def help_for_typed(self, *_):
        text = self.win.cmdline.text().strip()
        return self.show_command_reference(text.split(",")[0].strip().upper() if text else "")

    def show_guides(self, name: str = ""):
        """The help browser at its guides (the skill files, ai/skills.py)."""
        from .help_browser import guides

        dlg = self.show_command_reference()
        first = name or next(iter(guides()), "")
        if first:
            dlg.show_guide(first)
        return dlg

    def show_why(self):
        from ..ai.diagnose import DiagnoseError
        from .why_dialog import WhyDialog, diagnose_with_wait

        try:
            result = diagnose_with_wait(self.p)
        except DiagnoseError as exc:
            QMessageBox.information(self.win, "Why did it fail?", str(exc)[0].upper() + str(exc)[1:] + ".")
            return None
        dlg = WhyDialog(self.win, result)
        dlg.setModal(False)
        dlg.show()
        return dlg

    def show_skills(self):
        from .skills_dialog import SkillsDialog

        dlg = SkillsDialog(self.win, self.settings, self.p.project_dir)
        dlg.setModal(False)
        dlg.show()
        return dlg

    def show_command_reference(self, name: str = ""):
        """The help browser (gui/help_browser.py); with a name, open at that command."""
        from .help_browser import HelpBrowser

        dlg = HelpBrowser(self.win)
        if name:
            dlg.show_command(name)
        dlg.setModal(False)
        dlg.show()
        return dlg

    def show_about(self) -> QDialog:
        rows = "".join(f"<tr><td>{k}</td><td><b>{v}</b></td></tr>" for k, v in versions().items())
        logs = self.guard.log_dir if self.guard else "(not kept in this session)"
        html = (f"<h2>{APP_NAME} {__version__}</h2>"
                "<p>A 3D modeler where every click is a command, so any model can also be written, "
                "edited and replayed as a script.</p>"
                f"<table cellspacing=6>{rows}</table>"
                f"<p>Logs: {logs}</p><p><a href='{HOME_URL}'>{HOME_URL}</a></p>")
        return self._text_dialog(f"About {APP_NAME}", html)

    def report_problem(self) -> None:
        from urllib.parse import urlencode

        body = "What happened, and what did you expect?\n\nSteps or the script that shows it:\n\n\n" + \
               "Versions:\n" + "\n".join(f"- {k}: {v}" for k, v in versions().items())
        QDesktopServices.openUrl(QUrl(ISSUES_URL + "/new?" + urlencode({"body": body})))

    def open_log_folder(self) -> None:
        if self.guard is None:
            QMessageBox.information(self.win, "Logs", "Logs are not kept in this session.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.guard.log_dir))

    # ---- errors -----------------------------------------------------------------------
    def show_error(self, summary: str, details: str) -> None:
        """Called by the crash guard for an error that reached the event loop."""
        where = f"\nThe details were saved to {self.guard.errors_path}." if self.guard else ""
        self.win.output.appendPlainText(f"INTERNAL ERROR: {summary}{where}")
        box = QMessageBox(QMessageBox.Critical, "Something went wrong",
                          "The app hit an internal error, but your model is still here and "
                          "the history is unchanged." + where +
                          "\nPlease report it (Help > Report a problem) if it happens again.",
                          QMessageBox.Ok, self.win)
        box.setDetailedText(details)
        box.setModal(False)
        box.show()
        self.last_error_box = box

    def report_last_session(self) -> None:
        if self.guard is None or not self.guard.last_session_crashed:
            return
        msg = ("The last session ended without closing normally (a crash, or the computer shut down). ")
        if self.win.recover_action.isVisible():
            msg += "Press Recover on the toolbar, or type OPEN, AUTOSAVE, to get that work back. "
        msg += f"If it crashed, {self.guard.crash_path} has the details; please report it (Help menu)."
        self.win.output.appendPlainText(msg)
        self.win.statusBar().showMessage("The last session did not close normally: see the Output panel", 15000)

    # ---- window layout and closing ---------------------------------------------------------
    def restore_layout(self) -> None:
        """The window's size and panels as the last session left them."""
        if not self.keep_layout:
            return
        geo = self.settings.value("geometry")
        state = self.settings.value("windowState")
        if geo is not None:
            self.win.restoreGeometry(geo)
        # a window state saved before the roomier layout (PLAN item 120) is not brought back once:
        # the new arrangement shows instead, and is kept from then on
        if state is not None and self.settings.value(ROOMY_KEY):
            self.win.restoreState(state)
        self.settings.setValue(ROOMY_KEY, 1)

    def show_assistant(self) -> None:
        dock = getattr(self.win, "assistant_dock", None)
        if dock is not None:
            dock.show()
            dock.raise_()
            self.win.assistant_panel.input.setFocus()

    def close_event(self, event) -> None:
        if not self.confirm_discard("close"):
            event.ignore()
            return
        panel = getattr(self.win, "assistant_panel", None)
        if panel is not None:
            panel.shutdown()
        if self.keep_layout:
            self.settings.setValue("geometry", self.win.saveGeometry())
            self.settings.setValue("windowState", self.win.saveState())
        self.settings.sync()
        if self.guard is not None:
            self.guard.clean_exit()
        event.accept()


GETTING_STARTED = """
<h2>Getting started</h2>
<p>Everything you do, by mouse or by typing, becomes a line of text in the
<b>History</b> panel. You can edit any step later and the model rebuilds.</p>
<h3>Make something</h3>
<ul>
<li>Click <b>Block…</b>, <b>Cylinder…</b> or <b>Sphere…</b> on the toolbar and fill in the form,
or type a command in the line at the bottom, for example <code>BLOCK, 0,0,0, 40, 30, 10</code>.</li>
<li>The <b>Commands</b> menu has a form for every command. <b>Ctrl+K</b> finds one by name or purpose.
With a command half typed, <b>F2</b> opens its form.</li>
<li>Use <b>Sketch</b> on a flat face, draw with the mouse, then <b>Extrude…</b> or <b>Revolve…</b>.</li>
<li>Names make scripts readable: <code>W = 40</code> sets a parameter that any number can use.
Change it in the <b>Parameters</b> panel and the model follows.</li>
</ul>
<h3>Look around and pick</h3>
<ul>
<li>Left drag orbits, middle or right drag pans, the wheel zooms, <b>F</b> fits the view.</li>
<li>Click picks a face (or edge, vertex, body: choose on the toolbar). Ctrl adds, Alt removes.
Feature buttons such as <b>Hole…</b> or <b>Shell…</b> use what is picked.</li>
</ul>
<h3>Change your mind</h3>
<ul>
<li><b>Undo</b> and <b>Redo</b> are on the toolbar (Ctrl+Z, and Ctrl+Shift+Z or Ctrl+Y).</li>
<li>Double-click a step in History to edit it; right-click it to edit in a form, insert a step before it,
suppress it or delete it.</li>
</ul>
<h3>Keep your work</h3>
<ul>
<li><b>File &gt; Save</b> (Ctrl+S) writes a <code>.m3d</code> project with the whole history.</li>
<li><b>File &gt; Export</b> writes STEP, IGES, STL, OBJ, 3MF, glTF or BREP for other programs; <b>Import</b>
reads those and mesh files such as PLY, VTK and Gmsh (meshes become faceted bodies, or mesh bodies when they are big).</li>
<li>Work is autosaved as you go. After a crash, press <b>Recover</b> on the toolbar.</li>
</ul>
<p>Try <b>File &gt; Open example</b> to see finished models and their scripts
(Help &gt; Examples with pictures shows what each one makes).
The full guide is at <a href="{guide}">{guide}</a>.</p>
"""
