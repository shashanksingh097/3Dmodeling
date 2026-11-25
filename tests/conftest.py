import os

# GUI tests must not write an autosave into the user's own app-data folder
os.environ.setdefault("MODELER_AUTOSAVE", "off")

# nor read the user's own assistant skills (ai/skills.py): only the built-in ones count
import tempfile  # noqa: E402

os.environ.setdefault("MODELER_SKILLS_HOME", os.path.join(tempfile.gettempdir(), "modeler-test-no-user-skills"))
os.environ.pop("MODELER_SKILLS", None)

# nor load the user's own plug-ins (modeler/plugins.py)
os.environ.setdefault("MODELER_PLUGINS_HOME", os.path.join(tempfile.gettempdir(), "modeler-test-no-user-plugins"))

# nor read or write the user's own material library (core/matlib.py)
os.environ.setdefault("MODELER_MATERIALS", os.path.join(tempfile.mkdtemp(prefix="modeler-test-mat-"), "materials.json"))

# a history edit from the window asks first when it would break later steps (gui/edit_guard.py);
# tests that break steps on purpose run without the question (tests/test_free_edit_gui.py turns it on)
os.environ.setdefault("MODELER_EDIT_QUESTION", "0")
