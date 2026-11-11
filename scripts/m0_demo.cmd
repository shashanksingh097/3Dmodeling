! M0 demo: three primitives, then a few picks like the viewport would make
BLOCK,  0,0,0, 20,10,5
CYL,    30,5,0, 4, 12
SPHERE, 0,25,5, 6
PICKMODE, FACE
PICK, FACE, 6          ! top face of the block
PICK, FACE, 8, A       ! add the cylinder's top cap
VIEW, ISO
FIT
