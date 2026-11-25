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
| `FAILED()`, `STEPS("FILLET")` | how many history steps fail now; how many steps run a command (all steps with no name) |
| `SKETCHED("s")`, `SKETCHED("s", "circle")` | how many lines, circles, arcs ... sketch `s` holds (0 when there is no such sketch) |
| `HOLES(b)`, `HOLES(b, d)`, `HOLES(b, d, 1)` | round holes in the body: all, of diameter `d`, and only through (1) or only blind (0) holes; section 23 |
| `SYMMETRIC(b, "YZ")` | 1 if the body is its own mirror image in the plane (a base plane or a datum plane) |
| `MINWALL(b)` | the thinnest wall of a solid (see `THICK`, section 23) |
| `MASS(b)` | mass in kg, from the body's `MATERIAL` (an error when it has none) |
| `SAFETY(b, "fixed", "loaded", fx, fy, fz [, h])` | the `STRESS` safety factor with those named sets and that force in N (h: mesh size); `MAXSTRESS(...)` gives the largest stress in MPa and `DEFLECT(...)` the largest movement in mm |
| `OVERHANGS(b [, angle [, up]])` | overhanging area that `PRINTCHECK` finds (default 45 degrees, up `+Z`) |
| `FLOATING([ground, fastened])`, `TIPANGLE([ground, fastened])` | how many parts `GRAVITY` finds floating or tipping, and the smallest tip angle in degrees |
| `QTY("name")` | how many of a part the `BOM` counts |

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
| `UNDO [, n]`, `REDO [, n]` | take back the last n actions, or do them again: new steps, history edits (`HIST, EDIT`, `INSERT`, `DELETE`, `SUPPRESS`, `MOVE`, `PART`) and roll backs alike; parameters and macros come back too |
| `HIST` | list the history (`x` failed, `!` ran with a warning, `-` suppressed) |
| `HIST, EDIT, n, "text"` | replace entry n and re-run from there; `\n` separates lines of a block |
| `HIST, INSERT, n, "text"` | add an entry before n |
| `HIST, DELETE, n` | remove entry n |
| `HIST, SUPPRESS, n` / `HIST, RESUME, n` | skip entry n / take it back |
| `HIST, MOVE, n, to` | reorder |
| `HIST, ROLLBACK, n` | show the model as after entry n; the later entries stay, greyed, and `REDO` (or a roll back further on) brings them back; one `UNDO` step |
| `HIST, REPLAY` | re-run every entry (no skipping) |
| `RUN, file.cmd` | run a script; each top-level statement becomes an entry |

After an edit, later entries that now fail stay in the history marked as
failed (red in the History panel) and are skipped, so you can fix them.

**Only what changed runs again.** While an entry runs, the modeler notes
what it looks at: which parameters, which bodies, faces and edges (by ID),
and the rest of the model's state (selection, named sets, datums, sketches,
layers). When an edit re-runs the history, a later entry whose inputs are
all exactly as they were last time is not run again; what it did last time
is copied over. The rebuild message counts them: `re-ran 3 entries from 1
(6 unchanged, reused)`. So changing the size of one part of an assembly
re-runs that part's steps and the steps that use it, not the slow thread or
fillet on another part. An entry that looks at every body (`SEL, ALL`,
`VOL()` of a name that changed), reads a file (`IMPORT`, `LIB`), or reads an
older state (`PATTERN`) always runs again. `HIST, REPLAY` runs everything.

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
SEL, S, EDGE, LOOP, 7 [, face]             ! the edges round the face edge 7 is on (default: the flat face with the longer outline)
SEL, S, EDGE, CHAIN, 7 [, deg]             ! edges joined to 7 without a corner (tangent within deg, default 5)
SEL, S, FACE, TANGENT, 3 [, deg]           ! face 3 and every face that meets it smoothly, and so on
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
* **Look-alikes are told apart by how they were made.** When several
  entities fit, the one on the same body wins, then the one made by the same
  step, then the one made from the same entity. A face that got a new ID
  remembers what it was made from: a fillet face the edge it rounds, the
  smaller piece of a split face the face it was split from, a new edge the
  face a boolean cut it into. So when a size changed upstream and nothing
  has the old shape any more, a pick on a fillet face still finds "the face
  this fillet step made from that edge", if there is exactly one.
* **Merged faces** keep the older ID (the one from the first body of the
  step), and a split face keeps its ID on its largest piece.

`SEL` by IDs (`SEL, S, FACE, ID, 5, 6`) is kept the same way: each entity
it picked is remembered, and found again when its ID moves. When the range
itself changes (`SEL, S, FACE, ID, N` with a new `N`), it starts afresh.

**`REFS`** lists every pick the history holds and its state: `ok`,
`repaired` (its ID changed and it was found again; the reason is shown) or
`broken` (it could not be found, so its step failed). `REFS, PROBLEMS`
shows only the repaired and broken ones, `REFS, ALL, JSON` the same as data.

**Picking a step again.** In the window, right-click a pick step in the
History and choose **Pick again…**: the model goes back to just before that
step, clicks in the view only select (they add no steps), and **Use the
picked faces for step n** rewrites the step and runs the rest again. The
same as a command: `HIST, REPICK, 4, "FACE, 12"` (IDs as they are just
before step 4; several IDs give one pick step each). `UNDO` takes it back.

A plain script (Save log) holds only the text, so it does not carry these
IDs. In scripts you write to keep, select by geometry or by name.

## 7. Commands

