! template: sheet_metal
! title: New sheet metal part
! about: A bent sheet part in millimetres: thickness, bend radius and K-factor as parameters for SHEET and FLANGE, aluminium, and a sketch on XY for the flat outline.
! order: 3
/UNITS, MM
! the sheet: SHEET, base, T, R, K once the outline is drawn
T = 2
R = 2
K = 0.44
LAYER, construction, NEW, GREY
LAYER, DEFAULT
PROPERTY, TITLE, New sheet metal part
PROPERTY, MATERIAL, "Aluminium 5052, 2 mm"
SKETCH, base, XY
