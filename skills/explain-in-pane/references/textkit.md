# The viewer, the herdr side and custom drawings

## Contents

- The scripts
- The viewer
- The gallery and the pane
- Custom drawings in Python
- herdr gotchas

## The scripts

| Script | Does |
|---|---|
| `show.py` | Reads Markdown pages (stdin or `.md` files) or `.py` drawings, lays each out at 80, 120 and 200 columns, then hands them to the viewer. `--plain [--cols N,M]` prints them as text instead. |
| `mdview.py` | The Markdown layout engine. `mdview.py FILE.md --cols 80,120` prints the pages as plain text with their warnings. |
| `viewer.py` | Runs in the explain pane until it is closed and draws the focused page at the pane's size. |
| `textkit.py` | The drawing layer under both: `Canvas`, boxes, arrows, bars, `Raster`. |
| `session-start.sh` | A session-start hook. Inside herdr it tells the agent that the pane is available. |
| `example.md` | Every Markdown block, on three pages. |
| `example_bands.py` | A custom Python drawing: before and after panels with bands. |

## The viewer

`viewer.py GALLERY` draws the focused page at the pane's size, again on every resize, and
again when a page file changes. One footer row: `◀ 3/5 ▶  title  ...  top|bot|all|NN%`.

Keys, once the pane has focus (nvim style; a count repeats a motion):

| Keys | Does |
|---|---|
| `h` / `l`, `gT` / `gt` | previous / next page |
| `[N]gt` | page N |
| `j` / `k`, `Ctrl-e` / `Ctrl-y` | one line down / up |
| `Ctrl-d` / `Ctrl-u` | half a page |
| `Ctrl-f` / `Ctrl-b` | a page |
| `gg` / `G`, `[N]G` | top / bottom, line N |
| `q` | quit; herdr closes the pane, and the next `show.py` opens a new one with only its pages |

Arrow keys, PgUp/PgDn and Home/End work too. Mouse: a click on `◀` or `▶` in the footer,
the wheel scrolls (where herdr passes the mouse through). A page that fails to draw shows
its error in the pane instead. The viewer loads `mdview` and `textkit` once: after editing
them, press `q` and show again.

## The gallery and the pane

`show.py` keys everything on the agent's pane it runs from (`$HERDR_PANE_ID`):

```
$TMPDIR/explain-in-pane/<pane id>/
  <title slug>.md   one Markdown page each      order   names, oldest first
  <name>.py         a custom drawing            focus   "<name> <token>" request
  pane              the explain pane's id       shown   "<token> ok|error ..." answer
  viewer.pid
```

A page is named after its `# Title`, so the same title replaces it in place. The explain pane
is found by the id in `pane`, and only if it is still in the agent pane's tab; otherwise
`show.py` splits the agent pane to the right (ratio 0.5, `--no-focus`), labels the new pane
`explain` and starts the viewer. Whenever it starts a viewer, it first empties the gallery,
so a reopened pane holds only the pages of the new call. Each agent session gets its own
gallery and pane.

Pane id for other commands:

```bash
pane=$(cat "${TMPDIR%/}/explain-in-pane/${HERDR_PANE_ID//[^A-Za-z0-9_-]/_}/pane")
herdr pane send-keys "$pane" l                 # next page, as if the user pressed l
herdr pane read "$pane" --source visible       # what the pane shows, colour removed
```

## Custom drawings in Python

Use one only for a shape Markdown cannot express. It costs far more to write: every position
comes from `cols`.

```python
from textkit import Canvas, FG, GREEN, ORANGE, RED   # no sys.path line: show.py and the viewer set it

TITLE = "Retry flow"            # footer name; the file name without .py when absent

def render(cols, rows):         # cols: pane width; rows: visible height above the footer
    cv = Canvas(cols)
    cv.text(2, 1, "1. A retry keeps its own band", FG, bold=True)
    return cv
```

Write it in a temporary directory, then `show.py FILE.py`. `python3 textkit.py check FILE.py --cols
100,200` prints it as plain text with overlap warnings. `scripts/example_bands.py` is a full
example.

| Call | Draws | Returns |
|---|---|---|
| `text(x, y, s, fg=FG, bg=None, bold=False, anchor="start")` | one line; anchor `start`, `middle`, `end` | y + 1 |
| `lines(x, y, rows, fg, bold)` | lines as given | y below |
| `para(x, y, s, width, fg, bold)` | text wrapped to `width` | y below |
| `fill(x, y, w, h, bg)` | a block of background | |
| `cell(x, y, w, label, bg=CELL, fg)` | a table-like row of `w` cells | |
| `hatch(x, y, w, h=1)` | diagonal hatching for "nothing here" | |
| `box(x, y, w, h, label, sub=None, stroke=CYAN, bg=PANEL)` | rounded box, `h` 3 (or 4 with `sub`) | |
| `harrow(x1, x2, y, label, color, label_row=-1)` | horizontal arrow, head at `x2` | |
| `varrow(x, y1, y2, label, color)` | vertical arrow, head at `y2` | |
| `path(pts, color, head=True)` | right-angle path through `[(x, y), ...]` | |
| `joined_path(pts, color, head=True)` | the same, but it joins lines drawn by earlier calls (`┼ ├ ┬ ┴`); `head=False` leaves the last point undrawn | the cells |
| `stacked(x0, y, parts, unit, cap, label, label_x, suffix)` | one bar row; `parts = [(value, color, name)]` | |
| `cap_line(x, y1, y2, label)` | red limit line across bar rows | |
| `legend(x, y, [(color, label)], width)` | colour keys, wrapped | y below |

`Raster(x, y, w, h)` paints shapes text cannot draw, two pixels per cell:
`r.poly([(0, 1.4), (14, 6), (14, 14)], BLUE_FILL, 0.55)` in pixel coordinates, then
`r.paint(cv)`. Polygons are anti-aliased and blend. Draw the raster before the text around it,
and keep shapes few and large.

Colours: `FG`, `MUTED`, `GREY`, `PANEL`, `RED`, `GREEN`, `ORANGE`, `CYAN`, `YELLOW`, `LIME`,
`PURPLE`, `BLUE_FILL`, `PURPLE_FILL`, `CELL`, `PALETTE`. `ink(fill)` picks readable text for a
fill; `blend(base, top, a)` mixes two.

## herdr gotchas

- `herdr pane run` types the command into the pane's shell. `show.py` runs the viewer with
  `exec`, so no shell prompt is left and the pane closes when the viewer exits.
- `herdr pane current --current` is the focused pane, which may not be the agent's. Use
  `$HERDR_PANE_ID`.
- A pane's pty is a little shorter than the height `herdr pane layout` reports (the frame).
  The viewer asks the pty, so this only matters when reading pane rows by number.
- `herdr pane get <id>` exits 1 with `pane_not_found` for a pane that is gone.
- Do not close panes you did not create.
