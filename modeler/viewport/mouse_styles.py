"""Mouse styles: which drag turns, moves or zooms the 3D view (PLAN item 75).

People coming from another CAD program keep their hands' habits: each style
copies the usual buttons of a family of programs. Clicks do not change
between styles: a left click picks, a right click (without moving) opens
the menu. Only drags and the wheel's direction do. Kept free of Qt so it is
tested headless; buttons and modifiers are plain words here.
"""

from __future__ import annotations

from dataclasses import dataclass

# a drag: (button, modifier) -> what it does. button: LEFT, MIDDLE, RIGHT; modifier: "", SHIFT, CTRL, ALT
Drag = tuple[str, str]


@dataclass(frozen=True)
class Style:
    key: str
    label: str
    like: str  # the programs whose buttons it copies (shown in Preferences)
    drags: dict[Drag, str]  # -> ROTATE, PAN or ZOOM
    help: str = ""

    def action(self, button: str, modifier: str = "") -> str | None:
        """What a drag with this button and modifier does, or None (no navigation)."""
        hit = self.drags.get((button, modifier))
        if hit is None and modifier in ("CTRL", "ALT"):
            hit = self.drags.get((button, ""))  # Ctrl and Alt are for picking: a drag still navigates
        return hit

    def status_text(self, tr=None) -> str:
        """The status bar's hint: 'Left drag: orbit · Right drag: pan · Wheel: zoom' (``tr``
        puts each phrase in the window's language)."""
        english = tr is None
        tr = tr or (lambda s: s)
        words = {"ROTATE": "orbit", "PAN": "pan", "ZOOM": "zoom"}
        order = ("LEFT", "MIDDLE", "RIGHT")
        parts = []
        for (b, mod), what in sorted(self.drags.items(), key=lambda kv: (order.index(kv[0][0]), kv[0][1])):
            head = tr(f"{b.title()} drag")
            if mod:
                head = f"{mod.title()}+" + (head[0].lower() + head[1:] if english else head)
            parts.append(f"{head}: {tr(words[what])}")
        return " · ".join(parts + [f"{tr('Wheel')}: {tr('zoom')}", tr("Click: pick (Ctrl adds, Alt removes)")])


STYLES: dict[str, Style] = {s.key: s for s in (
    Style("default", "This app's own", "",
          {("LEFT", ""): "ROTATE", ("LEFT", "SHIFT"): "PAN", ("RIGHT", ""): "PAN", ("MIDDLE", ""): "PAN"},
          "Left drag orbits, right or middle drag pans."),
    Style("middle-orbit", "Middle button orbits", "SolidWorks, Solid Edge, Inventor",
          {("MIDDLE", ""): "ROTATE", ("MIDDLE", "CTRL"): "PAN", ("MIDDLE", "SHIFT"): "ZOOM"},
          "Middle drag orbits, Ctrl+middle pans, Shift+middle zooms."),
    Style("middle-pan", "Middle button pans", "Fusion 360, CATIA-like",
          {("MIDDLE", ""): "PAN", ("MIDDLE", "SHIFT"): "ROTATE", ("MIDDLE", "CTRL"): "ZOOM"},
          "Middle drag pans, Shift+middle orbits, Ctrl+middle zooms."),
    Style("right-orbit", "Right button orbits", "Onshape",
          {("RIGHT", ""): "ROTATE", ("MIDDLE", ""): "PAN", ("RIGHT", "CTRL"): "PAN"},
          "Right drag orbits, middle or Ctrl+right drag pans."),
    Style("blender", "Blender-like", "Blender, FreeCAD's Blender navigation",
          {("MIDDLE", ""): "ROTATE", ("MIDDLE", "SHIFT"): "PAN", ("MIDDLE", "CTRL"): "ZOOM"},
          "Middle drag orbits, Shift+middle pans, Ctrl+middle zooms."),
)}
DEFAULT = "default"

# the phrases status_text puts together (for the language files)
PHRASES = ("Left drag", "Middle drag", "Right drag", "orbit", "pan", "zoom", "Wheel",
           "Click: pick (Ctrl adds, Alt removes)")


def get(key: str) -> Style:
    return STYLES.get(key, STYLES[DEFAULT])


def modifier_word(shift: bool, ctrl: bool, alt: bool) -> str:
    """One modifier word for a drag (Ctrl wins over Shift, Alt over both)."""
    return "ALT" if alt else "CTRL" if ctrl else "SHIFT" if shift else ""
