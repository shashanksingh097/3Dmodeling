"""Several projects open at once, in tabs (PLAN item 109).

The window keeps one processor and one model; each tab keeps the rest of a project's state (its
history, undo, parameters, bodies, file name: everything :func:`modeler.core.transfer.processor_state`
holds) while another tab is shown. Switching tabs swaps that state in and redraws every panel and
the view, so each tab has its own history and undo. The tab bar sits above the 3D view and shows
only when more than one project is open.

File > New tab (Ctrl+T) and Open in new tab… add a tab; Ctrl+Tab and Ctrl+Shift+Tab move between
tabs; Ctrl+W closes one (asking to save first). Bodies go from one tab to another with Ctrl+C,
Ctrl+V (a PASTE step there) or, from a body's right-click menu, Copy to ▸ another tab.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QTabBar

from ..core import transfer

if TYPE_CHECKING:
    from .main_window import MainWindow


@dataclass
class Tab:
    state: dict | None = None  # None while it is the one shown (its state is live in the processor)
    saved_script: str = ""  # what was saved, to tell unsaved changes
    camera: object = None  # the view's camera when it was left
    label: str = "Untitled"
    modified: bool = False
    extra: dict = field(default_factory=dict)


class ProjectTabs:
    def __init__(self, win: MainWindow) -> None:
        self.win = win
        self.bar = QTabBar()
        self.bar.setTabsClosable(True)
        self.bar.setMovable(False)
        self.bar.setDocumentMode(True)
        self.bar.setExpanding(False)
        self.tabs: list[Tab] = [Tab()]
        self.bar.addTab("Untitled")
        self.bar.setVisible(False)
        self._switching = False
        self._shown = 0
        self.bar.currentChanged.connect(self._chosen)
        self.bar.tabCloseRequested.connect(self.close_tab)
        win.processor.history_listeners.append(self.refresh_labels)

    # ---- which tab -------------------------------------------------------------------------
    @property
    def current(self) -> int:
        return self.bar.currentIndex()

    def count(self) -> int:
        return len(self.tabs)

    def labels(self) -> list[str]:
        self.refresh_labels()
        return [t.label for t in self.tabs]

    def refresh_labels(self) -> None:
        if self._switching:
            return
        i = self.current
        if 0 <= i < len(self.tabs):
            shell = self.win.shell
            t = self.tabs[i]
            t.label, t.modified = shell.file_label(), shell.is_modified()
            self.bar.setTabText(i, t.label + (" *" if t.modified else ""))
            self.bar.setTabToolTip(i, self.win.processor.project_path or t.label)

    # ---- switching -------------------------------------------------------------------------
    def _store(self, i: int) -> None:
        """Keep the live project's state in tab i."""
        t = self.tabs[i]
        p = self.win.processor
        self.refresh_labels()
        t.state = transfer.processor_state(p)
        t.saved_script = self.win.shell._saved_script
        t.camera = self._camera()

    def _load(self, i: int) -> None:
        """Make tab i's state live and redraw everything."""
        t = self.tabs[i]
        p = self.win.processor
        state, t.state = t.state, None
        if state is None:  # a new tab: an empty project
            from ..commands import Processor

            state = transfer.processor_state(Processor())
            t.saved_script = state["p"].get("saved_script", "") or ""
        transfer.set_processor_state(p, state)
        self.win.shell._saved_script = t.saved_script
        p.model.restore(p.model.snapshot())  # every panel and the view redraw from this model
        p._history_changed()
        if t.camera is not None:
            self._set_camera(t.camera)
        self.win.shell.update_title()

    def _chosen(self, i: int) -> None:
        if self._switching or i < 0 or i == self._shown:
            self._shown = i
            return
        self.switch(i, from_bar=True)

    def switch(self, i: int, from_bar: bool = False) -> None:
        """Show tab i."""
        shown = self._shown
        if not (0 <= i < len(self.tabs)) or (i == shown and not from_bar):
            return
        if self.win.offload.busy:
            self.win.statusBar().showMessage("A rebuild is running: wait for it before changing tabs", 4000)
            self._set_bar(shown)
            return
        self._switching = True
        try:
            self._store(shown)
            self._set_bar(i)
            self._shown = i
            self._load(i)
        finally:
            self._switching = False
        self.refresh_labels()

    def _set_bar(self, i: int) -> None:
        old = self._switching
        self._switching = True
        self.bar.setCurrentIndex(i)
        self._switching = old

    def new_tab(self) -> int:
        """A new tab with an empty project; returns its index."""
        self.tabs.append(Tab())
        self.bar.addTab("Untitled")
        self.bar.setVisible(True)
        self.switch(len(self.tabs) - 1)
        return len(self.tabs) - 1

    def open_in_new_tab(self, path: str | None = None) -> None:
        shown = self.current
        self.new_tab()
        self.win.shell.open(path)
        if not self.win.processor.project_path and not self.win.processor.history:
            self.close_tab(self.current, ask=False)  # nothing was opened
            self.switch(shown)

    def next_tab(self, step: int = 1) -> None:
        if len(self.tabs) > 1:
            self.switch((self.current + step) % len(self.tabs))

    def close_tab(self, i: int | None = None, ask: bool = True) -> bool:
        """Close tab i (default: the shown one), asking to save its changes. The last tab stays."""
        i = self.current if i is None else i
        if len(self.tabs) <= 1 or not (0 <= i < len(self.tabs)):
            return False
        if i != self.current:
            self.switch(i)
        if ask and not self.win.shell.confirm_discard("close this tab"):
            return False
        nxt = i - 1 if i > 0 else 1
        self.switch(nxt)  # its state goes back into its tab
        self._switching = True
        try:
            del self.tabs[i]
            self.bar.removeTab(i)
            self._shown = self.bar.currentIndex()
        finally:
            self._switching = False
        self.bar.setVisible(len(self.tabs) > 1)
        self.refresh_labels()
        return True

    def unsaved_elsewhere(self) -> list[str]:
        """Labels of tabs other than the shown one with unsaved changes."""
        self.refresh_labels()
        return [t.label for k, t in enumerate(self.tabs) if k != self.current and t.modified]

    def confirm_close_all(self) -> bool:
        """Before the window closes: each tab with unsaved changes is shown and asked about."""
        for k in range(len(self.tabs)):
            if k == self.current:
                continue
            if self.tabs[k].modified:
                self.switch(k)
                if not self.win.shell.confirm_discard("close the window"):
                    return False
        return True

    # ---- bodies to another tab --------------------------------------------------------------
    def copy_to(self, bids: list[int], k: int) -> bool:
        """Copy bodies of the shown tab into tab k, where they stand (a PASTE step there)."""
        from ..commands import clip_handlers as ch

        if not (0 <= k < len(self.tabs)) or k == self.current:
            return False
        data = ch.copy_bodies(self.win.processor, list(bids))
        self.switch(k)
        lines = ch.paste_lines(self.win.processor, data, (0.0, 0.0, 0.0))
        res = self.win.execute("\n".join(lines))
        return res.ok

    # ---- the view's camera ----------------------------------------------------------------------
    def _camera(self):
        v = getattr(self.win.viewport, "view", None)
        if v is None:
            return None
        try:
            from OCP.Graphic3d import Graphic3d_Camera

            cam = Graphic3d_Camera()
            cam.Copy(v.Camera())
            return cam
        except Exception:  # noqa: BLE001 - no camera kept rather than no tab
            return None

    def _set_camera(self, cam) -> None:
        v = getattr(self.win.viewport, "view", None)
        if v is None:
            return
        try:
            v.Camera().Copy(cam)
            v.Redraw()
        except Exception:  # noqa: BLE001
            pass
