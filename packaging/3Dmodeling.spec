# PyInstaller recipe for the desktop app. Build with:
#     pip install pyinstaller
#     pyinstaller packaging/3Dmodeling.spec --noconfirm
# The app ends up in dist/3Dmodeling/ (and dist/3Dmodeling.app on macOS), with
# 3Dmodeling (the window) and 3Dmodeling-cli (for scripts, prints to the console).
# See docs/RELEASING.md.
import glob
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
hidden += ["scipy.sparse.linalg", "scipy.spatial"]  # STRESS, imported when it runs
hidden += ["PySide6.QtTest"]  # the desktop check moves the mouse with it (modeler/desktop_check.py)
hidden += ["manifold3d"]  # mesh booleans, imported when a mesh body is combined
try:  # the assistant (pip install ".[ai]"); its Copilot runtime downloads on first use
    hidden += collect_submodules("copilot")
except Exception:  # noqa: BLE001 - built without the assistant
    pass
examples = [(os.path.join(ROOT, "scripts", n), "modeler/examples")
            for n in sorted(os.listdir(os.path.join(ROOT, "scripts"))) if n.endswith(".cmd")]
SKILLS = os.path.join(ROOT, "modeler", "skills")  # the assistant's skill files (ai/skills.py)
examples += [(os.path.join(SKILLS, d, f), os.path.join("modeler", "skills", d))
             for d in sorted(os.listdir(SKILLS)) if os.path.isdir(os.path.join(SKILLS, d))
             for f in ("SKILL.md", "example.cmd") if os.path.isfile(os.path.join(SKILLS, d, f))]
examples += [(os.path.join(ROOT, "modeler", "plugin_examples", "bolt_ring.py"), "modeler/plugin_examples")]  # plugins.py
examples += [(p, "modeler/i18n") for p in glob.glob(os.path.join(ROOT, "modeler", "i18n", "*.ts"))]  # i18n language files
TEMPLATES = os.path.join(ROOT, "modeler", "templates")  # the start page's project templates (PLAN item 88)
examples += [(os.path.join(TEMPLATES, n), os.path.join("modeler", "templates"))
             for n in sorted(os.listdir(TEMPLATES)) if n.endswith((".cmd", ".kicad_pcb"))]  # + the bench's board
TUTORIALS = os.path.join(ROOT, "modeler", "tutorials")  # Help > Tutorials (PLAN item 94)
examples += [(os.path.join(TUTORIALS, n), os.path.join("modeler", "tutorials"))
             for n in sorted(os.listdir(TUTORIALS)) if n.endswith(".tut")]
TIPS = os.path.join(ROOT, "modeler", "gui", "tip_pictures")  # pictures in the buttons' tooltips
examples += [(os.path.join(TIPS, n), os.path.join("modeler", "gui", "tip_pictures"))
             for n in sorted(os.listdir(TIPS)) if n.endswith(".png")]
examples += [(os.path.join(ROOT, "docs", n), "modeler/docs")  # the assistant's search_docs (ai/knowledge.py)
             for n in ("LANGUAGE.md", "USER-GUIDE.md")]

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
