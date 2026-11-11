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
*MACRO, hole, x, y, d=6, depth=20     ! arguments, with optional defaults
  CYL, x, y, -1, d/2, depth + 2
  SUBTRACT, base, LAST
  *IF, d > 10
    *RETURN                            ! leave early
  *ENDIF
*END

hole, 10, 10                           ! called like any command
hole, 30, 10, 4
```

* Arguments and parameters set inside a macro are local to that call; the
  macro can read the global parameters.
* A bare word that is not a known name is passed as text: `pickall, EDGE`.
* A macro cannot take the name of a built-in command. `HELP, HOLE` shows its
  arguments.

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
| Patterns | `ARRAY, LINEAR, b, n, dx,dy,dz [, n2, dx2,dy2,dz2]` · `ARRAY, POLAR, b, n [, angle [, x,y,z [, dx,dy,dz]]]` · `ARRAY, PATH, b, path, n [, twist_law [, scale_law]] [, MINTWIST/FRENET/FIXED]`; add `FUSE` to fuse the copies into the original |
| Blends | `FILLET, r` · `CHAMFER, d` (on the selected edges, or all edges of the selected bodies) |
| Check and repair | `CHECK [, b]` · `HEAL, b [, tolerance]` · `CLEAN, b` (section 12) |
| Transforms | `MOVE, b, dx,dy,dz` · `ROTATE, b, angle [, x,y,z [, dx,dy,dz]]` · `COPY, b, dx,dy,dz` · `MIRROR, b [, x,y,z [, nx,ny,nz [, copy]]]` |
| Paths | `LINE, p1, p2` · `ARC, p1, p2, p3` · `POLYLINE, p1, p2, ... [, CLOSE]` · `SPLINE, p1, p2, ... [, CLOSE]` · `HELIX, x,y,z, r, pitch, turns [, axis] [, taper] [, RIGHT/LEFT] [, pitch_law]` · `CURVE, PARAM, x(t), y(t), z(t) [, t0, t1, n]` |
| Profiles | `CIRCLE, x,y,z, r` · `ELLIPSE, x,y,z, a, b` · `RECT, x,y,z, w, h [, r]` · `POLYGON, x,y,z, r, sides` · `STAR, x,y,z, ro, ri, points` · `SLOT, x,y,z, length, width` · `AIRFOIL, x,y,z, chord, code`, each followed by `[, nx,ny,nz [, angle]]` (section 9) |
| Shapes on curves | `LOFT, s1, s2, ... [, RULED] [, CLOSED] [, SURFACE]` · `SWEEP, profile, path [, twist, scale, mode, sx, sy, ox, oy, n, solid]` · `MORPH, path, twist, scale, mode, s1, s2, ...` · `PIPE, path, r [, ri, radius_law, mode]` (section 9) |
| Bodies | `NAME, b, name` · `DELETE, b` · `CLEAR` · `HIDE, b` · `SHOW [, b]` |
| Selection | `PICK, kind, id [, S/A/U]` · `SEL ...` · `CM` · `CMSEL` · `CMDEL` · `PICKMODE, kind` |
| Settings | `/UNITS, MM/CM/M/IN` · `/TOL, value` (fuzzy booleans and selection tolerance) |
| Files | `EXPORT, STEP/BREP/STL, file [, body]` · `IMPORT, STEP/IGES/BREP/STL, file [, name]` · `RUN, file` |
| Projects | `SAVE [, file.m3d]` · `OPEN, file.m3d` · `OPEN, AUTOSAVE` · `NEW` (section 10) |
| History | `UNDO` · `REDO` · `HIST ...` |
| View & info | `VIEW, ISO/TOP/...` · `FIT` · `LIST [, BODIES/PARAMS/MACROS/SETS]` · `ECHO, expr` · `HELP [, name]` |

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

### LOFT

`LOFT, s1, s2, s3, ...` fits one smooth solid through the sections in order.
The sections can be different shapes (a circle, then a rounded square, then
a polygon) and need not be parallel. Add `RULED` for straight sides between
sections, `CLOSED` to come back to the first section (a ring), `SURFACE` for
no end caps.

### SWEEP

`SWEEP, profile, path [, twist, scale, mode, sx, sy, ox, oy, n, solid]`

* Draw the profile where the path starts, usually across it. Its place
  relative to the path start is kept all along (an offset profile stays
  offset).
* `mode`: `MINTWIST` (default) keeps the profile from spinning on 3D
  curves; `FRENET` follows the curve's bend (good on helices); `FIXED` never
  turns the profile, it only moves.
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
body; the first one gets the name. STL files are sewn into a solid when
they are closed.

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

`CHECK` is a query and not part of the history. `HEAL` and `CLEAN` are
history entries; the body keeps its ID and name, and its faces keep their
IDs where they survive. `HEAL` refuses, and changes nothing, when the repair
does not give a valid body (a missing face cannot be invented).
