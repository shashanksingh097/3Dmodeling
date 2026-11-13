# PyInstaller recipe for the desktop app. Build with:
#     pip install pyinstaller
#     pyinstaller packaging/3Dmodeling.spec --noconfirm
# The app ends up in dist/3Dmodeling/ (and dist/3Dmodeling.app on macOS), with
# 3Dmodeling (the window) and 3Dmodeling-cli (for scripts, prints to the console).
# See docs/RELEASING.md.
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)
from modeler import __version__  # noqa: E402

# The kernel is one extension module (OCP.OCP); its sub-packages only
# re-export names. Take them all, except the VTK bridge the app never uses.
hidden = [m for m in collect_submodules("OCP") if ".IVtk" not in m] + collect_submodules("modeler")
hidden += collect_submodules("meshio")  # mesh file readers, imported when a mesh is read
try:  # the assistant (pip install ".[ai]"); its Copilot runtime downloads on first use
    hidden += collect_submodules("copilot")
except Exception:  # noqa: BLE001 - built without the assistant
    pass
examples = [(os.path.join(ROOT, "scripts", n), "modeler/examples")
            for n in sorted(os.listdir(os.path.join(ROOT, "scripts"))) if n.endswith(".cmd")]

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[ROOT],
    datas=examples,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "vtkmodules", "vtk", "IPython", "pytest",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtPdf"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="3Dmodeling",
    console=False,
    icon=None,
)
# Same program with a console, for scripts: 3Dmodeling-cli run part.cmd
cli = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="3Dmodeling-cli",
    console=True,
)
coll = COLLECT(exe, cli, a.binaries, a.datas, strip=False, upx=False, name="3Dmodeling")
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="3Dmodeling.app",
        bundle_identifier="io.github.shashanksingh097.modeler3d",
        version=__version__,
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": __version__,
            "CFBundleDocumentTypes": [{"CFBundleTypeName": "3Dmodeling project",
                                       "CFBundleTypeExtensions": ["m3d"],
                                       "CFBundleTypeRole": "Editor"}],
        },
    )
