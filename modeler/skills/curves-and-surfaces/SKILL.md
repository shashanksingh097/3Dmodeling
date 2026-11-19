---
name: curves-and-surfaces
description: Smooth and freeform shapes from curves - lofts through sections, sweeps and pipes along paths with twist and scale laws, rail sweeps, spine lofts, NURBS curves and surfaces, networks and sewing, with checks for smoothness (ANALYZE). Use for ducts, vases, handles, blades, wings, bottles, car body panels.
commands: CIRCLE, RECT, SPLINE, ARC, HELIX, LOFT, SWEEP, PIPE, MORPH, RAILSWEEP, SPINELOFT, NURBS, NSURF, NETWORK, SEW, ANALYZE
---
# Curves and surfaces

## Steps

1. **Curves first**, each named: profiles (`CIRCLE, x,y,z, r [, nx,ny,nz]`,
   `RECT, x,y,z, w, h [, r, nx,ny,nz]`, `ELLIPSE`, `POLYGON`, `AIRFOIL`) and
   paths (`LINE`, `ARC` through three points, `SPLINE, (p1), (p2), ...`,
   `HELIX`, `CURVE, PARAM, fx, fy, fz, t0, t1` with angles in degrees).
2. **Pick the shape command**:
   * through sections: `LOFT, s1, s2, s3` (in order along the shape; `RULED`
     for straight sides, `CLOSED` for a ring, `GUIDE, g1, g2` to steer);
   * along a path: `SWEEP, profile, path [, twist, scale, ...]` with laws in
     t from 0 to 1 (`360*t` = one turn), `PIPE, path, r [, ri]` (hollow with
     ri), `MORPH` (the profile changes shape on the way);
   * between rails (a wing, a blade): `RAILSWEEP, profile, rail1, rail2, spine`;
   * sections on a curved centre line: `SPINELOFT, spine, s1, s2, s3`;
   * freeform: `NURBS` curves from control points, `NSURF` from rows,
     `NETWORK, u1, u2, ACROSS, v1, v2`, then `SEW` the surfaces into a
     solid.
3. **Draw a profile across the path at its start**, square to the path's
   direction there (give the normal: the path's start tangent).
4. **Check smoothness**: `ANALYZE, b` (zebra; every join judged G2, G1 or
   creased), `ANALYZE, b, CURVATURE` (the tightest bend radius and where),
   `ANALYZE, b, DRAFT, 0,0,1, 2`. `render` helps here: these are shapes
   where a picture says more than the face list.

```cmd
CIRCLE, 0, 0, 0, 10
CIRCLE, 0, 0, 30, 6
LOFT, LAST - 1, LAST
NAME, LAST, neck
ASSERT, VALID(neck)
ASSERT, BBOX(neck).dz, EQ, 30, 0.01
```

## Check the result

* `VALID(b)`, `PIECES(b), EQ, 1`, `VOL(b)` against a rough hand estimate
  (area of the profile times the path length).
* `section_profile` at a few heights reads the shape back as text.
* A pipe or sweep that must not run into itself: the command already
  checks; its error names the place (t) and the bend radius there.

## Mistakes to avoid

* Sections listed out of order, or two in one plane: LOFT refuses.
* A profile bigger than the tightest bend of its path: make it smaller,
  or the bend gentler (more spline points further apart).
* A sharp corner in a sweep path (a POLYLINE): use a SPLINE or an ARC.
* Profiles drawn along the path instead of across it: no thickness.
* NETWORK curves that do not all cross: every u curve must meet every v.
