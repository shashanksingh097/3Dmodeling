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
