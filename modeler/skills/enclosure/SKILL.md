---
name: enclosure
description: Plastic enclosures and moulded cases - a hollow box with even walls, a lip and groove between two halves, screw bosses with ribs, snap hooks, vents, ribs and draft. Use for housings, cases, covers and lids.
commands: BOARD, BLOCK, SHELL, LIP, BOSS, SNAP, VENT, RIB, DRAFT, FILLET, MATERIAL, THICK, PRINTCHECK
---
# Enclosure

## Steps

0. **A circuit board inside?** `BOARD, "main.kicad_pcb", pcb` (or an IDF
   `.emn`) makes the board and its parts. Size the case from its report,
   not from a picture: inside = `envelope` (board and parts, connectors
   over the edge included) plus a clearance (1 to 2 mm round, 2 mm over
   `tallest_top`); put a `BOSS` under each of `mounting_holes` (hole 2.5
   for an M3 self-tapping screw), standing up to the board's underside, and
   lift the board by the boss height (`MOVE`, the board and the
   `pcb_parts` layer). Connectors at an edge (J1 ...): cut their opening
   through the wall from their `box`. Part heights marked
   `height_from: guess` are guesses: ask, or leave more room.
1. **Parameters**: outer size `W`, `D`, `H`, wall `T` (2 to 3 mm for
   moulded plastic), and the material: `MATERIAL, case, ABS`.
2. **Outer shape**: `BLOCK` (or a sketch + `EXTRUDE` for a shaped outline);
   round the vertical outer edges now if wanted, before the shell.
3. **Hollow it**: select the open face and `SHELL, T`
   (`SEL, S, FACE, LOC, Z, H` for an open top). With no face selected and
   the body selected it becomes hollow and closed.
4. **Two halves**: make the base and the lid as two shells. On the base's
   rim face `LIP, , 2, 0.8` (a band 0.8 wide standing 2 up, along the inside
   edge of the selected face); on the lid's rim the same with
   `GROOVE, 0.2` for clearance.
5. **Screw bosses**: `BOSS, case, x,y,z, h, od, hole [, ribs]` with the foot
   on the inside face; give the direction (`..., 0,0,-1`) when the boss hangs
   down from a top. A hole of 2.5 suits a self-tapping M3.
6. **Snap hooks**: `SNAP, part, x,y,z, length, width, thickness [, overhang]
   ..., dx,dy,dz, hx,hy,hz` (direction it stands, then the way the catch
   faces). SNAP reports the bending strain; keep it under the material's
   limit (about 2 % for ABS).
7. **Vents**: select the flat face, then `VENT, count, length, width
   [, pitch, angle]`.
8. **Ribs**: an open sketch line, then `RIB, sketch, t, part`; ribs about
   half to two thirds of the wall.
9. **Draft** for moulding: select the side faces, `DRAFT, 1` (degrees).

```cmd
BLOCK, 0, 0, 0, 60, 40, 20
NAME, LAST, base
SEL, S, FACE, LOC, Z, 20
SHELL, 2
SEL, NONE
ASSERT, MINWALL(base), GE, 1.9
```

## Check the result

* `VALID(b)`, `PIECES(b), EQ, 1` after every boss, hook and vent.
* Walls: `MINWALL(b), GE, T - 0.1` right after the shell (later the lip,
  ribs and vents count as thin walls too), or `wall_thickness` for where.
* Halves: `contact(base, lid)` touching on faces, `OVERLAP(base, lid), EQ, 0`.
* Around a board: `OVERLAP(case, U1), EQ, 0` for the tall parts (or
  `CLEARANCE`), and the bosses meet the board's mounting holes.
* Ready to make: `PRINTCHECK` or the manufacturing skill; `PARTING` for a
  mould.

## Mistakes to avoid

* Rounding inside edges before `SHELL`: the shell can fail; round outer
  edges before, inner ones after.
* A boss or hook placed on the outside: its foot point must be on the inside
  face (z = H - T under a top of height H).
* A lip on the wrong face: select the rim face (the thin face at the open
  side), not the outside.
* Walls of very different thickness (a 6 mm boss on a 2 mm wall sinks when
  moulded): use ribs and hollow bosses instead.
