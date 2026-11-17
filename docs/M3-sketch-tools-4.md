# Spline editing (PLAN.md item 7, third part)

What came in: trim, extend and split for sketch splines, splines as
cutters, a fillet between a spline and a line or arc, `ON` and `TANGENT`
constraints with a spline, and `SJOIN` (join curves into one spline, or
turn one curve into a spline).

## Design

**Positions along a spline.** The trim and split code works with a
position along each curve (0..1 along a line, degrees round an arc). A
spline uses a fraction of its OCCT parameter range (0..1), or 0..360 for a
closed spline, so the code that picks the piece to trim (`trim_piece`)
works on splines unchanged. `modeler/sketch/spline.py` holds this and the
other spline math: the OCCT curve (cached by its points), feet, tangents,
crossings (`Geom2dAPI_InterCurveCurve` against the carrier of a line,
circle, ellipse or spline).

**Cutting a spline** (`spline.pieces`). A sketch spline is the curve
through its points, so a piece is again a spline through points: the cut
point, the old points inside the range (the same x entries, so their
constraints carry over by renaming `3.K4` to `7.K1` and so on), and one
extra point half way along each span a cut shortened. Without that extra
point a cut span straightens noticeably; with it the piece stays within a
small fraction of the old curve. A point the old spline ran through goes
to one piece only; a cut exactly at such a point makes it the end of the
first piece.

**Constraints.** `ON` a spline is the signed distance from the point to
the spline built from the current point values (OCCT projection), so the
solver's finite differences see the spline move as its points move.
`TANGENT` with a spline is at the spline's end nearer the other curve
(chosen once, stored in the constraint): the sine of the angle to a line,
or the cosine of the angle to an arc's radius at the spline's end. Both
rebuild the OCCT curve on each evaluation; it is cached by point values,
and the sketches stay quick (the editing tests run in under a second).

**Fillet.** The existing arc-line fillet finds the centre where the
offset carriers cross. A spline's offset is found point by point: the
sign changes of "centre's gap to the other offset carrier" along 200
samples, each closed in by halving. The spline is then cut back with
`pieces`, the line or arc end moves as before, and the arc is held
`TANGENT` to both.

**SJOIN.** The chain is found with the offset code's `_chains`, sampled
(lines at their ends and thirds, arcs and ellipses every 30 degrees,
splines at their points) and interpolated. Corners are rounded off, which
is the point of a spline. Constraints on the chain's two free ends move to
the spline's ends; the rest go and are listed.

## Gotchas

- The projection skips the ends of an open curve; `_foot` checks both
  ends too.
- A line's carrier is a long trimmed line (ten times the sketch size), not
  an infinite one, so crossings stay finite.
- After a fillet the corner point is off the shortened spline, so it is
  held `ON` the line or arc only, not on the spline.
- A test sketch whose lines are not joined by `COINCIDENT` drifts when a
  fillet solves; real sketches join them as they are drawn.

## Still open in item 7

An offset of a spline, and an offset of a chain that crosses itself.
