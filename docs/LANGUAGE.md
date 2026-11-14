# The command language

Everything the modeler does is a line of text in this language: typed in the
command line, run from a `.cmd` script, or built by a GUI action. This page is
the reference. `HELP` lists the commands in the app and `HELP, NAME` shows one.

```text
! pipe flange, see scripts/flange.cmd for the full version
D = 80
N = 6
CYL, 0,0,0, D/2, 10
NAME, LAST, flange
*MACRO, drill, x, y, d
  CYL, x, y, -1, d/2, 12
  SUBTRACT, flange, LAST
*END
*DO, i, 0, N - 1
  drill, 30*cos(i*360/N), 30*sin(i*360/N), 8
*ENDDO
SEL, S, FACE, NORMAL, 0,0,1
CM, top, FACE
```

## 1. Lines

| Line | Meaning |
|------|---------|
| `NAME, arg, arg, , arg` | a command, or a call of a macro you defined |
| `W = 40` | set a parameter |
| `*DO` `*IF` `*WHILE` `*MACRO` ... | a block, up to its closing line |
| `! text` | a comment (anywhere on a line; `!=` is "not equal") |

* Command names, parameter names and keywords are case-insensitive.
* Arguments are separated by commas. Commas inside `( )` or quotes do not
  split: `CYL, max(1, R), 0, 0, 2, 5` works.
* An empty argument takes its default: `CYL, 0,0,0, 5, 10, , , , 90`.
* Text arguments (kinds, modes, names, file names) can be written bare:
  `SEL, S, FACE` and `EXPORT, STEP, part.step`. Quote them when they contain
  commas or when you want an expression: `EXPORT, STEP, "part" + STR(i) + ".step"`.
  A bare word that is the name of a parameter holding text uses that text,
  which is how macros pass kinds around.
* File names in `RUN` and `EXPORT` are taken exactly as written between the
  quotes, so Windows paths work as is: `RUN, "C:\work\part.cmd"`. (Inside
  other expressions a backslash starts an escape such as `\n`; use `/` there.)

## 2. Parameters and expressions

```text
W = 40
H = W/2
R = sqrt(W**2 + H**2) / 4
P = (10, 0, 5)                 ! a point
SPHERE, P, 3                   ! a point fills three numeric arguments
CYL, P + (0, 0, 10), 2, 5      ! points add and scale
LABEL = "bolt"                 ! text
```

Every numeric argument of every command is an expression.

| | |
|-|-|
| Operators | `+ - * / // % **`, comparisons `== != < <= > >=`, `and or not`, `a if cond else b` |
| Math | `sin cos tan asin acos atan atan2` (degrees), `sqrt exp log log10 abs floor ceil round int sign hypot min max rad deg` |
| Constants | `PI`, `E`, `TRUE`, `FALSE` |
| Units | `MM`, `CM`, `METER`, `INCH`: lengths in the model's unit, so `2*INCH` is 50.8 in a mm model |
| Points | `(x, y, z)`, `VEC(x, y, z)`, `P.x` / `P[0]`, `NORM(v)`, `DISTANCE(a, b)` |
| Text | `"a" + STR(3)`, `STR(x, 2)` (2 decimals) |
| Bodies | `LAST` (the last body made), a body's name stands for its ID |

`^` is not a power operator; write `**`.

### Model queries

| Query | Result |
|-------|--------|
| `VOL(b)` | volume of body `b` (ID or name) |
| `AREA(f)` | area of face `f` |
| `LENGTH(e)` | length of edge `e` |
| `CENT(b)` / `CENT(f, "FACE")` | centre of a body, face, edge or vertex, as a point |
| `BBOX(b).zmax` | bounding box: `xmin ymin zmin xmax ymax zmax dx dy dz` |
| `NSEL()` / `NSEL("EDGE")` | how many are selected (0 if another kind is) |
| `SELID(n)` | the n-th selected ID |
| `COUNT("FACE")` | how many faces (bodies, edges ...) exist |
| `BODY("name")`, `OWNER(f, "FACE")` | body ID by name, body that owns an entity |
| `EXISTS(id, "FACE")`, `PARAM("W", default)` | 1/0, a parameter with a fallback |
| `ORIGIN("top")`, `DIR("top")` | a datum's origin, and its normal (plane) or direction (axis), as points |
| `GAP(a, b)` | shortest distance between two bodies (0 when they touch or overlap) |
| `VALID(b)`, `PIECES(b)` | 1 if the body passes `CHECK`, else 0; how many separate solids it is made of |
| `NFACES(b)`, `NFACES(b, "cylinder")` | how many faces, or faces of one type (plane cylinder cone sphere torus bspline ...) |
| `HOLES(b)`, `HOLES(b, d)`, `HOLES(b, d, 1)` | round holes in the body: all, of diameter `d`, and only through (1) or only blind (0) holes; section 23 |
| `SYMMETRIC(b, "YZ")` | 1 if the body is its own mirror image in the plane (a base plane or a datum plane) |
| `MINWALL(b)` | the thinnest wall of a solid (see `THICK`, section 23) |

`ECHO, VOL(flange) / 1000` prints a value without changing anything.

## 3. Blocks

```text
*DO, i, 1, 10 [, step]        ! i = 1, 2 ... 10; step may be negative or fractional
  ...
*ENDDO

*IF, W, GT, 30 [, THEN]       ! words EQ NE LT GT LE GE ...
  ...
*ELSEIF, W > 20               ! ... or any expression
  ...
*ELSE
  ...
*ENDIF

*WHILE, NSEL() > 0
  ...
*ENDWHILE

*EXIT                          ! leave the loop
*CYCLE                         ! next iteration
*MSG, "volume is ", VOL(1)    ! print a line
*DEL, W, H                     ! forget parameters (or a macro)
```

Blocks nest. A loop runs at most 100 000 times, which stops a mistake like
`*WHILE, 1` instead of freezing the app.

## 4. Macros: your own commands

```text
*MACRO, drill, x, y, d=6, depth=20     ! arguments, with optional defaults
  CYL, x, y, -1, d/2, depth + 2
  SUBTRACT, base, LAST
  *IF, d > 10
    *RETURN                            ! leave early
  *ENDIF
*END

drill, 10, 10                           ! called like any command
drill, 30, 10, 4
```

* Arguments and parameters set inside a macro are local to that call; the
  macro can read the global parameters.
* A bare word that is not a known name is passed as text: `pickall, EDGE`.
* A macro cannot take the name of a built-in command (so a macro once called
  `hole` must be renamed now that `HOLE` is a command). `HELP, DRILL` shows
  its arguments.

## 5. History, undo and editing old steps

The history is the model. Each top-level statement (a command, an
assignment, or a whole block, with the comment lines just above it) is one
history entry, kept as you wrote it. Saving the log writes exactly that text,
and running it rebuilds the model.

* An entry runs all or nothing: if any line of a loop fails, the model goes
  back to how it was before the entry, and the entry is not added.
* View and query commands (`VIEW`, `FIT`, `PICKMODE`, `LIST`, `HELP`,
  `ECHO`, `EXPORT`) run but are not history.

| Command | |
|---------|-|
| `UNDO [, n]`, `REDO [, n]` | step back and forward (parameters and macros too) |
| `HIST` | list the history (`x` failed, `!` ran with a warning, `-` suppressed) |
| `HIST, EDIT, n, "text"` | replace entry n and re-run from there; `\n` separates lines of a block |
| `HIST, INSERT, n, "text"` | add an entry before n |
| `HIST, DELETE, n` | remove entry n |
| `HIST, SUPPRESS, n` / `HIST, RESUME, n` | skip entry n / take it back |
| `HIST, MOVE, n, to` | reorder |
| `HIST, REPLAY` | re-run everything |
| `RUN, file.cmd` | run a script; each top-level statement becomes an entry |

After an edit, later entries that now fail stay in the history marked as
failed (red in the History panel) and are skipped, so you can fix them.

An entry can also run **with a warning** (amber in the History panel, `!`
in `HIST`): it worked, but something needs a look. A pick that had to be
repaired, a union of bodies that do not touch, and a boolean that needed a
tolerance are reported this way. The warning goes away when the cause does.

In the GUI the **History** panel shows the entries; double-click one to edit
it. The **Parameters** panel lists parameter values; typing a new value edits
the history entry that sets it and rebuilds. Both only send `HIST` commands,
which you see in the output.

## 6. Stable references

Scripts and the history refer to things by ID (`PICK, FACE, 12`). These IDs
stay put:

1. **Through operations.** Booleans, fillets, chamfers, moves and rotations
   carry IDs over to the result: the top face of a block is still face 6
   after a hole is cut through it. A face split in two keeps its ID on the
   larger piece. Only new faces and edges get new IDs.
2. **Through history edits.** Each entry remembers the IDs it handed out and
   asks for the same ones when the history re-runs. Inserting a new body near
   the start, or changing a dimension, does not renumber later steps.
3. **By name.** `NAME, LAST, base` names a body. A body made from it (the
   first body of a boolean, a fillet, a move) keeps the name, so `base` always
   means "the part as it is now". Names work wherever a body is expected and
   inside expressions: `VOL(base)`.
4. **By meaning.** Select by geometry instead of by number, and save the
   result as a named set:

```text
SEL, S, FACE, NORMAL, 0,0,1 [, tol_deg]    ! planar faces facing +Z
SEL, R, FACE, LOC, Z, 10 [, 20]            ! R = keep those whose centre has z in [10, 20]
SEL, A, EDGE, SIZE, GT, 10                 ! A = add edges longer than 10 (area for faces, volume for bodies)
SEL, S, EDGE, RADIUS, EQ, 4                ! circular edges (or cylindrical faces) of radius 4
SEL, S, FACE, TYPE, CYLINDER               ! PLANE CYLINDER CONE SPHERE TORUS BSPLINE / LINE CIRCLE ELLIPSE
SEL, S, FACE, BOX, x0,y0,z0, x1,y1,z1      ! centre inside a box
SEL, S, FACE, AT, x,y,z                    ! the face through a point
SEL, S, EDGE, OF, FACE                     ! edges of the selected faces
SEL, S, FACE, BODY, 3                      ! all faces of body 3
SEL, S, FACE, ID, 3, 6                     ! IDs 3 to 6 (ID may be left out)
SEL, U, ...   SEL, ALL, FACE   SEL, NONE   SEL, INVE
CM, top, FACE                              ! save the selection as a named set
CMSEL, S, top    SEL, S, FACE, SET, top    CMDEL, top
```

Modes: `S` new set, `R` reselect within the current set, `A` add, `U` remove.
`SIZE` and `RADIUS` take `EQ NE LT GT LE GE` or `BETWEEN, lo, hi`.

### What happens to a pick when the history changes

`PICK, FACE, 12` is what a click in the viewport writes. Three things keep
it pointing at the same face:

* **IDs do not move.** An entry asks for the IDs it used last time. A loop
  that runs fewer times does not forget the IDs of its longer run, so a
  pick on hole 3 fails while the plate has two holes and works again when
  it has four. Project files store these IDs, so a reopened project is
  numbered exactly as it was when saved.
* **Every pick remembers what it picked**: which step made it, the kind of
  surface or curve, where it is, its size and its direction. If the ID is
  gone, or now belongs to something made by a different step (you deleted a
  step and built it again another way), the pick looks for the entity that
  matches. It is accepted only when exactly one entity fits: either one
  sitting in the same place, or the only one with the same shape, size and
  direction. The entry then gets a warning that names the entity it used.
* **It never guesses.** If several entities fit equally (the four equal
  edges of a block, say), the entry fails and asks you to pick again. A
  failed entry is easy to see; a pick that quietly moved to the wrong face
  is not.

A plain script (Save log) holds only the text, so it does not carry these
IDs. In scripts you write to keep, select by geometry or by name.

## 7. Commands

