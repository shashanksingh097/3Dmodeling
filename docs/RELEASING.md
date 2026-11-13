# Building and releasing the desktop app

The app is packaged with [PyInstaller](https://pyinstaller.org) into a folder
that runs without Python installed. The recipe is `packaging/3Dmodeling.spec`;
the GitHub workflow `.github/workflows/release.yml` builds it on Windows,
macOS (Apple silicon) and Linux.

## What a build contains

| File | What it is |
|------|------------|
| `3Dmodeling` (`3Dmodeling.exe`) | the app window |
| `3Dmodeling-cli` (`3Dmodeling-cli.exe`) | the same program with a console, for scripts: `3Dmodeling-cli run part.cmd`, `3Dmodeling-cli check` |
| `_internal/` | Python, Qt, the Open CASCADE kernel and the example scripts |

On macOS the build is `3Dmodeling.app`; the command-line program is inside it
at `3Dmodeling.app/Contents/MacOS/3Dmodeling-cli`. Unpacked, a build is about
1 GB (the kernel and its libraries are most of it); the download is a third
of that.

## Build on your own machine

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e . pyinstaller
pyinstaller packaging/3Dmodeling.spec --noconfirm
dist/3Dmodeling/3Dmodeling-cli check
dist/3Dmodeling/3Dmodeling         # macOS: open dist/3Dmodeling.app
```

## Test builds from GitHub

Actions > **Release builds** > **Run workflow**. Each platform's zip (or
tar.gz) is attached to the run as an artifact for 14 days. Every build is
started headless and runs two example scripts before it is packed.

## Making a release

1. Set the version in `modeler/__init__.py` and `pyproject.toml`, and add a
   `## [x.y.z]` section to `CHANGELOG.md`. Merge that to `main`.
2. Tag it: `git tag v0.1.0 && git push origin v0.1.0`.
3. The workflow checks that the tag matches the version, builds all three
   platforms, and makes a **draft** release with the downloads attached and
   the changelog section as its notes.
4. Try a download, then press **Publish** on the draft.

If you cannot push tags, run the workflow by hand instead (Actions > Release
builds > Run workflow) with `tag` set to `v0.1.0` and, if it is not the
branch's head, `ref` set to the commit to release. It makes the same draft;
publishing the draft creates the tag on that commit.

## Unsigned builds

The builds are not code-signed yet, so the first start shows a warning:

* **Windows**: "Windows protected your PC": press *More info*, then *Run anyway*.
* **macOS**: right-click (or Control-click) `3Dmodeling.app`, choose *Open*,
  then *Open* again. If macOS says the app "is damaged", run
  `xattr -dr com.apple.quarantine 3Dmodeling.app` once in Terminal.
* **Linux**: unpack and run `3Dmodeling/3Dmodeling`. It needs a desktop with
  X11 or XWayland (most do).

## Where the app keeps things

| What | Where |
|------|-------|
| Autosave | the app data folder, `autosave.m3d` (`MODELER_AUTOSAVE` overrides) |
| Error and crash logs | `logs/` in the app data folder (`MODELER_LOG_DIR` overrides); Help > Open the log folder |
| Recent files and window layout | Qt settings for "3Dmodeling" |

The app data folder is `%APPDATA%\3Dmodeling\3Dmodeling` on Windows,
`~/Library/Application Support/3Dmodeling/3Dmodeling` on macOS and
`~/.local/share/3Dmodeling/3Dmodeling` on Linux.
