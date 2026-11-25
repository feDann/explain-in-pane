#!/usr/bin/env python3
"""textkit: draw with coloured characters (24-bit ANSI) for the explain pane.

mdview.py lays Markdown pages out with it. A custom drawing is a Python file with an optional
TITLE and a function render(cols, rows) that returns a Canvas. The viewer calls render again
whenever the pane changes size, so lay out from `cols`. One character is one cell: no emoji,
no CJK, no combining marks.

    from textkit import Canvas, GREEN, ORANGE

    TITLE = "Retry flow"

    def render(cols, rows):
        cv = Canvas(cols)
        cv.text(2, 1, "1. A retry keeps its own band", bold=True)
        cv.para(2, 3, "Records with the same outcome that follow each other join.", cols - 4, GREEN)
        return cv

Check a diagram before showing it (plain text, then layout warnings):

    python3 textkit.py check DIAGRAM.py [--cols 80,120] [--rows 40]

Exit 0 clean, 1 warnings, 2 render error. `--quiet` prints nothing and only tells whether
render() runs at 80 and 200 columns.
"""
import importlib.util
import os
import sys
import textwrap
import traceback

BG = "#1e1f24"
FG = "#e6e6e6"
MUTED = "#9aa0aa"
GREY = "#7a7f8a"
PANEL = "#2a2c35"
RED = "#ff5c5c"
GREEN = "#6fd08c"
ORANGE = "#f8961e"
CYAN = "#4cc9f0"
YELLOW = "#f9c74f"
LIME = "#90be6d"
PURPLE = "#c77dff"
BLUE_FILL = "#2b4f9e"
PURPLE_FILL = "#6a2f94"
CELL, HATCH_BG, HATCH_LN = "#262830", "#202127", "#3a3d48"
PALETTE = [CYAN, YELLOW, LIME, PURPLE, ORANGE, "#43aa8b", "#f28482", "#a0c4ff"]
EIGHTHS = " ▏▎▍▌▋▊▉█"
# Line characters by the sides they reach (l r u d), for joined_path().
DIRS = {"─": "lr", "│": "ud", "╭": "rd", "╮": "ld", "╰": "ur", "╯": "ul", "┼": "udlr",
        "├": "udr", "┤": "udl", "┬": "lrd", "┴": "lru"}
JOIN = {frozenset(v): k for k, v in DIRS.items()}
JOIN.update({frozenset("l"): "─", frozenset("r"): "─", frozenset("u"): "│", frozenset("d"): "│"})
HEADS = {"r": "▶", "l": "◀", "d": "▼", "u": "▲"}
OPP = {"l": "r", "r": "l", "u": "d", "d": "u"}


def _towards(p, q):
    """The side of point `p` that the point `q` lies on, for two points on a line."""
    return "r" if q[0] > p[0] else "l" if q[0] < p[0] else "d" if q[1] > p[1] else "u"


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hexc(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in c)


def blend(base, top, a):
    """`top` over `base` at opacity `a` (0..1)."""
    b, t = rgb(base), rgb(top)
    return hexc(tuple(b[i] * (1 - a) + t[i] * a for i in range(3)))


def ink(fill):
    """Dark or light text, whichever reads better on `fill`."""
    r, g, b = rgb(fill)
    return "#111111" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"


