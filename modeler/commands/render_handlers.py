"""RENDER: a nicer picture of the model (viewport/nice_render.py), at any size, or a turntable."""

from __future__ import annotations

import os

from .processor import Arg, CommandError, Path, Processor, Text, command


@command(
    "RENDER",
    Arg("file", Path, help="the picture to write (.png)"),
    Arg("width", int, 1600, "pixels across"),
    Arg("height", int, 1000, "pixels down"),
    Arg("view", Text, "", "ISO, FRONT, TOP ... or a direction dx,dy,dz in quotes (default: as the view shows it)"),
    Arg("frames", int, 0, "a turntable: this many pictures round the model (file_000.png ..., and file.gif "
                          "when Pillow is installed)"),
    Arg("floor", str, "ON", "ON: a floor under the model catches the shadows · OFF"),
    logged=False,
    help="A nicer picture than the working view: ray traced, with shadows, reflections, smooth edges and a "
         "look from each body's MATERIAL: RENDER, part.png · RENDER, big.png, 3840, 2160, ISO · "
         "RENDER, spin.png, 800, 600, ISO, 36 (a turntable of 36 pictures). Needs the app's 3D view",
)
def render(p: Processor, file, width, height, view, frames, floor):
    if os.path.splitext(file)[1].lower() not in ("", ".png"):
        raise CommandError("RENDER: the picture is a .png")
    if not (16 <= width <= 8192 and 16 <= height <= 8192):
        raise CommandError("RENDER: the size is 16 to 8192 pixels each way")
    if frames < 0 or frames > 360:
        raise CommandError("RENDER: frames is 0 (one picture) to 360")
    if floor not in ("ON", "OFF"):
        raise CommandError("RENDER: floor is ON or OFF")
    hook = getattr(p.view, "render_nice", None) if p.view else None
    if hook is None:
        raise CommandError("RENDER: needs the app's 3D view (run it in the app, or with python -m modeler render)")
    path = file if os.path.splitext(file)[1] else file + ".png"
    from ..viewport.nice_render import RenderError

    try:
        got = hook(path, width, height, view.strip().strip('"').upper(), frames, floor == "ON")
    except RenderError as exc:
        raise CommandError(f"RENDER: {exc}") from None
    note = getattr(p.view, "last_render_note", "")
    note = f" ({note})" if note else ""
    if len(got) == 1:
        return f"rendered {width} x {height} to {got[0]}{note}"
    gif = [g for g in got if g.endswith(".gif")]
    return (f"rendered a turntable of {frames} pictures, {width} x {height}: {got[0]} ... "
            f"{[g for g in got if g.endswith('.png')][-1]}" + (f", and {gif[0]}" if gif else "") + note)
