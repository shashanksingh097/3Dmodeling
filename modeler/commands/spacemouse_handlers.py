"""SPACEMOUSE: the 3D mouse's settings (PLAN item 111; viewport/spacemouse.py)."""

from __future__ import annotations

from ..viewport import spacemouse as sm
from .processor import Arg, CommandError, Processor, Raw, command

WHATS = ("", "ON", "OFF", "SPEED", "ROTATE", "PAN", "ZOOM", "DOMINANT", "INVERT", "BUTTON", "RESET")


def _onoff(v: str, what: str) -> bool:
    v = v.strip().upper()
    if v in ("ON", "YES", "1", "TRUE"):
        return True
    if v in ("OFF", "NO", "0", "FALSE"):
        return False
    raise CommandError(f"SPACEMOUSE, {what}: ON or OFF")


@command(
    "SPACEMOUSE",
    Arg("what", str, "", "ON, OFF, SPEED, ROTATE, PAN, ZOOM, DOMINANT, INVERT, BUTTON or RESET; empty: how it is"),
    Arg("value", Raw, "", "SPEED: 0.1 ... 5; ROTATE/PAN/ZOOM/DOMINANT: ON or OFF; INVERT: the axes turned the other "
                          "way (TX TY TZ RX RY RZ, or NONE); BUTTON: its number"),
    Arg("command", Raw, "", "BUTTON: the command it runs (FIT, \"VIEW, TOP\" ...; empty: nothing)"),
    logged=False,
    help="The 3D mouse (a SpaceMouse or another six-axis cap): SPACEMOUSE alone says whether one was found and how "
         "it is set. SPACEMOUSE, SPEED, 2 · SPACEMOUSE, ROTATE, OFF (pan and zoom only) · SPACEMOUSE, DOMINANT, ON "
         "(only the strongest axis) · SPACEMOUSE, INVERT, RY TZ · SPACEMOUSE, BUTTON, 1, FIT · SPACEMOUSE, OFF. "
         "It is read through spacenavd on Linux or the pyspacemouse package (pip install pyspacemouse) anywhere. "
         "The settings are kept with the app, not the project.",
)
def spacemouse(p: Processor, what, value, command):
    what = what.strip().upper()
    if what not in WHATS:
        raise CommandError(f"SPACEMOUSE: use one of {', '.join(w for w in WHATS if w)}, or nothing to see it")
    s = sm.settings
    val = str(value).strip().strip('"')
    said = ""
    if what == "ON":
        s.on, said = True, "3D mouse on"
    elif what == "OFF":
        s.on, said = False, "3D mouse off"
    elif what == "SPEED":
        try:
            sp = float(p.evaluate(val))
        except Exception:  # noqa: BLE001
            raise CommandError("SPACEMOUSE, SPEED: a number from 0.1 to 5") from None
        if not 0.1 <= sp <= 5:
            raise CommandError("SPACEMOUSE, SPEED: a number from 0.1 to 5")
        s.speed, said = sp, f"3D mouse speed {sp:g}"
    elif what in ("ROTATE", "PAN", "ZOOM", "DOMINANT"):
        on = _onoff(val, what)
        setattr(s, what.lower(), on)
        said = {"ROTATE": "turning", "PAN": "panning", "ZOOM": "zooming",
                "DOMINANT": "strongest axis only"}[what] + (" on" if on else " off")
    elif what == "INVERT":
        axes = set(val.upper().replace(",", " ").replace("+", " ").split()) - {"NONE"}
        bad = axes - set(sm.AXES)
        if bad:
            raise CommandError(f"SPACEMOUSE, INVERT: the axes are {' '.join(sm.AXES)} (or NONE), not {' '.join(bad)}")
        s.invert = axes
        said = "turned the other way: " + (" ".join(sorted(axes)) or "none")
    elif what == "BUTTON":
        if not val.isdigit() or int(val) < 1:
            raise CommandError("SPACEMOUSE, BUTTON: the button's number (1, 2 ...), then its command")
        cmd = str(command).strip().strip('"')
        if cmd:
            s.buttons[int(val)] = cmd
        else:
            s.buttons.pop(int(val), None)
        said = f"button {val}: {cmd or 'nothing'}"
    elif what == "RESET":
        sm.settings = s = sm.Settings()
        said = "3D mouse settings back to how they came"
    drv = getattr(p.view, "spacemouse", None) if p.view else None
    if what and drv is not None:
        drv.settings_changed()
    st = drv.status() if drv is not None else {"found": False, "via": "", "notes": ["no window"], **s.to_dict()}
    p.give_report("spacemouse", st)
    lines = [said] if said else []
    lines += s.text()
    if not what:
        if st["found"]:
            lines.insert(0, f"a 3D mouse is connected (through {st['via']})")
        else:
            lines.insert(0, "no 3D mouse found" + (f" ({'; '.join(st['notes'])})" if st["notes"] else ""))
    return "\n".join(lines)
