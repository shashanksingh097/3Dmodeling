# 3Dmodeling user guide

3Dmodeling is a 3D modeler for solid parts. Everything you do with the mouse
is turned into a short line of text, a **command**, and kept in the
**History**. So every model is also a script: you can edit any step later,
change a number and watch the part rebuild, or write the whole part as text.

This guide covers version 0.7. It is also on the
[user guide website](https://shashanksingh097.github.io/3Dmodeling/), with a
tested example for every command. The full command language is in
[LANGUAGE.md](LANGUAGE.md), and inside the app under **Help > Command reference**
(Ctrl+F1): every command under the same headings as the command menu, with a
search box, what each argument means, lines from the example scripts that use
it, and buttons that open its form or put it in the command line. With a
command typed, Ctrl+F1 opens at that command.

Contents:

1. [Install](#1-install)
2. [The window](#2-the-window)
3. [Your first part, with the mouse](#3-your-first-part-with-the-mouse)
4. [The same part as a script](#4-the-same-part-as-a-script)
5. [Changing a part later](#5-changing-a-part-later)
6. [Sketches](#6-sketches)
7. [More ways to make shapes](#7-more-ways-to-make-shapes)
8. [Parts you can reuse](#8-parts-you-can-reuse)
9. [Layers, colours and materials](#9-layers-colours-and-materials)
10. [Measuring and checking](#10-measuring-and-checking)
11. [Saving, opening, import and export](#11-saving-opening-import-and-export)
12. [Running scripts without the window](#12-running-scripts-without-the-window)
13. [Keyboard shortcuts](#13-keyboard-shortcuts)
14. [When something goes wrong](#14-when-something-goes-wrong)
15. [The assistant (GitHub Copilot)](#15-the-assistant-github-copilot)

---

## 1. Install

### Download (no Python needed)

Get the installer (or the zip) for your system from the
[Releases page](https://github.com/shashanksingh097/3Dmodeling/releases):

| System | Download | Start it |
|--------|----------|----------|
| Windows 10 or 11 (64-bit) | `3Dmodeling-<version>-windows-x64.msi` (from 0.4.0), or the `.zip` | run the `.msi`; 3Dmodeling is then in the Start menu and can be removed in Settings > Apps. Or unzip the zip, open the folder, run `3Dmodeling.exe` |
| macOS 12 or later on Apple silicon (M1 and newer) | `3Dmodeling-<version>-macos-arm64.dmg` (from 0.4.0), or the `.zip` | open the `.dmg` and drag `3Dmodeling.app` onto Applications; or unzip and move it there. Then open it |
| Linux (64-bit, X11 or XWayland) | `3Dmodeling-<version>-linux-x64.tar.gz` | `tar xzf` it, run `3Dmodeling/3Dmodeling` |

The builds are not signed yet, so the first start shows a warning:

* **Windows**: "Windows protected your PC". Press *More info*, then *Run anyway*.
* **macOS**: right-click `3Dmodeling.app`, choose *Open*, then *Open* again.
  If it says the app "is damaged", run
  `xattr -dr com.apple.quarantine /Applications/3Dmodeling.app` once in Terminal.

### With Python (any system, also Intel Macs)

You need Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install git+https://github.com/shashanksingh097/3Dmodeling
modeler                            # or: python -m modeler
```

For the assistant (section 15) you need Python 3.11 or newer and
`pip install "modeler3d[ai] @ git+https://github.com/shashanksingh097/3Dmodeling"`.

`modeler check` prints the versions and tests the 3D kernel. If the window
does not open, see [When something goes wrong](#14-when-something-goes-wrong).

---

## 2. The window

| Part | What it does |
|------|--------------|
| **3D view** (middle) | the model. Left drag orbits, middle or right drag pans, the wheel zooms, **F** fits everything in view. A right click (without dragging) opens a menu for the body under the mouse |
| **Command line** (below the view) | type any command and press Enter. It suggests command names as you type and shows the arguments of the one you are typing |
| **Form** button, **F2** | opens a fill-in form for the command you are typing, so you never need to remember argument order |
| **Output** (bottom) | what each command did, and errors in plain words |
| **Model** (left) | every part with its placed copies, every body, sketch, datum and named set. Click a row to pick the body, untick it to hide it, double-click to zoom to it, right-click for the same menu as in the 3D view |
| **History** (right) | every step that built the model, in order. Grey steps are undone; red steps failed; amber steps ran but want a look |
| **Parameters** (right, tab) | named numbers such as `W = 80`. Change one and the model rebuilds |
| **Layers** (right, tab) | show, hide, lock and colour groups of bodies |
| **Ribbon** (top) | one row of tabs, each holding a few labelled groups of buttons with an icon and a name: **Home** (File, Edit with undo, redo and find a command, Pick, View), **Model** (Shapes, Booleans, Patterns), **Features** (Sketch, Datums, and hole, fillet, chamfer, shell, draft, push/pull, delete faces), **Freeform** (control points, knife, zebra) and **Inspect** (measuring). While a sketch is open, **Sketch**, **Sketch edit** and **Constrain** tabs appear. Undo, redo, the pick modes and Fit stay as small icons at the right of the tabs on every tab. Double-click a tab to fold the ribbon to its tab names; click a tab to use it once. |
| **Pick** and **View** (left of the 3D view) | what a click picks (body, face, edge, vertex), and the standard views and Fit |
| **Menus** | **File**; **Commands**, a form for every command, by group; **View** (how toolbar buttons show: icons with names under or beside them, icons only, or names only; Collapse ribbon; Ribbon tab to jump to a tab; **Preferences…**); **Help** |

**Preferences** (View > Preferences…, Ctrl+,): the theme (the system's,
light or dark), the 3D view's background (grey, dark, light or white) and
how toolbar buttons show. Changes apply at once and are kept.

**Picking.** A click picks what is under the mouse: a face by default, or
an edge, vertex or body if you choose that on the toolbar. Ctrl+click adds
to the pick, Alt+click removes. Feature buttons such as **Hole…** and
**Shell…** work on what is picked. A pick is a command too (`PICK, FACE, 6`),
so it is replayable.

---

## 3. Your first part, with the mouse

A plate with two holes and rounded top edges.

1. **File > New** (Ctrl+N).
2. Click **Block…** on the toolbar. Set the size to 80, 40, 8 and press
   **OK**. The form shows the command it runs:
   `BLOCK, 0,0,0, 80, 40, 8`.
3. Click the top face of the block, then **Hole…** on the Features toolbar,
   and give a diameter of 8. A through hole appears in the middle of the
   face. To place holes exactly, use the form instead:
   **Commands > Features > Hole…** and type the position.
4. Pick **Edge** on the toolbar, then Ctrl+click the four top edges of the
   plate. Open **Commands > Features > Fillet…**, give a radius of 2, and
   press **OK**.
5. **File > Save** (Ctrl+S) and give it a name such as `bracket.m3d`.

Look at the **History** panel: every step you made is there as a line of
text. Double-click the `BLOCK` line, change 80 to 120, and press OK. The
holes and fillets are made again on the longer plate.

---

## 4. The same part as a script

Type these lines one by one in the command line, or save them as
`bracket.cmd` and use **File > Run script…**:

```text
! a bracket: plate, two holes, a rounded top edge
W = 80
T = 8
BLOCK, 0,0,0, W, 40, T
NAME, LAST, bracket
HOLE, bracket, 15, 20, T, 8
HOLE, bracket, W - 15, 20, T, 8
SEL, S, EDGE, LOC, Z, T
FILLET, 2
```

What the lines mean:

* `!` starts a comment.
* `W = 80` makes a **parameter**. Any number in any command can be an
  expression of parameters, such as `W - 15`.
* `NAME, LAST, bracket` names the newest body, so later lines can say
  `bracket` instead of a number.
* `SEL, S, EDGE, LOC, Z, T` selects every edge at height `T`, the top
  edges. Picking by meaning, not by number, keeps the script right when
  sizes change.

Now change `W` in the **Parameters** panel to 120. The whole part rebuilds.

Scripts can also loop, branch and define your own commands (`*DO`, `*IF`,
`*MACRO`). See [LANGUAGE.md](LANGUAGE.md) sections 2 to 4, and open
**File > Open example** for finished models; [EXAMPLES.md](EXAMPLES.md) shows each one with a picture and its script.

---

## 5. Changing a part later

Right-click a step in the **History** panel:

| Choice | Does |
|--------|------|
| **Edit…** (or double-click) | change the text of the step; everything after it runs again |
| **Edit in form…** | the same, in the command's form |
| **Insert before…** | add a step at that point in the history |
| **Suppress** / **Resume** | leave the step out for now, or bring it back |
| **Delete** | remove the step |
| **Roll back to here** | show the model as it was after this step; the later steps stay, greyed (Redo, or **Redo up to here**, brings them back). Undo takes the roll back back |
| **Make a part from steps …** | with several steps selected, turn them into a reusable part |

**From the model tree.** Pick a body in the **Model** tree (or in the 3D
view): the panel under the tree lists every step that made it, and the
parameters those steps use. Double-click a step (or **Edit step…**) to change
it in its form. For a body placed from a part, such as one of 8 bolts, the
list holds the lines of the part's recipe (head, shank, `THREAD`): change
the thread's pitch there and all 8 bolts are rebuilt. Type a new value next
to a parameter to change it.

When a step is edited, picks made after it still point at the same faces
and edges where possible. If the app had to guess, the step turns amber and
says so. A step that fails turns red with the reason, and the steps after it
wait until it is fixed.

Long rebuilds show a progress bar with **Cancel**, which puts everything
back as it was. When the steps to re-run took a second or more last time,
the rebuild runs in a separate helper process: the window stays live, so
you can turn and zoom the view while it works (other commands wait until it
is done), and Cancel stops it at once.

---

## 6. Sketches

A sketch is a flat drawing held by constraints and sizes, which you then
push (**Extrude**) or turn (**Revolve**) into a solid.

1. Pick a flat face (or nothing, to choose a plane), then press **Sketch**.
   The view turns to face the sketch and three tabs appear on the ribbon:
   **Sketch** (drawing), **Sketch edit** and **Constrain** (constraints and
   sizes).
2. Draw with Line (L), Centreline, Rectangle (R), Centre rect, Angled rect,
   Circle (C), 3-point circle, Arc (A), Tangent arc (N, click the end of a
   line or arc, then where the arc ends), Slot, Arc slot, Polygon (G; the
   number of sides is next to it), Ellipse (I; centre, end of one axis, then
   the width), Elliptical arc, Tangent circle (click two or three curves,
   then near where it goes) and Point (P). Clicks snap to points, middles,
   curves and the axes. While you draw, a click on a curve puts the point on
   it, and a line drawn on from an arc's end is made tangent to it: the
   small mark by the cursor (On 3, Tangent, Perpendicular, H, V) shows what
   the click adds. Hold Shift to draw without them, or switch off **Auto
   constraints**.
3. Select geometry and press a constraint button (horizontal, parallel,
   tangent, ...) or **Size…** to give a length, radius or angle (for an
   ellipse its two radii; for a point and a circle how far it is from the
   rim), or **Arc length…**. The sketch
   turns green when it is fully defined.
4. Tidy up with Trim (T; click a piece, or drag across several pieces to
   cut every one the mouse passes over), Extend (E), Fillet (F) and Chamfer
   (K) at a corner, Split (B; click where a curve should be split) and
   Corner (O; click the part of each of two curves to keep, and they are
   trimmed or extended to meet). Switch on **Axes cut** to let the H and V
   axes cut when trimming. **Offset…**, **Mirror…**, **Pattern…**,
   **Move/Copy…** (move, turn or scale the selection, or copies of it),
   **Offset both…** (a slot along the selected path), **Join to spline**
   (the selected curves, end to end, as one smooth spline), **Project…** and
   **Cut bodies…** (the section of bodies in the sketch plane) are there too.
   Trim, Extend, Split and Fillet work on splines as well. **From DXF…**
   reads a 2D DXF drawing into the sketch, **Trace picture…** traces the
   dark shapes of a picture into it, and **Picture…** shows a picture on a
   plane behind the model to draw over.
5. Press **Extrude…** or **Revolve…**. Make a new body, add a boss to the
   body under the sketch, or cut a pocket.

To change a size later, right-click the sketch in History and choose
**Sizes of sketch …**. Details: [LANGUAGE.md](LANGUAGE.md) section 16.

---

## 7. More ways to make shapes

All of these are in the **Commands** menu with forms, and in
[LANGUAGE.md](LANGUAGE.md):

| Kind | Commands |
|------|----------|
| Basic solids | `BLOCK`, `CYL`, `TUBE`, `CONE`, `SPHERE`, `TORUS`, `WEDGE` |
| Combine | `UNION`, `SUBTRACT`, `INTERSECT` (and `KEEP, ON` to keep the inputs) |
| Copies | `COPY`, `MIRROR`, `ARRAY` (in a row, around an axis, along a path), `PATTERN` (repeat the last few steps) |
| Features | `HOLE` (plain, counterbore, countersink, threaded with `THREAD`), `FILLET`, `CHAMFER`, `SHELL`, `DRAFT`, `OFFSET`, `SPLIT` |
| From curves | `LOFT` through sections, `SWEEP` along a path with twist and scale laws, `MORPH`, `PIPE`, `RAILSWEEP` between rails, `SPINELOFT` |
| Special | `THREAD` (real ISO threads), `SPRING`, `TEXT`, `SURFACE, PARAM` (shapes from equations) |
| Edit faces | `PUSHPULL` (move faces), `DELFACE` (remove a hole or fillet and close the gap); handy on imported parts |
| Build on | `PLANE`, `AXIS`, `POINT` datums and `WORKPLANE` to draw on any plane |
| Freeform (NURBS) | `NURBS` curves and `NSURF` surfaces from control points, `NETWORK` through a grid of curves, `FILL` a hole, `SEW` surfaces into a solid, `REBUILD`, `MOVEPT`, `WEIGHT`, `KNOT`, `DEGREE` |
| Freeform edits | `BLEND` two surfaces smoothly (G1 or G2), `EXTEND`, `TRIM`, `MOVEFACE`, `REPLACEFACE`, `LOFT, ..., GUIDE` (lofts steered by guide curves), `PROJECT` a curve onto a surface |
| Deform | `BEND`, `TWIST`, `TAPER`, `STRETCH` whole bodies, `FLOW` a body (a text, say) along a curve, `SWEEPVOL` the volume a cutter sweeps |

The **Sweep editor** on the Features toolbar shapes a sweep's twist and
scale by dragging handles on a graph, with a live preview.

**Control points.** Pick a NURBS curve or surface and press **Control
points**: its control points appear in the 3D view and you can drag them.
Each drag becomes a `MOVEPT` step in the History, so it can be edited later
like any other step.

**Surface quality.** `ANALYZE` (and the **Zebra** button) colours a body
with zebra stripes, curvature or draft for moulding, and says in words
which joins are smooth (G2), tangent (G1) or creased. Details:
[M5-nurbs.md](M5-nurbs.md); a worked example is the computer mouse,
`scripts/mouse.cmd`.

**Families of sizes.** A configuration is a named set of parameter values
(`CONFIG, big, "W = 80, H = 20"`). Pick it from the **Configuration** list
above the parameters and the model rebuilds with those values; **Default**
goes back. **New…** starts one from the values you have now. `BOM` lists
the parts with their quantities, material and mass, and `BOM, parts.csv`
writes the list for a spreadsheet. Details: LANGUAGE.md section 30.

**Sculpting.** The **Sculpt** tab shapes a mesh body like clay. Pick a
body and press **Make sculptable** (it becomes a mesh body with fine, even
triangles), choose a brush (Draw, Clay, Inflate, Smooth, Flatten, Pinch,
Crease, Grab) and drag over the body. Hold Ctrl to work the other way (dig
in), Shift to smooth; `[` and `]` change the brush size, **Mirror X**
works on both sides at once, and the **Mask** brush freezes areas the
other brushes should leave alone (frozen areas show purple). A circle
shows the brush's size under the mouse, and the surface moves as you
drag; Esc during a drag cancels it. Set **Detail** to a small size to
add finer triangles where you brush, for sharp creases. Each stroke is one `SCULPT` step in
History, so Undo takes it back. Details: [LANGUAGE.md](LANGUAGE.md)
section 28; an example is `scripts/sculpt_head.cmd`.

**Scan to CAD.** **Fit surface** on the Sculpt tab (command `FITSURF`)
turns a mesh body into smooth NURBS geometry: a closed, rounded mesh
becomes a solid, and an open scan, or a region you painted with the Mask
brush, becomes one smooth face. Give the largest distance from the mesh
you accept; the message says how close it got. Details: LANGUAGE.md
section 29; an example is `scripts/scan_to_cad.cmd`.

A scan of a machined part (flat faces, holes, bosses) is better as exact
faces: type `RECONSTRUCT, scan` (on the command menu under Mesh bodies).
It splits the mesh at its sharp edges, fits each region as a plane,
cylinder or sphere, and makes one solid; `SEGMENT, scan` first lists the
regions and their fits. Details: LANGUAGE.md section 34; an example is
`scripts/scan_machined.cmd`.

**Sheet metal.** On the **Features** tab, **Sheet** makes a plate of one
thickness from a closed sketch. Pick an edge of its top face and press
**Flange** to bend a wall up along it (an edge of the bottom face bends
down); give the wall's length, the angle and, if it differs from the
sheet's, the bend radius. **Bend** folds the plate itself along a line
you drew in a sketch (the smaller side turns). **Unfold** lays the part flat beside it and can
write a DXF of the blank, with the bend lines and their angles, for a
laser or punch. Details: LANGUAGE.md section 31; an example is
`scripts/sheet_bracket.cmd`.

**Frames.** Draw the frame's lines with `POLYLINE` (or in a sketch) and
press **Member** on the Features tab: pick the profile (square, rectangular
or round tube, flat bar, angle, channel, I-beam), its size like `40x3`,
and mitred or butted corners. Each straight piece becomes one member.
**Cut list** lists what to cut: lengths, end angles and how many of each.
Details: LANGUAGE.md section 36; an example is `scripts/welded_frame.cmd`.

**Strength.** Press **Strength** on the Inspect tab, pick the faces held
still and the faces the load acts on, and give the force (N) or pressure
(MPa). The part is coloured by stress (blue none, red high), and the
message says the largest stress, the deflection and the safety factor
from the part's material. It is a quick check while you design, not a full
analysis. Details: LANGUAGE.md section 37; an example is
`scripts/bracket_strength.cmd`. **Topology…** next to it asks the same
question the other way round: which share of the part carries the load
best? It keeps that much material as a mesh body (the part is hidden) to
model a real part after, and then check with Strength. An example is
`scripts/topo_bracket.cmd`.

**Will it stand up?** **Gravity** on the Inspect tab checks the whole
assembly: parts that float, tip off what they rest on, or are held only at
their sides, small gaps where parts should touch, overlaps, and how far it
can lean before it tips over. Problem parts are marked. List the bolted or
glued parts so they count as held. Details: LANGUAGE.md section 39; an
example is `scripts/gravity_check.cmd`.

**3D printing and milling.** **Print check** on the Inspect tab colours the
part: blue sits on the bed, red overhangs and needs support. It also lists
thin walls and closed hollows, and can pick the build direction that needs
least support. **Mill** makes milling paths for a flat end mill from flat
faces: pockets, outlines and facing. The path shows in the view, and with a
file name the G-code is written. Details: LANGUAGE.md section 38; examples
are `scripts/print_check.cmd` and `scripts/milled_plate.cmd`.

**Ribs, lips and wrapping.** **Rib** (command `RIB`) turns an open sketch
line into a thin wall that runs down to the part: draw the line where the
rib's top edge goes, in a sketch square to the walls. **Lip** keys the two
halves of an enclosure together: pick the rim face of one half for a
raised band, and the rim of the other half with GROOVE for the matching
cut. **Wrap** lays a sketch round a cylindrical or conical face, raised or
cut, for grips, labels and bands. Details: LANGUAGE.md section 32; an example is
`scripts/enclosure_halves.cmd`.

**Gears and fasteners.** **Gear…** (Model tab, Standard parts) makes
spur, helical and internal gears and racks from a module and a tooth
count; the message says the centre distance to a mating gear. **Fastener…**
makes ISO cap screws, hex bolts, nuts and washers from M3 to M24, plain or
with real threads, named and made of steel. **Scale…** (Model tab) makes a
body bigger or smaller. Fillets can change radius along an edge
(`FILLET, 1, 4`), and chamfers can be uneven (`CHAMFER, 1, 3`). Details:
LANGUAGE.md section 41; an example is `scripts/gear_train.cmd`. **Gear…**
also makes bevel gears, a worm and its worm wheel, and helical racks.

**Cams.** **Cam…** (Model tab, Standard parts) makes a disc cam (or a
barrel cam with a groove) and its roller from a lift law such as
`R10/120 D60 F10/120 D60` (rise 10 over 120°, dwell, fall, dwell). Move
the roller by `CAMLIFT(law, A)` when the cam turns by A, and the two work
together in **Motion…**. **Trace path…** (Inspect tab) keeps the path a
point on a moving part follows as a curve. Details: LANGUAGE.md section 45;
an example is `scripts/cam_follower.cmd`.

**Plastic parts.** On the Features tab, **Boss…** adds a screw boss with
ribs, **Snap hook…** a cantilever hook (with the strain it takes to snap
in), and **Vent…** a grille of slots through the wall under the picked
flat face. Details: LANGUAGE.md section 42; an example is
`scripts/plastic_case.cmd`.

**Moulds.** **Parting…** (Inspect tab, Make) shows which faces come out of
which half of a mould, which need draft, any undercuts, and the parting
line. **Mould…** makes the two halves with a shrink allowance. Details:
LANGUAGE.md section 43; an example is `scripts/cap_mould.cmd`.

**Notes and fits.** **Note…** (Inspect tab) pins text, a size, a hole's
diameter or its ISO fit to the model. Notes show in the view and go onto
drawing sheets. **Fits…** gives ISO 286 limits and the clearance or
interference of a fit such as H7/g6. **Weld…** (Features tab, Frames) adds
weld beads where parts meet; the cut list adds their length.

**Sections and tolerances.** **Section…** (Inspect tab) opens a window
with a plane, the side to keep and a slider that moves the plane through
the model; **Add plane** cuts along up to three planes. **Stack-up…**
(Inspect tab, Notes) adds up a chain of sizes with their tolerances and
gives the worst case and statistical gap. **Note…** also puts datum
letters and geometric tolerance frames (flatness, position ...) on a
picked face. Details: LANGUAGE.md section 44.

**Pipes and cables.** **Route…** (Model tab, Pipes) runs a pipe or a cable
along a polyline or sketch, bent at the corners; a route that ends on
another joins it as a tee. **Pipe list** lists the lengths and bends. An
example is `scripts/pipe_run.cmd`.

**Exploded views.** Record how an assembly comes apart with `XSTEP` (the
command menu, under Parts): each step moves some parts by a distance.
`XSHOW, name` then shows the parts apart with thin trail lines back to
their places, and `XSHOW` alone puts them back (so does the next change).
Details: LANGUAGE.md section 35; an example is `scripts/exploded_view.cmd`.

**Moving an assembly.** Write the moving part's position with a parameter
(`A = 30` and then `MATE, ANGLE, ..., A`, or `ROTATE, lid, -A, ...`).
**Motion…** on the Inspect tab opens a window with a slider over that
parameter: the parts move as you drag (the history is not changed), and
Play runs through the range. **Check range** lists every position where
parts overlap and the value where they first meet. **Save pictures…**
writes one picture per step. Closing the window puts the parameter back.
Details: LANGUAGE.md section 33; an example is `scripts/hinged_lid.cmd`.

---

## 8. Parts you can reuse

A part is a model with its own parameters, placed as many times as you
like. Change the part and every copy follows.

```text
*PART, washer, D=10, T=2
  TUBE, 0,0,0, D/2, D/4, T
*ENDPART
INST, washer, 0,0,0
INST, washer, 30,0,0, D=16
```

Save a part to your library with `LIBSAVE, washer`, and load it in another
project with `LIB, LOAD, washer`. In the GUI, select some History steps,
right-click, and choose **Make a part from steps**. Details:
[M4-parts.md](M4-parts.md).

**Design a part on its own.** **File > New part…** starts an empty part:
set its sizes first (`D = 8`), then model it as usual. **File > Save** writes
it as a part file (`.cmd`) that any project can load. **File > Open part…**
opens a part file again with every step editable. To change a part that
lives inside a project, right-click one of its copies and choose **Edit
part**: it opens in its own window, and **Save** there updates every copy.


**Use a part file in an assembly, and keep it up to date.** **File > Link
part file…** (`LIB, LINK, file`) makes the file's parts available for
placing copies, and follows the file: when you change and save the part,
every copy in the assembly updates by itself (**File > Reload linked parts**
does it by hand). Right-click a copy, or its part in the Model tree, and
choose **Open part** to open the part file in its own window; **Save**
there updates the assembly. If the part file is missing when a project
opens, the copy saved in the project is used and the `LIB` step shows a
warning. The Model tree says for each part whether it is linked.

**Put copies together with mates.** Place a copy anywhere, then pick a
face or edge on the part that stays and one on the copy (click, then
Ctrl+click), right-click and choose **Mate the two picked…**. Concentric
lines up two axes (a shank in a hole), Coincident puts two flat faces
against each other (a bolt head on the plate), Distance leaves a gap and
Angle turns the copy. Mates are steps in History, so when the part changes
the copies are placed again. Give a copy its axis first, then its seat.
Details: [LANGUAGE.md](LANGUAGE.md) section 17.

---

## 9. Layers, colours and materials

The **Layers** panel shows, hides, locks and colours groups of bodies.
`MATERIAL, b, STEEL` gives a body a material, so `MASSPROP` reports its mass.
`ISOLATE, b` shows one body alone; `SHOW` brings everything back.

**Right-click a body** in the 3D view for a menu: Hide, Show only this,
Fade this, Fade all others (to see one part clearly inside an assembly),
Show everything, Zoom to, Rename, Colour, Layer, Material, Find the step
that made it, and Delete. Right-click empty space to show everything again.
Hiding and fading from this menu are view steps (`DISPLAY`, `FADE`,
`UNFADE`): they do not add history steps, but they are saved with the
project.
Details: [LANGUAGE.md](LANGUAGE.md) section 22.

---

## 10. Measuring and checking

| Button or command | Gives |
|-------------------|-------|
| **Distance**, `DIST` | shortest distance between two picked things |
| **Angle**, `ANGLE` | angle between two faces or edges |
| **Mass**, `MASSPROP` | volume, area, centre of mass, inertia, and mass with a material |
| **Clash**, `CLASH` | whether bodies overlap, and by how much |
| `CONTACT` | whether parts touch (on a face, a line or a point), how far apart they are, or how much they overlap; alone, which parts hold together and which touch nothing |
| `CLEARANCE` | the clearance or interference of each shaft in a hole |
| `RELATE` | where one part sits relative to another: sides, gaps, centred, rests on, flush faces |
| `COMPARE` | whether two bodies are the same shape, a moved copy or a mirror image |
| `DESIGNCHECK` | broken bodies, loose pieces, tiny edges, slivers, thin walls |
| **Section…**, `SECTION` | cuts the view open on a plane, moved with a slider; the cuts are hatched and their areas listed |
| `CHECK`, `HEAL`, `CLEAN` | finds and repairs broken bodies (often from imports) |
| `THICK`, `PROFILE`, `PROBE` | wall thickness, a cut through a body as text, what a ray hits |
| `ASSERT` | a check inside a script, e.g. `ASSERT, HOLES(bracket, 8), EQ, 2` |

Every boolean, fillet and feature is checked as it runs. A result that would
be broken is refused with a reason, and the model stays as it was.

---

## 11. Saving, opening, import and export

| Menu | Command | Notes |
|------|---------|-------|
| **File > Save** (Ctrl+S), **Save as…** | `SAVE, file.m3d` | a project: the whole history plus copies of the files it imports, so it opens anywhere |
| **File > Open…** (Ctrl+O), **Open recent** | `OPEN, file.m3d` | the history is replayed, so every step is still editable |
| **File > Import…** (Ctrl+I) | `IMPORT, format, file` | STEP, IGES and BREP: each solid becomes a body. STL, OBJ, 3MF, glTF, PLY, OFF, VTK and simulation meshes (`MESH`): each piece becomes a faceted body, a solid when closed |
| **File > Export…** (Ctrl+E) | `EXPORT, format, file [, body]` | STEP or IGES for other CAD programs, STL or 3MF for 3D printing, OBJ or glTF for viewers and game engines, BREP for Open CASCADE |
| **File > Render picture…** | `RENDER, file [, width, height, view, frames]` | a nicer picture of the view: ray traced, with shadows on a floor, reflections and a look from each body's material, at any size, or a turntable (LANGUAGE.md section 40) |
| **File > Export drawing…** (Ctrl+Shift+E) | `DRAWING, file [, views] [, body] [, sizes]` | a 2D drawing as a PDF sheet (A4 to A0 with a frame and a title block from `PROPERTY` values, at a usual scale), DXF (for CAD programs and laser or CNC cutting) or SVG (for documents and the web): front, top, right and iso views, hidden edges dashed, with the overall sizes and the hole diameters (`sizes` NONE leaves them off), and hatched sections and enlarged details when asked (LANGUAGE.md, DRAWING) |
| **File > Save log…** | | the history as a plain `.cmd` script |
| **File > Run script…** | `RUN, file.cmd` | runs a script; its lines join the history |

The title bar shows the file name, with a `*` when there are unsaved
changes. Closing or opening another file asks first.

**Autosave.** Work is saved in the background a moment after each change.
If the app closes without saving (a crash or a power cut), the next start
shows a **Recover** button on the toolbar, or you can type `OPEN, AUTOSAVE`.

---

## 12. Running scripts without the window

```bash
modeler run part.cmd                  # run headless, print each step
modeler run part.cmd -D W=120 -q      # set a parameter; print only errors and *MSG
modeler part.cmd                      # open the window and run it
modeler bracket.m3d                   # open the window with a project
```

In the downloaded app, use `3Dmodeling-cli` (Windows: `3Dmodeling-cli.exe`,
macOS: `3Dmodeling.app/Contents/MacOS/3Dmodeling-cli`) for these.

A script that ends with `EXPORT` makes files in batch: run it with
different `-D` values to make a family of parts.

**Other AI tools can model with the app.** `modeler mcp` (in the
downloaded app: `3Dmodeling-cli mcp`) starts a Model Context Protocol
server. Any MCP client, such as a chat app or a coding agent, can then use
the same modelling tools as the built-in assistant, with no window. It can
build a part, check it, and save or export it. How to add it to a client:
[mcp.md](mcp.md).

---

## 13. Keyboard shortcuts

| Keys | Does |
|------|------|
| Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Shift+S | new, open, save, save as |
| Ctrl+I, Ctrl+E, Ctrl+Shift+E | import, export, export a drawing |
| Ctrl+, | preferences |
| Ctrl+Z, Ctrl+Shift+Z (or Ctrl+Y on Windows) | undo, redo (history edits too) |
| Ctrl+K | find a command by name or purpose |
| F2 | open the form for the command being typed |
| F | fit the view |
| F1 | getting started |
| Ctrl+F1 | the command reference, open at the command being typed |
| Up, Down in the command line | earlier commands |
| L, R, C, A, P, S, T, E, F (in a sketch) | line, rectangle, circle, arc, point, select, trim, extend, fillet |
| Esc | end a line chain in a sketch, close a dialog |

On macOS, Ctrl is Cmd.

---

## 14. When something goes wrong

* **A command fails.** The Output panel says why in plain words, and the
  model is unchanged. Fix the numbers, or double-click the red step in
  History to edit it.
* **Why did it fail?** Right-click a red (failed) or amber (warning) step
  in History and choose **Why did it fail?**, or use **Help > Why did it
  fail?** for the first failed step (or the last line you typed that
  failed). The app tries the usual fixes on a copy of your model, such as
  a fillet radius just under the largest that works, the fillet moved
  before the shell, or the right spelling of a name. It lists the ones
  that work, and one button runs a fix (Undo takes it back). It also opens
  the guide for that command. No assistant or internet is needed.
* **A pick lost its face.** After an earlier step changed, a click
  (`PICK`) may no longer find what it picked: the step turns red, or amber
  when it found the face again by its shape. Right-click it and choose
  **Pick again…**: the model goes back to just before that step, you click
  the right face, and **Use the picked faces for step n** puts it in and
  runs the rest. `REFS, PROBLEMS` lists every such pick.
* **A sketch will not extrude, or will not sit still.** `SCHECK` names
  the constraints that repeat others, curves drawn twice, the geometry that
  can still move, and why the profile does not close.
* **An imported part is not a solid, or booleans refuse it.** Type
  `CHECK, 1, FLAWS` (with the body's number) to see its gaps, loose or
  flipped faces, slivers and tiny edges, then `HEAL, 1`. HEAL says what it
  fixed and what is left; a gap wider than the tolerance needs a larger
  one (`HEAL, 1, 0.05`).
* **The app shows "Something went wrong".** Your model is still there.
  The details are in the log; **Help > Report a problem** opens an issue
  with your versions filled in, so please paste the details there.
* **The app closed suddenly.** Start it again and press **Recover**.
  **Help > Open the log folder** has `crash.log`; please attach it to a
  problem report.
* **The window opens but the 3D view stays black or empty.** Update your
  graphics driver. On Linux under Wayland the app uses XWayland, which needs
  to be installed. Run `modeler check` (or `3Dmodeling-cli check`) and
  include its output in a report.
* **macOS says the app is damaged.** See [Install](#1-install).

Logs and the autosave are in the app's data folder:
`%APPDATA%\3Dmodeling\3Dmodeling` on Windows,
`~/Library/Application Support/3Dmodeling/3Dmodeling` on macOS and
`~/.local/share/3Dmodeling/3Dmodeling` on Linux.

Report problems at <https://github.com/shashanksingh097/3Dmodeling/issues>.

## 15. The assistant (GitHub Copilot)

The **Assistant** panel (beside History, or **Help > Ask the assistant**,
Ctrl+Shift+A) is a chat with GitHub Copilot. It explains commands and
errors, reads your model, and writes scripts for you.

**Sign in with your own GitHub account.** Press **Sign in with GitHub**.
The panel shows a short code and opens <https://github.com/login/device>;
enter the code there and allow access. The app then asks to keep the
sign-in in a file in your own app-data folder (`%APPDATA%\3Dmodeling\copilot`
on Windows, `~/Library/Application Support/3Dmodeling/copilot` on macOS,
`~/.local/share/3Dmodeling/copilot` on Linux), which only your user
account can read. Answer **Yes**; you then sign in only once. To sign
out, delete that folder.

**The working folder.** The line under the account shows the folder
Copilot works in: where it puts files it exports and looks for files to
import. Choose it with **Folder**:

* **A temporary folder** (the default): `3Dmodeling-assistant` in your
  system's temporary folder.
* **The project's folder**: the folder of the saved project, so Copilot and
  your project use the same folder. Until the project is saved, the
  temporary folder is used.
* **Choose a folder…**: any folder you like.

The app remembers your choice. Your sign-in is never kept in the working
folder, so sharing a project folder never shares it.

**Any Copilot plan works, Copilot Free too.** Requests count against your
own plan; the panel shows how much of this month's allowance is left. If
your account has no Copilot plan, turn on Copilot Free (it costs nothing)
at <https://github.com/settings/copilot>. On Copilot Free, Copilot picks
the model itself and the monthly allowance is small.

**It never changes your model by itself.** Copilot reads your model with
exact text tools (sizes, holes, sections, wall thickness), tries its
scripts in a sandbox copy, and then shows a **Proposal** with a **Run**
button. Above the button the proposal shows Copilot's plan and **what it
will do**, worked out on a copy of your model: the bodies it adds, changes
(with their volumes before and after) and removes, the parameters it sets
and the history steps it adds, edits or re-runs. A **broad change** (one
that removes bodies, changes three or more, changes a volume by more than
half, re-runs ten or more steps, edits three or more steps or uses files)
says why it is broad, and **Run** works only after you tick the box that
names it. Running it puts the commands in the History like anything you
type, and **one Undo takes the whole proposal back**, however many lines
or step edits it has. Copilot's own coding tools (shell,
files, web) are switched off in this app; it reads files only as described
below, when you allow it.

**Answers appear as they are written.** While Copilot answers, **Send**
becomes **Stop**: it stops the answer, and what was written so far stays.

**The conversation is saved with the project.** Save the project and the
chat goes into the project file with it (the newest 200 messages). Open the
project later and the panel shows that conversation again; Copilot is given
it with your next question, so you can carry on where you left off.

**New chat** starts over: Copilot forgets the conversation (you stay
signed in), the next question starts fresh, and the project no longer
keeps the old conversation.

**Reading your files.** Copilot can list and read text files (scripts,
notes, logs) in the working folder, never elsewhere, and only when you
allow it. Each time it asks, choose **Allow once**, **Allow for this
chat** or **Deny**.

**The Debug tab** shows everything sent to Copilot and back, in order:
the full first message (with the list of every command), your questions,
each tool Copilot used with its input, its answer and how long it took,
permissions, errors and replies. If Copilot goes wrong, look there to see
where, and tell it. **Copy** and **Save…** give you the whole log, for
example to attach to a bug report.

**Your own key instead of GitHub.** Press **Model…** and choose where
answers come from: GitHub Copilot, OpenAI, Anthropic, Azure OpenAI, Ollama
(a model on your own computer; nothing leaves it) or any service that
speaks the OpenAI chat API. Enter the model name and the key; tick **Keep
the key on this computer** to keep it in a file only your user account can
read. Requests are then billed to that account, not to your Copilot plan.
From a shell the key can also come from the `MODELER_AI_KEY` environment
variable.

**Pointing at things.** The assistant may ask you to pick something: the
panel says what (a face, an edge, a body) and you click it in the 3D view
(**Cancel** in the panel says no). It can also mark what it is talking about in orange, and it
reads what you have picked, so "put two holes on this face" works.

**Skills and guides.** The assistant comes with short guides to whole
jobs (sheet metal, enclosures, gears and cams, assemblies that move,
frames, scan to CAD, sculpting, strength, fixing a failed step ...). It
sees their names and reads the one that fits your request, so it follows
the right order of commands and checks the result. You can read the same
guides in **Help > Guides**: each links to the commands it uses, **Open
example** runs its example in a new model and **Ask the assistant** starts
a question that names it. **Help > Assistant skills…** switches guides off
and adds folders with your own: a folder per guide holding a `SKILL.md`
(see any built-in one: `python -m modeler skills show sheet-metal`). A
project's own `skills` folder next to its file counts too. **Check skills**
finds mistakes in your files. **Short first message** sends only the
command names at the start of a chat (about 12 KB instead of 30 KB); the
assistant then looks up each command as it needs it, which saves part of
a small monthly allowance.

**Pictures.** For looks, freeform and sculpted shapes, a model that can see
pictures may look at a small picture of the 3D view. GitHub Copilot models
decide this themselves; for your own key, **Model…** has a tick box for
whether the model can see pictures.

The first time, the app downloads the Copilot runtime (about 190 MB) to
your cache folder, so you need internet then.

From a shell, `python -m modeler copilot check` (in the downloaded app:
`3Dmodeling-cli copilot check`) tests everything for your
account: sign-in, allowance, models, and one question that Copilot must
answer with the modeler's tools. It prints PASS or FAIL per step. Add
`--folder DIR` to use another working folder, and `--provider openai
--model NAME` (or `anthropic`, `azure`, `ollama`, `custom` with
`--base-url`) to test your own key. `copilot bench` runs 24 modelling
requests and checks each result exactly, to compare models; add `--modes
full,small` to compare the full and the short first message.

