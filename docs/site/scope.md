# Scope and known limitations

What 3Dmodeling is for, what it leaves to other programs on purpose, and what does not
work well yet. This page is updated with each release (this is for 0.7.0).

## What it is for

A desktop modeller in which every action is a text command, so every model is a script
that can be read, edited, re-run and checked. It covers:

- **Parts**: solids from primitives, sketches (with a constraint solver), extrusions,
  revolutions, sweeps and lofts, holes, fillets, chamfers, shells, drafts, patterns, threads,
  springs, gears, fasteners, text, ribs, lips, wraps, sheet metal with flat patterns, frames
  from profiles, plastic part features and moulds.
- **Freeform**: NURBS curves and surfaces, guide-curve lofts, networks, continuity checks
  (G0/G1/G2, curvature combs, zebra), sculpting on meshes up to about a million triangles,
  implicit shapes and lattices.
- **Assemblies**: parts in their own files linked into assemblies, mates, motion, contact
  and clash checks, gravity checks, exploded views, configurations and a bill of materials.
- **Documentation and exchange**: drawing sheets (PDF, SVG, DXF) that follow the model,
  STEP (with sizes and GD&T), IGES, BREP, STL, OBJ, 3MF, glTF, VRML, AMF and one-page web
  viewers out; those, FreeCAD and OpenSCAD files, SVG, circuit boards, point clouds and more
  mesh formats in.
- **Checks**: `DESIGNCHECK`, `ASSERT`, `COMPARE` of revisions, tolerance stack-ups, print and
  milling checks, and an assistant that reads the model with exact text tools.

## What stays out, on purpose

These are not missing features; they belong in other programs, and the app writes the files
those programs read.

| Out of scope | Why, and what to use instead |
|---|---|
| Meshing for analysis: hexahedral or quad meshes, block decomposition, solver set-up | A separate meshing app is planned. Export STEP for the mesher. Small mesh tools for modelling, sculpting, checking and file exchange stay here. |
| Full finite element analysis (non-linear, contact, dynamics, thermal, fatigue) | `STRESS` is a quick linear first check: the largest stress, deflection and safety factor for one part and one load. Use a dedicated analysis program for anything you rely on. |
| Production CAM | `MILL` writes simple 2.5D paths (pocket, outline, facing) as G-code, for a look at what is possible. Use your CAM program and post-processor for real machining. |
| Photorealistic rendering studio | `RENDER` makes a good ray traced picture or turntable from the view. Export glTF for a rendering program. |
| Native files of other CAD programs (SolidWorks, Creo, CATIA, NX, Inventor, Parasolid) | The geometry kernel reads only open formats (FreeCAD `.FCStd` files are read, as shapes without their history). Ask for STEP (exact) from the other program. Imported STEP is a body without the other program's feature history. |
| Teamwork: shared cloud projects, check-in and check-out, PDM | Projects are files and plain text histories; keep them in a folder that is backed up or under version control (`COMPARE, PROJECT` compares two saved revisions). |
| 2D drafting from scratch | Drawings are made from the model. They are not a 2D drawing editor. |

## Known limitations

These are things the app does today, with the limits found by its tests and demonstrations.

**Model building**

- References to faces and edges are repaired after an upstream edit only when the match is
  certain; otherwise the step is marked broken with the reason (`REFS`) and asks for a new
  pick. Prefer `SEL` criteria over face numbers in scripts that will be edited.
- Very large counts are refused before they start (for example more than 1000 gear teeth or
  2000 helix turns), because they would take hours.
- Fillets and shells that the geometry kernel cannot make fail with a plain message and
  leave the model as it was. Smaller radii, or rounding fewer edges at a time, usually work.
- Bodies imported from meshes (STL, OBJ ...) are faceted: booleans, sections, measuring and
  export work; fillets, shells and offsets do not. `FITSURF` and `RECONSTRUCT` turn scans
  into exact surfaces where the shapes are simple enough.

**Speed**

- The geometry kernel works on one processor core. Long rebuilds run in a helper process
  with a progress bar and Cancel, so the window stays usable, but they are not faster.
  A history of about 250 steps rebuilds in about 5 seconds; see the benchmark
  (`python -m modeler perf`).
- Sculpting is smooth up to about a million triangles.

**Desktop**

- Tested automatically on Windows, macOS and Linux (`python -m modeler desktop-check`),
  including 150 % and 200 % screen scaling on Linux. Checks by hand on real Windows and
  macOS machines (several screens with different scaling, sleep and wake) are still being
  done; please report anything on the [Desktop check](desktop-check.md) list that fails.
- 3D mouse support (`SPACEMOUSE`) and FreeCAD import (`IMPORT, FCSTD`) are tested against
  simulated devices and files built like the real ones; they have not yet been tried with a
  real SpaceMouse or with files saved by FreeCAD itself.
- The window is in English, German and Spanish. Commands, their output and the assistant stay
  in English.
- The 3D view needs OpenGL. Remote desktops without a graphics driver may show a black view.

**The assistant**

- It needs the GitHub Copilot SDK and a GitHub sign-in, or your own key for another model
  provider. It never changes the model by itself: it proposes, shows what the change will
  do (tried on a copy), and you press Run. Broad changes need an extra tick.
- Its answers are only as good as the model behind it. It checks its scripts on a copy
  before proposing them, but read the proposal before running it.

**Files**

- Saved projects from every earlier release open; projects saved by this release may not
  open in older releases.
- Imported files are copied into the saved project. Linked parts and other outside files
  are not: if one moves, `FILES` lists them and `RELINK` points to the new place.

## Reporting a problem

**Help > Report a problem** in the app collects the version, the last steps and the
crash log (if any) for a GitHub issue. Saying which command, and attaching the project or
a short script that shows it, makes it much quicker to fix.