| Group | Commands |
|-------|----------|
| Primitives | `BLOCK, x,y,z, dx,dy,dz` · `CYL, x,y,z, r, h [, dx,dy,dz] [, angle]` · `TUBE, x,y,z, ro, ri, h [, axis]` · `CONE, x,y,z, r1, r2, h [, axis]` · `SPHERE, x,y,z, r` · `TORUS, x,y,z, ring_r, tube_r [, axis]` · `WEDGE, x,y,z, dx,dy,dz, ltx` |
| Booleans | `UNION, a, b [, c ...]` · `SUBTRACT, a, b [, c ...]` · `INTERSECT, a, b [, c ...]` (IDs or names; the result keeps the first body's name; `SEL` in place of the tools means every selected body) · `KEEP, ON/OFF` (keep the inputs as hidden bodies; tools keep their names) |
| Patterns | `ARRAY, LINEAR, b, n, dx,dy,dz [, n2, dx2,dy2,dz2]` · `ARRAY, POLAR, b, n [, angle [, x,y,z [, dx,dy,dz]]]` · `ARRAY, PATH, b, path, n [, twist_law [, scale_law]] [, MINTWIST/FRENET/FIXED]`; add `FUSE` to fuse the copies into the original, or `CUT, target` to cut them all from another body in one step · `PATTERN, LINEAR/POLAR, b, steps, n, ...` repeats a feature (section 21) |
| Blends | `FILLET, r [, r2]` · `CHAMFER, d [, d2]` (on the selected edges, or all edges of the selected bodies; `r2`: the radius grows from r to r2 along each edge; `d2`: d on one face and d2 on the other) |
| Check and repair | `CHECK [, b [, SELF / FLAWS [, tolerance [, JSON]]]]` · `HEAL, b [, tolerance]` · `CLEAN, b` (section 12) · `REFS [, PROBLEMS]` (section 6) · `SCHECK [, sketch]` (section 16) |
| Datums | `PLANE, name, how, ...` · `AXIS, name, how, ...` · `POINT, name, how, ...` · `DATUM, DELETE, name` · `WORKPLANE, plane/OFF` (section 13) |
| Sketches | `SKETCH, name [, plane / FACE, id]` · `ENDSKETCH` · `SLINE` · `SPOLY` · `SRECT` · `SRECTC` · `SRECT3` · `SCIRCLE` · `SCIRCLE3` · `SARC` · `SARC3` · `SARCT` · `SSLOT` · `SSLOTARC` · `SNGON` · `SELLIPSE` · `SEARC` · `SCIRCLET` · `SSPLINE` · `SPOINT` · `SCON` · `SDIM` · `SDEL` · `SMOVE` · `SCONSTRUCT` · `SSEL` · `STRIM` · `SEXTEND` · `SFILLET` · `SCHAMFER` · `SSPLIT` · `SCORNER` · `SOFFSET` · `SOFFSET2` · `SINTERSECT` · `SJOIN` · `SMIRROR` · `SPATTERN` · `STRANSFORM` · `SPROJECT` (section 16) |
| Sketch features | `EXTRUDE, sketch, d [, NEW/ADD/CUT [, b [, back]]]` · `REVOLVE, sketch, axis [, angle [, NEW/ADD/CUT [, b]]]` (section 16) |
| Part features | `HOLE, b, x,y,z, d [, depth, kind, d2, h2, tip, dx,dy,dz]` · `SPLIT, b, plane/body [, BOTH/ABOVE/BELOW]` · `SHELL, t [, IN/OUT]` · `DRAFT, angle [, plane [, dx,dy,dz]]` · `OFFSET, b, d [, ROUND/SHARP]` (section 14) |
| Parts | `*PART, name, P=default, ...` ... `*ENDPART` · `INST, part, x,y,z [, angle [, dx,dy,dz]] [, P=value ...]` · `EXPLODE, b` · `XSTEP, view, bodies, dx,dy,dz` · `XSHOW, view [, factor, trails]` (exploded views, section 35) · `MATE, kind, item, item [, value] [, FLIP]` · `MATE, FRAME, a, b [, FLIP]` · `MATES [, JSON]` · `CSYS, name, body, x,y,z [, nx,ny,nz [, angle]]` · `LIB, LINK, name/file` · `LIB, LOAD, name/file` · `RELOAD` · `LIBSAVE, part [, file]` · `LIST, PARTS` · `TAKE, what, part, n, name [, LINK/COPY]` · `DEPENDS [, JSON]` · `HIST, PART, first, "last, name"` (section 17) |
| Measure | `DIST` · `ANGLE` · `MASSPROP [, b [, density]]` · `CLASH [, a, b]` · `SECTION, plane/OFF [, BELOW/ABOVE, offset, NEW/ADD]` (sections 15, 44) |
| Transforms | `MOVE, b, dx,dy,dz` · `ROTATE, b, angle [, x,y,z [, dx,dy,dz]]` · `SCALE, b, f [, x,y,z [, fy, fz]]` · `COPY, b, dx,dy,dz` · `MIRROR, b [, x,y,z [, nx,ny,nz [, copy]]]` |
| Standard parts | `GEAR, x,y,z, module, teeth, width [, EXTERNAL/INTERNAL/RACK, helix, rim, pressure, dx,dy,dz]` · `FASTENER, CAP/HEXBOLT/NUT/WASHER, M8, x,y,z [, length, PLAIN/REAL, dx,dy,dz]` (section 41) |
| Moulds, welds, notes | `PARTING, b [, dx,dy,dz, draft]` · `MOLD, b [, wall, shrink, dx,dy,dz, level]` · `WELD, a, b [, size]` · `WELD, ALL [, size]` · `NOTE, "text", x,y,z [, x,y,z]` · `NOTE, SIZE, p1, p2` · `NOTE, HOLE` · `NOTE, FIT, H7` · `NOTE, DELETE, n` · `NOTE, CLEAR` · `FITS, H7/g6 [, size]` (section 43) |
| Cams, traced paths, sketches from files, topology | `CAM, x,y,z, law, base, roller, width [, DISC/BARREL, bore]` · `CAMLIFT(law, A)` · `GEAR, ..., BEVEL/WORM/WORMWHEEL` · `TRACE, name, from, to, steps, body, x,y,z` · `SDXF, file [, scale, du, dv, layer]` · `STRACE, file, width [, threshold, du, dv, SPLINE/LINES]` · `IMAGE, file, plane, width` · `TOPOPT, b, fixed, loaded, FORCE, fx,fy,fz, share` (section 45) |
| Sections, tolerances, pipes | `SECTION, plane, side, offset [, ADD]` · `STACKUP, +100 ±0.1, -60 +0/-0.05, ... [, MIN=a, MAX=b]` · `NOTE, DATUM, A` · `NOTE, GDT, kind, tol [, A, B, C]` · `ROUTE, path, PIPE/CABLE, size [, radius, name]` · `ROUTES [, file.csv]` (section 44) |
| Plastic parts | `BOSS, b, x,y,z, h, od [, hole, ribs, depth, dx,dy,dz]` · `SNAP, b, x,y,z, length, width, thickness [, overhang, up, hook direction, lead, catch]` · `VENT, count, length, width [, pitch, angle, depth, u, v]` (section 42) |
| Paths | `LINE, p1, p2` · `ARC, p1, p2, p3` · `POLYLINE, p1, p2, ... [, CLOSE]` · `SPLINE, p1, p2, ... [, CLOSE]` · `HELIX, x,y,z, r, pitch, turns [, axis] [, taper] [, RIGHT/LEFT] [, pitch_law]` · `CURVE, PARAM, x(t), y(t), z(t) [, t0, t1, n]` |
| Profiles | `CIRCLE, x,y,z, r` · `ELLIPSE, x,y,z, a, b` · `RECT, x,y,z, w, h [, r]` · `POLYGON, x,y,z, r, sides` · `STAR, x,y,z, ro, ri, points` · `SLOT, x,y,z, length, width` · `AIRFOIL, x,y,z, chord, code`, each followed by `[, nx,ny,nz [, angle]]` (section 9) |
| Shapes on curves | `LOFT, s1, s2, ... [, RULED] [, CLOSED] [, SURFACE] [, GUIDE, g1, g2, ...]` · `SPINELOFT, spine, s1, s2, ... [, FRENET/FIXED] [, SURFACE]` (section 20) · `SWEEP, profile, path [, twist, scale, mode, sx, sy, ox, oy, n, solid, on]` · `MORPH, path, twist, scale, mode, s1, s2, ...` · `RAILSWEEP, profile, rail1 [, rail2] ...` (section 19) · `PIPE, path, r [, ri, radius_law, mode]` (section 9) |
| Threads and springs | `THREAD [, pitch] [, length] [, hand]` · `SPRING, x,y,z, r, pitch, turns, d ...` (section 18) |
| Text and surfaces | `TEXT, text, x,y,z, size [, depth] [, nx,ny,nz [, angle]] [, LEFT/CENTER/RIGHT] [, font] [, style]` · `SURFACE, PARAM, x(u,v), y(u,v), z(u,v), u0, u1, v0, v1 [, nu, nv] [, thick]` (section 20) |
| Edit faces | `PUSHPULL, d` · `DELFACE` (on the selected faces, section 20) |
| Bodies | `NAME, b, name` · `DELETE, b` · `CLEAR` · `HIDE, b` · `SHOW [, b]` · `ISOLATE [, b/SEL/layer]` |
| Layers and looks | `LAYER, name [, CURRENT/NEW/ON/OFF/LOCK/UNLOCK/COLOR/ADD/RENAME/DELETE [, value]]` · `COLOR, b/SEL/ALL, colour` · `MATERIAL, b/SEL/ALL, name [, density [, colour]]` (section 22) |
| Selection | `PICK, kind, id [, S/A/U]` (several: `PICK, FACE, 3 5 7`) · `SEL ...` · `CM` · `CMSEL` · `CMDEL` · `PICKMODE, AUTO/BODY/FACE/EDGE/VERTEX` · `PICKREGION, BOX/LASSO/OFF` · `TOOLS [, JSON]` (section 46) |
| Previews | `PREVIEW, "step"` · `PREVIEW, OFF` (section 46) |
| Settings | `/UNITS, MM/CM/M/IN` · `/TOL, value` (fuzzy booleans and selection tolerance) |
| Pictures | `RENDER, file.png [, width, height, view, frames, ON/OFF]` (a ray-traced picture or a turntable, section 40) |
| Files | `EXPORT, STEP/IGES/BREP/STL/OBJ/3MF/GLTF, file [, body]` · `DRAWING, file.pdf/.svg/.dxf [, views, body, sizes, sheet, scale, section, detail]` · `DRAWSHEET, name, views [, body, sizes, paper, scale, section, detail, template]` · `DRAWINGS [, file [, AUTO/OFF]]` · `PROPERTY, key, value` · `BACKUPS [, n]` · `FILES` · `RELINK, name, file` · `SHARECHECK` · `IMPORT, STEP/IGES/BREP/STL/OBJ/3MF/GLTF/PLY/OFF/VTK/MESH, file [, name [, AUTO/SOLID/MESH]]` (section 10) · `RUN, file` |
| Mesh bodies | `TOMESH, b [, deflection]` · `TOSOLID, b` · `SMOOTH, b [, steps [, strength]]` · `REMESH, b, length` · `SIMPLIFY, b, tolerance` · `FITSURF, b [, region, tol, trim]` (smooth NURBS from a mesh, section 29) · `SEGMENT, b [, angle, tol]` · `RECONSTRUCT, b [, angle, tol]` (exact planes, cylinders and spheres from a scan, section 34); `UNION`, `SUBTRACT` and `INTERSECT` with a mesh body run on triangles (section 25) |
| Frames | `MEMBER, path, profile, size [, MITRE/BUTT, name, turn]` · `CUTLIST [, file.csv]` (structural members and the cut list, section 36) |
| Strength | `STRESS, b, fixed, loaded [, FORCE/PRESSURE, fx, fy, fz, h]` (a first strength check, section 37) |
| Gravity | `GRAVITY [, ground, fastened, dx, dy, dz, gap]` · `GRAVITY, OFF` (does the assembly stand up, section 39) |
| Making | `PRINTCHECK, b [, up/BEST, angle, wall]` · `MILL, b, FACE/POCKET/OUTLINE, faces [, tool, down, over, file.nc, feed, speed]` · `MILL, OFF` (3D printing checks and milling paths, section 38) |
| Knife | `KNIFE, b, stroke [, width [, dx,dy,dz]]`: cut along a curve seen from a direction (section 27) |
| Implicit and lattices | `IMPLICIT, name, f(x,y,z), x0,y0,z0, x1,y1,z1 [, step]` · `LATTICE, b, GYROID/SCHWARZ/DIAMOND/CUBIC/BCC/OCTET, cell, thickness [, skin [, step]]` (section 26) |
| Projects | `SAVE [, file.m3d]` · `OPEN, file.m3d` · `OPEN, AUTOSAVE` · `NEW` (section 10) |
| History | `UNDO` · `REDO` · `HIST ...` |
| View & info | `VIEW, ISO/TOP/TOP FRONT/...` · `VIEW, TURN, LEFT/RIGHT/UP/DOWN/CW/CCW` · `VIEW, HOME` · `FIT` · `LAYOUT [, name/SAVE/RESET]` · `TUTORIAL [, name/NEXT/...]` · `LIST [, BODIES/PARAMS/MACROS/SETS/DATUMS/SKETCHES/SKETCH/LAYERS/MATERIALS]` · `ECHO, expr` · `HELP [, name]` |
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
body; the first one gets the name. A STEP file's part names and colours come
along: each part keeps its name (made into one commands can use, so
"Pin 4 (M3)" becomes `Pin_4_M3`, with a number added when the name is taken)
and its colour. Parts placed several times in an assembly come in once per
place. `EXPORT, STEP` writes each body's name and colour the same way.
Faces left loose in the file, with no name, come in together as one body.

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
faceted body. A bigger file becomes a **mesh body** instead (section 25),
and so does any file imported with the kind `MESH`:
`IMPORT, STL, "scan.stl", scan, MESH`. `SOLID` asks for a faceted body
whatever the size (up to the limit), and `AUTO` (the default) picks.

`EXPORT` writes STEP, IGES or BREP (exact) or STL, OBJ, 3MF or GLTF
(triangles, 0.1 mm fine). OBJ, 3MF and glTF keep one object per body with
its name and colour; 3MF records the model's units; glTF is written in
metres with Y up, as viewers expect, as a binary `.glb` or a single
`.gltf` file.

### DRAWING: 2D drawings as PDF, SVG or DXF

```
DRAWING, "flange.dxf"                  ! front, top, right and iso views
DRAWING, "flange.svg", TOP+FRONT       ! just these views
DRAWING, "bolt.svg", ISO, bolt         ! one body
DRAWING, "plate.dxf", TOP, 0, HOLES    ! only the hole diameters (0: all shown bodies)
```

`DRAWING, file [, views] [, body] [, sizes]` writes the shown bodies (or one body)
as a flat drawing at true size: one drawing unit is one model unit, so a
DXF opens in any CAD program at the right size. `STANDARD` (the default)
puts the front view at the bottom left, the top view above it, the right
view beside it and an isometric view in the free corner; or name views
joined with `+`: `TOP`, `FRONT`, `RIGHT`, `LEFT`, `BACK`, `BOTTOM`, `ISO`.
Visible edges and outlines are solid, hidden ones dashed (DXF layers
`VISIBLE`, `HIDDEN`, `TEXT` and `DIMS`, with a `HIDDEN` line type); edges where
faces meet smoothly, such as a fillet's, are left out. Mesh bodies are
drawn from their triangles. The file type comes from the extension
(`.svg` or `.dxf`). Like `EXPORT` it runs when given and is not kept in the
history. **File > Export drawing…** (Ctrl+Shift+E) does the same.

**Sizes.** `sizes` is `ALL` (the default), `OVERALL`, `HOLES` or `NONE`.
The overall width, depth and height are each written once, outside the first
flat view that shows them: on the standard sheet, width and height on the
front view and depth on the top view. They are the exact sizes of the
bodies, not of the drawn lines. Every whole circle seen face-on (a hole, a
boss, a round outline) gets a diameter with a short leader; equal ones in a
view are counted, as `6x Ø8`, and each diameter is written once on the
sheet. In SVG the sizes are blue, in groups `front-dims`, `top-dims` and so
on; in DXF they are lines, filled arrows and text on layer `DIMS`. The
isometric view gets no sizes.

**Sheets, sections and details.**

```
PROPERTY, TITLE, Mounting bracket          ! the title block's fields
PROPERTY, NUMBER, MB-001
PROPERTY, AUTHOR, S. Singh
DRAWING, "bracket.pdf"                     ! on paper: A4 or A3, the scale that fits
DRAWING, "bracket.pdf", , , ALL, A3, 1:2   ! A3 at 1:2
DRAWING, "bracket.pdf", , , ALL, , , "X 20"            ! and a section through x = 20
DRAWING, "bracket.pdf", , , ALL, , , , "FRONT 30 0 12 6 3"  ! and a detail, 3 times bigger
DRAWING, "bracket.svg", , , ALL, A3        ! an SVG on paper too
```

A `.pdf` is always a sheet of paper. An `.svg` is one when `sheet` is given.
The paper is A4, A3, A2, A1 or A0 (landscape), or `AUTO`: A4 when the
drawing fits on it at full size or bigger, else A3. The scale is the largest
usual one that fits (10:1, 5:1, 2:1, 1:1, 1:2, 1:5, 1:10 ... 1:1000), unless
you give one. The sheet has a frame and a title block. The block holds the
title, number, revision, material, scale, units, paper, author, date, company
and the projection (third-angle). These come from `PROPERTY` values: the
title defaults to the body's name when there is one body, the material to
the bodies' materials, and the date to today. A DXF stays at true size,
without paper.

`section` cuts the part with a plane square to an axis, like `"X 20"` or
`"Y=25"` (several with `;` between). It shows what is left on the far side,
seen square-on, with the cut faces hatched at 45 degrees. X cuts are seen
from +X (as the right view), Y cuts from -Y (as the front view), and Z cuts
from +Z (as the top view). Each section is named `SECTION A-A`, `B-B` ...,
and a chain line with its letters marks where it was taken, on the first
view that shows the plane edge-on.

`detail` shows part of a flat view bigger. Give the view, a model point,
a radius and how many times bigger: `"FRONT 30 0 12 6 3"`. A circle and a
letter mark the place on that view, and the detail is named `DETAIL B (3:1)`.

`PROPERTY` with no values lists the properties. With a key and no value it
removes that one. Properties are kept in the project and follow undo.

### Drawings that follow the model: DRAWSHEET and DRAWINGS

`DRAWING` writes a file once. A **sheet** is kept with the model instead:
`DRAWSHEET, name, views [, body, sizes, paper, scale, section, detail,
template]` is a history step that says what the sheet shows (the same
choices as `DRAWING`), and its views are made from the model every time the
drawings are written, so they always show the model as it is:

```
DRAWSHEET, views, STANDARD                      ! sheet 1: the four views
DRAWSHEET, plan, TOP, 0, OVERALL, A3, 1:1       ! sheet 2: the top view on A3
DRAWSHEET, cut, FRONT, 0, NONE, A4, , "Y 10"    ! sheet 3: a section
DRAWINGS, "plate.pdf"                           ! one PDF, a page per sheet
DRAWINGS, "plate.pdf", AUTO                     ! ... and again after every rebuild and save
DRAWINGS                                        ! the sheets, and the sizes checked
```

`DRAWINGS, "plate.svg"` writes one SVG per sheet (`plate_views.svg`,
`plate_plan.svg` ...). The title block says which sheet it is ("SHEET 2 of
3"). With `AUTO` the file is written again after every rebuild and every
save, so it never shows an old model; `DRAWINGS, , OFF` stops that. The
setting is saved with the project. `DRAWSHEET, DELETE, name` removes a
sheet.

**Templates.** A title block of your own is a small text file:

```
! our title block
paper = A3                  ! the paper, when the sheet does not say
row = TITLE                 ! one field: shown big, without its label
row = NUMBER, REVISION      ! fields side by side, each with its label
row = MATERIAL, SCALE, SHEET
row = AUTHOR, COMPANY, DATE
COMPANY = Example Ltd       ! a value used when PROPERTY does not set it
```

Fields are `PROPERTY` names, and `SCALE`, `PAPER`, `UNITS`, `SHEET` and
`DATE` (today unless set). Give the file as the sheet's last value:
`DRAWSHEET, plan, TOP, 0, ALL, , , , , "company.tpl"`.

**Sizes checked against the model.** `DRAWINGS` also checks the sizes
pinned to the model with `NOTE`. A size between two points (`NOTE, SIZE`)
remembers what each end was on when it was made (a corner, an edge, a face);
when that changes (the part got longer, so the corner moved away from the
end) the size is out of date and is named. A diameter typed into a note
(`NOTE, "ø6", ...`) is checked against the hole next to it. Sizes made from
picks (`NOTE, SIZE` on picked vertices, `NOTE, HOLE`) are made again from
the model on every rebuild, so they always fit.

The app autosaves the project a moment after every change. When it starts
and finds the autosave of the last session, the **Recover** button appears;
it runs `OPEN, AUTOSAVE`. The autosave lives in the app's data folder; set
the environment variable `MODELER_AUTOSAVE` to another file, or to `off`.

### Keeping projects safe

**Saving.** A project is written next to its file first and put in place
only when it is complete, so a crash or a full disk while saving leaves the
last save as it was. Every `SAVE` over a project first keeps the one it
replaces in the folder `<name>-backups` next to it, named by when it was
saved; the newest 5 are kept. `BACKUPS` lists them, newest first, and
`BACKUPS, 10` keeps ten (`BACKUPS, 0` none); open one with `OPEN` to go
back to it. A project file that is damaged (cut short by a crash, say)
does not open, and the message names its newest backup. The autosave makes
no backups. Projects saved by every earlier release are opened by the
tests, and must give the same model.

**Outside files.** A project keeps a copy of every file it imports or
links, so it opens when they are gone; a linked part file (`LIB, LINK`) is
followed while it is there. `FILES` lists them: the step that reads each
one and where it was found, or that it is missing and the saved copy is
used. When a file moved, or a newer version of an imported file should be
used, point the project at it:

```
FILES                                          ! what the project reads, and from where
RELINK, "parts/peg.cmd", "D:/new/peg.cmd"      ! the file as the history names it, then where it is now
```

The steps that read it run again; the history keeps the old name, and the
next `SAVE` keeps a copy of the new file.

**Before sharing.** `SHARECHECK` lists what to fix before sending the
project to someone: changes since the last save, failing steps, missing
files the project has no copy of, broken links and parts that place each
other in a loop. It also says what goes with the file: steps with
warnings, part files linked from outside the project folder, the saved
assistant conversation, names in the title block, and full paths in your
own folders.

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

### Imported models: flaws and repairs

Files from other programs often bring small faults that a valid-or-not test
does not name. `CHECK, b, FLAWS [, tolerance]` lists them, face and edge by
face and edge (by the IDs `PICK` and `SEL` take), against a tolerance: flaws
smaller than it count as accidents of the file. Without one, a thousandth of
the body's size is used.

| Flaw | What it is | What `HEAL` does |
|------|------------|------------------|
| Open edges with a neighbour within the tolerance | faces that do not quite meet (a gap), or meet without being joined | sews them into one skin; a closed skin becomes a solid |
| Open edges with nothing near | a hole: a face is missing | nothing (a face cannot be invented); a larger tolerance or a patch (`SURFACE`) closes it |
| Loose faces | faces not joined into any skin | sews them in |
| Flipped faces | a face turned against its neighbours, or a solid inside out | turns them the right way |
| Duplicate faces | the same face twice | removes the copy |
| Tiny edges | edges shorter than the tolerance | merges them into their neighbours |
| Slivers | faces narrower than the tolerance (twice the area over the perimeter) | lists them; `DELFACE` removes one and lets its neighbours grow over it |

```text
CHECK, housing, FLAWS, 0.01        ! what is wrong, at a tolerance of 0.01
CHECK, housing, FLAWS, 0.01, JSON  ! the same as data
HEAL, housing, 0.01                ! repair, in turn, and say what was fixed and what is left
```

`HEAL` runs the repairs in the order of the table and keeps each one only
when it leaves fewer flaws than before. Its message lists what it fixed and,
under "left:", what is still there. `IMPORT` warns when an exact file gives a
body that is not a clean solid.

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
IDs where they survive. `HEAL` refuses, and changes nothing, when no repair
helps; when some help, it keeps them and lists the rest.

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
| `SECTION, plane [, BELOW/ABOVE, offset, NEW/ADD]` | cuts the view open along a plane to look inside, moved `offset` along its normal; the cut faces are capped red and hatched, and the area and centre of each cut are printed. `ADD` keeps the planes so far (up to three). `SECTION, OFF` closes it |

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
| `SSPLINE, p1, p2, ... [, CLOSE]` | a smooth curve through the points; `CLOSE` runs it back to the first point, smooth all round (the Freehand tool writes this) |
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
| `3.A` | the end of an ellipse's first axis (drag it to turn or stretch the ellipse) |
| `3.K1`, `3.K2` ... | the points a spline passes through between its ends (drag them with `SMOVE`, hold them with `SCON`) |
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
can be a parameter: `LENGTH`, `DIST` (two points, a point and a line, or a
point and an arc or circle: how far it is from the rim, outside or inside),
`HDIST`, `VDIST`, `RADIUS`, `DIAMETER`, `ANGLE` (degrees between two lines,
or from `H` with one line), `ARCLEN` (the length along an arc or
elliptical arc), and for an ellipse `MAJOR` (its first radius, from `n.C`
to `n.A`) and `MINOR` (its second radius, across).

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
| `STRIM, 3, u, v, AXES` | ... and the sketch's H and V axes cut too (half a profile for `REVOLVE`) |
| `SEXTEND, 3.E` | makes line or arc 3 longer at its end until it meets the next curve |
| `SEXTEND, 3.S, 5` | ... at its start, up to curve 5 (its full line or circle counts) |
| `SEXTEND, 3.E, V` | ... up to the vertical axis (`H`: the horizontal one) |
| `SFILLET, 1.E, 4` | rounds the corner where curve 1 ends and another curve meets it, radius 4: two lines, a line and an arc, or two arcs |
| `SFILLET, 1.E, 2.E, 3.E, 4` | several corners, one radius |
| `SOFFSET, 3, 1, 2, 3, 4` | curves 3 away from curves 1..4: lines, arcs, circles and splines; a chain meets again at its corners (a corner past a spline's end goes on straight from it). A closed chain that crosses itself (a figure eight) has no outside, so positive goes to the left walking along its lowest-numbered curve |
| `SMIRROR, V, 1, 2` | mirror copies of 1 and 2 about the vertical axis (or about a line: its number) |
| `SPATTERN, LINEAR, 4, 15, 0, 5` | 4 of circle 5 in all, each 15 to the right of the one before |
| `SPATTERN, POLAR, 6, 360, O, 5` | 6 round the origin, spread over the full turn (less than 360: the last one at that angle) |
| `SPROJECT, 12, 13` | body edges 12 and 13, laid flat on the sketch plane and fixed there |
| `SPROJECT, FACE, 6` | every edge of face 6 (`SEL` takes the picked edges or faces; `CONSTR` at the end makes construction geometry) |
| `SCHAMFER, 1.E, 3` | cuts the corner where line 1 ends and another line meets it with a straight line, 3 back along both |
| `SCHAMFER, 1.E, 3, 5` · `SCHAMFER, 1.E, 3, ANGLE, 30` | 3 along line 1 and 5 along the other, or 3 along line 1 at 30 deg to it (several corners: `SCHAMFER, 1.E, 2.E, 3`) |
| `SSPLIT, 3, u, v` | splits curve 3 at its point nearest (u, v); more points split it more (`SSPLIT, 3, u1, v1, u2, v2`; a circle needs two) |
| `SSPLIT, 3, 5` | splits curve 3 where curve 5 crosses it (`H` / `V`: an axis); the split points stay on 5 |
| `SCORNER, 1, 2` | trims or extends lines or arcs 1 and 2 so that they just meet (the end of each nearer the crossing moves) |
| `SCORNER, 1, 2, u1, v1, u2, v2` | ... keeping the part of 1 at (u1, v1) and of 2 at (u2, v2), as the Corner tool clicks them |
| `STRIM, 3, u, v, 5, u, v, ...` | several pieces in one step, in order (what the Trim tool sends when the mouse is dragged across curves) |
| `STRANSFORM, MOVE, du, dv, 1, 2` | moves geometry 1 and 2 by (du, dv) |
| `STRANSFORM, ROTATE, 45, O, 1, 2` · `STRANSFORM, SCALE, 2, 0, 0, 1, 2` | turns it about a point (a name like `O` or `3.C`, or u, v), or scales it about one |
| `STRANSFORM, ..., COPY` | leaves the originals and makes copies |
| `SCHECK` · `SCHECK, s1` | what is wrong with a sketch, or still loose: constraints that only repeat others (and which), curves drawn twice or too small, geometry that can still move and how, and whether the profile closes. `SCHECK, , SEL` also selects what it found; `SCHECK, s1, JSON` gives it as data |

What they leave behind keeps meaning what you asked for:

* A trimmed or extended end stays **on** the curve that cut it, so when
  that curve moves the end follows. Sizes that measured the part that went
  (a length, a fix) are dropped, and the output names them.
* A trimmed or extended end that stops at an axis stays on the axis.
* A fillet keeps the corner as a construction point on both curves. With
  an arc, the fillet sits on the side of the corner the other curve goes
  to: outside the arc's circle, or inside it when the other curve heads
  into the circle, and both curves are cut back to where it touches them. A size
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
  follows. When the distance is so big that parts of a closed chain's
  offset would turn round or cross (a slot narrower than twice the
  distance, a neck that pinches off), the loops are cut away instead: the
  slot closes, or the outline splits in two. That offset is made of plain
  curves joined end to end and is not held to the original; the output says
  so.
* Trims, extends and splits treat curves that come within a millionth of
  the sketch's size of touching (a tangent line or circle) as touching.
* Mirror and pattern copies are held as images of their originals: drag or
  size an original and every copy moves with it, and a copied circle keeps
  the same radius.
* Projected edges are made again from the bodies whenever an earlier step
  changes, so a sketch drawn round a projected hole follows the hole.
* A chamfer keeps the corner as a construction point, like a fillet, and its
  sizes are dimensions to that point: double-click one to change the number
  it came from in the `SCHAMFER` step.
* Split pieces stay joined end to end and on one line (or one circle), so
  each can be sized on its own; delete the `ON` constraint to bend them
  apart. A split made by a crossing curve stays on that curve.
* A corner joins the two ends with a coincident constraint; whatever pinned
  an end that moved is dropped and named.
* `STRANSFORM` takes the constraints among the geometry with it: a turn by
  a quarter swaps horizontal and vertical, a scale scales the sizes. A turn
  by any other angle keeps what horizontal and vertical meant: the first
  such line gets an angle (where it now points), the others are held
  parallel or square to it, so a turned rectangle stays a rectangle.
  Constraints that tie the geometry to the rest of the sketch (to the
  origin, to other curves) are dropped when it moves, and not copied. A
  copy made with `COPY` is free: unlike a `SPATTERN` copy it does not follow
  its original.

### More ways to draw

| Command | Draws |
|---------|-------|
| `SARCT, 3.E, u, v` | an arc that carries on smoothly from the end of line or arc 3 to (u, v), tied to the end and tangent to 3 |
| `SCIRCLE3, u1, v1, u2, v2, u3, v3` | a circle through three points (named points stay on it) |
| `SRECTC, cu, cv, u, v` | a level rectangle round a centre, through a corner; a construction diagonal and centre point keep it centred when sized |
| `SRECT3, u1, v1, u2, v2, u3, v3` | a rectangle at any angle: one side from the first point to the second, as wide as the third point is from it |
| `SNGON, cu, cv, n, r [, angle] [, OUT]` | a regular polygon with n sides, its corners on a construction circle of radius r (the first at `angle`, default 90: straight up); with `OUT` its sides touch the circle instead |
| `SSLOTARC, cu, cv, r, a1, a2, w` | a slot bent along an arc: its middle (kept as a construction arc) at radius r from a1 to a2 degrees, w half its width |
| `SLINE, ..., CONSTR` | a centreline (a construction line, the Centreline tool) |

The polygon stays regular when it is sized: give its construction circle a
radius (`SDIM, RADIUS, ...`), or a side a length.
  Straight edges become lines, circles and ellipses flat on the sketch become
  circles, arcs and ellipses; other curves come in as a chain of short lines. An edge square to
  the sketch shows as nothing.

### Ellipses, tangent circles, slots along a path, sections

| Command | Draws |
|---------|-------|
| `SELLIPSE, cu, cv, a, b [, angle] [, H]` | an ellipse round (cu, cv): radius a along its first axis (turned `angle` degrees from u, default 0), b across. `H` keeps the first axis level |
| `SEARC, cu, cv, a, b, angle, t1, t2` | part of that ellipse, from t1 to t2 degrees round it, counter-clockwise (0 is the end of the first axis, 90 of the second); its ends are `n.S` and `n.E` |
| `SCIRCLET, 1, 2, R, r, AT, u, v` | a circle of radius r touching curves 1 and 2 (lines, arcs, circles, `H`, `V`, or a line and an ellipse), the one nearest (u, v). The curves stay where they are |
| `SCIRCLET, 1, 2, 3, AT, u, v` | a circle touching three curves; they set its size |
| `SOFFSET2, d, 1, 2 ... [, FLAT]` | the curves offset by d to both sides, with round ends round the path's ends (`FLAT`: straight ends): a slot along a path. A closed chain gets an outline inside and one outside. The path becomes construction geometry |
| `SINTERSECT, body [, body ...]` | the curves where the bodies cut the sketch plane, fixed: lines, circles, arcs and ellipses (a cylinder cut at a slant gives an ellipse) |
| `SJOIN, 1, 2, 3 ...` | the curves (meeting end to end, in any order) joined into one smooth spline; corners where they meet are rounded off, a closed chain gives a closed spline. `SJOIN, 4` turns one line, arc, circle or ellipse into a spline to reshape by its points |

An ellipse is its centre `n.C`, the end of its first axis `n.A` and its
second radius: five degrees of freedom (an elliptical arc has two more, its
ends). It can be trimmed, split, extended, mirrored, patterned, moved and
scaled, and it takes `ON`, `CONCENTRIC`, `EQUAL` (two ellipses) and
`TANGENT` with a line. `SPROJECT` brings ellipse edges flat on the sketch
in as ellipses.

**Splines in the editing tools.** `STRIM`, `SEXTEND`, `SSPLIT` and
`SFILLET` work on splines, and splines cut other curves. A cut piece keeps
the points the spline ran through (with their constraints) and gains the
cut point, plus one point half way along each span the cut shortened, so
it keeps close to the old shape. A trimmed end stays `ON` the curve that
cut it (a point can be `ON` a spline too: `SCON, ON, 5, 3`). `SEXTEND`
carries a spline on the way it leaves its end; the old end stays as a
point it runs through. A split spline's pieces meet end to end but are not
held smooth where they meet; a closed spline split at one point opens
there. `SFILLET` rounds the corner of a spline and a line or arc: the
spline is cut back to where the arc touches it and held `TANGENT` to it.
`SCON, TANGENT, spline, line or arc` makes the spline leave its nearer end
along the line, or square to the arc's radius.

**Constraints made while drawing.** With the Line, Centreline, Rectangle,
Circle and Point tools a click on a curve puts the point on it (`SCON, ON`),
a line drawn on from the end of an arc along it is made tangent to it, and
a line that turns square off the line before it is made perpendicular. A
small mark by the cursor (On 3, Tangent, Perpendicular, H, V) shows what the
click will add, before you click. Hold Shift to draw without them, or switch
them off with **Auto constraints** on the Sketch tab. They are ordinary
`SCON` steps after the drawing step, so they can be deleted like any other.

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

### Linked part files: copies that follow the file

`LIB, LINK, bolt` reads the same files as `LIB, LOAD`, but follows the file:
every open, rebuild and `RELOAD` reads the part file itself, so when the
bolt file changes every copy placed from it is rebuilt.

| | `LIB, LOAD` | `LIB, LINK` |
|---|---|---|
| reads the file | once; the saved project reads its own copy from then on | on every open, rebuild and `RELOAD` |
| the file changes | the project keeps the old version | every copy updates ("bolt updated from bolt.cmd") |
| the file is missing | the saved copy | the saved copy, with a warning on the `LIB` step |

`RELOAD` reads the linked files again and, when one changed, re-runs the
history from its `LIB, LINK` step. It is not kept in the history. The window
does it by itself when a linked file changes on disk, or when you come back
to the app after changing it.

A saved project remembers where each linked file was, both as a full path
and relative to the project, so a folder holding the project and its parts
can be moved to another computer. The file is looked for there in this
order: the full path, next to the project, as written, then in the part
library; the copy saved in the project comes last.

`LIST, PARTS` says for each part where it comes from: `linked to ...`,
`loaded from ... (a copy)`, or `defined in this project`.


### Geometry from other parts: TAKE and DEPENDS

`TAKE` brings a face, edge, plane or axis of another part into this
project, so one part can be built against another:

| Line | Gives |
| --- | --- |
| `TAKE, FACE, plate, 3, lid` | a sheet body `lid`: face 3 of part `plate` |
| `TAKE, EDGE, plate, 10, rim` (or `CURVE`) | a curve body |
| `TAKE, PLANE, plate, 6, end_plane` | a datum plane on a flat face (normal out of the part) |
| `TAKE, AXIS, plate, FACE 7, hole_axis` | a datum axis along a round face; `EDGE n` for a straight edge |
| `TAKE, LIST, plate` | the faces and edges with their numbers, type, size and place (not kept in the history) |

The part is a part name, taken in the part's own coordinates with its
default values, or a placed copy (an `INST` body), taken where that copy
stands.

`LINK` (the default) takes the geometry again on every rebuild, so it follows
the part when the part, its file (`LIB, LINK`) or a value changes. The face
is found again by what it is: among the faces of the same kind (plane,
cylinder ...) facing the same way, the one nearest to where it was, which is
the same number unless the part's faces were numbered anew; the step then
says which face it followed. When nothing of that kind is left the step
fails as a **broken link**. `COPY` takes the geometry once and keeps it with
the saved project: later changes to the part do not reach it. Edit the step
(another number, another part) to take it afresh.

A part cannot take from itself, directly or through other parts: the part
build stops with "places itself".

`DEPENDS` shows what uses what: the linked part files (and whether each is
missing), every part with where it comes from, the other parts it uses and
the bodies it is placed as, the geometry taken with `TAKE`, loops between
parts, and every broken link with its step. `DEPENDS, JSON` gives the same
as data.

### Part documents: design one part on its own

A **part document** is a session that holds one part: its steps are normal
history entries (each opens in its form), and the parameters set first are
the part's inputs, with their values as defaults.

| Command | What it does |
|---------|--------------|
| `NEWPART, name` | starts an empty part document (the session is replaced) |
| `OPENPART, file [, name]` | opens one part of a part file (`.cmd`, a path or a name in the part library): its inputs become parameters (`D = 8`), its steps history entries. A file with several parts needs the name |
| `SAVEPART [, file]` | wraps the steps into one `*PART` block (the leading `NAME = value` entries become its inputs `NAME=value`) and writes it into the file: in place of the part of the same name, other parts and comments stay. With no file, the one it came from |

```
NEWPART, peg
D = 4                  ! inputs: the values set first
H = 3*D
CYL, 0,0,0, D/2, H
SEL, S, EDGE, AT, D/2, 0, H
FILLET, D/8
SAVEPART, peg.cmd      ! *PART, peg, D=4, H=3*D ... *ENDPART
```

A project links the file with `LIB, LINK, peg.cmd` (or loads a copy with
`LIB, LOAD`) and places copies with `INST`. In the window: **File > New part…**, **File > Open part…**, and
**File > Save** writes the part file; the title shows the part and its
file, and the Parameters panel shows the inputs in bold.

**Edit part** (right-click a copy of a part, the item panel under the model
tree, or a `*PART` step in History) opens a part defined in the project in a
window of its own, as a part document. **File > Save** there writes the new
block back into that history step (`HIST, EDIT`), and every copy is rebuilt.

**Open part** does the same for a copy of a part read from a part file
(`LIB, LINK` or `LIB, LOAD`): the part file opens in its own window, and
**File > Save** there writes the file. For a linked part the project then
reads the file again, so every copy updates; a loaded copy stays as it was
(the window says so).

### Mates: place copies by their faces and axes

`MATE, kind, <item that stays>, <item that moves> [, value] [, FLIP]` moves
the body that owns the second item so the two items meet. Items are written
as in `DIST`: `FACE, 12` · `EDGE, 4` · `VERTEX, 9` · `DATUM, name`, and for
the item that stays also `XY`, `YZ` or `ZX`. With no items, the two picked
ones are used (the first picked stays).

| Kind | Items | What happens |
|------|-------|--------------|
| `CONCENTRIC` | two axes: round faces, round or straight edges, datum axes | the axes line up; the copy keeps its place along the axis |
| `COINCIDENT` | two flat faces or planes | they face each other in one plane; the copy can still slide in it |
| | two round edges | same centre and axis |
| | two axes, two points, a point and a plane | in line, together, on the plane |
| `DISTANCE, d` | flat faces or planes, a point and a plane, two points, two parallel axes | as `COINCIDENT`, `d` apart |
| `ANGLE, a` | flat faces, planes, axes, edges | their normals or axes `a` degrees apart |

`FLIP` turns the copy the other way: faces that look the same way instead
of at each other, or an axis reversed (a bolt put in from the other side).

```
*PART, bolt, D=8, L=30
  CYL, 0, 0, 0, D, 5             ! head
  CYL, 0, 0, -L, D/2, L          ! shank
  UNION, 1, 2
*ENDPART
CYL, 0, 0, -12, 60, 12
NAME, LAST, plate
HOLE, plate, 45, 0, 0, 8.5
INST, bolt, 200, 80, 40          ! anywhere: the mates place it
MATE, CONCENTRIC, FACE, 4, FACE, 8     ! the hole's wall, the shank: axes 0 apart
MATE, COINCIDENT, FACE, 2, FACE, 7     ! the plate's top, the head's underside: distance now 0
```

(The face IDs are the ones this script gets; in the window you pick the
faces instead.)

Mates are placement steps, solved in the order they are written: each one
turns and shifts the copy as little as it can and keeps the freedom it does
not fix. Because they are history steps, a changed part, a moved hole or a
reloaded part file places the copies again. A later mate on the same copy
can undo an earlier one, so give a copy's mates in the order you would
assemble it (first the axis, then the seat). The result line says what was
checked ("distance now 0"); two flat faces put in one plane that do not
overlap give a warning. Check the whole assembly with `CONTACT`,
`CLEARANCE` or `DESIGNCHECK`. A mate that cannot be met (a flat face and
an axis for `CONCENTRIC`, two items on one body) is an error that names
both items, and nothing moves.

In the window: pick the two items (click, then Ctrl+click), right-click and
choose **Mate the two picked…**, or **Parts > Mate** in the command forms.
The form opens with the two picks filled in.

### Checking the mates: MATES

`MATES` measures every mate again on the finished assembly:

- **holds**, or **DOES NOT HOLD** with how far off it is and the later
  step that moved the copy away (the two **fight**: that step is marked
  `FIGHTS step n`). `MATE` itself warns when it undoes an earlier mate.
- **REPEATS step n** when a mate fixes nothing the earlier mates on that
  copy had not fixed already (two mates on the same faces, say), or
  *partly repeats* when only some of what it fixes is new.
- for each copy that was mated, the ways it can still move: **slides
  along** a direction or **turns about** an axis through a point (a face
  on a face leaves two slides and a turn; a pin in a hole that sits on its
  head only turns). A copy with none is **fully placed**.

`MATES, JSON` gives the same as data.

### Coordinate systems on bodies: CSYS

`CSYS, name, body, x,y,z [, nx,ny,nz [, angle]]` makes a coordinate
system at (x,y,z) with its Z along (nx,ny,nz) (default up) and its X
turned by angle about Z; `CSYS, name, FACE, id [, angle]` puts one on a
flat face, Z out of the body. It moves with its body (`MOVE`, `ROTATE`,
`MATE`), and it is a datum plane with an X axis, so `WORKPLANE, name`
draws in it and `DIST` measures to it. Body `0` makes one fixed in space.
`CSYS` alone lists them.

`MATE, FRAME, a, b` moves the body of coordinate system `b` so that `b`
lies on `a`, origin and axes: one step that places a copy fully. `FLIP`
turns `b` over (Z the other way, X the same), for two faces that meet:

```
CSYS, top, base, 20, 20, 10           ! on the base's top face
CSYS, foot, pin, 0, 0, 0, 0, 0, -1    ! at the pin's foot, Z out of it
MATE, FRAME, top, foot, FLIP          ! the pin stands on the base
```

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

A thread's groove starts at the free end it is cut from, so a nut placed on
a bolt usually needs a turn about the axis for its thread to line up with
the bolt's (otherwise the two overlap a little). The script works it out:
`TURN = 360*((L - T - D/10 - PITCH(D)/2) % PITCH(D))/PITCH(D)` for a nut
whose top is `T` below the head, then `INST, nut, x, y, z, TURN, D=D`.
`CONTACT, bolt, nut` then reports them touching, not overlapping.

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

### Hiding and fading for the view: DISPLAY, FADE, UNFADE

`HIDE`, `SHOW` and `ISOLATE` are history steps, so a script can rely on
them. Looking around a model is different: hiding a cover to see inside, or
fading everything but one bolt, should not fill the history. These commands
are **view steps**: they change only how bodies are drawn, are not history
entries (undo does not take them back, and a rebuild keeps them), and are
saved with the project.

| Command | What it does |
|---------|--------------|
| `FADE [, b/SEL/ALL [, amount]]` | draws bodies see-through; `amount` from 0.05 (nearly solid) to 0.95 (nearly invisible), 0.8 if not given |
| `FADE, OTHERS [, amount [, b/SEL]]` | fades every body but these (default: the selection), which stay solid |
| `UNFADE [, b/SEL/ALL]` | solid again (default: all of them) |
| `DISPLAY, HIDE, b/SEL` · `DISPLAY, SHOW, b/SEL/ALL` | hides or shows for the view only |
| `DISPLAY, ONLY, b/SEL` | shows only these bodies |
| `DISPLAY, FADE, b/SEL [, amount]` · `DISPLAY, UNFADE, b/SEL/ALL` | the same as `FADE` and `UNFADE` |
| `DISPLAY, ALL` | every body shown and solid (except bodies on a layer that is off) |
| `DISPLAY, MODEL` | drops the view's own changes: back to what the history shows |
| `FIT [, b/SEL]` | zooms to these bodies (no argument: everything) |

Where a body is named, several can be given separated by spaces:
`FADE, 3 5 7` or `DISPLAY, HIDE, 3 5`. A view step wins over `HIDE` and
`SHOW` in the history until a new `HIDE`, `SHOW`, `SHOW, ALL` or `ISOLATE`
names the body again. A faded body made of glass keeps whichever is more
see-through. `LIST, BODIES` marks faded bodies.

In the window, a **right click** without dragging opens a menu on the body
under the mouse (a right drag still pans): hide, show only this, fade this,
fade all others, show everything, zoom to, rename, colour, layer,
material, explode (for a part instance), find the step that made it, and
delete. When the body is one of several selected, the menu acts on the
whole selection. A right click on empty space offers Show everything, Make
all solid and Fit all. On the History panel, a step that made bodies has a
"Made by this step" submenu with the same view actions.

### The model tree and STEPS

The **Model** dock (left) lists what the model holds: **Parts** with their
placed instances (a bolt part and its 8 bolts), loose **Bodies**,
**Sketches**, **Datums** and **Named sets**. Each body row shows its colour,
a tick box for shown or hidden, "faded" or "hidden" when the view changed
it, and ⚠ when a step that made it needs a look. Its tooltip lists those
steps. Clicking a row picks the body (`PICK, BODY, b`; Ctrl or Shift adds
or removes) and a pick in the 3D view selects its row. A double click
zooms to it (`FIT, b`). The tick box hides or shows for the view
(`DISPLAY, HIDE` / `SHOW`), and so does the tick box of a part or group for
all of its bodies. A right click opens the same menu as on a body in the
3D view; on a part or a group it acts on all of its bodies.

Under the tree, the **item panel** shows the picked body's steps (from
`STEPS`) and the model parameters they use. A step that is a block, a
`*PART` recipe or a `*DO` loop, is shown line by line; each line opens in
its own form, and OK puts the new line back in its place in that entry with
`HIST, EDIT` (keeping its indent and comment), so the model rebuilds. A
line of a part's recipe changes every copy of the part.

`STEPS, b` lists the history steps that made a body, in order: the steps
that made or changed it (`COLOR`, `NAME`, `HIDE` count), the steps of the
bodies it was made from (the block and the cylinder before a `SUBTRACT`),
and for a part instance the `*PART` it came from. Each history step records
which bodies it read, made, used up and changed while it ran; a step with
a loop is followed one command at a time, so 8 bolts placed in one `*DO`
do not depend on each other.

## 23. Checking and describing: ASSERT, DESCRIBE, SELFOR, LINT, DIFF, CONTACT, CLEARANCE, RELATE, COMPARE, DESIGNCHECK

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

The analysis queries turn whole checks into one line, so a design rule stays
in the script and is checked again on every rebuild:

```
ASSERT, SAFETY(bracket, "wall", "tip", 0, 0, -400), GE, 2
ASSERT, OVERHANGS(case), EQ, 0, 1
ASSERT, FLOATING(), EQ, 0
ASSERT, MASS(bracket), LT, 0.25
```

They run quietly: no colours on the model and no message of their own, and
the answer is kept until the model changes, so checking twice costs nothing.

### Answers as data

`STRESS`, `PRINTCHECK`, `GRAVITY`, `MOTION`, `BOM`, `CUTLIST`, `MASSPROP`,
`MILL`, `PARTING`, `SHEETINFO` and `STACKUP` also hand back their answer as
data next to the message. The assistant's `run` tool and the MCP server show
it as a `report` on the step (for example `{"safety_factor": 3.1,
"max_deflection_mm": 0.12, ...}`), so a program reads the numbers instead of
picking them out of the text.

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

### RELATE, COMPARE and DESIGNCHECK: placement, same shape, design rules

`RELATE, lid, box` says where one body sits relative to another, so "the
lid sits centred on the box" can be checked without a picture:

```
body 2 (lid) relative to body 1 (box):
  X: within, overlap 30
  Y: within, overlap 30
  Z: on the +Z side, gap 0
  centres (0, 0, 12) apart; centred on X, Y
  contact: touch (face)
  a rests on top of b (a's -Z face on b)
```

It also lists flat faces that are flush (in one plane, facing the same way)
and round faces on one axis (a shaft and the hole it should line up with).

`COMPARE, left, right` compares volume, area, faces by type and inertia.
When they match it says whether the second body is a moved copy of the
first (and by how much) or its mirror image (and in which plane), otherwise
what differs. `SAMESHAPE(a, b)` is 1 or 0.

**Revisions.** `COMPARE, STEP, n` compares the model as it was after
history step `n` with now; `COMPARE, PROJECT, "old.m3d"` compares a saved
project with now. Bodies are paired by name. For each body that changed it
says, face by face, what is the same, what changed (the same surface with
another size: a plane cut by a new pocket, a hole made bigger, with the old
and new radius), what moved (the same face somewhere else, and by how
much), what was added and what was removed, the volume before and after,
and how far the surface moved (the largest distance out and in, and the
share of the surface that moved by more than the tolerance). The changed
body is coloured by how far it moved: green the same, red outward, blue
inward. `ANALYZE, OFF` ends the colours.

```
COMPARE, STEP, 12                    ! since step 12
COMPARE, STEP, 12, part, 0.01, JSON  ! one body, tolerance 0.01, as data
COMPARE, PROJECT, "bracket_v1.m3d"   ! against a saved revision
```

Faces are matched by what they are, not by their IDs, so a project that was
opened again or rebuilt compares correctly. `DIFF` (above) lists what each
step made; `COMPARE, STEP` shows how the shape itself changed.

`DESIGNCHECK, housing` runs rule checks and gives the IDs of what breaks
them: not valid, open edges, not a solid, loose pieces in one body, inside
out, edges shorter than a thousandth of the size (or `minedge`), narrow
sliver faces, and faces cutting through each other. `DESIGNCHECK, housing, 2`
also reports walls thinner than 2. `PROBLEMS(b)` counts the problems:
`ASSERT, PROBLEMS(housing, 2), EQ, 0`.

Each problem is a report row: its **severity** (ERROR for a broken, open,
inside-out or self-cutting body or one that is not a solid; WARNING for loose
pieces, tiny edges, slivers and thin walls), the value **measured** and the
**limit** it breaks, a suggested **fix** (a command such as `HEAL, housing`,
`EXPLODE, housing` or `CLEAN, housing`, or advice where no one command
fixes it) and whether the fix was **checked**: the fix is run on a copy of
the model and the rule tested again, so the row says "fixes it on a copy",
"does not fix it on a copy", or nothing when it is advice. The model itself
is not changed.

```
body 3 (a): 1 problem (0 errors, 1 warning)
  WARNING pieces: 2 separate pieces in one body
      measured 2, limit 1; fix: EXPLODE, a (fixes it on a copy)
```

`DESIGNCHECK, housing, 0, 0, JSON` gives the same rows as data (`severity`,
`measured`, `limit`, `fix`, `fix_is_command`, `fix_checked`).

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

### Continuity, curvature combs and inspection

```
CONTINUITY, b                      ! every join judged, with the largest gap and angle
CONTINUITY, b, 0.001, JSON         ! faces further apart than 0.001 do not meet; as data
COMB, EDGE, 12                     ! a curvature comb on edge 12
COMB, b                            ! combs on every curved edge of a body
COMB, OFF                          ! hide the combs
INSPECT, b                         ! the places worth a second look
```

`CONTINUITY` looks along every edge between two faces and measures the gap
between their surfaces (do they meet: G0), the angle between their normals
(are they tangent: G1) and the curvature straight across the edge on each
side (does it carry on: G2). Each join is *open* (a gap over the tolerance,
a ten-thousandth of the size by default), *sharp* (over 5 degrees: a real
edge), a *kink* (between 0.25 and 5 degrees: nearly tangent, almost always
a mistake), *G1* or *G2*. The answer counts each kind, gives the largest gap
and the largest angle of the smooth joins, and names the open joins, kinks
and G1 joins by edge and face.

`COMB` draws a curvature comb: at points along an edge, a tooth as long as
the curvature there, standing outside the bend, with a line through the
tips. A comb shows at a glance where a curve tightens, flattens or changes
the side it bends to. The answer gives each edge's tightest bend radius and,
for a flat curve, how many times it changes side. Straight edges get no
comb. All teeth in one `COMB` use one scale (the longest is a tenth of the
body's size), or give one: `COMB, b, , 50`.

`INSPECT` lists the places on a body worth a second look, each with its
IDs: kinks, gaps between faces, open edges, sliver and tiny faces, the
tightest bend (radius and where, "very tight" under a thousandth of the
size), the thinnest wall and how many G1 joins there are. `ANALYZE, b,
CURVATURE` and `GAUSS` show the curvature as colours, and `THICK` lists
thin walls.

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

## 25. Mesh bodies: big triangle meshes, fast mesh booleans, smoothing

A **mesh body** keeps its triangles as one mesh. A faceted body (section
10) has one flat face per triangle, which gets slow past about 100,000
triangles; a mesh body has one face that carries all of its triangles, so a
scan or a print file of a few million triangles stays quick to show, move
and combine. It has a body ID and one face ID like any body, so names,
picks, the Model tree, colours, layers, `HIDE`, `FADE` and the history work
as before.

```
SPHERE, 0, 0, 0, 30
NAME, LAST, shade
TOMESH, shade                ! the sphere becomes a mesh body, same ID
SPHERE, 0, 0, 0, 28
SUBTRACT, shade, LAST        ! mesh boolean: a 2 mm shell
CYL, -32, 0, 0, 6, 64, 1, 0, 0
SUBTRACT, shade, LAST        ! a solid cut from a mesh: meshed first, then cut
```

**Making and unmaking.** `TOMESH, b [, deflection]` turns a solid into a
mesh body; curved faces are cut into triangles that sit at most
`deflection` from the true face (default: a thousandth of the body's size,
at most 0.1 mm). `TOSOLID, b` turns a mesh body into a faceted solid (up to
100,000 triangles), for the commands that need faces and edges. `IMPORT`
makes mesh bodies from big files, or from any mesh file with the kind
`MESH` (section 10). Both keep the body's ID.

**Booleans.** When any body in `UNION`, `SUBTRACT` or `INTERSECT` is a mesh
body, the whole boolean runs on triangles (in the manifold3d library) and
the result is a mesh body; exact solids in it are meshed first. Mesh
booleans always give a closed mesh and are fast: two spheres of 245,000
triangles each are subtracted in about a second. A mesh with holes or loose
edges has no inside, so it is refused with that reason. `SEL` and `KEEP`
work as for any boolean.

**Shaping the mesh.**

| Command | What it does |
|---------|--------------|
| `SMOOTH, b [, steps [, strength]]` | Bumps and noise go and the body keeps its size (Taubin smoothing: each pass pulls every point towards its neighbours, then pushes it back a little). Long thin triangles next to small ones are split first, so a corner is not pulled far in. Default 5 passes at strength 0.5. |
| `REMESH, b, length` | More triangles: every edge longer than `length` is split, and the shape stays exactly the same. Use it before `SMOOTH`, and to give flat regions enough points to bend (`TWIST`, `BEND`). |
| `SIMPLIFY, b, tolerance` | Fewer triangles: no point of the surface moves more than `tolerance`. Flat regions lose the most. |

`MOVE`, `ROTATE`, `COPY`, `MIRROR` and the deformers (`BEND`, `TWIST`,
`TAPER`, `STRETCH`, `FLOW`) move every point of a mesh body, and it stays a
mesh body. `MASSPROP`, `VOL()`, `DESCRIBE` (which says `representation:
mesh` and what works), `DIST`, `CLASH` and `PROBE` measure it, and `EXPORT`
writes it to STL, OBJ, 3MF or GLTF. STEP, IGES and BREP hold exact faces,
so they refuse a mesh body: `TOSOLID` it first.

Commands that need faces and edges (`FILLET`, `HOLE`, `SHELL`, `SPLIT`,
`SECTION`, `CHECK` ...) refuse a mesh body with a message that says so and
points to `TOSOLID`, rather than failing inside the kernel.

The view shades a sharp edge of a mesh body sharp (its points are split
there for drawing only), and smooth regions smooth.

See `scripts/mesh_bodies.cmd`: a ball lamp shade cut as a mesh, a box
smoothed into a pebble, and a mesh bar twisted and simplified.

## 26. Implicit shapes, smooth blends and lattices

An **implicit shape** is given by an equation: the body is everywhere the
field `f(x, y, z)` is at most 0. A ball of radius 10 is
`SQRT(x**2 + y**2 + z**2) - 10`; a rounded box is a superquadric
`ABS(x/12)**4 + ABS(y/9)**4 + ABS(z/6)**4 - 1`. `IMPLICIT` evaluates the
field on a grid inside a box and makes a closed mesh body (section 25):

```
R = 10
IMPLICIT, a, BALL(0, 0, 0, R), -11, -11, -11, 11, 11, 11
IMPLICIT, b, BALL(16, 0, 0, 7), 8, -8, -8, 24, 8, 8
IMPLICIT, blob, SMIN(a, b, 5), -12, -12, -12, 25, 12, 12, 0.4
```

`IMPLICIT, name, f, x0,y0,z0, x1,y1,z1 [, step]`: the box is where the
field is looked at, and where the shape reaches the box it is cut flat
there, so the body is always closed. `step` is the grid spacing (default:
the box's largest side / 80); halving it gives about four times the
triangles and takes about eight times as long. Up to about 4.5 million grid
points are allowed; the message names the smallest step that fits.

The field is written like any expression, in `x`, `y`, `z` and parameters,
with `+ - * / **`, the usual functions (`SIN`, `COS` ... in degrees, `SQRT`,
`ABS`, `EXP`, `LOG`, `MIN`, `MAX`, `MOD`, `CLAMP`, `SIGN`) and building
blocks. Each building block is about the distance to its surface, so
`f - 1` grows a shape by about 1 and `ABS(f) - t/2` makes a wall t thick
around a surface:

| Block | Shape |
|-------|-------|
| `BALL(cx,cy,cz, r)` | ball |
| `BOX(cx,cy,cz, sx,sy,sz [, r])` | box of that size around the centre, with rounded edges of radius r |
| `ROD(x1,y1,z1, x2,y2,z2, r)` | rod with round ends between two points |
| `TORUS(cx,cy,cz, R, r)` | ring around the z direction |
| `CYLZ(cx,cy, r)` | endless cylinder along z (cut it with the box) |
| `GYROID(cell [, ox,oy,oz])`, `SCHWARZ(...)`, `DIAMOND(...)` | triply periodic surfaces repeating every `cell`: `ABS(GYROID(10)) - 0.5` is a gyroid wall 1 thick |
| `SMIN(a, b, k)`, `SMAX(a, b, k)`, `SDIFF(a, b, k)` | smooth union, intersection and difference: a blend about k wide where the shapes meet |
| `MIN(a, b, ...)`, `MAX(a, b, ...)` | sharp union and intersection; `MAX(a, -b)` cuts b out of a |

The name of an earlier `IMPLICIT` shape stands for its field, so shapes
combine and blend: `SMIN(a, b, 5)` above. Running `IMPLICIT` again with a
name that is already a body gives that body the new shape (same ID).

**Lattices.** `LATTICE, b, kind, cell, thickness [, skin [, step]]` fills
a solid with a lattice, for light parts and 3D printing:

- `GYROID`, `SCHWARZ` and `DIAMOND` are smooth walls `thickness` thick;
  `CUBIC`, `BCC` (corners to the centre) and `OCTET` (face diagonals) are
  round struts `thickness` across. `cell` is the size of one repeat.
- With a `skin`, the body keeps a closed outer wall that thick and the
  lattice fills the inside (found by offsetting the faces inwards, so this
  needs an exact solid: fill before `TOMESH`). Without one the lattice runs
  to the surface.
- The body becomes a mesh body with the same ID; the message says how much
  of the volume is left. `step` is the grid spacing (default: a third of the
  thickness, at least cell / 40).

```
BLOCK, 0, 40, -10, 50, 25, 20
NAME, LAST, bracket
LATTICE, bracket, GYROID, 8, 1, 1.5     ! 1 thick walls inside a 1.5 skin
```

A lattice body takes mesh booleans like any mesh body, so it can be cut
open (`SUBTRACT`) or joined to solid bosses (`UNION`). See
`scripts/implicit_lattices.cmd`.

## 27. Knife and freehand cuts

### KNIFE

`KNIFE, b, stroke [, width [, dx, dy, dz]]` cuts body `b` along a curve
(`LINE`, `POLYLINE`, `SPLINE` ...), straight through the body along a
direction, the way a knife drawn across the screen cuts along the line of
sight:

- The stroke is seen from the direction: only its shape across the
  direction counts, so it can be drawn anywhere in front of the body. The
  direction defaults to the normal of the plane the stroke lies in.
- An open stroke is carried on straight past the body at both ends, so a
  short stroke still cuts right through.
- Width 0 splits the body into pieces. The biggest keeps the body's ID and
  name; the others are new bodies (the message names them).
- A width cuts a slot that wide along the stroke, with round ends where it
  turns; what is left may be one piece or several.
- A closed stroke is a cookie cutter: the piece inside it and the piece
  outside it (with a width: a ring-shaped slot).
- The stroke is hidden afterwards; it stays in the history, so changing its
  points there moves the cut.
- It works on solids and on mesh bodies (section 25). A mesh body cut with
  width 0 along an open stroke is cut with a hairline gap (a hundred
  thousandth of its size), since a mesh piece needs a closed inside.

```
BLOCK, 0, 0, 0, 40, 24, 12
SPLINE, (14, -4, 30), (22, 6, 30), (16, 14, 30), (24, 28, 30)
KNIFE, 1, LAST                      ! seen from above (the stroke's plane)
LINE, 20, -5, 5, 20, 30, 5
KNIFE, 1, LAST, 2, 0, 0, 1          ! a straight stroke needs the direction
CIRCLE, 20, 10, 30, 5
KNIFE, 1, LAST                      ! cut out a round plug
```

**The Knife button** (Features toolbar) turns the tool on: drag across a
body in the 3D view and let go. The stroke is laid on a plane across the
view through the middle of the body under it (or of the picked body), and
two lines are run: a `SPLINE` (or `LINE`) for the stroke and `KNIFE, b,
LAST, 0, dx, dy, dz` with the view direction. End the stroke where it began
to cut out what is inside it. Esc or the button again ends the tool. For a
slot, change the 0 in the `KNIFE` line in History.

### Freehand sketches

In a sketch, the **Freehand** tool (key D) draws a curve with the mouse:
hold the left button, draw, let go. The stroke is thinned to the points
that matter and written as `SSPLINE` (a nearly straight stroke becomes
`SLINE`). Ending near where it began closes it, ready for `EXTRUDE` as a
cut or a boss, or `REVOLVE`; starting or ending on a sketch point ties the
curve there. A spline's points are `3.S`, `3.K1` ... `3.E`: drag them to
reshape it, or hold them with `SCON` (`FIX`, `COINCIDENT`). `SMIRROR` and
`SPATTERN` copy splines; `STRIM`, `SEXTEND`, `SSPLIT` and `SFILLET` work on
them (section 16), and so does `SOFFSET`: a spline's offset is a spline
through points kept at the distance (more than the spline's tightest bend
inwards is refused, since it would cross itself). `SJOIN` makes one spline
of a chain of curves.

```
SKETCH, pocket, top
SSPLINE, 8, 46, 20, 66, 34, 70, 30, 52, 20, 48, CLOSE
ENDSKETCH
EXTRUDE, pocket, -3, CUT, plate
```

See `scripts/knife_cuts.cmd`.


## 28. Sculpting mesh bodies

Sculpting pushes, pulls and smooths the points of a mesh body (section 25)
with brushes, the way clay is shaped. Each brush stroke is one history
step, so it can be undone, saved and replayed like any other command.

```
SPHERE, 0, 0, 0, 20
TOMESH, 1
REMESH, 1, 0.6                        ! even triangles, fine enough to shape
STROKE, S1, "4,-19,6  8,-19.5,7  12,-18,8"
SCULPT, 1, CLAY, 4, 0.8, S1, X        ! a brow ridge, mirrored in x = 0
STROKE, S2, "0,-20,-2  0,-20,2"
SCULPT, 1, INFLATE, 4, 0.9, S2        ! a nose
```

**STROKE, name, "x,y,z  x,y,z ..."** records the points of a stroke under
a name (`S1`, `S2` ...). The points are kept with the project (in
`strokes.npz`), so the history lines stay short. A script saved with
**File > Save log** writes the `STROKE` lines before the steps that use
them, so it runs on its own. `SCULPT` and `MASK` also take the points in
quotes in place of a name.

**SCULPT, b, brush, radius, strength, stroke [, sym]** runs one stroke over
mesh body `b`. The stroke is cut into dabs a quarter of the radius apart;
each dab moves the points within `radius` of it, most at the centre and
smoothly less towards the edge. `strength` (-1 to 1) is how far one dab
moves, as a part of the radius; a negative strength works the other way.

| Brush | What it does (negative strength: the other way) |
|-------|-------------------------------------------------|
| `DRAW` | raises the surface along its normal (digs in) |
| `CLAY` | like `DRAW`, but only up to a plane just above the surface: flat layers (scrapes) |
| `INFLATE` | puffs each point out along its own normal (deflates) |
| `SMOOTH` | moves points towards the middle of their neighbours |
| `FLATTEN` | presses the surface towards the plane through the brush |
| `PINCH` | pulls points in towards the stroke: sharpens a ridge (spreads) |
| `CREASE` | cuts a sharp groove along the stroke (a sharp ridge) |
| `GRAB` | moves what is under the first point to the last point |

`sym` mirrors the stroke in the planes `x = 0`, `y = 0` and/or `z = 0`:
`X`, `Y`, `Z`, `XY` ... A stroke that moves no point fails with "not near".

**Detail.** `SCULPT, b, brush, radius, strength, stroke, sym, detail` first
splits the triangles near the stroke (within 1.25 radii, mirrors included)
until no edge there is longer than `detail`, then runs the brush. A crease
or a fine ridge then comes out sharp without making the whole body fine.
The new points take the mask of the edge they split; points near the
stroke slide a little along the surface so the triangles stay even. After
the brush, edges near the stroke that it squeezed shorter than 0.4 times
`detail` are joined again (PINCH and CREASE squeeze), so stroke after stroke
the triangles keep about the same size and no slivers build up; frozen
points are never joined. Leave `sym` empty to skip it:
`SCULPT, head, CREASE, 2.5, 0.6, S3, , 0.25`.

Beyond the stroke the triangles grow back to the body's own size over a
band, not in one step: at a distance d outside the brush an edge may be up
to `detail + 0.5 × d` long. Sharp edges (where the surface turns by more
than 40 degrees, as on a box made into a mesh) stay sharp: their points do
not slide while the triangles are evened out, and a join never pulls a
point off one. Frozen points neither slide nor join.

**Every stroke is checked.** After the brush, the mesh near the stroke is
compared with how it was before: cracks (an edge with one triangle), edges
shared by three triangles, triangles turned inside out, folds (neighbours
facing opposite ways) and slivers (an angle under 1 degree). Folds the
stroke made are smoothed flat on the spot (the message says how many);
anything else new is a warning that says where. `CHECK, b, FLAWS` lists the
same for the whole mesh body.

**MASK** freezes part of a mesh body; sculpting leaves frozen points alone
(a half-frozen point moves half as far):

- `MASK, b, PAINT, x, y, z, r [, value]` freezes a soft sphere; `ERASE`
  unfreezes one. `MASK, b, PAINT, 0, 0, 0, r, 1, S3` paints along a stroke.
- `MASK, b, CLEAR` unfreezes everything, `ALL` freezes everything,
  `INVERT` swaps frozen and free.

A mask belongs to the mesh's points: `REMESH` keeps it (new points take
the mask of the edge they split), a boolean or `SIMPLIFY` drops it.

**The Sculpt tab.** **Sculpt** turns on sculpting in the 3D view; a left
drag over a mesh body (the picked one, or the one under the stroke) is a
stroke of the chosen brush. Ctrl works the other way (digs, or unmasks
with the Mask brush), Shift smooths, `[` and `]` change the radius, Esc
ends it. The radius starts at a twentieth of the body's size. Each drag
runs `SCULPT, b, brush, radius, strength, Sn [, sym]` (or `MASK, b, PAINT,
..., Sn`); the stroke's points are kept as `Sn`. **Detail** (off by
default) adds the detail size to each stroke. **Make sculptable** turns
the picked body into a mesh body with fine, even triangles (`TOMESH`, then
`REMESH` at a 150th of its size). **Mirror X/Y/Z**, **Clear mask** and
**Invert mask** are on the same tab.

While sculpting, a blue circle of the brush's size sits on the surface
under the mouse, the surface moves as you drag (the command that runs on
release gives the final result, so Esc during a drag leaves the body as it
was), and frozen areas are drawn purple.

See `scripts/sculpt_head.cmd`.

## 29. Fitting smooth surfaces to meshes (scan to CAD)

`FITSURF` turns a mesh body (a scan, an imported STL, a sculpture) into
smooth NURBS geometry that takes booleans, fillets and shells like any
other CAD body. The mesh stays; the fitted body is added.

```
FITSURF, b [, region [, tol [, trim]]]
```

| Argument | Meaning |
| --- | --- |
| `region` | `ALL` (default) the whole mesh; `MASK` only the points painted with `MASK` (section 28); `UNMASKED` the rest |
| `tol` | the largest distance from the mesh allowed; 0 (default) is a thousandth of the body's size |
| `trim` | `YES` (default) cuts the surface to the region's outline and holes; `NO` keeps the whole rectangle |

- **A closed mesh** with `ALL` becomes one smooth surface wrapped round it
  and closed into a solid. It must be seen whole from its centre (a ball,
  a head, a pebble, a bottle without handles); a shape that hides parts of
  itself, like a U, is refused. The two points where the surface gathers
  go where the shape is plainest, and so does its seam.
- **An open mesh, or a region**, becomes one trimmed face. The region must
  not fold back on itself when seen from its average direction (a cap, a
  panel, a face of a part); fit a bigger shape in such pieces.
- The control grid starts coarse and gets finer until every mesh point is
  within `tol`, up to 40 x 40 control points and never more than the mesh
  can support. If `tol` is still not met, the step is marked with a
  warning saying how far off it is.

The message says how many control points were used and how far the
surface is from the mesh, at most and on average. The Sculpt tab's **Fit
surface** button opens the form for the picked mesh body, with `MASK` as
the region when it has a mask.

```
SPHERE, 0, 0, 0, 20
TOMESH, 1
REMESH, 1, 0.8
...sculpt...
FITSURF, 1, ALL, 0.15                  ! a solid, within 0.15 mm
MASK, 1, PAINT, 0, -20, 2, 16
FITSURF, 1, MASK, 0.1                  ! just the painted region, one face
```

See `scripts/scan_to_cad.cmd` and docs/mesh-fit.md.

## 30. Configurations and the parts list

**Configurations** are named sets of parameter values for one model: the
sizes of a family of parts.

```
W = 40
H = 10
BLOCK, 0, 0, 0, W, 30, H
CONFIG, big, "W = 80, H = 20"         ! a history entry: defines (or redefines) BIG
CONFIG, small, "W = 20"
USECONFIG, big                        ! W and H keep BIG's values; the model rebuilds
USECONFIG, DEFAULT                    ! back to the values the history gives
USECONFIG                             ! lists them; * marks the one in use
```

While a configuration is in use, its parameters keep its values whatever
their own assignments say (the way `-D` fixes a parameter in the batch
runner); the others keep theirs. `USECONFIG` is not a history step: undo
does not switch back, and the configuration in use is saved with the
project. The Parameters panel shows a **Configuration** list once there is
one, and its values in italics; **New…** (or the panel's right-click menu)
opens the `CONFIG` form filled with every parameter's value now. The batch
runner takes `-C name`:

```
python -m modeler run plate.cmd -C big
```

**Design tables.** A CSV file with one row per configuration: its name,
then a column per parameter, and an optional `off` column with the steps
this configuration leaves out (by history number):

```
config, W,  H,  off
small,  30, 5,  5 6
big,    60, 20,
```

`DESIGNTABLE, "sizes.csv"` makes one `CONFIG` step per row (or changes the
one already there, so reading the table again after editing it updates the
configurations). `DESIGNTABLE, "sizes.csv", EXPORT` writes the
configurations out as such a table. Both are run when given, not kept in
the history; the values are kept by the `CONFIG` steps.

**Steps off per configuration.** `CONFIGOFF, small, "5 6"` leaves steps 5
and 6 out while `small` is in use (a hole the small size does not have);
`CONFIGOFF, small, "5", ON` puts one back and `CONFIGOFF, small` lists them.
The steps are remembered as steps, not numbers, so the right ones stay off
when steps are added or removed before them; they are saved with the
project. In the History panel such a step says "off in configuration SMALL".

**Comparing variants.** `VARIANTS` builds every configuration on its own,
and `DEFAULT`, without touching the model in use. For each one it says
whether it builds (or the step where it stops, with the reason), the
pieces, volume, mass and overall size, and the change in volume from
`DEFAULT`. `VARIANTS, JSON` gives the same as data; `VARIANTS, TEXT,
folder` also writes each configuration's parts list (`small_bom.csv`) and
drawing (`small.svg`) to the folder. `BOM, , small` shows the parts list of
one configuration without switching to it.

**`BOM`** lists the parts of the model: one row per part placed with
`INST` (instances of the same part with the same values are counted
together, with every parameter value shown) and one row per other solid
body, with quantity, material, volume and mass (for bodies with a
material). `BOM, parts.csv` also writes it as a CSV file. Bodies used up or
kept hidden by the history are not counted.

**Names.** A parameter and a body cannot have the same name, because in a
command the name would mean the parameter's value: `NAME, b, W` is refused
while `W` is a parameter, and `plate = 3` is refused while a body is called
`plate`.

## 31. Sheet metal

A sheet metal part is a plate of one thickness with walls bent along its
edges. It remembers its thickness, bend radius and K-factor, so it can be
laid flat again for cutting.

```
SKETCH, base, XY
SRECT, 0, 0, 60, 40
SCIRCLE, 30, 20, 6                    ! holes in the sketch are holes in the plate
ENDSKETCH
SHEET, base, 2                        ! 2 thick; bend radius 2 (the thickness), K-factor 0.44
SHEET, base, 2, 3, 0.4                ! or: bend radius 3, K-factor 0.4
SEL, S, EDGE, AT, 30, 0, 2            ! the front edge of the top face
FLANGE, , 25                          ! bends up 90 degrees, a 25 long wall
FLANGE, 12, 15, 45                    ! edge 12, 45 degrees; an edge of the bottom face bends down
FLANGE, 14, 10, 120, 1                ! bend radius 1 for this one
SHEETINFO, 1                          ! thickness, radius, K and each flange with its flat length
SBEND, 1, s2                          ! bend along the line in sketch s2: the smaller side turns up 90
SBEND, 1, s2, 45, 1, DOWN, FLIP       ! 45 down, radius 1, and the bigger side turns
UNFOLD, 1                             ! the flat blank as a body beside the part
UNFOLD, 1, blank.dxf                  ! and a DXF to cut it from
UNFOLD, 1, blank.dxf, NO              ! only the DXF
```

**`FLANGE`** bends along a straight edge of the plate's top face (the
wall goes up) or bottom face (it goes down). The bend starts at the edge
and its inside radius is the sheet's (or the one given), so the part
grows past the edge by the radius plus the thickness before the wall
starts. `FLANGE, , length` flanges every selected edge. Flanges on
neighbouring edges leave an open corner.

**`SBEND`** bends the plate itself along a line drawn in a sketch (one
straight line, in any sketch seen square to the plate; it may run past the
plate). The bend starts at the line, the smaller side turns (FLIP: the
bigger one), UP towards the top side or DOWN, and it keeps its holes. The
turning side loses the bend allowance from its flat width, so `UNFOLD`
gives the plate back exactly as it was. Bend before adding flanges on the
side that turns. The plate must cross the line in one piece.

**`UNFOLD`** lays the plate's bottom face (with every hole through it) flat
and adds each flange: a strip for the bend and the wall laid flat, with
any holes cut in the wall after bending. A bend takes `angle × (r + K × t)` of
flat length (in radians): the length of the line inside the bend that
neither stretches nor squeezes, which sits `K × t` from the inside face. K
is 0.44 unless `SHEET` says otherwise; use the value your shop or
material supplier gives. With K = 0.5 the blank has exactly the part's
volume. The DXF has the cut outline on layer OUTLINE, a centre line for
each bend on layer BEND, and its direction, angle and radius
(`UP 90° R2`) on layer TEXT.

`HOLE`, `SUBTRACT` and other changes keep a body sheet metal; holes through
the plate show in the flat pattern. Holes cut into a flange's wall do not
(yet), and a flange cannot start from another flange's wall.

## 32. Ribs, lips and wrapped sketches

```
PLANE, mid, XZ, 20
SKETCH, r1, mid                       ! a sketch square to the walls the rib joins
SLINE, -40, 20, -20, 20               ! the rib's top edge (an open line, arc or chain)
ENDSKETCH
RIB, r1, 2, box                       ! 2 thick (1 each side of the plane), down to the part
RIB, r1, 2, box, FLIP                 ! fill the other side of the line instead
SEL, S, FACE, AT, 1, 20, 30           ! the rim of an open box
LIP, , 2, 0.8                         ! a band 0.8 wide along its inside edge, 2 high
LIP, 32, 2, 0.8, GROOVE, 0.2          ! the other half: the band cut 2.2 deep and 1 wide
WRAP, grips, 7, 1                     ! sketch grips raised 1 out of cylindrical face 7
WRAP, band, , 0.4, CUT                ! sunk 0.4 into the selected cylindrical face
```

**`RIB`** carries the line's ends on straight along their direction, so a
line drawn between two walls needs to touch neither. The rib fills the
space between the line and the part on the side towards the middle of the
part (`FLIP`: the other side). If on that side nothing stops it, the rib
is refused.

**`LIP`** works on a flat face. On a face with a hole (the rim of a shelled
half) the band runs along the hole's edge, its outer corners rounded; on a
face without one it runs inside its outline. `GROOVE` adds the clearance
to both the width and the depth, so a lip made with the same numbers fits
in it.

**`WRAP`** needs a sketch on a plane parallel to the cylinder's axis. The
sketch's direction across the axis becomes length round the cylinder (so a
5 wide rectangle stays 5 wide on the surface) and the wrap starts where
the sketch plane faces the cylinder. Keep a band shorter than the
cylinder's circumference.

A conical face works the same way: the sketch is laid on the cone's flat
development (the sector the cone unrolls to), so sizes and angles are
kept. Across the axis becomes length round the cone, and along the axis
becomes length down its slope. Straight lines come out slightly curved on
the cone, as a label on a cone does. The sketch must stay clear of the tip.

## 33. Assemblies that move

A mechanism moves by a parameter: set it in the history and use it in the
steps that place the moving parts.

```
A = 60
BLOCK, 0, 0, 5, 40, 30, 2
NAME, LAST, lid
ROTATE, lid, -A, 0, 0, 5, 0, 1, 0     ! (or MATE, ANGLE, FACE, 3, FACE, 9, A)
DRIVE, A, 135                         ! hold A at 135: only the steps that read A run again
DRIVE                                 ! lists what is driven
DRIVE, A                              ! let go: back to the history's A = 60
MOTION, A, 0, 180, 12                 ! A = 0, 15 ... 180: overlaps at each, then A is put back
```

**`DRIVE`** is not a history step: the history keeps `A = 60` (its Result
column says `(driven)` while A is held), undo does not undo it, and it is
not saved. **`MOTION`** checks every pair of shown solid bodies that come
near each other at each position. It lists the positions, the ranges where
a pair overlaps with the largest overlap, and the value where they first
meet (found to a thousandth of a step). When nothing overlaps it gives the
smallest gap seen. Parts that only touch, like a lid on its hinge, are
not counted as a gap.

The **Motion window** (Inspect > Motion…) does the same with a slider,
Play, Check range and Save pictures. From a shell, one picture per step:

```
python -m modeler render part.cmd --motion A 0 180 18 frames
```

saves `frames/a_000.png` … `a_018.png`, with the camera fitted once to
the position that needs the most room.

## 34. Scan to CAD for machined parts

`FITSURF` (section 29) fits smooth freeform surfaces. A scan of a machined
part is mostly flat faces, bores and bosses, and those are better as exact
planes, cylinders and spheres, so that a hole is a true hole you can
measure and edit.

```
SEGMENT, scan                 ! the regions and what each is
SEGMENT, scan, 15, 0.05       ! split at bends over 15 degrees, fit within 0.05
RECONSTRUCT, scan             ! a new exact solid from the fitted faces; the mesh stays
RECONSTRUCT, scan, 25, 0.2
```

**`SEGMENT`** splits the mesh at its sharp edges (a bend between
neighbouring triangles sharper than `angle`, 25 degrees by default) and
fits each region. It lists every region with its triangles, its share of
the area and its fit: a plane (a point and its normal), a cylinder or a
bore (radius, axis), a sphere (radius, centre), or freeform when nothing
fits within `tol` (0.2% of the body's size by default). It is not a
history step.

**`RECONSTRUCT`** makes the solid: each fitted surface is made large,
space is cut into pieces by all of them, and the pieces inside the mesh
are joined. Directions within 0.3 degrees of a world axis or of a bigger
plane's normal are made exact first, so a bore comes out exactly square to
its face. It reports the faces it fitted and the solid's volume against the
mesh's. The mesh must be closed. If a region is freeform, RECONSTRUCT
names it and stops: fit it with FITSURF, or raise `tol`.

It also measures the mesh against the solid it made and says what share of
the mesh's points lie within `tol`, with the largest distances and the RMS.
Faces that are off in places get a warning naming them.

**`DEVIATION`** measures how far a scan is from a model, in numbers and in
colour:

```
DEVIATION, scan, part              ! tolerance ±0.1% of the model's size
DEVIATION, scan, part, 0.05        ! within ±0.05?
DEVIATION, scan, part, 0.05, JSON  ! the same as data
```

Every point of the scan gets its distance to the model's surface: positive
outside the model, negative inside. The first line gives the share of points
within ±tolerance, the largest distance out and in, the mean and the RMS,
and "tolerance met" when every point is within. Then come:

- the faces of the model that are off, worst first, each with its share
  within, RMS and worst distance;
- outliers: points more than five tolerances off in small separate pieces
  of the scan (stray points, dust, the fixture). They are left out of the
  numbers and listed with the worst one; far points on the scan's main
  surface (a real bump or dent) are counted;
- holes in the scan: loops of open edges, with their length and where;
- low confidence: faces the scan covers less than 80% of, where the numbers
  say little.

The scan is coloured in the view: green within the tolerance, yellow to red
outside the model, cyan to blue inside, magenta or dark blue past three
tolerances. `ANALYZE, OFF` ends the colours. `DEVIATION` is not a history
step. The scan can be any body (its triangles are measured), the model must
be an exact body.

An example is `scripts/scan_machined.cmd`.

## 35. Exploded views

An exploded view is a named list of steps, each moving some parts by a
vector. It shows how an assembly goes together, without moving anything in
the model.

```
XSTEP, apart, knob, 0, 0, 30                            ! step 1: the knob comes up
XSTEP, apart, "screw_1 screw_2 screw_3 screw_4", 0, 0, 45
XSTEP, apart, "lid knob", 0, 0, 25                      ! then the lid, taking the knob with it
XSHOW, apart                                            ! show it, with trail lines
XSHOW, apart, 0.5                                       ! half way
XSHOW                                                   ! back together
XSHOW, LIST                                             ! the views
XSTEP, apart, CLEAR                                     ! forget a view
```

**`XSTEP`** is a history step and the views are saved with the project,
but it moves nothing. Name the bodies by ID or name with spaces between,
or SEL for the selected bodies. A body in several steps moves by their sum,
so later steps can carry parts that moved before.

**`XSHOW`** is not a history step. It moves the parts by the view's steps
(times `factor`) and draws a thin grey trail from each part's centre back
to its place, with a corner at each step (`trails` NO leaves them out).
Looking around (`FIT`, `VIEW`, `LIST`, `DESCRIBE`) keeps the view shown.
Any other command, `UNDO`, a rebuild or `SAVE` first puts the parts back,
so an exploded view can never end up in the history or the saved model.
For a picture: `python -m modeler render part.cmd` with `XSHOW, apart` in
the shots file.

An example is `scripts/exploded_view.cmd`.

## 36. Frames and weldments

A frame is structural members (tube, bar, angle, channel, I-beam) laid
along straight lines. Draw the lines as a `POLYLINE` (in 3D) or in a
sketch, then give the profile and its sizes:

```
POLYLINE, (0,0,450), (600,0,450), (600,400,450), (0,400,450), CLOSE
MEMBER, LAST, SQUARE, 30x2                   ! square tube 30 wide, 2 wall, mitred corners: member_1 ... member_4
MEMBER, legs, SQUARE, 30x2, BUTT, leg        ! butted, named leg_1 ...
MEMBER, s2, IBEAM, 100x200x8, BUTT, beam, 90 ! turned 90 degrees about each member
CUTLIST                                      ! what to cut, with how many of each
CUTLIST, cuts.csv
```

| profile | size | |
|---|---|---|
| `SQUARE` | `w x t` | square tube, wall t (t 0: a solid bar) |
| `RECT` | `w x h x t` | rectangular tube |
| `ROUND` | `d x t` | round tube, outside diameter d (t 0: a solid bar) |
| `FLAT` | `w x t` | flat bar |
| `ANGLE` | `w x h x t` | angle (L) |
| `CHANNEL` | `w x h x t` | channel (U) |
| `IBEAM` | `w x h x t` | I-beam, flanges w wide, web and flanges t thick |

Each straight piece of the path becomes one body. The profile is centred
on the line. Its width (`w`) runs across, and its height (`h`) follows the
normal of the path's plane (Z for a path that is not flat); `turn`
rotates it about the member.

**Corners.** `MITRE` cuts both members on the plane halfway between them.
`BUTT` runs the first member on to the far side of the next one, and the
next one stops at its side. A round tube stopping at another is coped (cut
to the other's round). Where two members meet in a straight line they are
cut square.

**`CUTLIST`** groups the members by profile, size, length (end to end, the
longest points) and end cut angles (from square: 45 for a mitre of a right
angle), with how many of each and which bodies, plus the total length of
each profile. Members keep their place on the list after holes or other
cuts.

An example is `scripts/welded_frame.cmd`.

## 37. A first strength check

`STRESS` answers "will this part bend or break under this load?" while
you design. It is a quick, linear check of one solid. It is not a
replacement for a proper analysis program: there are no contacts, no
large deflections, no plasticity and no vibration modes, and you do not
make or tune a mesh.

```
SEL, S, FACE, NORMAL, -1, 0, 0
CM, wall, FACE                           ! the face bolted to the wall
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, LOC, X, 60
CM, tip, FACE                            ! the face the load hangs on
MATERIAL, bracket, ALUMINIUM
STRESS, bracket, wall, tip, FORCE, 0, 0, -400   ! 400 N down, shared over the tip faces
STRESS, bracket, "12", "7", PRESSURE, 2          ! 2 MPa (N/mm2) pushing into face 7
STRESS, bracket, wall, tip, FORCE, 0, 0, -400, 1 ! finer: 1 mm cells
ANALYZE, OFF                             ! ends the colours
```

Faces are given by number with spaces between (`"3 7"`), as a set saved
with `CM`, or as `SEL` for the selected faces. Units are mm, N and MPa.
The stiffness and yield stress come from the body's `MATERIAL` (steel when
it has none): steel, stainless, cast iron, aluminium, titanium, copper,
brass, ABS, nylon, PLA, wood and glass. Rubber is refused, because it is
not linear enough.

**How it works.** The part is filled with box cells, about 8000 of them
unless you give the cell size `h`. Each cell is an 8-node brick that also
bends well, so thin plates a few cells thick still bend about right. The
nodes near the fixed faces are held still, and the load is shared over the
nodes near the loaded faces. The answer usually comes in about a second.

**What you get.** The body is coloured from blue (no stress) to red (the
value that 99.5% of the part stays under), with magenta above it. The
message gives the largest stress and where, the 99.5% value, the largest
deflection and where, and the safety factor (yield stress over stress)
for both. The verdict uses the 99.5% value: "holds" at 1.5 or more, "is
close to yielding" from 1 to 1.5, "yields" below 1.

**Reading it.** The largest stress sits at sharp inside corners and at the
edge of a fixed face. There it depends on the cell size, so run again with
a smaller `h` and see whether it settles. Deflection settles much sooner
than peak stress. Curved faces become steps of cells, so treat stress right
at a curved surface as rough.

An example is `scripts/bracket_strength.cmd`.

## 38. Making it: 3D printing checks and milling paths

### Ready to print?

```
PRINTCHECK, hook                  ! built along +Z, 45 degree overhangs, 0.8 walls
PRINTCHECK, hook, BEST            ! tries +X, -X, +Y, -Y, +Z, -Z and uses the one needing least support
PRINTCHECK, hook, -Y, 50, 1.2     ! built along -Y, the printer manages 50 degrees, walls of 1.2
ANALYZE, OFF                      ! ends the colours
```

`PRINTCHECK` looks at the part the way a slicer will, and says:

- **bed**: how much flat face sits on the bed. A part that touches only at
  a point or an edge (a ball, a cylinder on its side) needs a flat or a
  brim.
- **overhangs**: the area facing down steeper than `angle` from vertical
  (45 by default), which needs support, with its faces and the height of
  the lowest one. A flat roof over a gap counts too, even though a short one
  often bridges.
- **walls**: places thinner than `wall` (about two nozzle widths; 0 skips
  this), measured as `THICK` does.
- **hollows**: closed spaces inside the part. Resin or powder stays trapped
  in them, so add a drain hole.

The part is coloured: blue sits on the bed, red needs support, the rest is
green. `up` is the build direction, from the bed upwards: `+Z`, `-X` and so
on, three numbers, or `BEST`, which lists all six directions and checks the
best one.

### Milling paths

```
MILL, plate, POCKET, floor, 6, 4              ! clear down to the floor faces, 6 mm end mill, 4 mm a cut
MILL, plate, OUTLINE, bottom, 6, 3, , part.nc  ! cut the part out of a plate, and write G-code
MILL, plate, FACE, top, 20                     ! flatten the top with a 20 mm cutter
MILL, OFF                                      ! hides the path
```

`MILL` makes 2.5D paths for a flat end mill coming down along Z. The faces
must be flat and face up (`OUTLINE` also takes a face facing down, such as
the bottom).

| op | what it cuts |
|---|---|
| `POCKET` | down to a floor face from the top of the part, in rings from the middle out to the wall, the last ring a tool radius off the wall; islands (the floor's holes) are cut around |
| `OUTLINE` | around the face's outline, with the tool outside the part, and inside its holes, from the top down to the bottom of the part. Holes smaller than the tool are left and listed |
| `FACE` | zig-zag passes along X over the face, grown by the tool radius |

`tool` is the diameter (6). `down` is the most each cut goes down (half the
tool); the depth is split into equal cuts. `over` is the step between
passes (40% of the tool), and it cannot be wider than the tool. `feed` is in
mm/min (600; plunges go at a third of it), and `speed` is the spindle in rpm
(10000).

The path's centre line shows in the view in cyan. The message gives the
number of passes, the cutting length, the time at the feed and how far the
tool goes. With a file name, the G-code (mm, absolute, G0/G1 moves only) is
written. Coordinates are the part's own, so set the machine's zero where the
part's zero is, and run the file in your machine's simulator before
cutting. The tool lifts to 2 mm above the part (or a tool radius) between
passes.

Examples are `scripts/print_check.cmd` and `scripts/milled_plate.cmd`.

## 39. Will it stand up? (gravity and connections)

`GRAVITY` checks every shown solid of an assembly under gravity. It looks at
how the parts touch and where their centres of mass are, so it is quick,
but it does not work out forces or bending (that is `STRESS`, part by part).

```
GRAVITY                            ! on a floor under the lowest part, gravity along -Z
GRAVITY, base                      ! base stays put instead of a floor
GRAVITY, FLOOR, "bolt_1 shelf"     ! these are bolted, glued or welded to what they touch
GRAVITY, FLOOR, , 0, -1, 0         ! gravity along -Y
GRAVITY, OFF                       ! clears the marks
```

For each part it says one of these:

| | |
|---|---|
| rests on ... | it sits on the parts named (or the floor). Its centre of mass, seen from above, is inside the outline of the places they hold it from below, by the margin given |
| TIPS off ... | its centre of mass is outside that outline (or it is balanced on an edge or a point), so it falls off |
| FLOATS | no chain of touching parts links it to the ground: it would fall |
| held only at its sides | it touches others, but nothing is under it: it needs a fastener, or list it as fastened |
| held | it is listed as fastened, or it cuts into a neighbour (a press fit) |

It also lists **gaps**: parts closer than `gap` (0.5% of the assembly's size
unless given) that do not touch, which were probably meant to. It lists
**overlaps**: parts that cut into each other. With the floor, it gives **the
whole on the floor**: whether the centre of mass of all the parts is inside
the footprint, and how far the assembly can lean before it tips.

Masses come from each body's `MATERIAL` (water's density for a body with
none). Parts with problems are marked in the view.

An example is `scripts/gravity_check.cmd`.

## 40. Pictures

```
RENDER, part.png                         ! as the view shows it, 1600 x 1000
RENDER, poster.png, 3840, 2160, ISO      ! any size, from a named view
RENDER, side.png, 1200, 800, "1,-1,0.6"  ! from a direction
RENDER, spin.png, 800, 600, ISO, 36      ! a turntable: spin_000.png ... spin_035.png (and spin.gif)
RENDER, part.png, 1600, 1000, , 0, OFF   ! no floor
```

`RENDER` draws a nicer picture than the working view, using the 3D view's
ray tracing:

- **Light:** sharp shadows from a sun high over the left shoulder, a soft
  fill light and some ambient light.
- **Floor:** a floor just under the model catches the shadows (`OFF`
  leaves it out).
- **Looks:** reflections, smoothed edges, and no edge lines. Each body's
  look comes from its `MATERIAL`: steel, stainless, aluminium, brass and
  copper shine, glass is clear, and plastics, rubber and wood are matte.
  The body keeps its own colour.

Without `view`, the picture uses the view's own camera. A turntable turns
the camera round the model's upright axis in `frames` steps and saves one
picture per step. When Pillow is installed it also saves an animated GIF.
The working view, its lights and its looks are put back afterwards.
**File > Render picture…** saves one picture of the view.

`RENDER` needs the app's 3D view: in a plain script run without the app it
says so.

## 41. Gears, fasteners and scaling

```
GEAR, 0,0,0, 2, 20, 10                   ! spur gear: module 2, 20 teeth, 10 wide
GEAR, 50,0,0, 2, 30, 10, , , 8           ! 30 teeth, an 8 mm bore
ROTATE, LAST, 6, 50,0,0                  ! half a tooth (180/30), so the two mesh
GEAR, 0,0,0, 2, 20, 10, , 15             ! helical, 15 degrees (its mate: -15)
GEAR, 0,0,0, 1, 60, 6, INTERNAL, , 70    ! a ring gear, 70 outside
GEAR, 0,-20,0, 2, 12, 8, RACK            ! a rack of 12 teeth along +X
FASTENER, CAP, M8, 0,0,10, 25            ! an M8x25 socket head cap screw, head on z = 10
FASTENER, WASHER, M8, 0,0,10             ! a washer under the head
FASTENER, NUT, M8, 0,0,-12               ! a nut hanging under a plate at z = -12
FASTENER, HEXBOLT, M6, 0,0,0, 20, REAL   ! a hex head screw with real threads
SCALE, 3, 2                              ! twice as big, about the origin
SCALE, 3, 1, 0,0,0, 1, 3                 ! three times as tall only
FILLET, 1, 4                             ! the radius grows from 1 to 4 along each edge
CHAMFER, 1, 3                            ! 1 on one face, 3 on the other
```

**Gears.** `GEAR` makes an involute gear about the axis through (x,y,z)
(`dx,dy,dz`, default +Z), its bottom face on the point. The size is set by
the **module** (the pitch diameter is module x teeth) and the tooth count;
the pressure angle is 20 degrees unless given. The message gives the pitch,
tip and root diameters and the centre distance to a mating gear.

- **Placing a pair.** Two gears of z1 and z2 teeth mesh at the centre
  distance module x (z1 + z2) / 2. A tooth of each gear points along its
  local X axis, so put the second gear along X and, when z2 is even, turn
  it by 180/z2 degrees so a tooth falls into a gap. `CLASH` then says the
  two touch without overlapping.
- **Helical gears** (`helix`, degrees) twist the teeth; the module is then
  the normal module, and the mate needs the opposite angle.
- **Internal gears** are a ring with the teeth inside (`rim` is the
  outside diameter). A gear of z1 teeth inside one of z2 teeth fits as
  made, along X, at module x (z2 - z1) / 2.
- **Racks** run along +X with their pitch line at the local Y = 0 and
  the teeth facing +Y (`rim` is the thickness under the roots). Gaps come
  every pitch (pi x module) from the start; a gear meshes with its centre
  module x z / 2 above a gap, turned so a tooth points down.

**Fasteners.** `FASTENER` makes a standard part from the ISO tables, M3 to
M24: `CAP` (ISO 4762 socket head cap screw), `HEXBOLT` (ISO 4017 hex head
screw), `NUT` (ISO 4032) and `WASHER` (ISO 7089). The point is the seat:
the face the head, washer or nut bears on. `dx,dy,dz` is the way the screw
points (default -Z): heads and washers stand up from the seat, a nut hangs
the other way, along the screw. Screws need their length under the head.
`PLAIN` (the default) leaves a smooth shank at the nominal diameter, quick
to build and to fit; `REAL` cuts helical ISO threads (a few seconds each).
The body is named after it (`M8x25_CAP_1`, `M8_NUT_1`) and made of steel,
so `GRAVITY` can list it as fastened and `BOM` gives its mass.

**Scaling.** `SCALE` makes a body bigger or smaller about a point that
stays put. One factor keeps the shape; with different factors along X, Y
and Z round faces become ellipses, so the faces are turned into general
splines. Mesh bodies scale too.

**Fillets and chamfers with two sizes.** `FILLET, r, r2` grows the radius
from r at one end of each edge to r2 at the other. `CHAMFER, d, d2` cuts
d along one face and d2 along the other.

An example is `scripts/gear_train.cmd`.

## 42. Plastic parts: bosses, snap hooks and vents

```
BOSS, case, 20,15,2, 10, 7, 2.5          ! a boss 10 tall, 7 across, a 2.5 hole, 4 ribs
BOSS, case, 20,15,28, 10, 7, 2.5, 0, 6, 0,0,-1   ! no ribs, a 6 deep hole, hanging down
SNAP, lid, 0,20,2, 12, 6, 1.5            ! a snap hook 12 long, 6 wide, 1.5 thick
SNAP, lid, 0,20,2, 12, 6, 1.5, 1, , , , -1,0,0, 30, 45   ! catch 1, facing -X, lets go
PICK, FACE, 12
VENT, 6, 20, 2                           ! six slots 20 x 2, 4 apart, through the wall
VENT, 6, 20, 2, 3, 90, , 10              ! turned 90 degrees, moved 10 along the slots
```

**Bosses.** `BOSS` adds a screw boss to a part: a post of the outside
diameter standing on (x,y,z) along `dx,dy,dz` (default +Z), with a hole
from its free end (`hole`, `depth`: default down to the foot) and support
ribs round it (`ribs`, default 4, reaching 0.75 x od out and sloping down
from 0.8 of the height). Put the foot on a face of the part: the boss is
joined to it.

**Snap hooks.** `SNAP` adds a cantilever hook: a beam of the thickness
standing on (x,y,z) along `dx,dy,dz`, with a catch at its tip facing
`hx,hy,hz` (default +X). The point is on the catch side of the beam; the
beam goes back from it by its thickness. The catch sticks out by
`overhang` (default the thickness); `lead` is the slope that pushes it in
and `catch` the angle that holds (90 holds for good, less lets it be pulled
apart). The message gives the bending strain it takes to snap in, and says
when it is more than the 2 to 5% most plastics take.

**Vents.** `VENT` cuts a grille of slots through the wall under the
selected flat face, centred on it: `count` slots of `length` x `width`,
`pitch` apart (default twice the width), turned by `angle` in the face and
moved by `u` (along the slots) and `v` (across them). The depth is the wall
under the middle of the face unless given. Slots that would run off the
face are refused.

An example is `scripts/plastic_case.cmd`.

## 43. Moulds, fits, notes and welds

```
PARTING, cover                           ! pulled along +Z, at least 1 degree of draft
PARTING, cover, 1,0,0, 2                 ! pulled along X, 2 degrees
MOLD, cover                              ! the two halves: cover_top and cover_bottom
MOLD, cover, 8, 0.5                      ! an 8 mm wall, 0.5% shrink
MOLD, cover, 8, 0.5, 0,0,1, 12.5         ! split at 12.5 along the pull
FITS, H7/g6, 25                          ! limits and the clearance of a fit
PICK, FACE, 4
FITS, H7/p6                              ! the size from the picked round face
NOTE, FIT, H7                            ! pin it: "ø25 H7 (+0.021/0)" with a leader
NOTE, HOLE                               ! just the diameter
NOTE, "Paint black", 50,30,40            ! a note at a point
NOTE, "Break edges", 120,0,30, 100,0,20  ! with a leader to 100,0,20
NOTE, SIZE, 0,0,0, 100,0,0               ! a size between two points (or two picked vertices, or an edge)
NOTE, DELETE, 2
LIST, NOTES
WELD, post, beam, 5                      ! a 5 mm bead along the joint
WELD, ALL, 4                             ! every joint between frame members
```

**Parting.** `PARTING` judges each face of a part for a mould that opens
along the pull direction: it comes out with the + half, with the - half,
it is too steep (it needs draft: steeper than the least draft angle), or
the parting line runs across it (a round side lying down). It lists the
faces that need draft, **undercuts** (faces whose way out is blocked by the
part itself, so they need a side action or another pull direction), and
the parting line: where + faces meet - faces, flat or stepped. The part is
coloured as by `ANALYZE, DRAFT` and the parting line is marked. Use
`DRAFT` on the steep faces until it says "ready for a two-part mould".

**Mould halves.** `MOLD` puts a block round the part (`wall` thick,
default a fifth of the part's size), takes the part's shape out of it
grown by the shrink allowance (percent, for the plastic's shrinkage as it
cools), and splits it across the pull: at a flat parting line, else at
the part's widest place, or at `level`. The halves are new bodies named
after the part (`cover_top`, `cover_bottom`); the part stays.

**Fits.** `FITS` gives ISO 286 limits from the standard's tables, sizes up
to 500 mm. Holes are written in capitals (D E F G H JS K M N P), shafts in
small letters (d e f g h js k m n p), with a grade from 5 to 13. A fit
(`H7/g6`) gives both parts' limits and the largest and smallest clearance,
or the interference of a press fit. With no size it reads the diameter of
the picked round face.

**Notes.** `NOTE` pins text to the model. It is shown in the view, kept
with the project (notes are history steps, so they follow edits) and put
on drawing sheets (`DRAWING`) in every plain view, with thin leaders. A
note on a picked face, edge or vertex gets a leader to it. `NOTE, HOLE` and
`NOTE, FIT, H7` on a picked round face write its diameter (and limits).
`NOTE, SIZE` writes the distance between two points. `LIST, NOTES` numbers
them for `NOTE, DELETE`.

**Welds.** `WELD` adds a bead along the joint where two solids meet: the
line where their surfaces cross, or the outline of where they touch.
`WELD, ALL` welds every pair of frame members (`MEMBER`) that touch. Each
bead is a new body (`weld_1` ...), drawn as a round bead of the weld size
across, made of the first part's material. `CUTLIST` adds the weld length
for each size.

Examples are `scripts/cap_mould.cmd` and `scripts/welded_frame.cmd`.

## 44. Sections, tolerances and pipes

```
SECTION, XY, BELOW, 12.5                 ! cut the view open 12.5 above XY, keep what is below
SECTION, YZ, ABOVE, 0, ADD               ! and along YZ too (up to three planes)
SECTION, OFF
STACKUP, +100 ±0.1, -60 +0/-0.05, -39.8 ±0.05      ! the gap a chain of sizes closes on
STACKUP, +25 H7, -25 g6                  ! ISO 286 tolerances in the chain
STACKUP, +W ±0.1, -(W - 0.5) ±0.05, MIN=0.1, MAX=0.8   ! parameters, and the gap allowed
PICK, FACE, 5
NOTE, DATUM, A                           ! datum A on the picked face
NOTE, GDT, FLATNESS, 0.02                ! a tolerance frame on the picked face
NOTE, GDT, POSITION, D0.05, A, B         ! a round zone (D or ø), from datums A and B
ROUTE, p1, PIPE, 28x2                    ! a pipe 28 across, 2 wall, bent at 1.5 x 28
ROUTE, p1, PIPE, 28x2, 50, water         ! bends of radius 50, named water
ROUTE, s1, CABLE, 7x2.5                  ! a bundle of seven 2.5 wires, bent at 6 x its diameter
ROUTES                                   ! the pipe list (ROUTES, pipes.csv writes it)
```

**Sections.** `SECTION` is a view setting, not a history step: it cuts the
view open along a plane (a datum plane or XY, YZ, ZX), moved `offset` along
the plane's normal. The cut faces are capped and hatched, and the command
prints the area and centre of the cut through each shown solid (and how
many pieces it falls into). `ADD` keeps the planes already there and cuts
along one more, up to three. **Section…** on the Inspect tab opens a window
with a slider that moves the plane through the model.

**Stack-ups.** `STACKUP` adds up a chain of sizes that closes on a gap:
each size is added (`+`) or taken away (`-`), with its tolerance written
`±0.1`, `+0.1/-0.05`, or as an ISO 286 letter and grade (`H7`, `g6`). Sizes
can be parameters or expressions (put an expression in brackets). It gives
the nominal gap, the **worst case** (every size at its limit at once), and
the **statistical** range (root sum square: each band taken as centred and
the half-widths added as squares, which is what parts from a steady process
give), and each size's share of the spread, so you see which tolerance to
tighten. `MIN=` and `MAX=` give the gap allowed and say whether the worst
case and the statistical range stay within it.

**Geometric tolerances.** `NOTE, DATUM, A` puts a datum letter on the
picked face. `NOTE, GDT, kind, tolerance [, datums]` puts a tolerance frame
on it: STRAIGHTNESS, FLATNESS, CIRCULARITY, CYLINDRICITY (form: no datum),
LINEPROFILE, PROFILE, PARALLELISM, PERPENDICULARITY, ANGULARITY,
POSITION, CONCENTRICITY, SYMMETRY, RUNOUT, TOTALRUNOUT (short names such as
FLAT, PERP and POS work too). A tolerance written `D0.05` (or `ø0.05`) is a
round zone. Up to three datum letters follow; it warns about a datum that
is not on the model yet. The view shows the frame as text with its symbol;
drawing sheets draw the boxes and the symbol as lines, and the datum's
triangle on the face. Notes on drawings move apart so they do not cover
each other or the sizes.

**Pipes and cables.** `ROUTE` runs a pipe (or tube) or a cable along the
straight lines of a polyline or sketch. At each corner it bends with the
bend radius, measured on the centreline (default 1.5 diameters for a pipe,
6 for a cable); it says so when a piece is too short for the bends at its
ends. A pipe's size is outside diameter x wall (`28x2`; one number makes a
solid rod); a cable's is wires x wire diameter (`7x2.5`), and the bundle's
diameter is the circle that packs them. A route that starts or ends on
another route's centreline joins it as a **tee**: the two are fused and
both bores are cut open again. `ROUTES` lists each route's size, length
along the centreline, straight pieces, bends and tees, with the total per
size, and writes it to CSV.

Examples are `scripts/pipe_run.cmd` and `scripts/toleranced_plate.cmd`.

## 45. Cams, traced paths, sketches from files and a topology check

```
LAW = "R12/150 D30 F12/150 D30"          ! rise 12 over 150°, dwell 30°, fall, dwell
CAM, 0, 0, 0, LAW, 30, 8, 12, DISC, 10   ! base radius 30, roller 8, 12 thick, bore 10
ROTATE, cam_1, A, 0, 0, 0, 0, 0, 1
MOVE, cam_1_roller, CAMLIFT(LAW, A), 0, 0          ! the roller follows the cam
CAM, 0, 0, 0, "R30/180H F30/180H", 30, 6, 80, BARREL   ! a groove round a cylinder
GEAR, 0,0,0, 2, 20, 10, BEVEL, 0, 8, 20, 0,0,1, 30  ! a bevel gear for a 30-tooth mate
GEAR, 0,0,0, 2, 1, 60, WORM, 0, 0, 20, 1,0,0        ! a one-start worm 60 long along X
GEAR, 30,-8,40.15, 2, 30, 16, WORMWHEEL, 0, 10, 20, 0,1,0   ! its 30-tooth wheel
GEAR, 0,0,0, 2, 30, 10, RACK, 15                    ! a helical rack (helix 15°)
TRACE, A, 0, 360, 24, arm, 40, 0, 2      ! the path of a point on arm as A runs: trace_1
SDXF, "plate.dxf", 1, 0, 0, OUTLINE      ! a DXF drawing's OUTLINE layer into the sketch
STRACE, "logo.png", 80                   ! the dark shapes of a picture, 80 wide
IMAGE, "front.jpg", XZ, 400, -200, 0, 0.6   ! a picture behind the model to draw over
IMAGE, CLEAR
TOPOPT, plate, wall, tip, FORCE, 0, 0, -1000, 0.3   ! keep the best 30% for this load
```

**Cams.** A lift law is pieces round the turn that add up to 360°: `R12/150`
rises 12 over 150°, `D30` dwells, `F12/150` falls. A letter after a rise or
fall picks the motion: `C` cycloidal (the default, no jump in
acceleration), `H` simple harmonic, `P` the 3-4-5 polynomial, `V` constant
speed. `CAM` makes the cam turning about Z through (x, y, z) and its roller,
named `cam_k` and `cam_k_roller`. A **disc** cam pushes the roller along
+X; its outline is where the roller's circles touch. A **barrel** cam is a
cylinder with a groove, and the roller slides along its axis. The message
gives the stroke, the steepest pressure angle (a warning above 30°) and the
tightest bend of the outline (an error if the roller is bigger than it, as
the outline would cross itself). `CAMLIFT(law, A)` is the lift when the cam
has turned A degrees: move the roller by it, and drive A with `MOTION`.

**More gears.** `BEVEL` makes a straight bevel gear whose pitch cone meets
its mate's (the `mate` argument gives the mate's teeth) at a right angle;
the message says where the cone's apex is, and the face width can be at
most a third of the cone distance. `WORM` takes the number of starts as its
teeth and its length as its width; `WORMWHEEL` makes a wheel with helical
teeth at the worm's lead angle (it is not throated, so it touches the worm
along a line, as a first model of the pair). A `RACK` takes a helix angle
to mesh with a helical gear of the same angle.

