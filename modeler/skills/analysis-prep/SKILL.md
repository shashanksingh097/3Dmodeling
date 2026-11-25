---
name: analysis-prep
description: Get geometry ready for the separate analysis app - middle surfaces of thin parts with their thickness (MIDSURFACE), beam centre lines with section values (BEAMS), the fluid inside pipes and housings (FLUIDVOLUME), air round a model (ENCLOSURE), touching parts that share faces (SHAREFACES, IMPRINT) and fewer, cleaner faces (MERGEFACES), spot weld points (SPOTWELD). Use for "shell model", "spot welds", "beam model", "flow volume", "mesh these as one", "clean it up for meshing".
commands: MIDSURFACE, SPOTWELD, BEAMS, FLUIDVOLUME, ENCLOSURE, SHAREFACES, IMPRINT, MERGEFACES, CM, CMRENAME, CHECK, EXPORT
---
# Getting parts ready for analysis

This program prepares geometry only. Meshing and solving happen in the
separate analysis app, which reads the STEP (or BREP) file. Say so when the
user asks for a mesh or a full analysis here.

## Steps

1. **Thin parts (sheet metal, shelled housings, tubes)**: `MIDSURFACE,
   part` makes a new surface body in the middle of the walls. Its report
   `MIDSURFACE` gives the thickness of each face (`faces`), which walls were
   paired and which faces were left out as too thick (`left_out`). With one
   thickness the walls meet at their corners (`joined: true`); with several
   each face is offset on its own and flat faces are carried on (or cut
   back) until they meet: steps, L and T joins stay closed (`gaps_closed`,
   and `free_edges` counts the edges with one face: the outline plus any gap
   left). `EXPORT,
   STEP` names each face "thickness 2" for the shell thickness.
   `MIDSURFACE, part, 3` only takes walls up to 3 thick.
2. **Frames**: `BEAMS, ALL` (or the members) makes one curve body with a
   line per member, joined where the ends meet. The report `BEAMS` lists each
   line's ends, length, area, `iy`/`iz` (second moments about the section's
   main directions, `y_dir` is the first) and `j` (torsion constant: exact
   for round sections, thin-wall estimate for tubes and open sections).
   MEMBER bodies keep their profile and size.
3. **Flow inside a pipe, valve or housing**: `FLUIDVOLUME, part` closes each
   opening (a flat end face with a hole) with a cap and gives the inside as
   new solid(s). The report lists the openings and, for each fluid body, the
   faces that close them (inlets and outlets). If an opening is missed, pick
   its end face and use `FLUIDVOLUME, part, SEL`, or give the face IDs.
4. **Air round a model**: `ENCLOSURE, ALL, BOX, 20` (or `CYLINDER`, along
   Z, or `SPHERE`), or six margins `"-X +X -Y +Y -Z +Z"` for more room
   behind a part in a flow. The report names the outer faces (`XMIN` ...
   `ZMAX`, `SIDE`/`TOP`/`BOTTOM`, `OUTER`) and `WALLS` (the model's faces),
   by face ID, for the boundary conditions.
5. **Parts meshed as one connected piece**: `SHAREFACES, ALL, CHECK` lists
   touching pairs and whether they share their faces; `SHAREFACES, ALL`
   splits them where they touch so both use the same face there. To make
   only a contact patch its own face (for a load), `IMPRINT, plate, pad`.
6. **Faces that trouble a mesher**: `CHECK, part, FLAWS, 0.2` lists slivers
   and short edges; `MERGEFACES, part` joins faces on the same surface
   (seams), `MERGEFACES, part, SMALL, 0.2` also removes slivers under 0.2
   wide. The report says what is left.
7. **Spot welds between sheet parts**: `SPOTWELD, lid, box, 12, 25` puts a
   weld point every 25 along edge 12 (centred, at least half a pitch from
   the ends; `margin` and the nugget `dia` come next), each halfway between
   the two parts. They are a body of points `spotwelds` and a named set;
   `EXPORT, STEP` names each point "spot weld 3; joins lid + box; nugget
   5". The report lists every weld with its point and the `gap` between the
   parts there. Pick the edge where the parts lap (the menu on a picked edge
   offers it when another part touches).
8. **Name the faces the analysis needs** (inlet, fixed face, loaded face):
   pick them and `CM, inlet, FACE`; `CMRENAME, top, inlet` renames a set.
   `EXPORT, STEP` writes every face, edge and point set by name, so the
   analysis app finds them without picking again (a face in two sets gets
   "fixed; outside"). FLUIDVOLUME makes `<fluid>_opening_1` ... and
   ENCLOSURE makes `enclosure_xmin` ... `enclosure_walls` itself. `IMPORT,
   STEP` reads the names back as sets. `describe_model` lists the sets.

```cmd
BLOCK, 0, 0, 0, 100, 50, 2
NAME, LAST, bracket
BLOCK, 0, 0, 0, 2, 50, 40
UNION, bracket, LAST
MIDSURFACE, bracket
ASSERT, AREA(bracket_mid, "BODY"), BETWEEN, 6890, 6910
```

## Check the result

* A middle surface's area: `AREA(name_mid, "BODY")`, about the wall's
  length times width (to the middle of the corners).
* A fluid body: `VOL(part_fluid)` and `VALID(part_fluid)`.
* After SHAREFACES: `SHAREFACES, ALL, CHECK` says "all share their faces".

## Mistakes to avoid

* MIDSURFACE on a block: walls must be thinner than they are wide; a thick
  part has no middle surface (the answer says the faces left out).
* FLUIDVOLUME on a pipe whose ends are not flat: pick the end faces, or cut
  the ends flat first.
* Promising a mesh, contacts or results: those belong to the analysis app.
