# 3Dmodeling user guide

3Dmodeling is a 3D modeler for solid parts. Everything you do with the mouse
is turned into a short line of text, a **command**, and kept in the
**History**. So every model is also a script: you can edit any step later,
change a number and watch the part rebuild, or write the whole part as text.

This guide covers version 0.2. The full command language is in
[LANGUAGE.md](LANGUAGE.md), and inside the app under **Help > Command reference**.

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

Get the zip for your system from the
[Releases page](https://github.com/shashanksingh097/3Dmodeling/releases):

| System | Download | Start it |
|--------|----------|----------|
| Windows 10 or 11 (64-bit) | `3Dmodeling-0.2.0-windows-x64.zip` | unzip, open the folder, run `3Dmodeling.exe` |
| macOS 12 or later on Apple silicon (M1 and newer) | `3Dmodeling-0.2.0-macos-arm64.zip` | unzip, move `3Dmodeling.app` to Applications, open it |
| Linux (64-bit, X11 or XWayland) | `3Dmodeling-0.2.0-linux-x64.tar.gz` | `tar xzf` it, run `3Dmodeling/3Dmodeling` |

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
| **3D view** (middle) | the model. Left drag orbits, middle or right drag pans, the wheel zooms, **F** fits everything in view |
| **Command line** (below the view) | type any command and press Enter. It suggests command names as you type and shows the arguments of the one you are typing |
| **Form** button, **F2** | opens a fill-in form for the command you are typing, so you never need to remember argument order |
| **Output** (bottom) | what each command did, and errors in plain words |
| **History** (right) | every step that built the model, in order. Grey steps are undone; red steps failed; amber steps ran but want a look |
| **Parameters** (right, tab) | named numbers such as `W = 80`. Change one and the model rebuilds |
| **Layers** (right, tab) | show, hide, lock and colour groups of bodies |
| **Main toolbar** | undo and redo, quick shapes, what a click picks (body, face, edge, vertex), views, files |
| **Features toolbar** | sketch, extrude, revolve, the sweep editor, datum and work planes, hole, shell, draft, push/pull, delete faces, measuring, section view |
| **Menus** | **File**; **Commands**, a form for every command, by group; **Help** |

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
| **Roll back to here** | undo back to this step (Redo brings the rest back) |
| **Make a part from steps …** | with several steps selected, turn them into a reusable part |

When a step is edited, picks made after it still point at the same faces
and edges where possible. If the app had to guess, the step turns amber and
says so. A step that fails turns red with the reason, and the steps after it
wait until it is fixed.

Long rebuilds show a progress bar with **Cancel**, which puts everything
back as it was.

---

## 6. Sketches

A sketch is a flat drawing held by constraints and sizes, which you then
push (**Extrude**) or turn (**Revolve**) into a solid.

1. Pick a flat face (or nothing, to choose a plane), then press **Sketch**.
   The view turns to face the sketch and the **Sketch** toolbar appears.
2. Draw with Line (L), Rectangle (R), Circle (C), Arc (A) and Point (P).
   Clicks snap to points, middles, curves and the axes.
3. Select geometry and press a constraint button (horizontal, parallel,
   tangent, ...) or **Size…** to give a length, radius or angle. The sketch
   turns green when it is fully defined.
4. Trim (T), Extend (E) and Fillet (F) tidy corners; **Offset…**,
   **Mirror…**, **Pattern…** and **Project…** are on the toolbar too.
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

---

## 9. Layers, colours and materials

The **Layers** panel shows, hides, locks and colours groups of bodies.
`MATERIAL, b, STEEL` gives a body a material, so `MASSPROP` reports its mass.
`ISOLATE, b` shows one body alone; `SHOW` brings everything back.
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
| **Section**, `SECTION` | cuts the view open on a plane |
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

---

## 13. Keyboard shortcuts

| Keys | Does |
|------|------|
| Ctrl+N, Ctrl+O, Ctrl+S, Ctrl+Shift+S | new, open, save, save as |
| Ctrl+I, Ctrl+E | import, export |
| Ctrl+Z, Ctrl+Shift+Z (or Ctrl+Y on Windows) | undo, redo |
| Ctrl+K | find a command by name or purpose |
| F2 | open the form for the command being typed |
| F | fit the view |
| F1 | getting started |
| Up, Down in the command line | earlier commands |
| L, R, C, A, P, S, T, E, F (in a sketch) | line, rectangle, circle, arc, point, select, trim, extend, fillet |
| Esc | end a line chain in a sketch, close a dialog |

On macOS, Ctrl is Cmd.

---

## 14. When something goes wrong

* **A command fails.** The Output panel says why in plain words, and the
  model is unchanged. Fix the numbers, or double-click the red step in
  History to edit it.
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
button. Running it puts the commands in the History like anything you
type, and **Undo** takes them back. Copilot's own coding tools (shell,
files, web) are switched off in this app.

The first time, the app downloads the Copilot runtime (about 190 MB) to
your cache folder, so you need internet then.

From a shell, `python -m modeler copilot check` (in the downloaded app:
`3Dmodeling-cli copilot check`) tests everything for your
account: sign-in, allowance, models, and one question that Copilot must
answer with the modeler's tools. It prints PASS or FAIL per step. Add
`--folder DIR` to use another working folder.