**Traced paths.** `TRACE` runs a parameter set in the history from one
value to another, follows a point on a body that moves with it (the body
must only move, not change shape) and adds a spline through where the
point goes, named `trace_k`. The parameter is put back afterwards.

**Sketches from files.** In a sketch, `SDXF` reads an ASCII DXF drawing:
lines, arcs, circles, ellipses, polylines (with bulges as arcs), splines and
points, optionally from one layer only, scaled and shifted by du, dv. Ends
that meet are joined, so closed outlines become profiles. `STRACE` turns a
picture grey, splits it into dark and light at a threshold (0 to 255) and
traces the outlines of the dark shapes, scaled to the width given, as
smooth splines broken at sharp corners (or straight pieces with `LINES`).
`IMAGE` shows a picture on a plane (XY, YZ, ZX or a datum plane) at a
width, shifted by du, dv, with an opacity: it is a backdrop to draw over,
kept with the model but not part of it.

**Topology check.** `TOPOPT` fills the body with the same cells as `STRESS`,
holds the fixed faces, loads the loaded ones and keeps the share of the
material that makes the part stiffest (cells touching the faces stay). The
result is a mesh body named `topo_k`, trimmed to the part, and the part is
hidden. It is a suggestion to model a real part after on a coarse grid with
one load case: check the part you make with `STRESS`.

