---
name: gears-and-cams
description: Involute gears (spur, helical, internal, rack, bevel, worm and worm wheel) placed at the right centre distance and phase so they mesh, and disc or barrel cams with a roller follower moved by CAMLIFT. Use for gear trains, gearboxes, cam mechanisms.
commands: GEAR, CAM, ROTATE, MOVE, CONTACT, MOTION
---
# Gears and cams

## Steps

1. **Parameters**: module `M`, tooth counts `Z1`, `Z2`, face width.
   Gears that mesh share the module (and the pressure angle, 20 by default).
2. **First gear**: `GEAR, x,y,z, M, Z1, width [, kind, helix, bore]`.
   The answer gives pitch, tip and root diameters. A tooth points along
   local X.
3. **Mating gear**: put it along X at the centre distance
   `M*(Z1 + Z2)/2`, and if Z2 is even turn it by `180/Z2` degrees about its
   own axis so a tooth falls into a gap.
   * inside an `INTERNAL` ring: at `M*(Zring - Z)/2`, as made;
   * a `RACK`: gaps at X = 0, 1, 2 ... pitches (pitch = pi x M); a gear above
     a gap at height `M*Z/2`, turned -90 degrees;
   * `BEVEL` pairs: give the mate's tooth count as the last argument and set
     the axes at right angles;
   * `WORM` (Z = number of starts) and `WORMWHEEL`: axes crossed, centre
     distance from both pitch radii.
   * helical pair: opposite helix angles (15 and -15).
4. **Cams**: `CAM, x,y,z, law, base, roller, width [, DISC/BARREL, bore]`.
   The law is text: `"R10/150 D30 F10/150 D30"` = rise 10 over 150 degrees,
   dwell 30, fall 10 over 150, dwell 30. It makes `cam_1` and
   `cam_1_roller`. Turn the cam with an angle parameter `A` and move the
   roller by `CAMLIFT(law, A)` so the follower tracks it.
5. **Make it move**: drive the angle parameter (assembly-and-motion skill):
   `MOTION, A, 0, 360, 36` checks for clashes all the way round.

```cmd
GEAR, 0, 0, 0, 2, 20, 10
NAME, LAST, g1
GEAR, 50, 0, 0, 2, 30, 10
NAME, LAST, g2
ROTATE, g2, 6, 50, 0, 0
ASSERT, OVERLAP(g1, g2), EQ, 0
```

## Check the result

* `OVERLAP(g1, g2), EQ, 0` (no clash) and `TOUCH(g1, g2)` or a small
  `GAP` (teeth in contact or with a little backlash).
* `BBOX(g).dx` = tip diameter `M*(Z + 2)` for a spur gear.
* Cam: the pressure angle in the CAM answer (keep it under about 30
  degrees), `OVERLAP(cam_1, cam_1_roller), EQ, 0` at several angles
  (`vary` on A).

## Mistakes to avoid

* Different modules on a pair, or the centre distance from the tip
  diameters instead of the pitch diameters.
* Forgetting the half-tooth turn: the teeth then sit tip to tip and overlap.
* Turning the gear about the origin instead of its own centre: give the
  centre in `ROTATE, g, angle, x, y, z`.
* Very small pinions: below about 17 teeth at 20 degrees real gears are
  undercut when cut; keep 17 or more unless the user asks otherwise.
