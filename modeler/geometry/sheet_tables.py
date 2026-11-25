"""Tables and balloons on a drawing sheet (PLAN item 72).

A sheet can carry, made again from the model each time it is written:

* a parts list (the rows of BOM), drawn just above the title block, with
  balloons on the drawing: a circle with the item number and a thin leader to
  the part;
* a hole table: a tag per hole (A1, A2 ...), its position, diameter, depth and
  thread, with the tag written beside the hole in every flat view that looks
  down its axis;
* a revision table (REVISION) in the top right corner.

The tables sit in a column on the right of the sheet; the views are fitted
into the room left of it. Everything here is in paper millimetres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

ROW_H = 6.0  # a table row
TEXT_H = 2.8
TITLE_ROW_H = 7.0
GAP = 4.0  # between tables, and between the tables and the views
BALLOON_R = 4.0


@dataclass
class Table:
    title: str
    header: list[str]
    rows: list[list[str]]
    where: str = "top"  # "top": from the top right corner down; "bottom": up from the title block
    right: set[int] = field(default_factory=set)  # columns written from the right (numbers)

    def widths(self) -> list[float]:
        cols = len(self.header)
        out = []
        for i in range(cols):
            texts = [self.header[i]] + [r[i] for r in self.rows if i < len(r)]
            out.append(max(_w(t) for t in texts) + 4.0)
        return out

    @property
    def width(self) -> float:
        return max(sum(self.widths()), _w(self.title) + 6.0)

    @property
    def height(self) -> float:
        return TITLE_ROW_H + ROW_H * (1 + len(self.rows))


def _w(text: str, h: float = TEXT_H) -> float:
    return 0.62 * h * len(text)


def side_width(tables: list[Table], title_w: float) -> float:
    """How much of the sheet's width the table column takes (0 with no tables)."""
    if not tables:
        return 0.0
    return max(t.width for t in tables) + GAP


def column_height(tables: list[Table]) -> float:
    return sum(t.height + GAP for t in tables)


def draw(pg, tables: list[Table], margin: float, title_h: float) -> list[str]:
    """Put the tables on the page. Returns warnings (tables that run off the sheet)."""
    if not tables:
        return []
    x1 = pg.width - margin
    width = max(t.width for t in tables)
    x0 = x1 - width
    top = pg.height - margin
    bottom = margin + title_h
    warn = []
    for t in [t for t in tables if t.where == "top"]:
        _table(pg, t, x0, top, width)
        top -= t.height + GAP
    for t in [t for t in tables if t.where == "bottom"]:
        _table(pg, t, x0, bottom + t.height, width)
        bottom += t.height + GAP
    if bottom > top + GAP:
        warn.append("the tables do not all fit on the sheet: use bigger paper")
    return warn


def _table(pg, t: Table, x0: float, top: float, width: float) -> None:
    ws = t.widths()
    extra = (width - sum(ws)) / max(len(ws), 1)
    ws = [w + extra for w in ws]
    y1 = top
    y0 = top - t.height
    x1 = x0 + width
    pg.thick.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
    pg.texts.append((x0 + 2, y1 - TITLE_ROW_H + 2.0, 3.2, t.title, "l", "k", 0.0))
    y = y1 - TITLE_ROW_H
    pg.thick.append([(x0, y), (x1, y)])
    for r, row in enumerate([t.header] + t.rows):
        if r:
            pg.thin.append([(x0, y), (x1, y)])
        x = x0
        for i, w in enumerate(ws):
            text = row[i] if i < len(row) else ""
            if i in t.right and r:
                pg.texts.append((x + w - 2, y - ROW_H + 1.9, TEXT_H, text, "r", "k", 0.0))
            else:
                pg.texts.append((x + 2, y - ROW_H + 1.9, TEXT_H, text, "l", "k", 0.0))
            x += w
        y -= ROW_H
    x = x0
    for w in ws[:-1]:
        x += w
        pg.thin.append([(x, y1 - TITLE_ROW_H), (x, y0)])


# ---- balloons and hole tags -------------------------------------------------------------------------

def balloons(pg, anchors: list[tuple[str, tuple[float, float]]], box: tuple[float, float, float, float],
             keep_out: list[tuple[float, float, float, float]]) -> int:
    """A balloon per (label, paper point on the part), set round the view's box with a leader each.
    Balloons are spread round the box so they do not overlap each other. Returns how many."""
    if not anchors:
        return 0
    bx0, by0, bx1, by1 = box
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    ax = (bx1 - bx0) / 2 + BALLOON_R + 6
    ay = (by1 - by0) / 2 + BALLOON_R + 6
    placed: list[tuple[float, float]] = []
    order = sorted(anchors, key=lambda a: math.atan2(a[1][1] - cy, a[1][0] - cx))
    step = math.radians(4)
    for label, (px, py) in order:
        th = math.atan2(py - cy, px - cx)
        best = None
        for k in range(90):
            for sgn in ((1,) if k == 0 else (1, -1)):
                a = th + sgn * k * step
                q = (cx + ax * math.cos(a), cy + ay * math.sin(a))
                if all(math.dist(q, o) >= 2 * BALLOON_R + 1 for o in placed) and not _inside(q, keep_out):
                    best = q
                    break
            if best is not None:
                break
        if best is None:
            best = (cx + ax * math.cos(th), cy + ay * math.sin(th))
        placed.append(best)
        qx, qy = best
        circle = [(qx + BALLOON_R * math.cos(i * math.pi / 16), qy + BALLOON_R * math.sin(i * math.pi / 16))
                  for i in range(33)]
        pg.thin.append(circle)
        d = math.dist(best, (px, py))
        if d > BALLOON_R:
            ex = qx + (px - qx) * BALLOON_R / d
            ey = qy + (py - qy) * BALLOON_R / d
            pg.thin.append([(ex, ey), (px, py)])
            pg.thin.append([(px + 0.7 * math.cos(i * math.pi / 4), py + 0.7 * math.sin(i * math.pi / 4))
                            for i in range(9)])
        pg.texts.append((qx, qy - TEXT_H * 1.1 / 3, TEXT_H * 1.1, label, "m", "k", 0.0))
    return len(placed)


def _inside(q, boxes) -> bool:
    x, y = q
    r = BALLOON_R
    return any(x0 - r < x < x1 + r and y0 - r < y < y1 + r for x0, y0, x1, y1 in boxes)


def tag(pg, at: tuple[float, float], r: float, label: str) -> None:
    """A hole's tag, written below and to the right of the hole's circle (sizes take the upper right)."""
    x, y = at
    d = r / math.sqrt(2) + 0.6
    pg.texts.append((x + d, y - d - TEXT_H, TEXT_H, label, "l", "b", 0.0))