Examples are `scripts/cam_follower.cmd` and `scripts/topo_bracket.cmd`.

## 46. Everyday work: previews, picking, numbers, typed sizes, templates, errors, repeat, properties, units, the view cube, tutorials and layouts

### See a step before it runs: PREVIEW

Every fill-in form draws what its step would make before you press OK: new
and changed bodies see-through in blue (the bodies they replace drawn faint),
bodies it would remove in red. When the step would fail, the form says why in
red and the faces or edges it was given are drawn in red in the 3D view. The
preview is worked out on a copy of the model 0.3 s after you stop typing, and
again when you pick something else while the form is open; nothing reaches
the history until OK. A step that takes longer than 1.5 s to work out switches
the form to an **Update preview** button. **Show in 3D** on the form (or
Preferences > Preview in forms) turns it off.

```text
PREVIEW, "FILLET, 2"          ! draws the result and says: changes plate, volume 8,000 -> 7,770.36 (-229.64)
PREVIEW, "FILLET, 30"         ! Would fail: FILLET: radius 30 is too large ... (shown in red: edges 1, 2)
PREVIEW, OFF                  ! clears the ghost
```

`PREVIEW` is not a history step. The assistant's `preview_step` tool gives
the same answer as data (bodies added, changed with their volumes, removed,
or the reason and the faces or edges at fault), also for a changed history
entry (`entry`).

