"""What the sweep editor edits, without Qt (so it is tested headless).

A ``SweepEdit`` is opened on one ``SWEEP`` history entry. It reads the entry
back through its form, finds the profile and path as they were just before
that entry, and keeps the twist and scale laws as stations (``t``, value).
The editor's handles move those stations; ``section(t)`` gives the profile
placed at ``t`` (the ghost section the slider moves), ``preview()`` the swept
shape, and ``command()`` the new entry text, which the window sends as
``HIST, EDIT``. So the command stays the one source of truth.
"""

from __future__ import annotations

from ..commands import Processor
from ..commands.processor import CommandError
from ..geometry import curves as cv
from ..geometry import sweep as sw
from ..lang import table
from . import forms as F

LAWS = ("twist", "scale")
DEFAULTS = {"twist": 0.0, "scale": 1.0, "sx": 1.0, "sy": 1.0, "ox": 0.0, "oy": 0.0}
LABELS = {"twist": "Twist (degrees)", "scale": "Scale"}
SAMPLES = 5  # stations made from a law written as a formula, when it is first dragged


class SweepEditError(Exception):
    pass


class SweepEdit:
    def __init__(self, p: Processor, row: int) -> None:
        if not 0 <= row < p.cursor:
            raise SweepEditError(f"no history entry {row + 1}")
        self.p, self.row = p, row
        text = p.history[row].text
        try:
            self.spec, self.variant, self.values = F.parse(text)
        except F.FormError as exc:
            raise SweepEditError(str(exc)) from None
        if self.spec.command != "SWEEP":
            raise SweepEditError("the sweep editor works on SWEEP steps")
        before = p._snaps[row]["model"]
        self.profile = self._wire(before, self.values.get("profile", ""), "profile")
        self.path = self._wire(before, self.values.get("path", ""), "path")
        self.mode = (self.values.get("mode") or "MINTWIST").strip().upper() or "MINTWIST"
        if self.mode not in sw.MODES:
            raise SweepEditError(f"unknown mode {self.mode}")
        self.ps = sw.PathSampler(self.path)
        self._fs = sw.frames(self.ps, 200, self.mode)
        self.stations: dict[str, list[tuple[float, float]]] = {}
        self.formula: dict[str, str] = {}
        for key in LAWS:
            src = (self.values.get(key) or "").strip()
            st = table.parse(src) if src else None
            if st is not None:
                self.stations[key] = st
            else:
                self.formula[key] = src or F._default_text(DEFAULTS[key])
        self._compiled: dict = {}
        self._others = {k: self._law(self.values.get(k) or "", k) for k in ("sx", "sy", "ox", "oy")}

    # ---- reading the entry ------------------------------------------------------
    def _wire(self, snap: dict, ref: str, what: str):
        """The curve ``ref`` named, read as the SWEEP itself read it: in the
        state just before the step (so LAST, LAST-1 and parameters work)."""
        from ..commands.processor import REGISTRY

        p = self.p
        now = p._state()
        p._restore(p._snaps[self.row], emit=False)
        try:
            bid = p._body_arg(REGISTRY["SWEEP"], ref)
            shape = p.model.body(bid).shape
        except Exception as exc:  # noqa: BLE001 - any failure means the curve is not there
            raise SweepEditError(f"the {what} {ref.strip()!r} cannot be found as it was before this step ({exc})") from None
        finally:
            p._restore(now, emit=False)
        try:
            return sw.as_wire(shape, f"the SWEEP {what}")
        except cv.CurveError as exc:
            raise SweepEditError(str(exc)) from None

    def _law(self, src: str, key: str):
        from ..commands.curve_handlers import _Law

        try:
            return _Law(self.p, src or F._default_text(DEFAULTS[key]), f"SWEEP {key}", DEFAULTS[key])
        except CommandError as exc:
            raise SweepEditError(str(exc)) from None

    # ---- laws -------------------------------------------------------------------
    def value(self, key: str, t: float) -> float:
        if key in self.stations:
            return table.value(self.stations[key], t)
        if key in self.formula:
            if key not in self._compiled:
                self._compiled[key] = self._law(self.formula[key], key)
            return self._compiled[key](t)
        return self._others[key](t)

    def law_stations(self, key: str) -> list[tuple[float, float]]:
        """The stations of a law; a formula becomes stations sampled from it."""
        if key not in self.stations:
            f = self._law(self.formula[key], key)
            if f.value is not None:
                st = [(0.0, f.value), (1.0, f.value)]
            else:
                st = [(i / (SAMPLES - 1), f(i / (SAMPLES - 1))) for i in range(SAMPLES)]
            self.stations[key] = [(t, round(v, 4)) for t, v in st]
            self.formula.pop(key, None)
        return self.stations[key]

    def set_station(self, key: str, i: int, t: float | None = None, v: float | None = None) -> None:
        st = list(self.law_stations(key))
        t0, v0 = st[i]
        if t is not None and 0 < i < len(st) - 1:  # the ends stay at 0 and 1
            lo, hi = st[i - 1][0] + 0.01, st[i + 1][0] - 0.01
            t0 = min(max(t, lo), hi)
        if v is not None:
            v0 = v
        if key == "scale" and v0 <= 0.01:
            v0 = 0.01
        st[i] = (round(t0, 4), round(v0, 4))
        self.stations[key] = st

    def add_station(self, key: str, t: float) -> int:
        st = list(self.law_stations(key))
        if any(abs(t - s[0]) < 0.02 for s in st) or not 0 < t < 1:
            raise SweepEditError("too close to another station")
        v = table.value(st, t)
        st.append((round(t, 4), round(v, 4)))
        st.sort()
        self.stations[key] = st
        return [s[0] for s in st].index(round(t, 4))

    def remove_station(self, key: str, i: int) -> None:
        st = list(self.law_stations(key))
        if i in (0, len(st) - 1):
            raise SweepEditError("the stations at the ends stay")
        del st[i]
        self.stations[key] = st

    def law_text(self, key: str) -> str:
        if key in self.stations:
            return table.text(self.stations[key])
        return self.formula[key]

    # ---- geometry ---------------------------------------------------------------
    def section(self, t: float):
        """The profile placed where it is at t (the ghost section)."""
        t = min(max(t, 0.0), 1.0)
        f0, f = self._fs[0], self._fs[round(t * (len(self._fs) - 1))]
        s = self.value("scale", t)
        a, b = s * self.value("sx", t), s * self.value("sy", t)
        if a <= 1e-9 or b <= 1e-9:
            raise SweepEditError(f"the scale must stay above 0 (it is {min(a, b):g} at t = {t:g})")
        M, off = sw._station_matrix(f0, f, self.value("twist", t), a, b, self.value("ox", t), self.value("oy", t), s)
        return sw._apply(self.profile, M, off, abs(a - b) < 1e-12)

    def preview(self):
        """The swept shape with the laws as they are now."""
        laws = [lambda t, k=k: self.value(k, t) for k in ("twist", "scale", "sx", "sy", "ox", "oy")]
        n = int(float(self.values.get("n") or 0))
        solid = (self.values.get("solid") or "1").strip() not in ("0", "0.0")
        try:
            shape, _ = sw.section_sweep([self.profile], self.path, *laws, self.mode, n, solid)
        except cv.CurveError as exc:
            raise SweepEditError(str(exc)) from None
        return shape

    def command(self) -> str:
        vals = dict(self.values)
        for key in LAWS:
            vals[key] = self.law_text(key)
        return F.build(self.spec, vals, self.variant)

    def entry_text(self) -> str:
        """The whole new entry: the command, with the entry's comments kept."""
        return F.replace_code_line(self.p.history[self.row].text, self.command())
