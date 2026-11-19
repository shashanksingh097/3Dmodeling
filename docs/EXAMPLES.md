# Examples

Every example below is one script in [scripts/](../scripts). Run it and you get the part in the
picture: the numbers under each picture (bodies and volume) are what the script makes, and CI
checks them on every change. Each script is plain text, so read it, change a number at the top,
and run it again.

**To run one:** in the app, **File > Open example**, then pick it. Or from a terminal:

```bash
python -m modeler scripts/flange.cmd             # the app, with the model built
python -m modeler run scripts/flange.cmd         # headless: prints every step
python -m modeler run scripts/flange.cmd -D N_BOLTS=8 -q   # with a parameter changed
```

In the downloaded app, use `3Dmodeling-cli` in place of `python -m modeler`. To check the result,
type `LIST` (bodies) or `MASSPROP` (volume) in the command line.

The pictures are made by the scripts themselves: `python -m modeler gallery` runs each one and
saves the 3D view (see `modeler/gallery.py`).

| | Example |
|---|---|
| [<img src="examples/plate.png" width="160">](#plate-with-a-row-of-holes) | [Plate with a row of holes](#plate-with-a-row-of-holes) |
| [<img src="examples/flange.png" width="160">](#pipe-flange) | [Pipe flange](#pipe-flange) |
| [<img src="examples/m0_demo.png" width="160">](#three-primitives-and-picks) | [Three primitives and picks](#three-primitives-and-picks) |
| [<img src="examples/bracket_features.png" width="160">](#housing-built-on-datum-planes) | [Housing built on datum planes](#housing-built-on-datum-planes) |
| [<img src="examples/sketch_bracket.png" width="160">](#plate-boss-and-pulley-from-sketches) | [Plate, boss and pulley from sketches](#plate-boss-and-pulley-from-sketches) |
| [<img src="examples/sketch_tools.png" width="160">](#plate-drawn-with-sketch-editing-tools) | [Plate drawn with sketch editing tools](#plate-drawn-with-sketch-editing-tools) |
| [<img src="examples/blade.png" width="160">](#twisted-blade-from-stacked-sections) | [Twisted blade from stacked sections](#twisted-blade-from-stacked-sections) |
| [<img src="examples/blade_smooth.png" width="160">](#twisted-blade-as-one-smooth-sweep) | [Twisted blade as one smooth sweep](#twisted-blade-as-one-smooth-sweep) |
| [<img src="examples/sweep_gallery.png" width="160">](#shapes-on-curves-one-of-each) | [Shapes on curves, one of each](#shapes-on-curves-one-of-each) |
| [<img src="examples/m2_shell_demo.png" width="160">](#arrays-kept-inputs-and-a-chain-on-a-curve) | [Arrays, kept inputs and a chain on a curve](#arrays-kept-inputs-and-a-chain-on-a-curve) |
| [<img src="examples/wing_rails.png" width="160">](#wing-swept-between-two-rails) | [Wing swept between two rails](#wing-swept-between-two-rails) |
| [<img src="examples/m4_shapes.png" width="160">](#text-spine-loft-equation-surface-face-editing) | [Text, spine loft, equation surface, face editing](#text-spine-loft-equation-surface-face-editing) |
| [<img src="examples/bolted_plate.png" width="160">](#plate-with-bolt-and-washer-parts) | [Plate with bolt and washer parts](#plate-with-bolt-and-washer-parts) |
| [<img src="examples/threaded_bolts.png" width="160">](#bolts-and-nuts-with-real-threads) | [Bolts and nuts with real threads](#bolts-and-nuts-with-real-threads) |
| [<img src="examples/layers_demo.png" width="160">](#pump-base-on-layers) | [Pump base on layers](#pump-base-on-layers) |
| [<img src="examples/nurbs_freeform.png" width="160">](#nurbs-curves-surfaces-and-patches) | [NURBS curves, surfaces and patches](#nurbs-curves-surfaces-and-patches) |
| [<img src="examples/surface_ops.png" width="160">](#surface-blends-extend-trim-and-face-moves) | [Surface blends, extend, trim and face moves](#surface-blends-extend-trim-and-face-moves) |
| [<img src="examples/guides_analysis.png" width="160">](#guide-curve-lofts-and-surface-analysis) | [Guide-curve lofts and surface analysis](#guide-curve-lofts-and-surface-analysis) |
| [<img src="examples/deformers.png" width="160">](#bent-twisted-and-flowed-bodies-and-a-milled-slot) | [Bent, twisted and flowed bodies, and a milled slot](#bent-twisted-and-flowed-bodies-and-a-milled-slot) |
| [<img src="examples/mouse.png" width="160">](#computer-mouse-shell-the-m5-exit-test) | [Computer mouse shell (the M5 exit test)](#computer-mouse-shell-the-m5-exit-test) |
| [<img src="examples/car_body.png" width="160">](#car-body) | [Car body](#car-body) |
| [<img src="examples/mesh_bodies.png" width="160">](#mesh-bodies-a-lamp-shade-cut-as-a-mesh-a-smoothed-pebble-a-twisted-bar) | [Mesh bodies: a lamp shade cut as a mesh, a smoothed pebble, a twisted bar](#mesh-bodies-a-lamp-shade-cut-as-a-mesh-a-smoothed-pebble-a-twisted-bar) |
| [<img src="examples/implicit_lattices.png" width="160">](#implicit-shapes-and-lattices-a-blend-a-superquadric-gyroid-walls-lattice-infill) | [Implicit shapes and lattices: a blend, a superquadric, gyroid walls, lattice infill](#implicit-shapes-and-lattices-a-blend-a-superquadric-gyroid-walls-lattice-infill) |
| [<img src="examples/knife_cuts.png" width="160">](#knife-and-freehand-cuts-a-wavy-split-a-cookie-cutter-a-slot-through-a-mesh-ball-freehand-pocket-and-boss) | [Knife and freehand cuts: a wavy split, a cookie cutter, a slot through a mesh ball, freehand pocket and boss](#knife-and-freehand-cuts-a-wavy-split-a-cookie-cutter-a-slot-through-a-mesh-ball-freehand-pocket-and-boss) |
| [<img src="examples/sculpt_head.png" width="160">](#sculpted-head-brow-ridges-nose-and-mouth-brushed-onto-a-mesh-ball-mirrored-with-a-mask) | [Sculpted head: brow ridges, nose and mouth brushed onto a mesh ball, mirrored, with a mask](#sculpted-head-brow-ridges-nose-and-mouth-brushed-onto-a-mesh-ball-mirrored-with-a-mask) |
| [<img src="examples/cover_plate.png" width="160">](#cover-plate-chamfers-a-hexagon-window-a-slot-bent-along-an-arc-a-copied-hole) | [Cover plate: chamfers, a hexagon window, a slot bent along an arc, a copied hole](#cover-plate-chamfers-a-hexagon-window-a-slot-bent-along-an-arc-a-copied-hole) |
| [<img src="examples/cam_plate.png" width="160">](#cam-plate-an-elliptical-outline-a-slot-along-a-curved-path-an-elliptical-window-a-hole-touching-two-edges) | [Cam plate: an elliptical outline, a slot along a curved path, an elliptical window, a hole touching two edges](#cam-plate-an-elliptical-outline-a-slot-along-a-curved-path-an-elliptical-window-a-hole-touching-two-edges) |
| [<img src="examples/spline_handle.png" width="160">](#handle-a-stepped-edge-joined-into-one-spline-a-nose-spline-extended-to-the-base-a-fillet-between-a-line-and-a-spline) | [Handle: a stepped edge joined into one spline, a nose spline extended to the base, a fillet between a line and a spline](#handle-a-stepped-edge-joined-into-one-spline-a-nose-spline-extended-to-the-base-a-fillet-between-a-line-and-a-spline) |
| [<img src="examples/sheet_bracket.png" width="160">](#sheet-metal-bracket-flanges-bent-up-and-down-at-three-angles-and-its-flat-blank-with-the-bend-allowances) | [Sheet metal bracket: flanges bent up and down at three angles, and its flat blank with the bend allowances](#sheet-metal-bracket-flanges-bent-up-and-down-at-three-angles-and-its-flat-blank-with-the-bend-allowances) |
| [<img src="examples/enclosure_halves.png" width="160">](#ribs-lips-and-wrapping-an-enclosures-two-halves-with-a-rib-and-a-lip-and-groove-a-gusset-a-knob-with-wrapped-grips) | [Ribs, lips and wrapping: an enclosure's two halves with a rib and a lip and groove, a gusset, a knob with wrapped grips](#ribs-lips-and-wrapping-an-enclosures-two-halves-with-a-rib-and-a-lip-and-groove-a-gusset-a-knob-with-wrapped-grips) |
| [<img src="examples/scan_machined.png" width="160">](#scan-to-cad-for-machined-parts-a-mesh-of-a-block-split-into-planes-cylinders-and-a-sphere-fitted-exactly-and-joined-into-a-solid) | [Scan to CAD for machined parts: a mesh of a block split into planes, cylinders and a sphere, fitted exactly and joined into a solid](#scan-to-cad-for-machined-parts-a-mesh-of-a-block-split-into-planes-cylinders-and-a-sphere-fitted-exactly-and-joined-into-a-solid) |
| [<img src="examples/hinged_lid.png" width="160">](#assembly-that-moves-a-lid-on-a-hinge-driven-by-a-parameter-motion-finds-where-it-hits-the-post) | [Assembly that moves: a lid on a hinge, driven by a parameter; MOTION finds where it hits the post](#assembly-that-moves-a-lid-on-a-hinge-driven-by-a-parameter-motion-finds-where-it-hits-the-post) |
| [<img src="examples/scan_to_cad.png" width="160">](#scan-to-cad-a-sculpted-mesh-fitted-as-one-smooth-solid-with-a-hole-cut-through-it-and-a-painted-region-fitted-as-one-face) | [Scan to CAD: a sculpted mesh fitted as one smooth solid (with a hole cut through it) and a painted region fitted as one face](#scan-to-cad-a-sculpted-mesh-fitted-as-one-smooth-solid-with-a-hole-cut-through-it-and-a-painted-region-fitted-as-one-face) |
| [<img src="examples/exploded_view.png" width="160">](#exploded-view-with-trail-lines-xstep-xshow-and-marks-wrapped-onto-a-cone) | [Exploded view with trail lines (XSTEP, XSHOW), and marks wrapped onto a cone](#exploded-view-with-trail-lines-xstep-xshow-and-marks-wrapped-onto-a-cone) |
| [<img src="examples/welded_frame.png" width="160">](#frames-and-weldments-a-welded-table-of-square-tube-with-mitred-top-corners-butted-legs-and-an-angle-brace-a-weld-bead-on-every-joint-weld-cutlist-lists-the-cuts-and-welds) | [Frames and weldments: a welded table of square tube with mitred top corners, butted legs and an angle brace, a weld bead on every joint (WELD); CUTLIST lists the cuts and welds](#frames-and-weldments-a-welded-table-of-square-tube-with-mitred-top-corners-butted-legs-and-an-angle-brace-a-weld-bead-on-every-joint-weld-cutlist-lists-the-cuts-and-welds) |
| [<img src="examples/bracket_strength.png" width="160">](#a-first-strength-check-an-aluminium-bracket-bolted-to-a-wall-400-n-on-its-arm-coloured-by-stress-stress) | [A first strength check: an aluminium bracket bolted to a wall, 400 N on its arm, coloured by stress (STRESS)](#a-first-strength-check-an-aluminium-bracket-bolted-to-a-wall-400-n-on-its-arm-coloured-by-stress-stress) |
| [<img src="examples/print_check.png" width="160">](#ready-to-3d-print-a-wall-hook-built-standing-up-red-overhangs-need-support-blue-sits-on-the-bed-printcheck) | [Ready to 3D print? A wall hook built standing up: red overhangs need support, blue sits on the bed (PRINTCHECK)](#ready-to-3d-print-a-wall-hook-built-standing-up-red-overhangs-need-support-blue-sits-on-the-bed-printcheck) |
| [<img src="examples/milled_plate.png" width="160">](#25d-milling-a-pocket-around-a-boss-cleared-in-rings-with-g-code-mill) | [2.5D milling: a pocket around a boss cleared in rings, with G-code (MILL)](#25d-milling-a-pocket-around-a-boss-cleared-in-rings-with-g-code-mill) |
| [<img src="examples/gravity_check.png" width="160">](#will-it-stand-up-a-table-with-a-book-tipping-off-a-floating-lamp-shade-and-a-shelf-held-only-at-its-side-marked-gravity) | [Will it stand up? A table with a book tipping off, a floating lamp shade and a shelf held only at its side, marked (GRAVITY)](#will-it-stand-up-a-table-with-a-book-tipping-off-a-floating-lamp-shade-and-a-shelf-held-only-at-its-side-marked-gravity) |
| [<img src="examples/gear_train.png" width="160">](#gears-and-fasteners-a-pinion-and-a-wheel-in-mesh-a-planet-in-a-ring-gear-and-a-rack-on-cap-screws-with-washers-and-nuts-gear-fastener) | [Gears and fasteners: a pinion and a wheel in mesh, a planet in a ring gear and a rack, on cap screws with washers and nuts (GEAR, FASTENER)](#gears-and-fasteners-a-pinion-and-a-wheel-in-mesh-a-planet-in-a-ring-gear-and-a-rack-on-cap-screws-with-washers-and-nuts-gear-fastener) |
| [<img src="examples/plastic_case.png" width="160">](#a-moulded-case-seen-from-its-open-side-screw-bosses-with-ribs-snap-hooks-on-the-rim-and-two-vents-boss-snap-vent) | [A moulded case seen from its open side: screw bosses with ribs, snap hooks on the rim and two vents (BOSS, SNAP, VENT)](#a-moulded-case-seen-from-its-open-side-screw-bosses-with-ribs-snap-hooks-on-the-rim-and-two-vents-boss-snap-vent) |
| [<img src="examples/cap_mould.png" width="160">](#mould-tools-and-notes-a-drafted-cap-between-its-two-mould-halves-with-an-h7-bore-note-a-size-and-a-material-note-parting-mold-note-fits) | [Mould tools and notes: a drafted cap between its two mould halves, with an H7 bore note, a size and a material note (PARTING, MOLD, NOTE, FITS)](#mould-tools-and-notes-a-drafted-cap-between-its-two-mould-halves-with-an-h7-bore-note-a-size-and-a-material-note-parting-mold-note-fits) |
| [<img src="examples/pipe_run.png" width="160">](#pipes-and-cables-a-water-line-bent-at-its-corners-with-a-tee-branch-and-a-cable-bundle-on-a-tray-route-routes) | [Pipes and cables: a water line bent at its corners with a tee branch, and a cable bundle on a tray (ROUTE, ROUTES)](#pipes-and-cables-a-water-line-bent-at-its-corners-with-a-tee-branch-and-a-cable-bundle-on-a-tray-route-routes) |
| [<img src="examples/toleranced_plate.png" width="160">](#tolerances-datums-flatness-parallelism-and-an-h7-bore-placed-by-position-cut-open-by-a-section-plane-note-stackup-section) | [Tolerances: datums, flatness, parallelism and an H7 bore placed by position, cut open by a section plane (NOTE, STACKUP, SECTION)](#tolerances-datums-flatness-parallelism-and-an-h7-bore-placed-by-position-cut-open-by-a-section-plane-note-stackup-section) |
| [<img src="examples/cam_follower.png" width="160">](#cams-and-more-gears-a-disc-cam-lifting-its-roller-a-barrel-cam-a-bevel-pair-at-right-angles-and-a-worm-driving-its-wheel-cam-camlift-gear-bevelwormwormwheel) | [Cams and more gears: a disc cam lifting its roller, a barrel cam, a bevel pair at right angles and a worm driving its wheel (CAM, CAMLIFT, GEAR BEVEL/WORM/WORMWHEEL)](#cams-and-more-gears-a-disc-cam-lifting-its-roller-a-barrel-cam-a-bevel-pair-at-right-angles-and-a-worm-driving-its-wheel-cam-camlift-gear-bevelwormwormwheel) |
| [<img src="examples/topo_bracket.png" width="160">](#a-quick-topology-check-the-30-of-a-plate-that-carries-a-load-from-its-tip-to-the-wall-best-as-a-mesh-to-model-a-part-after-topopt) | [A quick topology check: the 30% of a plate that carries a load from its tip to the wall best, as a mesh to model a part after (TOPOPT)](#a-quick-topology-check-the-30-of-a-plate-that-carries-a-load-from-its-tip-to-the-wall-best-as-a-mesh-to-model-a-part-after-topopt) |

---

## Plate with a row of holes

![Plate with a row of holes](examples/plate.png)

plate with a row of holes; change W or N and it rebuilds

**Script:** [scripts/plate.cmd](../scripts/plate.cmd) (14 lines) · **Run:** `python -m modeler scripts/plate.cmd`

**You should get:** 1 body, volume 5,434.5 mm³, 10 faces

<details><summary>The whole script</summary>

```text
! plate with a row of holes; change W or N and it rebuilds
W = 60
N = 4
BLOCK, 0,0,0, W,20,5
NAME, LAST, plate
*MACRO, drill, x, y, d=6
  CYL, x, y, -1, d/2, 7
  SUBTRACT, plate, LAST
*END
*DO, i, 1, N
  drill, i*W/(N+1), 10
*ENDDO
SEL, S, FACE, NORMAL, 0,0,1      ! the top face, chosen by meaning, not number
CM, top, FACE
```

</details>

---

## Pipe flange

![Pipe flange](examples/flange.png)

Pipe flange, fully parametric. Change any value below (or edit it in the History panel) and the model rebuilds.

**Script:** [scripts/flange.cmd](../scripts/flange.cmd) (54 lines) · **Run:** `python -m modeler scripts/flange.cmd`

**You should get:** 1 body, volume 66,877.7 mm³, 15 faces

<details><summary>The whole script</summary>

```text
! Pipe flange, fully parametric.
! Change any value below (or edit it in the History panel) and the model rebuilds.
D_FLANGE = 80          ! flange diameter
T_FLANGE = 10          ! flange thickness
D_HUB = 40             ! hub diameter
H_HUB = 30             ! hub height above the flange
D_BORE = 24            ! bore diameter
N_BOLTS = 6            ! number of bolt holes
D_BOLT = 8             ! bolt hole diameter
PCD = 60               ! bolt circle diameter
R_FILLET = 3           ! hub-to-flange fillet
C_BORE = 1.5           ! chamfer on the bore and hub top

CYL, 0,0,0, D_FLANGE/2, T_FLANGE
NAME, LAST, flange
CYL, 0,0,T_FLANGE, D_HUB/2, H_HUB
UNION, flange, LAST

! a hole through everything, as a reusable command
*MACRO, drill, x, y, d
  CYL, x, y, -1, d/2, T_FLANGE + H_HUB + 2
  SUBTRACT, flange, LAST
*END

drill, 0, 0, D_BORE
*DO, i, 0, N_BOLTS - 1
  A = i * 360 / N_BOLTS
  drill, PCD/2 * cos(A), PCD/2 * sin(A), D_BOLT
*ENDDO

! fillet the circular edge where the hub meets the flange top
SEL, S, EDGE, RADIUS, EQ, D_HUB/2
SEL, R, EDGE, LOC, Z, T_FLANGE
FILLET, R_FILLET

! chamfer the bore's top and the hub's outer top edge
SEL, S, EDGE, LOC, Z, T_FLANGE + H_HUB
CHAMFER, C_BORE

! the flange top face, saved as a named set for later steps
SEL, S, FACE, NORMAL, 0,0,1
SEL, R, FACE, LOC, Z, T_FLANGE
CM, flange_top, FACE

! checks that hold for any values above: the step fails if one does not
ASSERT, VALID(flange)
ASSERT, HOLES(flange, D_BOLT), EQ, N_BOLTS
ASSERT, HOLES(flange, D_BORE, 1), EQ, 1          ! the bore goes all the way through
ASSERT, BBOX(flange).dz, EQ, T_FLANGE + H_HUB, 0.001
ASSERT, SYMMETRIC(flange, "ZX")             ! true for any number of bolts

*MSG, "flange volume: ", round(VOL(flange)), " mm3"
VIEW, ISO
FIT
```

</details>

---

## Three primitives and picks

![Three primitives and picks](examples/m0_demo.png)

M0 demo: three primitives, then a few picks like the viewport would make

**Script:** [scripts/m0_demo.cmd](../scripts/m0_demo.cmd) (9 lines) · **Run:** `python -m modeler scripts/m0_demo.cmd`

**You should get:** 3 bodies, volume 2,508.0 mm³, 10 faces

<details><summary>The whole script</summary>

```text
! M0 demo: three primitives, then a few picks like the viewport would make
BLOCK,  0,0,0, 20,10,5
CYL,    30,5,0, 4, 12
SPHERE, 0,25,5, 6
PICKMODE, FACE
PICK, FACE, 6          ! top face of the block
PICK, FACE, 8, A       ! add the cylinder's top cap
VIEW, ISO
FIT
```

</details>

---

## Housing built on datum planes

![Housing built on datum planes](examples/bracket_features.png)

A shelled, drafted housing with holes, built on datum planes. Change W, H or WALL and everything follows: the planes move with the faces.

**Script:** [scripts/bracket_features.cmd](../scripts/bracket_features.cmd) (30 lines) · **Run:** `python -m modeler scripts/bracket_features.cmd`

**You should get:** 1 body, volume 25,060.7 mm³, 16 faces

<details><summary>The whole script</summary>

```text
! A shelled, drafted housing with holes, built on datum planes.
! Change W, H or WALL and everything follows: the planes move with the faces.
W = 80
D = 50
H = 30
WALL = 2.5
BLOCK, 0,0,0, W, D, H
NAME, LAST, housing

! datum planes from faces and numbers
PLANE, top, FACE, 6                  ! on the top face
PLANE, mid, MID, 1, 2                ! half way between the end faces
PLANE, side, MID, 3, 4
AXIS, centre, PLANES, mid, side      ! the vertical centre line
POINT, corner, VERTEX, 1

! tilt the four sides by 3 degrees about the base, so it leaves a mould
SEL, S, FACE, ID, 1, 4
DRAFT, 3

! hollow it out, open at the bottom
SEL, S, FACE, NORMAL, 0,0,-1
SHELL, WALL

! holes drilled on the top face, drawn in the top plane's own coordinates
WORKPLANE, top
HOLE, housing, -25, 0, 0, 8, 0, CBORE, 13, 1.5
HOLE, housing, 25, 0, 0, 8, 0, CSINK, 14
HOLE, housing, 0, 0, 0, 12
WORKPLANE, OFF
```

</details>

---

## Plate, boss and pulley from sketches

![Plate, boss and pulley from sketches](examples/sketch_bracket.png)

A plate from a sketch, a boss sketched on its top face, a pocket cut through, and a pulley revolved about a construction line. Change W, H or HOLE_D in the Parameters panel and everything follows.

**Script:** [scripts/sketch_bracket.cmd](../scripts/sketch_bracket.cmd) (44 lines) · **Run:** `python -m modeler scripts/sketch_bracket.cmd`

**You should get:** 2 bodies, volume 84,868.2 mm³, 24 faces

<details><summary>The whole script</summary>

```text
! A plate from a sketch, a boss sketched on its top face, a pocket cut
! through, and a pulley revolved about a construction line.
! Change W, H or HOLE_D in the Parameters panel and everything follows.
W = 100
H = 60
T = 8
HOLE_D = 10

SKETCH, base, XY
SRECT, 0, 0, W, H
SCON, COINCIDENT, 1.S, ORIGIN
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, H
*DO, i, 0, 1
  SCIRCLE, 12 + i*(W - 24), 12, HOLE_D/2
*ENDDO
SDIM, DIAMETER, 5, HOLE_D
SCON, EQUAL, 5, 6
SDIM, HDIST, ORIGIN, 5.C, 12
SDIM, VDIST, ORIGIN, 5.C, 12
SCON, HORIZONTAL, 5.C, 6.C
SDIM, HDIST, 6.C, 2.S, 12
ENDSKETCH
EXTRUDE, base, T
NAME, LAST, plate

SEL, S, FACE, NORMAL, 0,0,1
SKETCH, boss, FACE, SEL
SCIRCLE, 0, 10, 15
SDIM, DIAMETER, 1, 30
ENDSKETCH
EXTRUDE, boss, 20, ADD, plate

SKETCH, slot, XY
SSLOT, 30, 45, 70, 45, 5
ENDSKETCH
EXTRUDE, slot, 0, CUT, plate

SKETCH, pulley, ZX
SLINE, 0, 120, 0, 160, V, CONSTR
SPOLY, 5, 130, 5, 150, 25, 150, 25, 144, 20, 142, 20, 138, 25, 136, 25, 130, CLOSE
ENDSKETCH
REVOLVE, pulley, 1
CHECK
```

</details>

---

## Plate drawn with sketch editing tools

![Plate drawn with sketch editing tools](examples/sketch_tools.png)

A plate drawn with the sketch editing tools: rounded corners, a ring offset from a bore, a ring of holes and mirrored slots. Change W or H (or any size) and everything follows.

**Script:** [scripts/sketch_tools.cmd](../scripts/sketch_tools.cmd) (20 lines) · **Run:** `python -m modeler scripts/sketch_tools.cmd`

**You should get:** 1 body, volume 20,855.5 mm³, 28 faces

<details><summary>The whole script</summary>

```text
! A plate drawn with the sketch editing tools: rounded corners, a ring
! offset from a bore, a ring of holes and mirrored slots. Change W or H
! (or any size) and everything follows.
W = 80
H = 50
SKETCH, plate, XY
SRECT, -40,-25, 40,25
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, H
SCON, SYMMETRIC, 1.S, 1.E, V
SCON, SYMMETRIC, 2.S, 2.E, H
SFILLET, 1.E, 2.E, 3.E, 4.E, 8        ! all four corners; the corners stay as points 5, 7, 9, 11
SCIRCLE, 0, 0, 12
SOFFSET, 3, 13                        ! a ring 3 outside the bore
SCIRCLE, 18, 0, 2
SPATTERN, POLAR, 6, 360, O, 15        ! six holes round the middle
SSLOT, -30, -15, -20, -15, 2.5
SMIRROR, H, 21, 22, 23, 24            ! the slot again on the other side
ENDSKETCH
EXTRUDE, plate, 6
```

</details>

---

## Twisted blade from stacked sections

![Twisted blade from stacked sections](examples/blade.png)

Twisted, tapered blade on a hub and axle, built only from M1 commands. Each blade section is a biconvex "lens" airfoil: the overlap of two cylinders. A *DO loop stacks thin sections along the span, turning and shrinking each one a little, and unions them into one body.

**Script:** [scripts/blade.cmd](../scripts/blade.cmd) (48 lines) · **Run:** `python -m modeler scripts/blade.cmd`

**You should get:** 1 body, volume 30,414.3 mm³, 150 faces

<details><summary>The whole script</summary>

```text
! Twisted, tapered blade on a hub and axle, built only from M1 commands.
! Each blade section is a biconvex "lens" airfoil: the overlap of two
! cylinders. A *DO loop stacks thin sections along the span, turning and
! shrinking each one a little, and unions them into one body.

R_AXLE = 6          ! axle radius
L_AXLE = 80         ! axle length
R_HUB = 16          ! hub radius
H_HUB = 24          ! hub height
SPAN = 120          ! blade length from the hub surface
CHORD_ROOT = 30     ! chord at the root
CHORD_TIP = 14      ! chord at the tip
T_RATIO = 0.12      ! thickness / chord
TWIST_ROOT = 40     ! pitch angle at the root (deg)
TWIST_TIP = 8       ! pitch angle at the tip (deg)
N = 24              ! number of sections (more = smoother)

! axle along Z, hub in the middle
CYL, 0,0,-L_AXLE/2, R_AXLE, L_AXLE
NAME, LAST, rotor
CYL, 0,0,-H_HUB/2, R_HUB, H_HUB
UNION, rotor, LAST

! one airfoil section at radius x, thickness dx along the span
*MACRO, station, x, dx, chord, pitch
  T = T_RATIO * chord
  RC = (chord**2/4 + T**2/4) / T       ! radius of the arcs
  CYL, x, 0, -(RC - T/2), RC, dx, 1,0,0
  CYL, x, 0, RC - T/2, RC, dx, 1,0,0
  INTERSECT, LAST - 1, LAST
  ROTATE, LAST, pitch, 0,0,0, 1,0,0     ! pitch about the span axis
*END

DS = SPAN / N
*DO, i, 0, N - 1
  F = (i + 0.5) / N                     ! 0 at root, 1 at tip
  station, R_HUB - 2 + i*DS, DS + 0.01, CHORD_ROOT + (CHORD_TIP - CHORD_ROOT)*F, TWIST_ROOT + (TWIST_TIP - TWIST_ROOT)*F
  *IF, i, EQ, 0
    NAME, LAST, blade
  *ELSE
    UNION, blade, LAST
  *ENDIF
*ENDDO

UNION, rotor, blade
*MSG, "rotor volume: ", round(VOL(rotor)), " mm3, span to ", round(BBOX(rotor).xmax), " mm"
VIEW, ISO
FIT
```

</details>

---

## Twisted blade as one smooth sweep

![Twisted blade as one smooth sweep](examples/blade_smooth.png)

The twisted, tapered blade from blade.cmd, now as ONE smooth sweep. A NACA airfoil is moved along a straight span line; the twist law turns it and the scale law shrinks it on the way. Change any number and re-run.

**Script:** [scripts/blade_smooth.cmd](../scripts/blade_smooth.cmd) (45 lines) · **Run:** `python -m modeler scripts/blade_smooth.cmd`

**You should get:** 3 bodies, volume 40,260.0 mm³, 19 faces

<details><summary>The whole script</summary>

```text
! The twisted, tapered blade from blade.cmd, now as ONE smooth sweep.
! A NACA airfoil is moved along a straight span line; the twist law turns it
! and the scale law shrinks it on the way. Change any number and re-run.

R_AXLE = 6          ! axle radius
L_AXLE = 80         ! axle length
R_HUB = 16          ! hub radius
H_HUB = 24          ! hub height
SPAN = 120          ! blade length from the hub surface
CHORD_ROOT = 30     ! chord at the root
CHORD_TIP = 14      ! chord at the tip
NACA = "2412"       ! airfoil: 2% camber at 40% chord, 12% thick
TWIST_ROOT = 40     ! pitch angle at the root (deg)
TWIST_TIP = 8       ! pitch angle at the tip (deg)
N_BLADES = 3

! axle along Z, hub in the middle
CYL, 0,0,-L_AXLE/2, R_AXLE, L_AXLE
NAME, LAST, rotor
CYL, 0,0,-H_HUB/2, R_HUB, H_HUB
UNION, rotor, LAST

! the span line, and the root airfoil drawn where it starts (normal = span)
X0 = R_HUB - 2
LINE, X0,0,0, X0 + SPAN,0,0
NAME, LAST, spanline
AIRFOIL, X0,0,0, CHORD_ROOT, NACA, 1,0,0, TWIST_ROOT
NAME, LAST, root

! one smooth blade: twist from the root pitch to the tip pitch, chord shrinks
SWEEP, root, spanline, (TWIST_TIP - TWIST_ROOT)*t, 1 + (CHORD_TIP/CHORD_ROOT - 1)*t
NAME, LAST, blade

! copies around the hub
*DO, k, 1, N_BLADES - 1
  COPY, blade
  ROTATE, LAST, k*360/N_BLADES, 0,0,0, 0,0,1
  UNION, rotor, LAST
*ENDDO
UNION, rotor, blade
HIDE, spanline
HIDE, root
*MSG, "rotor volume: ", round(VOL(rotor)), " mm3, span to ", round(BBOX(rotor).xmax), " mm"
VIEW, ISO
FIT
```

</details>

---

## Shapes on curves, one of each

![Shapes on curves, one of each](examples/sweep_gallery.png)

Shapes on curves: one example of each kind, side by side.

**Script:** [scripts/sweep_gallery.cmd](../scripts/sweep_gallery.cmd) (46 lines) · **Run:** `python -m modeler scripts/sweep_gallery.cmd`

**You should get:** 20 bodies, volume 67,581.0 mm³, 40 faces

<details><summary>The whole script</summary>

```text
! Shapes on curves: one example of each kind, side by side.

! 1. MORPH: a duct that starts round, turns into a rounded square, then a
!    star, while it twists a quarter turn along an arc.
ARC, 0,0,0, 40,25,0, 80,0,0
NAME, LAST, duct_path
P0 = (0,0,0)
D0 = (0.6, 0.8, 0)                      ! the arc's start direction
CIRCLE, P0, 8, D0
RECT, P0, 14, 14, 3, D0
STAR, P0, 10, 5, 6, D0
MORPH, duct_path, 90*t, 1, MINTWIST, LAST - 2, LAST - 1, LAST

! 2. A spring: the coils get closer at the ends (pitch law) and the wire
!    gets thicker toward the top (radius law).
HELIX, 130,0,0, 14, 9, 6, 0,0,1, 0, RIGHT, 0.5 + 2*t*(1 - t)*2
NAME, LAST, coil
PIPE, coil, 1.6, 0, 0.7 + 0.6*t

! 3. A twisted ring: a flat bar swept round a closed circle, turning one full
!    turn on the way.
CIRCLE, 0,90,0, 28
NAME, LAST, ring_path
RECT, 28,90,0, 4, 10, 0.8, 0,1,0
SWEEP, LAST, ring_path, 360*t

! 4. A vase: LOFT through round, square and round sections.
CIRCLE, 130,90,0, 12
RECT, 130,90,18, 26, 26, 6
CIRCLE, 130,90,36, 9
POLYGON, 130,90,50, 13, 8, , , , 22.5, 2
LOFT, LAST - 3, LAST - 2, LAST - 1, LAST

! 5. A trefoil knot from an equation (angles are in degrees), made into a pipe.
CURVE, PARAM, 70 + 8*(sin(t) + 2*sin(2*t)), 180 + 8*(cos(t) - 2*cos(2*t)), 10 + 8*(-sin(3*t)), 0, 360, 180
NAME, LAST, knot
PIPE, knot, 3.5

! 6. A stretched S-duct: an ellipse that widens sideways and slides up.
SPLINE, (180,-20,0), (200,0,15), (220,20,15), (240,40,30)
NAME, LAST, s_path
ELLIPSE, 180,-20,0, 5, 3, 1,1,0.5
SWEEP, LAST, s_path, 0, 1, , 1 + 1.5*t, 1, 0, 4*t

VIEW, ISO
FIT
```

</details>

---

## Arrays, kept inputs and a chain on a curve

![Arrays, kept inputs and a chain on a curve](examples/m2_shell_demo.png)

M2 shell demo: patterns (ARRAY), keeping boolean inputs (KEEP), and a chain whose links follow a curve, turning a quarter turn each.

**Script:** [scripts/m2_shell_demo.cmd](../scripts/m2_shell_demo.cmd) (29 lines) · **Run:** `python -m modeler scripts/m2_shell_demo.cmd`

**You should get:** 19 bodies, volume 57,132.8 mm³, 57 faces

<details><summary>The whole script</summary>

```text
! M2 shell demo: patterns (ARRAY), keeping boolean inputs (KEEP), and a
! chain whose links follow a curve, turning a quarter turn each.

! a round plate with 8 holes on a circle (POLAR) and a 3 x 3 grid of pins (LINEAR)
CYL, 0,0,0, 40, 6
NAME, LAST, plate
CYL, 30,0,-1, 4, 8
ARRAY, POLAR, LAST, 8, 360, 0,0,0, 0,0,1, FUSE
SUBTRACT, plate, LAST
CYL, -10,-10,6, 2.5, 10
ARRAY, LINEAR, LAST, 3, (10,0,0), 3, (0,10,0), FUSE
UNION, plate, LAST

! a chain hanging on a curve: one link, copied along the path
SPLINE, (60,-40,40), (90,-10,20), (120,20,30), (150,50,10)
NAME, LAST, chain_path
TORUS, 60,-40,40, 4, 1.2, 0.7,-0.7,0
ARRAY, PATH, LAST, chain_path, 14, 90*round(13*t)

! KEEP: cut a pocket but keep the cutting tool (hidden, same name) to use again
KEEP, ON
BLOCK, -20,60,0, 40,30,10
NAME, LAST, block
SPHERE, 0,75,12, 9
NAME, LAST, ball
SUBTRACT, block, ball
SHOW, ball
MOVE, ball, 0,0,22
KEEP, OFF
```

</details>

---

## Wing swept between two rails

![Wing swept between two rails](examples/wing_rails.png)

A wing swept between two rails: the leading edge and the trailing edge. The root airfoil is drawn once; the rails set the chord, the sweep back, the dihedral and the twist that follow from them, and a thickness law thins the section towards the tip. Change any number and run again.

**Script:** [scripts/wing_rails.cmd](../scripts/wing_rails.cmd) (20 lines) · **Run:** `python -m modeler scripts/wing_rails.cmd`

**You should get:** 5 bodies, volume 10,853.0 mm³, 4 faces

<details><summary>The whole script</summary>

```text
! A wing swept between two rails: the leading edge and the trailing edge.
! The root airfoil is drawn once; the rails set the chord, the sweep back,
! the dihedral and the twist that follow from them, and a thickness law
! thins the section towards the tip. Change any number and run again.
SPAN = 120       ! half span, along +Y
ROOT = 40        ! root chord
TIP = 16         ! tip chord
BACK = 28        ! how far the leading edge sweeps back at the tip
DIH = 8          ! dihedral: how far the tip rises

AIRFOIL, 0, 0, 0, ROOT, 2412, 0, -1, 0, , 0     ! root section, chord along +X
NAME, LAST, foil
LINE, 0, 0, 0, 0, SPAN, 0                        ! the span: sections stand square to it
NAME, LAST, spine
SPLINE, (0, 0, 0), (0.25*BACK, SPAN/2, 0.25*DIH), (BACK, SPAN, DIH)
NAME, LAST, le
SPLINE, (ROOT, 0, 0), (0.5*(ROOT + BACK + TIP) + 3, SPAN/2, 0.25*DIH), (BACK + TIP, SPAN, DIH)
NAME, LAST, te
RAILSWEEP, foil, le, te, spine, 1 - 0.3*t
NAME, LAST, wing
```

</details>

---

## Text, spine loft, equation surface, face editing

![Text, spine loft, equation surface, face editing](examples/m4_shapes.png)

The rest of M4 in one script: text, a loft along a spine, an equation surface, and direct face editing. Change any number and run again.

**Script:** [scripts/m4_shapes.cmd](../scripts/m4_shapes.cmd) (45 lines) · **Run:** `python -m modeler scripts/m4_shapes.cmd`

**You should get:** 9 bodies, volume 52,860.2 mm³, 179 faces

<details><summary>The whole script</summary>

```text
! The rest of M4 in one script: text, a loft along a spine, an equation
! surface, and direct face editing. Change any number and run again.

! ---- a name plate with raised and engraved letters ----------------------------
W = 70
BLOCK, 0, -60, 0, W, 24, 4
NAME, LAST, plate
TEXT, "M4 DONE", W/2, -54, 4, 9, 1.2, , , , , CENTER, , BOLD   ! raised letters
UNION, plate, LAST
TEXT, "No 16", 4, -58.5, 3.4, 4, 1                       ! engraved 0.6 deep
SUBTRACT, plate, LAST

! ---- a duct that bends and changes shape: round, then a rounded square, then round
R = 50
ARC, 0, 0, 0, R*(1 - cos(45)), 0, R*sin(45), R, 0, R
NAME, LAST, spine
CIRCLE, 0, 0, 0, 9
NAME, LAST, inlet
RECT, R*(1 - cos(45)), 0, R*sin(45), 20, 14, 4, sin(45), 0, cos(45)
NAME, LAST, middle
CIRCLE, R, 0, R, 5, 1, 0, 0
NAME, LAST, outlet
SPINELOFT, spine, inlet, middle, outlet
NAME, LAST, duct

! ---- a wavy cover from an equation, thickened to 2 ----------------------------
SURFACE, PARAM, 80 + u, v - 30, 3*sin(6*u)*cos(6*v), 0, 60, 0, 60, 30, 30, 2
NAME, LAST, cover

! ---- a torus from its equation is a solid ---------------------------------------
SURFACE, PARAM, (12 + 4*cos(v))*cos(u) + 110, (12 + 4*cos(v))*sin(u) + 45, 4*sin(v), 0, 360, 0, 360
NAME, LAST, ring

! ---- direct editing on a block with a hole: no history needed ------------------
BLOCK, -60, -20, 0, 40, 30, 10
NAME, LAST, blk
CYL, -40, -5, -1, 4, 12
SUBTRACT, blk, LAST
SEL, S, FACE, BODY, blk
SEL, R, FACE, NORMAL, 0, 0, 1
PUSHPULL, 6                       ! the top goes up by 6
SEL, S, FACE, BODY, blk
SEL, R, FACE, TYPE, CYLINDER
PUSHPULL, -2                      ! the hole grows from radius 4 to 6
SEL, NONE
```

</details>

---

## Plate with bolt and washer parts

![Plate with bolt and washer parts](examples/bolted_plate.png)

A round plate held down by bolts: one bolt part and one washer part, each placed N times on a circle. Change D or N and every copy follows; edit the *PART block and every bolt changes shape.

**Script:** [scripts/bolted_plate.cmd](../scripts/bolted_plate.cmd) (29 lines) · **Run:** `python -m modeler scripts/bolted_plate.cmd`

**You should get:** 13 bodies, volume 146,515.1 mm³, 93 faces

<details><summary>The whole script</summary>

```text
! A round plate held down by bolts: one bolt part and one washer part,
! each placed N times on a circle. Change D or N and every copy follows;
! edit the *PART block and every bolt changes shape.
D = 8            ! bolt size
N = 6            ! how many bolts
PCD = 90         ! the circle they sit on

*PART, bolt, D=8, L=30, K=0.7*D
  ! hexagon head: two hexagons joined by a straight loft
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, K, D*0.9, 6
  LOFT, 1, 2, RULED
  CYL, 0, 0, -L, D/2, L           ! shank
  UNION, 3, 4
*ENDPART

*PART, washer, D=8
  TUBE, 0, 0, 0, D, D/2 + 0.2, 1.5
*ENDPART

CYL, 0, 0, -12, 60, 12
NAME, LAST, plate
*DO, i, 1, N
  X = PCD/2*cos(360*i/N)
  Y = PCD/2*sin(360*i/N)
  HOLE, plate, X, Y, 0, D + 0.5
  INST, washer, X, Y, 0, D=D
  INST, bolt, X, Y, 1.5, D=D
*ENDDO
```

</details>

---

## Bolts and nuts with real threads

![Bolts and nuts with real threads](examples/threaded_bolts.png)

A plate held by 8 bolts and nuts with real ISO metric threads. One bolt part and one nut part, each placed 8 times. Change D and every bolt and nut is rebuilt at the new size, thread pitch included (PITCH(D) looks up the ISO coarse pitch). Each size is built once and copied. Each nut is turned so its thread lines up with its bolt's thread, so CONTACT finds them touching on the thread flanks, not overlapping.

**Script:** [scripts/threaded_bolts.cmd](../scripts/threaded_bolts.cmd) (48 lines) · **Run:** `python -m modeler scripts/threaded_bolts.cmd`

**You should get:** 17 bodies, volume 121,095.0 mm³, 1526 faces

<details><summary>The whole script</summary>

```text
! A plate held by 8 bolts and nuts with real ISO metric threads.
! One bolt part and one nut part, each placed 8 times. Change D and every
! bolt and nut is rebuilt at the new size, thread pitch included (PITCH(D)
! looks up the ISO coarse pitch). Each size is built once and copied.
! Each nut is turned so its thread lines up with its bolt's thread, so
! CONTACT finds them touching on the thread flanks, not overlapping.
D = 8            ! bolt size (M8)
L = 30           ! bolt length under the head
T = 10           ! plate thickness
A = 40           ! bolt spacing

*PART, bolt, D=8, L=30, K=0.7*D, B=2*D+6
  ! hexagon head: two hexagons joined by a straight loft
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, K, D*0.9, 6
  LOFT, 1, 2, RULED
  CYL, 0, 0, -L, D/2, L           ! shank
  UNION, 3, 4
  SEL, S, EDGE, AT, 0, D/2, -L    ! the rim at the tip
  CHAMFER, D/10
  SEL, S, FACE, AT, D/2, 0, -L/2  ! the side of the shank
  THREAD, , MIN(B, L)             ! ISO coarse, from the tip
*ENDPART

*PART, nut, D=8, M=0.8*D
  POLYGON, 0, 0, 0, D*0.9, 6
  POLYGON, 0, 0, M, D*0.9, 6
  LOFT, 1, 2, RULED
  HOLE, LAST, 0, 0, M, D - PITCH(D)          ! the tap drill
  SEL, S, FACE, AT, (D - PITCH(D))/2, 0, M/2
  THREAD                                      ! the matching inside thread
*ENDPART

! The bolt's thread groove starts at the tip chamfer (L - D/10 below the
! head), the nut's at its top face; a turn of 360 degrees moves a thread one
! pitch, and half a pitch puts the nut's ridge into the bolt's groove.
P = PITCH(D)
TURN = 360*((L - T - D/10 - P/2) % P)/P

BLOCK, -A/2 - 15, -1.5*A - 15, -T, A + 30, 3*A + 30, T
NAME, LAST, plate
*DO, i, 0, 7
  X = A*((i % 2) - 0.5)
  Y = A*(INT(i/2) - 1.5)
  HOLE, plate, X, Y, 0, D + 1
  INST, bolt, X, Y, 0, D=D, L=L
  INST, nut, X, Y, -T - 0.8*D, TURN, D=D   ! turned TURN degrees about Z
*ENDDO
```

</details>

---

## Pump base on layers

![Pump base on layers](examples/layers_demo.png)

A small pump base sorted into layers: the frame, the bolts and the cover each sit on their own layer with their own colour and material. Switch a layer off in the Layers panel (or LAYER, cover, OFF) to look inside; lock the frame so nothing changes it by accident.

**Script:** [scripts/layers_demo.cmd](../scripts/layers_demo.cmd) (36 lines) · **Run:** `python -m modeler scripts/layers_demo.cmd`

**You should get:** 6 bodies, volume 56,262.6 mm³, 31 faces

<details><summary>The whole script</summary>

```text
! A small pump base sorted into layers: the frame, the bolts and the
! cover each sit on their own layer with their own colour and material.
! Switch a layer off in the Layers panel (or LAYER, cover, OFF) to look
! inside; lock the frame so nothing changes it by accident.
LAYER, frame, NEW, #5a6f8a
LAYER, bolts, NEW, ORANGE
LAYER, cover, NEW, TEAL

LAYER, frame
BLOCK, -40, -25, 0, 80, 50, 8
NAME, LAST, base
MATERIAL, base, CASTIRON
HOLE, base, 0, 0, 8, 30
BLOCK, -40, -25, 8, 8, 50, 30
MATERIAL, LAST, CASTIRON
UNION, base, LAST
*DO, i, -1, 1, 2
  *DO, j, -1, 1, 2
    HOLE, base, 30*i, 17*j, 8, 6.4
  *ENDDO
*ENDDO

LAYER, bolts
*DO, i, -1, 1, 2
  *DO, j, -1, 1, 2
    CYL, 30*i, 17*j, -4, 3, 16
    MATERIAL, LAST, STEEL
  *ENDDO
*ENDDO

LAYER, cover
TUBE, 0, 0, 8, 22, 16, 24
MATERIAL, LAST, ALUMINIUM

LAYER, frame, LOCK
LAYER, DEFAULT
```

</details>

---

## NURBS curves, surfaces and patches

![NURBS curves, surfaces and patches](examples/nurbs_freeform.png)

NURBS freeform (M5 part 1): control-point curves and surfaces, a surface through a network of curves, a patch that fills a hole, and surfaces sewn into a solid.

**Script:** [scripts/nurbs_freeform.cmd](../scripts/nurbs_freeform.cmd) (45 lines) · **Run:** `python -m modeler scripts/nurbs_freeform.cmd`

**You should get:** 13 bodies, volume 14,738.6 mm³, 3 faces

<details><summary>The whole script</summary>

```text
! NURBS freeform (M5 part 1): control-point curves and surfaces,
! a surface through a network of curves, a patch that fills a hole,
! and surfaces sewn into a solid.
L = 60
W = 40
H = 14

! ---- a dome through a network of curves, closed with a flat patch ----
! curves one way (across the width) ...
SPLINE, (0, 0, 0), (L/2, 0, 0), (L, 0, 0)
NAME, LAST, u1
SPLINE, (0, W/2, 0), (L/4, W/2, 0.8*H), (L/2, W/2, H), (3*L/4, W/2, 0.7*H), (L, W/2, 0)
NAME, LAST, u2
SPLINE, (0, W, 0), (L/2, W, 0), (L, W, 0)
NAME, LAST, u3
! ... and the other way, each meeting all three
SPLINE, (0, 0, 0), (0, W/2, 0), (0, W, 0)
NAME, LAST, v1
SPLINE, (L/2, 0, 0), (L/2, W/4, 0.75*H), (L/2, W/2, H), (L/2, 3*W/4, 0.75*H), (L/2, W, 0)
NAME, LAST, v2
SPLINE, (L, 0, 0), (L, W/2, 0), (L, W, 0)
NAME, LAST, v3
NETWORK, u1, u2, u3, ACROSS, v1, v2, v3
NAME, LAST, dome
! the flat bottom: a patch inside the four edge curves
FILL, G0, u1, v3, u3, v1
NAME, LAST, base
SEW, dome, base
NAME, LAST, pebble

! ---- a control-point curve, edited ----
NURBS, 3, (0, -30, 0), (15, -18, 0), (30, -42, 0), (45, -18, 0), (60, -30, 0)
NAME, LAST, wave
MOVEPT, wave, 3, 0, 0, 12
WEIGHT, wave, 2, 3
KNOT, wave, 0.5

! ---- a surface from rows of control points, one point pulled up ----
NURBS, 3, (80, 0, 0), (90, 0, 4), (100, 0, 4), (110, 0, 0)
NURBS, 3, (80, 13, 2), (90, 13, 6), (100, 13, 6), (110, 13, 2)
NURBS, 3, (80, 26, 2), (90, 26, 6), (100, 26, 6), (110, 26, 2)
NURBS, 3, (80, 40, 0), (90, 40, 4), (100, 40, 4), (110, 40, 0)
NSURF, 3, LAST-3, LAST-2, LAST-1, LAST
NAME, LAST, tile
MOVEPT, tile, (2, 2), 0, 0, 10
```

</details>

---

## Surface blends, extend, trim and face moves

![Surface blends, extend, trim and face moves](examples/surface_ops.png)

Freeform surface operations (M5 part 2): a G2 blend between two surfaces, extending and trimming a surface, and moving or replacing faces of a solid.

**Script:** [scripts/surface_ops.cmd](../scripts/surface_ops.cmd) (46 lines) · **Run:** `python -m modeler scripts/surface_ops.cmd`

**You should get:** 11 bodies, volume 9,359.9 mm³, 11 faces

<details><summary>The whole script</summary>

```text
! Freeform surface operations (M5 part 2): a G2 blend between two surfaces,
! extending and trimming a surface, and moving or replacing faces of a solid.

! ---- two curved panels with a gap, bridged by a smooth G2 blend ----
NURBS, 3, (0, 0, 0), (0, 10, 6), (0, 20, 6), (0, 30, 0)
NURBS, 3, (-25, 0, 0), (-25, 10, 8), (-25, 20, 8), (-25, 30, 0)
NSURF, 1, LAST-1, LAST
NAME, LAST, left
NURBS, 3, (15, 0, 6), (15, 10, 12), (15, 20, 12), (15, 30, 6)
NURBS, 3, (40, 0, 4), (40, 10, 8), (40, 20, 8), (40, 30, 4)
NSURF, 1, LAST-1, LAST
NAME, LAST, right
! the edges facing each other: at x = 0 on the left panel, at x = 15 on the right
SEL, S, EDGE, BOX, -0.1, -1, -1, 0.1, 31, 20
SEL, R, EDGE, BODY, left
E1 = SELID(1)
SEL, S, EDGE, BOX, 14.9, -1, -1, 15.1, 31, 20
SEL, R, EDGE, BODY, right
E2 = SELID(1)
BLEND, G2, E1, E2
NAME, LAST, bridge
SEW, left, bridge, right
NAME, LAST, skin

! ---- a panel carried on 6 past one edge, with a round hole trimmed out ----
NURBS, 3, (0, 50, 0), (0, 60, 4), (0, 70, 4), (0, 80, 0)
NURBS, 3, (30, 50, 2), (30, 60, 6), (30, 70, 6), (30, 80, 2)
NSURF, 1, LAST-1, LAST
NAME, LAST, panel
EXTEND, panel, 6, U1
CIRCLE, 15, 65, 20, 6
NAME, LAST, hole
TRIM, panel, hole, 15, 65, 4

! ---- a block whose top takes the shape of a wavy surface, and one side moved in ----
BLOCK, 60, 0, 0, 30, 30, 10
NAME, LAST, base
SURFACE, PARAM, u, v, 13 + 2*sin(12*u)*sin(12*v), 50, 100, -10, 40
NAME, LAST, wave
SEL, S, FACE, NORMAL, 0, 0, 1
SEL, R, FACE, BODY, base
REPLACEFACE, wave
HIDE, wave
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, BODY, base
MOVEFACE, -6, 0, 0
```

</details>

---

## Guide-curve lofts and surface analysis

![Guide-curve lofts and surface analysis](examples/guides_analysis.png)

Guide-curve lofts, sweeps that follow a surface, and surface analysis (M5 part 3).

**Script:** [scripts/guides_analysis.cmd](../scripts/guides_analysis.cmd) (34 lines) · **Run:** `python -m modeler scripts/guides_analysis.cmd`

**You should get:** 11 bodies, volume 36,472.6 mm³, 10 faces

<details><summary>The whole script</summary>

```text
! Guide-curve lofts, sweeps that follow a surface, and surface analysis (M5 part 3).

! ---- a vase: three sections, and two guide curves its side must run along ----
R0 = 14                                  ! foot radius
CIRCLE, 0, 0, 0, R0
NAME, LAST, foot
ELLIPSE, 0, 0, 30, 18, 12
NAME, LAST, belly
CIRCLE, 0, 0, 60, 8
NAME, LAST, neck
! the outline seen from the front (through x) and from the side (through y)
SPLINE, (R0, 0, 0), (22, 0, 14), (18, 0, 30), (9, 0, 48), (8, 0, 60)
NAME, LAST, front
SPLINE, (0, R0, 0), (0, 15, 14), (0, 12, 30), (0, 7, 48), (0, 8, 60)
NAME, LAST, side
LOFT, foot, belly, neck, GUIDE, front, side
NAME, LAST, vase

! ---- a rib that stays square to a domed panel along a wavy line ----
SURFACE, PARAM, 60 + u, v, 4 - 0.015*(u*u + v*v), -20, 20, -20, 20
NAME, LAST, panel
SPLINE, (46, -14, 20), (55, -4, 20), (64, 2, 20), (74, 12, 20)
PROJECT, LAST, panel, 0, 0, -1            ! drop the line straight down onto the panel
NAME, LAST, track
! the rib's cross-section, drawn where the track starts: 1 wide, 3 tall, standing on the panel
P0 = CURVEPT(track, 0)
T0 = CURVETAN(track, 0)
RECT, P0.x, P0.y, P0.z + 1.5, 1, 3, 0, T0.x, T0.y, T0.z
NAME, LAST, rib_profile
SWEEP, rib_profile, track, , , NORMAL, , , , , , 1, panel
NAME, LAST, rib

! ---- look at it: stripes on the vase, and its joins in words ----
ANALYZE, vase, ZEBRA
```

</details>

---

## Bent, twisted and flowed bodies, and a milled slot

![Bent, twisted and flowed bodies, and a milled slot](examples/deformers.png)

Deformers and swept volumes (M5 part 4): BEND, TWIST, TAPER, STRETCH, FLOW, SWEEPVOL. A deformed body keeps its ID and its faces keep theirs, so later steps that pick them still work.

**Script:** [scripts/deformers.cmd](../scripts/deformers.cmd) (43 lines) · **Run:** `python -m modeler scripts/deformers.cmd`

**You should get:** 9 bodies, volume 75,017.7 mm³, 94 faces

<details><summary>The whole script</summary>

```text
! Deformers and swept volumes (M5 part 4): BEND, TWIST, TAPER, STRETCH, FLOW, SWEEPVOL.
! A deformed body keeps its ID and its faces keep theirs, so later steps that pick them still work.

! ---- a flat bar bent into a quarter circle, and one bent more towards its far end ----
BLOCK, 0, 0, 0, 100, 10, 4
NAME, LAST, bar
BEND, bar, 90
BLOCK, 0, 30, 0, 100, 10, 4
NAME, LAST, hook
BEND, hook, 150, X, Z, t**2

! ---- a square column, twisted half a turn and tapered to a point-ish top ----
BLOCK, 140, -6, 0, 12, 12, 80
NAME, LAST, column
TWIST, column, 180
TAPER, column, 0.4, Z
! a round bar twisted out and back: the ends stay where they were
BLOCK, 170, -4, 0, 8, 8, 60
NAME, LAST, wave
TWIST, wave, 60, Z, sin(180*t)

! ---- a block stretched to twice its length, keeping its volume ----
BLOCK, 200, 0, 0, 30, 12, 12
NAME, LAST, plug
STRETCH, plug, 2

! ---- a word laid along an arc, fitted to its length ----
TEXT, "FLOW", 0, -60, 0, 16, 3
NAME, LAST, label
ARC, 0, -60, 0, 50, -30, 0, 100, -60, 0
NAME, LAST, arc
FLOW, label, arc, FIT

! ---- a slot cut by an end mill moving along a curve ----
BLOCK, 130, -100, -10, 90, 60, 10
NAME, LAST, plate
CYL, 140, -80, -4, 3, 10
NAME, LAST, cutter
SPLINE, (140, -80, -4), (170, -60, -4), (200, -75, -4), (210, -55, -4)
NAME, LAST, track
SWEEPVOL, cutter, track
SUBTRACT, plate, LAST
DELETE, cutter
```

</details>

---

## Computer mouse shell (the M5 exit test)

![Computer mouse shell (the M5 exit test)](examples/mouse.png)

The M5 exit test: a computer mouse shell built from curves. The top and the side wall are joined by a G2 blend (no jump in curvature), the skin is sewn into a solid, shelled to 2 mm with the bottom open, and a name is flowed along a curve laid on the top.

**Script:** [scripts/mouse.cmd](../scripts/mouse.cmd) (81 lines) · **Run:** `python -m modeler scripts/mouse.cmd`

**You should get:** 2 bodies, volume 24,354.4 mm³, 161 faces

<details><summary>The whole script</summary>

```text
! The M5 exit test: a computer mouse shell built from curves. The top and the side wall
! are joined by a G2 blend (no jump in curvature), the skin is sewn into a solid, shelled
! to 2 mm with the bottom open, and a name is flowed along a curve laid on the top.

L = 110                                  ! length
WALL = 2                                 ! shell thickness
SIDE_H = 14                              ! height of the straight side wall

! ---- the plan outline, at any size s about its middle and height z ----
*MACRO, OUTLINE, s, z
SPLINE, (L/2 - 55*s, 0, z), (L/2 - 47*s, 22*s, z), (L/2 - 20*s, 26*s, z), (L/2 + 15*s, 31*s, z), (L/2 + 43*s, 25*s, z), (L/2 + 55*s, 0, z), (L/2 + 43*s, -25*s, z), (L/2 + 15*s, -31*s, z), (L/2 - 20*s, -26*s, z), (L/2 - 47*s, -22*s, z), CLOSE
*END

! ---- the side wall: from the foot up to a slightly smaller outline ----
OUTLINE, 1, 0
NAME, LAST, foot
OUTLINE, 0.97, SIDE_H
NAME, LAST, waist
LOFT, foot, waist, SURFACE
NAME, LAST, side

! ---- the top: a hump towards the back, cut to an inset outline laid onto it ----
SURFACE, PARAM, u, v, 20 + 16*exp(-((u - 68)/45)**2) * (1 - (v/48)**2), -10, 120, -45, 45
NAME, LAST, top
OUTLINE, 0.84, 60
NAME, LAST, rim_plan
PROJECT, rim_plan, top, 0, 0, -1
NAME, LAST, rim
TRIM, top, rim, L/2, 0, 30, KEEP
COPY, top
NAME, LAST, top_ref                      ! a copy to lay the logo's curve on later

! ---- the G2 blend all round, between the side's upper edge and the top's rim ----
SEL, S, EDGE, BODY, side
SEL, R, EDGE, BOX, -10, -50, SIDE_H - 1, 130, 50, SIDE_H + 1
E_SIDE = SELID(1)
SEL, S, EDGE, BODY, top
E_TOP = SELID(1)
BLEND, G2, E_SIDE, E_TOP
NAME, LAST, round

! ---- close the bottom and sew everything into one solid ----
FILL, G0, foot
NAME, LAST, base
SEW, side, round, top, base
NAME, LAST, mouse
ANALYZE, mouse                           ! the two blend joins come out G2; the foot edge is the only crease

! ---- hollow it out, open at the bottom ----
SEL, S, FACE, BOX, -10, -50, -0.1, 130, 50, 0.1
SEL, R, FACE, BODY, mouse
SHELL, WALL
SEL, NONE
T_SHELL = MINWALL(mouse)                 ! the thinnest wall of the shell: 2

! ---- the split between the two buttons, and a scroll wheel ----
BLOCK, -5, -0.6, 10, 50, 1.2, 40
SUBTRACT, mouse, LAST
BLOCK, 20, -4.5, 10, 16, 9, 40
SUBTRACT, mouse, LAST
CYL, 28, -3, 23, 6.2, 6, 0, 1, 0
NAME, LAST, wheel

! ---- a name flowed along a curve on the top ----
ARC, 84, -16, 60, 78, 0, 60, 84, 16, 60
NAME, LAST, logo_arc
PROJECT, logo_arc, top_ref, 0, 0, -1
NAME, LAST, logo_line
TEXT, "M5 MOUSE", 0, 0, 0, 7, 1.2
NAME, LAST, logo
FLOW, logo, logo_line, FIT               ! half of each letter sinks into the wall, half stands proud
UNION, mouse, logo

! ---- tidy up: the construction curves are no longer needed ----
DELETE, top_ref
DELETE, logo_line
DELETE, logo_arc
DELETE, foot
DELETE, waist
DELETE, rim
DELETE, rim_plan
```

</details>

---

## Car body

![Car body](examples/car_body.png)

A detailed car body, built only with the command language. x runs from the front bumper (x = 0) to the back, y to the car's left, z up; mm. The lower body and the cabin are two smooth NURBS surfaces (rows of control points, closed with flat patches and sewn into solids). The lower body is hollowed into a 3 mm skin and cut into panels with shut lines; the cabin becomes a frame of roof and pillars with glass set into it. Wheels, lights, mirrors and other add-ons are parts placed on both sides.

**Script:** [scripts/car_body.cmd](../scripts/car_body.cmd) (502 lines) · **Run:** `python -m modeler scripts/car_body.cmd`

**You should get:** 218 bodies, volume 8,070,474,278.2 mm³, 4531 faces

<details><summary>The whole script</summary>

```text
! A detailed car body, built only with the command language.
! x runs from the front bumper (x = 0) to the back, y to the car's left, z up; mm.
! The lower body and the cabin are two smooth NURBS surfaces (rows of control
! points, closed with flat patches and sewn into solids). The lower body is
! hollowed into a 3 mm skin and cut into panels with shut lines; the cabin
! becomes a frame of roof and pillars with glass set into it. Wheels, lights,
! mirrors and other add-ons are parts placed on both sides.

FA = 880                 ! front axle
FB = 3560                ! rear axle
TRACK = 790              ! wheel centre from the middle
RW = 330                 ! wheel radius (tyre)
ARCH = 372               ! wheel arch radius
SHUT = 3                 ! half the shut-line gap between panels
THK = 3                  ! panel thickness

LAYER, build, NEW        ! curves and cutters: switched off at the end
LAYER, paint, NEW, #a3151d
LAYER, glass, NEW, #1b2430
LAYER, trim, NEW, #26282c
LAYER, chrome, NEW, #c9ccd1
LAYER, lamps, NEW, #e9eef2
LAYER, redlamps, NEW, #b0101a
LAYER, tyres, NEW, #202022
LAYER, rims, NEW, #9da3ab
LAYER, brakes, NEW, #c23b22
LAYER, build

! ---------------------------------------------------------------- master shapes
! One section of the lower body: closed control polygon around the car.
*MACRO, tsec, x, w, zb, zt, cr, b=0
  ! b pushes the side out (over the wheels); the shoulder is a crisp line under the top
  h = zt - zb
  NURBS, 3, (x,0,zb), (x,0.6*w,zb), (x,0.88*w,zb), (x,0.97*w+0.5*b,zb+0.15*h), (x,w+b,zb+0.45*h), (x,w+0.6*b+4,zt-0.22*h), (x,w-6,zt-0.06*h), (x,0.88*w,zt), (x,0.5*w,zt+cr), (x,0,zt+cr), (x,-0.5*w,zt+cr), (x,-0.88*w,zt), (x,-w+6,zt-0.06*h), (x,-w-0.6*b-4,zt-0.22*h), (x,-w-b,zb+0.45*h), (x,-0.97*w-0.5*b,zb+0.15*h), (x,-0.88*w,zb), (x,-0.6*w,zb), CLOSE
*END
! One section of the cabin: sides lean in towards the roof.
*MACRO, gsec, x, w, wr, zb, zr, cr
  h = zr - zb
  NURBS, 3, (x,0,zb), (x,0.5*w,zb), (x,w,zb), (x,0.5*(w+wr),zb+0.55*h), (x,wr,zr), (x,0.5*wr,zr+cr), (x,0,zr+cr), (x,-0.5*wr,zr+cr), (x,-wr,zr), (x,-0.5*(w+wr),zb+0.55*h), (x,-w,zb), (x,-0.5*w,zb), CLOSE
*END

tsec, 0, 560, 330, 520, 5
NAME, LAST, nose
tsec, 0, 700, 255, 600, 15
tsec, 150, 830, 205, 665, 30
tsec, 480, 880, 175, 720, 50, 10
tsec, FA, 890, 172, 770, 50, 30
tsec, 1350, 895, 170, 840, 40, 8
tsec, 2200, 900, 170, 890, 25
tsec, 3000, 900, 175, 925, 25, 12
tsec, FB, 900, 185, 950, 35, 36
tsec, 4000, 885, 205, 970, 40, 12
tsec, 4320, 850, 245, 965, 35
tsec, 4440, 800, 310, 935, 15
tsec, 4440, 620, 410, 850, 5
NAME, LAST, tail
NSURF, 3, nose, LAST-11, LAST-10, LAST-9, LAST-8, LAST-7, LAST-6, LAST-5, LAST-4, LAST-3, LAST-2, LAST-1, tail
NAME, LAST, tubskin
! a power bulge down the middle of the hood: lift the top control points of two rows
! (POLES, tubskin lists them: row 4 is x = 480, row 5 the front axle; point 10 is the top middle)
MOVEPT, tubskin, (4, 10), 0, 0, 22
MOVEPT, tubskin, (5, 10), 0, 0, 30
MOVEPT, tubskin, (6, 10), 0, 0, 18
FILL, G0, nose
NAME, LAST, tubcap1
FILL, G0, tail
NAME, LAST, tubcap2
SEW, tubskin, tubcap1, tubcap2
NAME, LAST, tub

gsec, 1120, 830, 790, 700, 830, 5
NAME, LAST, cowl
gsec, 1350, 820, 730, 760, 960, 30
gsec, 1750, 800, 665, 760, 1300, 40
gsec, 2000, 795, 645, 760, 1490, 35
gsec, 2800, 795, 645, 770, 1500, 35
gsec, 3250, 785, 625, 780, 1450, 35
gsec, 3650, 770, 585, 800, 1160, 25
gsec, 3880, 750, 560, 780, 990, 10
NAME, LAST, deck
NSURF, 3, cowl, LAST-6, LAST-5, LAST-4, LAST-3, LAST-2, LAST-1, deck
NAME, LAST, cabskin
FILL, G0, cowl
NAME, LAST, cabcap1
FILL, G0, deck
NAME, LAST, cabcap2
SEW, cabskin, cabcap1, cabcap2
NAME, LAST, cabin

! wheel wells: a round pocket on each side at each axle
*DO, k, 0, 1
  XA = FA if k == 0 else FB
  CYL, XA, 560, RW, ARCH, 500, 0, 1, 0
  SUBTRACT, tub, LAST
  CYL, XA, -1060, RW, ARCH, 500, 0, 1, 0
  SUBTRACT, tub, LAST
*ENDDO
LAYER, paint, ADD, tub
LAYER, glass, ADD, cabin

! ---------------------------------------------------------------- cutting tools
! A box with rounded edges running along axis ax (1 = x, 2 = y, 3 = z),
! grown by g on every side (negative g shrinks it).
*MACRO, rbox, x0, y0, z0, x1, y1, z1, r, ax, g=0
  cx = 0.5*(x0 + x1)
  cy = 0.5*(y0 + y1)
  cz = 0.5*(z0 + z1)
  *IF, ax == 3
    RECT, cx, cy, z0 - g, x1 - x0 + 2*g, y1 - y0 + 2*g, r + g
    LINE, cx, cy, z0 - g, cx, cy, z1 + g
  *ELSEIF, ax == 2
    RECT, cx, y0 - g, cz, x1 - x0 + 2*g, z1 - z0 + 2*g, r + g, 0, 1, 0
    LINE, cx, y0 - g, cz, cx, y1 + g, cz
  *ELSE
    RECT, x0 - g, cy, cz, y1 - y0 + 2*g, z1 - z0 + 2*g, r + g, 1, 0, 0
    LINE, x0 - g, cy, cz, x1 + g, cy, cz
  *ENDIF
  SWEEP, LAST-1, LAST
*END

! Cut a panel out of the skin: the panel is the skin inside the box shrunk by
! SHUT, and the skin loses the box grown by SHUT, which leaves the shut line.
*MACRO, panel, name, x0, y0, z0, x1, y1, z1, r, ax
  rbox, x0, y0, z0, x1, y1, z1, r, ax, -SHUT
  RG = LAST
  COPY, skin
  INTERSECT, LAST, RG
  NAME, LAST, name
  LAYER, paint, ADD, LAST
  rbox, x0, y0, z0, x1, y1, z1, r, ax, SHUT
  SUBTRACT, skin, LAST
*END

! the same panel on the left (+y) and the right (-y) side
*MACRO, panel2, name, x0, z0, x1, z1, yin, r, ax=2
  panel, "" + name + "_l", x0, yin, z0, x1, 1200, z1, r, ax
  panel, "" + name + "_r", x0, -1200, z0, x1, -yin, z1, r, ax
*END

! ---------------------------------------------------------------- body panels
! The lower body becomes a 3 mm skin. Panels are cut from it in order: what
! one panel takes, the later ones no longer see, so a rough box is enough
! where an earlier panel already holds the edge.
COPY, tub
NAME, LAST, skin
PICK, BODY, skin
SHELL, THK
panel2, headlamp, 30, 520, 470, 900, 430, 70, 3
panel2, taillamp, 4080, 720, 4500, 1000, 520, 50, 3
panel, bumper_f, -100, -1200, 0, 360, 1200, 1300, 10, 2
panel, hood, 360, -690, 500, 1240, 690, 1300, 60, 3
panel2, fender, 360, 255, 1262, 1300, 600, 20
panel2, door_f, 1262, 255, 2330, 1300, 600, 30
panel2, door_r, 2330, 255, 3180, 1300, 600, 30
panel, bumper_r, 4290, -1200, 0, 4600, 1200, 1300, 10, 2
panel, trunk, 3860, -690, 760, 4290, 690, 1300, 60, 3
panel2, quarter, 3180, 255, 4290, 1300, 600, 20
NAME, skin, bodyframe   ! what is left: sills, cowl, floor, wheel wells

! ---------------------------------------------------------------- glass and pillars
! The openings, as solids: windscreen and rear window seen from above, the
! side windows seen from the side.
POLYLINE, (1150,-770,880), (1150,770,880), (1985,605,880), (1985,-605,880), CLOSE
LINE, 1150, 0, 880, 1150, 0, 1700
SWEEP, LAST-1, LAST
NAME, LAST, o_ws
POLYLINE, (3290,-600,990), (3290,600,990), (3830,690,990), (3830,-690,990), CLOSE
LINE, 3290, 0, 990, 3290, 0, 1700
SWEEP, LAST-1, LAST
NAME, LAST, o_rw
*DO, s, -1, 1, 2
  POLYLINE, (1480,300*s,940), (2050,300*s,1385), (2375,300*s,1395), (2375,300*s,940), CLOSE
  LINE, 1480, 300*s, 940, 1480, 1200*s, 940
  SWEEP, LAST-1, LAST
  NAME, LAST, "o_sf_" + ("l" if s > 0 else "r")
  POLYLINE, (2455,300*s,940), (2455,300*s,1395), (3040,300*s,1390), (3500,300*s,950), CLOSE
  LINE, 2455, 300*s, 940, 2455, 1200*s, 940
  SWEEP, LAST-1, LAST
  NAME, LAST, "o_sr_" + ("l" if s > 0 else "r")
*ENDDO

! the cabin as a 4 mm skin: the openings give the glass, the rest is the roof and pillars
COPY, cabin
NAME, LAST, glassskin
PICK, BODY, glassskin
SHELL, 4
*MACRO, pane, name, opening
  COPY, glassskin
  INTERSECT, LAST, opening
  NAME, LAST, name
  LAYER, glass, ADD, LAST
*END
KEEP, ON                 ! the openings are needed again below
pane, windscreen, o_ws
pane, backlight, o_rw
pane, glass_fl, o_sf_l
pane, glass_fr, o_sf_r
pane, glass_rl, o_sr_l
pane, glass_rr, o_sr_r
KEEP, OFF

COPY, glassskin
NAME, LAST, roof
SUBTRACT, roof, o_ws, o_rw, o_sf_l, o_sf_r, o_sr_l, o_sr_r
LAYER, paint, ADD, roof
HIDE, tub
HIDE, cabin
HIDE, glassskin

! ---------------------------------------------------------------- details
! A chunk of the lower body inside a box, moved in by d (out when d < 0):
! anything trimmed by it follows the body's curves at that distance.
*MACRO, under, x0, y0, z0, x1, y1, z1, d
  BLOCK, x0, y0, z0, x1 - x0, y1 - y0, z1 - z0
  BX = LAST
  COPY, tub
  INTERSECT, BX, LAST      ! the box first, so the result stays on the current layer
  OFFSET, LAST, -d
*END

! lamps: the lens is the panel cut above, in see-through glass; behind it a
! dark housing, a light strip and (headlamps) two projectors
*MACRO, lampguts, nm, x0, y0, z0, x1, y1, z1, r, head
  LAYER, nm, ADD, nm
  MATERIAL, nm, GLASS
  LAYER, trim
  under, x0, y0, z0, x1, y1, z1, 40
  NAME, LAST, "" + nm + "_housing"
  LAYER, "lamps" if head else "redlamps"
  under, x0, y0, z0, x1, y1, z1, 10
  S1 = LAST
  BLOCK, x0 - 100, y0 - 100, z0 + 40, x1 - x0 + 200, y1 - y0 + 200, 16
  INTERSECT, S1, LAST
  S1 = LAST
  under, x0, y0, z0, x1, y1, z1, 22
  SUBTRACT, S1, LAST
  NAME, LAST, "" + nm + "_strip"
  *IF, head
    LAYER, chrome
    under, x0, y0, z0, x1, y1, z1, 14
    P1 = LAST
    YM = 0.5*(y0 + y1)
    CYL, x0 - 100, YM - 0.2*(y1 - y0), z0 + 0.55*(z1 - z0) - 60, 38, 700, 1, 0, 0
    CYL, x0 - 100, YM + 0.18*(y1 - y0), z0 + 0.55*(z1 - z0) - 60, 38, 700, 1, 0, 0
    UNION, LAST-1, LAST
    INTERSECT, LAST, P1
    NAME, LAST, "" + nm + "_projectors"
  *ENDIF
  LAYER, build
*END
LAYER, headlamp_l, NEW, #b8c8d8
LAYER, headlamp_r, NEW, #b8c8d8
LAYER, taillamp_l, NEW, #c0141e
LAYER, taillamp_r, NEW, #c0141e
lampguts, "headlamp_l", 30, 430, 520, 470, 900, 900, 70, 1
lampguts, "headlamp_r", 30, -900, 520, 470, -430, 900, 70, 1
lampguts, "taillamp_l", 4080, 520, 720, 4500, 1000, 1000, 50, 0
lampguts, "taillamp_r", 4080, -1000, 720, 4500, -520, 1000, 50, 0

! front grille: an opening in the bumper with a honeycomb insert behind it
rbox, -100, -400, 395, 250, 400, 515, 45, 1
SUBTRACT, bumper_f, LAST
LAYER, trim
under, -100, -440, 360, 300, 440, 550, 22
NAME, LAST, grille
LAYER, build
*DO, row, 0, 1
  POLYGON, -60, -400 + 20*row, 410 + 34.6*row, 17, 6, 1, 0, 0, 30
  LINE, -60, -400 + 20*row, 410 + 34.6*row, 320, -400 + 20*row, 410 + 34.6*row
  SWEEP, LAST-1, LAST
  ARRAY, LINEAR, LAST, 21 - row, 0, 40, 0, 3 - row, 0, 0, 69.2, CUT, grille
*ENDDO
LAYER, trim
CYL, 60, 0, 455, 40, 80, -1, 0, 0
NAME, LAST, badge
LAYER, chrome
TEXT, "3D", 40, 0, 440, 34, 30, -1, 0, 0, , CENTER, , BOLD
TX = LAST
under, -100, -60, 400, 100, 60, 500, 15
INTERSECT, TX, LAST
NAME, LAST, badge_text
LAYER, build

! lower intakes with fog lamps, and the number plate between them
*DO, sd, -1, 1, 2
  rbox, -100, (260 if sd > 0 else -640), 222, 250, (640 if sd > 0 else -260), 330, 35, 1
  SUBTRACT, bumper_f, LAST
  LAYER, trim
  BLOCK, 110, (240 if sd > 0 else -660), 240, 25, 420, 105
  NAME, LAST, "intake_" + ("l" if sd > 0 else "r")
  LAYER, lamps
  CYL, 70, sd*560, 276, 30, 45, 1, 0, 0
  NAME, LAST, "foglamp_" + ("l" if sd > 0 else "r")
  LAYER, build
*ENDDO
*MACRO, plate, nm, x0, x1, zc, nx, txt
  LAYER, lamps
  under, x0, -250, zc - 55, x1, 250, zc + 55, -6
  NAME, LAST, nm
  LAYER, trim
  TEXT, txt, (x1 if nx < 0 else x0), 0, zc - 24, 62, (x1 - x0)*1.2, nx, 0, 0, , CENTER, , BOLD
  TX = LAST
  under, x0, -250, zc - 60, x1, 250, zc + 60, -8
  INTERSECT, TX, LAST
  NAME, LAST, "" + nm + "_text"
  LAYER, build
*END
plate, plate_f, -80, 120, 282, -1, "CMD 3D"

! rear: number plate, a diffuser with fins, two exhaust tips
plate, plate_r, 4300, 4520, 540, 1, "CMD 3D"
rbox, 4150, -660, 200, 4600, 660, 335, 30, 1
SUBTRACT, bumper_r, LAST
LAYER, trim
under, 4150, -700, 150, 4600, 700, 380, 25
NAME, LAST, diffuser
under, 4150, -700, 150, 4600, 700, 380, 3
NAME, LAST, finclip
KEEP, ON                 ! finclip trims every fin, so it must stay
*DO, f, -2, 2
  BLOCK, 4150, f*210 - 4, 150, 450, 8, 230
  INTERSECT, LAST, finclip
  UNION, diffuser, LAST
*ENDDO
KEEP, OFF
LAYER, chrome
*DO, sd, -1, 1, 2
  TUBE, 4250, sd*470, 262, 44, 38, 165, 1, 0, 0
  NAME, LAST, "exhaust_" + ("l" if sd > 0 else "r")
*ENDDO

! black sills under the doors, and a fuel flap on the right
*DO, sd, -1, 1, 2
  LAYER, trim
  under, 1290, (560 if sd > 0 else -1200), 120, 3150, (1200 if sd > 0 else -560), 232, -7
  NAME, LAST, "sill_" + ("l" if sd > 0 else "r")
*ENDDO
LAYER, build
TUBE, 3930, -1100, 800, 80, 76, 300, 0, 1, 0
SUBTRACT, quarter_r, LAST

! mirrors: a housing lofted through three ellipses on a short arm, and its glass
*PART, wingmirror
  ELLIPSE, -80, 120, 30, 50, 28, 1, 0, 0
  ELLIPSE, -35, 132, 30, 92, 52, 1, 0, 0
  ELLIPSE, 8, 138, 30, 104, 60, 1, 0, 0
  LOFT, LAST-2, LAST-1, LAST
  NAME, LAST, cap
  ELLIPSE, -30, 0, 0, 45, 16, 0, 1, 0
  ELLIPSE, -30, 90, 22, 26, 13, 0, 1, 0
  LOFT, LAST-1, LAST
  UNION, cap, LAST
  ELLIPSE, 0, 138, 30, 94, 52, 1, 0, 0       ! a shallow recess for the glass
  LINE, 0, 138, 30, 30, 138, 30
  SWEEP, LAST-1, LAST
  SUBTRACT, cap, LAST
*ENDPART
*PART, mirrorglass
  ELLIPSE, 1, 138, 30, 93, 51, 1, 0, 0
  LINE, 1, 138, 30, 4, 138, 30
  SWEEP, LAST-1, LAST
*ENDPART
LAYER, paint
INST, wingmirror, 1470, 845, 880
NAME, LAST, mirror_l
MIRROR, mirror_l, 0, 0, 0, 0, 1, 0
NAME, LAST, mirror_r
LAYER, glass
INST, mirrorglass, 1470, 845, 880
NAME, LAST, mirrorglass_l
MATERIAL, LAST, GLASS
COLOR, LAST, #c8d4dc
MIRROR, mirrorglass_l, 0, 0, 0, 0, 1, 0
NAME, LAST, mirrorglass_r

! door handles: a rounded bar standing a little proud of each door
*PART, handle
  SLOT, 0, -20, 0, 150, 28, 0, 1, 0
  LINE, 0, -20, 0, 0, 14, 0
  SWEEP, LAST-1, LAST
*ENDPART
LAYER, chrome
*DO, sd, -1, 1, 2
  INST, handle, 2150, sd*902, 830, (0 if sd > 0 else 180)
  NAME, LAST, "handle_f_" + ("l" if sd > 0 else "r")
  INST, handle, 3020, sd*900, 855, (0 if sd > 0 else 180)
  NAME, LAST, "handle_r_" + ("l" if sd > 0 else "r")
*ENDDO

! a lip spoiler on the trunk lid: an airfoil swept between two curved rails
LAYER, build
AIRFOIL, 4170, -640, 985, 130, 0015, 0, -1, 0, , 0
NAME, LAST, sfoil
LINE, 4170, -640, 985, 4170, 640, 985
NAME, LAST, sspan
SPLINE, (4170, -640, 985), (4165, 0, 1004), (4170, 640, 985)
NAME, LAST, sle
SPLINE, (4300, -640, 985), (4305, 0, 1012), (4300, 640, 985)
NAME, LAST, ste
LAYER, paint
RAILSWEEP, sfoil, sle, ste, sspan
NAME, LAST, spoiler

! a fin antenna on the back of the roof, lofted through three airfoils
! (its height comes from the roof itself: the top of a thin slice through it)
LAYER, build
BLOCK, 3060, -5, 1000, 20, 10, 700
BX = LAST
COPY, roof
INTERSECT, BX, LAST
ZF = BBOX(LAST).zmax
AIRFOIL, 3000, 0, ZF - 12, 170, 0018
AIRFOIL, 3045, 0, ZF + 30, 110, 0018
AIRFOIL, 3095, 0, ZF + 60, 40, 0018
LAYER, trim
LOFT, LAST-2, LAST-1, LAST
NAME, LAST, antenna
LAYER, build

! ---------------------------------------------------------------- wheels
! Each wheel is four parts (tyre, rim, brake disc, caliper), drawn with the
! axle along y and the outside of the wheel towards +y, placed four times.
*PART, tyre, R=330, W=225, RI=232
  TUBE, 0, -W/2, 0, R, RI, W, 0, 1, 0
  NAME, LAST, t
  SEL, S, EDGE, RADIUS, EQ, R
  FILLET, 42
  *DO, i, -1, 1
    TUBE, 0, i*52 - 6, 0, R + 5, R - 10, 12, 0, 1, 0
    SUBTRACT, t, LAST
  *ENDDO
  BLOCK, -4, 60, R - 12, 8, 60, 20
  ARRAY, POLAR, LAST, 64, 360, 0, 0, 0, 0, 1, 0, CUT, t
  BLOCK, -4, -120, R - 12, 8, 60, 20
  ROTATE, LAST, 2.8, 0, 0, 0, 0, 1, 0
  ARRAY, POLAR, LAST, 64, 360, 0, 0, 0, 0, 1, 0, CUT, t
*ENDPART
*PART, rim, R=230
  RECT, -20, 92, 72, 28, 30, 8
  RECT, -46, 76, R - 24, 34, 22, 6
  LOFT, LAST-1, LAST
  NAME, LAST, spoke
  RECT, 20, 92, 72, 28, 30, 8
  RECT, 46, 76, R - 24, 34, 22, 6
  LOFT, LAST-1, LAST
  UNION, spoke, LAST
  ARRAY, POLAR, spoke, 5, 360, 0, 0, 0, 0, 1, 0, FUSE
  TUBE, 0, -95, 0, R + 2, R - 14, 180, 0, 1, 0
  UNION, spoke, LAST
  TUBE, 0, 68, 0, R + 12, R - 28, 22, 0, 1, 0
  UNION, spoke, LAST
  CYL, 0, 50, 0, 88, 52, 0, 1, 0
  UNION, spoke, LAST
  CYL, 0, 100, 52, 11, 12, 0, 1, 0
  ARRAY, POLAR, LAST, 5, 360, 0, 0, 0, 0, 1, 0, FUSE
  UNION, spoke, LAST
  CYL, 0, 100, 0, 34, 6, 0, 1, 0
  UNION, spoke, LAST
*ENDPART
*PART, disc
  TUBE, 0, -20, 0, 165, 70, 28, 0, 1, 0
  NAME, LAST, disc
  CYL, 0, -30, 118, 5, 50, 0, 1, 0
  ARRAY, POLAR, LAST, 24, 360, 0, 0, 0, 0, 1, 0, CUT, disc
  CYL, 0, -30, 140, 5, 50, 0, 1, 0
  ROTATE, LAST, 7.5, 0, 0, 0, 0, 1, 0
  ARRAY, POLAR, LAST, 24, 360, 0, 0, 0, 0, 1, 0, CUT, disc
*ENDPART
*PART, caliper
  CYL, 0, -45, 0, 188, 80, 0, 1, 0, 64
  NAME, LAST, cal
  CYL, 0, -50, 0, 120, 90, 0, 1, 0
  SUBTRACT, cal, LAST
  BLOCK, -200, -6, -200, 400, 12, 400
  SUBTRACT, cal, LAST
  ROTATE, cal, 30, 0, 0, 0, 0, 1, 0
*ENDPART

*MACRO, wheel, x, side, tag
  A = 0 if side > 0 else 180
  LAYER, tyres
  INST, tyre, x, side*TRACK, RW, A
  NAME, LAST, "tyre_" + tag
  LAYER, rims
  INST, rim, x, side*TRACK, RW, A
  NAME, LAST, "rim_" + tag
  LAYER, chrome
  INST, disc, x, side*TRACK, RW, A
  NAME, LAST, "disc_" + tag
  LAYER, brakes
  INST, caliper, x, side*TRACK, RW, A
  NAME, LAST, "caliper_" + tag
*END
wheel, FA, 1, "fl"
wheel, FA, -1, "fr"
wheel, FB, 1, "rl"
wheel, FB, -1, "rr"
LAYER, build
LAYER, build, OFF
LAYER, paint
VIEW, ISO
FIT
```

</details>

---

## Mesh bodies: a lamp shade cut as a mesh, a smoothed pebble, a twisted bar

![Mesh bodies: a lamp shade cut as a mesh, a smoothed pebble, a twisted bar](examples/mesh_bodies.png)

Mesh bodies (M6 part 1): TOMESH, mesh booleans, SMOOTH, REMESH, SIMPLIFY, deformers on meshes. A mesh body keeps its triangles as one mesh, so booleans stay fast at any size (they run in manifold3d). It keeps its ID through every mesh command, like any other body.

**Script:** [scripts/mesh_bodies.cmd](../scripts/mesh_bodies.cmd) (44 lines) · **Run:** `python -m modeler scripts/mesh_bodies.cmd`

**You should get:** 3 bodies, volume 52,362.5 mm³, 3 faces

<details><summary>The whole script</summary>

```text
! Mesh bodies (M6 part 1): TOMESH, mesh booleans, SMOOTH, REMESH, SIMPLIFY, deformers on meshes.
! A mesh body keeps its triangles as one mesh, so booleans stay fast at any size (they run in
! manifold3d). It keeps its ID through every mesh command, like any other body.

! ---- a ball lamp shade: a thin sphere with 24 round windows, all cut as a mesh ----
R = 30
SPHERE, 0, 0, 0, R
NAME, LAST, shade
TOMESH, shade
SPHERE, 0, 0, 0, R - 2
SUBTRACT, shade, LAST
! each cylinder goes right through, so it opens two windows
*DO, i, 0, 5
  CYL, -(R + 2)*COS(i*60)*COS(25), -(R + 2)*SIN(i*60)*COS(25), -(R + 2)*SIN(25), 6, 2*R + 4, COS(i*60)*COS(25), SIN(i*60)*COS(25), SIN(25)
  SUBTRACT, shade, LAST
  CYL, -(R + 2)*COS(i*60 + 30)*COS(25), -(R + 2)*SIN(i*60 + 30)*COS(25), (R + 2)*SIN(25), 6, 2*R + 4, COS(i*60 + 30)*COS(25), SIN(i*60 + 30)*COS(25), -SIN(25)
  SUBTRACT, shade, LAST
*ENDDO
! a neck on top, joined on as a mesh too
TUBE, 0, 0, R - 4, 8, 5, 14
UNION, shade, LAST
COLOR, shade, ORANGE

! ---- a pebble: a box made fine enough to bend, then smoothed round ----
BLOCK, 60, -20, -12, 44, 30, 20
NAME, LAST, pebble
TOMESH, pebble
REMESH, pebble, 1.5
SMOOTH, pebble, 40, 0.6
COLOR, pebble, GREY

! ---- a twisted bar: deformers move every point of a mesh body ----
BLOCK, 125, -6, -15, 12, 12, 60
NAME, LAST, bar
TOMESH, bar
REMESH, bar, 2
TWIST, bar, 120, Z
! fewer triangles where the bar is flat
SIMPLIFY, bar, 0.02
COLOR, bar, TEAL

ASSERT, VOL(shade), GT, 0
! smoothing keeps the size: the pebble holds about as much as the box it came from
ASSERT, VOL(pebble), EQ, 44*30*20, 1500
```

</details>

---

## Implicit shapes and lattices: a blend, a superquadric, gyroid walls, lattice infill

![Implicit shapes and lattices: a blend, a superquadric, gyroid walls, lattice infill](examples/implicit_lattices.png)

Implicit shapes and lattices (M6 part 2): IMPLICIT, SMIN blends, LATTICE. An implicit shape is where a field f(x, y, z) is at most 0. The result is a mesh body.

**Script:** [scripts/implicit_lattices.cmd](../scripts/implicit_lattices.cmd) (41 lines) · **Run:** `python -m modeler scripts/implicit_lattices.cmd`

**You should get:** 6 bodies, volume 29,838.5 mm³, 6 faces

<details><summary>The whole script</summary>

```text
! Implicit shapes and lattices (M6 part 2): IMPLICIT, SMIN blends, LATTICE.
! An implicit shape is where a field f(x, y, z) is at most 0. The result is a mesh body.

! ---- two balls joined by a smooth blend (a "metaball") ----
R = 10
IMPLICIT, a, BALL(0, 0, 0, R), -11, -11, -11, 11, 11, 11
IMPLICIT, b, BALL(16, 0, 0, 7), 8, -8, -8, 24, 8, 8
IMPLICIT, blob, SMIN(a, b, 5), -12, -12, -12, 25, 12, 12, 0.4
DELETE, a
DELETE, b
COLOR, blob, PINK

! ---- a superquadric: a rounded box written as one equation ----
IMPLICIT, pillow, ABS((x - 50)/12)**4 + ABS(y/9)**4 + ABS(z/6)**4 - 1, 37, -10, -7, 63, 10, 7
COLOR, pillow, PURPLE

! ---- a cube of gyroid walls, 1 thick, cut by a box ----
IMPLICIT, gyro, MAX(ABS(GYROID(10)) - 0.5, BOX(90, 0, 0, 24, 24, 24)), 77, -13, -13, 103, 13, 13, 0.35
COLOR, gyro, TEAL

! ---- a bracket filled with a gyroid, keeping a 1.5 thick outer skin ----
BLOCK, 0, 40, -10, 50, 25, 20
NAME, LAST, bracket
LATTICE, bracket, GYROID, 8, 1, 1.5
! cut away a corner to show the inside
BLOCK, 25, 35, 0, 30, 17.5, 20
SUBTRACT, bracket, LAST
COLOR, bracket, ORANGE

! ---- a cylinder of octet struts, and a ball of BCC struts ----
CYL, 75, 52, -10, 12, 22
NAME, LAST, post
LATTICE, post, OCTET, 6, 1.2
SPHERE, 105, 52, 0, 11
NAME, LAST, ball
LATTICE, ball, BCC, 5, 1.2
COLOR, post, GREY
COLOR, ball, BLUE

ASSERT, VOL(blob), GT, 4/3*PI*R**3
ASSERT, VOL(bracket), LT, 50*25*20
```

</details>

---

## Knife and freehand cuts: a wavy split, a cookie cutter, a slot through a mesh ball, freehand pocket and boss

![Knife and freehand cuts: a wavy split, a cookie cutter, a slot through a mesh ball, freehand pocket and boss](examples/knife_cuts.png)

Knife and freehand cuts (M6 part 3): KNIFE, sketch splines (SSPLINE). In the app, the Knife button lets you draw the stroke over the view, and the sketcher's Freehand tool draws SSPLINE; these lines are what they write.

**Script:** [scripts/knife_cuts.cmd](../scripts/knife_cuts.cmd) (46 lines) · **Run:** `python -m modeler scripts/knife_cuts.cmd`

**You should get:** 10 bodies, volume 38,897.4 mm³, 32 faces

<details><summary>The whole script</summary>

```text
! Knife and freehand cuts (M6 part 3): KNIFE, sketch splines (SSPLINE).
! In the app, the Knife button lets you draw the stroke over the view, and the
! sketcher's Freehand tool draws SSPLINE; these lines are what they write.

! ---- a block cut in two along a wavy stroke, seen from above ----
BLOCK, 0, 0, 0, 40, 24, 12
NAME, LAST, loaf
SPLINE, (14, -4, 30), (22, 6, 30), (16, 14, 30), (24, 28, 30)
KNIFE, loaf, LAST
! loaf (the bigger piece) keeps its ID; the other piece is body 3: pull it away to show the cut
MOVE, 3, -8, 0, 0
COLOR, loaf, ORANGE

! ---- a disc and a cookie cutter: a closed stroke cuts out its inside ----
CYL, 70, 12, 0, 16, 8
NAME, LAST, disc
SPLINE, (70, 2, 20), (80, 12, 20), (77, 21, 20), (70, 17, 20), (63, 21, 20), (60, 12, 20), CLOSE
KNIFE, disc, LAST
MOVE, 6, 0, 0, 12
COLOR, 6, RED
COLOR, disc, TEAL

! ---- a slot cut along a curve through a mesh ball ----
IMPLICIT, ball, BALL(115, 12, 6, 12), 102, -1, -7, 128, 25, 19
SPLINE, (100, 6, 30), (112, 14, 30), (122, 8, 30), (132, 16, 30)
KNIFE, ball, LAST, 2.5
COLOR, ball, PURPLE

! ---- a plate with a freehand pocket and a freehand boss (sketch splines) ----
BLOCK, 0, 40, 0, 60, 36, 6
NAME, LAST, plate
PLANE, top, XY, 6
SKETCH, pocket, top
SSPLINE, 8, 46, 20, 66, 34, 70, 30, 52, 20, 48, CLOSE
ENDSKETCH
EXTRUDE, pocket, -3, CUT, plate
NAME, LAST, plate
SKETCH, boss, top
SSPLINE, 40, 46, 54, 50, 50, 64, 42, 70, CLOSE
ENDSKETCH
EXTRUDE, boss, 8, ADD, plate
COLOR, LAST, GRAY
DATUM, DELETE, top

! the two pieces of the loaf still make the whole block
ASSERT, VOL(loaf) + VOL(3), EQ, 40*24*12, 0.01
```

</details>

---

## Sculpted head: brow ridges, nose and mouth brushed onto a mesh ball, mirrored, with a mask

![Sculpted head: brow ridges, nose and mouth brushed onto a mesh ball, mirrored, with a mask](examples/sculpt_head.png)

A face sculpted on a ball: every stroke is one SCULPT step (LANGUAGE.md section 28). In the window the Sculpt tab writes these lines for you as you drag over the mesh.

**Script:** [scripts/sculpt_head.cmd](../scripts/sculpt_head.cmd) (21 lines) · **Run:** `python -m modeler scripts/sculpt_head.cmd`

**You should get:** 1 body, volume 33,651.8 mm³, 1 faces

<details><summary>The whole script</summary>

```text
! A face sculpted on a ball: every stroke is one SCULPT step (LANGUAGE.md section 28).
! In the window the Sculpt tab writes these lines for you as you drag over the mesh.
SPHERE, 0, 0, 0, 20
NAME, LAST, head
TOMESH, head
REMESH, head, 0.6
! brow ridges (the mirror in x = 0 makes both)
STROKE, S1, "4,-19,6  6,-19,6.5  8,-19,7  10,-19,7.5  12,-19,8"
SCULPT, head, CLAY, 4, 0.8, S1, X
! the nose
STROKE, S2, "0,-20,-2  0,-20,0  0,-20,2"
SCULPT, head, INFLATE, 4, 0.9, S2
! the mouth (detail 0.25: the triangles there are split first, so the crease is sharp)
STROKE, S3, "2,-18,-8  4,-18,-8.4  6,-18,-8.9  9,-18,-9.5"
SCULPT, head, CREASE, 2.5, 0.6, S3, X, 0.25
! keep the brows, then dig the eye sockets
MASK, head, PAINT, 0, 0, 0, 4, 1, S1
STROKE, S4, "6,-16,2  7.5,-16,2  9,-16,2"
SCULPT, head, DRAW, 3, -0.8, S4, X
MASK, head, CLEAR
SCULPT, head, SMOOTH, 3, 0.5, S4, X
```

</details>

---

## Cover plate: chamfers, a hexagon window, a slot bent along an arc, a copied hole

![Cover plate: chamfers, a hexagon window, a slot bent along an arc, a copied hole](examples/cover_plate.png)

A cover plate drawn with the newer sketch tools: a chamfer of equal sides, a chamfer at an angle, a hexagon window, a slot bent along an arc and a hole copied with STRANSFORM. Change W or H and the outline follows.

**Script:** [scripts/cover_plate.cmd](../scripts/cover_plate.cmd) (19 lines) · **Run:** `python -m modeler scripts/cover_plate.cmd`

**You should get:** 1 body, volume 23,951.9 mm³, 21 faces

<details><summary>The whole script</summary>

```text
! A cover plate drawn with the newer sketch tools: a chamfer of equal
! sides, a chamfer at an angle, a hexagon window, a slot bent along an arc
! and a hole copied with STRANSFORM. Change W or H and the outline follows.
W = 90
H = 60
SKETCH, cover, XY
SRECT, 0, 0, 90, 60
SCON, COINCIDENT, 1.S, ORIGIN
SDIM, LENGTH, 1, W
SDIM, LENGTH, 2, H
SCHAMFER, 1.E, 8                        ! bottom right: 8 back along both sides
SCHAMFER, 3.E, 6, ANGLE, 30             ! top left: 6 along the top, at 30 deg to it
SFILLET, 2.E, 5                         ! top right
SNGON, 22, 30, 6, 9                     ! a hexagon, its corners on construction circle 11
SSLOTARC, 62, 24, 16, 20, 160, 3.5      ! middle radius 16 from 20 to 160 deg, 7 wide
SCIRCLE, 10, 10, 2.5
STRANSFORM, MOVE, 0, 40, 23, COPY       ! the same hole 40 higher
ENDSKETCH
EXTRUDE, cover, 5
```

</details>

---

## Cam plate: an elliptical outline, a slot along a curved path, an elliptical window, a hole touching two edges

![Cam plate: an elliptical outline, a slot along a curved path, an elliptical window, a hole touching two edges](examples/cam_plate.png)

A cam plate drawn with ellipses: an elliptical outline, a slot along a curved path (SOFFSET2), a hole that touches two edges (SCIRCLET), and an elliptical window. Change A or B and the outline follows.

**Script:** [scripts/cam_plate.cmd](../scripts/cam_plate.cmd) (18 lines) · **Run:** `python -m modeler scripts/cam_plate.cmd`

**You should get:** 1 body, volume 26,194.6 mm³, 9 faces

<details><summary>The whole script</summary>

```text
! A cam plate drawn with ellipses: an elliptical outline, a slot along a
! curved path (SOFFSET2), a hole that touches two edges (SCIRCLET), and an
! elliptical window. Change A or B and the outline follows.
A = 50
B = 32
SKETCH, cam, XY
SELLIPSE, 0, 0, A, B, 0, H              ! the outline: radius A along u, B across
SCON, COINCIDENT, 1.C, ORIGIN
SDIM, MAJOR, 1, A
SDIM, MINOR, 1, B
SARC, 0, -40, 50, 60, 120               ! a curved path ...
SOFFSET2, 4, 2                          ! ... made a slot 8 wide with round ends
SELLIPSE, -24, -14, 9, 5, 30            ! an elliptical window, turned 30 deg
SLINE, 18, -4, 40, -4, CONSTR           ! two construction edges ...
SLINE, 18, -4, 18, -24, CONSTR
SCIRCLET, 8, 9, R, 4, AT, 23, -9        ! ... and a hole of radius 4 touching both
ENDSKETCH
EXTRUDE, cam, 6
```

</details>

---

## Handle: a stepped edge joined into one spline, a nose spline extended to the base, a fillet between a line and a spline

![Handle: a stepped edge joined into one spline, a nose spline extended to the base, a fillet between a line and a spline](examples/spline_handle.png)

A handle outline made with spline editing: a stepped top edge and a nose joined into one smooth spline (SJOIN), carried on to the base (SEXTEND), the base extended to meet it, and the top left corner rounded with a fillet between a line and a spline.

**Script:** [scripts/spline_handle.cmd](../scripts/spline_handle.cmd) (20 lines) · **Run:** `python -m modeler scripts/spline_handle.cmd`

**You should get:** 1 body, volume 8,557.1 mm³, 7 faces

<details><summary>The whole script</summary>

```text
! A handle outline made with spline editing: a stepped top edge and a nose
! joined into one smooth spline (SJOIN), carried on to the base (SEXTEND),
! the base extended to meet it, and the top left corner rounded with a
! fillet between a line and a spline.
SKETCH, handle, XY
SLINE, 0, 0, 60, 0                       ! 1: the base
SLINE, 0, 0, 0, 12                       ! 2: the left end
SCON, COINCIDENT, 1.S, 2.S
SLINE, 0, 12, 20, 12                     ! 3, 4, 5: a step-shaped top edge ...
SARC, 30, 12, 10, 0, 180
SARC, 50, 12, 10, 180, 360
SSPLINE, 60, 12, 70, 20, 78, 14          ! 6: ... and a nose
SJOIN, 3, 4, 5, 6                        ! joined into one smooth spline (7)
SCON, COINCIDENT, 7.S, 2.E
SEXTEND, 7.E, 1                          ! carried on until it meets the base's line
SEXTEND, 1.E, 7                          ! and the base carried on to meet it
SFILLET, 2.E, 3                          ! round the top left corner (line and spline)
SCIRCLE, 12, 5, 2.5                      ! a hole for a lanyard
ENDSKETCH
EXTRUDE, handle, 8
```

</details>

---

## Sheet metal bracket: flanges bent up and down at three angles, and its flat blank with the bend allowances

![Sheet metal bracket: flanges bent up and down at three angles, and its flat blank with the bend allowances](examples/sheet_bracket.png)

Sheet metal (SHEET, FLANGE, UNFOLD): a bent bracket and its flat blank (docs/sheet-metal.md).

**Script:** [scripts/sheet_bracket.cmd](../scripts/sheet_bracket.cmd) (27 lines) · **Run:** `python -m modeler scripts/sheet_bracket.cmd`

**You should get:** 2 bodies, volume 21,922.0 mm³, 42 faces

<details><summary>The whole script</summary>

```text
! Sheet metal (SHEET, FLANGE, UNFOLD): a bent bracket and its flat blank (docs/sheet-metal.md).
W = 60
D = 40
T = 2
SKETCH, base, XY
SRECT, 0, 0, W, D
SCIRCLE, W/2, D/2, 6
SSLOT, 12, 10, 12, 30, 2.5
ENDSKETCH
! a 2 mm plate, bend radius 2, K-factor 0.44
SHEET, base, T, 2
NAME, LAST, bracket
! the front edge of the top face bends up 90 degrees, 25 long
SEL, S, EDGE, AT, W/2, 0, T
FLANGE, , 25
! the right edge of the bottom face bends down 45 degrees
SEL, S, EDGE, AT, W, D/2, 0
FLANGE, , 15, 45
! the back edge bends up a lip, 120 degrees, tighter radius
SEL, S, EDGE, AT, W/2, D, T
FLANGE, , 10, 120, 1
SEL, NONE
SHEETINFO, bracket
! the flat blank beside it (UNFOLD, bracket, blank.dxf also writes the DXF to cut)
UNFOLD, bracket
NAME, LAST, blank
FIT
```

</details>

---

## Ribs, lips and wrapping: an enclosure's two halves with a rib and a lip and groove, a gusset, a knob with wrapped grips

![Ribs, lips and wrapping: an enclosure's two halves with a rib and a lip and groove, a gusset, a knob with wrapped grips](examples/enclosure_halves.png)

Ribs, lips and wrapped text (RIB, LIP, WRAP): two halves of an enclosure and a knurled knob.

**Script:** [scripts/enclosure_halves.cmd](../scripts/enclosure_halves.cmd) (62 lines) · **Run:** `python -m modeler scripts/enclosure_halves.cmd`

**You should get:** 4 bodies, volume 38,000.7 mm³, 108 faces

<details><summary>The whole script</summary>

```text
! Ribs, lips and wrapped text (RIB, LIP, WRAP): two halves of an enclosure and a knurled knob.
W = 60
D = 40
H = 18
T = 2
! the base half: an open box with a rib across the floor and a lip on its rim
BLOCK, 0, 0, 0, W, D, H
NAME, LAST, base
SEL, S, FACE, AT, W/2, D/2, H
SHELL, T
PLANE, mid, XZ, D/2
SKETCH, r1, mid
SLINE, -(W - T), H/2, -T, H/2
ENDSKETCH
RIB, r1, 1.5, base
SEL, S, FACE, AT, T/2, D/2, H
LIP, , 2, 0.8
! the lid: the same box, upside down above it, with the matching groove
BLOCK, 0, 0, H + 15, W, D, 8
NAME, LAST, lid
SEL, S, FACE, AT, W/2, D/2, H + 15
SHELL, T
SEL, S, FACE, AT, T/2, D/2, H + 15
LIP, , 2, 0.8, GROOVE, 0.2
! a gusset in the corner of an angle bracket
BLOCK, 80, 0, 0, 40, 30, 4
NAME, LAST, angle
BLOCK, 80, 0, 0, 4, 30, 40
UNION, angle, LAST
PLANE, g, XZ, 15
SKETCH, gs, g
SLINE, -84, 30, -110, 4
ENDSKETCH
RIB, gs, 3, angle
! a knob with raised grips and a sunk band wrapped round it
CYL, 150, 20, 0, 12, 20
NAME, LAST, knob
PLANE, k, XZ, 5
SKETCH, grips, k
SRECT, -150 - 28 - 1.5, 5, -150 - 28 + 1.5, 17
SRECT, -150 - 21 - 1.5, 5, -150 - 21 + 1.5, 17
SRECT, -150 - 14 - 1.5, 5, -150 - 14 + 1.5, 17
SRECT, -150 - 7 - 1.5, 5, -150 - 7 + 1.5, 17
SRECT, -150 + 0 - 1.5, 5, -150 + 0 + 1.5, 17
SRECT, -150 + 7 - 1.5, 5, -150 + 7 + 1.5, 17
SRECT, -150 + 14 - 1.5, 5, -150 + 14 + 1.5, 17
SRECT, -150 + 21 - 1.5, 5, -150 + 21 + 1.5, 17
SRECT, -150 + 28 - 1.5, 5, -150 + 28 + 1.5, 17
ENDSKETCH
SEL, S, FACE, AT, 162, 20, 10
WRAP, grips, , 1
SKETCH, band, k
SRECT, -150 - 35, 1.5, -150 + 35, 3
ENDSKETCH
SEL, S, FACE, AT, 162, 20, 10
WRAP, band, , 0.4, CUT
SEL, NONE
! the planes were only for the sketches
DATUM, DELETE, mid
DATUM, DELETE, g
DATUM, DELETE, k
FIT
```

</details>

---

## Scan to CAD for machined parts: a mesh of a block split into planes, cylinders and a sphere, fitted exactly and joined into a solid

![Scan to CAD for machined parts: a mesh of a block split into planes, cylinders and a sphere, fitted exactly and joined into a solid](examples/scan_machined.png)

Scan to CAD for machined parts (SEGMENT, RECONSTRUCT): a mesh of a block with a bore, a boss and a dome is split at its sharp edges, each region is fitted exactly as a plane, cylinder or sphere, and the fitted faces are joined into one exact solid. Here the mesh is made with TOMESH; a real scan is IMPORTed.

**Script:** [scripts/scan_machined.cmd](../scripts/scan_machined.cmd) (20 lines) · **Run:** `python -m modeler scripts/scan_machined.cmd`

**You should get:** 2 bodies, volume 95,640.0 mm³, 12 faces

<details><summary>The whole script</summary>

```text
! Scan to CAD for machined parts (SEGMENT, RECONSTRUCT): a mesh of a block with a bore, a boss and a dome
! is split at its sharp edges, each region is fitted exactly as a plane, cylinder or sphere, and the
! fitted faces are joined into one exact solid. Here the mesh is made with TOMESH; a real scan is IMPORTed.
BLOCK, 0, 0, 0, 60, 40, 20
NAME, LAST, part
CYL, 35, 20, -1, 5, 30
SUBTRACT, part, LAST
CYL, 45, 20, 20, 6, 10
UNION, part, LAST
SPHERE, 15, 20, 20, 5
UNION, part, LAST
TOMESH, part
NAME, part, scan
! what is in the scan: 10 regions, each with its fit
SEGMENT, scan
RECONSTRUCT, scan
NAME, LAST, solid
MOVE, solid, 0, 50, 0
COLOR, solid, ORANGE
FIT
```

</details>

---

## Assembly that moves: a lid on a hinge, driven by a parameter; MOTION finds where it hits the post

![Assembly that moves: a lid on a hinge, driven by a parameter; MOTION finds where it hits the post](examples/hinged_lid.png)

Assemblies that move (DRIVE, MOTION, the Motion window): a lid on a hinge and a post it hits. Motion window: Inspect > Motion…, parameter A from 0 to 180. From a shell: python -m modeler render scripts/hinged_lid.cmd --motion A 0 180 18 frames

**Script:** [scripts/hinged_lid.cmd](../scripts/hinged_lid.cmd) (17 lines) · **Run:** `python -m modeler scripts/hinged_lid.cmd`

**You should get:** 3 bodies, volume 9,248.2 mm³, 15 faces

<details><summary>The whole script</summary>

```text
! Assemblies that move (DRIVE, MOTION, the Motion window): a lid on a hinge and a post it hits.
! Motion window: Inspect > Motion…, parameter A from 0 to 180. From a shell:
!   python -m modeler render scripts/hinged_lid.cmd --motion A 0 180 18 frames
A = 60
BLOCK, 0, 0, 0, 40, 30, 5
NAME, LAST, base
COLOR, base, BLUE
BLOCK, 0, 0, 5, 40, 30, 2
NAME, LAST, lid
COLOR, lid, ORANGE
! the hinge line is the base's top back edge, along Y
ROTATE, lid, -A, 0, 0, 5, 0, 1, 0
CYL, -20, 15, 0, 3, 30
NAME, LAST, post
! where does the lid hit the post? (MOTION reports it and puts A back)
MOTION, A, 0, 180, 12
FIT
```

</details>

---

## Scan to CAD: a sculpted mesh fitted as one smooth solid (with a hole cut through it) and a painted region fitted as one face

![Scan to CAD: a sculpted mesh fitted as one smooth solid (with a hole cut through it) and a painted region fitted as one face](examples/scan_to_cad.png)

Scan to CAD (FITSURF): smooth NURBS surfaces fitted to meshes (docs/mesh-fit.md). A sculpted head stands in for a scanned part.

**Script:** [scripts/scan_to_cad.cmd](../scripts/scan_to_cad.cmd) (22 lines) · **Run:** `python -m modeler scripts/scan_to_cad.cmd`

**You should get:** 3 bodies, volume 65,178.4 mm³, 4 faces

<details><summary>The whole script</summary>

```text
! Scan to CAD (FITSURF): smooth NURBS surfaces fitted to meshes (docs/mesh-fit.md).
! A sculpted head stands in for a scanned part.
SPHERE, 0, 0, 0, 20
NAME, LAST, scan
TOMESH, scan
REMESH, scan, 0.8
STROKE, S1, "0,-20,-2  0,-20,0  0,-20,2"
SCULPT, scan, INFLATE, 5, 0.9, S1
STROKE, S2, "6,-18,6  10,-17,7  14,-15,7"
SCULPT, scan, CLAY, 4, 0.6, S2, X
! the whole closed mesh: one smooth surface wrapped round it, closed into a solid
FITSURF, scan, ALL, 0.15
NAME, LAST, fitted
MOVE, fitted, 50, 0, 0
! only the face of it: paint the region, then fit that region as one trimmed face
MASK, scan, PAINT, 0, -20, 2, 16
FITSURF, scan, MASK, 0.1
NAME, LAST, front
MOVE, front, 100, 0, 0
! the fitted solid is ordinary CAD: it takes booleans, fillets and shells
CYL, 50, 0, -30, 4, 60
SUBTRACT, fitted, LAST
```

</details>

---

## Exploded view with trail lines (XSTEP, XSHOW), and marks wrapped onto a cone

![Exploded view with trail lines (XSTEP, XSHOW), and marks wrapped onto a cone](examples/exploded_view.png)

Exploded views (XSTEP, XSHOW) and a label wrapped onto a cone (WRAP): a box with a lid, four screws and a conical knob. XSTEP records how the parts come apart; XSHOW shows it with trail lines, and the parts go back before the next command (or XSHOW alone).

**Script:** [scripts/exploded_view.cmd](../scripts/exploded_view.cmd) (39 lines) · **Run:** `python -m modeler scripts/exploded_view.cmd`

**You should get:** 7 bodies, volume 60,789.1 mm³, 42 faces

<details><summary>The whole script</summary>

```text
! Exploded views (XSTEP, XSHOW) and a label wrapped onto a cone (WRAP): a box with a lid, four screws
! and a conical knob. XSTEP records how the parts come apart; XSHOW shows it with trail lines, and
! the parts go back before the next command (or XSHOW alone).
BLOCK, -30, -20, 0, 60, 40, 20
NAME, LAST, box
BLOCK, -30, -20, 20, 60, 40, 4
NAME, LAST, lid
COLOR, lid, ORANGE
CYL, -25, -15, 14, 2, 14
NAME, LAST, screw_1
COLOR, LAST, GREY
CYL, 25, -15, 14, 2, 14
NAME, LAST, screw_2
COLOR, LAST, GREY
CYL, -25, 15, 14, 2, 14
NAME, LAST, screw_3
COLOR, LAST, GREY
CYL, 25, 15, 14, 2, 14
NAME, LAST, screw_4
COLOR, LAST, GREY
CONE, 0, 0, 24, 10, 6, 12
NAME, LAST, knob
COLOR, knob, BLUE
! a band of text-like marks round the knob: the sketch is laid on the cone's development
PLANE, w, XZ, -20
SKETCH, marks, w
SRECT, -1, 27, 1, 33
SRECT, 4, 27, 6, 33
SRECT, -6, 27, -4, 33
ENDSKETCH
SEL, S, FACE, TYPE, CONE
WRAP, marks, , 0.6
DATUM, DELETE, w
! the exploded view: the knob and screws first, then the lid
XSTEP, apart, knob, 0, 0, 30
XSTEP, apart, "screw_1 screw_2 screw_3 screw_4", 0, 0, 45
XSTEP, apart, "lid knob", 0, 0, 25
! show it with: XSHOW, apart  (and XSHOW alone to put the parts back)
FIT
```

</details>

---

## Frames and weldments: a welded table of square tube with mitred top corners, butted legs and an angle brace, a weld bead on every joint (WELD); CUTLIST lists the cuts and welds

![Frames and weldments: a welded table of square tube with mitred top corners, butted legs and an angle brace, a weld bead on every joint (WELD); CUTLIST lists the cuts and welds](examples/welded_frame.png)

Frames and weldments (MEMBER, CUTLIST): a small welded table. The top frame is square tube with mitred corners, the legs are square tube butted under it, and a cross brace of angle runs between two legs. WELD, ALL puts a 4 mm bead on every joint, and CUTLIST gives what to cut (lengths and end angles, with how many of each) and the weld length.

**Script:** [scripts/welded_frame.cmd](../scripts/welded_frame.cmd) (27 lines) · **Run:** `python -m modeler scripts/welded_frame.cmd`

**You should get:** 29 bodies, volume 935,183.5 mm³, 386 faces

<details><summary>The whole script</summary>

```text
! Frames and weldments (MEMBER, CUTLIST): a small welded table. The top frame is square tube with
! mitred corners, the legs are square tube butted under it, and a cross brace of angle runs between
! two legs. WELD, ALL puts a 4 mm bead on every joint, and CUTLIST gives what to cut (lengths and end
! angles, with how many of each) and the weld length.
W = 600
D = 400
H = 450
T = 30
POLYLINE, (0,0,H), (W,0,H), (W,D,H), (0,D,H), CLOSE
NAME, LAST, top_path
MEMBER, top_path, SQUARE, 30x2, MITRE, rail
HIDE, top_path
*DO, i, 0, 1
  *DO, j, 0, 1
    POLYLINE, (T/2 + i*(W - T), T/2 + j*(D - T), 0), (T/2 + i*(W - T), T/2 + j*(D - T), H - T/2)
    HIDE, LAST
    MEMBER, LAST, SQUARE, 30x2, BUTT, leg
  *ENDDO
*ENDDO
POLYLINE, (T, T/2, 120), (W - T, T/2, 120)
NAME, LAST, brace_path
MEMBER, brace_path, ANGLE, 25x25x3, BUTT, brace, 180
HIDE, brace_path
COLOR, brace_1, ORANGE
WELD, ALL, 4
CUTLIST
FIT
```

</details>

---

## A first strength check: an aluminium bracket bolted to a wall, 400 N on its arm, coloured by stress (STRESS)

![A first strength check: an aluminium bracket bolted to a wall, 400 N on its arm, coloured by stress (STRESS)](examples/bracket_strength.png)

A first strength check (STRESS): an aluminium L-bracket bolted to a wall by its back plate, with 400 N hanging from the end of its arm. CM names the faces so the check reads plainly; STRESS colours the part (red: the 99.5% stress) and gives the largest stress, deflection and safety factor.

**Script:** [scripts/bracket_strength.cmd](../scripts/bracket_strength.cmd) (21 lines) · **Run:** `python -m modeler scripts/bracket_strength.cmd`

**You should get:** 1 body, volume 24,735.7 mm³, 10 faces

<details><summary>The whole script</summary>

```text
! A first strength check (STRESS): an aluminium L-bracket bolted to a wall by its back plate, with
! 400 N hanging from the end of its arm. CM names the faces so the check reads plainly; STRESS colours
! the part (red: the 99.5% stress) and gives the largest stress, deflection and safety factor.
BLOCK, 0, 0, 0, 60, 40, 6
NAME, LAST, bracket
BLOCK, 0, 0, 0, 6, 40, 50
UNION, bracket, LAST
SEL, S, EDGE, LOC, X, 6
SEL, R, EDGE, LOC, Z, 6
FILLET, 3                             ! round the inside corner
CYL, 45, 20, -1, 4, 10
SUBTRACT, bracket, LAST
MATERIAL, bracket, ALUMINIUM
SEL, S, FACE, NORMAL, -1, 0, 0
CM, wall, FACE
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, LOC, X, 60
CM, tip, FACE
SEL, NONE
STRESS, bracket, wall, tip, FORCE, 0, 0, -400
FIT
```

</details>

---

## Ready to 3D print? A wall hook built standing up: red overhangs need support, blue sits on the bed (PRINTCHECK)

![Ready to 3D print? A wall hook built standing up: red overhangs need support, blue sits on the bed (PRINTCHECK)](examples/print_check.png)

Ready to 3D print? (PRINTCHECK): a wall hook with a cable hole through its back and an arm sticking out. Built standing up (+Z), the arm's underside and the top of the hole hang over more than 45 degrees and are coloured red (they need support); blue sits on the bed. PRINTCHECK, hook, BEST tries the six directions: on its side (+X) only the top of the hole needs support.

**Script:** [scripts/print_check.cmd](../scripts/print_check.cmd) (13 lines) · **Run:** `python -m modeler scripts/print_check.cmd`

**You should get:** 1 body, volume 32,011.7 mm³, 13 faces

<details><summary>The whole script</summary>

```text
! Ready to 3D print? (PRINTCHECK): a wall hook with a cable hole through its back and an arm
! sticking out. Built standing up (+Z), the arm's underside and the top of the hole hang
! over more than 45 degrees and are coloured red (they need support); blue sits on the bed.
! PRINTCHECK, hook, BEST tries the six directions: on its side (+X) only the top of the hole needs support.
BLOCK, 0, 0, 0, 40, 8, 60
NAME, LAST, hook
BLOCK, 0, 0, 44, 40, 40, 8
UNION, hook, LAST
BLOCK, 0, 32, 52, 40, 8, 10
UNION, hook, LAST
CYL, 20, -1, 20, 5, 10, 0, 1, 0
SUBTRACT, hook, LAST
PRINTCHECK, hook
```

</details>

---

## 2.5D milling: a pocket around a boss cleared in rings, with G-code (MILL)

![2.5D milling: a pocket around a boss cleared in rings, with G-code (MILL)](examples/milled_plate.png)

2.5D milling (MILL): a plate with a pocket around a round boss and two bolt holes. The pocket is cleared down to its floor in rings, from the middle out to the wall, 4 mm a cut with a 6 mm end mill; MILL, ..., file.nc writes the G-code. The cyan lines are the tool's centre.

**Script:** [scripts/milled_plate.cmd](../scripts/milled_plate.cmd) (17 lines) · **Run:** `python -m modeler scripts/milled_plate.cmd`

**You should get:** 1 body, volume 60,154.6 mm³, 15 faces

<details><summary>The whole script</summary>

```text
! 2.5D milling (MILL): a plate with a pocket around a round boss and two bolt holes. The pocket
! is cleared down to its floor in rings, from the middle out to the wall, 4 mm a cut with a 6 mm
! end mill; MILL, ..., file.nc writes the G-code. The cyan lines are the tool's centre.
BLOCK, 0, 0, 0, 80, 60, 16
NAME, LAST, plate
BLOCK, 12, 12, 6, 48, 36, 20
SUBTRACT, plate, LAST
CYL, 36, 30, 6, 7, 10
UNION, plate, LAST
CYL, 70, 10, -1, 3, 20
SUBTRACT, plate, LAST
CYL, 70, 50, -1, 3, 20
SUBTRACT, plate, LAST
SEL, S, FACE, LOC, Z, 6
CM, floor, FACE
SEL, NONE
MILL, plate, POCKET, floor, 6, 4
```

</details>

---

## Will it stand up? A table with a book tipping off, a floating lamp shade and a shelf held only at its side, marked (GRAVITY)

![Will it stand up? A table with a book tipping off, a floating lamp shade and a shelf held only at its side, marked (GRAVITY)](examples/gravity_check.png)

Will it stand up? (GRAVITY): a small table on four legs with things on it. The vase stands well, the book hangs too far over the edge and tips off, the lamp shade was drawn 0.4 above its stand (a gap: it floats), and the side shelf touches only the table's side, so it needs fasteners unless it is listed as fastened. Problem parts are marked in the view.

**Script:** [scripts/gravity_check.cmd](../scripts/gravity_check.cmd) (31 lines) · **Run:** `python -m modeler scripts/gravity_check.cmd`

**You should get:** 10 bodies, volume 43,705.5 mm³, 51 faces

<details><summary>The whole script</summary>

```text
! Will it stand up? (GRAVITY): a small table on four legs with things on it. The vase stands
! well, the book hangs too far over the edge and tips off, the lamp shade was drawn 0.4 above
! its stand (a gap: it floats), and the side shelf touches only the table's side, so it needs
! fasteners unless it is listed as fastened. Problem parts are marked in the view.
BLOCK, 0, 0, 0, 6, 6, 70
NAME, LAST, leg1
BLOCK, 94, 0, 0, 6, 6, 70
NAME, LAST, leg2
BLOCK, 0, 54, 0, 6, 6, 70
NAME, LAST, leg3
BLOCK, 94, 54, 0, 6, 6, 70
NAME, LAST, leg4
BLOCK, 0, 0, 70, 100, 60, 4
NAME, LAST, top
MATERIAL, leg1, WOOD
MATERIAL, leg2, WOOD
MATERIAL, leg3, WOOD
MATERIAL, leg4, WOOD
MATERIAL, top, WOOD
CYL, 25, 30, 74, 6, 20
NAME, LAST, vase
MATERIAL, vase, GLASS
BLOCK, 88, 20, 74, 30, 20, 4
NAME, LAST, book
CYL, 60, 40, 74, 4, 25
NAME, LAST, stand
CONE, 60, 40, 99.4, 10, 4, 8
NAME, LAST, shade
BLOCK, 100, 10, 68, 15, 40, 4
NAME, LAST, shelf
GRAVITY
```

</details>

---

## Gears and fasteners: a pinion and a wheel in mesh, a planet in a ring gear and a rack, on cap screws with washers and nuts (GEAR, FASTENER)

![Gears and fasteners: a pinion and a wheel in mesh, a planet in a ring gear and a rack, on cap screws with washers and nuts (GEAR, FASTENER)](examples/gear_train.png)

Gears and fasteners (GEAR, FASTENER): a pinion driving a bigger gear on a plate, a planet inside a ring gear, and a rack. The 20-tooth pinion and the 30-tooth gear sit at the centre distance module x (20 + 30) / 2 = 50, the bigger one turned half a tooth (180/30 degrees) so the teeth fall into the gaps. The rack runs under the pinion, its pitch line on the pinion's pitch circle (0.02 lower, for a little play) and a gap (they come every 2 pi from its start) under the pinion's centre. Each gear has a bore and runs on a cap screw through the plate, with a washer under the head and a nut underneath.

**Script:** [scripts/gear_train.cmd](../scripts/gear_train.cmd) (30 lines) · **Run:** `python -m modeler scripts/gear_train.cmd`

**You should get:** 12 bodies, volume 206,989.4 mm³, 732 faces

<details><summary>The whole script</summary>

```text
! Gears and fasteners (GEAR, FASTENER): a pinion driving a bigger gear on a plate, a planet
! inside a ring gear, and a rack. The 20-tooth pinion and the 30-tooth gear sit at the centre
! distance module x (20 + 30) / 2 = 50, the bigger one turned half a tooth (180/30 degrees) so
! the teeth fall into the gaps. The rack runs under the pinion, its pitch line on the pinion's
! pitch circle (0.02 lower, for a little play) and a gap (they come every 2 pi from its start) under the
! pinion's centre. Each gear has a bore and runs on a cap screw through the plate,
! with a washer under the head and a nut underneath.
BLOCK, -50, -40, -8, 210, 90, 8
NAME, LAST, plate
MATERIAL, plate, ALUMINIUM
GEAR, 0, 0, 0, 2, 20, 10, , , 8
NAME, LAST, pinion
GEAR, 50, 0, 0, 2, 30, 10, , , 8
NAME, LAST, wheel
ROTATE, wheel, 6, 50, 0, 0
GEAR, 125, 0, 0, 1, 50, 6, INTERNAL, , 62
NAME, LAST, ring
GEAR, 140, 0, 0, 1, 20, 6, , , 6
NAME, LAST, planet
GEAR, -43.982297, -20.02, 0, 2, 8, 8, RACK
NAME, LAST, rack
FASTENER, WASHER, M8, 0, 0, 10
FASTENER, CAP, M8, 0, 0, 11.6, 25
FASTENER, NUT, M8, 0, 0, -8
FASTENER, WASHER, M8, 50, 0, 10
FASTENER, CAP, M8, 50, 0, 11.6, 25
FASTENER, NUT, M8, 50, 0, -8
CLASH, pinion, wheel
CLASH, ring, planet
CLASH, rack, pinion
```

</details>

---

## A moulded case seen from its open side: screw bosses with ribs, snap hooks on the rim and two vents (BOSS, SNAP, VENT)

![A moulded case seen from its open side: screw bosses with ribs, snap hooks on the rim and two vents (BOSS, SNAP, VENT)](examples/plastic_case.png)

A moulded case (BOSS, SNAP, VENT): a box hollowed to 2 mm walls and open at the bottom, with four screw bosses with ribs on the inside of the top, two snap hooks standing on the open rim, a vent of six slots in the top, and a second, turned vent in one end wall. The case is shown upside down (open side up) so the bosses and hooks can be seen; SNAP reports the bending strain each hook takes to snap in.

**Script:** [scripts/plastic_case.cmd](../scripts/plastic_case.cmd) (21 lines) · **Run:** `python -m modeler scripts/plastic_case.cmd`

**You should get:** 1 body, volume 30,022.6 mm³, 143 faces

<details><summary>The whole script</summary>

```text
! A moulded case (BOSS, SNAP, VENT): a box hollowed to 2 mm walls and open at the bottom, with
! four screw bosses with ribs on the inside of the top, two snap hooks standing on the open rim, a vent of six
! slots in the top, and a second, turned vent in one end wall. The case is shown upside down
! (open side up) so the bosses and hooks can be seen; SNAP reports the bending strain each
! hook takes to snap in.
BLOCK, 0, 0, 0, 90, 60, 30
NAME, LAST, case
MATERIAL, case, ABS
SEL, S, FACE, LOC, Z, 0
SHELL, 2
SEL, S, FACE, LOC, Z, 30
VENT, 6, 30, 2.5, 6, 0, 0, 0, 0
SEL, S, FACE, LOC, X, 90
VENT, 4, 16, 2, 4.5, 90
BOSS, case, 10, 10, 28, 20, 7, 2.5, 4, 0, 0, 0, -1
BOSS, case, 80, 10, 28, 20, 7, 2.5, 4, 0, 0, 0, -1
BOSS, case, 10, 50, 28, 20, 7, 2.5, 4, 0, 0, 0, -1
BOSS, case, 80, 50, 28, 20, 7, 2.5, 4, 0, 0, 0, -1
SNAP, case, 45, 0.4, 0, 10, 8, 1.2, 0.8, 0, 0, -1, 0, -1, 0
SNAP, case, 45, 59.6, 0, 10, 8, 1.2, 0.8, 0, 0, -1, 0, 1, 0
SEL, NONE
```

</details>

---

## Mould tools and notes: a drafted cap between its two mould halves, with an H7 bore note, a size and a material note (PARTING, MOLD, NOTE, FITS)

![Mould tools and notes: a drafted cap between its two mould halves, with an H7 bore note, a size and a material note (PARTING, MOLD, NOTE, FITS)](examples/cap_mould.png)

Mould tools and notes (PARTING, MOLD, NOTE, FITS): a round cap moulded in ABS. Its side gets 2 degrees of draft, so PARTING finds every face coming out of one half with a flat parting line at the bottom. MOLD makes the two halves round it with 0.5% shrink, shown pulled apart. The bearing bore is machined after moulding: NOTE, FIT pins its H7 size, NOTE, SIZE the cap's height, and a note says the material. FITS gives the fit with a g6 shaft.

**Script:** [scripts/cap_mould.cmd](../scripts/cap_mould.cmd) (25 lines) · **Run:** `python -m modeler scripts/cap_mould.cmd`

**You should get:** 3 bodies, volume 172,892.7 mm³, 22 faces

<details><summary>The whole script</summary>

```text
! Mould tools and notes (PARTING, MOLD, NOTE, FITS): a round cap moulded in ABS. Its side gets 2
! degrees of draft, so PARTING finds every face coming out of one half with a flat parting line at
! the bottom. MOLD makes the two halves round it with 0.5% shrink, shown pulled apart. The bearing
! bore is machined after moulding: NOTE, FIT pins its H7 size, NOTE, SIZE the cap's height, and a
! note says the material. FITS gives the fit with a g6 shaft.
CYL, 0, 0, 0, 30, 14
NAME, LAST, cap
MATERIAL, cap, ABS
SEL, S, FACE, LOC, Z, 0
SEL, A, FACE, LOC, Z, 14
SEL, INVE
DRAFT, 2
SEL, S, EDGE, LOC, Z, 14
FILLET, 3
PARTING, cap
MOLD, cap, 8, 0.5
MOVE, cap_top, 0, 0, 45
MOVE, cap_bottom, 0, 0, -30
HOLE, cap, 0, 0, 14, 12
SEL, S, FACE, TYPE, CYLINDER
NOTE, FIT, H7
FITS, H7/g6
NOTE, SIZE, 31, 0, 0, 31, 0, 14
NOTE, "ABS, 0.5% shrink", -45, 0, 25, -25, 0, 8
SEL, NONE
```

</details>

---

## Pipes and cables: a water line bent at its corners with a tee branch, and a cable bundle on a tray (ROUTE, ROUTES)

![Pipes and cables: a water line bent at its corners with a tee branch, and a cable bundle on a tray (ROUTE, ROUTES)](examples/pipe_run.png)

Pipes and cables (ROUTE, ROUTES): a water line along a skid, bent at each corner, with a branch that joins it as a tee, and a cable bundle of seven wires run beside it on a tray. ROUTES lists each route's length, straight pieces and bends, and the total per size.

**Script:** [scripts/pipe_run.cmd](../scripts/pipe_run.cmd) (25 lines) · **Run:** `python -m modeler scripts/pipe_run.cmd`

**You should get:** 7 bodies, volume 2,102,540.4 mm³, 43 faces

<details><summary>The whole script</summary>

```text
! Pipes and cables (ROUTE, ROUTES): a water line along a skid, bent at each corner, with a branch that
! joins it as a tee, and a cable bundle of seven wires run beside it on a tray. ROUTES lists each
! route's length, straight pieces and bends, and the total per size.
L = 600
BLOCK, -40, -60, -40, L + 80, 260, 10
NAME, LAST, skid
COLOR, skid, GREY
POLYLINE, (0,0,40), (L,0,40), (L,180,40), (L,180,240)
NAME, LAST, main_path
ROUTE, main_path, PIPE, 28x2, 50, water
POLYLINE, (L/2,0,40), (L/2,0,140), (L/2 + 120,0,140)
NAME, LAST, branch_path
ROUTE, branch_path, PIPE, 28x2, 50
BLOCK, 0, 150, -30, L - 100, 40, 4
NAME, LAST, tray
COLOR, tray, ORANGE
POLYLINE, (0,170,-20), (L - 150,170,-20), (L - 150,170,100), (L - 60, 170, 100)
NAME, LAST, cable_path
ROUTE, cable_path, CABLE, 7x4, 30
COLOR, cable_1, BLUE
HIDE, main_path
HIDE, branch_path
HIDE, cable_path
ROUTES
FIT
```

</details>

---

## Tolerances: datums, flatness, parallelism and an H7 bore placed by position, cut open by a section plane (NOTE, STACKUP, SECTION)

![Tolerances: datums, flatness, parallelism and an H7 bore placed by position, cut open by a section plane (NOTE, STACKUP, SECTION)](examples/toleranced_plate.png)

Tolerances (NOTE, STACKUP, SECTION): a bearing plate with datums A (the bottom) and B (the left side), the top held flat and parallel to A, the bore placed to A and B and toleranced H7, and a stack-up of the shaft's end play through the plate. SECTION cuts the view open through the bore.

**Script:** [scripts/toleranced_plate.cmd](../scripts/toleranced_plate.cmd) (20 lines) · **Run:** `python -m modeler scripts/toleranced_plate.cmd`

**You should get:** 1 body, volume 177,862.8 mm³, 7 faces

<details><summary>The whole script</summary>

```text
! Tolerances (NOTE, STACKUP, SECTION): a bearing plate with datums A (the bottom) and B (the left side),
! the top held flat and parallel to A, the bore placed to A and B and toleranced H7, and a stack-up of
! the shaft's end play through the plate. SECTION cuts the view open through the bore.
BLOCK, 0,0,0, 120,80,20
NAME, LAST, plate
HOLE, plate, 60,40,20, 30
SEL, S, FACE, LOC, Z, 0
NOTE, DATUM, A
SEL, S, FACE, LOC, X, 0
NOTE, DATUM, B
SEL, S, FACE, LOC, Z, 20
NOTE, GDT, FLATNESS, 0.02
NOTE, GDT, PARALLELISM, 0.05, A
SEL, S, FACE, TYPE, CYLINDER
NOTE, FIT, H7
NOTE, GDT, POSITION, D0.05, A, B
SEL, NONE
STACKUP, +20.2 ±0.05, -20 ±0.05, MIN=0.05, MAX=0.4
SECTION, ZX, ABOVE, 40
FIT
```

</details>

---

## Cams and more gears: a disc cam lifting its roller, a barrel cam, a bevel pair at right angles and a worm driving its wheel (CAM, CAMLIFT, GEAR BEVEL/WORM/WORMWHEEL)

![Cams and more gears: a disc cam lifting its roller, a barrel cam, a bevel pair at right angles and a worm driving its wheel (CAM, CAMLIFT, GEAR BEVEL/WORM/WORMWHEEL)](examples/cam_follower.png)

Cams and more gears: a disc cam lifting its roller (CAM, CAMLIFT), a barrel cam with its groove, a pair of bevel gears at right angles, and a worm driving a worm wheel. Change A to turn the cam; the roller follows by CAMLIFT.

**Script:** [scripts/cam_follower.cmd](../scripts/cam_follower.cmd) (17 lines) · **Run:** `python -m modeler scripts/cam_follower.cmd`

**You should get:** 8 bodies, volume 338,040.8 mm³, 584 faces

<details><summary>The whole script</summary>

```text
! Cams and more gears: a disc cam lifting its roller (CAM, CAMLIFT), a barrel cam with its groove,
! a pair of bevel gears at right angles, and a worm driving a worm wheel. Change A to turn the cam;
! the roller follows by CAMLIFT.
A = 40
LAW = "R12/150 D30 F12/150 D30"
CAM, 0, 0, 0, LAW, 30, 8, 12, DISC, 10
ROTATE, cam_1, A, 0, 0, 0, 0, 0, 1
MOVE, cam_1_roller, CAMLIFT(LAW, A), 0, 0
CAM, -110, 0, 0, "R30/180H F30/180H", 30, 6, 80, BARREL, 12
! a bevel pair, 20 teeth meshing with 30, the axes meeting at a right angle
GEAR, 0, 90, 0, 2, 20, 10, BEVEL, 0, 8, 20, 0, 0, 1, 30
GEAR, 20.1, 90, 30, 2, 30, 10, BEVEL, 0, 10, 20, -1, 0, 0, 20
ROTATE, LAST, 6, 20.1, 90, 30, -1, 0, 0
! a single-start worm along X and its wheel
GEAR, 70, 0, 0, 2, 1, 60, WORM, 0, 0, 20, 1, 0, 0
GEAR, 100, -8, 40.15, 2, 30, 16, WORMWHEEL, 0, 10, 20, 0, 1, 0
ROTATE, LAST, 8, 100, -8, 40.15, 0, 1, 0
```

</details>

---

## A quick topology check: the 30% of a plate that carries a load from its tip to the wall best, as a mesh to model a part after (TOPOPT)

![A quick topology check: the 30% of a plate that carries a load from its tip to the wall best, as a mesh to model a part after (TOPOPT)](examples/topo_bracket.png)

A quick topology check (TOPOPT): which 30% of a plate carries a load best? The plate is held at its left end and pulled down at the middle of its right end; TOPOPT keeps the material that makes it stiffest, as a mesh body to model a real part after. The plate itself is hidden.

**Script:** [scripts/topo_bracket.cmd](../scripts/topo_bracket.cmd) (16 lines) · **Run:** `python -m modeler scripts/topo_bracket.cmd`

**You should get:** 2 bodies, volume 63,167.9 mm³, 7 faces

<details><summary>The whole script</summary>

```text
! A quick topology check (TOPOPT): which 30% of a plate carries a load best? The plate is held
! at its left end and pulled down at the middle of its right end; TOPOPT keeps the material that
! makes it stiffest, as a mesh body to model a real part after. The plate itself is hidden.
BLOCK, 0, 0, 0, 120, 8, 50
NAME, LAST, plate
BLOCK, 116, 0, 20, 4, 8, 10
NAME, LAST, pad
UNION, plate, pad
SEL, S, FACE, NORMAL, -1, 0, 0
CM, wall, FACE
SEL, S, FACE, NORMAL, 1, 0, 0
SEL, R, FACE, LOC, X, 120
CM, tip, FACE
SEL, NONE
TOPOPT, plate, wall, tip, FORCE, 0, 0, -1000, 0.3, 30
FIT
```

</details>
