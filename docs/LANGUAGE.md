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
| `HIST` | list the history (`x` failed, `-` suppressed) |
| `HIST, EDIT, n, "text"` | replace entry n and re-run from there; `\n` separates lines of a block |
| `HIST, INSERT, n, "text"` | add an entry before n |
| `HIST, DELETE, n` | remove entry n |
| `HIST, SUPPRESS, n` / `HIST, RESUME, n` | skip entry n / take it back |
| `HIST, MOVE, n, to` | reorder |
| `HIST, REPLAY` | re-run everything |
| `RUN, file.cmd` | run a script; each top-level statement becomes an entry |

After an edit, later entries that now fail stay in the history marked as
failed (red in the History panel) and are skipped, so you can fix them.

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

## 7. Commands

| Group | Commands |
|-------|----------|
| Primitives | `BLOCK, x,y,z, dx,dy,dz` · `CYL, x,y,z, r, h [, dx,dy,dz] [, angle]` · `TUBE, x,y,z, ro, ri, h [, axis]` · `CONE, x,y,z, r1, r2, h [, axis]` · `SPHERE, x,y,z, r` · `TORUS, x,y,z, ring_r, tube_r [, axis]` · `WEDGE, x,y,z, dx,dy,dz, ltx` |
| Booleans | `UNION, a, b [, c ...]` · `SUBTRACT, a, b [, c ...]` · `INTERSECT, a, b [, c ...]` (IDs or names; the result keeps the first body's name) |
| Blends | `FILLET, r` · `CHAMFER, d` (on the selected edges, or all edges of the selected bodies) |
| Transforms | `MOVE, b, dx,dy,dz` · `ROTATE, b, angle [, x,y,z [, dx,dy,dz]]` · `COPY, b, dx,dy,dz` · `MIRROR, b [, x,y,z [, nx,ny,nz [, copy]]]` |
| Bodies | `NAME, b, name` · `DELETE, b` · `CLEAR` |
| Selection | `PICK, kind, id [, S/A/U]` · `SEL ...` · `CM` · `CMSEL` · `CMDEL` · `PICKMODE, kind` |
| Settings | `/UNITS, MM/CM/M/IN` · `/TOL, value` (fuzzy booleans and selection tolerance) |
| Files | `EXPORT, STEP/BREP/STL, file [, body]` · `RUN, file` |
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
