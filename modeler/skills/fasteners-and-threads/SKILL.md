---
name: fasteners-and-threads
description: Standard screws (cap, hex, countersunk, button, set), nuts, washers, pins, threaded inserts, ball bearings, circlips and keys from the ISO/DIN tables (and inch screws), with their matching holes, real helical threads on shafts and in holes, clearance holes and ISO 286 fits checked with CLEARANCE and FITS. Use for anything bolted, screwed or pinned together.
commands: FASTENER, THREAD, HOLE, CLEARANCE, FITS, CONTACT, NOTE
---
# Fasteners and threads

## Steps

1. **Clearance hole first**: `HOLE, plate, x,y,z, d` with the ISO medium
   clearance (M3 3.4, M4 4.5, M5 5.5, M6 6.6, M8 9, M10 11, M12 13.5);
   a counterbore for cap screws a little wider and deeper than the head
   (M6: `..., 0, CBORE, 11, 6.5`; M8: `..., 0, CBORE, 15, 8.6`).
2. **Standard parts**: `FASTENER, kind, size, x,y,z [, length [, thread
   [, dx,dy,dz [, hole [, fit]]]]]` with kind `CAP` (socket head),
   `HEXBOLT`, `CSK` (countersunk, flush with the seat), `BUTTON`, `SET`,
   `NUT`, `WASHER`, sizes M3 to M24; inch sizes `1/4-20`, `#10-24` for CAP,
   HEXBOLT, SET, NUT, WASHER (lengths stay in mm: 25.4 per inch). Also
   `DOWEL` and `SPRINGPIN` (size = diameter), `INSERT` (heat-set, M2-M8),
   `BEARING` (608, 6000-6005, 6200-6205), `CIRCLIP` (shaft 8-40), `KEY`
   (`8x7`, or the shaft diameter). **Give the part it goes into as
   `hole`** and FASTENER cuts the matching hole in the same step: `CLEAR`
   (default for screws; a CSK gets its countersink), `TAP`, `CBORE` (the
   head sinks into a counterbore) or `FIT` (default for pins, inserts and
   bearings): `FASTENER, CSK, M5, 20,10,8, 16, , , , , plate`. The BOM
   counts the same standard parts together. (x, y, z) is where the part sits: the
   underside of a head, the top of a nut under a plate; the default
   direction is down (0,0,-1). Stack them: washer at the plate top `T`,
   screw head at `T + washer thickness` (1.6 for M8).
   Name each one: `NAME, LAST, screw`.
3. **Plain or real thread**: fasteners are plain cylinders unless the
   thread argument is `REAL`. Real threads are slow to make and to check,
   so use them only where they matter.
4. **Threads on your own parts**: select the round face, then `THREAD`
   (`THREAD, , 10` = 10 long from the free end, `THREAD, 1` = fine pitch,
   `..., LEFT`). A shaft gets an outside thread, a hole wall an inside one;
   the size comes from the diameter (an 8 mm shaft or a 6.8 mm tapping
   hole is M8).
5. **Fits**: `FITS, H7/g6, 8` gives both limits and the clearance range;
   `NOTE, FIT, H7` on a picked face puts it on drawings.

```cmd
BLOCK, 0, 0, 0, 40, 40, 8
NAME, LAST, plate
HOLE, plate, 20, 20, 8, 6.6
FASTENER, CAP, M6, 20, 20, 8, 20
NAME, LAST, screw
ASSERT, CLEARANCE(screw, plate), GE, 0.2
```

## Check the result

* `CLEARANCE(screw, plate), GE, 0.2`: every shaft in its hole has room;
  `fit_check` gives diameters, axis offset and engaged length.
* `OVERLAP(a, b), EQ, 0` (no clash) and `TOUCH(washer, plate)` (seated).
* `assembly_check` for a whole bolted joint: what touches, what floats.
* A real thread: `VALID(b)`; a threaded pair (bolt in nut) shows as
  state "thread" in `contact`.

## Mistakes to avoid

* A screw placed with its tip at the plate top: (x, y, z) is under the
  head, and the shank goes along the direction (down by default).
* A hole the same size as the screw (no clearance): CLEARANCE is 0 or
  negative.
* A nut with a real thread that does not line up with the bolt's thread:
  they overlap a little; turn the nut about its axis until `OVERLAP` is 0.
* Real threads everywhere: a large assembly gets very slow. Plain
  fasteners are enough for layout, mass and the parts list.