### Picking

`PICKMODE, AUTO` (the default) picks whatever is nearest the cursor: a
vertex near a corner, an edge near an edge, else the face. `PICKMODE, FACE`
(or BODY, EDGE, VERTEX) picks only that kind, as before.

* **Tab** in the 3D view picks the next thing under the cursor, further
  back each time: the face behind the one in front, then round again.
* **Double-click** an edge: the loop of edges round the face that faces
  you (`SEL, S, EDGE, LOOP, e, f`); double-click it again: the tangent chain
  (`SEL, S, EDGE, CHAIN, e`). Double-click a face: it and the faces that meet
  it smoothly (`SEL, S, FACE, TANGENT, f`). Ctrl adds to the pick.
* **Box** (Pick group, or `PICKREGION, BOX`): drag left to right to pick
  what lies wholly inside, right to left to pick what the box touches.
  **Lasso** (`PICKREGION, LASSO`): draw a loop round what you want. Hidden
  faces behind are picked too, as in a wireframe. **Ctrl+drag** makes a box
  any time, adding to the pick. Esc ends the tool. A box or lasso writes one
  step, `PICK, FACE, 3 5 7` (several IDs separated by spaces), which keeps
  pointing at the same faces when the history changes, like a single pick.

### The tools beside a pick: TOOLS

