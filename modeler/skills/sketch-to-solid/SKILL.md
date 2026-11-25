---
name: sketch-to-solid
description: Make a part from a 2D sketch - draw on a plane or a face, hold it with constraints and sizes until no freedom is left, then EXTRUDE or REVOLVE it as a new body, a boss or a cut. Use for plates with outlines, bosses on faces, pockets, slots and turned parts.
commands: SKETCH, SRECT, SCIRCLE, SLINE, SPOLY, SSLOT, SARC, SFILLET, SCON, SDIM, ENDSKETCH, EXTRUDE, REVOLVE
---
# Sketch to solid

## Steps

1. **Start the sketch**: `SKETCH, base, XY` (or `ZX`, `YZ`, a datum plane,
   or `SKETCH, boss, FACE, SEL` on a selected flat face, which also makes
   that face's body the default target).
2. **Draw** with S-commands in the sketch's u, v coordinates: `SRECT, u1,v1,
   u2,v2`, `SCIRCLE, u, v, r`, `SLINE`, `SPOLY, ..., CLOSE`, `SSLOT`, `SARC`.
   Geometry is numbered 1, 2, 3 in drawing order; a line's ends are `1.S` and
   `1.E`, a circle's centre `5.C`; `ORIGIN`, `H`, `V` are the sketch axes.
3. **Hold it**: `SCON` for relations (COINCIDENT, HORIZONTAL, EQUAL,
   TANGENT, CONCENTRIC ...) and `SDIM` for sizes, written with parameters
   (`SDIM, LENGTH, 1, W`). Each step reports the degrees of freedom left;
   0 means fully defined. A constraint that fights the others is refused
   and names them.
4. **Round corners** in the sketch with `SFILLET, 1.E, r` rather than with
   `FILLET` on the solid later: it is cheaper and always works.
5. `ENDSKETCH`, then:
   * `EXTRUDE, s, 10` (new body), `EXTRUDE, s, 5, ADD` (a boss on the
     sketch's body), `EXTRUDE, s, -8, CUT` (a pocket), `EXTRUDE, s, 0, CUT,
     part` (through all), `EXTRUDE, s, 10, NEW, , 10` (both ways).
   * `REVOLVE, s, V` (a full turn about the sketch's vertical axis) or about
     a construction line (`SLINE, ..., CONSTR`, then `REVOLVE, s, 5, 360`).
     The profile must stay on one side of the axis.

```cmd
W = 60
SKETCH, s1, XY
SRECT, 0, 0, W, 30
SDIM, LENGTH, 1, W
SCIRCLE, 15, 15, 4
ENDSKETCH
EXTRUDE, s1, 5
NAME, LAST, plate
ASSERT, HOLES(plate, 8), EQ, 1
```

## Check the result

* `sketch_state`-style questions: the sketch's answer lists freedom left;
  aim for 0 so later size edits move what you expect.
* After EXTRUDE: `VALID(b)`, `BBOX(b).dz`, holes from inner loops with
  `HOLES(b, d)`.
* After REVOLVE: `BBOX(b)` (twice the largest radius across), `VOL(b)`.

## Mistakes to avoid

* An open outline (a gap at a corner) or three curves meeting at one point:
  the error names the place; join them with `SCON, COINCIDENT`.
* A sketch on a face that is not flat, or a REVOLVE axis that crosses the
  profile.
* A body and a sketch (or parameter) with the same name: names are shared,
  so call the sketch `knob_s` and the body `knob`.
* Sizes typed as numbers when the user gave a parameter: use the parameter
  so editing it moves the sketch.
* Sizes the user typed into the boxes beside the cursor while drawing are
  already `SDIM` steps (a line's `LENGTH` and `ANGLE`, a rectangle's two
  `LENGTH`s, a circle's `RADIUS`): change those entries, do not add more.
