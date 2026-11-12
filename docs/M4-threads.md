# M4 part 2: screw threads and springs

`THREAD` cuts real helical ISO metric threads, outside on shafts and inside
in holes, and `SPRING` makes coil springs. With them the M4 bolt can carry a
real thread: `scripts/threaded_bolts.cmd` places a threaded bolt and nut 8
times each, and changing `D` rebuilds every copy at the new size, pitch
included. The commands are in LANGUAGE.md section 18.

## Design

* **A thread is cut, never added.** A groove with the ISO profile is swept
  along a helix and subtracted from the body. Outside a shaft it runs from
  just outside the major diameter down to the minor diameter (ISO h3, the
  rounded root depth 0.613 x pitch, leaving the P/8 crest flat). Inside a
  hole it runs from just inside the wall out to the major diameter (depth
  0.541 x pitch, root flat P/8). The same tool code serves both. Cutting
  keeps the body's other faces and IDs, and a part made from a cylinder
  stays a cylinder where it is not threaded.
* **Exact helix, in half turns.** The helix is a straight line on a cylinder
  (exact), split into half-turn edges. Found by trying: one swept face that
  wraps round the axis many times makes the boolean report success and
  remove almost nothing; a fitted spline helix is less exact. Half turns cut
  cleanly, an M8 x 30 thread in about 1.2 s.
* **Binormal sweep.** The groove profile is drawn in a plane through the
  axis and swept with the axis as the fixed binormal, so it turns rigidly
  with the helix: every point of the profile follows its own helix, which is
  the exact screw surface.
* **Free ends.** A point just past each end of the face, just off it on its
  open side, is classified against the body. In air means a free end (plain,
  chamfered or countersunk); in material means a head, shoulder or blind
  bottom. The groove overshoots a free end by one pitch and stops half a
  groove short of a closed one.
* **Sizes.** A table of ISO coarse pitches (M1 to M64). A shaft's diameter is
  the major diameter. A hole is matched to the size it is drilled for (from
  the minor diameter to the tap drill), so `HOLE` at `D - PITCH(D)` followed
  by `THREAD` gives the right thread for any `D`.
* **Springs.** A circle square to the helix, swept in binormal mode. Constant
  pitch uses the exact helix; closed ends use a fitted helix whose pitch eases
  smoothly (a smoothstep over half a turn) from tight to open, so the wire has
  no kinks. Tight coils get 1.02 x the wire diameter, not exactly touching,
  since a solid that touches itself is not valid. Ground ends are an
  intersection with a slab.
* Booleans now run in parallel (`SetRunParallel`), which roughly halves the
  time of a thread cut on 4 cores and helps every other boolean too.

## Tests

`tests/test_threads.py`: thread and nut volumes against the profile, a hole
matched to its size, threads that stop before a head and run out past a
chamfer, left hand, length, the errors, the bolt and nut parts placed 8
times with `D` changed, springs (height, closed and ground ends, left hand),
forms, and `PITCH()`.

## Next in M4

Sweeps along one and two guide rails (a wing swept between two rails), spine
lofts, text.
