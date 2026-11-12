# M4 part 3: sweeps steered by rails

`RAILSWEEP` sweeps a profile along a path while one or two rail curves
steer it. With one rail, the profile turns (and, if asked, scales) so a point
of it stays on the rail. With two rails it turns, moves and scales to span
both, so a wing can be swept between its leading and trailing edges. This
meets the last part of the M4 exit test: a wing swept between two rails
(`scripts/wing_rails.cmd`). The command is in LANGUAGE.md section 19.

## Design

* **Stations along the path.** The path is cut into sections with the same
  rotation-minimizing frames as `SWEEP` (side, up, tangent). At each one, the
  plane square to the path cuts each rail. The crossing is found by walking
  along the rail (600 samples), picking the sign change that carries on from
  the last station, then bisecting. So a rail can be drawn in either
  direction, and one that winds round (a helix) is followed turn by turn.
* **A 2D map per station.** In section coordinates, the rail points at the
  start (g0, h0) and at the station (g, h) give the map:
  * one rail: turn by the change of angle of g about the path, scale by
    |g| / |g0| (`SCALE`) or 1 (`TURN`);
  * two rails: the similarity that takes g0 to g and h0 to h, times an
    optional thinning square to the line between the rails (the `thick`
    law).
  The map is lifted to 3D as start frame to station frame, and the profile is
  placed there with a true similarity (`gp_Trsf`) when it is one, so curves
  stay exact, or an affine `GTransform` when the thickness law stretches it.
* **A smooth loft** through the placed sections (`ThruSections`), as for the
  law sweeps. The number of sections is chosen from a first look at 40
  stations: how much the profile turns and grows, and how much the path bends.
* The volume of a straight two-rail taper matches the integral of the section
  area to 0.1%, and a section cut half way spans the rails to 0.01.

## Tests

`tests/test_rails.py`: section position, chord and rise between straight
rails; the volume of a tapered sweep; the thickness law; one rail turning a
strip round a post; `SCALE` and `TURN`; rails that are too short or meet; the
wing example with its tip section between the rail ends; the form.

## Next in M4

Spine lofts (sections placed along a curved center line), text, parametric
surfaces, direct face editing.
