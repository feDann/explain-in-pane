"""Example diagram: before/after panels, bands between columns, a legend with a verdict column.

Placeholder content (batches of records committed as one). Copy the layout, not the words.
The bands use a Raster: coarse, so keep such shapes few and large.
Check:  python3 textkit.py check example_bands.py --cols 100,200
"""
from textkit import (BLUE_FILL, FG, GREEN, GREY, ORANGE, PURPLE_FILL, RED, Canvas, Raster)

TITLE = "Batch join"

COLW, GAP, P = 22, 14, 2          # column width, band gap, row pitch (row + spacer)
PW = 2 * COLW + GAP               # panel width
WEDGES = {
    "band": [(0, 1), (12, 0), (12, 4), (0, 3)],
    "open-left": [(0, 2), (12, 0), (12, 4)],
    "open-right": [(0, 0), (0, 4), (12, 2)],
    "sliver": [(0, 4), (12, 0.5), (12, 4)],
}


def panel(cv, x0, y0, mode):
    """Two columns of rows joined by bands. mode: not_joined | joined | edit. Returns y below."""
    xr = x0 + COLW + GAP
    top = lambda i: y0 + i * P                                  # noqa: E731
    r = Raster(x0 + COLW, y0, GAP, 6 * P + 1)

    def band(a, b, color, opacity):                             # rows a..b on the right
        r.poly([(0, 1.4), (GAP, 2 * a * P), (GAP, 2 * b * P + 2)], color, opacity)

    if mode == "not_joined":
        for i in range(3, 7):
            band(i, i, BLUE_FILL, 0.55)
    elif mode == "joined":
        band(3, 6, BLUE_FILL, 0.7)
    else:
        band(3, 4, BLUE_FILL, 0.7)
        band(6, 6, BLUE_FILL, 0.7)
        band(5, 5, PURPLE_FILL, 0.9)
    r.paint(cv)
    cv.cell(x0, top(0), COLW, "poll: 4 records", BLUE_FILL, "#8fb0ff")
    for i in (1, 2):
        cv.cell(x0, top(i), COLW, "idle")
        cv.cell(xr, top(i), COLW, "idle")
    for i in range(3, 7):
        cv.hatch(x0, top(i), COLW)
    cv.hatch(xr, top(0), COLW)
    for k, i in enumerate(range(3, 7)):
        if mode == "edit" and k == 2:
            cv.cell(xr, top(i), COLW, "retry-3", PURPLE_FILL, "#f0d4ff")
        else:
            cv.cell(xr, top(i), COLW, f"rec-{k + 1}", BLUE_FILL, "#dfe6f5")
    return y0 + 6 * P + 1


def render(cols, rows):
    cv = Canvas(cols)
    x0, y = 2, 1

    # 1. before / after: side by side when both fit, else one under the other
    cv.text(x0, y, "1. A batch is one commit for all its records", FG, bold=True)
    y += 2
    side = cols >= x0 + 2 * PW + 10
    xb = x0 + PW + 8
    not_cap = "Four see-through bands pile up where they meet the poll."
    yes_cap = "One band. This is what the join is for. Keep."
    cv.text(x0, y, "not joined", ORANGE)
    if side:
        cv.text(xb, y, "joined", GREEN)
    end = panel(cv, x0, y + 2, "not_joined")
    if side:
        panel(cv, xb, y + 2, "joined")
        a = cv.para(x0, end + 1, not_cap, 32, ORANGE)
        y = max(a, cv.para(xb, end + 1, yes_cap, 32, GREEN))
    else:
        y = cv.para(x0, end + 1, not_cap, min(PW, cols - 4), ORANGE) + 1
        cv.text(x0, y, "joined", GREEN)
        end = panel(cv, x0, y + 2, "joined")
        y = cv.para(x0, end + 1, yes_cap, min(PW, cols - 4), GREEN)

    # 2. one panel, captions beside it when they fit
    y += 2
    cv.text(x0, y, "2. A retry inside the batch keeps its own band", FG, bold=True)
    y += 2
    end = panel(cv, x0, y, "edit")
    notes = ["Records with the same outcome that follow each other join.",
             "A different outcome in between splits them: blue, purple, blue.", "Keep."]
    if cols >= x0 + PW + 6 + 30:
        cy = y + 1
        for note in notes:
            cy = cv.para(x0 + PW + 6, cy, note, min(36, cols - PW - 10), GREEN) + 1
        y = max(end, cy)
    else:
        y = end + 1
        for note in notes:
            y = cv.para(x0, y, note, cols - 4, GREEN) + 1

    # 3. legend of connector kinds with a verdict column
    y += 2
    cv.text(x0, y, "3. The kinds of connector the join handles today", FG, bold=True)
    y += 2
    for kind, fill, desc, verdict, color in [
        ("band", BLUE_FILL, "many records to one commit: a batch, a retry", "joined. Keep.", GREEN),
        ("open-left", "#3a9a5b", "new partition: starts at a point on the left", "cut", RED),
        ("open-right", "#b04444", "revoked partition: ends at a point on the right", "cut", RED),
        ("sliver", "#6b7280", "an empty poll: nothing on either side", "cut", RED),
    ]:
        r = Raster(x0, y, 12, 2)
        r.poly(WEDGES[kind], fill)
        r.paint(cv)
        if cols >= x0 + 15 + 50 + 14:
            cv.text(x0 + 15, y, desc, FG)
            cv.text(x0 + 65, y, verdict, color)
            y += 3
        else:                                   # verdict under the description
            below = cv.para(x0 + 15, y, desc, cols - x0 - 17, FG)
            y = max(y + 3, cv.text(x0 + 15, below, verdict, color) + 1)
    cv.para(x0, y, "The last three still draw after the cut. The join just stops looking for "
            "neighbours to merge them with. In a real batch there are none: only a retry has "
            "many pieces that end at the same place.", min(70, cols - 4), GREY)
    return cv
