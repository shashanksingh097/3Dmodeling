---
name: frames-and-welds
description: Welded frames from structural members (square, rectangular and round tube, flat bar, angle, channel, I-beam) laid along the lines of a path, mitred or butted, with weld beads and a cut list of lengths and end angles. Use for tables, racks, stands, machine frames, trusses.
commands: POLYLINE, MEMBER, WELD, CUTLIST, HIDE, MATERIAL
---
# Frames and welds

## Steps

1. **Paths**: draw the centre lines with `POLYLINE, (x,y,z), (x,y,z), ...
   [, CLOSE]` (or the lines of a sketch). One member is made per straight
   piece. Name the path; hide it afterwards (`HIDE, top_path`).
2. **Members**: `MEMBER, path, profile, size [, MITRE/BUTT [, name
   [, turn]]]`. Profiles: `SQUARE 40x3`, `RECT 60x40x3`, `ROUND 30x2`,
   `FLAT 40x5`, `ANGLE 25x25x3`, `CHANNEL`, `IBEAM 100x200x8`. Members are
   named name_1, name_2 ... in path order. `turn` rotates the profile
   about the line (an angle facing the right way).
3. **Where members meet**: mitred corners on one closed path; members on
   their own paths are butted, so stop a leg's path at the underside of the
   rail (`H - T/2` for a rail of size T centred on height H).
4. **Welds**: `WELD, a, b, size` for one joint or `WELD, ALL, 4` for every
   joint. Each bead is a body (weld_1 ...).
5. **Cut list**: `CUTLIST` (or `CUTLIST, cuts.csv`): quantity, profile,
   length and end angles, with the weld length.
6. A path line is the **centre** of the member, so a frame drawn on the
   outer size `W` comes out `W + T` across. Draw the path inset by `T/2` to
   keep the outer size.

```cmd
POLYLINE, (0,0,0), (500,0,0)
NAME, LAST, p
MEMBER, p, SQUARE, 40x3, BUTT, beam
HIDE, p
ASSERT, BBOX(beam_1).dx, EQ, 500, 0.01
```

## Check the result

* `VALID(member_1)` and the lengths in CUTLIST against what was asked.
* `OVERLAP(a, b), EQ, 0` between members (butted, not cutting into each
  other); `GROUPS(), EQ, 1` once welded (everything holds together).
* Outer size: `BBOX` of the frame members.

## Mistakes to avoid

* Paths drawn on the outer size when the user gave outer sizes: the frame
  is one member size too big.
* Legs that run up into the top rails (path to H instead of H - T/2):
  they overlap the rails.
* Very many welds on a large frame are slow to make; weld the joints that
  matter, or leave WELD to the end.
