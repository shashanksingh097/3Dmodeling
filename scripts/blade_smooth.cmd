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
