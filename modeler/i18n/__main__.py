"""``python -m modeler.i18n update``: add every text of the window to the language files.
``python -m modeler.i18n missing [lang]``: list the labels a language file has no translation for."""

from __future__ import annotations

import sys

from . import LANGUAGES, read, update
from .sources import labels_and_notes


def main(argv: list[str]) -> int:
    what = argv[0] if argv else "update"
    labels, notes = labels_and_notes()
    src = labels | notes
    if what == "update":
        added = update(src)
        for lang, n in added.items():
            have = read(lang)
            done = sum(1 for _t, ok in have.values() if ok)
            print(f"{lang}: {len(have)} texts, {done} translated, {n} new")
        return 0
    if what == "missing":
        langs = argv[1:] or [k for k in LANGUAGES if k != "en"]
        bad = 0
        for lang in langs:
            have = read(lang)
            for t in sorted(s for s in labels if not have.get(s, ("", False))[1]):
                print(f"{lang}\t{t}")
                bad += 1
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
