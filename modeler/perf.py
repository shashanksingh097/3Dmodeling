"""Speed and memory benchmark (PLAN item 63).

    python -m modeler perf [--json out.json] [--check] [--budgets file.json] [--quick]

Times the work people wait for on a model of a realistic size: importing a STEP
file, rebuilding a long history after an early edit, finding what was picked,
making a drawing, and saving and opening the project. Each case also notes how
much memory the process holds after it. ``--check`` compares the times with
``docs/perf-budgets.json`` and fails when one is more than its budget; CI runs it
on every push so a change that makes the app slow is seen at once.

Budgets are generous on purpose (CI machines vary by about two times): they
catch a change that makes something several times slower, not a few percent.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BUDGETS = os.path.join(os.path.dirname(HERE), "docs", "perf-budgets.json")


# ---- memory ---------------------------------------------------------------------------------------

def rss_mb() -> float:
    """Memory the process holds now, in MB (on macOS the peak so far)."""
    try:
        with open("/proc/self/statm", encoding="ascii") as f:
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 2**20
    except (OSError, ValueError, AttributeError):
        pass
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        c = Counters()
        c.cb = ctypes.sizeof(c)
        # the handle is pointer sized: without these types ctypes passes it as a 32-bit int and the
        # call fails on 64-bit Windows
        k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        proc = k32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(proc, ctypes.byref(c), c.cb):
            return c.WorkingSetSize / 2**20
        return 0.0
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 2**20 if sys.platform == "darwin" else peak / 1024


# ---- the model ------------------------------------------------------------------------------------

def plate_script(n: int) -> str:
    """A plate with an n x n grid of holes, rounded top edges and a pocket:
    a few hundred faces, the size of a typical machined part."""
    return "\n".join([
        f"N = {n}",
        "W = 12 * N + 12",
        "BLOCK, 0,0,0, W, W, 10",
        "NAME, LAST, plate",
        "CYL, 12, 12, -1, 3, 12",
        "ARRAY, LINEAR, LAST, N, 12,0,0, N, 0,12,0, CUT, plate",
        "SEL, S, EDGE, LOC, Z, 10",
        "SEL, R, EDGE, TYPE, LINE",
        "FILLET, 2",
        "BLOCK, 6, 6, 7, W - 12, 4, 5",
        "SUBTRACT, plate, LAST",
    ])


def history_script(steps: int) -> str:
    """A long history: a parameter at the top that every later step depends on."""
    lines = ["T = 2", "BLOCK, 0,0,0, 200, 40, 10", "NAME, LAST, bar"]
    for i in range(steps):
        x = 4 + (i % 48) * 4
        y = 8 + (i // 48) * 8
        if i % 2:
            lines += [f"CYL, {x}, {y % 36 + 2}, -1, T / 2, 12", "SUBTRACT, bar, LAST"]
        else:
            lines += [f"BLOCK, {x - 1}, {y % 36 + 1}, 10, 2, 2, T", "UNION, bar, LAST"]
    return "\n".join(lines)


# ---- the cases ------------------------------------------------------------------------------------

def _ok(p, text: str):
    res = p.run_script(text)
    bad = [r for r in res if not r.ok]
    if bad:
        raise RuntimeError(f"{bad[0].line.splitlines()[0]}: {bad[0].message}")
    return res[-1]


def _timed(fn) -> float:
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


def run(quick: bool = False, out=print) -> dict:
    from .commands import Processor

    n, steps = (4, 30) if quick else (8, 120)
    rows: dict[str, dict] = {}

    def note(name, seconds, extra=""):
        rows[name] = {"seconds": round(seconds, 4), "memory_mb": round(rss_mb(), 1)}
        out(f"  {name:<18} {seconds:8.3f} s   {rows[name]['memory_mb']:7.1f} MB   {extra}")

    out(f"3Dmodeling benchmark ({'quick' if quick else 'full'}), memory at start {rss_mb():.1f} MB")
    with tempfile.TemporaryDirectory(prefix="m3d-perf-") as tmp:
        p = Processor()
        build = _timed(lambda: _ok(p, plate_script(n)))
        faces = p.model.entity_ids("FACE")
        note("build plate", build, f"{len(faces)} faces")

        step = os.path.join(tmp, "plate.step")
        _ok(p, f'EXPORT, STEP, "{step}"')
        q = Processor()
        note("import STEP", _timed(lambda: _ok(q, f'IMPORT, STEP, "{step}"')),
             f"{os.path.getsize(step) // 1024} KB")

        # what the 3D view does after the kernel finds the shape under the mouse
        bid = next(iter(p.model.bodies))
        shapes = [(g, p.model.entity_shape("FACE", g)) for g in faces]

        def picks():
            for _ in range(20):
                for g, s in shapes:
                    if p.model.find_entity(bid, "FACE", s) != g:
                        raise RuntimeError(f"face {g} was found as another face")
        note("pick faces", _timed(picks), f"{20 * len(shapes)} picks")

        svg = os.path.join(tmp, "plate.svg")
        note("drawing", _timed(lambda: _ok(p, f'DRAWING, "{svg}", STANDARD, , ALL')))

        proj = os.path.join(tmp, "plate.m3d")
        note("save", _timed(lambda: _ok(p, f'SAVE, "{proj}"')), f"{os.path.getsize(proj) // 1024} KB")
        note("open", _timed(lambda: _ok(Processor(), f'OPEN, "{proj}"')))

        h = Processor()
        note("long history", _timed(lambda: _ok(h, history_script(steps))), f"{len(h.history)} steps")
        note("rebuild after edit", _timed(lambda: _ok(h, 'HIST, EDIT, 1, "T = 2.5"')), "from step 1")
    out(f"memory at the end {rss_mb():.1f} MB")
    return {"quick": quick, "python": sys.version.split()[0], "platform": sys.platform, "cases": rows}


def check(result: dict, budgets: dict) -> list[str]:
    """Cases over their budget, as lines to print."""
    key = "quick" if result["quick"] else "full"
    slow = []
    for name, row in result["cases"].items():
        b = budgets.get(key, {}).get(name)
        if b and row["seconds"] > b["seconds"]:
            slow.append(f"{name}: {row['seconds']:.2f} s, over its budget of {b['seconds']} s")
        if b and b.get("memory_mb") and row["memory_mb"] > b["memory_mb"]:
            slow.append(f"{name}: {row['memory_mb']:.0f} MB held, over its budget of {b['memory_mb']} MB")
    return slow


def main(args: list[str]) -> int:
    quick = "--quick" in args
    result = run(quick)
    if "--json" in args:
        with open(args[args.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(result, f, indent=1)
    if "--check" in args:
        path = args[args.index("--budgets") + 1] if "--budgets" in args else BUDGETS
        with open(path, encoding="utf-8") as f:
            slow = check(result, json.load(f))
        for line in slow:
            print("SLOW " + line)
        if slow:
            return 1
        print("all cases within their budgets")
    return 0