class Canvas:
    """A grid `w` cells wide that grows downwards as you draw. Cells: [char, fg, bg, bold].

    Every drawing call records a warning when it writes past the right edge or over a
    character another call drew: `check` prints them.
    """

    def __init__(self, w, h=0):
        self.w = w
        self.cells = []
        self.warnings = []
        self._hits = []
        self._lines = set()           # cells joined_path() drew, so later paths can join them
        self.degraded = 0             # how far drawings fell back to plainer text (a tree as a
                                      # list): panels stack rather than let it happen
        self._grow(h)

    @property
    def h(self):
        return len(self.cells)

    def _grow(self, h):
        while len(self.cells) < h:
            self.cells.append([[" ", FG, BG, False] for _ in range(self.w)])

    # -- low level ---------------------------------------------------------------
    def put(self, x, y, ch, fg=None, bg=None, bold=False):
        if y < 0 or x < 0 or x >= self.w:
            if ch != " ":
                self._hits.append(("clip", x, y, ch, ""))
            return
        self._grow(y + 1)
        c = self.cells[y][x]
        if ch != " " and c[0] != " " and c[0] != ch:
            self._hits.append(("over", x, y, ch, c[0]))
        c[0] = ch
        if fg is not None:
            c[1] = fg
        if bg is not None:
            c[2] = bg
        c[3] = bold

    def _report(self, what, x, y):
        if not self._hits:
            return
        clip = [h for h in self._hits if h[0] == "clip"]
        over = [h for h in self._hits if h[0] == "over"]
        if clip:
            self.warnings.append(f"{what} at x={x} y={y}: {len(clip)} cells past the right "
                                 f"edge (canvas is {self.w} wide)")
        if over:
            old = "".join(h[4] for h in over)[:30]
            self.warnings.append(f"{what} at x={x} y={y}: drew over {len(over)} cells "
                                 f"already drawn ({old!r})")
        self._hits = []

    # -- text ----------------------------------------------------------------------
    def text(self, x, y, s, fg=FG, bg=None, bold=False, anchor="start"):
        """One line. anchor: start | middle | end (x is where the text starts, centres, ends)."""
        s = str(s)
        if anchor == "end":
            x -= len(s)
        elif anchor == "middle":
            x -= len(s) // 2
        for i, ch in enumerate(s):
            self.put(x + i, y, ch, fg, bg, bold)
        self._report(f"text {s[:24]!r}", x, y)
        return y + 1

    def lines(self, x, y, rows, fg=FG, bold=False):
        """Several lines as given. Returns the y below the last."""
        for i, s in enumerate(rows):
            self.text(x, y + i, s, fg, bold=bold)
        return y + len(rows)

    def para(self, x, y, s, width, fg=FG, bold=False):
        """Text wrapped to `width` columns. Returns the y below the last line."""
        return self.lines(x, y, textwrap.wrap(str(s), max(10, width)) or [""], fg, bold)

    # -- blocks ----------------------------------------------------------------------
    def fill(self, x, y, w, h, bg):
        for yy in range(y, y + h):
            for xx in range(x, min(x + w, self.w)):
                self.put(xx, yy, " ", None, bg)

    def cell(self, x, y, w, label, bg=CELL, fg="#cfd2d8"):
        """A table-like row: `w` cells of `bg` with a label."""
        self.fill(x, y, w, 1, bg)
        for i, ch in enumerate(str(label)[:max(0, w - 2)]):
            self.put(x + 1 + i, y, ch, fg, bg)
        self._report(f"cell {label!r}", x, y)

    def hatch(self, x, y, w, h=1):
        """Diagonal hatching for "nothing here"."""
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.put(xx, yy, "╱" if (xx + yy) % 3 == 0 else " ", HATCH_LN, HATCH_BG)
        self._report("hatch", x, y)

    def box(self, x, y, w, h, label, sub=None, stroke=CYAN, bg=PANEL):
        """Rounded box, `h` >= 3 rows (4 with `sub`). Label centred, sub below it."""
        self.fill(x + 1, y + 1, w - 2, h - 2, bg)
        for xx in range(x + 1, x + w - 1):
            self.put(xx, y, "─", stroke, BG)
            self.put(xx, y + h - 1, "─", stroke, BG)
        for yy in range(y + 1, y + h - 1):
            self.put(x, yy, "│", stroke, BG)
            self.put(x + w - 1, yy, "│", stroke, BG)
        for (xx, yy), ch in {(x, y): "╭", (x + w - 1, y): "╮",
                             (x, y + h - 1): "╰", (x + w - 1, y + h - 1): "╯"}.items():
            self.put(xx, yy, ch, stroke, BG)
        self._report(f"box {label!r}", x, y)
        cx = x + w // 2
        if sub:
            self.text(cx, y + 1, label, FG, bg, True, "middle")
            self.text(cx, y + 2, sub, MUTED, bg, False, "middle")
        else:
            self.text(cx, y + (h - 1) // 2, label, FG, bg, True, "middle")

    # -- arrows ----------------------------------------------------------------------
    def harrow(self, x1, x2, y, label=None, color=MUTED, label_row=-1):
        """x1 -> x2 on row y (head at x2; x2 < x1 points left). Label on y + label_row."""
        step = 1 if x2 >= x1 else -1
        for xx in range(x1, x2, step):
            self.put(xx, y, "─", color)
        self.put(x2, y, "▶" if step == 1 else "◀", color)
        self._report("harrow", x1, y)
        if label:
            self.text((x1 + x2) // 2, y + label_row, label, MUTED, anchor="middle")

    def varrow(self, x, y1, y2, label=None, color=MUTED):
        """y1 -> y2 in column x (head at y2; y2 < y1 points up). Label right of the middle."""
        step = 1 if y2 >= y1 else -1
        for yy in range(y1, y2, step):
            self.put(x, yy, "│", color)
        self.put(x, y2, "▼" if step == 1 else "▲", color)
        self._report("varrow", x, y1)
        if label:
            self.text(x + 2, (y1 + y2) // 2, label, MUTED)

    def path(self, pts, color=MUTED, head=True):
        """Right-angle path through cell points [(x, y), ...]; arrow head at the last point."""
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            if ya == yb:
                for xx in range(min(xa, xb), max(xa, xb) + 1):
                    self.put(xx, ya, "─", color)
            else:
                for yy in range(min(ya, yb), max(ya, yb) + 1):
                    self.put(xa, yy, "│", color)
        def side(of, to):  # which side of point `of` the segment towards `to` leaves from
            (xo, yo), (xt, yt) = of, to
            return "left" if xt < xo else "right" if xt > xo else "up" if yt < yo else "down"

        corners = {frozenset(("left", "down")): "╮", frozenset(("left", "up")): "╯",
                   frozenset(("right", "down")): "╭", frozenset(("right", "up")): "╰"}

        def mark(p, ch):
            x, y = p
            if 0 <= x < self.w and 0 <= y < self.h:
                self.cells[y][x][0] = ch

        for a, b, c in zip(pts, pts[1:], pts[2:]):
            ch = corners.get(frozenset((side(b, a), side(b, c))))
            if ch:
                mark(b, ch)
        if head and len(pts) >= 2:
            (xa, ya), (xb, yb) = pts[-2], pts[-1]
            mark(pts[-1], "▶" if xb > xa else "◀" if xb < xa else "▼" if yb > ya else "▲")
        self._hits = [h for h in self._hits if h[3] not in "─│" or h[4] not in "─│╭╮╰╯"]
        self._report("path", *pts[0])

    def joined_path(self, pts, color=MUTED, head=True):
        """Right-angle line through `pts`, joining lines that earlier calls drew (┼ ├ ┬ ┴ ...).

        Two paths that share a stretch or cross make one connector: use it for trees and
        flows. With head=False the last point is left undrawn, so a box border can go there.
        Returns the cells the line passes.
        """
        seq = [pts[0]]
        for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
            while (xa, ya) != (xb, yb):
                xa += (xb > xa) - (xb < xa)
                ya += (yb > ya) - (yb < ya)
                seq.append((xa, ya))
        if len(seq) < 2:
            return seq
        for j, (px, py) in enumerate(seq[:-1]):
            d = {_towards(seq[j], seq[j + 1])}
            d.add(_towards(seq[j], seq[j - 1]) if j else OPP[_towards(seq[0], seq[1])])
            if (px, py) in self._lines and 0 <= py < self.h and 0 <= px < self.w:
                d |= set(DIRS.get(self.cells[py][px][0], ""))
                self.cells[py][px][0] = JOIN.get(frozenset(d), "┼")
                self.cells[py][px][1] = color
            else:
                self.put(px, py, JOIN.get(frozenset(d), "─"), color)
                self._lines.add((px, py))
        if head:
            self.put(*seq[-1], HEADS[_towards(seq[-2], seq[-1])], color)
        return seq

    # -- bars ------------------------------------------------------------------------
    def stacked(self, x0, y, parts, unit, cap=None, label=None, label_x=None, suffix=""):
        """One bar row. parts = [(value, color, name)]; unit = cells per value unit.

        Joins fall inside a cell as eighth blocks. Labels go inside the segments that fit
        them, clear of the cap column. The total goes after the bar (with `suffix`, such as
        " MiB"), red when over `cap`. Draw the cap with cap_line() after the rows.
        """
        if label:
            self.text(label_x if label_x is not None else x0 - 2, y, label, FG, anchor="end")
        edges, pos = [], 0.0
        for value, color, name in parts:
            edges.append((pos, pos + value * unit, color, name, value))
            pos += value * unit
        end = int(round(pos))
        for i in range(end):
            covering = [(a, b, c) for a, b, c, _, _ in edges if a < i + 1 and b > i]
            if not covering:
                continue
            if len(covering) == 1:
                self.put(x0 + i, y, " ", None, covering[0][2])
            else:
                a, b, left = covering[0]
                n = max(0, min(8, round((b - i) * 8)))
                self.put(x0 + i, y, EIGHTHS[n], left, covering[1][2])
        cx = x0 + int(round(cap * unit)) if cap is not None else None
        for a, b, color, name, value in edges:
            ia, ib = int(round(a)) + 1, int(round(b)) - 1
            for cand in (f"{name} {value:g}" if name else None, name, f"{value:g}"):
                if not cand or len(cand) > ib - ia:
                    continue
                tx = (ia + ib - len(cand)) // 2
                if cx is not None and x0 + tx <= cx <= x0 + tx + len(cand):
                    tx = cx - x0 - len(cand) - 1 if cx - x0 - len(cand) - 1 >= ia else cx - x0 + 2
                    if tx + len(cand) > ib or tx < ia:
                        continue
                self.text(x0 + tx, y, cand, ink(color), color, True)
                break
        total = sum(v for v, _, _ in parts)
        over = cap is not None and total > cap
        tail = f"{total:g}{suffix}" + (f"  (+{total - cap:g} over)" if over else "")
        tx = x0 + end + 2
        if cx is not None and tx - 1 <= cx <= tx + len(tail):
            tx = cx + 2
        self.text(tx, y, tail, RED if over else MUTED)

    def cap_line(self, x, y1, y2, label=None):
        """Red limit line in column x from row y1 to y2, label centred on the row above."""
        for yy in range(y1, y2 + 1):
            self._grow(yy + 1)
            bg = self.cells[yy][x][2] if 0 <= x < self.w else None
            self.put(x, yy, "┃", RED, bg)
        self._report("cap_line", x, y1)
        if label:
            self.text(x, y1 - 1, label, RED, anchor="middle")

    def legend(self, x, y, items, width):
        """items = [(color, label)], wrapped within `width`. Returns the y below."""
        xx = x
        for color, lab in items:
            if xx > x and xx + len(lab) + 3 > x + width:
                xx, y = x, y + 1
            self.text(xx, y, "██", color)
            self.text(xx + 3, y, lab, FG)
            xx += len(lab) + 7
        return y + 1

    # -- output ----------------------------------------------------------------------
    def ansi_rows(self):
        """One string per row, each exactly `w` cells, reset at the end."""
        rows = []
        for row in self.cells:
            out, last = [], None
            for ch, fg, bg, bold in row:
                key = (fg, bg, bold)
                if key != last:
                    f, b = rgb(fg), rgb(bg)
                    out.append(f"\x1b[{'1' if bold else '22'};38;2;{f[0]};{f[1]};{f[2]};"
                               f"48;2;{b[0]};{b[1]};{b[2]}m")
                    last = key
                out.append(ch)
            out.append("\x1b[0m")
            rows.append("".join(out))
        return rows

    def plain(self):
        return "\n".join("".join(c[0] for c in row).rstrip() for row in self.cells)


class Raster:
    """Pixels over a cell region for shapes text cannot draw (bands, wedges).

    Two pixels per cell, upper and lower half block, so a pixel is about square. Polygons are
    anti-aliased and blend, so see-through shapes pile up where they overlap. Coarse: use it
    for a shape that carries meaning, not for decoration.
    """

    SS = 4

    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.px = [[None] * w for _ in range(2 * h)]

    @staticmethod
    def _inside(pts, x, y):
        hit, n = False, len(pts)
        for i in range(n):
            (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                hit = not hit
        return hit

    def poly(self, pts, color, opacity=1.0):
        """pts in pixel units: x 0..w (one per column), y 0..2h (two per row)."""
        s = self.SS
        for py in range(2 * self.h):
            for px in range(self.w):
                k = sum(self._inside(pts, px + (i + .5) / s, py + (j + .5) / s)
                        for i in range(s) for j in range(s))
                if k:
                    self.px[py][px] = blend(self.px[py][px] or BG, color, opacity * k / (s * s))

    def paint(self, cv):
        for cy in range(self.h):
            for cx in range(self.w):
                top, bot = self.px[2 * cy][cx], self.px[2 * cy + 1][cx]
                if top is not None or bot is not None:
                    cv.put(self.x + cx, self.y + cy, "▀", top or BG, bot or BG)
        cv._report("raster", self.x, self.y)


# -- loading and checking diagrams -------------------------------------------------------
def load(path):
    """Import a diagram file fresh (textkit importable from it)."""
    sys.dont_write_bytecode = True                  # no __pycache__ next to diagrams
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    name = "diagram_%d" % abs(hash((os.path.abspath(path), os.path.getmtime(path))))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "render", None)):
        raise TypeError(f"{path} defines no render(cols, rows)")
    return mod


def title_of(mod, path):
    return getattr(mod, "TITLE", None) or os.path.splitext(os.path.basename(path))[0]


def _check(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="textkit.py check")
    ap.add_argument("file")
    ap.add_argument("--cols", default="120")
    ap.add_argument("--rows", type=int, default=40)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    widths = [80, 200] if a.quiet else [int(c) for c in a.cols.split(",")]
    try:
        mod = load(a.file)
        canvases = [(w, mod.render(w, a.rows)) for w in widths]
    except Exception:
        traceback.print_exc()
        return 2
    if a.quiet:
        return 0
    warned = False
    for w, cv in canvases:
        print(f"== {title_of(mod, a.file)} · {w} cols · {cv.h} rows")
        print(cv.plain())
        print("-- warnings: " + ("none" if not cv.warnings else str(len(cv.warnings))))
        for msg in cv.warnings[:20]:
            print("   " + msg)
        warned |= bool(cv.warnings)
    return 1 if warned else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        sys.exit(_check(sys.argv[2:]))
    print(__doc__.strip())
    sys.exit(2)
