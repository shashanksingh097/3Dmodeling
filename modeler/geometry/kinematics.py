"""Motion studies (PLAN item 105): positions, speeds and accelerations of points on moving
parts, and the drive force or torque, from the positions MOTION steps through. No Qt here.

The drive parameter moves at a steady rate over ``time`` seconds. Each moving part is followed
as a rigid body (its corners now, fitted to its corners at each step), so a point on it is
carried along. Speeds and accelerations are differences between the steps (central ones in the
middle). The drive force or torque is what keeps the motion going at that steady rate against
gravity and the parts' own inertia, with no friction: the power that goes into the parts'
energy (moving, turning, lifting) divided by the drive's rate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

G = 9.81  # m/s2, along -Z


@dataclass
class BodyMass:
    """A part's mass properties as it is at the first position (SI units: kg, m, kg m2)."""

    bid: int
    mass: float
    centre: np.ndarray  # m
    inertia: np.ndarray  # 3 x 3 about the centre, kg m2


@dataclass
class Study:
    values: list[float]
    times: np.ndarray
    points: dict[str, dict[str, np.ndarray]] = field(default_factory=dict)  # label -> pos, vel, acc, speed
    drive: np.ndarray | None = None  # N m (angle) or N (length) at each position
    drive_static: np.ndarray | None = None  # the share that holds the parts up against gravity
    energy: np.ndarray | None = None  # J


def rotation_vector(r: np.ndarray) -> np.ndarray:
    """The axis times the angle (radians) of a rotation matrix."""
    c = max(-1.0, min(1.0, (np.trace(r) - 1) / 2))
    ang = math.acos(c)
    if ang < 1e-12:
        return np.zeros(3)
    w = np.array([r[2, 1] - r[1, 2], r[0, 2] - r[2, 0], r[1, 0] - r[0, 1]])
    s = 2 * math.sin(ang)
    if abs(s) < 1e-9:  # half a turn: the axis from the symmetric part
        m = (r + np.eye(3)) / 2
        axis = m[:, int(np.argmax(np.diag(m)))]
        return axis / np.linalg.norm(axis) * ang
    return w / s * ang


def angular_velocity(rs: list[np.ndarray], t: np.ndarray) -> np.ndarray:
    """omega (rad/s, world axes) at each step from the rotations (central differences)."""
    n = len(rs)
    out = np.zeros((n, 3))
    for k in range(n):
        a, b = max(0, k - 1), min(n - 1, k + 1)
        if b == a:
            continue
        out[k] = rotation_vector(rs[b] @ rs[a].T) / (t[b] - t[a])
    return out


def _diff(x: np.ndarray, t: np.ndarray) -> np.ndarray:
    if len(t) < 2:
        return np.zeros_like(x)
    return np.gradient(x, t, axis=0, edge_order=1)


def study(values: list[float], time: float, frames: dict[int, list[tuple[np.ndarray, np.ndarray]]],
          points: dict[str, tuple[int, np.ndarray]], masses: list[BodyMass], per_rad: bool,
          scale: float) -> Study:
    """``frames``: body -> (R, t) at each position (model units). ``points``: label -> (body, point in
    model units, where it is at the first position). ``scale``: metres per model unit. ``per_rad``: the
    parameter is an angle in degrees (a torque comes out), else a length in model units (a force)."""
    n = len(values)
    t = np.linspace(0.0, time, n)
    st = Study(values, t)
    for label, (bid, q) in points.items():
        pos = np.array([r @ q + s for r, s in frames[bid]])
        vel = _diff(pos, t)
        acc = _diff(vel, t)
        st.points[label] = {"pos": pos, "vel": vel, "acc": acc, "speed": np.linalg.norm(vel, axis=1),
                            "accel": np.linalg.norm(acc, axis=1)}
    if not masses or n < 2:
        return st
    ke = np.zeros(n)
    pe = np.zeros(n)
    for bm in masses:
        fr = frames[bm.bid]
        rs = [r for r, _ in fr]
        cm = np.array([r @ (bm.centre / scale) + s for r, s in fr]) * scale  # m
        v = _diff(cm, t)
        w = angular_velocity(rs, t)
        for k in range(n):
            i_w = rs[k] @ bm.inertia @ rs[k].T
            ke[k] += 0.5 * bm.mass * float(v[k] @ v[k]) + 0.5 * float(w[k] @ i_w @ w[k])
        pe += bm.mass * G * cm[:, 2]
    rate = (values[-1] - values[0]) / time  # parameter units per second
    rate_si = math.radians(rate) if per_rad else rate * scale
    if abs(rate_si) < 1e-15:
        return st
    st.energy = ke + pe
    st.drive = _diff(ke + pe, t) / rate_si
    st.drive_static = _diff(pe, t) / rate_si
    return st


