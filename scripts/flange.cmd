! Pipe flange: built only from primitives, booleans and fillets
CYL, 0,0,0, 40, 10          ! 1 flange disc
CYL, 0,0,10, 20, 30         ! 2 hub
UNION, 1, 2                 ! -> 3
CYL, 0,0,-5, 12, 50         ! 4 bore
SUBTRACT, 3, 4              ! -> 5
CYL, 30,0,-5, 4, 20         ! 6..11 six bolt holes on a 30 mm circle
CYL, 15,25.98,-5, 4, 20
CYL, -15,25.98,-5, 4, 20
CYL, -30,0,-5, 4, 20
CYL, -15,-25.98,-5, 4, 20
CYL, 15,-25.98,-5, 4, 20
SUBTRACT, 5, 6,7,8,9,10,11  ! -> 12
PICK, EDGE, 50              ! hub-to-flange edge (what clicking it emits)
PICK, EDGE, 43, A           ! outer rim, added with Ctrl+click
FILLET, 3                   ! -> 13
SEL, S, EDGE, 93            ! bore and hub top edges
SEL, A, EDGE, 99
CHAMFER, 1.5                ! -> 14
SPHERE, 0,75,10, 12         ! 15 a second part next to it:
BLOCK, -9,66,1, 18,18,18    ! 16
INTERSECT, 15, 16           ! -> 17 cube with spherical corners
PICKMODE, FACE
PICK, FACE, 78              ! the flange top face
VIEW, ISO
FIT