After a click picks something, a small toolbar beside the cursor offers the
tools that fit it, and the right-click menu starts with the full list:

| Picked | Tools |
| --- | --- |
| a flat face | Sketch on this face, Pull, Hole, Fillet its edges, Shell (open this face), Move face, Work plane on it, Faces that meet it smoothly, Delete face |
| a round face | Pull, Thread, Fillet its edges, Shell, Move face, Axis through it ... |
| two faces | Pull, Fillet their edges, Shell, Move faces, Distance and angle, Mate, Joint ... |
| an edge | Fillet, Chamfer, Loop round its face, Tangent chain, Axis along it |
| two edges | Fillet, Chamfer, Distance and angle, Joint |
| vertices | Distance (two), Work plane through the three (three) |
| bodies | Move, Rotate, Mirror, Array, Union, Subtract the others, Intersect, Distance, Check, Mass and volume |

Each tool opens its form filled in from the pick, or runs its commands.
`TOOLS` lists the same for the current pick (`TOOLS, JSON` as data), and the
assistant's `suggest_tools` tool returns it. The toolbar goes when the mouse
moves away, after a few seconds, on Esc or with the next pick;
Preferences > Tools beside a pick turns it off.

### The numbers of the pick: SELINFO

The right of the status bar always shows the numbers of what is picked:

