---
name: assembly-and-motion
description: Assemblies - reusable parts placed as copies, parts mated against each other, a mechanism moved by a parameter (DRIVE, MOTION), clash, contact and gravity checks, and the parts list. Use for anything with more than one part, hinges, linkages, mechanisms.
commands: *PART, INST, MATE, JOINT, JOINTS, ROTATE, DRIVE, MOTION, GRAVITY, CONTACT, BOM, NAME, MATERIAL, CLASH, CLASHFIX
---
# Assemblies and motion

## Steps

1. **Parts used more than once** go in a part block, with their sizes as
   part parameters:
   `*PART, pin, D=6, L=8` ... `*ENDPART`, then `INST, pin, x, y, z [, angle
   [, dx,dy,dz]] [, D=8]` for each copy. Editing the block updates every
   copy. Name each copy right after: `NAME, LAST, pin_a`. Parts kept in a
   file: `LIB, LINK, bolt` (follows the file) or `LIB, LOAD, bolt` (a copy).
2. **Materials** on every part (`MATERIAL, base, ALUMINIUM`) so masses,
   GRAVITY and the parts list are right.
3. **Place parts** by coordinates from the same parameters, or with
   `MATE, kind, fixed item, moving item [, value] [, FLIP]` (COINCIDENT,
   CONCENTRIC, DISTANCE, ANGLE between FACE, EDGE, VERTEX or DATUM items).
4. **Motion**: joints that stay solved. `JOINT, REVOLUTE, EDGE, 2, EDGE,
   16, A [, LIMITS, 0, 110]` hinges the second item's body on the first
   (also FIXED, SLIDER, CYLINDRICAL, BALL, PLANAR; couplings `JOINT, GEAR,
   J1, J2, ratio`, BELT, RACK, SCREW). A positive value moves the part away
   from the fixed one (REVERSE turns that round). Chains and closed loops
   (four-bar linkages) are solved together; `JOINTS` lists each joint, its
   value now, what it leaves free and any that fight, as data. Hold a joint
   with one parameter per motion (`A = 30`). `DRIVE, A, 75` holds a value
   without touching the history; `MOTION, A, 0, 120, 12` checks every pair
   of parts at each position and puts A back.
5. **Will it stand up**: `GRAVITY, ground [, "fastened parts"]`: floating
   parts, parts that tip off, parts only held at their sides, gaps and
   overlaps. List bolted or hinged parts as fastened.
6. **Parts list**: `BOM` (or `BOM, parts.csv`); copies of a part with the
   same values are counted together.
7. **Fixing a clash**: `CLASH` lists the overlaps. `CLASHFIX, a, b, CUT
   [, clearance]` cuts b's shape out of a (b stays); `CLASHFIX, a, b, MOVE
   [, clearance [, direction]]` moves a the shortest way clear (AUTO tries
   the six axes and straight away). Add `PREVIEW` as the last word first:
   nothing changes, the result is marked and its report `CLASHFIX` says the
   volume removed or the move. Moving is right for a part placed wrong;
   cutting is right for a pocket or a hole the other part needs.

```cmd
BLOCK, 0, 0, 0, 40, 30, 5
NAME, LAST, base
BLOCK, 0, 0, 5, 40, 30, 2
NAME, LAST, lid
ASSERT, TOUCH(lid, base)
ASSERT, OVERLAP(lid, base), EQ, 0
```

## Check the result

* No clashes: `OVERLAP(a, b), EQ, 0` for each pair that must not touch,
  or `assembly_check` for all pairs at once.
* Seated: `TOUCH(a, b)`; held together: `GROUPS(), EQ, 1`.
* Through the motion: `MOTION` says "no parts run into each other" and
  the smallest gap; a clash gives the range of the parameter.
* Pins in holes: `CLEARANCE(pin, base), GE, 0.01` (or the fit you want).

## Mistakes to avoid

* Rotating about the origin instead of the hinge line: use a JOINT, or
  give the point and direction of the axis in ROTATE.
* A joint that fights (JOINTS says FIGHTS): two joints that want different
  places, or a held value outside its limits. Remove one or free a value.
* Parts that stick through each other at some angles only: a check at one
  position is not enough; run MOTION over the whole range.
* Using body numbers for copies (`4`, `5`): name them.
* GRAVITY reports a hinged or bolted part as tipping: list it as fastened
  once the hinge or bolts are really there.
