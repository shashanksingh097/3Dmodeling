"""A small 2D geometric constraint solver (plain Python + numpy).

The sketch hands the solver a flat list of numbers (point coordinates and
radii) and a list of constraints. Each constraint is a function of a few of
those numbers that is zero when the constraint holds. The solver moves the
numbers until every function is zero, changing them as little as possible,
so an under-constrained sketch keeps the shape you drew.

How it works
------------
* The problem is split into independent groups (numbers that share no
  constraint never affect each other). A plate with 40 holes is 40 small
  problems, not one big one, which keeps solving fast.
* Each group is solved by Gauss-Newton steps of least norm (the smallest
  change that removes the error, to first order), with a backtracking line
  search, falling back to Levenberg-Marquardt when a step does not help.
* After solving, the rank of the constraint Jacobian gives the degrees of
  freedom left, which numbers are still free (so the GUI can show what is
  fully defined), and which constraints repeat others (redundant) or cannot
  hold together with them (conflicting). Blame goes to the later
  constraint, which is the one the user just added.

Derivatives are taken by central differences on each constraint's own few
numbers; constraints are small, so this costs little and keeps every
constraint a few lines of plain math.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

TOL = 1e-9  # residual (in model units) that counts as satisfied


@dataclass
class Constraint:
    tag: int  # who added it (the sketch's constraint number; < 0 for built-in rules)
    idx: tuple[int, ...]  # the numbers it reads
    fn: Callable[[np.ndarray], list[float]]  # their values -> residuals (zero when it holds)

    def eval(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(self.fn(x[list(self.idx)]), dtype=float)


@dataclass
class Report:
    ok: bool  # every constraint holds
    dof: int  # degrees of freedom left
    free: set[int] = field(default_factory=set)  # numbers that can still move
    redundant: list[int] = field(default_factory=list)  # tags of constraints that repeat others
    conflicting: list[int] = field(default_factory=list)  # tags of constraints that cannot hold with the others
    failed: list[int] = field(default_factory=list)  # tags not satisfied at the end
    iterations: int = 0


def _jacobian(c: Constraint, x: np.ndarray, r0: np.ndarray) -> np.ndarray:
    v = x[list(c.idx)].astype(float)
    J = np.zeros((len(r0), len(v)))
    for k in range(len(v)):
        h = 1e-7 * max(1.0, abs(v[k]))
        a, b = v.copy(), v.copy()
        a[k] += h
        b[k] -= h
        J[:, k] = (np.asarray(c.fn(a), float) - np.asarray(c.fn(b), float)) / (2 * h)
    return J


def _groups(n: int, cons: list[Constraint], fixed: set[int]) -> list[tuple[list[int], list[int]]]:
    """Split into independent problems: (free number indices, constraint indices)."""
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for c in cons:
        live = [i for i in c.idx if i not in fixed]
        for i in live[1:]:
            a, b = find(live[0]), find(i)
            if a != b:
                parent[b] = a
    vars_of: dict[int, list[int]] = {}
    for i in range(n):
        if i not in fixed:
            vars_of.setdefault(find(i), []).append(i)
    cons_of: dict[int, list[int]] = {}
    lonely: list[int] = []  # constraints on fixed numbers only
    for k, c in enumerate(cons):
        live = [i for i in c.idx if i not in fixed]
        if live:
            cons_of.setdefault(find(live[0]), []).append(k)
        else:
            lonely.append(k)
    out = [(vars_of[root], cons_of.get(root, [])) for root in vars_of]
    if lonely:
        out.append(([], lonely))
    return out


def _residuals(x: np.ndarray, cons: list[Constraint], ks: list[int]) -> np.ndarray:
    rs = [cons[k].eval(x) for k in ks]
    return np.concatenate(rs) if rs else np.zeros(0)


def _system(x: np.ndarray, cons: list[Constraint], ks: list[int], cols: list[int]):
    """Residuals and Jacobian (rows: constraints ks; columns: numbers cols)."""
    col = {v: j for j, v in enumerate(cols)}
    rs, rows, owners = [], [], []
    for k in ks:
        c = cons[k]
        r = c.eval(x)
        J = _jacobian(c, x, r)
        block = np.zeros((len(r), len(cols)))
        for j, v in enumerate(c.idx):
            if v in col:
                block[:, col[v]] += J[:, j]
        rs.append(r)
        rows.append(block)
        owners.extend([k] * len(r))
    if not rs:
        return np.zeros(0), np.zeros((0, len(cols))), []
    return np.concatenate(rs), np.vstack(rows), owners


def _solve_group(x: np.ndarray, cons: list[Constraint], ks: list[int], cols: list[int],
                 weights: np.ndarray | None = None, max_iter: int = 60) -> int:
    """Move x[cols] until the constraints ks hold. Returns the iterations used."""
    if not cols or not ks:
        return 0
    r, J, _ = _system(x, cons, ks, cols)
    if weights is not None:
        r, J = r * weights, J * weights[:, None]
    err = float(r @ r)
    lam = 1e-3
    for it in range(1, max_iter + 1):
        if math.sqrt(err) < TOL * 0.1:
            return it - 1
        # least-norm Gauss-Newton step: the smallest change that cancels the error to first order
        step = np.linalg.lstsq(J, -r, rcond=1e-10)[0]
        improved = False
        t = 1.0
        for _ in range(12):
            trial = x.copy()
            trial[cols] += t * step
            r2 = _residuals(trial, cons, ks)
            if weights is not None:
                r2 = r2 * weights
            e2 = float(r2 @ r2)
            if e2 < err:
                improved = True
                break
            t *= 0.5
        if not improved:  # Levenberg-Marquardt: shorter, better-conditioned steps
            for _ in range(10):
                A = J.T @ J + lam * np.eye(len(cols))
                step = np.linalg.solve(A, -J.T @ r)
                trial = x.copy()
                trial[cols] += step
                r2 = _residuals(trial, cons, ks)
                if weights is not None:
                    r2 = r2 * weights
                e2 = float(r2 @ r2)
                if e2 < err:
                    improved = True
                    lam = max(lam / 10, 1e-12)
                    break
                lam *= 10
        if not improved:
            return it
        x[cols] = trial[cols]
        err = e2
        r, J, _ = _system(x, cons, ks, cols)
        if weights is not None:
            r, J = r * weights, J * weights[:, None]
    return max_iter


def _diagnose(x: np.ndarray, cons: list[Constraint], ks: list[int], cols: list[int], rep: Report) -> None:
    r, J, owners = _system(x, cons, ks, cols)
    if len(r) == 0:
        rep.dof += len(cols)
        rep.free.update(cols)
        return
    scale = max(1.0, float(np.abs(J).max()))
    # which constraints repeat earlier ones: build the row space in order
    Q = np.zeros((min(len(r), len(cols)) + 1, len(cols)))  # orthonormal rows found so far
    rank = 0
    by_k: dict[int, list[int]] = {}
    for row, k in enumerate(owners):
        by_k.setdefault(k, []).append(row)
    for k in ks:
        rows = by_k.get(k, [])
        new = 0
        for row in rows:
            v = J[row].copy()
            for _ in range(2):  # twice, for round-off
                v -= Q[:rank].T @ (Q[:rank] @ v)
            nv = np.linalg.norm(v)
            if nv > 1e-7 * scale and rank < len(cols):
                Q[rank] = v / nv
                rank += 1
                new += 1
        if rows and new == 0 and cons[k].tag >= 0:
            bad = float(np.abs(r[rows]).max()) > 1e2 * TOL * max(1.0, float(np.abs(x).max()))
            (rep.conflicting if bad else rep.redundant).append(cons[k].tag)
    rep.dof += len(cols) - rank
    if len(cols) > rank:
        _, s, vt = np.linalg.svd(J, full_matrices=True)
        null = vt[rank:]  # directions the constraints do not fix
        movable = np.linalg.norm(null, axis=0) > 1e-6
        rep.free.update(c for c, m in zip(cols, movable) if m)
    tol = 1e2 * TOL * max(1.0, float(np.abs(x).max()))
    for k in ks:
        rows = by_k.get(k, [])
        if rows and float(np.abs(r[rows]).max()) > tol and cons[k].tag >= 0:
            rep.failed.append(cons[k].tag)


def solve(x: np.ndarray, cons: list[Constraint], fixed: set[int] = frozenset(), diagnose: bool = True) -> Report:
    """Solve in place. ``fixed`` numbers never move (the sketch origin and axes)."""
    n = len(x)
    rep = Report(ok=True, dof=0)
    groups = _groups(n, cons, set(fixed))
    for cols, ks in groups:
        rep.iterations = max(rep.iterations, _solve_group(x, cons, ks, cols))
    if diagnose:
        for cols, ks in groups:
            _diagnose(x, cons, ks, cols, rep)
    else:
        tol = 1e2 * TOL * max(1.0, float(np.abs(x).max()) if n else 1.0)
        for c in cons:
            if c.tag >= 0 and float(np.abs(c.eval(x)).max(initial=0.0)) > tol:
                rep.failed.append(c.tag)
    rep.failed = sorted(set(rep.failed))
    rep.ok = not rep.failed
    return rep


def solve_dragging(x: np.ndarray, cons: list[Constraint], fixed: set[int], drag: dict[int, float]) -> Report:
    """Solve with some numbers pulled towards target values (a mouse drag).

    The pull is a soft wish: the constraints always win. First try to meet
    both; if they cannot both hold, get as close to the targets as the
    constraints allow."""
    pulls = [Constraint(-1, (i,), (lambda v, t=t: [v[0] - t])) for i, t in drag.items()]
    trial = x.copy()
    rep = solve(trial, cons + pulls, fixed, diagnose=False)
    if rep.ok and all(abs(trial[i] - t) < 1e-6 for i, t in drag.items()):
        x[:] = trial
        return solve(x, cons, fixed, diagnose=False)
    trial = x.copy()
    for i, t in drag.items():
        trial[i] = t
    allc = cons + pulls
    groups = _groups(len(x), allc, set(fixed))
    for cols, ks in groups:
        w = np.concatenate([np.full(len(allc[k].eval(trial)), 1e-3 if allc[k].tag == -1 else 1.0) for k in ks]) \
            if ks else None
        _solve_group(trial, allc, ks, cols, weights=w)
    x[:] = trial
    return solve(x, cons, fixed, diagnose=False)
