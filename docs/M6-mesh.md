# M6: mesh bodies, implicit shapes, lattices, knife

M6 adds the second kind of body the plan has asked for since section 2.2 of
PLAN.md: triangle meshes that stay meshes. It comes in three parts:

1. **M6a, mesh bodies** (this note): big meshes, fast mesh booleans,
   smoothing, refining and simplifying (LANGUAGE.md section 25).
2. **M6b, implicit shapes and lattices**: shapes given by an equation
   `f(x, y, z) ≤ 0`, smooth blends between them, lattice infill of a solid.
   They come out as mesh bodies.
3. **M6c, knife and freehand cuts**: `KNIFE` and the Knife button, sketch
   splines and the sketcher's Freehand tool (LANGUAGE.md section 27).

## Part 1: mesh bodies

### What a mesh body is

A faceted body (an imported STL turned into a solid) has one flat B-rep
face per triangle. That is what lets fillets, sections and every face pick
work on it, but each face carries edges, vertices, a plane and a tolerance,
and past about 100,000 triangles it is too slow to build and to combine.

A mesh body keeps its triangles as one mesh instead. Its shape is a **single
OCCT face that carries only a `Poly_Triangulation`** and no surface. That
one choice keeps the rest of the app unchanged:

- The model gives it a body ID and one face ID like any body, so names,
  `PICK`, selections, the Model tree, layers, colours, `HIDE`, `FADE`,
  snapshots, undo and history replay need nothing new.
- OCCT draws it (`AIS_Shape` shades a face from its triangulation), picks
  it, measures its volume and area (`BRepGProp` falls back to triangles), and
  `StlAPI_Writer` writes it.
- The arrays (points, triangles) are read back from the triangulation and
  cached by shape, so commands that work on them in `numpy` and
  `manifold3d` pay for the conversion once.

Rejected: a separate `Body.mesh` field next to an empty shape. Every place
that reads `body.shape` (dozens of them) would then see an empty body,
and the viewport would need its own drawing and picking path for meshes.

### Keeping kernel commands away from mesh bodies

A face with no surface is not something most kernel algorithms expect. Most
of them return an error, but the kernel's general boolean on two such faces
ends the process (found with `CLASH` between two mesh bodies). So:

- `MESH_OK` (commands/mesh_handlers.py) lists the commands that take a mesh
  body. Any other command that names one is refused while its arguments are
  read, with a message that points to `TOSOLID`.
- While a command outside `MESH_OK` runs, `Model.entity_shape` refuses a
  mesh body's face too, so a pick (`PICK, FACE, 7` then `PUSHPULL`) cannot
  carry a mesh into the kernel either (`Model.mesh_entities_ok`, set by
  `Processor._call`).
- Commands that look at every body (`CLASH` with no bodies, `CHECK`,
  `PROBE`, `DESCRIBE`) know mesh bodies: overlaps are found on triangles,
  distances and rays go through a cached faceted copy (`as_faceted`, up to
  100,000 triangles), `CHECK` checks that the mesh is closed.

### Booleans

When any body in `UNION`, `SUBTRACT` or `INTERSECT` is a mesh body, the whole
boolean runs in `manifold3d`: exact solids in it are meshed first (at a
thousandth of their size, at most 0.1 mm), and the result is a mesh body.
manifold3d always returns a closed (manifold) mesh, which is why it was
chosen; it takes 64-bit coordinates (`Mesh64`), so millimetre models lose
nothing. A mesh with holes is refused (it has no inside). The result gets a
new body ID, as every boolean does.

Measured (one core of the build container, November 2026):

| Triangles per body | `IMPORT` STL | `COPY` | `SUBTRACT` | `SMOOTH`, 3 passes |
|-------------------:|-------------:|-------:|-----------:|-------------------:|
| 245,000 | 1.0 s | 0.5 s | 1.0 s | 0.7 s |
| 1,000,000 | 5.1 s | 2.2 s | 4.7 s | 4.2 s |

Most of that is handing the triangles to OCCT one by one from Python; the
boolean itself is a fraction of it. A faster hand-over (or a renderer of our
own for meshes) is a candidate for M7, where sculpting needs it.

### Smoothing, refining, simplifying

