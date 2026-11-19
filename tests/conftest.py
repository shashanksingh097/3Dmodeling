import os

# GUI tests must not write an autosave into the user's own app-data folder
os.environ.setdefault("MODELER_AUTOSAVE", "off")

# nor read the user's own assistant skills (ai/skills.py): only the built-in ones count
import tempfile  # noqa: E402

os.environ.setdefault("MODELER_SKILLS_HOME", os.path.join(tempfile.gettempdir(), "modeler-test-no-user-skills"))
os.environ.pop("MODELER_SKILLS", None)
