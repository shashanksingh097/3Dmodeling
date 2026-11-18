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

## Part 2: help browser, sizes on drawings, installers

**Help browser** (`gui/help_browser.py`, Help > Command reference, Ctrl+F1).
Built from the command registry, so it is never out of date:

- Left: every command under the command menu's headings (`forms.CATEGORIES`),
  the rest under "Other". The search box matches names, help and argument
  names or help, and keeps only the headings with matches, opened.
- Right: with a search, every match with its signature and help (the old
  reference page). A picked command gets its own page: signature, help, an
  argument table with defaults, up to four lines from the example scripts
  that use it, whether it has a form, and links to the commands beside it.
- **Open form** and **Put in command line**. With a command typed, Ctrl+F1
  opens at it.

**Sizes on drawings** (`geometry/drawing.py`, `dimension`). Kept simple on
purpose, so that it is right without a layout engine:

- Overall sizes: each model direction once, on the first flat view that
  shows it, outside the view (horizontal below, vertical at the left). The
  number is the exact size of the bodies (`BRepBndLib.AddOptimal`), since
  curves are drawn as short lines and their drawn extent is a little short.
- Diameters: HLR keeps circles as circles in a view that sees them face-on
  (`GeomAbs_Circle`, a full turn or arcs that add up to one), so these are
  read from the visible edges. Equal ones in a view are counted; each
  diameter is written once on the sheet. Each size of circle gets its own
  leader angle (45, 135, 30, 150 degrees ...), so leaders of circles around
  one centre do not lie on top of each other, and a label that would cover
  another moves further out.
- Pieces: lines, filled arrows and text, in a `*-dims` SVG group or the DXF
  layer `DIMS` (TEXT with rotation, SOLID arrows, `%%c` for Ø).
- `sizes`: ALL (default), OVERALL, HOLES, NONE.

**Installers** (`.github/workflows/release.yml`, `packaging/3Dmodeling.wxs`):
a `.msi` made with WiX 5 (the `Files` glob takes the whole PyInstaller
folder; the main `.exe` is its own component so it can carry the advertised
Start menu shortcut), signed when the Windows secrets are set; and a `.dmg`
(the app plus a link to Applications, `hdiutil create -format UDZO`), signed
when the macOS secrets are set. The job installs the `.msi`, runs the
installed command line, checks the Start menu entry and removes it again;
it mounts the `.dmg` and runs the app's command line from it. The zips stay
for people who do not want to install.

## Still open in M8

- Sizes between features (hole positions, steps), and radii of arcs.
- A Linux AppImage or Flatpak.
