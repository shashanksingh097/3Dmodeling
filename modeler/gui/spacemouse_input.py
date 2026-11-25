"""The 3D mouse in the window (PLAN item 111): reads the device (viewport/spacemouse.py) and moves the
3D view's camera about 60 times a second while the cap is moved; its buttons run commands.

It looks for a device when the window opens and again when the 3D mouse is turned on (Preferences or
SPACEMOUSE, ON). Its settings are kept with the app's settings under "spaceMouse".
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QSocketNotifier, QTimer

from ..viewport import spacemouse as sm

if TYPE_CHECKING:
    from .main_window import MainWindow

SETTING = "spaceMouse"


class SpaceMouseInput(QObject):
    def __init__(self, win: MainWindow) -> None:
        super().__init__(win)
        self.win = win
        self.device = None
        self.notes: list[str] = []
        self.motion = (0.0,) * 6
        self._last = 0.0
        self._notifier = None
        self._poll = QTimer(self)
        self._poll.setInterval(16)
        self._poll.timeout.connect(self._read)
        self._tick = QTimer(self)
        self._tick.setInterval(16)
        self._tick.timeout.connect(self._move)
        self.load()
        win.viewport.spacemouse = self

    # ---- settings ------------------------------------------------------------------------------------
    def _settings(self):
        return getattr(getattr(self.win, "shell", None), "settings", None)

    def load(self) -> None:
        st = self._settings()
        raw = st.value(SETTING, "") if st is not None else ""
        try:
            sm.settings = sm.Settings.from_dict(json.loads(raw)) if raw else sm.Settings()
        except (ValueError, TypeError):
            sm.settings = sm.Settings()

    def save(self) -> None:
        st = self._settings()
        if st is not None:
            st.setValue(SETTING, json.dumps(sm.settings.to_dict()))

    def settings_changed(self) -> None:
        """After Preferences or SPACEMOUSE changed the settings: keep them and start or stop."""
        self.save()
        if sm.settings.on and self.device is None:
            self.start()
        elif not sm.settings.on:
            self.stop()

    # ---- the device ----------------------------------------------------------------------------------
    def start(self) -> bool:
        if self.device is not None or not sm.settings.on:
            return self.device is not None
        self.device, self.notes = sm.find_device()
        if self.device is None:
            return False
        fd = self.device.fileno()
        if fd >= 0:
            self._notifier = QSocketNotifier(fd, QSocketNotifier.Read, self)
            self._notifier.activated.connect(self._read)
        else:
            self._poll.start()
        return True

    def stop(self) -> None:
        self._poll.stop()
        self._tick.stop()
        if self._notifier is not None:
            self._notifier.setEnabled(False)
            self._notifier = None
        if self.device is not None:
            self.device.close()
            self.device = None
        self.motion = (0.0,) * 6

    def status(self) -> dict:
        return {"found": self.device is not None, "via": getattr(self.device, "name", ""),
                "notes": list(self.notes), **sm.settings.to_dict()}

    def _read(self, *_args) -> None:
        try:
            events = self.device.read() if self.device is not None else []
        except OSError as exc:
            self.notes = [f"{getattr(self.device, 'name', 'the 3D mouse')}: {exc}"]
            self.stop()
            return
        for ev in events:
            self.feed(ev)

    def feed(self, ev: tuple) -> None:
        """One event from the device: ("motion", 6 values) or ("button", n, pressed)."""
        if not sm.settings.on:
            return
        if ev[0] == "motion":
            self.motion = tuple(float(v) for v in ev[1])
            if any(abs(v) > 1e-9 for v in self.motion) and not self._tick.isActive():
                self._last = time.monotonic()
                self._tick.start()
        elif ev[0] == "button" and ev[2]:
            cmd = sm.settings.buttons.get(int(ev[1]))
            if cmd:
                self.win.execute(cmd)

    # ---- moving the camera ---------------------------------------------------------------------------
    def _move(self) -> None:
        now = time.monotonic()
        dt, self._last = min(now - self._last, 0.1), now
        if not any(abs(v) > 1e-9 for v in self.motion):
            self._tick.stop()
            return
        self.apply(self.motion, dt)

    def apply(self, motion, dt: float) -> bool:
        vp = self.win.viewport
        if not getattr(vp, "_initialized", False):
            return False
        from OCP.gp import gp_Dir, gp_Pnt

        cam = vp.view.Camera()
        e, c, u = cam.Eye(), cam.Center(), cam.Up()
        eye, center, up, scale = sm.step((e.X(), e.Y(), e.Z()), (c.X(), c.Y(), c.Z()), (u.X(), u.Y(), u.Z()),
                                         cam.Scale(), motion, dt)
        cam.SetEye(gp_Pnt(*eye))
        cam.SetCenter(gp_Pnt(*center))
        cam.SetUp(gp_Dir(*up))
        cam.SetScale(scale)
        vp.view.ZFitAll()
        vp.view.Redraw()
        return True


def attach(win: MainWindow) -> SpaceMouseInput:
    drv = SpaceMouseInput(win)
    if sm.settings.on:
        QTimer.singleShot(0, drv.start)
    return drv
