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

A plate held by 8 bolts and nuts with real ISO metric threads. One bolt part and one nut part, each placed 8 times. Change D and every bolt and nut is rebuilt at the new size, thread pitch included (PITCH(D) looks up the ISO coarse pitch). Each size is built once and copied.

**Script:** [scripts/threaded_bolts.cmd](../scripts/threaded_bolts.cmd) (39 lines) · **Run:** `python -m modeler scripts/threaded_bolts.cmd`

**You should get:** 17 bodies, volume 121,095.0 mm³, 1526 faces

<details><summary>The whole script</summary>

```text
! A plate held by 8 bolts and nuts with real ISO metric threads.
! One bolt part and one nut part, each placed 8 times. Change D and every
! bolt and nut is rebuilt at the new size, thread pitch included (PITCH(D)
! looks up the ISO coarse pitch). Each size is built once and copied.
D = 8            ! bolt size (M8)
T = 10           ! plate thickness
A = 40         ! bolt spacing

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

BLOCK, -A/2 - 15, -1.5*A - 15, -T, A + 30, 3*A + 30, T
NAME, LAST, plate
*DO, i, 0, 7
  X = A*((i % 2) - 0.5)
  Y = A*(INT(i/2) - 1.5)
  HOLE, plate, X, Y, 0, D + 1
  INST, bolt, X, Y, 0, D=D
  INST, nut, X, Y, -T - 0.8*D, D=D
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