def mass_of(shape, density: float, scale: float, bid: int) -> BodyMass | None:
    """Mass properties of a solid (density kg/m3) in SI units."""
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    if density <= 0:
        return None
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    vol = g.Mass()
    if vol <= 0:
        return None
    c = g.CentreOfMass()
    mat = g.MatrixOfInertia()  # about the centre, per unit density, model units^5
    inertia = np.array([[mat.Value(i, j) for j in (1, 2, 3)] for i in (1, 2, 3)]) * density * scale ** 5
    return BodyMass(bid, vol * scale ** 3 * density, np.array([c.X(), c.Y(), c.Z()]) * scale, inertia)


def csv_text(st: Study, param: str, drive_unit: str, unit: str) -> str:
    head = [param, "time_s"]
    for label in st.points:
        head += [f"{label}_x", f"{label}_y", f"{label}_z", f"{label}_speed_{unit}/s", f"{label}_accel_{unit}/s2"]
    if st.drive is not None:
        head += [f"drive_{drive_unit}", f"drive_gravity_{drive_unit}"]
    rows = [",".join(head)]
    for k, v in enumerate(st.values):
        row = [f"{v:.6g}", f"{st.times[k]:.6g}"]
        for d in st.points.values():
            row += [f"{c:.6g}" for c in d["pos"][k]] + [f"{d['speed'][k]:.6g}", f"{d['accel'][k]:.6g}"]
        if st.drive is not None:
            row += [f"{st.drive[k]:.6g}", f"{st.drive_static[k]:.6g}"]
        rows.append(",".join(row))
    return "\n".join(rows) + "\n"


def svg_plot(series: list[tuple[str, list[float], list[float], str]], title: str, xlabel: str,
             width: int = 720, height: int = 300 * 1) -> str:
    """Line charts, one panel per series (name, x, y, unit), stacked; plain SVG."""
    colours = ("#2a6fdb", "#d9534f", "#2e9e5b", "#b26fd1", "#e08a1e", "#3aa6b9")
    ph, pad_l, pad_r, pad_t, pad_b = 160, 70, 20, 30, 34
    h = pad_t + len(series) * (ph + pad_b) + 10
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{h}" viewBox="0 0 {width} {h}" '
           'font-family="sans-serif" font-size="11">',
           f'<rect width="{width}" height="{h}" fill="white"/>',
           f'<text x="{pad_l}" y="18" font-size="13" font-weight="bold">{_esc(title)}</text>']
    for i, (name, xs, ys, unit) in enumerate(series):
        top = pad_t + i * (ph + pad_b)
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        if y1 - y0 < 1e-12:
            y0, y1 = y0 - 1, y1 + 1
        if x1 - x0 < 1e-12:
            x1 = x0 + 1
        w = width - pad_l - pad_r

        def px(x):
            return pad_l + (x - x0) / (x1 - x0) * w

        def py(y):
            return top + ph - (y - y0) / (y1 - y0) * ph

        out.append(f'<rect x="{pad_l}" y="{top}" width="{w}" height="{ph}" fill="none" stroke="#999"/>')
        if y0 < 0 < y1:
            out.append(f'<line x1="{pad_l}" x2="{pad_l + w}" y1="{py(0):.1f}" y2="{py(0):.1f}" stroke="#ccc"/>')
        pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{colours[i % len(colours)]}" stroke-width="1.6"/>')
        out.append(f'<text x="{pad_l + 4}" y="{top + 13}">{_esc(name)} ({_esc(unit)})</text>')
        for y in (y0, y1):
            out.append(f'<text x="{pad_l - 4}" y="{py(y) + 4:.1f}" text-anchor="end">{y:.4g}</text>')
        for x in (x0, x1):
            out.append(f'<text x="{px(x):.1f}" y="{top + ph + 13}" text-anchor="middle">{x:.4g}</text>')
        out.append(f'<text x="{pad_l + w / 2:.1f}" y="{top + ph + 26}" text-anchor="middle">{_esc(xlabel)}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
