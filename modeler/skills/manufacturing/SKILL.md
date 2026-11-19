---
name: manufacturing
description: Get a part ready to make - 3D printing checks (overhangs, thin walls, trapped hollows, the best build direction), 2.5D milling paths written as G-code, and moulding (draft, parting line, the two mould halves with shrink). Use for "can I print this", "make the toolpath", "make a mould for it".
commands: PRINTCHECK, MILL, DRAFT, PARTING, MOLD, THICK, CM
---
# Manufacturing

## 3D printing

1. `PRINTCHECK, part` (built along +Z, 45 degree overhangs, 0.8 walls),
   `PRINTCHECK, part, BEST` ranks the six build directions by the support
   needed, `PRINTCHECK, part, -Y, 50, 1.2` sets direction, angle and wall.
2. The answer: footprint and height, area on the bed, overhang area and
   faces, walls thinner than the limit, closed hollows (need a drain hole),
   loose pieces, and "ready to print" or what to look at.
3. Keep it in the script: `ASSERT, OVERHANGS(part, 45, "+X"), EQ, 0, 1`
   (area in mm2 that needs support; the last number is the tolerance),
   `ASSERT, MINWALL(part), GE, 0.8`.

## Milling (2.5D, along Z)

1. Name the faces to machine: `SEL, S, FACE, LOC, Z, 6` then
   `CM, floor, FACE`.
2. `MILL, part, POCKET, floor, tool, step_down [, step_over [, file.nc]]`
   clears down to the floor; `OUTLINE` cuts round a face's outline;
   `FACE` skims a top face. The answer gives passes, cutting length and
   time; the path shows in the view; with a file name it writes G-code.
3. Coordinates are the part's own: tell the user to set the machine zero
   to match and to check the G-code in their machine's simulator.

## Moulding

1. **Draft** on the side faces: select them (`SEL, S, FACE, BODY, part`,
   then `SEL, U, ...` to drop the top and bottom) and `DRAFT, 1` to `2`.
2. `PARTING, part [, dx,dy,dz [, angle]]`: which faces come out of which
   half, faces that need draft, undercuts, and the parting line (flat or
   stepped). Fix what it lists first.
3. `MOLD, part [, margin [, shrink %]]` makes `part_top` and
   `part_bottom` round the part (the part stays). Shrink for ABS is about
   0.5 %.

```cmd
CYL, 0, 0, 0, 20, 10
NAME, LAST, cap
SEL, S, FACE, TYPE, CYLINDER
DRAFT, 2
SEL, NONE
PARTING, cap
MOLD, cap, 6, 0.5
ASSERT, VALID(cap_top)
```

## Mistakes to avoid

* DRAFT on faces that face the pull direction (top, bottom): it tilts side
  faces only; select only the sides.
* A selection carried over from other bodies (`SEL, INVE` selects across
  every body): narrow it with `SEL, S, FACE, BODY, part` first.
* Calling a part "ready" from one check: printing needs walls and hollows
  checked too; moulding needs PARTING clean before MOLD.
* G-code presented as ready to run: it is a starting point to simulate.
