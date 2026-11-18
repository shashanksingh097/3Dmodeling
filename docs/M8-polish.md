# M8 polish: drawings, themes, signed builds (PLAN.md item 9)

## DRAWING

`modeler/geometry/drawing.py`; the command is in
`modeler/commands/drawing_handlers.py`.

- **Projection.** Each view is OCCT hidden-line removal: `HLRBRep_Algo`
  (exact, on the B-rep) for solids, `HLRBRep_PolyAlgo` (on triangles) for
  mesh bodies. The projector is a `gp_Ax2` whose Z points at the viewer and
  whose X is the drawing's x, so the drawing's y comes out as Z x X (up is
  +Z in the front, right and iso views, +Y in the top view).
- **Edges kept.** Sharp visible edges (`VCompound`) and visible outlines
  (`OutLineVCompound`), and the hidden ones of both. Smooth edges
  (`Rg1Line`, where a fillet meets a face) are left out, as on a usual
  drawing. Curves become polylines at 1/2000 of the model's size.
- **Sheet.** Third-angle placement: front at the origin, top above it
  (same x), right beside it (same y), iso in the free corner, any other
  views in a row after. Gaps are a fifth of the largest view.
- **True size.** SVG width and height are in the model's units (mm, cm or
  in) with a matching viewBox; DXF coordinates are model units, and
  `$INSUNITS` says which.
- **DXF** is written by hand, as R12 entities (LINE, POLYLINE/VERTEX,
  TEXT) with LTYPE (CONTINUOUS, HIDDEN) and LAYER (VISIBLE, HIDDEN, TEXT)
  tables. No new dependency, and R12 opens everywhere.

Timing: the flange (one body, 100 faces) takes 0.04 s for four views.

## Preferences and themes

`modeler/gui/prefs.py`, View > Preferences… (Ctrl+,).

- Light and dark themes use Fusion with their own palettes. "System"
  puts back the style and palette the app started with.
- The toolbar icons are drawn from the palette, and each QAction carries
  its icon name (`icon_name` property). After a theme change,
  `refresh_icons` draws them all again.
- The 3D view background is a gradient preset (`occ_view.BACKGROUNDS`).
  The axis triad's label colour flips to dark on light backgrounds.
- Settings keys: `theme`, `viewBackground`, plus the existing
  `toolbarButtons`. They are put back at start by `prefs.restore`.

## Code signing

`.github/workflows/release.yml` signs only when the secrets are set (see
docs/RELEASING.md). Without them it builds unsigned as before. A step's
own `env` is not visible to its `if`, so job-level `WIN_SIGN` and
`MAC_SIGN` flags say whether the secrets exist.

- **Windows:** signtool from the newest Windows Kit, SHA-256, with a
  DigiCert timestamp.
- **macOS:**
  - The certificate goes into a temporary keychain.
  - The app is signed with `codesign --deep --options runtime` and the
    entitlements that Python needs (`packaging/entitlements.plist`).
  - With the Apple ID secrets it is also notarized (`notarytool --wait`),
    stapled, and zipped again.
- Every release gets `SHA256SUMS.txt`.

The certificates themselves are the owner's to buy and add.

## Still open in M8

- Dimensions on drawings.
- Installers (.msi, .dmg).
- A help browser built from the command metadata.
