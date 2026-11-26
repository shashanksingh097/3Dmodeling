"""Window layouts (PLAN item 94): the panels for the job at hand.

``Layouts`` does what the LAYOUT command (commands/layout_handlers.py) asks:
a built-in layout opens its panels, closes the rest, brings the named ones to
the front of their tab group and selects a ribbon tab; a saved one is Qt's
own ``saveState`` plus the ribbon tab, kept in the settings under
``layouts/<name>``. ``reset`` goes back to the state the window was built
with. View > Layout lists them all.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDockWidget

KEY = "layouts/"


class Layouts:
    def __init__(self, win) -> None:
        self.win = win
        self.first = win.saveState()  # the window as built, before the last session's layout comes back
        self.first_tab = "Model"
        self.current = ""

    @property
    def settings(self):
        return getattr(getattr(self.win, "shell", None), "settings", None)

    def docks(self) -> dict[str, QDockWidget]:
        return {d.objectName(): d for d in self.win.findChildren(QDockWidget) if d.parent() is self.win}

    # ---- built in ----------------------------------------------------------------------------
    def apply(self, key: str, spec: dict) -> None:
        docks = self.docks()
        show = set(spec["show"])
        self.win.restoreState(self.first)  # every panel back in its first place, then open/close
        for name, d in docks.items():
            d.setVisible(name in show)
        for name in spec.get("front", ()):
            if name in docks:
                docks[name].raise_()
        self._tab(spec.get("tab", ""), spec.get("tab_else", ""))
        self.current = key
        self._mark()

    def _tab(self, tab: str, fallback: str = "") -> None:
        rb = getattr(self.win, "ribbon", None)
        if rb is None or not tab:
            return
        i = rb.tab_index(tab)
        if i >= 0 and rb.isTabVisible(i):
            rb.setCurrentIndex(i)
        elif fallback:
            rb.select(fallback)

    # ---- saved ---------------------------------------------------------------------------------
    def saved_names(self) -> list[str]:
        s = self.settings
        if s is None:
            return []
        s.beginGroup(KEY.rstrip("/"))
        try:
            names = sorted({k.split("/")[0] for k in s.allKeys()})
        finally:
            s.endGroup()
        return names

    def _find(self, name: str) -> str:
        for n in self.saved_names():
            if n.lower() == name.strip().lower():
                return n
        return ""

    def save(self, name: str) -> None:
        s = self.settings
        if s is None:
            raise RuntimeError("no settings to save layouts in")
        name = self._find(name) or name.strip()
        s.setValue(KEY + name + "/state", self.win.saveState())
        rb = getattr(self.win, "ribbon", None)
        s.setValue(KEY + name + "/tab", rb.current_title() if rb is not None else "")
        s.sync()
        self.current = name
        self._mark()

    def restore(self, name: str) -> bool:
        s = self.settings
        found = self._find(name)
        if s is None or not found:
            return False
        state = s.value(KEY + found + "/state")
        if state is None:
            return False
        self.win.restoreState(state)
        self._tab(str(s.value(KEY + found + "/tab", "") or ""))
        self.current = found
        self._mark()
        return True

    def delete(self, name: str) -> bool:
        s = self.settings
        found = self._find(name)
        if s is None or not found:
            return False
        s.remove(KEY + found)
        s.sync()
        if self.current == found:
            self.current = ""
        self._mark()
        return True

    def reset(self) -> None:
        from ..commands.layout_handlers import DEFAULT_SHOWN

        self.win.restoreState(self.first)
        for d in self.docks().values():
            if d.objectName() != "tutorial":
                d.setVisible(d.objectName() in DEFAULT_SHOWN)
        props = self.docks().get("properties")
        if props is not None:
            props.raise_()
        tut = self.docks().get("tutorial")
        if tut is not None:
            tut.setVisible(self.win.processor.tutorial is not None)
        self._tab(self.first_tab)
        self.current = ""
        self._mark()

    # ---- View > Layout ---------------------------------------------------------------------------
    def build_menu(self, menu) -> None:
        from ..commands.layout_handlers import BUILT_IN

        self.menu = menu.addMenu("&Layout")
        self.menu.setToolTipsVisible(True)
        self.menu.aboutToShow.connect(lambda: self._fill(BUILT_IN))
        self._fill(BUILT_IN)

    def _fill(self, built_in: dict) -> None:
        m = self.menu
        m.clear()
        for key, spec in built_in.items():
            a = m.addAction(key.capitalize())
            a.setCheckable(True)
            a.setChecked(self.current == key)
            a.setToolTip(f"{spec['about']} (LAYOUT, {key})")
            a.triggered.connect(lambda _=False, k=key: self.win.execute(f"LAYOUT, {k}"))
        saved = self.saved_names()
        if saved:
            m.addSeparator()
            for name in saved:
                a = m.addAction(name)
                a.setCheckable(True)
                a.setChecked(self.current == name)
                a.setToolTip(f"your saved layout (LAYOUT, {name})")
                a.triggered.connect(lambda _=False, n=name: self.win.execute(f'LAYOUT, "{n}"'))
        m.addSeparator()
        a = m.addAction("Save this layout…")
        a.setToolTip("Keep the panels as they are now under a name (LAYOUT, SAVE, name)")
        a.triggered.connect(self.ask_save)
        if saved:
            d = m.addMenu("Delete a saved layout")
            for name in saved:
                d.addAction(name).triggered.connect(lambda _=False, n=name: self.win.execute(f'LAYOUT, DELETE, "{n}"'))
        a = m.addAction("Reset")
        a.setToolTip("The panels as the window first opens (LAYOUT, RESET)")
        a.triggered.connect(lambda: self.win.execute("LAYOUT, RESET"))

    def ask_save(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, ok = QInputDialog.getText(self.win, "Save layout", "Name of this layout:")
        if ok and name.strip():
            self.win.execute(f'LAYOUT, SAVE, "{name.strip()}"')

    def _mark(self) -> None:
        win = self.win
        if hasattr(win, "statusBar") and self.current:
            win.statusBar().showMessage(f"Layout: {self.current}", 4000)


def _vertical():
    from PySide6.QtCore import Qt

    return Qt.Vertical
