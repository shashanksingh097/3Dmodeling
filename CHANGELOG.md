# Changelog

All notable changes to 3Dmodeling. Versions follow [semantic versioning](https://semver.org).

## [0.1.0] - unreleased

The first release: a desktop 3D modeler for solid parts in which every
click is a command, so every model is also an editable script.

**Downloads** for Windows (x64), macOS (Apple silicon) and Linux (x64) are
attached below and need no Python. They are not code-signed yet; the
[user guide](https://github.com/shashanksingh097/3Dmodeling/blob/main/docs/USER-GUIDE.md#1-install)
says how to open them the first time.

### Modeling
- Solids (block, cylinder, tube, cone, sphere, torus, wedge), booleans that keep their inputs on request, move, copy, mirror, and arrays in a row, around an axis or along a path.
- Sketches with constraints and sizes, a solver that names what a refused constraint fights, trim, extend, fillet, offset, mirror, pattern and projected edges; extrude and revolve as new bodies, bosses or pockets.
- Features: holes (plain, counterbore, countersink, drill point, threaded), fillets, chamfers, shell, draft, offset, split, push/pull and delete faces, feature patterns.
- Shapes from curves: loft, sweep with twist and scale laws (with a graphical sweep editor), morph, pipe, one- and two-rail sweeps, spine lofts, ISO threads, springs, text, shapes from equations.
- Datum planes, axes and points, and work planes.
- Parts with parameters, placed many times and following their definition, and a part library.
- Layers, colours and materials; volume, mass and inertia, distances, angles, clash checks, section views.

### Working with history
- Every step is kept in the History panel and can be edited, inserted, suppressed, deleted or rolled back to; the model rebuilds from there, with progress and Cancel for long rebuilds.
- Parameters and expressions in any number, loops, conditions and your own commands (macros).
- Picks remember what they pointed at and are repaired after edits when the match is certain, with a warning.
- Every boolean, blend and feature is checked; a broken result is refused with a reason and the model is unchanged. `CHECK`, `HEAL` and `CLEAN` repair imported parts.

### App
- File menu with recent files, example models, save as, import (STEP, IGES, BREP, STL) and export (STEP, STL, BREP); `.m3d` projects that carry the whole history and copies of imported files.
- Asks before unsaved work is closed or replaced; the title bar shows the file and an unsaved marker.
- Autosave, and Recover after a crash.
- A fill-in form for every command, a command line with completion and argument hints, and Ctrl+K to find a command by purpose.
- Help menu: getting started, a searchable command reference, report a problem, about.
- Errors are logged and shown instead of closing the app; kernel crashes leave a crash log.
- `modeler run script.cmd -D NAME=value` runs scripts without the window.

### For AI assistants (groundwork)
- Text tools that describe bodies and their holes, probe with rays and points, cut profiles, measure wall thickness, check expectations (`ASSERT`), compare history, and try changes in a sandbox. The chat panel that uses them comes in a later release.

### Known limits
- Builds are tested headless on Windows, macOS and Linux. The 3D view is tested under a virtual display; real Windows and macOS desktops are still being tried.
- No undo for history edits themselves yet; a sketch fillet between a line and an arc, and trimming to the sketch axes, are not in yet.
- Rebuilding re-runs every step after an edit, even ones that did not change.
