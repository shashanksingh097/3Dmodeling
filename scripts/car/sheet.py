"""Put several pictures on one contact sheet, two per row (used to check shots quickly).

usage: python scripts/car/sheet.py sheet.png a.png b.png c.png ...
"""

import sys

from PIL import Image


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    out, files = argv[0], argv[1:]
    w, h, cols = 800, 500, 2
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (w * cols, h * rows), "white")
    for i, f in enumerate(files):
        im = Image.open(f).convert("RGB")
        im.thumbnail((w, h))
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
