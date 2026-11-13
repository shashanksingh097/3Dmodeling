# Changelog

All notable changes to 3Dmodeling. Versions follow [semantic versioning](https://semver.org).

## [Unreleased]

### Assistant
- An **Assistant** panel with GitHub Copilot (Help > Ask the assistant, Ctrl+Shift+A). Sign in with your own GitHub account using a one-time code; any Copilot plan works, Copilot Free included, and requests count against your own plan. Copilot reads the model with the modeler's text tools, tries scripts in a sandbox, and shows a proposal with a Run button; it never changes the model by itself, and its own coding tools are switched off. Needs `pip install "3Dmodeling[ai]"` (Python 3.11+); the Copilot runtime downloads on first use (about 190 MB).
- The assistant can change existing steps (a size, a step that fails): it tries the edits on a copy first, and the panel shows each step's old and new text before you press Run. It can also explain what works on an imported body: `DESCRIBE` and its tools now say whether a body is exact (STEP, IGES, BREP) or faceted (a mesh) and which file it came from.
- A working folder for the assistant (**Folder** in the panel): a temporary folder by default, the project's folder, or one you choose; Copilot keeps its own files in `.copilot` there. This also fixes "Copilot is not available: CopilotClient(mode='empty') requires base_directory" when signing in.
- `python -m modeler copilot status|login|quota|models|ask|check`: the assistant from a shell; `check` tests sign-in, allowance and a question that must use the modeler's tools.

### Examples
- An examples gallery, [docs/EXAMPLES.md](docs/EXAMPLES.md): every example script with a picture of what it makes, its description, the numbers you should get (bodies, volume) and the whole script. Help > Examples with pictures opens it.
- `python -m modeler render part.cmd part.png` saves a picture of what a script makes, as the app draws it; a shots file takes several pictures with commands per picture. `python -m modeler gallery` remakes the gallery, and CI keeps scripts, pictures and page in step.

### Files
- Export to IGES, OBJ, 3MF and glTF (`.glb` or `.gltf`) as well as STEP, BREP and STL. OBJ, 3MF and glTF keep one object per body with its name and colour; 3MF records the units; glTF is in metres with Y up.
- Import OBJ, 3MF, glTF, PLY, OFF and VTK (`.vtk`, `.vtu`) files, and simulation meshes such as Gmsh, Abaqus and Nastran with `IMPORT, MESH, file`. Each connected piece becomes a faceted body, a solid when it is closed (turned the right way out if needed); volume meshes keep their outer skin. Up to 100,000 triangles.
- Mesh import is much faster: STL files are no longer sewn triangle by triangle (a 50,000-triangle STL took 17 s, now under 4 s), and an STL with several pieces gives a body for each piece instead of only the first.

### Modeling
- NURBS freeform, part 1: curves from control points with weights (`NURBS`), editing control points, weights, knots and degree (`MOVEPT`, `WEIGHT`, `KNOT`, `DEGREE`), refitting any curve or surface with a chosen number of control points (`REBUILD`), surfaces from rows of control points (`NSURF`), through a network of curves (`NETWORK`) or filling a hole smoothly (`FILL`, G0/G1/G2), and sewing surfaces into a solid (`SEW`).
- Drag control points in the 3D view: pick a curve or surface and press Control points; each drag is a `MOVEPT` step in the history.
- NURBS freeform, part 2: smooth blends between two surfaces (`BLEND`, G1 or G2), extending and trimming surfaces (`EXTEND`, `TRIM`), and moving or replacing faces of a solid (`MOVEFACE`, `REPLACEFACE`).
- NURBS freeform, part 3: lofts steered by guide curves (`LOFT, ..., GUIDE, g1, g2`), sweeps that keep their angle to a surface (`SWEEP` mode `NORMAL`), laying a curve onto a surface (`PROJECT`), and surface analysis in words and colours: zebra stripes with every join judged G2, G1 or creased, curvature and Gaussian curvature maps, and draft for moulding (`ANALYZE`, and a Zebra button). `CURVEPT()` and `CURVETAN()` give a curve's point and direction.
- Deformers: bend (`BEND`), twist (`TWIST`), taper (`TAPER`) and stretch (`STRETCH`, keeping the volume or not) whole bodies, with an optional law for how the change runs along the body, and lay a body such as a text along a curve (`FLOW`, optionally fitted to the curve's length). The body and its faces keep their IDs; solids are refitted as NURBS within 1/10000 of their size, mesh bodies are moved point by point.
- `SWEEPVOL`: the volume a cutter sweeps along a path, as a body to `SUBTRACT`; exact for a ball and for an end mill moving square to its axis.
- `BLEND` between two closed loops (a wall's top edge and a lid's rim) makes a blend all the way round whose seam closes exactly, so the pieces sew into a solid.
- A computer mouse example (`scripts/mouse.cmd`): a side wall and a humped top joined by a G2 blend, sewn, shelled to 2 mm, with a button split, a scroll wheel and a name flowed along a curve on the top.
- A detailed car body example (`scripts/car_body.cmd`): NURBS master surfaces cut into panels with shut lines, glass, lamps, grille, wheels, mirrors and trim, all in the command language (see `docs/example-car.md`).

### Viewing
- Bodies of the `GLASS` material are drawn see-through.
- Face edges are drawn in a darker shade of the body's colour, so panel lines and small gaps read at any zoom.

### Fixes
- `ANALYZE` no longer calls a join G1 between two nearly flat faces whose tiny curvatures differ (a bend wider than 100 times the body counts as flat).
- `python -m modeler run` marks the line that failed inside a block or macro with `ERROR:`, not the block's first line.

## [0.1.0] - 2026-11-13

The first release: a desktop 3D modeler for solid parts in which every
click is a command, so every model is also an editable script.

**Downloads** for Windows (x64), macOS (Apple silicon) and Linux (x64) are
attached below and need no Python. They are not code-signed yet; the
[user guide](https://github.com/shashanksingh097/3Dmodeling/blob/main/docs/USER-GUIDE.md#1-install)
says how to open them the first time.

### Modeling
- Solids (block, cylinder, tube, cone, sphere, torus, wedge), booleans that keep their inputs on request, move, copy, mirror, and arrays in a row, around an axis or along a path.
- Sketches with constraints and sizes, a solver that names what a refused constraint fights, trim, extend, fillet, offset, mirror, pattern and projected edges; extrude and revolve as new bodies, bosses or pockets.
- Features: holes (plain, counterbore, countersink, drill point, threaded), fillets, chamfers, shell, draft, offset, split, push/pull and delete faces, feature patterns.
- Shapes from curves: loft, sweep with twist and scale laws (with a graphical sweep editor), morph, pipe, one- and two-rail sweeps, spine lofts, ISO threads, springs, text, shapes from equations.
- Datum planes, axes and points, and work planes.
- Parts with parameters, placed many times and following their definition, and a part library.
- Layers, colours and materials; volume, mass and inertia, distances, angles, clash checks, section views.

### Working with history
- Every step is kept in the History panel and can be edited, inserted, suppressed, deleted or rolled back to; the model rebuilds from there, with progress and Cancel for long rebuilds.
- Parameters and expressions in any number, loops, conditions and your own commands (macros).
- Picks remember what they pointed at and are repaired after edits when the match is certain, with a warning.
- Every boolean, blend and feature is checked; a broken result is refused with a reason and the model is unchanged. `CHECK`, `HEAL` and `CLEAN` repair imported parts.

### App
- File menu with recent files, example models, save as, import (STEP, IGES, BREP, STL) and export (STEP, STL, BREP); `.m3d` projects that carry the whole history and copies of imported files.
- Asks before unsaved work is closed or replaced; the title bar shows the file and an unsaved marker.
- Autosave, and Recover after a crash.
- A fill-in form for every command, a command line with completion and argument hints, and Ctrl+K to find a command by purpose.
- Help menu: getting started, a searchable command reference, report a problem, about.
- Errors are logged and shown instead of closing the app; kernel crashes leave a crash log.
- `modeler run script.cmd -D NAME=value` runs scripts without the window.

### For AI assistants (groundwork)
- Text tools that describe bodies and their holes, probe with rays and points, cut profiles, measure wall thickness, check expectations (`ASSERT`), compare history, and try changes in a sandbox. The chat panel that uses them comes in a later release.

### Known limits
- Builds are tested headless on Windows, macOS and Linux. The 3D view is tested under a virtual display; real Windows and macOS desktops are still being tried.
- No undo for history edits themselves yet; a sketch fillet between a line and an arc, and trimming to the sketch axes, are not in yet.
- Rebuilding re-runs every step after an edit, even ones that did not change.
