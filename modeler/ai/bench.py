"""The assistant's benchmark: modelling requests across the skill areas, each checked exactly.

    python -m modeler copilot bench [--only NAME,...] [--modes full,small,noskills,small-noskills]
                                    [--out results.json] [--provider ... --model ...]

``--modes`` runs the tasks once per mode (a full or small first prompt, skills on or off) and
prints them side by side, so the small first prompt becomes the default only if the numbers say so.

Each task starts from a fresh model (some from a small starting script), asks
the assistant once, runs what it proposed (as the user's **Run** would), and
checks the result with expectations (the same as ``ASSERT``). Two tasks are
impossible and pass only when the assistant proposes nothing and says why.

For each task it records: passed, the checks, model calls (turns), input and
output tokens, tool calls, pictures used (``render``) and the time. The goal
(docs/M9-ai-tools.md section 6): at least 90% finished correctly, most
without a picture.

Every task has a reference script that passes its checks
(``tests/test_bench.py``), so a failure is the assistant's, not the check's.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Awaitable, Callable

from . import expect


@dataclass
class Task:
    name: str
    request: str
    checks: list[str]  # expectations; {b} is the largest body, {n0} the history length before
    setup: str = ""  # runs before the request
    reference: str = ""  # a script that passes the checks (proves the checks are right)
    refuse: tuple[str, ...] = ()  # an impossible task: no proposal, and the answer says one of these
    area: str = "modeling-basics"  # the skill it exercises (modeler/skills)


TASKS: list[Task] = [
    Task("flange",
         "Make a round flange: 100 mm across and 12 mm thick, with a 30 mm bore through the middle and 6 bolt "
         "holes of 8 mm, evenly spaced on an 80 mm circle.",
         ["VALID({b})", "BBOX({b}).dx, BETWEEN, 99.5, 100.5", "BBOX({b}).dz, BETWEEN, 11.5, 12.5",
          "HOLES({b}, 8, 1), EQ, 6", "HOLES({b}, 30, 1), EQ, 1"],
         reference="CYL, 0,0,0, 50, 12\nCYL, 0,0,-1, 15, 14\nSUBTRACT, 1, 2\n"
                   "*DO, i, 0, 5\nCYL, 40*cos(60*i), 40*sin(60*i), -1, 4, 14\nSUBTRACT, LAST-1, LAST\n*ENDDO"),
    Task("bracket",
         "Make an L bracket from 5 mm plate: one leg 60 mm long lying flat, one leg 60 mm tall standing up "
         "from one end, both 40 mm wide, as one solid, with two 6 mm holes through each leg.",
         ["VALID({b})", "PIECES({b}), EQ, 1", "HOLES({b}, 6, 1), EQ, 4", "VOL({b}), BETWEEN, 21500, 23700"],
         reference="BLOCK, 0,0,0, 60,40,5\nBLOCK, 0,0,0, 5,40,60\nUNION, 1, 2\n"
                   "CYL, 30,12,-1, 3, 7\nSUBTRACT, LAST-1, LAST\nCYL, 30,28,-1, 3, 7\nSUBTRACT, LAST-1, LAST\n"
                   "CYL, -1,12,35, 3, 7, 1,0,0\nSUBTRACT, LAST-1, LAST\nCYL, -1,28,35, 3, 7, 1,0,0\n"
                   "SUBTRACT, LAST-1, LAST"),
    Task("shelled_box",
         "Make a box 80 x 60 x 40 mm (40 tall), open at the top, with 3 mm walls and a 3 mm bottom.",
         ["VALID({b})", "BBOX({b}).dx, BETWEEN, 79.5, 80.5", "BBOX({b}).dy, BETWEEN, 59.5, 60.5",
          "BBOX({b}).dz, BETWEEN, 39.5, 40.5", "VOL({b}), BETWEEN, 43000, 45500"],
         reference="BLOCK, 0,0,0, 80,60,40\nBLOCK, 3,3,3, 74,54,40\nSUBTRACT, 1, 2"),
    Task("pipe_tee",
         "Make a pipe tee as one solid: a straight pipe 100 mm long, 30 mm outside and 24 mm inside diameter, "
         "with a branch of the same pipe coming out of its middle at right angles, reaching 50 mm from the "
         "main pipe's axis. The insides must connect.",
         ["VALID({b})", "PIECES({b}), EQ, 1", "BBOX({b}).dx, BETWEEN, 99.5, 100.5",
          "VOL({b}), BETWEEN, 29000, 36000"],
         reference="CYL, -50,0,0, 15, 100, 1,0,0\nCYL, 0,0,0, 15, 50, 0,0,1\nUNION, 1, 2\n"
                   "CYL, -51,0,0, 12, 102, 1,0,0\nSUBTRACT, LAST-1, LAST\nCYL, 0,0,0, 12, 51, 0,0,1\n"
                   "SUBTRACT, LAST-1, LAST"),
    Task("spring",
         "Make a compression spring of 2 mm wire: 20 mm outside diameter, 8 turns, 40 mm long.",
         ["VALID({b})", "BBOX({b}).dx, BETWEEN, 19.5, 20.6", "BBOX({b}).dz, BETWEEN, 38, 42.5"],
         reference="SPRING, 0,0,0, 9, 4.75, 8, 2"),
    Task("vase",
         "Make a vase by revolving a profile: 80 mm tall, 40 mm across at the bottom, 60 mm at the widest "
         "(halfway up) and 30 mm at the top rim, hollow with 2 mm walls, closed at the bottom, open at the top.",
         ["VALID({b})", "BBOX({b}).dz, BETWEEN, 79, 81", "BBOX({b}).dx, BETWEEN, 58, 62.5",
          "VOL({b}), BETWEEN, 15000, 50000"],
         reference="SKETCH, outer, XZ\nSPOLY, 0,0, 20,0, 30,40, 15,80, 0,80, 0,0\nENDSKETCH\n"
                   "REVOLVE, outer, Z\nSKETCH, inner, XZ\nSPOLY, 0,2, 18,2, 28,40, 13,80.5, 0,80.5, 0,2\n"
                   "ENDSKETCH\nREVOLVE, inner, Z\nSUBTRACT, LAST-1, LAST"),
    Task("bolt_and_nut",
         "Make a bolt and a nut: a cylinder bolt 8 mm across and 40 mm long with a hexagonal head 13 mm across "
         "the flats and 5 mm tall, and a separate hex nut 13 mm across the flats and 6.5 mm thick with an 8 mm "
         "hole, placed beside the bolt (no threads needed).",
         ["COUNT(\"BODY\"), GE, 2", "VALID({b})", "HOLES({b2}, 8, 1), EQ, 1", "BBOX({b}).dz, BETWEEN, 44.5, 45.5"],
         reference="SKETCH, head, XY\nSPOLY, 7.5056,0, 3.7528,6.5, -3.7528,6.5, -7.5056,0, -3.7528,-6.5, "
                   "3.7528,-6.5, 7.5056,0\nENDSKETCH\nEXTRUDE, head, 5\nCYL, 0,0,5, 4, 40\nUNION, LAST-1, LAST\n"
                   "SKETCH, nut, XY\nSPOLY, 37.5056,0, 33.7528,6.5, 26.2472,6.5, 22.4944,0, 26.2472,-6.5, "
                   "33.7528,-6.5, 37.5056,0\nENDSKETCH\nEXTRUDE, nut, 6.5\nCYL, 30,0,-1, 4, 8.5\n"
                   "SUBTRACT, LAST-1, LAST"),
    Task("edit_width",
         "Make the plate 60 mm wide instead of 40, keeping the hole in its middle.",
         ["BBOX(plate).dx, BETWEEN, 59.9, 60.1", "HOLES(plate, 8, 1), EQ, 1",
          "CENT(plate)[0], BETWEEN, 29.9, 30.1", "HISTORY(), EQ, {n0}"],
         setup="W = 40\nBLOCK, 0,0,0, W,30,10\nNAME, LAST, plate\nCYL, W/2,15,-1, 4, 12\nSUBTRACT, plate, LAST",
         reference="HIST, EDIT, 1, \"W = 60\""),
    Task("selected_face_holes",
         "Put four 5 mm holes, 8 mm deep, into the selected face, each 6 mm in from two edges of its corner.",
         ["HOLES(plate, 5, 0), EQ, 4", "VALID(plate)", "VOL(plate), BETWEEN, 12000 - 4*19.64*8 - 30, "
          "12000 - 4*19.64*8 + 30"],
         setup="BLOCK, 0,0,0, 40,30,10\nNAME, LAST, plate\nSEL, S, FACE, NORMAL, 0,0,1",
         reference="HOLE, plate, 6,6,10, 5, 8\nHOLE, plate, 34,6,10, 5, 8\nHOLE, plate, 6,24,10, 5, 8\n"
                   "HOLE, plate, 34,24,10, 5, 8"),
    Task("impossible_fillet",
         "Round all edges of the plate with a 30 mm radius.",
         [],
         setup="BLOCK, 0,0,0, 40,30,10\nNAME, LAST, plate",
         refuse=("too large", "too big", "cannot", "can't", "not possible", "impossible", "larger than",
                 "at most", "maximum"), area="fixing-failed-steps"),
    # ---- one or more per skill area (PLAN item 47) ----
    Task("imported_holes",
         "This plate came from another program with no history. Make every 6 mm hole in it 8 mm, and leave "
         "the 10 mm hole as it is.",
         ["VALID(plate)", "HOLES(plate, 8, 1), EQ, 4", "HOLES(plate, 6, 1), EQ, 0", "HOLES(plate, 10, 1), EQ, 1"],
         setup="BLOCK, 0,0,0, 80,50,8\nNAME, LAST, plate\nHOLE, plate, 10, 10, 8, 6\nHOLE, plate, 70, 10, 8, 6\n"
               "HOLE, plate, 10, 40, 8, 6\nHOLE, plate, 70, 40, 8, 6\nHOLE, plate, 40, 25, 8, 10",
         reference="RESIZE, plate, HOLE, EQ, 6, 8", area="imported-parts"),
    Task("sheet_bracket",
         "Make a sheet metal bracket from 2 mm sheet: a flat 60 x 40 mm base with a 25 mm wall bent up along "
         "one of its 60 mm edges (bend radius 2), and its flat blank as a separate body beside it.",
         ["VALID({b})", "COUNT(\"BODY\"), GE, 2", "BBOX({b}).dz, BETWEEN, 24, 30",
          "BBOX({b2}).dz, BETWEEN, 1.99, 2.01"],
         reference="SKETCH, base, XY\nSRECT, 0, 0, 60, 40\nENDSKETCH\nSHEET, base, 2, 2\nNAME, LAST, bracket\n"
                   "SEL, S, EDGE, AT, 30, 0, 2\nFLANGE, , 25\nSEL, NONE\nUNFOLD, bracket",
         area="sheet-metal"),
    Task("enclosure_base",
         "Make the base of a plastic enclosure: 100 x 60 mm outside, 30 mm tall, open at the top, 2 mm walls "
         "and bottom, with a screw boss in each inside corner for a 2.5 mm screw.",
         ["VALID({b})", "PIECES({b}), EQ, 1", "BBOX({b}).dx, BETWEEN, 99.5, 100.5",
          "BBOX({b}).dz, BETWEEN, 29.5, 32.5", "HOLES({b}, 2.5), EQ, 4",
          "VOL({b}), BETWEEN, 20000, 32000"],
         reference="BLOCK, 0, 0, 0, 100, 60, 30\nNAME, LAST, base\nSEL, S, FACE, LOC, Z, 30\nSHELL, 2\nSEL, NONE\n"
                   "BOSS, base, 8, 8, 2, 12, 6, 2.5\nBOSS, base, 92, 8, 2, 12, 6, 2.5\n"
                   "BOSS, base, 8, 52, 2, 12, 6, 2.5\nBOSS, base, 92, 52, 2, 12, 6, 2.5",
         area="enclosure"),
    Task("gear_pair",
         "Make two spur gears that mesh: module 2, 20 and 40 teeth, 10 mm wide, each with an 8 mm bore, placed "
         "at the right centre distance.",
         ["COUNT(\"BODY\"), GE, 2", "VALID({b})", "VALID({b2})", "OVERLAP({b}, {b2}), EQ, 0",
          "DISTANCE(CENT({b}), CENT({b2})), BETWEEN, 59.9, 60.1", "HOLES({b}, 8, 1), EQ, 1"],
         reference="GEAR, 0, 0, 0, 2, 20, 10, , , 8\nGEAR, 60, 0, 0, 2, 40, 10, , , 8\nROTATE, LAST, 4.5, 60, 0, 0",
         area="gears-and-cams"),
    Task("frame",
         "Make a welded rectangular frame 600 x 400 mm (outside) from 30 x 30 x 2 square tube, mitred at the "
         "corners, lying flat.",
         ["COUNT(\"BODY\"), GE, 4", "VALID({b})", "BBOX({b}).dz, BETWEEN, 29.5, 30.5"],
         reference="POLYLINE, (15,15,15), (585,15,15), (585,385,15), (15,385,15), CLOSE\nHIDE, LAST\n"
                   "MEMBER, LAST, SQUARE, 30x2, MITRE, rail",
         area="frames-and-welds"),
    Task("print_upright",
         "This part has to be 3D printed without supports. Turn it so nothing overhangs; do not change its shape.",
         ["OVERHANGS(part), LE, 1", "VOL(part), BETWEEN, 9999, 10001", "VALID(part)"],
         setup="BLOCK, 0, 0, 20, 40, 40, 5\nNAME, LAST, part\nBLOCK, 15, 15, 0, 10, 10, 20\nUNION, part, LAST",
         reference="ROTATE, part, 180, 20, 20, 12.5, 1, 0, 0",
         area="manufacturing"),
    Task("shell_model",
         "The analysis app needs a shell model of this 2 mm bracket: make its middle surface, keeping the "
         "thickness on the faces.",
         ["COUNT(\"BODY\"), GE, 2", "AREA(bracket_mid, \"BODY\"), BETWEEN, 6890, 6910"],
         setup="BLOCK, 0, 0, 0, 100, 50, 2\nNAME, LAST, bracket\nBLOCK, 0, 0, 0, 2, 50, 40\nUNION, bracket, LAST",
         reference="MIDSURFACE, bracket",
         area="analysis-prep"),
    Task("name_inlet",
         "The analysis app needs to know where the water comes in: name the pipe's top end face inlet and its "
         "bottom end face outlet, so the STEP file carries them.",
         ["SETSIZE(\"inlet\"), EQ, 1", "SETSIZE(\"outlet\"), EQ, 1",
          "SETAREA(\"inlet\"), BETWEEN, 112.9, 113.2", "SETAREA(\"outlet\"), BETWEEN, 112.9, 113.2"],
         setup="CYL, 0, 0, 0, 10, 80\nNAME, LAST, pipe\nCYL, 0, 0, 0, 8, 80\nSUBTRACT, pipe, LAST",
         reference="SEL, S, FACE, NORMAL, 0, 0, 1\nCM, inlet, FACE\nSEL, S, FACE, NORMAL, 0, 0, -1\nCM, outlet, FACE",
         area="analysis-prep"),
    Task("strength",
         "The aluminium bracket carries 400 N straight down on its tip face (set tip) with the wall face (set "
         "wall) fixed. Make its plates thick enough for a safety factor of at least 2, keeping its 60 x 40 x 50 "
         "outside size.",
         ["SAFETY(bracket, \"wall\", \"tip\", 0, 0, -400), GE, 2", "BBOX(bracket).dx, BETWEEN, 59.9, 60.1",
          "BBOX(bracket).dz, BETWEEN, 49.9, 50.1"],
         setup="T = 2\nBLOCK, 0, 0, 0, 60, 40, T\nNAME, LAST, bracket\nBLOCK, 0, 0, 0, T, 40, 50\n"
               "UNION, bracket, LAST\nMATERIAL, bracket, ALUMINIUM\nSEL, S, FACE, NORMAL, -1, 0, 0\nCM, wall, FACE\n"
               "SEL, S, FACE, NORMAL, 1, 0, 0\nSEL, R, FACE, LOC, X, 60\nCM, tip, FACE\nSEL, NONE",
         reference="HIST, EDIT, 1, \"T = 5\"",
         area="strength-and-weight"),
    Task("pin_in_hole",
         "Put the pin into the plate's hole: on the hole's axis, its bottom flush with the bottom of the plate.",
         ["CENT(pin)[0], BETWEEN, 19.95, 20.05", "CENT(pin)[1], BETWEEN, 14.95, 15.05",
          "BBOX(pin).zmin, BETWEEN, -0.05, 0.05", "OVERLAP(pin, plate), EQ, 0"],
         setup="BLOCK, 0, 0, 0, 40, 30, 8\nNAME, LAST, plate\nHOLE, plate, 20, 15, 8, 6\n"
               "CYL, 70, 40, 5, 3, 20\nNAME, LAST, pin",
         reference="MOVE, pin, -50, -25, -5",
         area="assembly-and-motion"),
    Task("fix_failed_step",
         "Since I changed R, a step fails. Fix it so every step works again, with the rounding as large as it "
         "can be (a little under the limit is fine).",
         ["FAILED(), EQ, 0", "VALID(box)", "NFACES(box, \"cylinder\"), GE, 4"],
         setup="R = 0.3\nBLOCK, 0, 0, 0, 20, 20, 10\nNAME, LAST, box\nSEL, S, FACE, NORMAL, 0, 0, 1\nSHELL, 1\n"
               "SEL, S, EDGE, BODY, box\nFILLET, R\nHIST, EDIT, 1, \"R = 3\"",
         reference="HIST, EDIT, 1, \"R = 0.45\"",
         area="fixing-failed-steps"),
    Task("hole_grid",
         "Add a grid of 4 x 3 through holes of 5 mm, 15 mm apart, centred on the plate.",
         ["HOLES(plate, 5, 1), EQ, 12", "CENT(plate)[0], BETWEEN, 39.99, 40.01",
          "CENT(plate)[1], BETWEEN, 29.99, 30.01", "VALID(plate)"],
         setup="BLOCK, 0, 0, 0, 80, 60, 6\nNAME, LAST, plate",
         reference="*DO, i, 0, 3\n*DO, j, 0, 2\nHOLE, plate, 17.5 + 15*i, 15 + 15*j, 6, 5\n*ENDDO\n*ENDDO",
         area="holes-and-patterns"),
    Task("vent_holes",
         "The lid has one 3 mm vent hole in its corner. Cover the whole top with holes like it, 6 mm apart in "
         "staggered rows, keeping at least 4 mm of solid lid round the edge.",
         ["HOLES(lid, 3, 1), GE, 60", "HOLES(lid, 3, 1), LE, 140", "VALID(lid)", "PIECES(lid), EQ, 1"],
         setup="BLOCK, 0, 0, 0, 80, 50, 2\nNAME, LAST, lid\nHOLE, lid, 7, 7, 2, 3",
         reference="PATTERN, FILL, lid, 1, 6, 6, 4, HEX",
         area="holes-and-patterns"),
    Task("rounded_plate",
         "Sketch a 50 x 30 mm rectangle with 5 mm rounded corners and extrude it 8 mm.",
         ["VALID({b})", "VOL({b}), BETWEEN, 11800, 11860", "NFACES({b}, \"cylinder\"), EQ, 4"],
         reference="SKETCH, s, XY\nSRECT, 0, 0, 50, 30\nSFILLET, 1.E, 5\nSFILLET, 2.E, 5\nSFILLET, 3.E, 5\n"
                   "SFILLET, 4.E, 5\nENDSKETCH\nEXTRUDE, s, 8",
         area="sketch-to-solid"),
    Task("screw",
         "Make a standard M8 hex head screw, 30 mm long, with a real thread.",
         ["VALID({b})", "BBOX({b}).dz, BETWEEN, 34, 37", "BBOX({b}).dx, BETWEEN, 12.5, 15.5"],
         reference="FASTENER, HEXBOLT, M8, 0, 0, 0, 30, REAL",
         area="fasteners-and-threads"),
    Task("loft",
         "Make a solid that changes from a 40 mm square at the bottom to a 20 mm circle 50 mm higher up.",
         ["VALID({b})", "BBOX({b}).dz, BETWEEN, 49.9, 50.1", "BBOX({b}).dx, BETWEEN, 39.9, 40.1",
          "VOL({b}), BETWEEN, 30000, 50000"],
         reference="RECT, 0, 0, 0, 40, 40\nCIRCLE, 0, 0, 50, 10\nLOFT, LAST - 1, LAST",
         area="curves-and-surfaces"),
    Task("scan_back",
         "The part is a mesh from a scan. Turn it back into an exact solid with real flat faces and a real "
         "hole, and delete the mesh.",
         ["COUNT(\"BODY\"), EQ, 1", "VALID({b})", "NFACES({b}), LE, 20", "HOLES({b}), EQ, 1"],
         setup="BLOCK, 0, 0, 0, 60, 40, 20\nNAME, LAST, part\nCYL, 30, 20, -1, 6, 30\nSUBTRACT, part, LAST\n"
               "TOMESH, part\nNAME, part, scan",
         reference="SEGMENT, scan\nRECONSTRUCT, scan\nDELETE, scan",
         area="scan-to-cad"),
    Task("tutorial_holes",
         "I'm on the 'Drill two holes' step of the first-part tutorial and can't get it to work. Do it for me: "
         "two 8 mm holes right through the plate, 15 mm in from each end, in the middle of its width.",
         ["HOLES(plate, 8), GE, 2", "VALID(plate)", "FAILED(), EQ, 0"],
         setup="BLOCK, 0, 0, 0, 80, 50, 10\nNAME, LAST, plate",
         reference="HOLE, plate, 15, 25, 10, 8\nHOLE, plate, 65, 25, 10, 8",
         area="tutor"),
    Task("impossible_shell",
         "Hollow out the cube with 12 mm walls, open at the top.",
         [],
         setup="BLOCK, 0, 0, 0, 20, 20, 20\nNAME, LAST, cube",
         refuse=("too thick", "too large", "cannot", "can't", "not possible", "impossible", "thinner",
                 "at most", "maximum", "less than"), area="fixing-failed-steps"),
]

for _t in TASKS:  # the first ten tasks' areas
    _t.area = {"flange": "holes-and-patterns", "bracket": "modeling-basics", "shelled_box": "enclosure",
               "pipe_tee": "modeling-basics", "spring": "fasteners-and-threads", "vase": "sketch-to-solid",
               "bolt_and_nut": "fasteners-and-threads", "edit_width": "editing-a-model",
               "selected_face_holes": "holes-and-patterns"}.get(_t.name, _t.area)
AREAS = sorted({t.area for t in TASKS})
PICTURE_TOOLS = ("render", "render_detail", "render_compare")
# the run modes the benchmark compares: (small first prompt, skills on)
MODES = {"full": (False, True), "small": (True, True), "noskills": (False, False), "small-noskills": (True, False)}


@dataclass
class Result:
    name: str
    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""
    turns: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    pictures: int = 0
    seconds: float = 0.0
    tools: list[str] = field(default_factory=list)
    answer: str = ""


def fresh(task: Task):
    """The processor a task starts from."""
    from ..commands import Processor

    p = Processor()
    for res in p.run_script(task.setup) if task.setup else []:  # one history step per line
        if not res.ok:
            raise RuntimeError(f"{task.name}: the setup failed: {res.message}")
    return p


def _largest(p) -> tuple[int, int]:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    vols = []
    for bid, b in p.model.bodies.items():
        g = GProp_GProps()
        try:
            BRepGProp.VolumeProperties_s(b.shape, g)
            vols.append((abs(g.Mass()), bid))
        except Exception:  # noqa: BLE001 - a body without volume
            vols.append((0.0, bid))
    vols.sort(reverse=True)
    first = vols[0][1] if vols else 0
    second = vols[1][1] if len(vols) > 1 else first
    return first, second


def score(task: Task, p, n0: int, proposals: list[list[str]], answer: str) -> tuple[bool, list[dict], str]:
    """Run the proposals (each a list of command lines) and check. Returns (passed, checks, note)."""
    if task.refuse:
        if proposals:
            return False, [], "proposed something for an impossible request"
        said = answer.lower()
        ok = any(w in said for w in task.refuse)
        return ok, [], "" if ok else "proposed nothing, but did not say why"
    if not proposals:
        return False, [], "proposed nothing"
    for lines in proposals:
        for line in lines:
            res = p.run(line)
            if not res.ok:
                return False, [], f"the proposal failed: {res.message.splitlines()[0][:200]}"
    if not p.model.bodies:
        return False, [], "no bodies"
    b, b2 = _largest(p)
    rows, passed = [], True
    for text in task.checks:
        line = (text.replace("{b}", str(b)).replace("{b2}", str(b2)).replace("{n0}", str(n0))
                .replace("HISTORY()", str(p.cursor))
                .replace("FAILED()", str(sum(1 for e in p.history[:p.cursor] if not e.ok and not e.suppressed))))
        try:
            out = expect.check(p, line).as_dict()
        except expect.ExpectError as exc:
            out = {"check": line, "pass": False, "error": str(exc)}
        rows.append(out)
        passed = passed and bool(out.get("pass"))
    return passed, rows, ""


AskFn = Callable[[Task, Any], Awaitable[Any]]  # (task, processor) -> a copilot.Reply


async def run_task(task: Task, ask: AskFn) -> Result:
    p = fresh(task)
    n0 = p.cursor
    t = time.time()
    reply = await ask(task, p)
    seconds = time.time() - t
    proposals = [prop.commands() for prop in reply.proposals]
    if reply.error:
        passed, checks, note = False, [], f"error: {reply.error}"
    else:
        passed, checks, note = score(task, p, n0, proposals, reply.text)
    return Result(task.name, passed, checks, note, reply.turns, reply.input_tokens, reply.output_tokens,
                  len(reply.tools), sum(reply.tools.count(n) for n in PICTURE_TOOLS), round(seconds, 1),
                  list(reply.tools), reply.text[:400])


def _say(text: str) -> None:
    print(text, flush=True)


async def run(ask: AskFn, only: list[str] | None = None, log: Callable[[str], None] = _say) -> list[Result]:
    results = []
    for task in TASKS:
        if only and task.name not in only:
            continue
        log(f"{task.name} ...")
        r = await run_task(task, ask)
        log(f"  {'PASS' if r.passed else 'FAIL'}  {r.turns} turns, {r.tool_calls} tool calls, {r.pictures} "
            f"pictures, {r.input_tokens}+{r.output_tokens} tokens, {r.seconds:g} s"
            + (f"  ({r.note})" if r.note else "")
            + "".join(f"\n        failed: {c.get('check')} {c.get('error') or c.get('actual', '')}"
                      for c in r.checks if not c.get("pass")))
        results.append(r)
    return results


def summary(results: list[Result]) -> dict[str, Any]:
    n = len(results)
    ok = sum(r.passed for r in results)
    return {"tasks": n, "passed": ok, "without_pictures": sum(r.passed and not r.pictures for r in results),
            "goal_met": n > 0 and ok >= round(0.9 * n),
            "tokens": sum(r.input_tokens + r.output_tokens for r in results),
            "tool_calls": sum(r.tool_calls for r in results), "pictures": sum(r.pictures for r in results),
            "seconds": round(sum(r.seconds for r in results), 1)}


def by_area(results: list[Result]) -> dict[str, list[int]]:
    """Skill area -> [passed, tasks]."""
    area = {t.name: t.area for t in TASKS}
    out: dict[str, list[int]] = {}
    for r in results:
        row = out.setdefault(area.get(r.name, "?"), [0, 0])
        row[0] += int(r.passed)
        row[1] += 1
    return dict(sorted(out.items()))


def compare_text(runs: dict[str, list[Result]]) -> str:
    """A table of the modes side by side: passed, tokens, tool calls and pictures, then per task."""
    names = list(runs)
    lines = ["mode            passed  tokens   tool calls  pictures  seconds"]
    for m in names:
        s = summary(runs[m])
        lines.append(f"{m:15} {s['passed']:>3}/{s['tasks']:<3} {s['tokens']:>8} {s['tool_calls']:>11} "
                     f"{s['pictures']:>9} {s['seconds']:>8}")
    lines.append("")
    lines.append("task".ljust(24) + "".join(m[:14].ljust(15) for m in names))
    tasks = [r.name for r in runs[names[0]]]
    for t in tasks:
        cells = []
        for m in names:
            r = next((x for x in runs[m] if x.name == t), None)
            cells.append(("-" if r is None else ("PASS" if r.passed else "fail") + f" {r.input_tokens // 1000}k")
                         .ljust(15))
        lines.append(t.ljust(24) + "".join(cells))
    return "\n".join(lines)


def save_modes(runs: dict[str, list[Result]], path: str, about: dict[str, Any] | None = None) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"about": about or {}, "modes": {m: {"settings": dict(zip(("small_prompt", "skills"), MODES[m]))
                                                       if m in MODES else {}, "summary": summary(rs),
                                                       "by_area": by_area(rs),
                                                       "results": [asdict(r) for r in rs]}
                                                   for m, rs in runs.items()}}, f, indent=1)


def save(results: list[Result], path: str, about: dict[str, Any] | None = None) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"about": about or {}, "summary": summary(results), "by_area": by_area(results),
                   "results": [asdict(r) for r in results]}, f, indent=1)


def assistant_ask(asst) -> AskFn:
    """Ask with a real assistant (Copilot or your own key): a new chat for each task."""
    from .tools import Toolbox

    async def ask(task: Task, p):
        await asst.new_chat()
        asst.toolbox = Toolbox(p)
        return await asst.ask(task.request)

    return ask
