"""3D mouse support (PLAN item 111): a 3Dconnexion SpaceMouse or another six-axis cap moves the view.

Pushing, pulling and twisting the cap moves the model the same way (object mode): slide it to pan,
push or pull it to zoom, tilt and spin it to turn the model around the middle of the view. The two
buttons run commands (FIT and VIEW, ISO unless set otherwise).

The device is read in one of two ways, whichever works first:

* the spacenavd service on Linux (its socket, /var/run/spnav.sock), the usual driver there;
* the pyspacemouse package (pip install pyspacemouse, which needs the hidapi library) on Windows,
  macOS or Linux: it reads the device straight from USB.

Settings (on/off, speed, which motions, the axes turned the other way, the strongest axis only,
what the buttons do) are kept with the app's settings; the Preferences window and the SPACEMOUSE
command both change them. :func:`step` is the camera arithmetic alone, so it is tested without a
device.
"""

from __future__ import annotations

import math
import os
import socket
import struct
from dataclasses import dataclass, field

import numpy as np

AXES = ("TX", "TY", "TZ", "RX", "RY", "RZ")
SPNAV_SOCKET = os.environ.get("SPNAV_SOCKET", "/var/run/spnav.sock")
SPNAV_FULL = 350.0  # spacenavd's values run to about this at full deflection


@dataclass
class Settings:
    on: bool = True
    speed: float = 1.0  # 0.1 ... 5
    rotate: bool = True
    pan: bool = True
    zoom: bool = True
    dominant: bool = False  # only the strongest of the six axes counts
    invert: set = field(default_factory=set)  # axes turned the other way: {"RY", "TZ"}
    deadzone: float = 0.06
    buttons: dict = field(default_factory=lambda: {1: "FIT", 2: "VIEW, ISO"})

    def to_dict(self) -> dict:
        return {"on": self.on, "speed": self.speed, "rotate": self.rotate, "pan": self.pan, "zoom": self.zoom,
                "dominant": self.dominant, "invert": sorted(self.invert), "deadzone": self.deadzone,
                "buttons": {str(k): v for k, v in sorted(self.buttons.items())}}

    @classmethod
    def from_dict(cls, d: dict) -> Settings:
        s = cls()
        for k in ("on", "rotate", "pan", "zoom", "dominant"):
            if k in d:
                setattr(s, k, bool(d[k]))
        try:
            s.speed = min(max(float(d.get("speed", 1.0)), 0.1), 5.0)
            s.deadzone = min(max(float(d.get("deadzone", 0.06)), 0.0), 0.5)
        except (TypeError, ValueError):
            pass
        s.invert = {a for a in d.get("invert", []) if a in AXES}
        if isinstance(d.get("buttons"), dict):
            s.buttons = {int(k): str(v) for k, v in d["buttons"].items() if str(k).isdigit()}
        return s

    def text(self) -> list[str]:
        moves = [w for w, on in (("turn", self.rotate), ("pan", self.pan), ("zoom", self.zoom)) if on]
        out = [f"3D mouse {'on' if self.on else 'off'}, speed {self.speed:g}, moves: {', '.join(moves) or 'none'}"]
        if self.dominant:
            out.append("only the strongest axis counts")
        if self.invert:
            out.append("turned the other way: " + " ".join(sorted(self.invert)))
        out.append("buttons: " + "; ".join(f"{k}: {v}" for k, v in sorted(self.buttons.items())))
        return out


settings = Settings()  # the app's one set; the GUI loads and saves it


# ---- the motion ------------------------------------------------------------------------------------

def shape(motion, s: Settings) -> np.ndarray:
    """The six values (-1 ... 1, view axes: right, up, toward the viewer; tilt, spin, roll) after the
    dead zone, the turned-round axes, the motions that are off and the strongest-axis rule."""
    m = np.clip(np.asarray(motion, float).reshape(6), -1.0, 1.0)
    for i, a in enumerate(AXES):
        if a in s.invert:
            m[i] = -m[i]
    # the dead zone, with the rest scaled so the motion starts at nothing
    mag = np.abs(m)
    m = np.where(mag > s.deadzone, np.sign(m) * (mag - s.deadzone) / (1 - s.deadzone), 0.0)
    if not s.pan:
        m[0] = m[1] = 0.0
    if not s.zoom:
        m[2] = 0.0
    if not s.rotate:
        m[3:] = 0.0
    if s.dominant and np.any(m):
        k = int(np.argmax(np.abs(m)))
        m = np.where(np.arange(6) == k, m, 0.0)
    return m


