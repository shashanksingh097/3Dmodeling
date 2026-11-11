import os

# GUI tests must not write an autosave into the user's own app-data folder
os.environ.setdefault("MODELER_AUTOSAVE", "off")
