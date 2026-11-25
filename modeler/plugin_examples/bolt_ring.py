"""Bolt ring: a ring of equal holes round the middle of a body's top face.

An example plug-in. Copy it into the plug-in folder (Preferences > Plug-ins > Add the example),
change it, and press Reload. A plug-in only changes the model with api.run, so each of its
commands is one history step that undo and rebuild handle like any other.
"""

import math

from modeler.plugins import Arg, BodyRef, CommandError, plugin_command


@plugin_command(
    "BOLTRING",
    Arg("b", BodyRef, help="the body to drill"),
    Arg("n", int, 6, "how many holes"),
    Arg("d", float, 6.0, "the hole diameter"),
    Arg("r", float, 20.0, "the radius of the ring"),
    Arg("start", float, 0.0, "the angle of the first hole, in degrees"),
    help="A ring of n through holes round the middle of a body's top face: BOLTRING, plate, 6, 6, 20",
)
def boltring(api, b, n, d, r, start):
    if n < 1 or n > 360:
        raise CommandError("the ring has 1 to 360 holes")
    box = api.value(f"BBOX({b})")  # the body's box, as data (any expression works)
    x0, y0, x1, y1, z1 = (box.get(k) for k in ("xmin", "ymin", "xmax", "ymax", "zmax"))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if r + d / 2 > min(x1 - x0, y1 - y0) / 2:
        raise CommandError(f"a ring of radius {r:g} does not fit on the body")
    ref = b  # the body's name, or its number when it has no name
    for i in range(n):
        a = math.radians(start + 360.0 * i / n)
        api.run(f"HOLE, {ref}, {cx + r * math.cos(a):.6g}, {cy + r * math.sin(a):.6g}, {z1:.6g}, {d:g}")
        ref = b if not b.isdigit() else "LAST"  # HOLE makes the body again: an unnamed one is the last body
    return f"{n} holes of {d:g} on a ring of radius {r:g}"