def _rot(axis: np.ndarray, ang: float) -> np.ndarray:
    a = axis / np.linalg.norm(axis)
    c, s_ = math.cos(ang), math.sin(ang)
    x, y, z = a
    return np.array([[c + x * x * (1 - c), x * y * (1 - c) - z * s_, x * z * (1 - c) + y * s_],
                     [y * x * (1 - c) + z * s_, c + y * y * (1 - c), y * z * (1 - c) - x * s_],
                     [z * x * (1 - c) - y * s_, z * y * (1 - c) + x * s_, c + z * z * (1 - c)]])


def step(eye, center, up, scale: float, motion, dt: float, s: Settings | None = None):
    """Move a camera by one time step of 3D mouse motion. ``scale`` is the height the view shows (model
    units). Returns (eye, center, up, scale). The model moves the way the cap is moved."""
    s = s or settings
    m = shape(motion, s) * s.speed
    eye, center, up = (np.asarray(v, float) for v in (eye, center, up))
    if not np.any(m) or dt <= 0:
        return eye, center, up, scale
    look = center - eye
    dist = float(np.linalg.norm(look))
    fwd = look / dist
    up = up - fwd * (up @ fwd)
    up /= np.linalg.norm(up)
    right = np.cross(fwd, up)
    # pan: half the view's height a second at full push; the camera goes the other way to the model
    shift = -(m[0] * right + m[1] * up) * 0.5 * scale * dt
    eye, center = eye + shift, center + shift
    # zoom: pull (toward the viewer) shows more, push shows less: twice as much a second at full
    k = math.exp(m[2] * math.log(2.0) * dt)
    scale *= k
    eye = center - fwd * dist * k
    # turn: up to 90 degrees a second, about the middle of the view
    ang = math.radians(90.0) * dt
    r = _rot(right, -m[3] * ang) @ _rot(up, -m[4] * ang) @ _rot(fwd, -m[5] * ang)
    eye = center + r @ (eye - center)
    up = r @ up
    return eye, center, up, scale


# ---- reading a device ---------------------------------------------------------------------------------

class Spnav:
    """spacenavd's socket (its first, simple protocol): 8 numbers per event."""

    name = "spacenavd"

    def __init__(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(0.5)
        self.sock.connect(SPNAV_SOCKET)
        self.sock.setblocking(False)
        self._buf = b""

    def fileno(self) -> int:
        return self.sock.fileno()

    def read(self) -> list[tuple]:
        """Events waiting: ("motion", 6 values -1 ... 1) or ("button", n, pressed)."""
        try:
            while True:
                got = self.sock.recv(4096)
                if not got:
                    raise OSError("spacenavd closed the connection")
                self._buf += got
        except BlockingIOError:
            pass
        out = []
        while len(self._buf) >= 32:
            pk, self._buf = self._buf[:32], self._buf[32:]
            v = struct.unpack("<8i", pk)
            if v[0] == 0:
                x, y, z, rx, ry, rz = (c / SPNAV_FULL for c in v[1:7])
                out.append(("motion", (x, y, -z, rx, ry, -rz)))  # its z points into the screen
            elif v[0] in (1, 2):
                out.append(("button", v[1] + 1, v[0] == 1))
        return out

    def close(self) -> None:
        self.sock.close()


class Hid:
    """The pyspacemouse package, read straight from USB."""

    name = "pyspacemouse"

    def __init__(self) -> None:
        import pyspacemouse  # optional: pip install pyspacemouse

        self.lib = pyspacemouse
        self.dev = pyspacemouse.open()
        if not self.dev:
            raise OSError("no 3D mouse found over USB")
        self._pressed: list = []

    def fileno(self) -> int:
        return -1

    def read(self) -> list[tuple]:
        st = self.lib.read()
        if st is None:
            return []
        out = [("motion", (st.x, st.z, -st.y, st.pitch, st.yaw, -st.roll))]
        btn = list(getattr(st, "buttons", []) or [])
        for i, b in enumerate(btn):
            was = self._pressed[i] if i < len(self._pressed) else 0
            if b != was:
                out.append(("button", i + 1, bool(b)))
        self._pressed = btn
        return out

    def close(self) -> None:
        try:
            self.lib.close()
        except Exception:  # noqa: BLE001
            pass


def find_device():
    """The first way of reading a 3D mouse that works, and why the others did not (device, notes)."""
    notes = []
    if os.name == "posix" and os.path.exists(SPNAV_SOCKET):
        try:
            return Spnav(), notes
        except OSError as exc:
            notes.append(f"spacenavd: {exc}")
    else:
        notes.append("spacenavd: not running" if os.name == "posix" else "spacenavd: Linux only")
    try:
        return Hid(), notes
    except ImportError:
        notes.append("pyspacemouse: not installed (pip install pyspacemouse)")
    except Exception as exc:  # noqa: BLE001 - any failure of an optional driver is only a note
        notes.append(f"pyspacemouse: {exc}")
    return None, notes
