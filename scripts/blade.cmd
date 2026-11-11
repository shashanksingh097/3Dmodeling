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
*MACRO, section, x, dx, chord, pitch
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
  section, R_HUB - 2 + i*DS, DS + 0.01, CHORD_ROOT + (CHORD_TIP - CHORD_ROOT)*F, TWIST_ROOT + (TWIST_TIP - TWIST_ROOT)*F
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
