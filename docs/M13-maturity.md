# M13: a dependable modeler (after 0.5.0)

Up to 0.5.0 the work added commands. This milestone makes what is there
dependable. It follows the user's "product maturity" document of 2026-11-19.
The aim is not more commands. It is confidence: a user can build a
non-trivial model, change it, reopen it, inspect it, document it and export
it without workarounds.

Rules for this milestone:

* Reliability before new commands. Improve an existing command rather than add
  one that overlaps it.
* Every item starts with test models and an acceptance test that fails, then
  the fix. A feature is done when it holds up from a saved project (save,
  reopen, edit, rebuild, export), not only in a fresh session.
* Meshing for analysis stays out: no hexahedral or quad meshing, no block
  decomposition, no solver setup. Those belong to a separate meshing app
  that comes later. Small mesh tools for modelling, sculpting, checking and
  file exchange stay.
* The command history stays the one record. Anything the assistant does is
  a command in it, and can be undone.

## Where the app stands (checked against the code on 2026-11-19)

| Area in the document | Status | What exists | What is missing |
|---|---|---|---|
| 3.1 Reference stability | partial | Picks store a fingerprint and the step that made the entity; a pick is repaired only when the match is unique, never guessed (`core/refs.py`). Saved projects keep the IDs and pins. `SELFOR` writes picks by meaning. | Names from parents for faces made by booleans and fillets; split, merge and vanish rules; fingerprints for `SEL` ID lists and named sets; a list of every reference and its state; long-history tests through save and reopen. |
| 3.2 Sketcher | partial | Own solver reports degrees of freedom, redundant (repeated) and conflicting constraints; trim, extend, offset, fillet, split on lines, arcs, ellipses and splines. | Tangent and near-tangent trims with many crossings; offsets of closed chains and splines that cross themselves; constraints kept through move and copy; which entity causes a failure, shown in the view; large-sketch and edit-cycle tests. |
| 3.3 Sculpting topology | partial | Dynamic detail splits long edges under the brush and collapses short ones nearby; `REMESH` keeps the mask. | Smooth density changes, symmetry and sharp edges kept while remeshing, checks for cracks and flipped triangles, long-session tests. |
| 3.4 Scan to CAD | partial | `FITSURF`, `SEGMENT`, `RECONSTRUCT` (planes, cylinders, cones, spheres, freeform). | A deviation map with tolerance bands, max/RMS per region, outliers, holes and low-confidence regions; tolerance-driven refinement; continuity across region boundaries. |
| 3.5 Healing imports | partial | `CHECK`, `HEAL`, `CLEAN`, `SEW`, `DESIGNCHECK` (tiny edges, slivers). | Gaps and duplicate faces found with a tolerance; a report of what was fixed and what was not; STEP names and colours kept; a set of imperfect test files. |
| 3.6 Desktop and speed | partial | CI on Windows, macOS and Linux; long rebuilds in a helper process with Cancel; crash log. | Speed and memory baselines (import, rebuild, picking, drawing, save/open); long-session test; real-machine checks on high-DPI and multiple screens (by the user). |
| 4.1 Revision comparison | partial | `COMPARE` (two bodies), `DIFF` (two points of the history). | Two saved projects compared; added, removed and moved faces coloured; deviation map; a report. |
| 4.2 Links to other parts | partial | `LIB`, `LINK`, `RELOAD` link whole parts. | Faces, edges, planes and curves taken from another part, linked or copied; a dependency view; broken links and loops found. |
| 4.3 Surface inspection | partial | `ANALYZE` zebra, curvature and draft colours; `PROBE` and `PROFILE` for the assistant. | G0/G1/G2 checks between neighbouring faces, curvature combs, Gaussian and mean curvature maps, smallest radius, local thickness, a report of suspicious patches. |
| 4.4 Configurations | partial | `CONFIG`, `USECONFIG`, `BOM`. | A design table from CSV, steps switched off per configuration, variants compared, drawing and BOM per configuration. |
| 4.5 Assemblies | partial | `MATE`, `DRIVE`, `MOTION`, `CONTACT`, `GRAVITY`, exploded views. | Mates that repeat or fight each other found and named; local coordinate systems. |
| 4.6 Drawings | partial | `DRAWING` sheets with views, sections, details, sizes, GD&T notes. | Views that update with the model, sheet templates, many sheets, sizes checked against the model. |
| 4.7 Project integrity | partial | Autosave and Recover, a format version in `project.json`, `RELOAD`. | Backups of earlier saves, migration tests across versions, a relink step for missing files, a check before sharing. |
| 5 Assistant | partial | Read-only tools, `diagnose`, Why?, skills, `DESIGNCHECK`. | A plan shown before any change, a confirm step for broad changes, one undo for an assistant turn, report rows with severity, measured value, limit, fix and whether it was checked. |

## The new PLAN items

They are numbered on from PLAN.md item 49 and built in this order, about
three per pull request.

### Phase 1: hardening

