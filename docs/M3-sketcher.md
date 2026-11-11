# M3, part 2: the sketcher, EXTRUDE and REVOLVE

Parts can now start from a 2D drawing: a sketch on any plane or flat face,
held by constraints and dimensions, then pushed or turned into a solid. Like
everything else, each sketch step is a command first and a history entry;
the mouse tools only build and run those commands. The reference is
LANGUAGE.md section 16; `scripts/sketch_bracket.cmd` is a worked example.

## The solver spike

Before writing the sketcher we tried three solvers on the same job: a plate
fixed at the origin and fully dimensioned, with an n x n grid of holes, each
with a diameter and a position. Every point starts 5 % to 15 % off, as after
a drag or a size change. `spikes/solver_spike.py` runs it.

Solve time in ms (one run on a Linux cloud machine, Python 3.13):

| Holes | Our own (numpy) | planegcs (FreeCAD's solver) | py-slvs (SolveSpace's solver) |
|------:|----------------:|----------------------------:|------------------------------:|
| 4 | 3.6 | 0.5 | 7.5 |
| 25 | 11 | 3 | 296 |
| 100 | 36 | 10 | 6264 |
| 400 | 168 | 36 | ran out of memory |

A chain of 100 linked segments (one big coupled problem, no splitting
possible): ours 206 ms, planegcs 59 ms. All three found the right answer and
reported 0 degrees of freedom; all three caught an extra, contradicting
dimension.

| | Our own | planegcs | py-slvs |
|---|---|---|---|
| Speed | fast enough: a sketch people draw by hand has tens of constraints, which is a few ms | about 3 to 5 times faster | slow from 25 holes up, then out of memory |
| Install | numpy only, wheels for every OS and Python | LGPL; no macOS wheel, Python 3.12 or later only | GPL-3; last release 2023, no Python 3.14 wheel |
| Diagnosis | degrees of freedom, which geometry is still free, redundant and conflicting constraints, and which ones a refused constraint fights, all in our own constraint numbers | conflicting and redundant lists | a failure flag and a list |
| Changing it | ours, so new constraint kinds are one residual function | C++ | C++ |

**Decision: our own solver.** It is fast enough with a wide margin for real
sketches, it installs everywhere the app does, and the part users meet most
(what is still free, and why a constraint was refused) is in our own terms.
The solver sits behind one function (`solve`), so planegcs can be plugged in
later as a faster back end if very big sketches turn out to be slow.

## How it is built

* `sketch/solver.py`: constraints are residual functions over one vector
  of numbers. The problem is split into independent groups first (each
  hole is its own small problem), each group is solved with least-change
  Gauss-Newton steps and a line search, with Levenberg-Marquardt as the
  fallback. The rank of the Jacobian gives the degrees of freedom and the
  redundant or conflicting constraints; its null space tells which
  geometry is fully defined (drawn green). Dragging adds a soft pull.
* `sketch/sketch.py`: geometry (point, line, circle, arc), constraints and
  dimensions, names like `3.E`, and the rules: a constraint that cannot
  hold is refused with the sketch unchanged and names what it fights; one
  that would shrink a line or circle to nothing is refused too. Dimensions
  remember which side they were drawn on, so a distance never flips a hole
  to the other side of an edge.
* `sketch/profile.py`: closed loops from the curves, nested even-odd into
  faces with holes and islands, then OCCT faces.
* `commands/sketch_handlers.py`: the commands; `EXTRUDE` (prism) and
  `REVOLVE` with NEW, ADD and CUT, checked like every other feature.
* `gui/sketch_tools.py` (no Qt, tested headless): what a click, a drag or
  a button turns into. `gui/sketch_ui.py`: the Sketch toolbar and forms.
  The viewport draws the sketch on top of the bodies, with dimension lines,
  sizes you can double click, and constraint marks.
* Sketches are kept in the model's snapshots, so undo, redo and history
  edits treat them like bodies.

## Try it

```bash
python -m modeler run scripts/sketch_bracket.cmd
python -m modeler                       # then press Sketch on the Features toolbar
```

## Not yet

Trim, extend, offset, sketch fillets, mirroring and patterns inside a
sketch, and projecting body edges into a sketch. Only straight lines, arcs
and circles so far (no splines or ellipses in sketches).
