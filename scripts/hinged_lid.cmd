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
