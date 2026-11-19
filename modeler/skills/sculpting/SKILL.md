---
name: sculpting
description: Sculpt mesh bodies with brushes (DRAW, CLAY, INFLATE, SMOOTH, FLATTEN, PINCH, CREASE, GRAB) along recorded strokes, mirrored, with masks to protect areas and REMESH for detail. Use for organic shapes - characters, faces, handles shaped to the hand, rocks, terrain.
commands: TOMESH, REMESH, STROKE, SCULPT, MASK, SMOOTH, SIMPLIFY, FITSURF
---
# Sculpting

Sculpted shapes are where text tools say least: faces and features do not
describe them well. Use `render` (when the model can see pictures) to look
at the result, and say that you did.

## Steps

1. **A mesh with enough points**: start from a solid (`SPHERE`, a loft ...),
   `TOMESH, b`, then `REMESH, b, 1` (edges no longer than 1; smaller for
   finer detail, more triangles).
2. **Strokes**: `STROKE, S1, "x,y,z  x,y,z  ..."` records points on or near
   the surface (the Sculpt tab in the window writes these as the user
   drags). Find surface points with `probe_ray` from outside toward the
   body.
3. **Brushes**: `SCULPT, b, brush, radius, strength, stroke [, sym [, detail]]`.
   DRAW raises (negative strength digs), CLAY builds flat layers, INFLATE
   puffs out, SMOOTH evens, FLATTEN, PINCH, CREASE (a sharp groove; give a
   detail like 0.25 so the triangles there are split first), GRAB moves
   what is under the first point to the last.
   `sym` X, Y or Z mirrors the stroke across that plane through the origin
   (both sides of a face at once).
4. **Masks**: `MASK, b, PAINT, x,y,z, r` (or along a stroke) freezes an
   area; `ERASE`, `INVERT`, `ALL`, `CLEAR`.
5. **Finish**: `SMOOTH, b` for overall noise; `SIMPLIFY, b, tol` to make it
   lighter; `FITSURF` if it must become a smooth CAD surface.

```cmd
SPHERE, 0, 0, 0, 10
NAME, LAST, blob
TOMESH, blob
REMESH, blob, 1
STROKE, S1, "0,-10,0  0,-10,3"
SCULPT, blob, INFLATE, 3, 0.5, S1
ASSERT, VALID(blob)
```

## Check the result

* `VALID(b)` (still closed), `BBOX(b)` for overall size.
* `SYMMETRIC(b, "YZ")` when every stroke was mirrored.
* The SCULPT answer: how many points moved and by how much at most; 0
  points means the stroke missed the surface.
* `render` for the look; `section_profile` for a profile through it.

## Mistakes to avoid

* Sculpting a coarse mesh (few points move, the result is faceted):
  REMESH first.
* Stroke points far off the surface: nothing moves. Probe for surface
  points.
* A radius far larger than the feature: the whole side moves.
* Forgetting `MASK, b, CLEAR` after protected work: later strokes then skip
  that area.