50. **Reference stability, part 1** (P0): every reference in the history can
    be listed (`REFS`: step, what it points at, state ok, repaired or broken,
    and why). `SEL` ID lists and named sets keep fingerprints like picks do.
    A test set of long histories (booleans, fillets, pattern counts, upstream
    size edits), each one edited upstream, rebuilt, saved, reopened and
    checked against the faces and edges it should hit.
51. **Reference stability, part 2** (P0): faces made by booleans, fillets and
    chamfers get names from their parents (the face of the tool, the edge
    that was rounded). A face that splits keeps its name on all its pieces.
    Faces that merge keep the older name. A face that vanishes makes a
    broken reference that the History marks in red with the reason, and a
    **Pick again** action that writes the fix as an edit. Fixes are always
    the same for the same model, and nothing is guessed.
52. **Sketcher robustness** (P0): trims, extends and intersections at
    tangent and near-tangent crossings, and with many crossings. Offsets of
    closed chains and splines that remove the loops they make. Constraints
    are kept through `STRANSFORM`. `SCHECK` names which constraints and
    entities are redundant, conflicting or free, and the view shows them.
    A test of a 500-entity sketch through 50 edit cycles, with timings.
53. **Healing imported models** (P1): `CHECK` finds gaps, sliver faces, tiny
    edges and duplicate faces against a tolerance. `HEAL` reports what it
    fixed and what is left. Sewing an open import uses a tolerance. STEP part
    names and colours are kept. A set of imperfect test files is generated
    (gaps, flipped faces, slivers, duplicates).
54. **Sculpting that stays clean** (P1): smooth changes between fine and
    coarse areas. Symmetry, masks and sharp edges are kept while remeshing.
    After every stroke the mesh is checked for cracks, flipped triangles and
    very thin triangles. A test of 2,000 strokes on a growing mesh, with
    timings.
55. **Scan to CAD with numbers** (P1): `DEVIATION, scan, body` gives the
    distance from scan to model as colours with tolerance bands, the max,
    RMS and per-region error, and lists outliers, holes and low-confidence
    regions. `FITSURF` and `RECONSTRUCT` take a tolerance and refine where
    it is not met. Neighbouring fitted regions meet with the continuity
    asked for.

### Phase 2: complete workflows

56. **Comparing revisions** (P2): `COMPARE` on two saved projects or two
    history points shows added, removed, moved and changed faces in colour,
    a deviation map, and a short report with the regions and sizes.
57. **Surface inspection** (P1): `CONTINUITY` (G0, G1 or G2 on every join
    between faces, with the worst gap and angle), curvature combs on curves
    and edges, Gaussian and mean curvature maps, the smallest radius, local
    wall thickness, and a report of suspicious patches.
58. **Geometry from other parts** (P2): take a face, edge, plane or curve
    from a linked part, either linked (it updates) or copied (it does not).
    A dependency view lists what uses what, finds broken links and refuses
    loops.
59. **Design tables** (P2): `CONFIG` from a CSV table, steps switched off
    per configuration, two configurations compared, and a drawing and BOM
    for one configuration.
60. **Assembly checks** (P2): mates that repeat or fight each other are found
    and named; parts that can still move are listed with the free directions;
    local coordinate systems to place parts by.
61. **Drawings that follow the model** (P2): sheets remember their views and
    are made again after a rebuild, sheet templates, several sheets in one
    file, and sizes on the sheet checked against the model.

### Phase 3: a product you can trust

62. **Project safety** (P1): numbered backups of earlier saves, crash
    recovery tested by killing the app mid-rebuild, projects from every
    earlier version opened in a test, a relink step for missing part files,
    and a check before sharing (missing files, broken references, failed
    steps).
63. **Speed and long sessions** (P1): a benchmark in CI for import, rebuild,
    picking, drawing and save/open on large models, with memory. A
    long-session test (hours of edits and rebuilds in a loop). Kernel
    failures always reach the user as a clear message, never a silent bad
    shape.
64. **Real desktop checks** (P1): a short checklist and a test script for the
    user to run on Windows and macOS (high-DPI, two screens, picking,
    graphics drivers), and fixes for what it finds.

### Phase 4: proof

65. **Five demonstration projects** as regression tests. Each one goes from
    an empty model to save, reopen, edit, rebuild and export, and the export
    is read back by another reader. The five are:
    * a machined part: sketch, holes, fillets, drawing, STEP;
    * a freeform part: curves, surfaces, lofts and blends, continuity checks;
    * an assembly: parts, mates, motion and clash check, BOM, exploded view,
      drawing;
    * a scan: import, segment, fit, deviation, export;
    * a sheet metal part: flat pattern, drawing, manufacturing checks.

    Each project is also a page on the website.
66. **Assistant safeguards and reports** (P3): read-only and changing tools
    kept apart; a plan with the expected effect shown before any change;
    a confirm step for broad changes; one undo for a whole assistant turn;
    `DESIGNCHECK` rows with severity, measured value, limit, suggested fix
    and whether the fix was checked.
67. **Scope and release 0.6.0**: a known-limitations page and a written
    scope list (what stays out of this app), then the release.
