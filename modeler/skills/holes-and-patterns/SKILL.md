---
name: holes-and-patterns
description: Holes (through, blind, counterbored, countersunk, threaded) and repeated features - bolt circles, grids, rows - with HOLE, PATTERN and ARRAY ... CUT, checked with HOLES(). Use for flanges, plates with bolt patterns, perforated panels.
commands: HOLE, PATTERN, ARRAY, SUBTRACT, THREAD, SEL, ASSERT
---
# Holes and patterns

## Steps

1. **One hole**: `HOLE, b, x, y, z, d` drills from the point (x, y, z) on
   the body's surface, straight into it (through by default).
   * blind: `HOLE, b, x,y,z, 6, 10` (10 deep);
   * counterbore: `HOLE, b, x,y,z, 6, 0, CBORE, 11, 4` (11 across, 4 deep);
   * countersink: `HOLE, b, x,y,z, 6, 0, CSINK, 12`;
   * a drill point: `..., SIMPLE, , , 118`;
   * on a side face: give the direction (`..., dx, dy, dz` at the end).
2. **Repeat it** right after with `PATTERN`, which copies what the last
   steps did to the body, all copies in one step:
   * a bolt circle: `PATTERN, POLAR, flange, 1, 6` (6 around Z through
     the origin; `, angle, x,y,z, dx,dy,dz` to change that);
   * a grid: `PATTERN, LINEAR, plate, 1, 10, 8,0,0, 5, 0,8,0`.
   The 1 is how many steps back to copy (the HOLE).
3. **Very many cuts of any shape**: make one tool body and
   `ARRAY, LINEAR, tool, 20, 5,0,0, 15, 0,5,0, CUT, plate` (cuts all of them,
   the original too, in one boolean).
4. **Threads**: select the hole wall and `THREAD` (see the
   fasteners-and-threads skill).
5. Parameters for the count and the circle (`N = 6`, `PCD = 80`) so
   `vary` can prove the pattern follows them.

```cmd
CYL, 0, 0, 0, 50, 12
NAME, LAST, flange
HOLE, flange, 40, 0, 12, 8
PATTERN, POLAR, flange, 1, 6
ASSERT, HOLES(flange, 8, 1), EQ, 6
```

## Check the result

* `HOLES(b, d), EQ, n` counts round holes of diameter d; `HOLES(b, d, 1)`
  only through holes, `HOLES(b, d, 0)` only blind ones.
* `describe_body` lists each hole group with its pattern (circle and step
  angle, or grid), depth and counterbore.
* `vary` on N with a few values and the HOLES check.

## Mistakes to avoid

* A hole point inside the body or off its surface: put it on the face
  the hole starts from (z = the top for a plate on XY).
* One `CYL` + `SUBTRACT` per hole in a loop: slow for many holes and more
  steps to edit. Use HOLE + PATTERN or ARRAY ... CUT.
* A polar pattern around the wrong centre: the default axis is Z through
  the origin; give x, y, z when the part is elsewhere.
* Holes that break through an edge or into each other: check with
  `PIECES(b), EQ, 1` and the HOLES count.
