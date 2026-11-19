---
name: strength-and-weight
description: A quick linear strength check of one solid (STRESS - largest stress, deflection, safety factor from its material), checks kept in the script with SAFETY, MAXSTRESS, DEFLECT and MASS, and TOPOPT to see where material carries the load. Use for "will it hold", "how much does it bend", "make it lighter".
commands: MATERIAL, CM, SEL, STRESS, TOPOPT, MASSPROP, ASSERT
---
# Strength and weight

STRESS is a quick check while designing (linear, one load case, a grid of
brick cells). It is not a full analysis: no contacts between parts, no
large deflections, no vibration. Say so when you report a result.

## Steps

1. **Material**: `MATERIAL, part, ALUMINIUM` (steel is assumed if none).
   The yield strength used is in the STRESS answer.
2. **Name the faces**: the faces held still and the faces the load acts
   on, as sets: `SEL, S, FACE, NORMAL, -1,0,0` then `CM, wall, FACE`;
   `SEL, S, FACE, LOC, X, 60` then `CM, tip, FACE`. Then `SEL, NONE`.
3. **Run it**: `STRESS, part, wall, tip, FORCE, fx, fy, fz` (N, shared over
   the loaded faces) or `..., PRESSURE, MPa`. The answer: largest stress
   and where, the 99.5 % value, largest deflection, safety factor on both,
   and a verdict. The part is coloured.
4. **Keep the check in the script** with the same arguments as numbers:
   `ASSERT, SAFETY(part, "wall", "tip", 0, 0, -400), GE, 2`,
   `MAXSTRESS(...)` in MPa, `DEFLECT(...)` in mm. The set names are quoted.
5. **Peaks at sharp inside corners** depend on the cell size: round the
   corner (`FILLET`) or run again with a smaller `h` (the last argument)
   to see whether the peak settles; trust the 99.5 % value more.
6. **Lighter**: `MASS(part)` in kg; `TOPOPT, part, fixed, loaded, FORCE,
   fx,fy,fz, keep [, rounds [, h]]` keeps that share of the material where
   it carries the load, as a mesh body to model a real part after. Then
   model the new part and check it with STRESS again.

```cmd
BLOCK, 0, 0, 0, 100, 20, 10
NAME, LAST, beam
MATERIAL, beam, STEEL
SEL, S, FACE, LOC, X, 0
CM, root, FACE
SEL, S, FACE, LOC, X, 100
CM, end, FACE
SEL, NONE
ASSERT, SAFETY(beam, "root", "end", 0, 0, -200), GE, 2
```

## Check the result

* `SAFETY(...), GE, 2` (or what the user asks; 1.5 is a common minimum
  for a known static load), `DEFLECT(...), LT, limit`.
* `MASS(part), LT, target` after making it lighter.
* `VALID(part)` after adding ribs or fillets to make it stronger.

## Mistakes to avoid

* The load or the fixed faces on the wrong faces: check the sets with
  `preview_selection` or `describe_entities` before running.
* A load given as a pressure in N or a force in MPa: FORCE is in N,
  PRESSURE in MPa (N/mm2).
* Presenting the result as a certified analysis. Real meshing, contacts
  and nonlinear solves belong in a separate analysis program.
* Bodies that are meshes: STRESS needs a solid (`TOSOLID` first).
