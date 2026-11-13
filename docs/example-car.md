# Example: a detailed car body

`scripts/car_body.cmd` builds the outside of a car (an original, generic
four-door saloon) with the command language only. It is a showcase and a
real-world test: about 500 lines of script make 218 bodies, every one of
which passes `CHECK`. Open it from File → Open example, or run it headless:

```bash
python -m modeler run scripts/car_body.cmd -q     # about 35 s
```

## How it is built

1. **Two master surfaces.** The lower body and the cabin are each one
   smooth NURBS surface: a row of closed control-point curves (`NURBS ...
   CLOSE`, one per station along the car, made by the macros `tsec` and
   `gsec`) joined by `NSURF`. The ends are closed with flat patches (`FILL`)
   and sewn into solids (`SEW`). A power bulge on the hood is three
   `MOVEPT` steps on the lower body's control net. Wheel wells are
   cylinders cut from each side.
2. **Panels with shut lines.** The lower body becomes a 3 mm skin
   (`SHELL`). The macro `panel` cuts one panel out of it with a rounded box
   (`RECT` swept along a line): the panel is the skin inside the box shrunk
   by 3 mm, and the skin loses the box grown by 3 mm, which leaves a 6 mm
   shut line. Panels are cut in order (lamps, bumpers, hood, fenders,
   doors, trunk lid, quarters), so a later box only has to be rough where
   an earlier panel already took the edge. What is left is the body frame:
   sills, cowl, floor and wheel wells.
3. **Glass and pillars.** The cabin becomes a 4 mm skin. The window
   openings are solids (polylines swept across the car); the skin inside
   each opening is a pane, and the skin with the openings cut out is the
   roof with its pillars.
4. **Details on the body's curves.** The macro `under` takes the part of
   the lower body inside a box and moves it in (or out) by a distance.
   Anything trimmed by it follows the body's curves at that distance: lamp
   housings 40 mm behind the lens, the light strips and projectors behind
   it, the honeycomb grille insert, the number plates standing 6 mm proud
   with their letters 2 mm above that, the diffuser and its fins, and the
   black sills.
5. **Parts placed many times.** Tyre (with grooves and tread cuts made
   with `ARRAY ... CUT`), rim (lofted spokes repeated with `ARRAY, POLAR`),
   drilled brake disc and caliper are parts, placed at four wheels; the
   right side is the same part turned 180°. Mirrors (lofted through
   ellipses) and door handles are parts too. The lip spoiler is a
   `RAILSWEEP` of an airfoil between two curved rails, and the fin antenna
   a `LOFT` of three airfoils, placed at the roof height measured from the
   roof itself (`BBOX(...).zmax` of a thin slice).

Layers give the colours (paint, glass, trim, chrome, lamps, tyres, rims,
brakes); the lamp lenses and mirror glass are `GLASS`, which is drawn
see-through. The cutting tools and curves sit on the layer `build`, which
is switched off at the end.

## Body names

Every part has a name, so it can be shown alone (`ISOLATE`) or moved:
`hood`, `bumper_f`, `bumper_r`, `trunk`, `spoiler`, `roof`, `antenna`,
`bodyframe`, `fender_l/_r`, `door_f_l/_r`, `door_r_l/_r`, `quarter_l/_r`,
`windscreen`, `backlight`, `glass_fl/fr/rl/rr`, `headlamp_l/_r` (with
`_housing`, `_strip`, `_projectors`), `taillamp_l/_r` (with `_housing`,
`_strip`), `grille`, `badge`, `badge_text`, `intake_l/_r`,
`foglamp_l/_r`, `plate_f/_r` (with `_text`), `diffuser`, `exhaust_l/_r`,
`sill_l/_r`, `mirror_l/_r`, `mirrorglass_l/_r`, `handle_f_l` ...,
`tyre_fl` ..., `rim_fl` ..., `disc_fl` ..., `caliper_fl` ... (fl, fr, rl,
rr).

## Things worth knowing that the example ran into

* `LAST-1` is arithmetic on IDs (the body whose ID is one less), not "the
  body made before the last one". A boolean or `OFFSET` makes a new ID, so
  keep IDs in parameters (`TX = LAST`) when other steps come in between.
* With `KEEP, ON` the kept inputs come back as new hidden bodies with new
  IDs; their names stay, so refer to a kept tool by name.
* A parameter and a body with the same name: the parameter wins. With a
  parameter `SKIN = 3`, `PICK, BODY, skin` picks body 3, not the body named
  `skin`. Give parameters and bodies different names.
* A bare word passed to a macro is text only when it is not already a
  name. A body's name passes its ID; quote it (`lampguts, "headlamp_l"`)
  when the macro needs the text, for example to make a layer of that name.
* `OFFSET` of a piece of the lower body can fail when the piece crosses
  the seam of the closed control-point rows (two faces meet there). Keep
  such boxes on one side of it, or use a plain plate behind an opening, as
  the intakes do.
* `ISOLATE` and `SHOW, ALL` act on every body, including helpers hidden on
  purpose (kept inputs, the master solids). Put helpers on a layer that is
  off; `SHOW, ALL` does not switch layers on.
