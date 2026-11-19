# Changelog

All notable changes to 3Dmodeling. Versions follow [semantic versioning](https://semver.org).

## [Unreleased]

### Added
- `REFS`: every pick the history holds (PICK, and SEL by IDs) and whether it still points at
  what was picked: ok, repaired or broken, with the reason.
- **Pick again** on a pick step in History (and `HIST, REPICK, n, "FACE, 12"`): pick again with
  the model as it was just before that step; clicks then select without adding steps.
- `SCHECK`: what is wrong with a sketch, or still loose, named by geometry and constraint.
- `CHECK, b, FLAWS [, tolerance]`: gaps, holes, loose and flipped faces, slivers, tiny edges and
  duplicate faces of an imported body, by face and edge ID, against a tolerance (also as JSON).
- STEP part names and colours are kept by `IMPORT` (assemblies placed part by part) and written
  by `EXPORT`.
- `CHECK, b, FLAWS` on a mesh body: cracks, three-way edges, inside-out triangles, folds and slivers.
- `DEVIATION, scan, body [, tolerance]`: how far a scan is from its model. Share within tolerance,
  largest out and in, mean and RMS, the same per face, outliers, holes in the scan and faces it hardly
  covers; the scan is coloured by tolerance band. `RECONSTRUCT` reports the same numbers for the solid
  it made.
- `COMPARE, STEP, n` and `COMPARE, PROJECT, "old.m3d"`: two revisions face by face (added, removed,
  moved, changed with old and new sizes), volume before and after, how far the surface moved, and
  the changed body coloured by distance.
- `CONTINUITY`: every join between faces judged open, sharp, kink (nearly tangent), G1 or G2, with the
  largest gap and angle. `COMB` draws curvature combs on edges. `INSPECT` lists kinks, gaps, open
  edges, slivers, tiny faces, the tightest bend and the thinnest wall.
- `TAKE, FACE/EDGE/PLANE/AXIS, part, n, name [, LINK/COPY]`: geometry from another part (by name
  or a placed copy), linked so it follows the part, or copied; a face that is gone is a broken link.
  `DEPENDS` lists linked files, parts, copies and taken geometry, with broken links and loops.

### Changed
- `SEL` by IDs remembers what it picked, like `PICK`, and finds it again when IDs move.
- Faces and edges that get a new ID remember what they were made from (a fillet face the edge it
  rounds, the smaller piece of a split face that face); a pick uses it to tell look-alikes apart
  and to find a face whose size changed upstream.
- Sketch trims treat a tangent touch within a millionth of the sketch's size as touching.
- A closed-chain `SOFFSET` too big for a linked offset cuts its loops away (a slot closes, an
  outline splits) instead of making an outline that crosses itself.
- A sketch turn (`STRANSFORM, ROTATE`) by any angle keeps horizontal and vertical as an angle plus
  parallel and square constraints, so a turned rectangle stays a rectangle.
- Big sketches rebuild about 4 times faster (500 curves: from 22 s to 5 s per rebuild).
- `HEAL` repairs in turn (duplicates, sewing gaps and loose faces into a solid, flipped faces,
  tiny edges, invalid faces), keeps each repair that helps, and lists what it fixed and what is
  left. `IMPORT` warns when an exact file gives a body that is not a clean solid.
- Sculpting stays clean: with a detail size the triangles grow back gently away from the stroke,
  sharp edges and frozen points stay put while the triangles are evened out and joined, and every
  stroke is checked where it went (folds it made are smoothed flat, anything else is a warning).
  A test runs 2,000 strokes on a growing mesh and finds it clean at the end.

## [0.5.0] - 2026-11-19

### Added

- **User guide website** (https://shashanksingh097.github.io/3Dmodeling/):
  a quick start, the app guide and the command language split into pages,
  the examples gallery, and a command reference with every command's
  arguments and one small example for each of the 244 commands, most with a
  picture of what it makes. Every example runs in the tests, so none can go
  stale. `python -m modeler docs --serve` shows it locally; it is
  published to GitHub Pages from main. **Help > Every command with an
  example (web)** opens it.
- **Why did it fail?** Right-click a failed step in History (or use
  **Help > Why did it fail?**). The app tries the usual fixes on a copy of
  the model: a size just under the largest that works, a fillet moved
  before the shell, HEAL before a boolean, the right spelling of a name.
  It lists the ones that work, and one button runs a fix. The assistant
  has the same as its `diagnose` tool.
- **The assistant reads more of the model as text**:
  - `describe_body` now names fillets, rounds, chamfers, bosses, pockets
    and slots with their sizes.
  - `around` lists what touches a face or edge.
  - `outline` gives a body seen from a view as a few hundred numbers.
  - For models that take pictures, `render_detail` gives a close-up and
    `render_compare` shows a change in orange over the model.
- **Short first message**: a setting under **Help > Assistant skills…**
  sends only the command names at the start of a chat, about 12 KB
  instead of 30 KB.
- **A bigger assistant benchmark**: 24 tasks, at least one per skill area.
  `copilot bench --modes full,small,noskills` compares the full and the
  short first message, with and without skills.
- **Assistant skills and Guides**: 17 step-by-step guides to whole jobs
  (sheet metal, enclosures, fasteners, gears and cams, assemblies and
  motion, frames, surfaces, scan to CAD, sculpting, strength,
  manufacturing, drawings, fixing a failed step ...), each with an example
  script that is checked. The assistant loads the one that fits a request;
  people read them in **Help > Guides**; the MCP server serves them as
  prompts and resources; `python -m modeler skills` lists, checks and
  exports them. **Help > Assistant skills…** switches them off and adds
  folders with your own.
- **Better assistant tools**: `search_docs` (the manual, guides and
  examples), `parameters` (who sets and who reads each one, with a ready
  edit line) and `sketch_state`.
- **Checks as data and in ASSERT**: `STRESS`, `GRAVITY`, `PRINTCHECK`,
  `BOM`, `MASSPROP` and other checks hand their numbers to the assistant as
  data, and new queries `MASS`, `SAFETY`, `MAXSTRESS`, `DEFLECT`,
  `OVERHANGS`, `FLOATING`, `TIPANGLE` and `QTY` keep design rules in the
  script (`ASSERT, SAFETY(bracket, "wall", "tip", 0, 0, -400), GE, 2`).
- **Gears**: `GEAR` makes involute spur, helical and internal gears and
  racks from a module and a tooth count, with a bore, and says the centre
  distance to a mating gear.
- **Standard fasteners**: `FASTENER` makes ISO 4762 cap screws, ISO 4017
  hex screws, ISO 4032 nuts and ISO 7089 washers from M3 to M24, plain or
  with real threads, named and made of steel.
- **Scaling and uneven blends**: `SCALE` (one factor, or one per axis),
  fillets whose radius changes along the edge (`FILLET, r, r2`) and
  chamfers with two distances (`CHAMFER, d, d2`).
- **Plastic part features**: screw bosses with ribs (`BOSS`), snap hooks
  with their snap-in strain (`SNAP`) and vents through a wall (`VENT`).
- **Mould tools**: `PARTING` shows the faces for each mould half, the ones
  that need draft, undercuts and the parting line; `MOLD` makes the two
  halves with a shrink allowance.
- **Fits and notes**: `FITS` gives ISO 286 limits and fits. `NOTE` pins
  text, sizes, hole diameters and fits to the model: shown in the view and
  put on drawing sheets.
- **Welds**: `WELD` adds weld beads where parts meet (`WELD, ALL` on a
  frame), and `CUTLIST` adds the weld lengths.
- **Section view**: `SECTION` takes an offset and up to three planes, caps
  the cuts with hatching and prints each cut's area and centre; the
  Section window moves the plane with a slider.
- **Tolerances**: `STACKUP` gives a stack-up's worst case and statistical
  gap, with each size's share; `NOTE, DATUM` and `NOTE, GDT` put datums and
  geometric tolerance frames on faces, drawn as frames on drawing sheets.
  Notes on drawings now move apart instead of covering each other.
- **Pipes and cables**: `ROUTE` bends a pipe or cable bundle along a path,
  joins routes as tees, and `ROUTES` lists lengths and bends.
- **Cams and more gears**: `CAM` makes a disc or barrel cam and its roller
  from a lift law, checking the pressure angle; `CAMLIFT` gives the lift
  to move the follower by. `GEAR` adds bevel gears, worms, worm wheels and
  helical racks. `TRACE` keeps the path of a point through a motion as a
  curve.
- **Sketches from drawings and pictures**: `SDXF` reads a DXF drawing into
  a sketch, `STRACE` traces the outlines of a picture into one, and
  `IMAGE` shows a picture on a plane to draw over.
- **Topology check**: `TOPOPT` keeps the share of a part that carries a
  load best, as a mesh body to model a part after.

### Fixed

- The command forms for `GEAR`, `FASTENER`, `STRESS`, `LATTICE`, `MATE` and
  a few others offered the wrong list of choices for their kind or mode.

## [0.4.0] - 2026-11-19

### Added

- **Pictures**: `RENDER` saves a ray-traced picture at any size, with
  shadows on a floor, reflections and a look from each body's material. It
  can also make a turntable (numbered pictures, plus a GIF when Pillow is
  installed). This is also **File > Render picture…**.
- **Drawing sheets**: `DRAWING` writes PDF too. It puts the views on A4 to
  A0 paper at a usual scale, with a frame and a title block filled from the
  new `PROPERTY` command. It also adds hatched section views (`"X 20"`) and
  enlarged detail views (`"FRONT 30 0 12 6 3"`). **File > Export drawing**
  now offers PDF first.
- **Will it stand up?** `GRAVITY` checks a whole assembly: parts that
  float (not connected to the ground), tip off what they rest on, or hang
  only at their sides; small gaps and overlaps; and how far the whole can
  lean on the floor before it tips. Problem parts are marked in the view.
- **Ready to print and mill**: `PRINTCHECK` shows what sits on the bed and
  what overhangs and needs support (red), and reports thin walls and closed
  hollows. `BEST` picks the build direction needing least support. `MILL`
  makes 2.5D milling paths (pockets around islands, outlines, facing),
  shows them in the view and writes G-code. Both are on the Inspect tab's
  new Make group.
- **A first strength check**: `STRESS` holds some faces, pushes on others
  (a force or a pressure) and colours the solid by stress, with the largest
  stress, deflection and safety factor from its material. A quick linear
  check while designing, solved in about a second. Adds scipy as a
  dependency.
- **Frames and weldments**: `MEMBER` lays square, rectangular or round
  tube, flat bar, angle, channel or I-beam along a polyline or sketch, with
  mitred or butted (coped for round tube) corners. `CUTLIST` lists what to
  cut, with lengths, end angles and quantities, also as CSV.
- **Exploded views**: `XSTEP` records how an assembly comes apart (named
  views, saved with the project) and `XSHOW` shows it, with trail lines from
  each part back to its place. The parts go back before the next change.
- **Sheet metal bends along a sketched line**: `SBEND` (Bend… on the
  Features tab) turns one side of a plate about a line, with its holes, and
  `UNFOLD` lays it flat again.
- **Holes in flange walls show in the flat pattern**: `UNFOLD` lays each
  wall flat as it is, so holes cut after bending are in the blank and DXF.
- **WRAP onto cones**: a sketch is laid on the cone's development, so sizes
  and angles are kept.
- **Scan to CAD for machined parts**: `SEGMENT` splits a mesh at its sharp
  edges and says what each region is (a plane, a cylinder or bore, a sphere,
  or freeform). `RECONSTRUCT` fits those exactly and joins them into one
  solid. A scanned block with a bore, a boss and a dome comes back within
  0.01% of its volume.
- **Help browser**: Help > Command reference (Ctrl+F1) lists every command
  under the command menu's headings, searchable by name, help or argument.
  Each command's page has its arguments with their defaults, lines from the
  example scripts that use it, links to the commands beside it, and buttons
  to open its form or put it in the command line. With a command typed,
  Ctrl+F1 opens at it.
- **Sizes on drawings**: `DRAWING` writes the overall width, depth and height
  (exact, each once) and the diameter of every whole circle seen face-on,
  equal ones counted (`6x Ø8`). New argument `sizes`: ALL, OVERALL, HOLES or
  NONE. DXF puts them on layer DIMS.
- **Installers**: the release workflow also makes a `.msi` for Windows
  (Start menu entry, removable in Settings > Apps, a newer version replaces an
  older one) and a `.dmg` for macOS, and tries both on the build machine.
- **Assistant answers stream in** as they are written. While it answers,
  **Stop** ends the answer and keeps what was written.
- **SOFFSET of splines**, alone, closed or in chains with lines and arcs.
  A closed chain that crosses itself can now be offset too.
- **Sculpting with a detail size joins squeezed edges** after each stroke,
  so the triangles stay even stroke after stroke.
- **The assistant conversation is saved with the project.** Reopening the
  project shows it, and the assistant is given it with the next question.
  **New chat** clears it.
- **Scan to CAD with `FITSURF`**: fits a smooth NURBS surface to a mesh
  body. A closed rounded mesh becomes a solid; an open scan or a region
  painted with `MASK` becomes one trimmed face. It reports how far the
  surface is from the mesh. **Fit surface** on the Sculpt tab opens it.
- **Configurations**: `CONFIG, big, "W = 80, H = 20"` names a set of
  parameter values; `USECONFIG, big` (or the new list above the
  parameters) rebuilds the model with them. Saved with the project; the
  batch runner takes `-C big`.
- **`BOM`**: the parts list, with instances of the same part counted
  together, material and mass; `BOM, parts.csv` writes it as CSV.
- **Sheet metal**: `SHEET` makes a plate of one thickness from a sketch,
  `FLANGE` bends a wall up or down along an edge (angle, length, bend
  radius) and `UNFOLD` lays the part flat, as a body and as a DXF to cut
  with bend lines and their angles. The flat length of each bend follows
  the sheet's K-factor. `SHEETINFO` lists the flanges. On the Features tab.
- **Ribs, lips and wrapped sketches**: `RIB` makes a thin wall from an open
  sketch line down to the part's faces (its ends carry on to the walls).
  `LIP` raises a band along the inside edge of an enclosure's rim, and
  `LIP, ..., GROOVE` cuts the matching step with a clearance. `WRAP` lays
  a sketch round a cylinder, raised or cut, keeping its sizes. Rib, Lip and
  Wrap buttons are on the Features tab.
- **Assemblies that move**: Inspect > **Motion…** drives a parameter (a
  `MATE` angle, a `ROTATE`, a `MOVE`) with a slider and Play, without
  changing the history (`DRIVE, A, 75`). **Check range** (`MOTION, A, 0,
  180, 18`) finds where parts run into each other and the exact value
  where they first meet. **Save pictures…** and `python -m modeler render
  part.cmd --motion A 0 180 18 frames` save a picture per step.
- **The modelling tools for any MCP client**: `python -m modeler mcp`
  serves the assistant's tools (run, describe, probe, check, the working
  copy, undo) plus `apply`, `save_project` and `export`, over the Model
  Context Protocol on stdin/stdout, headless. See docs/mcp.md.

- **Sculpting a million triangles is smooth.** The brush circle follows
  the mouse 50 times faster on a 1M-triangle mesh, drag steps are three
  times faster and a finished stroke twice as fast.
- **Long rebuilds no longer freeze the window.** A history edit whose steps
  took a second or more runs in a helper process; the view can be turned
  while it works, and Cancel stops it at once, even in the middle of a step.

### Fixed

- A body named like a parameter could not be reached in commands (the name
  gave the parameter's value). Such names are now refused with a note.

## [0.3.0] - 2026-11-18

The third release: sculpting, a model tree with a right-click menu, part
documents with linked parts and mates, mesh bodies that stay fast at a
million triangles, implicit shapes and lattices, knife cuts, 2D drawings,
light and dark themes, many more sketch tools, and an assistant that can
use your own API key, look at the 3D view and show you what it means.

**Downloads** for Windows (x64), macOS (Apple silicon) and Linux (x64) are
attached below and need no Python; the assistant is included. Builds are
code-signed only when signing certificates are set up (docs/RELEASING.md);
the
[user guide](https://github.com/shashanksingh097/3Dmodeling/blob/main/docs/USER-GUIDE.md#1-install)
says how to open an unsigned build the first time. Projects and scripts
from 0.2.0 open unchanged. `SHA256SUMS.txt` lists the checksum of each
download.

### Sculpting

- The **Sculpt** tab: drag over a mesh body to shape it with a brush:
  Draw, Clay, Inflate, Smooth, Flatten, Pinch, Crease or Grab. Ctrl works
  the other way, Shift smooths, `[` and `]` change the size, Mirror X/Y/Z
  sculpts both sides. **Make sculptable** turns a solid into a fine mesh.
- The **Mask** brush (and `MASK`) freezes areas so the brushes leave them
  alone; Clear mask and Invert mask.
- Every stroke is a `SCULPT` step in History; its points are kept as
  `STROKE` and saved with the project, so sculpting undoes, saves and
  replays like any other step. Example: `scripts/sculpt_head.cmd`.
- A stroke on a mesh of 820,000 triangles takes about half a second.
- The surface moves while you drag, a circle shows the brush's size on the
  surface under the mouse, and frozen areas are drawn purple.
- **Detail** on the Sculpt tab (`SCULPT ..., detail`): the triangles near
  each stroke are split first, so creases and fine ridges come out sharp.
  `REMESH` keeps the sculpt mask.

### The assistant: your own key, pointing at things, pictures

- **Model…** in the Assistant panel: answers from GitHub Copilot or from
  your own key: OpenAI, Anthropic, Azure OpenAI, a local Ollama model (nothing
  leaves your computer) or any OpenAI-compatible service. Pick the model;
  the key can be kept in a file only your user account can read.
- The assistant can ask you to click a face, edge or body in the 3D view
  (the panel says what to pick), mark what it means in orange, and read what
  you have picked.
- When words are not enough (looks, freeform and sculpted shapes), a model
  that can see pictures may look at the 3D view. A setting says whether your
  own-key model can.
- `python -m modeler copilot bench`: ten modelling requests (a flange, a
  bracket, a spring, a bolt and nut, editing a width, holes on a picked
  face ...) checked exactly against reference scripts, to compare models.
  `--provider`, `--model` and `--base-url` work for every `copilot`
  command.

### The assistant: Debug tab, every command up front, files with permission

- The Assistant panel has a **Debug** tab: the full system message, each
  question, every tool call with its input, JSON answer and time, errors
  and replies, in order. **Copy**, **Save…** and **Clear**.
- Every new chat starts with the whole command list (one line per command)
  and the basics of the language, so Copilot knows the commands without
  looking each one up.
- **New chat** starts a fresh conversation and keeps the sign-in.
- Copilot can list and read text files in the working folder, asking you
  first each time (allow once, allow for this chat, or deny).

### Drawings, themes and signed builds

- `DRAWING, file.svg/.dxf [, views] [, body]` and **File > Export drawing…**:
  2D drawings at true size, the front, top, right and iso views by default,
  hidden edges dashed. DXF files have layers VISIBLE, HIDDEN and TEXT.
- **View > Preferences…**: a light or dark theme (or the system's), the 3D
  view's background, and how toolbar buttons show. Kept between sessions.
- The release workflow signs the Windows and macOS builds (and notarizes
  the macOS one) once signing certificates are added as repository
  secrets (docs/RELEASING.md), and adds `SHA256SUMS.txt` to each release.

### Splines in the sketch editing tools

- Trim, extend and split splines (`STRIM`, `SEXTEND`, `SSPLIT` and their
  tools), and splines now cut other curves. The pieces keep the points the
  spline ran through and the constraints on them.
- `SFILLET` rounds the corner of a spline and a line or arc.
- Constraints with a spline: a point `ON` a spline, and a spline `TANGENT`
  to a line or arc at its end.
- `SJOIN` and **Join to spline**: curves that meet end to end become one
  smooth spline; one line, arc, circle or ellipse becomes a spline to
  reshape.

### Ellipses, constraints while drawing, and the last sketch tools

- Sketch ellipses and elliptical arcs: `SELLIPSE, cu, cv, a, b [, angle]`,
  `SEARC, ..., t1, t2`, the Ellipse (I) and Elliptical arc tools. Size them
  with `SDIM, MAJOR` and `SDIM, MINOR`; trim, split, extend, mirror,
  pattern, move and scale them; put points `ON` them and lines `TANGENT`
  to them. `SPROJECT` brings flat ellipse edges in as ellipses.
- Constraints made while drawing: a click on a curve puts the point on it,
  a line drawn on from an arc's end is tangent, a square turn off a line is
  perpendicular. A mark by the cursor shows it first; Shift skips them, and
  **Auto constraints** switches them off.
- `SCIRCLET` and the Tangent circle tool: a circle touching two curves at a
  radius, or three curves.
- `SOFFSET2, d, ...` and **Offset both…**: a slot along a path (round or
  flat ends), or an outline inside and outside a closed chain.
- `SINTERSECT, body` and **Cut bodies…**: the section of bodies in the
  sketch plane, as fixed sketch curves.
- New sizes: `ARCLEN` (length along an arc, **Arc length…**) and `DIST`
  from a point to an arc or circle.

### More sketch tools, and toolbars with icons

- Sketch chamfer: `SCHAMFER, 1.E, d [, d2]` or `SCHAMFER, 1.E, d, ANGLE, a`,
  and the Chamfer tool. The corner stays as a construction point and the
  sizes are dimensions you can double-click.
- `SSPLIT` splits a curve at points or where another curve crosses it (the
  Split tool); `SCORNER` trims or extends two curves so they meet (the
  Corner tool).
- Power trim: drag the Trim tool across curves and every piece it passes
  over goes, in one step (`STRIM` takes several pieces).
- `STRANSFORM, MOVE/ROTATE/SCALE, ... [, COPY]` and the **Move/Copy…**
  button move, turn or scale sketch geometry, or copies of it, keeping the
  constraints among it.
- New ways to draw: tangent arc (`SARCT`), circle through three points
  (`SCIRCLE3`), centre rectangle (`SRECTC`), rectangle at an angle
  (`SRECT3`), regular polygon (`SNGON`), arc slot (`SSLOTARC`) and
  centreline, each with a mouse tool.
- The toolbars are now a ribbon: one row of tabs (Home, Model, Features,
  Freeform, Inspect, and Sketch, Sketch edit, Constrain while a sketch is
  open), each with labelled groups of buttons, plus quick-access icons
  (undo, redo, pick modes, fit) on every tab. Double-click a tab to fold
  the ribbon. Every button has an icon
  drawn for light and dark themes and keeps its name, and **View > Toolbar
  buttons** switches between icons with names, icons only and names only.
  New buttons: Cone, Torus, Union, Subtract, Intersect, Array, Pattern,
  Mirror, Fillet and Chamfer.
- The sketch's count of degrees of freedom no longer counts numbers left
  behind by deleted geometry or a circle turned into an arc.
- Example: `scripts/cover_plate.cmd`.

### History and sketch leftovers (M3)

- `UNDO` takes back history edits: changing, inserting, deleting,
  suppressing or moving a step, or making a part from steps, is one undo
  step like a new command, and `REDO` does it again. **Roll back to here**
  (`HIST, ROLLBACK, n`) is one undo step too.
- A rebuild runs again only the steps whose inputs changed. Each step notes
  the parameters, bodies, faces and other model state it looked at; a step
  that finds them all as they were reuses what it did last time. Changing
  one part of an assembly no longer rebuilds the others. `HIST, REPLAY`
  still runs everything.
- `SFILLET` rounds a corner between a line and an arc, or two arcs, as well
  as two lines (and the Fillet tool takes those corners).
- The sketch axes can cut: `STRIM, 3, u, v, AXES` (or **Axes cut** on the
  sketch toolbar) and `SEXTEND, 3.E, V`.

### Knife and freehand cuts (M6, third part)

- `KNIFE, b, stroke [, width [, dx, dy, dz]]` cuts a body along a curve seen
  from a direction: splits it into pieces, cuts a slot, or with a closed
  stroke cuts out what is inside. Works on solids and mesh bodies.
- The **Knife** button in the Features toolbar: drag across a body in the 3D
  view to cut it along the view direction.
- Sketch splines: `SSPLINE, p1, p2, ... [, CLOSE]`, with points that can be
  dragged and constrained (`3.K1` ...). The sketcher's **Freehand** tool
  (key D) draws one with the mouse, for freehand pockets and bosses.
- New example `scripts/knife_cuts.cmd`; LANGUAGE.md section 27.

### Implicit shapes and lattices (M6, second part)

- `IMPLICIT, name, f(x,y,z), box [, step]` makes a shape from an equation:
  the body is where the field is at most 0, as a closed mesh body. Building
  blocks `BALL`, `BOX`, `ROD`, `TORUS`, `CYLZ`, `GYROID`, `SCHWARZ`,
  `DIAMOND`; smooth blends `SMIN`, `SMAX`, `SDIFF`; earlier shapes by name.
- `LATTICE, b, kind, cell, thickness [, skin]` fills a solid with gyroid,
  Schwarz or diamond walls, or cubic, BCC or octet struts, optionally
  inside a solid outer skin.
- New example `scripts/implicit_lattices.cmd`; LANGUAGE.md section 26.

### Mesh bodies (M6, first part)

- **Mesh bodies** keep big triangle meshes as meshes: one body, one face,
  up to 5 million triangles. `TOMESH, b` turns a solid
  into one, `TOSOLID, b` turns it back into a faceted solid, and `IMPORT`
  makes one from a mesh file with more than 100,000 triangles (which used to
  be refused), or from any mesh file with the new kind `MESH`.
- `UNION`, `SUBTRACT` and `INTERSECT` with a mesh body run on triangles in
  the manifold3d library: fast (two 245,000-triangle spheres in about a
  second) and always closed. Solids in the same boolean are meshed first.
- `SMOOTH` (noise and bumps go, the size stays), `REMESH` (finer triangles,
  same shape) and `SIMPLIFY` (fewer triangles within a tolerance).
- Moving, copying, mirroring and the deformers keep a mesh body a mesh body;
  `MASSPROP`, `CHECK`, `CLASH`, `DIST`, `PROBE` and `DESCRIBE` measure it;
  `EXPORT` writes it to STL, OBJ, 3MF and GLTF.
- Commands that need faces and edges refuse a mesh body with a message that
  points to `TOSOLID`, instead of failing inside the kernel.
- Sharp edges of a mesh body are shaded sharp.
- New example `scripts/mesh_bodies.cmd`; LANGUAGE.md section 25; a Mesh
  bodies group in the forms menu. New dependency: manifold3d.

### Mates (separate part design, third part)

- `MATE, kind, item, item [, value] [, FLIP]` places a copy against another
  by faces, edges, vertices, datums or base planes: `CONCENTRIC`,
  `COINCIDENT`, `DISTANCE`, `ANGLE`. Mates are history steps, solved in
  order, so copies are placed again when a part changes.
- A mate that cannot be met names both items and moves nothing; flat faces
  put in one plane that do not overlap give a warning.
- **Mate the two picked…** in the right-click menu, and a Mate form (under
  Parts) filled in from the two picked items.

### Linked part files (separate part design, second part)

- `LIB, LINK, file` (**File > Link part file…**): an assembly follows a part
  file. Every open, rebuild and `RELOAD` reads the file itself, and the
  window reloads by itself when the file changes, so every copy updates.
  When the file is missing the copy saved in the project is used, with a
  warning. A saved project finds the file again next to it after the folder
  is moved.
- **Open part** on a copy of a part from a file (right-click, the Model
  tree, the item panel) opens the part file in its own window; saving it
  updates the assembly.
- `LIST, PARTS` and the Model tree say whether each part is linked, loaded
  as a copy, or defined in the project. The `LIB` form links by default.

### Part documents (separate part design, first part)

- **File > New part…** and **File > Open part…**: design one part on its own.
  Its steps are normal history entries and its first parameters are the
  part's inputs (bold in the Parameters panel). **File > Save** writes one
  `*PART` block into a part file, keeping other parts in the file.
- Commands `NEWPART`, `OPENPART`, `SAVEPART`.
- **Edit part** (on a copy of a part, the item panel, or a `*PART` step in
  History) opens a part defined in the project in its own window; saving
  it there updates every copy.

### Model tree and right-click menu (first part)

- Right-click a body in the 3D view for a menu: hide, show only this, fade
  this, fade all others, show everything, zoom to, rename, colour, layer,
  material, explode an instance, find the step that made it, delete. It acts
  on the whole selection when you right-click a selected body. A right drag
  still pans.
- History rows have a "Made by this step" submenu with the same view
  actions for the bodies that step made.
- New view steps `FADE`, `UNFADE` and `DISPLAY` (`HIDE`, `SHOW`, `ONLY`,
  `ALL`, `MODEL`): they change only what the view shows, add no history
  steps, survive undo and rebuilds, and are saved with the project.
- `FIT, b` zooms to some bodies.
- A **Model** tree in a left dock: parts with their placed instances,
  bodies, sketches, datums and named sets, with colour, shown/hidden tick
  boxes, faded and hidden markers and a warning mark. Picking in the tree and
  in the 3D view stay in step; double-click zooms; right-click opens the body
  menu (on a part or group it acts on all its bodies).
- Each history step now records which bodies it read, made, used up and
  changed. `STEPS, b` lists the steps that made a body, including the
  `*PART` of an instance.
- An **item panel** under the tree lists the steps that made the picked
  body and the parameters they use. Each step, also a line inside a part
  recipe or a loop, opens in its form; change a bolt part's `THREAD` pitch
  there and every bolt follows. Parameters can be changed in place.
- Bodies picked in the tree are highlighted in the 3D view whatever a click
  picks (face, edge or body).

## [0.2.0] - 2026-11-14

The second release: freeform NURBS surfaces and deformers, an assistant
on GitHub Copilot that signs in with your own GitHub account, checks for
whether parts touch and fit, and many more file formats.

**Downloads** for Windows (x64), macOS (Apple silicon) and Linux (x64) are
attached below and need no Python; the assistant is included. They are not
code-signed yet; the
[user guide](https://github.com/shashanksingh097/3Dmodeling/blob/main/docs/USER-GUIDE.md#1-install)
says how to open them the first time. Projects and scripts from 0.1.0 open
unchanged.

### Assistant
- An **Assistant** panel with GitHub Copilot (Help > Ask the assistant, Ctrl+Shift+A). Sign in with your own GitHub account using a one-time code; any Copilot plan works, Copilot Free included, and requests count against your own plan. Copilot reads the model with the modeler's text tools, tries scripts in a sandbox, and shows a proposal with a Run button; it never changes the model by itself, and its own coding tools are switched off. Included in the downloads; from source it needs `pip install -e ".[ai]"` in a checkout (Python 3.11+). The Copilot runtime downloads on first use (about 190 MB).
- The assistant can change existing steps (a size, a step that fails): it tries the edits on a copy first, and the panel shows each step's old and new text before you press Run. It can also explain what works on an imported body: `DESCRIBE` and its tools now say whether a body is exact (STEP, IGES, BREP) or faceted (a mesh) and which file it came from.
- A working folder for the assistant (**Folder** in the panel): a temporary folder by default, the project's folder, or one you choose. This also fixes "Copilot is not available: CopilotClient(mode='empty') requires base_directory" when signing in.
- Signing in works on Windows: the sign-in is kept in your own app-data folder (`%APPDATA%\3Dmodeling\copilot`) after you agree. Before, pressing Yes still ended with "the credential could not be stored".
- Do parts touch? `CONTACT, a, b` says whether two bodies are apart (with the gap and where), touch (on faces with the contact area, along a line, or at a point) or overlap (with the volume in common). `CONTACT` alone checks every pair and lists clashes, near misses, the groups of parts that hold together and the parts touching nothing. `CLEARANCE, bolt, plate` gives the clearance or interference of every shaft in a hole. Scripts can keep these as checks with `TOUCH()`, `OVERLAP()`, `CONTACTAREA()`, `GROUPS()` and `CLEARANCE()`, and the assistant has them as its `contact`, `assembly_check` and `fit_check` tools.
- `RELATE, lid, box` says where one part sits relative to another (on which side and how far, centred or not, what it rests on, flush faces, shared axes). `COMPARE, a, b` says whether two bodies are the same shape, a moved copy or a mirror image, or what differs. `DESIGNCHECK, part` finds broken or open bodies, loose pieces, tiny edges, sliver faces, self-intersections and, with a minimum, thin walls. `SAMESHAPE()` and `PROBLEMS()` keep these as script checks; the assistant has them as `placement`, `compare_bodies` and `check_design`.
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
- The nuts in the threaded bolts example (`scripts/threaded_bolts.cmd`) no longer overlap their bolts by about 13 mm³ each: each nut is turned so its thread lines up with the bolt's, and `CONTACT` finds them touching on the thread flanks. [LANGUAGE.md](docs/LANGUAGE.md) shows the formula for your own bolts and nuts.
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
