"""Checks before 3D printing a solid: what sits on the bed, what hangs over
(needs support), walls too thin for the nozzle, and hollows that trap
material inside. Works on the analysis mesh (geometry/analysis.py).

Overhang angle: a downward-facing surface at angle a from vertical needs
support when a is more than the printer's limit (45 degrees is usual).
With n the outward normal and up the build direction, the surface faces
down when n·up < 0, and its angle from vertical is asin(-n·up); so it
overhangs when -n·up > sin(limit). A flat ceiling (n = -up) is the worst.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

BED_TOL = 1e-3  # relative to the part's size: this close to the lowest point counts as on the bed

# per-node classes
OK, OVERHANG, BASE = 0, 1, 2


def unit(d) -> np.ndarray:
    d = np.asarray(d, float)
    n = float(np.linalg.norm(d))
    if n < 1e-12:
        raise ValueError("the build direction is zero")
    return d / n


def classes(nodes: np.ndarray, normals: np.ndarray, up, limit_deg: float) -> np.ndarray:
    """Per node: BASE (on the bed, facing down), OVERHANG, or OK."""
    up = unit(up)
    h = nodes @ up
    size = max(float(np.ptp(nodes, axis=0).max()), 1e-9)
    down = -(normals @ up)
    on_bed = (h <= h.min() + BED_TOL * size) & (down > 1 - 1e-6)
    over = (down > math.sin(math.radians(limit_deg)) + 1e-9) & ~on_bed
    return np.where(on_bed, BASE, np.where(over, OVERHANG, OK))


@dataclass
class Report:
    up: np.ndarray
    limit: float
    height: float  # along up
    footprint: tuple  # extent across, the two other directions
    area: float
    base_area: float
    overhang_area: float
    overhang_faces: list = field(default_factory=list)  # face indices (mesh order)
    lowest_overhang: float = 0.0  # height above the bed of the lowest overhang (0: none)


def check(m, up, limit_deg: float) -> Report:
    """The bed contact and the overhangs of an analysis mesh ``m``."""
    up = unit(up)
    cls = classes(m.nodes, m.normals, up, limit_deg)
    tcls = cls[m.tris]
    areas = m.tri_areas()
    base = (tcls == BASE).all(axis=1)
    over = (tcls == OVERHANG).sum(axis=1) >= 2
    h = m.nodes @ up
    a = _across(up)
    ext = [float(np.ptp(m.nodes @ v)) for v in a]
    faces = sorted({int(f) for f in m.face_of_tri[over]})
    low = float(h[m.tris[over]].min() - h.min()) if over.any() else 0.0
    return Report(up, limit_deg, float(np.ptp(h)), tuple(ext), float(areas.sum()), float(areas[base].sum()),
                  float(areas[over].sum()), faces, low)


def _across(up: np.ndarray) -> list[np.ndarray]:
    """Two directions square to up (world X/Y when up is Z)."""
    ref = np.array([1.0, 0.0, 0.0]) if abs(up[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    a = ref - (ref @ up) * up
    a /= np.linalg.norm(a)
    return [a, np.cross(up, a)]


DIRECTIONS = {"+Z": (0, 0, 1), "-Z": (0, 0, -1), "+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0),
              "-Y": (0, -1, 0)}


def best_direction(m, limit_deg: float) -> list[tuple[str, Report]]:
    """The six axis directions as build direction, least support first (then most on the bed)."""
    out = [(k, check(m, d, limit_deg)) for k, d in DIRECTIONS.items()]
    out.sort(key=lambda kr: (round(kr[1].overhang_area, 6), -kr[1].base_area, kr[1].height))
    return out


def colours(m, up, limit_deg: float) -> np.ndarray:
    """Base blue, overhang red, the rest a quiet green."""
    cls = classes(m.nodes, m.normals, up, limit_deg)
    out = np.empty((len(cls), 3))
    out[cls == OK] = (0.55, 0.78, 0.55)
    out[cls == OVERHANG] = (0.95, 0.2, 0.15)
    out[cls == BASE] = (0.25, 0.45, 0.95)
    return out


def hollows(shape) -> list[float]:
    """Volumes of closed hollows inside the solids (shells inside a solid's outer shell)."""
    from OCP.BRepClass3d import BRepClass3d
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    as_solid = getattr(TopoDS, "Solid_s", None) or TopoDS.Solid
    out = []
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        sol = as_solid(ex.Current())
        ex.Next()
        outer = BRepClass3d.OuterShell_s(sol)
        sh = TopExp_Explorer(sol, TopAbs_SHELL)
        while sh.More():
            s = sh.Current()
            sh.Next()
            if s.IsSame(outer):
                continue
            g = GProp_GProps()
            BRepGProp.VolumeProperties_s(s, g, 1e-7)
            out.append(abs(g.Mass()))
    return out