- `SMOOTH` is Taubin's filter: a pass pulls each point towards the middle of
  its neighbours (λ), then pushes it back a little (μ < -λ), so noise goes
  but the body does not shrink. Next to long thin triangles a corner would be
  pulled far in (a box cut by a sphere lost most of its volume in the first
  version), so edges longer than three times the typical edge are split
  first, to twice the typical length.
- `REMESH` splits every edge longer than the length given (manifold3d's
  `refine_to_length`). It never changes the shape, only the triangles.
- `SIMPLIFY` collapses edges while no point of the surface moves more than
  the tolerance (manifold3d's `simplify`).

### Drawing sharp edges

The triangulation stored in the face has its points split along edges
sharper than 50 degrees, so the view shades a box's edges sharp instead of
smearing them, and smoothed regions stay smooth. `arrays()` joins the split
points again by exact position, so the model always works on the closed
mesh.

### Where it shows

- `IMPORT, fmt, file [, name [, AUTO/SOLID/MESH]]`: AUTO keeps the old
  behaviour (faceted solid) up to 100,000 triangles and makes a mesh body
  above that (that used to be refused).
- `EXPORT` writes mesh bodies to STL, OBJ, 3MF and GLTF; STEP, IGES and BREP
  refuse them.
- `DESCRIBE` says `representation: mesh`, with what works and what does not,
  and the assistant's instructions know the word.
- The deformers (`BEND`, `TWIST`, `TAPER`, `STRETCH`, `FLOW`) move every
  point of a mesh body; `MOVE`, `ROTATE`, `COPY`, `MIRROR` move the points
  (a mirror turns the triangles over so they still face out).

### Files

- `modeler/geometry/meshbody.py`: the shape that holds a mesh, arrays and
  caches, `triangles_of` (any body as one welded mesh), manifold3d
  booleans, smoothing, refining, simplifying, sharp-edge splitting.
- `modeler/commands/mesh_handlers.py`: `TOMESH`, `TOSOLID`, `SMOOTH`,
  `REMESH`, `SIMPLIFY`, the mesh route of the booleans, `MESH_OK`.
- `scripts/mesh_bodies.cmd`, `tests/test_meshbody.py`.

## Part 2: implicit shapes, smooth blends, lattices

### Fields

`geometry/implicit.py` compiles a field written in the script language to a
numpy function of x, y, z arrays (an AST walk that builds closures; the
script evaluator itself works on single numbers and would take minutes for
a million points). Trig is in degrees, as everywhere in the language.
Building blocks take plain numbers (centres, sizes); a block given an
expression in x, y, z is refused. Named fields live in `Model.fields`
(`FieldDef`: name, text, box, compiled function), which is in snapshots, so
undo and history edits see the right fields.

### Meshing: marching tetrahedra

The field is sampled on a grid with one spare layer outside the box, and
cut by the box exactly (`max(f, box distance)`), so the cap where the box
cuts a shape lies on the box face. Each grid cube is cut into six
tetrahedra around its long diagonal, the same way in every cube, so
neighbouring cubes meet triangle edge to triangle edge. Only cubes with
corners on both sides are processed. A tetrahedron with one or three
corners inside gives a triangle, with two a quad (two triangles). Each
point on a grid edge is made once (keyed by the edge's two grid points), so
triangles share points and the mesh is closed.

Which way a triangle faces comes from the tetrahedron, not the geometry:
corners are sorted inside-first, and a triangle of a tetrahedron with a
negative volume (in grid steps) is turned over. The first version faced
triangles away from an inside corner geometrically; slivers then faced the
wrong way and lattices came out not closed.

Grid meshes have many small triangles, so the result is simplified by a
twentieth of the grid step in manifold3d.

### Lattices

Sheet lattices are `ABS(tpms) - t/2`, with the gyroid, Schwarz P and
diamond surfaces scaled by their gradient so that t is about the wall
thickness. Strut lattices are the distance to the struts of one unit cell
(coordinates taken modulo the cell) minus the radius. `LATTICE` meshes the
lattice over the body's box, then in manifold3d: `lattice ∩ body`, or with
a skin `(body − inside) ∪ (lattice ∩ inside)`, where the inside is the
kernel's offset of the exact solid. Everything stays as manifold3d objects
until the end, since converting a million-triangle mesh to and from
manifold3d is what took most of the time (7 s down to 4 s for a 50 × 25 ×
20 bracket with a gyroid of cell 8).

Measured: a 32 mm cube of gyroid walls at step 0.3, about 9 s (870,000
triangles before simplifying); the bracket above, about 4 s; the example
script, about 13 s.

### Files

- `modeler/geometry/implicit.py`: field compiler, building blocks, grid
  sampling, marching tetrahedra, lattice fields.
- `modeler/commands/implicit_handlers.py`: `IMPLICIT`, `LATTICE`.
- `scripts/implicit_lattices.cmd`, `tests/test_implicit.py`.

## Part 3: knife and freehand cuts

### KNIFE

`geometry/knife.py` turns a stroke into cutting tools. The stroke's wire is
projected, edge by edge, onto a plane across the direction (placed
behind the body), so only the stroke's shape as seen from the direction
counts. An open stroke gets a straight line added at each end, along its
end tangent, long enough to leave the body. Then:

- **Split** (width 0, solid): the flat stroke is swept along the direction
  into a sheet and handed to the kernel's splitter, as `SPLIT` does with a
  cutting body, so the pieces' faces keep their history.
- **Slot** (a width): the slot outline is the flat stroke offset by half the
  width each way (the kernel's 2D offset, round at the ends and bends), swept
  into a solid and subtracted. A straight stroke gets a rectangle instead,
  since the 2D offset cannot tell which plane a straight line is in (it
  guessed one, and a side-on slot came out as a plain split). A closed stroke
  gives a ring: the outline offset outwards with the inward offset as its
  hole.
- **Cookie cutter** (a closed stroke, width 0): the face inside the stroke
  is swept into a solid; on a solid the splitter does the work, on a mesh
  body the pieces are `body ∩ inside` and `body − inside`.
- **Mesh bodies**: everything runs in manifold3d. A split along an open
  stroke has no closed tool to subtract, so it subtracts a hairline slot
  (1e-5 of the body's size) and the separate pieces are found by
  manifold3d's `decompose`.

The biggest piece keeps the body's ID, as with `SPLIT`. The stroke is a body
of its own (a `SPLINE`), hidden afterwards, so editing it in the history
moves the cut.

### The Knife button

The 3D view records the stroke in pixels while the left button is down and
draws it in front of everything. On release (`gui/knife_tool.py`) the
stroke is thinned (Douglas-Peucker, 2 pixels, at most 40 points), each
point's line of sight is met with the plane across the view through the
middle of the body, and two commands are sent: `SPLINE` (or `LINE`, or a
closed `SPLINE` when the stroke ends within 14 pixels of its start) and
`KNIFE, b, LAST, 0, view direction`. The body is the picked one, else the
one the stroke passes over most.

### Sketch splines and the Freehand tool

A sketch spline (`SSPLINE`) is a new kind of sketch geometry. Its points
(`S`, `K1` ... `Kn`, `E`) are ordinary sketch points: solver variables that
can be dragged, fixed and tied, so a freehand curve is not frozen. The curve
is OCCT's interpolation through them (`Geom2dAPI_Interpolate`, periodic
when closed) in the sketch's (u, v), carried onto the sketch plane exactly
(`GeomAPI::To3d`), so the profile and what is drawn are the same curve. The
loop finder treats a closed spline like a circle (one curve that is a loop)
and an open one like an arc (two ends that join other curves).

The Freehand tool records the stroke in sketch coordinates while the
button is down. On release the stroke is thinned by Douglas-Peucker at 0.4
of the pick tolerance (raised until there are at most 60 points) and
written as `SSPLINE`; ends on sketch points are tied there, and a stroke
that ends within two pick tolerances of its start is closed.

Not yet for splines: trim, extend, fillet and offset (they refuse them with
a message), tangent and on-curve constraints.

### Files

- `modeler/geometry/knife.py`: stroke to sheet, slot and cutter.
- `modeler/commands/knife_handlers.py`: `KNIFE`.
- `modeler/gui/knife_tool.py`: the Knife button's stroke to commands;
  `viewport/occ_view.py`: recording and drawing the stroke.
- `modeler/sketch/sketch.py` (`add_spline`), `sketch/profile.py`
  (`spline2d`), `commands/sketch_handlers.py` (`SSPLINE`),
  `gui/sketch_tools.py` (Freehand, `freehand_commands`).
- `scripts/knife_cuts.cmd`, `tests/test_knife.py`, GUI tests in
  `tests/test_sketch_gui.py`.