| Group | Commands |
|-------|----------|
| Primitives | `BLOCK, x,y,z, dx,dy,dz` · `CYL, x,y,z, r, h [, dx,dy,dz] [, angle]` · `TUBE, x,y,z, ro, ri, h [, axis]` · `CONE, x,y,z, r1, r2, h [, axis]` · `SPHERE, x,y,z, r` · `TORUS, x,y,z, ring_r, tube_r [, axis]` · `WEDGE, x,y,z, dx,dy,dz, ltx` |
| Booleans | `UNION, a, b [, c ...]` · `SUBTRACT, a, b [, c ...]` · `INTERSECT, a, b [, c ...]` (IDs or names; the result keeps the first body's name; `SEL` in place of the tools means every selected body) · `KEEP, ON/OFF` (keep the inputs as hidden bodies; tools keep their names) |
| Patterns | `ARRAY, LINEAR, b, n, dx,dy,dz [, n2, dx2,dy2,dz2]` · `ARRAY, POLAR, b, n [, angle [, x,y,z [, dx,dy,dz]]]` · `ARRAY, PATH, b, path, n [, twist_law [, scale_law]] [, MINTWIST/FRENET/FIXED]`; add `FUSE` to fuse the copies into the original, or `CUT, target` to cut them all from another body in one step · `PATTERN, LINEAR/POLAR, b, steps, n, ...` repeats a feature (section 21) |
| Blends | `FILLET, r` · `CHAMFER, d` (on the selected edges, or all edges of the selected bodies) |
| Check and repair | `CHECK [, b]` · `HEAL, b [, tolerance]` · `CLEAN, b` (section 12) |
| Datums | `PLANE, name, how, ...` · `AXIS, name, how, ...` · `POINT, name, how, ...` · `DATUM, DELETE, name` · `WORKPLANE, plane/OFF` (section 13) |
| Sketches | `SKETCH, name [, plane / FACE, id]` · `ENDSKETCH` · `SLINE` · `SPOLY` · `SRECT` · `SCIRCLE` · `SARC` · `SARC3` · `SSLOT` · `SPOINT` · `SCON` · `SDIM` · `SDEL` · `SMOVE` · `SCONSTRUCT` · `SSEL` (section 16) |
| Sketch features | `EXTRUDE, sketch, d [, NEW/ADD/CUT [, b [, back]]]` · `REVOLVE, sketch, axis [, angle [, NEW/ADD/CUT [, b]]]` (section 16) |
| Part features | `HOLE, b, x,y,z, d [, depth, kind, d2, h2, tip, dx,dy,dz]` · `SPLIT, b, plane/body [, BOTH/ABOVE/BELOW]` · `SHELL, t [, IN/OUT]` · `DRAFT, angle [, plane [, dx,dy,dz]]` · `OFFSET, b, d [, ROUND/SHARP]` (section 14) |
| Parts | `*PART, name, P=default, ...` ... `*ENDPART` · `INST, part, x,y,z [, angle [, dx,dy,dz]] [, P=value ...]` · `EXPLODE, b` · `LIB, LOAD, name/file` · `LIBSAVE, part [, file]` · `LIST, PARTS` · `HIST, PART, first, "last, name"` (section 17) |
| Measure | `DIST` · `ANGLE` · `MASSPROP [, b [, density]]` · `CLASH [, a, b]` · `SECTION, plane/OFF [, BELOW/ABOVE]` (section 15) |
| Transforms | `MOVE, b, dx,dy,dz` · `ROTATE, b, angle [, x,y,z [, dx,dy,dz]]` · `COPY, b, dx,dy,dz` · `MIRROR, b [, x,y,z [, nx,ny,nz [, copy]]]` |
| Paths | `LINE, p1, p2` · `ARC, p1, p2, p3` · `POLYLINE, p1, p2, ... [, CLOSE]` · `SPLINE, p1, p2, ... [, CLOSE]` · `HELIX, x,y,z, r, pitch, turns [, axis] [, taper] [, RIGHT/LEFT] [, pitch_law]` · `CURVE, PARAM, x(t), y(t), z(t) [, t0, t1, n]` |
| Profiles | `CIRCLE, x,y,z, r` · `ELLIPSE, x,y,z, a, b` · `RECT, x,y,z, w, h [, r]` · `POLYGON, x,y,z, r, sides` · `STAR, x,y,z, ro, ri, points` · `SLOT, x,y,z, length, width` · `AIRFOIL, x,y,z, chord, code`, each followed by `[, nx,ny,nz [, angle]]` (section 9) |
| Shapes on curves | `LOFT, s1, s2, ... [, RULED] [, CLOSED] [, SURFACE] [, GUIDE, g1, g2, ...]` · `SPINELOFT, spine, s1, s2, ... [, FRENET/FIXED] [, SURFACE]` (section 20) · `SWEEP, profile, path [, twist, scale, mode, sx, sy, ox, oy, n, solid, on]` · `MORPH, path, twist, scale, mode, s1, s2, ...` · `RAILSWEEP, profile, rail1 [, rail2] ...` (section 19) · `PIPE, path, r [, ri, radius_law, mode]` (section 9) |
| Threads and springs | `THREAD [, pitch] [, length] [, hand]` · `SPRING, x,y,z, r, pitch, turns, d ...` (section 18) |
| Text and surfaces | `TEXT, text, x,y,z, size [, depth] [, nx,ny,nz [, angle]] [, LEFT/CENTER/RIGHT] [, font] [, style]` · `SURFACE, PARAM, x(u,v), y(u,v), z(u,v), u0, u1, v0, v1 [, nu, nv] [, thick]` (section 20) |
| Edit faces | `PUSHPULL, d` · `DELFACE` (on the selected faces, section 20) |
| Bodies | `NAME, b, name` · `DELETE, b` · `CLEAR` · `HIDE, b` · `SHOW [, b]` · `ISOLATE [, b/SEL/layer]` |
| Layers and looks | `LAYER, name [, CURRENT/NEW/ON/OFF/LOCK/UNLOCK/COLOR/ADD/RENAME/DELETE [, value]]` · `COLOR, b/SEL/ALL, colour` · `MATERIAL, b/SEL/ALL, name [, density [, colour]]` (section 22) |
| Selection | `PICK, kind, id [, S/A/U]` · `SEL ...` · `CM` · `CMSEL` · `CMDEL` · `PICKMODE, kind` |
| Settings | `/UNITS, MM/CM/M/IN` · `/TOL, value` (fuzzy booleans and selection tolerance) |
| Files | `EXPORT, STEP/IGES/BREP/STL/OBJ/3MF/GLTF, file [, body]` · `IMPORT, STEP/IGES/BREP/STL/OBJ/3MF/GLTF/PLY/OFF/VTK/MESH, file [, name]` (section 10) · `RUN, file` |
| Projects | `SAVE [, file.m3d]` · `OPEN, file.m3d` · `OPEN, AUTOSAVE` · `NEW` (section 10) |
| History | `UNDO` · `REDO` · `HIST ...` |
| View & info | `VIEW, ISO/TOP/...` · `FIT` · `LIST [, BODIES/PARAMS/MACROS/SETS/DATUMS/SKETCHES/SKETCH/LAYERS/MATERIALS]` · `ECHO, expr` · `HELP [, name]` |
| Check and describe | `PROBE, RAY/POINT, ...` · `PROFILE, b, plane [, offset [, step, count]]` · `THICK, b [, below]` · `ASSERT, value [, op, ref [, tol]]` · `DESCRIBE [, b/SEL/FACE, id [, SUMMARY/FACES/EDGES]] [, JSON]` · `SELFOR [, kind, id]` · `LINT [, file]` · `DIFF [, first [, last]] [, JSON]` (section 23) |

## 8. Running scripts without the GUI

```bash
python -m modeler run scripts/flange.cmd                     # print every step
python -m modeler run scripts/flange.cmd -D N_BOLTS=8 -q     # fix a parameter, quiet
```

`-D NAME=value` fixes a parameter: the script's own `NAME = ...` keeps the
given value, so one script makes a whole family of parts. The exit code is 0
when every statement ran.

## 9. Shapes on curves

A **path** is a curve to move along; a **profile** is a closed curve that
moves. Both are ordinary bodies (drawn in orange), so they have IDs and names,
and they stay after you use them: one path can carry many sweeps.

```text
LINE, 14,0,0, 134,0,0                   ! a path
NAME, LAST, spanline
AIRFOIL, 14,0,0, 30, 2412, 1,0,0, 40    ! a profile where the path starts
SWEEP, LAST, spanline, -32*t, 1 - 0.53*t
```

### Points

Commands that take a list of points (`POLYLINE`, `SPLINE`) take them as
points in parentheses, and parameters holding points work too:
`SPLINE, (0,0,0), P1, P1 + (10,0,5), CLOSE`. Angles everywhere are in
degrees, including in `sin` and `cos`.

### Where a profile lies

Every profile is drawn on a plane through `(x,y,z)` with normal `(nx,ny,nz)`
(default +Z), then turned by `angle` in that plane. The profile's own X and Y
directions are:

* normal +Z: X is world X, Y is world Y;
* any other normal: X is level (world Z x normal), Y points as far up (+Z)
  as the plane allows. For normal +X, profile X is world Y and profile Y is
  world Z.

`AIRFOIL` puts its chord along profile X with the quarter-chord point on
`(x,y,z)` (change it with the last argument, `pivot`), so a twist turns the
airfoil about that point.

### Laws

A law is any expression in `t`, where `t` is 0 at the start of the path and
1 at the end. Laws can use parameters, macro arguments and every function:

| Law | Meaning | Example |
|-----|---------|---------|
| `twist` | turn about the path, degrees | `40 - 32*t`, `360*t`, `20*sin(180*t)` |
| `scale` | grow or shrink | `1 - 0.5*t`, `1 + 0.3*sin(720*t)` |
| `sx`, `sy` | stretch along the profile's X or Y only | `1 + t` |
| `ox`, `oy` | slide off the path along X or Y | `10*t**2` |

A law can also be quoted: `SWEEP, prof, path, "30*t"`. A law without `t` is
a constant: `SWEEP, prof, path, 15` turns the whole profile by 15 degrees.

A law can also be a **table** of values at stations along the path, joined
smoothly: `TABLE(t, t0, v0, t1, v1, ...)`. It passes through every station,
never overshoots between two of them, and holds the end values outside
them. This is what the sweep editor writes when you drag its handles:

```text
SWEEP, root, spanline, TABLE(t, 0, 40, 0.6, 20, 1, 8)    ! twist 40 -> 20 at 60% -> 8
```

`TABLE` is an ordinary function, so it works in any expression, not only in
laws: `TABLE(X, 0, 1, 10, 3)`.

### The sweep editor

Right-click a `SWEEP` step in the History panel and choose **Sweep
editor…** (or press **Sweep editor…** on the Features toolbar, which opens
the selected step or the last `SWEEP`). It shows:

* a graph of the twist and one of the scale over `t`, with a handle at each
  station. Drag a handle up or down to change the value there, or sideways
  to move it along the path; double-click to add one, right-click to remove
  one. A law written as a formula turns into five handles the first time you
  drag it;
* a slider that moves a ghost section (pink) along the path, with the twist
  and scale at that `t`;
* a see-through preview of the sweep as it will be.

Nothing changes until **Apply**, which runs `HIST, EDIT` with the new
`SWEEP` line (laws as `TABLE(t, ...)`, comments kept), so the history stays
the record of the model and Undo works as for any edit.

### LOFT

`LOFT, s1, s2, s3, ...` fits one smooth solid through the sections in order.
The sections can be different shapes (a circle, then a rounded square, then
a polygon) and need not be parallel. Add `RULED` for straight sides between
sections, `CLOSED` to come back to the first section (a ring), `SURFACE` for
no end caps.

Curves after `GUIDE` steer the side between the sections: `LOFT, foot,
belly, neck, GUIDE, front, side`. Each guide must pass through every
section, crossing them in the order they are given (the message names the
section a guide misses, and by how much). Round closed sections, each
section swells or shrinks about its middle to reach the guides, smoothly
from one guide to the next, so one or two guides shape the whole side; open
sections (a `SURFACE` loft) are pulled along smoothly between the guides. The loft
passes through each section as a smooth curve through 96 of its points, so
sharp corners come out slightly rounded. Not with `RULED` or `CLOSED`.

### SWEEP

`SWEEP, profile, path [, twist, scale, mode, sx, sy, ox, oy, n, solid, on]`

* Draw the profile where the path starts, usually across it. Its place
  relative to the path start is kept all along (an offset profile stays
  offset).
* `mode`: `MINTWIST` (default) keeps the profile from spinning on 3D
  curves; `FRENET` follows the curve's bend (good on helices); `FIXED` never
  turns the profile, it only moves; `NORMAL` keeps the profile at the same
  angle to the surface `on` that the path lies on (a rib standing up from a
  curved panel, a bead round a car body): `SWEEP, rib, track, , , NORMAL, ,
  , , , , 1, panel`. Lay the path on the surface first with `PROJECT` (see
  section 24); the sweep is then exact. A path that only lies on the
  surface by its numbers is swept through sections instead.
* With no laws the sweep is exact. With a scale law only, it is still exact.
  Other laws place the profile at `n` stations and fit a smooth surface
  through them; `n` = 0 picks enough stations for the twist and the bends of
  the path (the result message says how many).
* `solid` = 0 gives the swept surface only.

### MORPH

`MORPH, path, twist, scale, mode, s1, s2, s3, ...` sweeps a shape that
changes on the way: profile `s1` at the start, the last one at the end, the
others evenly in between, blending smoothly from each to the next. Draw all
profiles at the start of the path (they may overlap); repeat one to hold it
longer: `MORPH, duct, 0, 1, , round, round, square`.

### PIPE

`PIPE, path, r [, ri, radius_law, mode]` is a round tube along any path:
solid, or hollow when `ri` > 0, with an optional radius law
(`PIPE, coil, 1.5, 0, 1 + t`).

### HELIX and CURVE

`HELIX, x,y,z, r, pitch, turns [, dx,dy,dz] [, taper] [, RIGHT/LEFT] [, pitch_law]`
starts on the profile-X side of the axis. `taper` (degrees) makes it
conical; the pitch law multiplies the pitch along the helix
(`0.5 + 2*t*(1-t)*2` gives tighter coils at the ends).

`CURVE, PARAM, x(t), y(t), z(t) [, t0, t1, n]` samples an equation at `n`
points and fits an exact smooth curve through them; it closes itself when
it ends where it starts:

```text
CURVE, PARAM, 8*(sin(t) + 2*sin(2*t)), 8*(cos(t) - 2*cos(2*t)), -8*sin(3*t), 0, 360, 180
PIPE, LAST, 3                     ! a trefoil knot
```

See `scripts/blade_smooth.cmd` and `scripts/sweep_gallery.cmd`.

## 10. Projects, imports and autosave

`SAVE, bracket.m3d` writes a project file: a zip with the history as a
script, a copy of every file the history imports, and a small description.
`OPEN, bracket.m3d` replaces the session and replays that history, so every
step is still there to edit, and imports read the copies inside the project
(the project still opens when the original STEP file is gone). `SAVE` with
no file saves back to the last project saved or opened. `NEW` starts an
empty session. These commands act on the session, so they are not history
entries and `UNDO` does not undo them.

`IMPORT, STEP, "housing.step", housing` adds each solid in the file as a
body; the first one gets the name.

**Exact files and mesh files.** STEP, IGES and BREP hold exact shapes:
an imported body works like one made here (fillets, holes, `SHELL`,
`PUSHPULL`, `DELFACE`), but the other program's feature history does not
come along, so edits are recorded on top of the body as it came in.

STL, OBJ, 3MF, GLTF (`.glb` or `.gltf`), PLY, OFF and VTK (`.vtk`,
`.vtu`) hold triangles. Each connected piece becomes one **faceted body**:
every triangle is a flat face. A closed piece is a solid (turned the right
way out if its triangles faced inwards); an open one is a surface, and the
message says so. Volume meshes from simulation tools (tetrahedra,
hexahedra, wedges, pyramids, also second-order ones) keep only their outer
skin. `MESH` reads any other file the meshio library knows, by its
extension: Gmsh `.msh`, Abaqus `.inp`, Nastran `.bdf`/`.nas`, `.med`,
`.xdmf` and more. 3MF and glTF carry their units (glTF is in metres), so
they arrive at the right size; the other mesh formats have no units and
are read as the model's units.

Faceted bodies take booleans, `SPLIT`, `SECTION`, measuring and export,
but not fillets or shells across facets. Up to 100,000 triangles become a
body; reduce a bigger mesh in a mesh tool first. Editing meshes as meshes
(smoothing, sculpting, fast mesh booleans) is planned for M6 and M7.

`EXPORT` writes STEP, IGES or BREP (exact) or STL, OBJ, 3MF or GLTF
(triangles, 0.1 mm fine). OBJ, 3MF and glTF keep one object per body with
its name and colour; 3MF records the model's units; glTF is written in
metres with Y up, as viewers expect, as a binary `.glb` or a single
`.gltf` file.

The app autosaves the project a moment after every change. When it starts
and finds the autosave of the last session, the **Recover** button appears;
it runs `OPEN, AUTOSAVE`. The autosave lives in the app's data folder; set
the environment variable `MODELER_AUTOSAVE` to another file, or to `off`.

## 11. Typing help in the command line

While you type, the command line offers the words that fit where the cursor
is: command and macro names at the start of a line, the choices of a keyword
argument (`ARRAY, P` offers `POLAR`, `PATH`), and parameter and body names.
Tab or Enter takes the highlighted word. Above the line, the command's
arguments are listed with the one you are typing underlined, plus what it
means and its default.

## 12. Results you can trust: checks, CHECK, HEAL and CLEAN

A geometry kernel can report success and still hand back a broken shape.
Every boolean and every fillet or chamfer is therefore checked before its
result is accepted, and a bad result is an error at the command that caused
it, with the model left as it was:

| Situation | What you get |
|-----------|--------------|
| `SUBTRACT` removes the whole body | error: nothing is left |
| `INTERSECT` of bodies that do not overlap (or only touch) | error: no volume in common |
| `FILLET` or `CHAMFER` too large for the edges | error that names the largest size that works there, for example "the largest radius that works here is about 4.9" |
| A boolean whose exact result is not a valid shape | retried with a small tolerance; if that works the entry gets a warning, otherwise an error |
| `UNION` of bodies that do not touch | works, with a warning that the body is in separate pieces |

`UNION` (and `ARRAY ... FUSE`) also joins faces that end up on the same
surface, so two blocks fused side by side give one block with 6 faces, not
10; the joined face keeps the ID it had on the first body. A boolean result
that is one solid is stored as a solid.

Cutting many tools in one step is far faster than one at a time, because
the kernel rebuilds the whole body for every cut: 300 holes take about 13 s
one by one and under half a second together. Make the tool bodies, select
them, and write `SEL` for the tools:

```text
*DO, i, 0, 29
  *DO, j, 0, 9
    CYL, 5 + i*10, 5 + j*10, -1, 1.5, 10
  *ENDDO
*ENDDO
SEL, S, BODY, SIZE, LT, 100        ! the cylinders
SUBTRACT, plate, SEL
```

Booleans always get the quick tests (something is left, it is still a
solid, the skin has no open edges). The full validity check is slow on big
bodies, so on those it runs only now and then, keeping its cost under a
tenth of the modelling time. Fillets and chamfers always get the full check.

```text
CHECK                 ! every body: OK, or what is wrong and what to try
CHECK, housing        ! one body, always the full check
HEAL, housing         ! repair a broken body (typically an import); HEAL, b, 0.01 closes gaps up to 0.01
CLEAN, housing        ! join neighbouring faces on the same surface (seams from imports or cuts)
```

`CHECK, b, SELF` adds the kernel's own self-intersection test: faces that
cut through each other, which no repair can fix. It can take seconds on a
long sweep, so it runs only when asked, and faces that only touch along a
seam can also show up there.

### Shapes made from curves

`LOFT`, `SPINELOFT`, `SWEEP`, `MORPH`, `RAILSWEEP` and `PIPE` get their own
checks. The kernel builds a pipe that is too fat for its bend, or a sweep
whose turns overlap, without complaint and calls the result valid; booleans
on it then fail steps later. So before a solid is built, its sections are
compared: the cross-sections of a sound shape never touch each other, and
two that do mean the shape runs into itself there. That takes milliseconds
and the message says where and why:

| Situation | What you get |
|-----------|--------------|
| A profile bigger than a bend of the path (`PIPE` of radius 8 round a bend of radius 5) | error: "the path bends with a radius of about 5 there, but the profile reaches 8 from the path" |
| A sharp corner in the path (a `POLYLINE`) | error at the corner's t: round it (a `SPLINE`, or an `ARC` between the lines) |
| A path that comes back near itself (a tight helix) | error naming the two places (t values) that meet |
| A profile drawn along the path instead of across it | error: the shape would have no thickness |
| `LOFT` sections that cut through each other, or lie in the same plane | error naming the two sections |
| `LOFT` sections out of order (z = 0, 20, 10) | error: the shape would pass through itself |
| A `LOFT` section that crosses itself (a figure-of-eight) | error naming the section |
| A result that is not valid, has gaps in its skin, or no volume | repaired if a repair works (with a warning), otherwise an error |
| A solid made inside out | turned the right way round, with a warning |

A solid swept round a closed path (a ring, a knot) is built as a closed loft
through sections along the path, because the kernel's exact sweep leaves
two caps where the ends meet. Its volume is within a percent of the exact
one.

The examples in `scripts/` and the hard cases in `tests/corpus/hard/` run in
CI: every example must work, every body must pass `CHECK`, and the bodies,
faces and volume of each example must stay as recorded, so a kernel upgrade
cannot change a model unnoticed (`python tests/test_corpus.py --update`
records new numbers after a deliberate change).

`CHECK` is a query and not part of the history. `HEAL` and `CLEAN` are
history entries; the body keeps its ID and name, and its faces keep their
IDs where they survive. `HEAL` refuses, and changes nothing, when the repair
does not give a valid body (a missing face cannot be invented).

## 13. Datums: planes, axes and points to build on

A datum is a named reference, not a body: it has no faces to pick, takes no
part in booleans or exports, and is drawn see-through in the view (planes
blue, the work plane green, axes yellow, points pink, each with its name).
Datums are history entries like everything else, so when an earlier step
changes, a plane made on a face moves with the face.

| Command | Makes |
|---------|-------|
| `PLANE, name, XY [, offset]` (also `YZ`, `ZX`) | a world plane, moved along its normal |
| `PLANE, name, PN, x,y,z, nx,ny,nz [, angle]` | through a point with a normal |
| `PLANE, name, 3P, p1, p2, p3` | through three points (X towards the second) |
| `PLANE, name, FACE, id [, offset]` | on a flat face, normal pointing out of the body |
| `PLANE, name, OFFSET, plane, d` | parallel to another plane |
| `PLANE, name, ANGLE, plane, axis, degrees` | another plane turned about an axis that lies in it |
| `PLANE, name, MID, face1, face2` | half way between two parallel flat faces |
| `PLANE, name, NORMAL, edge [, t]` | across an edge at fraction `t` (0 start, 1 end): where a sweep profile goes |
| `AXIS, name, X` (also `Y`, `Z`) | a world axis |
| `AXIS, name, PD, x,y,z, dx,dy,dz` · `AXIS, name, 2P, p1, p2` | from a point and direction, or two points |
| `AXIS, name, EDGE, id` | along a straight edge, or the axis of a round one |
| `AXIS, name, FACE, id` | the axis of a cylinder or cone, or the normal through a flat face's middle |
| `AXIS, name, PLANES, plane1, plane2` | where two planes meet |
| `POINT, name, XYZ, x,y,z` · `POINT, name, VERTEX, id` | at coordinates, or on a vertex |
| `POINT, name, CENTER, kind, id` | centre of a round edge, or the middle of a face, edge or body |
| `POINT, name, ON, edge, t` | at fraction `t` along an edge |
| `DATUM, DELETE, name` · `LIST, DATUMS` | remove one, list them |

Where a command expects an entity ID, `SEL` takes the first selected one:
`PICK, FACE, 6` then `PLANE, top, FACE, SEL`. Wherever a plane is asked for
(`SPLIT`, `DRAFT`, `SECTION`, `WORKPLANE`, `PLANE ... OFFSET`), you can give a
datum plane's name or `XY`, `YZ`, `ZX`. A datum's name cannot also be a
body's or a parameter's name.

Every plane has its own X and Y: on a +Z normal, X is world X; otherwise X
is level and Y points as far up as the plane allows (the same rule as the
profiles in section 9).

### Work planes

```text
PLANE, top, FACE, 6
WORKPLANE, top          ! from here, x and y run along the top face, z out of it
CYL, 0, 0, 0, 4, 10     ! a boss standing on the middle of the top face
RECT, 0, 0, 0, 20, 10   ! a profile lying on it
HOLE, part, 15, 0, 0, 5 ! a hole in it, 15 along the face's X
WORKPLANE, OFF          ! back to world X, Y, Z
```

`WORKPLANE` changes where the commands that make shapes from typed numbers
put them: the primitives, the curves and profiles of section 9, and `HOLE`.
Selection, transforms, datums and measuring always use world coordinates.

## 14. Part features: HOLE, SPLIT, SHELL, DRAFT, OFFSET

These change a body in place: it keeps its ID and name, and the faces that
survive keep their IDs, like after a fillet. Each result is checked; a step
that would give a broken body is an error, with the model left as it was.

### HOLE

`HOLE, body, x,y,z, d [, depth, kind, d2, h2, tip, dx,dy,dz]` drills at a
point on the body's surface. With no direction it goes straight into the
flat face the point is on.

| | |
|-|-|
| `HOLE, plate, 20,10,5, 6` | 6 mm, through everything |
| `HOLE, plate, 20,10,5, 6, 12` | 12 deep, flat bottom |
| `HOLE, plate, 20,10,5, 6, 12, SIMPLE, , , 118` | with a 118 degree drill point |
| `HOLE, plate, 20,10,5, 6, 0, CBORE, 11, 4` | counterbore 11 wide, 4 deep |
| `HOLE, plate, 20,10,5, 6, 0, CSINK, 12 [, 90]` | countersink 12 wide at the top, 90 degrees |
| `HOLE, plate, 0,10,2, 3, 0, SIMPLE, , , , 1,0,0` | sideways, along +X |

### SPLIT

`SPLIT, body, plane` cuts a body in two along a plane. The piece on the
plane's normal side keeps the body's ID and name; the others are new bodies.
`ABOVE` or `BELOW` keeps only one side. `SPLIT, body, other` cuts it with the
faces of another body (which stays as it is); the biggest piece keeps the name.

### SHELL

Select the faces to open, then `SHELL, thickness`: the part is hollowed out
with walls of that thickness, open where the faces were. Select bodies
instead to make them hollow and closed. `OUT` grows the walls outwards. If
the wall does not fit, the error names the thickest wall that does.

```text
SEL, S, FACE, NORMAL, 0,0,-1     ! the bottom
SHELL, 2.5                        ! an open box with 2.5 mm walls
```

### DRAFT

Select side faces, then `DRAFT, angle [, plane [, dx,dy,dz]]`: the faces tilt
so a moulded or cast part comes out of its mould. They keep their size where
they cross the neutral plane (default: the work plane, or XY), and a positive
angle makes the part narrower along the pull direction (default: the plane's
normal).

### OFFSET

`OFFSET, body, d` grows (`d` > 0) or shrinks the whole body. Corners round
off when growing; `SHARP` keeps them square.

## 15. Measuring

These print what they find and change nothing, so they are not history.
`DIST` and `ANGLE` take two things, each as a kind and an ID (`FACE, 6`,
`BODY, plate`, `DATUM, mid`, or a world plane `XY`), or no arguments to use
the two selected things.

| Command | Prints |
|---------|--------|
| `DIST, FACE, 6, VERTEX, 3` | the shortest distance, the two closest points, and the gap in X, Y and Z |
| `ANGLE, FACE, 1, FACE, 3` | the angle between flat faces, straight or round edges, axes and planes |
| `MASSPROP [, body [, density]]` | volume, area, centre of mass and principal moments of inertia; with a density in kg/m3 (7850 for steel), or when every body has a `MATERIAL` (section 22), also the mass in kg and inertia in kg.mm2. No body: the selected bodies, or all shown |
| `CLASH [, a, b]` | whether bodies overlap, by how much, or how far apart they are; alone, every pair of shown bodies |
| `SECTION, plane [, BELOW/ABOVE]` | cuts the view open along a plane to look inside; the cut faces are drawn red. `SECTION, OFF` closes it |

In the GUI the **Features** toolbar runs these from the selection: pick a
flat face and press **Plane**, **Work plane** or **Hole**; select faces and
press **Shell** or **Draft**; select two things and press **Distance** or
**Angle**. Each button only builds the command and runs it, so you see the
command in the output and in the history.

See `scripts/bracket_features.cmd`.

## 16. Sketches, EXTRUDE and REVOLVE

A sketch is a flat drawing on a plane: lines, arcs and circles held in place
by constraints (level, upright, tangent ...) and dimensions (a length, a
radius, a distance). Its closed loops become a solid with `EXTRUDE` or
`REVOLVE`. Every step of a sketch is its own history entry, so a dimension
is changed by editing its entry, and everything after it runs again.

```text
W = 80
SKETCH, s1, XY                ! or a datum plane, or FACE, 6 / FACE, SEL
SRECT, 0, 0, W, 40
SCON, COINCIDENT, 1.S, ORIGIN
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, 40
SCIRCLE, 20, 20, 5
SDIM, DIAMETER, 5, 10
SDIM, HDIST, ORIGIN, 5.C, 20
SDIM, VDIST, ORIGIN, 5.C, 20  ! now fully defined
ENDSKETCH
EXTRUDE, s1, 10               ! a plate with a hole
```

### Where a sketch lies

`SKETCH, name` opens a sketch on the work plane (or XY). `SKETCH, name, XY`
(or `YZ`, `ZX`, or a datum plane's name) puts it on that plane, and
`SKETCH, name, FACE, 6` on a flat face; `FACE, SEL` uses the picked face. A
sketch on a face remembers its body, which is where `EXTRUDE ... ADD` and
`CUT` go by default. In-sketch positions are `u, v` on the plane; `LIST,
SKETCH` shows which world directions they run along. `ENDSKETCH` closes the
sketch; using it in `EXTRUDE` or `REVOLVE` closes it too. `SKETCH, name,
DELETE` removes a sketch nothing uses yet.

### Drawing

| Command | Draws |
|---------|-------|
| `SLINE, p1, p2 [, H/V] [, CONSTR]` | a line; `H` or `V` makes it level or upright |
| `SPOLY, p1, p2, ... [, CLOSE]` | joined lines |
| `SRECT, p1, p2` | a rectangle from two corners, held square |
| `SCIRCLE, centre, r` | a circle |
| `SARC, centre, r, a1, a2` · `SARC3, start, through, end` | an arc (degrees, counter-clockwise) or an arc through three points |
| `SSLOT, c1, c2, r` | a slot: two half circles joined by tangent lines |
| `SPOINT, p` | a lone point |

A point is `u, v`, a point value `(u, v)`, or the name of a point already in
the sketch. Giving a name ties the new geometry there:
`SLINE, 1.E, 40, 20` starts at the end of line 1 and stays joined to it.
`CONSTR` at the end makes construction geometry: it helps place things
(and can be a `REVOLVE` axis) but is not part of a profile.

### Names in a sketch

| Name | Is |
|------|----|
| `3` | geometry 3 (the numbers the drawing commands print) |
| `3.S`, `3.E`, `3.C` | its start, end, centre; `3.P` a lone point |
| `ORIGIN` (or `O`) | the sketch origin |
| `H`, `V` | the sketch's horizontal and vertical axes |
| `C4` | constraint or dimension 4 |

### Constraints and dimensions

`SCON, kind, things` holds geometry without a size: `COINCIDENT` (two
points; a point and a curve means `ON`), `ON`, `HORIZONTAL`, `VERTICAL`
(a line, or two points), `PARALLEL`, `PERPENDICULAR`, `TANGENT`, `EQUAL`,
`MIDPOINT` (a point and a line), `SYMMETRIC` (two points about a line or
`H`/`V`), `CONCENTRIC`, `FIX`.

`SDIM, kind, things, size` gives a size; the size is any expression, so it
can be a parameter: `LENGTH`, `DIST` (two points, or a point and a line),
`HDIST`, `VDIST`, `RADIUS`, `DIAMETER`, `ANGLE` (degrees between two lines,
or from `H` with one line).

After each step the sketch says how many degrees of freedom are left. At 0
it is fully defined, and the GUI draws it green. A constraint that cannot
hold with the others is refused and names the ones it fights, so the sketch
is never left half broken. One that adds nothing new is kept but reported.

`SDEL, 3` deletes geometry with its constraints, `SDEL, C4` one constraint.
`SMOVE, 3.E, u, v` drags a point (what is held stays held).
`SCONSTRUCT, 3 [, ON/OFF]` toggles construction.

### Profiles

The closed loops of the non-construction curves are the profile. A loop
inside another is a hole, a loop inside a hole is a new island. An open end,
or three curves meeting at a point, is an error that says where, so you can
fix it or make the extra curve construction.

### EXTRUDE and REVOLVE

| Command | Makes |
|---------|-------|
| `EXTRUDE, s1, 20` | a new body, 20 along the sketch normal (negative: the other way) |
| `EXTRUDE, s1, 20, NEW, , 5` | also 5 the other way |
| `EXTRUDE, s1, 5, ADD [, b]` | a boss, fused into body `b` (default: the body the sketch is on) |
| `EXTRUDE, s1, -8, CUT [, b]` | a pocket; `0` with `CUT` goes through everything |
| `REVOLVE, s1, V` | a full turn about the sketch's vertical axis |
| `REVOLVE, s1, 5, 90` | a quarter turn about line 5 (often a construction line) |
| `REVOLVE, s1, Z, 360, CUT, part` | about a world or datum axis, cut from `part` |

The result is checked like every other feature: a cut that misses or an add
that changes nothing says so.

### In the GUI

Press **Sketch** on the Features toolbar (with a flat face picked, the
sketch goes on that face; otherwise you choose a plane). The view turns to
face the sketch, bodies go see-through, and the **Sketch** toolbar appears:

* Drawing tools: Select (S), Line (L), Rectangle (R), Circle (C), Arc (A),
  Point (P). Clicks snap to points, line middles, curves and the axes, and
  round to a step that suits the zoom. A line tool click on the first point
  closes the shape; Esc or a double click ends a chain.
* Click geometry to select it (Shift adds), then press a constraint button,
  or **Size…**, **Across…** or **Up…** for a length, radius, angle or a
  horizontal or vertical distance. Double click a size on the drawing to
  change it. Drag a point to move it.
* **Construction**, **Delete**, **Finish sketch** and **Extrude…**.
  **Extrude…** and **Revolve…** open a form that shows the command it will
  run.
* In the History panel, right click a sketch step and choose **Sizes of
  sketch …** for a table of every size; changing one re-runs the model.

Every button and click only builds a command and runs it, so the output and
the history show exactly what happened, and a script can do the same.

See `scripts/sketch_bracket.cmd`.

### Editing sketch geometry

| Command | Does |
|---------|------|
| `STRIM, 3, u, v` | cuts away the piece of curve 3 nearest (u, v), between the curves crossing it on either side; a piece in the middle leaves two curves, a circle becomes an arc, a curve nothing crosses is deleted |
| `SEXTEND, 3.E` | makes line or arc 3 longer at its end until it meets the next curve |
| `SEXTEND, 3.S, 5` | ... at its start, up to curve 5 (its full line or circle counts) |
| `SFILLET, 1.E, 4` | rounds the corner where line 1 ends and another line meets it, radius 4 |
| `SFILLET, 1.E, 2.E, 3.E, 4` | several corners, one radius |
| `SOFFSET, 3, 1, 2, 3, 4` | curves 3 away from curves 1..4 |
| `SMIRROR, V, 1, 2` | mirror copies of 1 and 2 about the vertical axis (or about a line: its number) |
| `SPATTERN, LINEAR, 4, 15, 0, 5` | 4 of circle 5 in all, each 15 to the right of the one before |
| `SPATTERN, POLAR, 6, 360, O, 5` | 6 round the origin, spread over the full turn (less than 360: the last one at that angle) |
| `SPROJECT, 12, 13` | body edges 12 and 13, laid flat on the sketch plane and fixed there |
| `SPROJECT, FACE, 6` | every edge of face 6 (`SEL` takes the picked edges or faces; `CONSTR` at the end makes construction geometry) |

What they leave behind keeps meaning what you asked for:

* A trimmed or extended end stays **on** the curve that cut it, so when
  that curve moves the end follows. Sizes that measured the part that went
  (a length, a fix) are dropped, and the output names them.
* A fillet keeps the corner as a construction point on both lines. A size
  that went to the corner (a length, a distance) now goes to that point, so
  a fully sized sketch stays fully sized. The radius is a size like any
  other: double-click it, or change it in **Sizes of sketch**; that edits
  the `SFILLET` step.
* An offset is held to its original: lines stay parallel at the distance,
  arcs keep the centre and the radius plus the distance. Curves joined end
  to end are offset as one chain; sharp corners meet again, smooth ones
  stay smooth. Positive is outwards for a closed chain or a circle, and to
  the left for an open chain (walking along its lowest-numbered curve from
  its start). Change a size of the original afterwards and the offset
  follows.
* Mirror and pattern copies are held as images of their originals: drag or
  size an original and every copy moves with it, and a copied circle keeps
  the same radius.
* Projected edges are made again from the bodies whenever an earlier step
  changes, so a sketch drawn round a projected hole follows the hole.
  Straight edges become lines and circles flat on the sketch become circles
  or arcs; other curves come in as a chain of short lines. An edge square to
  the sketch shows as nothing.

In the GUI the Sketch toolbar has **Trim** (T: click the piece to cut
away; it is shown before you click), **Extend** (E: click near the end),
**Fillet** (F: click a corner; the radius starts at a fifth of the shorter
line, then double-click it to change it), and **Offset…**, **Mirror…**,
**Pattern…** and **Project…**, which work on the selected geometry.

See `scripts/sketch_tools.cmd` for a plate drawn with these.

## 17. Parts and instances

A part is a reusable shape recipe with parameters. Define it once, place it
as often as you like, and every copy follows the definition.

```
*PART, bolt, D=8, L=30, K=0.7*D     ! parameters and their defaults
  POLYGON, 0, 0, 0, D*0.9, 6        ! hexagon head: two hexagons and a straight loft
  POLYGON, 0, 0, K, D*0.9, 6
  LOFT, 1, 2, RULED
  CYL, 0, 0, -L, D/2, L             ! shank
  UNION, 3, 4
*ENDPART

*DO, i, 1, 8
  INST, bolt, i*25, 0, 0, D=SIZE    ! eight copies; SIZE is a parameter out here
*ENDDO
INST, bolt, 0, 40, 0, 90, 1, 0, 0, L=50   ! turned 90 degrees about X, a longer one
```

* **The definition** is one history entry. Its body runs in a model of its
  own, starting empty, so body numbers inside it start at 1 whatever the
  main model holds. A default can use an earlier parameter (`K=0.7*D`). A
  parameter with no default (`*PART, washer, D`) must be given by every
  `INST`. When every parameter has a default, the part is built once when it
  is defined, so mistakes show at once.
* **A part sees only its own parameters.** Pass anything else in:
  `INST, bolt, x, y, z, D=SIZE`. Parts can place other parts.
* **What a part gives** is the solids it leaves shown (curves and profiles
  used to build them are left out). Several solids stay together as one body.
* **`INST, part, x, y, z [, angle [, dx, dy, dz]] [, NAME=value ...]`** turns
  the part by `angle` degrees about the axis `(dx, dy, dz)` (default Z)
  through its own origin, then moves it to `(x, y, z)`, on the work plane if
  one is set. `NAME=value` items can come anywhere after the part name.
* **Every copy follows.** Edit the `*PART` entry, or a parameter an `INST`
  passes, and everything after it re-runs. A part built with the same values
  is reused, so fifty identical bolts are built once.
* **Instances are bodies.** You can name, move, copy, cut and fillet them.
  `MOVE`, `ROTATE`, `COPY` and `MIRROR` keep a body an instance; any other
  change makes plain geometry. `LIST, BODIES` marks instances and `LIST,
  PARTS` lists the parts with how many copies each has.
* **`EXPLODE, b`** splits a body into one body per solid (`name_1`,
  `name_2` ...), or turns a one-solid instance into plain geometry.
* **Steps into a part.** `HIST, PART, 3, "7, bracket"` turns history entries
  3 to 7 into `*PART, bracket` and places it once where those steps put it,
  so the model looks the same. Parameters set inside those steps become the
  part's parameters. Parameters from before them that the steps use become
  part parameters too, passed in by the `INST` (`W=W`), so the model still
  follows them. If the steps used a body made earlier, the part cannot be
  built on its own; nothing changes and the message says why. In the GUI:
  select the rows in the History panel, right click, "Make a part from
  steps …".

### The part library

`LIBSAVE, bolt` writes the part's definition to `bolt.cmd` in the library
folder (`MODELER_LIBRARY`, default `~/.modeler/parts`), or `LIBSAVE, bolt,
"path/file.cmd"`. It runs when given and is not kept in the history.
`LIB, LOAD, bolt` reads it back in another project (also `LIB, LOAD,
"path/file.cmd"`; the file must hold only `*PART` blocks and comments). A
saved project keeps a copy of every part file it loaded, like imported
files, so it opens on a computer without your library.


## 18. Screw threads and springs

### THREAD

`THREAD [, pitch] [, length] [, RIGHT|LEFT]` cuts a real helical ISO metric
thread (60 degree flanks) into the selected round faces. Select the face
first: `PICK, FACE, 7`, or by script `SEL, S, FACE, AT, x, y, z` with a point
on the face.

```
CYL, 0, 0, 0, 4, 30           ! an 8 mm shaft
SEL, S, FACE, AT, 4, 0, 15    ! its side
THREAD                        ! M8: ISO coarse pitch 1.25, the whole length

HOLE, plate, 20, 10, 0, 6.8   ! the M8 tap drill
SEL, S, FACE, AT, 23.4, 10, -2
THREAD                        ! the matching M8 inside thread
```

* **Outside or inside** comes from the face: the side of a shaft gets an
  outside thread, the wall of a hole an inside thread.
* **Size.** A shaft's diameter is the thread's major diameter. A hole is read
  as drilled for a thread: anything from the minor diameter to the usual tap
  drill (size minus pitch) counts, so a 6.8 hole takes M8. With no pitch
  given, the ISO coarse pitch of that size is used (M8: 1.25, M10: 1.5, M12:
  1.75); a size that is not an ISO size needs the pitch. A pitch given for a
  hole that is not drilled for a standard size makes a thread 0.54 x pitch
  deep into the wall.
* **Where it runs.** A thread starts at a free end of the face (one with
  nothing of the body beyond it, a chamfer or countersink counts as free) and
  runs out past it cleanly. It stops before a closed end (a bolt head, a
  shoulder, the bottom of a blind hole) and never cuts into it. `length` is
  measured from the free end of the face (where a chamfer starts); if both ends are free and a length is given,
  it starts at the upper end (highest Z). A face with no free end cannot be
  threaded.
* **Hand.** `RIGHT` (default) or `LEFT`.
* The body keeps its ID and name. The message names the thread, for example
  `M8 outside thread (pitch 1.25, minor diameter 6.466)`.
* `PITCH(d)` gives the ISO coarse pitch of a size inside any expression:
  `HOLE, nut, 0, 0, M, D - PITCH(D)` drills the tap drill for any `D`.

A threaded bolt and nut as parts (from `scripts/threaded_bolts.cmd`):

```
*PART, bolt, D=8, L=30, K=0.7*D, B=2*D+6
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, K, D*0.9, 6
  LOFT, 1, 2, RULED
  CYL, 0, 0, -L, D/2, L
  UNION, 3, 4
  SEL, S, EDGE, AT, 0, D/2, -L    ! the rim at the tip
  CHAMFER, D/10
  SEL, S, FACE, AT, D/2, 0, -L/2  ! the side of the shank
  THREAD, , MIN(B, L)
*ENDPART

*PART, nut, D=8, M=0.8*D
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, M, D*0.9, 6
  LOFT, 1, 2, RULED
  HOLE, LAST, 0, 0, M, D - PITCH(D)
  SEL, S, FACE, AT, (D - PITCH(D))/2, 0, M/2
  THREAD
*ENDPART
```

### SPRING

`SPRING, x, y, z, r, pitch, turns, d [, dx, dy, dz] [, RIGHT|LEFT] [, closed] [, PLAIN|GROUND]`
makes a coil spring of round wire around the axis through `(x, y, z)`
(default +Z, on the work plane if one is set).

* `r` is the coil radius (axis to the middle of the wire), `d` the wire
  diameter, `turns` counts every turn, end coils included.
* `closed` turns at each end are wound tight, so the spring stands flat
  (a compression spring); the pitch eases smoothly from the tight end coils
  to `pitch` in the middle.
* `GROUND` grinds both ends flat, square to the axis, taking off half a wire.
* The message gives the free height.

```
SPRING, 0, 0, 0, 10, 6, 8, 1.5                    ! plain, open ends
SPRING, 40, 0, 0, 10, 5, 10, 2, , , , , 1, GROUND ! closed and ground ends
SPRING, 80, 0, 0, 6, 3, 8, 1, , , , LEFT          ! left-hand
```

For a spring with any other pitch law, or a wire that is not round, use
`HELIX` with a pitch law and `SWEEP` or `PIPE` (sections 9 to 11).

## 19. Sweeps steered by rails

`RAILSWEEP, profile, rail1 [, rail2] [, path] [, thick] [, SCALE|TURN] [, n] [, solid]`
sweeps a profile along a path while one or two rails steer it. Draw the
profile where the sweep starts, touching the rails there. At every station
the section plane, square to the path, cuts each rail in one point, and the
profile is moved within that plane so the points it had on the rails at the
start land on the rails again.

* **One rail:** the profile turns about the path so its point on the rail
  stays on it: a twisted handrail, a strip wound round a post. With `SCALE`
  (default) it also grows or shrinks evenly when the rail moves away from or
  towards the path; with `TURN` it keeps its size.
* **Two rails:** the profile turns, moves and scales evenly so it spans both
  rails: a wing between its leading and trailing edges, a hull between keel
  and deck line. Thickness goes with the chord. `thick` is a law in `t` that
  thins (or thickens) it on top, square to the line between the rails.
* **The path** is the curve the sections stand square to. Leave it out and
  rail 1 is used. For a wing, give a straight line along the span, so the
  sections stay parallel to the root as they are on real wings.
* The rails must run the whole length of the path: each section plane must
  cut them. Two rails must stay apart. Rails can be drawn in either
  direction.

```
AIRFOIL, 0, 0, 0, 40, 2412, 0, -1, 0, , 0     ! root section, chord along +X
NAME, LAST, foil
LINE, 0, 0, 0, 0, 120, 0                         ! the span
NAME, LAST, spine
SPLINE, (0, 0, 0), (7, 60, 2), (28, 120, 8)      ! leading edge: swept back, rising
NAME, LAST, le
SPLINE, (40, 0, 0), (45, 60, 2), (44, 120, 8)    ! trailing edge: tip chord 16
NAME, LAST, te
RAILSWEEP, foil, le, te, spine, 1 - 0.3*t        ! thinner towards the tip
```

The full example is `scripts/wing_rails.cmd`. One rail:

```
RECT, 10, 0, 0, 10, 2, 0, 0, 0, 1   ! a strip from x = 5 to 15
HELIX, 0, 0, 0, 15, 60, 100/60      ! the rail, through the strip's outer edge
LINE, 0, 0, 0, 0, 0, 100            ! the post's axis
RAILSWEEP, 1, 2, 0, 3               ! the strip winds round the post
```

## 20. Text, spine lofts, equation surfaces and face editing

### TEXT

`TEXT, text, x,y,z, size [, depth] [, nx,ny,nz [, angle]] [, align] [, font] [, style]`
writes letters from a font. The baseline starts at `(x,y,z)` and runs along
the plane's X (the same plane rule as profiles, section 9); `size` is the
font size, so capital letters are about 0.7 of it tall.

* `depth` 0 gives flat letters (faces); any other depth gives solid letters
  that thick along the normal (negative: below the plane).
* `align` is `LEFT` (default), `CENTER` or `RIGHT` of the point.
* `font` is a font name (`sans-serif`, the default, `serif`, `monospace`,
  `DejaVu Sans` ...) or the path to a `.ttf`/`.otf` file; `style` is
  `REGULAR`, `BOLD`, `ITALIC` or `BOLDITALIC`.
* Put the text in quotes when it has spaces or commas: `TEXT, "M8 x 1.25", ...`.

The letters are exact curves from the font, so they cut and fillet like any
other solid:

```
BLOCK, 0,0,0, 70,24,4
NAME, LAST, plate
TEXT, "M4 DONE", 35,6,4, 9, 1.2, , , , , CENTER, , BOLD   ! raised
UNION, plate, LAST
TEXT, "No 16", 4,1.5,3.4, 4, 1                           ! engraved 0.6 deep
SUBTRACT, plate, LAST
```

### SPINELOFT

`SPINELOFT, spine, s1, s2, ... [, FRENET/FIXED] [, SURFACE]` lofts through
sections that sit along a curved centre line. Draw each section where it
belongs, across the spine (it need not be exactly square to it). The
sections can be given in any order; they are sorted along the spine, and the
result says where each one sits (`t` from 0 to 1). Between them, the shape
blends smoothly (through all the sections at once, so there is no kink at a
middle one) and stays square to the spine, so the shape follows the bend of
the spine rather than cutting straight across as a plain `LOFT` would.

```
ARC, 0,0,0, 14.64,0,35.36, 50,0,50                ! a 90 degree bend
NAME, LAST, spine
CIRCLE, 0,0,0, 9                                  ! round at the start
RECT, 14.64,0,35.36, 20, 14, 4, 0.7071,0,0.7071    ! rounded square half way
CIRCLE, 50,0,50, 5, 1,0,0                         ! smaller and round at the end
SPINELOFT, spine, 2, 3, 4
```

`FRENET` turns the sections with the spine's bend, `FIXED` never turns them
(default: `MINTWIST`, as for `SWEEP`). `SURFACE` leaves the ends open.

### SURFACE

`SURFACE, PARAM, x(u,v), y(u,v), z(u,v), u0, u1, v0, v1 [, nu, nv] [, thick]`
samples an equation on a grid of `nu` x `nv` steps (32 each by default) and
fits one exact smooth surface through the points. Angles in `sin` and `cos`
are in degrees, as everywhere.

* An open surface stays a surface, or becomes a solid wall when `thick` is
  given (negative: to the other side).
* A surface that closes on itself (a torus, a sphere, any closed shell)
  becomes a solid by itself.

```
SURFACE, PARAM, u, v, 3*sin(6*u)*cos(6*v), 0, 60, 0, 60, 30, 30, 2     ! a wavy cover, 2 thick
SURFACE, PARAM, (20 + 6*cos(v))*cos(u), (20 + 6*cos(v))*sin(u), 6*sin(v), 0, 360, 0, 360   ! torus
```

### PUSHPULL and DELFACE: editing faces directly

These change the faces of a solid without needing the steps that made it,
so they work on imported STEP parts too. Select faces first (click them, or
`SEL, S, FACE, ...`).

* `PUSHPULL, d` moves each selected face by `d` along its outward normal and
  lets the faces around it stretch to meet it. Positive adds material,
  negative removes it. A flat face moves flat; a hole's wall changes the
  hole's radius (`PUSHPULL, -1` makes it 1 bigger in radius); a fillet's
  face changes the fillet. Face IDs stay the same.
* `DELFACE` removes the selected faces and closes the gap: the faces around
  them grow to fill it. Select all the faces of the feature to remove: a
  through hole's wall, a blind hole's wall and bottom, a fillet's face, a
  boss's side and top.

```
BLOCK, 0,0,0, 40,30,10
NAME, LAST, blk
CYL, 20,15,-1, 4, 12
SUBTRACT, blk, LAST
SEL, S, FACE, BODY, blk
SEL, R, FACE, NORMAL, 0,0,1
PUSHPULL, 6                       ! the top goes up by 6
SEL, S, FACE, BODY, blk
SEL, R, FACE, TYPE, CYLINDER
PUSHPULL, -2                      ! the hole grows from radius 4 to 6
DELFACE                           ! ... and now it is gone
```

The Features toolbar has **Push/Pull…** and **Delete faces** buttons for the
selected faces. See `scripts/m4_shapes.cmd`.

`MOVEFACE, dx, dy, dz` moves the picked faces of a solid in any direction
and `REPLACEFACE, surface` gives them the shape of a surface body; the faces
around stretch or shrink to meet them, and every face keeps its ID:

```
PICK, FACE, 6
MOVEFACE, 0, 0, 5        ! the top up 5 (for a flat face this is PUSHPULL, 5)
PICK, FACE, 6
REPLACEFACE, wave        ! the top takes the shape of surface 'wave'
```

The solid is grown along the face's outward direction as far as needed,
then cut back by the new surface (carried on past its edges when it does not
reach across). The surface has to cross the body cleanly there: one that
misses it, or would cut the body in two, is refused with the body unchanged.

## 21. Patterns of features, and fast repeated cuts

Cutting holes one at a time makes the kernel rebuild the whole body for each
cut, so 300 holes take about 11 seconds, and the same again after an edit
near the start of the history. Two commands do the same work in one kernel
call:

* `ARRAY, ..., CUT, target` places the copies as `ARRAY` always does, then
  cuts all of them (the original too) from `target` in one step. The tool
  body is used up, as with `SUBTRACT` (with `KEEP, ON` it stays, hidden).

  ```
  BLOCK, 0,0,0, 160,160,10
  NAME, LAST, plate
  CYL, 5,5,-1, 2, 12
  ARRAY, LINEAR, LAST, 15, 10,0,0, 20, 0,8,0, CUT, plate   ! 300 holes in 0.3 s
  ```

* `PATTERN, kind, b, steps, n, ...` repeats a **feature**: whatever the last
  `steps` history steps did to body `b`. The material those steps added and
  the material they took away are copied to each place and put in at once
  (one fuse and one cut, however many copies). So any feature can be
  repeated: a `HOLE`, a pocket, a boss with its hole, a `THREAD`, engraved
  `TEXT`.

  | Kind | Arguments after `steps` |
  |------|-------------------------|
  | `LINEAR` | `n, dx,dy,dz [, n2, dx2,dy2,dz2]` (a row, or a grid) |
  | `POLAR` | `n [, angle [, x,y,z [, dx,dy,dz]]]` (round an axis; 360 by default) |

  ```
  HOLE, plate, 5,5,10, 4
  PATTERN, LINEAR, plate, 1, 15, 10,0,0, 20, 0,8,0       ! 300 holes in 0.4 s

  CYL, 0,0,0, 40, 5
  NAME, LAST, flange
  CYL, 30,0,5, 3, 4
  UNION, flange, LAST                  ! a boss ...
  HOLE, flange, 30,0,9, 2              ! ... with a hole through it
  PATTERN, POLAR, flange, 3, 6         ! the last 3 steps, 6 times round the axis
  ```

  `steps` counts history steps, selections included: `SEL ...` then
  `THREAD` is 2 steps. Edit the feature (`HIST, EDIT` on the `HOLE`) and the
  pattern follows. As in other modelers, each copy is the same change
  made at another place, so the shape round the original must be the same
  where the copies go (a copy that runs off the edge of the body is cut off
  there, like the original would be).

### Long rebuilds: progress and Cancel

When an edit far back in the history takes more than half a second to
re-run, the window shows which step is running, with a **Cancel** button.
Cancel puts the model and the history back exactly as they were before the
edit.

## 22. Layers, colours and materials

Every body sits on one **layer**. A model starts with one layer, `DEFAULT`.
A layer can be switched off (its bodies are not drawn, and `MASSPROP` and
`CLASH` with no bodies named skip them), **locked** (its bodies cannot be
changed, used up as a tool, or deleted) and given a colour.

| Command | What it does |
|---------|--------------|
| `LAYER, name` | makes the layer if it is new, and puts new bodies on it from now on |
| `LAYER, name, NEW [, colour]` | makes a layer without switching to it |
| `LAYER, name, ON` / `OFF` | shows or hides its bodies |
| `LAYER, name, LOCK` / `UNLOCK` | protects its bodies from changes |
| `LAYER, name, COLOR, colour` | its colour (`DEFAULT` for none) |
| `LAYER, name, ADD [, b/SEL/ALL]` | moves bodies onto it (default: the selection) |
| `LAYER, name, RENAME, new` | renames it (its bodies follow) |
| `LAYER, name, DELETE` | deletes it; its bodies move to `DEFAULT` |
| `LAYER, ALL, ON/OFF/LOCK/UNLOCK` | every layer at once |
| `COLOR, b/SEL/ALL, colour` | a body's own colour (`DEFAULT` to draw it by layer or material) |
| `MATERIAL, b/SEL/ALL, name` | a material: `MASSPROP` then gives the mass without a density (`NONE` takes it off) |
| `MATERIAL, b, name, density [, colour]` | makes a material of your own (kg/m3) and gives it to the bodies |
| `ISOLATE [, b/SEL/layer]` | shows only these bodies; `SHOW, ALL` brings the rest back |
| `SEL, S, BODY, LAYER, name` · `SEL, S, BODY, MAT, name` | selects by layer or material (any kind: `SEL, S, FACE, LAYER, pipes`) |
| `LIST, LAYERS` · `LIST, MATERIALS` | what there is, with body counts |

`SEL` in `COLOR`, `MATERIAL`, `LAYER ... ADD` and `ISOLATE` means the
selected bodies, or the bodies of the selected faces, edges or vertices.

A **colour** is a name (`RED`, `ORANGE`, `YELLOW`, `GREEN`, `TEAL`, `CYAN`,
`BLUE`, `NAVY`, `PURPLE`, `MAGENTA`, `PINK`, `BROWN`, `WHITE`, `GREY`,
`BLACK`), a code `#rrggbb` (or `#rgb`), or three numbers from 0 to 255:
`COLOR, LAST, 255, 128, 0`, or a point parameter `C = (255, 128, 0)`.

Built-in **materials** (kg/m3): `STEEL` 7850, `STAINLESS` 8000, `CASTIRON`
7200, `ALUMINIUM` 2700 (also `ALUMINUM`), `TITANIUM` 4430, `COPPER` 8960,
`BRASS` 8500, `ABS` 1050, `NYLON` 1150, `PLA` 1240, `RUBBER` 1100, `WOOD`
600, `GLASS` 2500. Each has a colour, and bodies of `GLASS` are drawn
see-through, so what sits behind a lamp lens or a window shows.

How the rules fit together:

* A body is drawn in its own colour; if it has none, in its layer's colour;
  if that has none, in its material's colour; else in the plain grey.
* New bodies go on the current layer. A body made **from** other bodies (a
  boolean, a fillet, `MOVE`, a `HOLE`) keeps the layer, colour and material
  of its first input, and so do copies (`COPY`, `MIRROR`, `ARRAY`), whatever
  the current layer is.
* With mixed materials, `MASSPROP` adds up each body's own mass, so the
  centre of mass and the inertia are right for the assembly.
* Inside a `*PART`, bodies on a layer that is off are not part of the
  instance: a handy place for construction bodies.
* All of these are history steps like any other: undo, `HIST, EDIT` and
  saved projects replay them.

```
LAYER, frame, NEW, #5a6f8a
LAYER, bolts, NEW, ORANGE
LAYER, frame
BLOCK, -40,-25,0, 80,50,8
MATERIAL, LAST, CASTIRON
LAYER, bolts
CYL, 30,17,-4, 3, 16
MATERIAL, LAST, STEEL
LAYER, frame, LOCK          ! the frame cannot change by accident now
MASSPROP                    ! mass of both, from their materials
```

In the window, the **Layers** panel (a tab next to Parameters) shows one row
per layer: click the first column to make it current, tick Show and Lock,
double-click a name to rename it, click the colour to choose one. The
buttons make a layer, move the selected bodies onto the chosen layer, show
only that layer, and delete it. Each click runs the matching `LAYER`
command, so it lands in the history like typed text. `COLOR`, `MATERIAL` and
`ISOLATE` have forms in the Commands menu under "Layers, colours,
materials".

## 23. Checking and describing: ASSERT, DESCRIBE, SELFOR, LINT, DIFF, CONTACT, CLEARANCE

These commands say exactly what the model is and whether it is right,
in words and numbers. They are what the AI assistant uses instead of
looking at pictures (docs/M9-ai-tools.md), and they are just as handy
typed by hand.

### ASSERT: checks that live in the script

```
ASSERT, VALID(flange)                         ! true or false
ASSERT, HOLES(flange, D_BOLT), EQ, N_BOLTS    ! a comparison: EQ NE LT GT LE GE
ASSERT, BBOX(flange).dz, EQ, 40, 0.001        ! ... with a tolerance
ASSERT, VOL(flange), BETWEEN, 66000, 68000
ASSERT, VOL(a) > VOL(b)                        ! one comparison written out
ASSERT, SYMMETRIC(flange, "YZ")
```

When the check holds, `ASSERT` does nothing but print `ok: HOLES(flange, 8)
= 6`. When it does not, the step fails and says why: `ASSERT failed:
BBOX(flange).dz is 40, expected EQ 41 (± 0.01)`, and like any failed step it
does not go into the history (a script stops there). A passing `ASSERT` is a
history step, so it runs again whenever the history is re-run: change
`N_BOLTS` in the Parameters panel and the check on the number of holes is
done again with the new value. `scripts/flange.cmd` ends with a few.

Without a tolerance, `EQ` allows a millionth of the value (plus `/TOL`).

### DESCRIBE: the model in words

| Command | What it shows |
|---------|---------------|
| `DESCRIBE` | every body (kind, volume, bounding box), parameters, datums, sketches, named sets, the selection, the history length |
| `DESCRIBE, flange` | one body: valid, volume, area, box, centre of mass, numbers of faces, edges and vertices, faces by type, flat faces by direction, the step that made it, and its **holes**: diameter, through or depth, counterbore, axis, positions, and the circle they sit on when they form a pattern |
| `DESCRIBE, flange, FACES` / `EDGES` | one row per face (type, area, centre, normal or axis and radius, whether a round face is on the inside, the faces next to it) or edge (type, length, ends, radius, the two faces) |
| `DESCRIBE, FACE, 12` · `DESCRIBE, SEL` | those faces, edges or vertices |

Add `JSON` at the end for the same data as compact JSON. Numbers are
rounded to 3 decimals and lists are in ID order, so two answers compare
line by line.

A hole is a round, concave face (or several on one axis) that goes all the
way round. It is *through* when its axis leaves the body at both ends
without meeting material; a chamfer, countersink or counterbore round the
mouth does not count as material, a floor or a drill point does. A wider
hole on the same axis that starts where a narrower one ends is that hole's
counterbore. A rounded slot end or a fillet in a corner is only part of a
cylinder, so it is not a hole.

### SELFOR: a selector instead of an ID

`SELFOR, FACE, 12` (or `SELFOR` with one thing selected) prints the `SEL`
lines that pick exactly that entity by what it is, most telling criteria
first:

```
SELFOR, EDGE, 45
SEL, S, EDGE, RADIUS, EQ, 20
SEL, R, EDGE, LOC, Z, 38.5
```

Use these in scripts in place of `PICK, EDGE, 45`: when an earlier step
changes and IDs move, the criteria still find the right edge. When nothing
but the ID tells an entity apart from its look-alikes, `SELFOR` says so and
lists them.

### LINT: check a script before running it

`LINT, "bracket.cmd"` (or `LINT` alone, for the history as it stands) reads
a script without running it and reports, by line: syntax errors, unknown
commands (with the nearest names), too many or missing arguments, names used
before they are set, and raw IDs (`PICK`, `SEL ... ID`) that may move.

### DIFF: what changed

`DIFF` shows what the last step did; `DIFF, 3` what happened since entry 3;
`DIFF, 0, 5` what the first five entries made. Bodies made, removed and
changed (volume, faces added and removed, moved, renamed, layer or
material), parameters, datums and sketches. `JSON` at the end gives the
data.

### PROBE: is there material here?

```
PROBE, RAY, -50,0,5, 1,0,0          ! every face the ray crosses, and the material along it
PROBE, RAY, (35,0,50), (0,0,-1), flange
PROBE, POINT, 37, 0, 5               ! inside, on or outside, and the nearest face
```

A ray lists each crossing (distance along the ray, entering or leaving,
which body and face, the point) and then the stretches of material: `from
10 to 16 (6)` is a wall 6 thick. A ray up the middle of a through hole meets
nothing. Add a body name to look at that body only.

### PROFILE: a cut through a body, as text

`PROFILE, flange, XY, 5` cuts the body with the XY plane moved 5 along its
normal and lists the loops of the cut: the outside and the holes, each a
circle, a rectangle, or a list of lines, arcs and curves, in the plane's own
u and v (printed in the first line). Equal round holes are one line, with
the circle they sit on:

```
body 19 cut by XY (u along (1, 0, 0), v along (0, 1, 0)):
  at 5: area 4272.57, centre (0, 0)
    outside: circle c (0, 0) r 40
    hole: circles n 6 r 4 on c (0, 0) r 30 step_deg 60
    hole: circle c (0, 0) r 12
```

`PROFILE, flange, XY, 0, 10, 5` makes five cuts 10 apart, like a scan up the
part. A cut exactly on a flat face shows the cut just beside it, and says so.

### THICK and MINWALL: the thinnest walls

`THICK, housing` measures the wall straight into the material from points
spread over every face and lists the five thinnest places, with the faces on
both sides; `THICK, housing, 2` lists every wall thinner than 2.
`MINWALL(housing)` gives the thinnest in an expression, so
`ASSERT, MINWALL(housing), GE, 2` keeps a part printable or castable. The
measurement samples 25 points per face, so a thin spot smaller than that
spacing can be missed.

### CONTACT and CLEARANCE: do the parts touch?

`CONTACT, a, b` says how two solid bodies meet:

```
bodies 5 (plate) and 6 (block) touch on faces, area 100 (faces [6] and [17])
bodies 5 (plate) and 9 (roller) touch along a line, length 30 (faces [6] and [31])
bodies 10 (ball) and 5 (plate) touch at a point (85, 20, 10) (faces [34] and [6])
bodies 5 (plate) and 8 (lid) are apart: gap 2 from (70, 70, 10) to (70, 70, 12) (faces [6] and [25])
bodies 5 (plate) and 7 (peg) OVERLAP: 500 in common (33.33% of the smaller), overlap box (10, 10, 5) ...
```

Closer than a tolerance counts as touching: a millionth of the parts' size
by default, or give one (`CONTACT, a, b, 0.01`). A body buried completely
inside another is an overlap too. `CONTACT, bolt` checks one body against
every other shown body. `CONTACT` alone checks every pair of shown solid
bodies and adds the **groups** of bodies that hold together through
contacts and the bodies that touch nothing (a bolt floating above its
washer, a part placed in the wrong spot). `CONTACT, , , 0, 0.5` also lists
the pairs that are less than 0.5 apart, which is where a part meant to sit
on another usually turns out to be. `FMT JSON` (fifth argument) gives the
answer as JSON.

`CLEARANCE, bolt, plate` finds every round shaft of one body inside a round hole
of the other and gives both diameters, the clearance (negative for an
interference fit), how far the axes are apart and how long the shaft is
engaged:

```
shaft d 9.6 of body 12 in hole d 10 of body 5: clearance, clearance 0.4 (0.2 a side), engaged 10
```

Threads and part cylinders (fillets, slots) are not counted as shafts or
holes. All of it is in expressions, so a script can keep its own checks:

```
ASSERT, TOUCH(bolt, washer)                 ! touch without overlapping
ASSERT, OVERLAP(bolt, nut), EQ, 0           ! no clash (the volume in common)
ASSERT, CONTACTAREA(foot, floor), GE, 100   ! sits flat, not on an edge
ASSERT, GROUPS(), EQ, 1                     ! every shown part is connected
ASSERT, CLEARANCE(pin, plate), GE, 0.05        ! the tightest gap of the pin in its hole
```

### The same, for the AI assistant

`modeler/ai/tools.py` wraps these (and a sandbox to try scripts in) as a
fixed list of tools that take and give JSON. They can be tried from a
shell:

```
python -m modeler tools                                  # the tool list
python -m modeler tool --script scripts/flange.cmd describe_body '{"body": "flange"}'
python -m modeler tool --script scripts/flange.cmd -  < calls.txt   # one "name {json}" per line
```

The sandbox is a copy of the model: `run` executes a script there step by
step and reports what each step changed, `check` tests a list of `ASSERT`
expectations, `diff` and `sandbox_script` show what was added. `vary`
re-runs the history with other values of a parameter and reports which
values break a step or a check (it found that the flange's check for
symmetry about YZ fails with 3 bolts; about ZX it holds for any number).
`round_trip` makes history edits, edits them back, and checks that every
ID, volume, the selection and named sets came back. Nothing in
the sandbox reaches the real model; commands that read or write files are
refused there.

## 24. NURBS freeform: control points, networks, patches and sewing

A NURBS curve or surface is shaped by **control points**: the shape starts
and ends on the end points and is pulled towards the others like a magnet
pulls a thread. Each point has a **weight** (how hard it pulls, normally 1),
and the **degree** says how smooth the joins are (1 straight pieces, 3 the
usual smooth curve). Every edit below is a history entry, so it re-runs when
an earlier step changes.

### Curves

```
NURBS, 3, (0,0,0), (10,8,0), (20,-8,0), (30,0,0)       ! degree 3, four control points
NURBS, 2, (10,0,0), (10,10,0,0.70710678), (0,10,0)     ! a fourth number is the weight: an exact quarter circle
NURBS, 3, (10,0,0), (0,10,0), (-10,0,0), (0,-10,0), CLOSE   ! a smooth closed loop
```

With fewer points than the degree needs, the degree is lowered (with a
warning). `SPLINE` is still the way to draw a curve *through* points.

### Editing control points

| Command | What it does |
|---|---|
| `MOVEPT, c, 2, 0, 5, 0` | move control point 2 by (0, 5, 0); add `TO` to move it *to* that point |
| `MOVEPT, s, (2, 3), 0, 0, 4` | on a surface a point is `(row, point in the row)` |
| `WEIGHT, c, 2, 3` | set a point's weight (more pulls harder) |
| `KNOT, c, 0.5` | add control points at 0.5 along the curve without changing its shape (`KNOT, s, 0.5, V` on a surface) |
| `DEGREE, c, 5` | raise the degree, shape unchanged (`U`, `V` or `BOTH` on a surface) |
| `REBUILD, c, 8` | remake as one smooth curve of 8 control points (a polyline or chain of curves becomes one curve; says how far it moved) |
| `REBUILD, s, 6, 3, 5` | a surface with 6 x 5 control points, degree 3 |
| `POLES, c` | list the control points and weights with their numbers |

Lines, arcs, circles and untrimmed faces (a block's side, a cylinder) are
turned into their exact NURBS first, so they can be edited too. A face
trimmed by other curves (a `FILL` patch, a face with a hole) cannot have its
points moved, because it would tear away from its edges: `REBUILD` it or
edit the curves it came from. An edit keeps the body's ID and, while it has
as many faces, edges and vertices as before, their IDs too.

In expressions, `POLE(c, 2)` is a control point of a curve,
`POLE(s, 2, 3)` one of a surface, and `NPOLES(c)` / `NPOLES(s, "V")` count
them.

**In the view:** pick a curve or surface and press **Control points** on
the Features toolbar (or type `CPOINTS, body`). The control points and the
lines joining them appear; drag one and a preview follows the mouse, in the
plane through the point that faces you. Letting go runs `MOVEPT` with the
distance moved. Esc during a drag cancels it; press the button again (or
`CPOINTS, OFF`) to hide the points.

### Surfaces

```
NSURF, 3, r1, r2, r3, r4                  ! the curves' control points are the rows of the surface's net
NETWORK, u1, u2, u3, ACROSS, v1, v2, v3   ! a surface through every curve of a network
FILL, G0, c1, c2, c3, c4                  ! a patch inside a closed loop of curves
FILL, G2, SEL                             ! ... meeting the surfaces whose edges are picked
FILL, G1, SEL, c5, THROUGH, (10, 10, 6)   ! also passing through a point (or curves) inside
SEW, top, bottom, side                    ! surfaces that meet become one skin; a closed skin becomes a solid
```

- `NSURF` uses the control points of each curve as one row, so the surface
  is pulled towards the middle rows rather than passing through them (that
  is what `LOFT, ..., SURFACE` does). Rows with different point counts or
  degrees are matched first without changing them.
- `NETWORK` needs every curve of one set to meet every curve of the other,
  in order across them. Curves drawn the wrong way round are turned. The
  surface runs from the first to the last curve of each set.
- `FILL` takes curve bodies, or `SEL` for the picked edges of open
  surfaces. Along a picked edge the patch flows on from that surface: `G1`
  without a crease, `G2` with matching curvature too; the result says how
  closely it met them. Along a curve body the patch only touches (`G0`).
- `SEW` uses up the surfaces. Edges closer than about 1/10000 of the
  model's size are joined. If any edge is left free the result is an open
  skin and the warning says how many edges are free.

### Blends, extending and trimming

```
BLEND, G2                          ! pick an edge of each of two surfaces first
BLEND, G1, 12, 31, 1.5             ! by edge IDs; 1.5 makes it fuller (default 1)
EXTEND, s, 5                       ! carry s on by 5 past its picked edge (or U0, U1, V0, V1, ALL)
TRIM, s, c, 10, 5, 0               ! cut s with curve c and remove the piece nearest (10, 5, 0)
TRIM, s, c, 10, 5, 0, KEEP         ! ... or keep only that piece
OFFSET, s, 2                       ! a surface moved 2 along its normal (the same OFFSET as for solids)
```

- `BLEND` makes a new surface across the gap between two edges. `G1`
  leaves no crease where it meets each surface; `G2` also matches their
  curvature, so reflections run on without a kink. The result says how
  closely it met them (in degrees). The two surfaces stay as they are;
  `SEW` them with the blend for one skin. Two closed loops (the top edge
  of a side wall and the rim of a lid) give a blend all the way round: it
  runs on smoothly across its own seam, which closes exactly, wherever
  each loop starts and whichever way round it runs.
- `EXTEND` carries a surface on the way it was going at that edge (its last
  span continued) and keeps the body's ID. `POLES` and where an edge lies
  tell which side is `U0`; picking the edge is easier.
- `TRIM` lays the curve onto the surface along the surface's normal. The
  curve must cross the surface from edge to edge, or close into a loop on
  it (that cuts a hole when the inside is removed). A trimmed face can no
  longer have its control points moved (see above).

### Laying a curve on a surface

```
PROJECT, c, dome                   ! along the dome's normal, as a new curve
PROJECT, c, dome, 0, 0, -1         ! straight down onto it
```

`PROJECT` keeps the original curve and adds the one on the surface. It is
a path for `SWEEP ... NORMAL`, or a cutting curve for `TRIM`. If the curve
lands in several separate pieces it says so (the body is then not one path).
`CURVEPT(c, t)` and `CURVETAN(c, t)` give the point and the direction of a
curve at `t` (0 at the start, 1 at the end), handy to place a profile where
a path starts.

### Analysis: zebra stripes, curvature and draft

```
ANALYZE, b                         ! zebra stripes, and every join between faces judged
ANALYZE, b, CURVATURE              ! mean curvature map (red bulges out, blue is hollow)
ANALYZE, b, GAUSS                  ! Gaussian curvature: dome, saddle, or bent one way only
ANALYZE, b, DRAFT, 0, 0, 1, 2      ! pull along +Z, at least 2 degrees of draft
ANALYZE, OFF                       ! back to the plain view
```

Each one colours the body in the view (in place of its usual shading) and
answers in words, so a script or the assistant can check a shape without a
picture. `ANALYZE` only looks: it is not a history step.

- `ZEBRA` judges every edge between two faces at a few points along it:
  *creased* if the faces meet at an angle (more than 0.25 degrees), *G1*
  (tangent only) if they meet smoothly but the curvature across the edge
  jumps by more than a tenth, *G2* if the curvature runs on too (a bend
  wider than 100 times the body's size counts as flat). It lists
  the edges in each group. The stripes show the same: they break at a
  crease, kink at a G1 join and flow straight on over G2. The stripes are
  lit from where the view looks from when the command runs (or give a
  direction).
- `CURVATURE` gives the range of mean curvature, how much of the area is
  flat, and the tightest bend (its radius and where). `GAUSS` tells dome-like
  areas (both directions curve the same way), saddles, and areas bent one way
  only (cylinders, cones, flat).
- `DRAFT`: green comes out of the mould towards the pull direction, blue
  towards the other side, red is steeper than the angle allows. The answer
  gives the share of the area of each and lists the faces with red on them.

The **Zebra** button (Features toolbar) shows stripes on the picked body and
ends them when pressed again; the form (Freeform category) has the others.

### Deformers: bend, twist, taper, stretch, and flow along a curve

```
BEND, bar, 90                      ! the bar's centre line becomes a quarter circle
BEND, bar, 90, X, -Z               ! along X, bending downwards
BEND, hook, 150, X, Z, t**2        ! more of the bend towards the far end
TWIST, column, 180                 ! the far end turns half a turn about the middle
TWIST, bar, 60, Z, sin(180*t)      ! out and back: both ends stay square
TAPER, column, 0.4                 ! the far end shrinks to 0.4 of its size
STRETCH, plug, 2                   ! twice as long, thinner, same volume
STRETCH, plug, 2, X, FREE          ! twice as long, same cross-section
FLOW, label, arc, FIT              ! lay a text along a curve, fitted to its length
FLOW, label, arc, X, 12            ! from 12 along the curve, at its own length
```

Each one changes the body in place: it keeps its ID and name, and its
faces, edges and vertices keep theirs, so later steps that pick them still
work. The axis is the length that changes (X, Y or Z; by default the body's
longest side), measured over the body's bounding box: `t` runs from 0 at
its low end to 1 at its high end.

- `BEND` turns the centre line through the angle while keeping its length
  (the inner side is squeezed, the outer stretched). The bend goes towards
  `+Z`, or the side you give (`X`, `-Y` ...; `+X` for an axis Z). Less than
  360 degrees.
- `TWIST` and `TAPER` work about the axis through the middle of the body's
  cross-section; `TAPER` scales both sides of the cross-section (above 0).
- The optional law says how much of the bend, turn or size change is done
  by `t`: plain `t` (the default) is even, `t**2` gathers it towards the
  far end, `sin(180*t)` goes out and comes back.
- `STRETCH` keeps the start where it is. `KEEP` (the default) makes the
  sides thinner by the square root of the factor, so the volume stays;
  `FREE` changes only the length.
- `FLOW` lays the body's length along a curve from the curve's start; its
  cross-section turns with the curve as a `SWEEP` profile would (its up
  side, `+Z` or `+X` for an axis Z, stays on the curve's up side;
  `MINTWIST`, `FRENET` or `FIXED` as for `SWEEP`). Without `FIT` a body
  longer than the curve is refused.

How it works: the body is turned into NURBS, each face is refined until the
deformed shape is fitted within 1/10000 of the body's size, and the message
says how close it is. A body read from a mesh file is moved point by
point instead (the message says "as a mesh"). Planes and cylinders become
freeform faces, so a deformed block reports `bspline` faces.

### SWEEPVOL: the volume a moving tool sweeps

```
SWEEPVOL, cutter, track            ! a new body: what the cutter passes through
SUBTRACT, plate, LAST              ! cut it away
```

The tool moves along the curve without turning, from where it stands (the
curve's start is taken as the tool's start). The result is exact for a
ball (a round pipe with the ball at each end) and for a cylinder moving
square to its axis, such as an end mill along a path across it (its
rectangular section swept upright, with the cylinder at each end). Any
other tool is copied closely along the path and the copies are joined; the
message gives how many copies and how high the ridges between them can be.

Example: `scripts/mouse.cmd` (the M5 exit test: a computer mouse whose
side wall and humped top are joined by a G2 blend all round, sewn into a
solid, shelled to 2 mm with the bottom open, with a button split, a scroll
wheel and a name flowed along a curve laid on the top).

Example: `scripts/deformers.cmd` (a bar bent into a quarter circle and a
hook bent more at its end; a square column twisted and tapered, and one
twisted out and back; a block stretched to twice its length; the word FLOW
laid along an arc; a slot milled along a curve with `SWEEPVOL`).

Example: `scripts/guides_analysis.cmd` (a vase lofted through three sections
along two guide curves; a rib swept along a wavy line on a domed panel,
staying square to it; zebra stripes on the vase).

Example: `scripts/surface_ops.cmd` (two panels joined by a G2 blend and sewn
into one skin; a panel extended and trimmed with a round hole; a block
whose top takes the shape of a wavy surface and whose side is moved in).

Example: `scripts/nurbs_freeform.cmd` (a dome through a network of curves,
closed with a flat patch and sewn into a solid; an edited curve; a surface
from rows of control points with one point pulled up).