| Picked | The line says |
| --- | --- |
| a face | its type and area; radius and diameter for a cylinder, cone, sphere or torus |
| an edge | line, arc or circle, its length; an arc's radius and angle |
| a vertex | where it is |
| a body | volume, area, mass (from its `MATERIAL`) and size |
| several | how many, and the total area, length, volume or mass |
| two | also the distance between them (dx, dy, dz when it is along one or two axes), and the angle, or "parallel" |

A click on the line copies it (with every row). Resting the mouse on a face,
edge or vertex for a moment shows its numbers in a tooltip, without picking it
(Preferences > Numbers on hover turns that off). `SELINFO` prints the same:

    SELINFO                        ! the picked things
    SELINFO, FACE, "3 5"           ! any faces
    SELINFO, BODY, plate, JSON     ! as data

It is a query, not a history step. The assistant gets the line, the totals and
the distance and angle of two picks in `user_context`, and any of them with
`selection_numbers`.

### Typed sizes while sketching

After the first click of a line, centreline, rectangle, centre rectangle,
circle, arc, slot or polygon, boxes beside the cursor show its sizes as the
mouse moves: length and angle (a line, the first two clicks of an arc or a
slot, a polygon's radius and turn), width and height, or radius. Type a number
and it goes into the first box; Tab fixes it and moves to the next (Tab first
to type a parameter name, such as `W` or `D*2`); Enter places the point; Esc
clears what was typed (a second Esc ends the drawing). Clicking a box types into
it. The mouse still sets whatever is not typed: with only a length typed, a
line still turns with the mouse.

Each typed value becomes a size on the sketch, written as the ordinary steps:

    SLINE, 5, 5, 39.641, 25
    SDIM, LENGTH, 1, 40
    SDIM, ANGLE, 1, 30

A level or upright line gets `H` or `V` rather than an angle size, an arc its
`DIST` between the ends and its `RADIUS`, a slot the `DIST` between its centres
and its `RADIUS`, and a polygon's radius and angle go into `SNGON` itself. A
size typed as an expression keeps it, so editing the parameter later resizes
the sketch.

### Starting a project: the start page, NEW and TEMPLATE

The start page opens when the app starts with nothing to open (and from
File > New). It has a card per template, the recent projects with a picture
of each (taken when it was saved), the examples and the quick start.

The built-in templates:

| Template | Sets |
| --- | --- |
| `part` | mm; a construction layer; parameters W, D, T; title and material in the title block |
| `assembly` | mm; layers frame, parts and fasteners; a clearance parameter; a title |
| `sheet_metal` | mm; thickness T, bend radius R and K-factor K for `SHEET` and `FLANGE`; the sketch `base` open on XY for the outline |
| `drawing` | mm; A3 paper (`PROPERTY, SHEET, A3`, which `DRAWING` then uses); title, number, revision and author |

    NEW, sheet_metal               ! clears the session; the template's steps are the first entries
    TEMPLATE                       ! lists them, with what each sets (TEMPLATE, JSON as data)
    TEMPLATE, SHOW, part           ! its steps
    TEMPLATE, SAVE, my_bracket, "My bracket", "A bracket to start from"
    TEMPLATE, DELETE, my_bracket

A template's steps are ordinary history entries, so each can be edited later.
`TEMPLATE, SAVE` keeps the current history as your own template, in the
per-user app data folder (`MODELER_TEMPLATES` names another folder); one of
yours with a built-in name is used instead of it, until you delete it. The
assistant's `templates` tool lists them all with what each sets.

### When a step fails: the error bar and WHY

A line or step that fails changes nothing. The bar above the command line
says why and lights up the faces, edges or bodies at fault in red: the ones
its message names, else the pick it used, else the bodies it names.

* A misspelt command or name gets "did you mean ..." in the message
  (`BLOK` gives BLOCK, `plaet` gives plate). A "Use BLOCK" button puts the
  fixed line back on the command line, so Enter runs it.
* "Find fixes" tries the usual fixes on a copy of the model (a radius under
  the limit, the nearest name, HEAL before a boolean ...); each one that
  works becomes a button. Undo takes a fix back.
* "Why?" opens the whole answer. Esc in the command line (or the ✕) hides
  the bar; the next line that works hides it too.
* Failed history rows are tinted red, with the reason as a tool tip; a
  click on one shows it in the bar.

The same as commands:

    WHY                    ! the first failed step, else the last line that failed
    WHY, 5                 ! history step 5: the reason, the fixes, the IDs at fault (red in the view)
    WHY, 5, JSON           ! as data
    WHY, OFF               ! clears the red

The assistant's `diagnose` gives the same, with `fault` (kind and IDs).

### The same step again: REPEAT

`REPEAT` runs the last step that changed the model again, on the current
pick (picking, undo and history edits do not count):

    PICK, EDGE, 1
    FILLET, 2
    REPEAT, EDGE, 3 7      ! picks edges 3 and 7, then FILLET, 2 again
    SEL, S, EDGE, RADIUS, EQ, 4
    REPEAT                 ! the same fillet on every edge the rule found
    REPEAT, SHOW           ! what it would run

In the window, Enter on an empty command line is `REPEAT` (the command
line says what it would repeat), and so is right click > Repeat. A form's
"Keep open" pin keeps it open after OK: pick the next faces or edges and
press OK again, until Esc. The pin is remembered for each command.

### One table of properties: PROPS and the Properties panel

The Properties panel (beside Parameters) shows the picked body, or the
history step clicked in History. White values can be changed; each change
is the ordinary step, so Undo takes it back:

| Row | Changing it writes |
| --- | --- |
| name | `NAME, b, new` |
| x, y, z (the centre of its box) | `MOVE, b, dx, dy, dz` |
| turn (`Z 90`) | `ROTATE, b, 90, centre, 0, 0, 1` |
| colour | `COLOR, b, value` |
| layer | `LAYER, name, ADD, b` (the layer is made if new) |
| material | `MATERIAL, b, name` |
| `5.dx` (argument dx of step 5) | `HIST, EDIT, 5, ...` |

Size, volume, area, mass and the centre of mass are shown too. For a copy
of a part (`INST`) the rows are its place and the part's values, including
the ones left at their defaults (a change adds `L=25`).

    PROPS, plate                 ! the table (PROPS alone: the pick)
    PROPS, plate, x, 50          ! moves its centre to x = 50
    PROPS, plate, 1.dz, 15       ! changes the BLOCK of step 1
    PROPS, plate, colour, red
    PROPS, STEP 1                ! the values of step 1 (or #1)
    PROPS, STEP 1, dx, 60
    PROPS, plate, JSON

The assistant's `properties` tool gives the same table as data.

### Numbers with units

Any number in a command, a form field or a parameter may carry a unit:
`mm`, `cm`, `m`, `in` (or `inch`), `ft` for lengths and `deg` or `rad` for
angles. The number is turned into the model's units before it is used, so
in a millimetre project `1 in` is 25.4 and `1/4 in` is 6.35. Brackets take a
unit too: `(W/4) in`. Text in quotes is left alone.

    BLOCK, 0,0,0, 2 in, 1 in, 6 mm
    HOLE, plate, 1 in, 0.5 in, 6 mm, 1/4 in
    W = 3/8 in
    ROTATE, plate, 0.5 rad, 0,0,0, 0,0,1

`/UNITS, IN, SHOW` changes only the units numbers are *shown* in (the
status bar, the Properties panel, `SELINFO`), not the model. In the
Properties panel a plain number is read in the shown units. Forms show the
unit beside every length and angle field. `/UNITS` alone says what is set.

    /UNITS, MM                   ! the model is in millimetres
    /UNITS, IN, SHOW             ! ... shown in inches
    /UNITS                       ! units MM, numbers shown in inches

### The view cube and VIEW

The small cube in the top right corner of the 3D view turns the view: click
a face to look straight at it, an edge for the view between two faces, a
corner for an iso view from that corner. The arrows round it turn the model
by 90 degrees (left, right, up, down) or roll the view (the curved arrows),
and the house goes back to the standard view with everything in sight.
Every click writes the ordinary `VIEW` line, so it works the same typed:

    VIEW, TOP                    ! a face: TOP BOTTOM FRONT BACK LEFT RIGHT (ISO too)
    VIEW, TOP FRONT              ! an edge
    VIEW, TOP FRONT RIGHT        ! a corner (the same as ISO)
    VIEW, TURN, LEFT             ! LEFT RIGHT UP DOWN, CW CCW: turn by 90 degrees
    VIEW, HOME                   ! iso, everything in sight

Preferences > View cube hides it. The assistant's `view_state` tool says
where the view looks from, which way is up, the cube name of the view and
which bodies are in sight.

### Learning by doing: TUTORIAL

Help > Tutorials opens the Tutorial panel with short lessons: **Your first
part** (a shape, a name, sizes in Properties, holes, fillets), **From a
sketch to a solid** and **Fixing a step that failed**. Each starts a new
project. A step says what to do and which button does it, and its checks
look at the model itself, so it does not matter whether you click, type or
ask the assistant: the checks turn green and **Next** lights up the moment
the step is done. **Show me** does the step for you.

    TUTORIAL                     ! the list
    TUTORIAL, first_part         ! start one (a new project)
    TUTORIAL, first_part, NEW    ! ... even with unsaved changes
    TUTORIAL, CHECK              ! what is done and what is still missing
    TUTORIAL, HINT               ! what to type
    TUTORIAL, SHOW               ! do it for me
    TUTORIAL, NEXT               ! on to the next step (only once this one is done)
    TUTORIAL, BACK
    TUTORIAL, STOP               ! the model stays as it is
    TUTORIAL, JSON

Write your own as a text file `name.tut` in the `tutorials` folder beside
your templates folder:

    ! tutorial: bracket
    ! title: An angle bracket
    ! about: what it teaches, in one line
    ! start: W = 40                (steps the project starts with, if any)

    ## Make the base
    The text of the step. **Bold** for buttons, `code` for values.
    hint: BLOCK, 0, 0, 0, W, 30, 5           (what Show me runs)
    check: BBOX(LAST).dx, EQ, 40 ! 40 long   (an ASSERT check, then the words shown)

A step without `check:` lines is one to read; Next goes on. The assistant's
`tutorial` tool gives the lesson as data, and its `tutor` skill helps with
the step the user is on.

### Pictures in tooltips

Hover a ribbon button to see a small picture of what it makes, from the
same examples as the user guide's command pages, under what it does and the
command it runs. Preferences > Tooltips turns the pictures off.

### Layouts: LAYOUT

View > Layout shows the panels for the job at hand:

| Layout | Panels | Ribbon tab |
| --- | --- | --- |
| modelling | Model tree, History, Properties, Parameters, Output | Model |
| sketch | History, Properties, Output (a bigger view) | Sketch |
| assembly | Model tree, History, Properties, Parameters (in front), Output | Model |
| drawing | History, Parameters, Output | Inspect |
| sculpt | only a small Output (the most room) | Sculpt |

Arrange the panels your own way and keep it with **Save this layout…**:

    LAYOUT, sketch
    LAYOUT, SAVE, mine           ! the window as it is now
    LAYOUT, mine                 ! back to it
    LAYOUT, DELETE, mine
    LAYOUT, RESET                ! the panels as the window first opens
    LAYOUT                       ! the list (LAYOUT, JSON as data)

Layouts are kept with your settings, not in the project, and `LAYOUT` is
not a history step.
