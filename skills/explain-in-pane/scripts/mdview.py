#!/usr/bin/env python3
"""mdview: lay out an explanation written in Markdown on a textkit Canvas, for the pane's width.

The format is in SKILL.md. A document holds pages, each starting with `# Title`. Inside a page:
`##` sections, paragraphs, `-` and `1.` lists, `>` notes, `|` tables, `---` rules, fenced
```flow, ```seq, ```bars and ```tree blocks (any other fence is drawn as code), and
`::: panels` with `### title` panels side by side. Inline: {red: text}, **bold**, `code`.

    pages(text)          -> [(title, [(line_no, raw_line)], title_line_no)]   raises MdError
    render(page, cols)   -> Canvas; canvas.notes = [(line_no, warning)]        raises MdError
"""
import os
import re
import shlex
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textkit import (BG, CELL, CYAN, FG, GREEN, GREY, LIME, MUTED, ORANGE,  # noqa: E402
                     PANEL, PURPLE, RED, YELLOW, Canvas)

COLORS = {"red": RED, "green": GREEN, "orange": ORANGE, "yellow": YELLOW, "cyan": CYAN,
          "blue": "#a0c4ff", "purple": PURPLE, "lime": LIME, "teal": "#43aa8b",
          "pink": "#f28482", "grey": GREY, "gray": GREY, "muted": MUTED, "white": FG}
SERIES = [CYAN, YELLOW, LIME, PURPLE, ORANGE, "#43aa8b", "#f28482", "#a0c4ff"]
DIM = "#4a4e58"                    # lifelines, rules, the bar beside a note
TEXT_W = 110                       # wider panes do not stretch text, bars, panels or sequences
SLOT_W = 32
BAR_W = 100
PANEL_W = 70
NAMES = ", ".join(k for k in COLORS if k != "gray")


class MdError(Exception):
    """Text the format cannot draw. `line` counts from 1 in the document."""

    def __init__(self, line, msg):
        super().__init__(f"line {line}: {msg}")
        self.line, self.msg = line, msg


# -- inline text: styled characters (ch, fg, bg or None, bold) ------------------------------
_OPEN = re.compile(r"\{([A-Za-z]+):[ ]?")
_SPAN = re.compile(r"\{([A-Za-z]+):")
SPACE = (" ", FG, None, False)


def inline(s, fg=FG, bold=False, warn=None):
    """Characters of `s` styled by **bold**, `code` and {colour: text}; \\ escapes."""
    out, stack, code, i = [], [], False, 0
    while i < len(s):
        c = s[i]
        if code:
            if c == "`":
                code = False
            else:
                out.append((c, FG, CELL, False))
            i += 1
            continue
        cur = stack[-1] if stack else fg
        if c == "\\" and i + 1 < len(s) and s[i + 1] in "\\`*{}|":
            out.append((s[i + 1], cur, None, bold))
            i += 2
            continue
        if s.startswith("**", i):
            bold = not bold
            i += 2
            continue
        if c == "`":
            code = True
            i += 1
            continue
        if c == "{":
            m = _OPEN.match(s, i)
            if m and m.group(1).lower() in COLORS:
                stack.append(COLORS[m.group(1).lower()])
                i = m.end()
                continue
            if m and warn and "}" in s[m.end():]:
                warn(f"{{{m.group(1)}: ...}} is drawn as text: {m.group(1)!r} is not a "
                     f"colour ({NAMES})")
        if c == "}" and stack:
            stack.pop()
            i += 1
            continue
        out.append((c, cur, None, bold))
        i += 1
    return out


def span_color(s):
    """The first {colour: ...} colour in `s`, or None."""
    for m in _SPAN.finditer(s or ""):
        if m.group(1).lower() in COLORS:
            return COLORS[m.group(1).lower()]
    return None


def plain(chars):
    return "".join(c[0] for c in chars)


def wrap(chars, width):
    """Greedy word wrap of styled characters; words longer than `width` are split."""
    width = max(1, width)
    items, cur, sep = [], [], None
    for c in chars:
        if c[0] == " ":
            if cur:
                items.append((sep, cur))
                cur = []
            sep = c
        else:
            cur.append(c)
    if cur:
        items.append((sep, cur))
    lines, line = [], []
    for sep, word in items:
        if line and len(line) + 1 + len(word) <= width:
            line += [sep or SPACE] + word
            continue
        if line:
            lines.append(line)
            line = []
        while len(word) > width:
            lines.append(word[:width])
            word = word[width:]
        line = list(word)
    if line or not lines:
        lines.append(line)
    return lines


def cut(chars, width):
    return chars if len(chars) <= width else chars[:max(0, width - 1)] + [("…",) + chars[0][1:]]


def put_line(cv, x, y, chars):
    for i, (ch, fg, bg, bold) in enumerate(chars):
        cv.put(x + i, y, ch, fg, bg, bold)


def text_lines(cv, x, y, lines):
    for ln in lines:
        put_line(cv, x, y, ln)
        y += 1
    return y


# -- pages and blocks --------------------------------------------------------------------------
FENCE = re.compile(r"^(`{3,}|~{3,})\s*(.*)$")
HEAD = re.compile(r"^(#{2,6})\s+(.*)$")
ITEM = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
RULE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")


def _closes(s, mark):
    return s.startswith(mark) and not s.strip(mark[0])


def pages(text):
    """Split a document at its `# Title` lines (outside fences)."""
    out, cur, fence = [], None, None
    for n, raw in enumerate(text.expandtabs(4).splitlines(), 1):
        s = raw.strip()
        if fence:
            if _closes(s, fence):
                fence = None
        elif FENCE.match(s):
            fence = FENCE.match(s).group(1)
        elif raw.startswith("# "):
            if not raw[2:].strip():
                raise MdError(n, "a '#' line without a title")
            cur = (raw[2:].strip(), [], n)
            out.append(cur)
            continue
        if cur is None:
            if s:
                raise MdError(n, "text before the first '# Title' line: every page starts "
                                 "with one")
            continue
        cur[1].append((n, raw))
    if not out:
        raise MdError(1, "no '# Title' line: every page starts with one")
    return out


class Block:
    def __init__(self, kind, line, **kw):
        self.kind, self.line = kind, line
        self.__dict__.update(kw)


def _starts_block(raw):
    s = raw.strip()
    return (not s or s.startswith(("|", ">", ":::")) or bool(HEAD.match(s))
            or bool(FENCE.match(s)) or bool(ITEM.match(raw)) or bool(RULE.match(s)))


def parse(lines):
    blocks, i = [], 0
    while i < len(lines):
        n, raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        m = FENCE.match(s)
        if m:
            mark, info = m.group(1), m.group(2).strip()
            j = i + 1
            while j < len(lines) and not _closes(lines[j][1].strip(), mark):
                j += 1
            if j >= len(lines):
                raise MdError(n, f"the {mark} block has no closing {mark} line")
            kind, _, args = info.partition(" ")
            kind = kind.lower()
            body = lines[i + 1:j]
            if kind in ("flow", "seq", "bars", "tree"):
                blocks.append(Block(kind, n, body=body, args=args.strip()))
            else:
                blocks.append(Block("code", n, body=[r.rstrip() for _, r in body]))
            i = j + 1
            continue
        if s.startswith(":::"):
            j, fence = i + 1, None
            while j < len(lines):
                t = lines[j][1].strip()
                if fence:
                    if _closes(t, fence):
                        fence = None
                elif FENCE.match(t):
                    fence = FENCE.match(t).group(1)
                elif t == ":::":
                    break
                j += 1
            if j >= len(lines):
                raise MdError(n, "the ::: block has no closing ::: line")
            blocks.append(_panels(n, lines[i + 1:j]))
            i = j + 1
            continue
        m = HEAD.match(s)
        if m:
            blocks.append(Block("h2" if len(m.group(1)) == 2 else "h3", n, text=m.group(2)))
            i += 1
            continue
        if RULE.match(s):
            blocks.append(Block("hr", n))
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i][1].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            blocks.append(Block("table", n, rows=rows))
            continue
        if s.startswith(">"):
            parts = []
            while i < len(lines) and lines[i][1].strip().startswith(">"):
                parts.append(lines[i][1].strip()[1:].strip())
                i += 1
            blocks.append(Block("note", n, text=" ".join(p for p in parts if p)))
            continue
        m = ITEM.match(raw)
        if m:
            text, i = [m.group(3)], i + 1
            while i < len(lines) and not _starts_block(lines[i][1]):
                text.append(lines[i][1].strip())
                i += 1
            blocks.append(Block("li", n, level=min(3, len(m.group(1)) // 2), bullet=m.group(2),
                                text=" ".join(text)))
            continue
        parts = []
        while i < len(lines) and lines[i][1].strip() and not (parts and _starts_block(lines[i][1])):
            parts.append(lines[i][1].strip())
            i += 1
        blocks.append(Block("p", n, text=" ".join(parts)))
    return blocks


def _panels(n, lines):
    panels, cur, fence = [], None, None
    for ln, raw in lines:
        t = raw.strip()
        if fence:
            if _closes(t, fence):
                fence = None
        elif FENCE.match(t):
            fence = FENCE.match(t).group(1)
        elif t.startswith("### "):
            cur = (t[4:].strip(), ln, [])
            panels.append(cur)
            continue
        if cur is None:
            if t:
                raise MdError(ln, "inside ::: every panel starts with a '### title' line")
            continue
        cur[2].append((ln, raw))
    if not panels:
        raise MdError(n, "a ::: block holds panels, each starting with '### title'")
    return Block("panels", n, panels=[(t, ln, parse(body)) for t, ln, body in panels])


# -- drawing blocks --------------------------------------------------------------------------
def render(page, cols):
    """Draw one page `cols` wide. Layout problems go to canvas.notes as (line, message)."""
    title, lines, _ = page
    blocks = parse(lines)
    cv = Canvas(cols)
    notes = []
    y = draw_blocks(cv, blocks, 2, 1, cols - 4, notes)
    cv._grow(y + 1)
    cv.notes = sorted(set(notes))
    return cv


def _gap(prev, b):
    if prev is None:
        return 0
    if b.kind == "h2":
        return 2
    if prev.kind == "li" and b.kind == "li":
        return 0
    return 1


WHAT = {"h2": "heading", "h3": "heading", "p": "paragraph", "li": "list item", "note": "note",
        "hr": "rule", "code": "code block", "table": "table", "bars": "bars", "flow": "flow",
        "seq": "sequence", "tree": "tree", "panels": "panels"}


def draw_blocks(cv, blocks, x, y, width, notes):
    prev = None
    for b in blocks:
        y += _gap(prev, b)
        before = len(cv.warnings)
        y = DRAW[b.kind](cv, b, x, y, width, notes)
        cv._report(b.kind, x, y)
        if len(cv.warnings) > before:
            first = cv.warnings[before]
            del cv.warnings[before:]
            notes.append((b.line, f"the {WHAT[b.kind]} draws over itself or past the edge "
                                  f"at {cv.w} columns ({first})"))
        prev = b
    return y


def _warner(notes, line):
    return lambda msg, ln=line: notes.append((ln, msg))


def d_h2(cv, b, x, y, width, notes):
    return text_lines(cv, x, y, wrap(inline(b.text, FG, True, _warner(notes, b.line)),
                                     min(width, TEXT_W)))


def d_h3(cv, b, x, y, width, notes):
    return text_lines(cv, x, y, wrap(inline(b.text, MUTED, True, _warner(notes, b.line)),
                                     min(width, TEXT_W)))


def d_p(cv, b, x, y, width, notes):
    return text_lines(cv, x, y, wrap(inline(b.text, FG, False, _warner(notes, b.line)),
                                     min(width, TEXT_W)))


def d_note(cv, b, x, y, width, notes):
    lines = wrap(inline(b.text, GREY, False, _warner(notes, b.line)), min(width, TEXT_W) - 2)
    for i in range(len(lines)):
        cv.put(x, y + i, "▎", DIM)
    return text_lines(cv, x + 2, y, lines)


def d_li(cv, b, x, y, width, notes):
    ind = x + 2 * b.level
    mark = b.bullet if b.bullet[0].isdigit() else ("•" if b.level == 0 else "◦")
    cv.text(ind, y, mark, MUTED)
    tx = ind + len(mark) + 1
    return text_lines(cv, tx, y, wrap(inline(b.text, FG, False, _warner(notes, b.line)),
                                      x + min(width, TEXT_W) - tx))


def d_hr(cv, b, x, y, width, notes):
    for i in range(width):
        cv.put(x + i, y, "─", DIM)
    return y + 1


def d_code(cv, b, x, y, width, notes):
    body = b.body or [""]
    w = min(width, max(len(s) for s in body) + 2)
    cv.fill(x, y, w, len(body), CELL)
    for i, s in enumerate(body):
        if len(s) > w - 2:
            s = s[:w - 3] + "…"
            notes.append((b.line, f"code lines longer than {w - 2} columns are cut at "
                                  f"{cv.w} columns"))
        cv.text(x + 1, y + i, s, FG, CELL)
    return y + len(body)


# -- tables ----------------------------------------------------------------------------------
_SEP = re.compile(r"^:?-+:?$")
_NUM = re.compile(r"[-+~<>]?\d[\d.,_]*\s*[%a-zA-Z/]{0,6}")


def _cells(s):
    s = s.strip()
    s = s[1:] if s.startswith("|") else s
    s = s[:-1] if s.endswith("|") and not s.endswith("\\|") else s
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def d_table(cv, b, x, y, width, notes):
    warn = _warner(notes, b.line)
    rows = [_cells(r) for _, r in b.rows]
    head = None
    if len(rows) >= 2 and all(_SEP.match(c) for c in rows[1] if c):
        head, rows = rows[0], rows[2:]
    ncol = max(len(r) for r in rows + ([head] if head else []))
    pad = lambda r: r + [""] * (ncol - len(r))  # noqa: E731
    hs = [inline(c, MUTED, True, warn) for c in pad(head)] if head else None
    cs = [[inline(c, FG, False, warn) for c in pad(r)] for r in rows]
    nat = [max([len(hs[j]) if hs else 0] + [len(r[j]) for r in cs]) for j in range(ncol)]
    right = [bool(cs) and all(_NUM.fullmatch(plain(r[j]).strip()) or not plain(r[j]).strip()
                              for r in cs) and any(plain(r[j]).strip() for r in cs)
             for j in range(ncol)]
    G = 3
    widths = list(nat)
    while sum(widths) + G * (ncol - 1) > width:
        j = max(range(ncol), key=lambda k: widths[k])
        if widths[j] <= 12:
            break
        widths[j] -= 1
    if sum(widths) + G * (ncol - 1) > width:
        cv.degraded += 1
        return _table_stacked(cv, x, y, width, hs, cs)
    xs = [x]
    for w in widths[:-1]:
        xs.append(xs[-1] + w + G)

    def row(cells, y):
        wrapped = [wrap(c, widths[j]) for j, c in enumerate(cells)]
        for j, lines in enumerate(wrapped):
            for i, ln in enumerate(lines):
                off = widths[j] - len(ln) if right[j] else 0
                put_line(cv, xs[j] + off, y + i, ln)
        return y + max(len(w) for w in wrapped), max(len(w) for w in wrapped) > 1

    if hs:
        y, _ = row(hs, y)
        for i in range(sum(widths) + G * (ncol - 1)):
            cv.put(x + i, y, "─", DIM)
        y += 1
    tall = any(len(c) > widths[j] for r in cs for j, c in enumerate(r))
    for k, r in enumerate(cs):
        if k and tall:
            y += 1
        y, _ = row(r, y)
    return y


def _table_stacked(cv, x, y, width, hs, cs):
    for k, r in enumerate(cs):
        if k:
            y += 1
        y = text_lines(cv, x, y, wrap([(c[0], c[1], c[2], True) for c in r[0]], width))
        for j in range(1, len(r)):
            if not r[j]:
                continue
            lab = [(ch, MUTED, None, False) for ch in plain(hs[j]) + ": "] if hs and hs[j] else []
            y = text_lines(cv, x + 2, y, wrap(lab + r[j], width - 2))
    return y


# -- bars ------------------------------------------------------------------------------------
_VALUE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def d_bars(cv, b, x, y, width, notes):
    warn = _warner(notes, b.line)
    try:
        opts = dict(kv.split("=", 1) for kv in shlex.split(b.args))
    except ValueError:
        raise MdError(b.line, "bars options look like: ```bars cap=1024 unit=MiB")
    for k in set(opts) - {"cap", "unit", "max", "caplabel"}:
        warn(f"bars option {k!r} is ignored (options: cap, unit, max, caplabel)")
    try:
        cap = float(opts["cap"]) if "cap" in opts else None
        maxv = float(opts.get("max", 0))
    except ValueError:
        raise MdError(b.line, "cap= and max= take a number")
    unit = opts.get("unit", "")
    suffix = f" {unit}" if unit else ""
    rows, names = [], {}
    for ln, raw in b.body:
        s = raw.strip()
        if not s:
            continue
        label, sep, rest = s.partition(": ")
        if not sep:
            raise MdError(ln, "a bar row looks like 'label: 420' or 'label: heap 420, batch 260'")
        parts = []
        for seg in rest.split(","):
            toks = seg.split()
            color = None
            if toks and toks[-1].lower() in COLORS:
                color = COLORS[toks.pop().lower()]
            if not toks or not _VALUE.fullmatch(toks[-1]):
                raise MdError(ln, f"{seg.strip()!r} does not end in a number: a segment is "
                                  f"'name 420' or '420', with an optional colour after it")
            value = float(toks.pop())
            name = " ".join(toks)
            if name:
                color = names.setdefault(name, color or SERIES[len(names) % len(SERIES)])
            parts.append((value, color or CYAN, name))
        rows.append((label, parts))
    if not rows:
        raise MdError(b.line, "the bars block has no rows")
    totals = [sum(v for v, _, _ in p) for _, p in rows]
    top = maxv or max(totals + ([cap] if cap else []))
    lw = min(max(len(lab) for lab, _ in rows), width // 3)
    bx = x + lw + 2

    def tail(t):
        return f"{t:g}{suffix}" + (f"  (+{t - cap:g} over)" if cap is not None and t > cap else "")

    area = min(BAR_W, max(10, width - lw - 2 - max(len(tail(t)) for t in totals) - 2))
    per = area / top if top > 0 else 0
    step = 2 if len(rows) <= 8 else 1
    if cap is not None:
        y += 1                                       # the cap's label goes on this row
    first = y
    for label, parts in rows:
        if len(label) > lw:
            label = label[:lw - 1] + "…"
        cv.stacked(bx, y, parts, per, cap=cap, label=label, label_x=bx - 2, suffix=suffix)
        y += step
    last = y - step
    if cap is not None:
        cx = bx + round(cap * per)
        cv.cap_line(cx, first, last)
        lab = opts.get("caplabel") or f"limit {cap:g}{suffix}"
        lx = max(x, min(cx - len(lab) // 2, x + width - len(lab)))
        cv.text(lx, first - 1, lab, RED)
    y = last + 1
    if len(names) >= 2:
        y = cv.legend(x, y + 1, [(c, n) for n, c in names.items()], width)
    return y


# -- flows -----------------------------------------------------------------------------------
ARROW = re.compile(r"\s*(?:--\s+(?P<l1>[^>]+?)\s+--?>|-{1,2}>\s*(?:\|(?P<l2>[^|]*)\|)?)\s*")
_NODE_COLOR = re.compile(r"^\{([A-Za-z]+):\s*(.*?)\}(.*)$")
_SUB = re.compile(r"^(.*?)\s*\((.*)\)$")


class Node:
    def __init__(self, label, sub, color, line):
        self.label, self.sub, self.color, self.line = label, sub, color, line
        self.r = self.c = None


class Edge:
    def __init__(self, a, b, label, line):
        self.a, self.b, self.label, self.line = a, b, label, line
        self.kind, self.lane = None, 0


def _node(tok, ln):
    tok, color = tok.strip(), None
    m = _NODE_COLOR.match(tok)
    if m and m.group(1).lower() in COLORS:
        color, tok = COLORS[m.group(1).lower()], (m.group(2) + m.group(3)).strip()
    m = _SUB.match(tok)
    if m and m.group(1).strip():
        label, sub = m.group(1).strip(), m.group(2).strip()
    else:
        label, sub = tok, ""
    if not label:
        raise MdError(ln, "an arrow with no box on one side")
    return label, sub, color


def parse_flow(b):
    nodes, edges, chains = {}, [], []
    for ln, raw in b.body:
        s = raw.strip()
        if not s:
            continue
        toks, labels, pos = [], [], 0
        for m in ARROW.finditer(s):
            toks.append(s[pos:m.start()])
            labels.append((m.group("l1") or m.group("l2") or "").strip())
            pos = m.end()
        toks.append(s[pos:])
        chain = []
        for t in toks:
            label, sub, color = _node(t, ln)
            n = nodes.get(label.lower())
            if n is None:
                n = nodes[label.lower()] = Node(label, sub, color, ln)
            else:
                n.sub, n.color = n.sub or sub, n.color or color
            chain.append(n)
        edges += [Edge(a, z, lab, ln) for a, z, lab in zip(chain, chain[1:], labels)]
        chains.append(chain)
    if not nodes:
        raise MdError(b.line, "the flow block is empty")
    taken = {}

    def put(n, r, c):
        while (r, c) in taken:
            r += 1
        n.r, n.c = r, c
        taken[(r, c)] = n

    for chain in chains:
        known = {id(n) for n in nodes.values() if n.r is not None}
        prev = None
        for n in chain:
            if n.r is None:
                if prev is None:
                    put(n, max(r for r, _ in taken) + 1 if taken else 0, 0)
                elif id(prev) in known:              # continues from an earlier line: branch
                    put(n, prev.r + 1, prev.c)
                else:
                    put(n, prev.r, prev.c + 1)
            prev = n
    return list(nodes.values()), edges


def _label_on_line(cv, seq, text, color):
    """Write ` text ` over the straight middle of a drawn path. False when it does not fit."""
    own = cv._lines
    row = [p for p in seq[1:-1] if p in own and 0 <= p[1] < cv.h and cv.cells[p[1]][p[0]][0] == "─"]
    rows = {}
    for p in row:
        rows.setdefault(p[1], []).append(p[0])
    s = f" {plain(text)} "
    for yy, xs in sorted(rows.items(), key=lambda kv: -len(kv[1])):
        xs = sorted(xs)
        runs, start = [], xs[0]
        for a, b in zip(xs, xs[1:] + [None]):
            if b != a + 1:
                runs.append((start, a))
                start = b
        for a, b in sorted(runs, key=lambda r: r[0] - r[1]):
            if b - a + 1 >= len(s) + 2:
                x0 = a + (b - a + 1 - len(s)) // 2
                chars = [SPACE] + list(text) + [SPACE]
                for i, (ch, fg, bg, bold) in enumerate(chars):
                    cv.cells[yy][x0 + i] = [ch, color if fg == MUTED else fg, BG, bold]
                    own.discard((x0 + i, yy))
                return True
    return False


class FlowLayout:
    def __init__(self, nodes, edges, x0, y0, width, vertical, cap):
        self.nodes, self.edges = nodes, edges
        P = self.P = {id(n): ((n.c, n.r) if vertical else (n.r, n.c)) for n in nodes}
        nr = max(r for r, _ in P.values()) + 1
        nc = max(c for _, c in P.values()) + 1
        self.body = {}
        for n in nodes:
            self.body[id(n)] = (wrap(inline(n.label, FG, True), cap)
                                + (wrap(inline(n.sub, MUTED), cap) if n.sub else []))
        colw, rowh = [0] * nc, [0] * nr
        for n in nodes:
            r, c = P[id(n)]
            colw[c] = max(colw[c], max(len(ln) for ln in self.body[id(n)]) + 4)
            rowh[r] = max(rowh[r], len(self.body[id(n)]) + 2)
        hneed, rlanes, below = [4] * max(0, nc - 1), [0] * nc, [0] * nr
        self.hlab, self.vlab, self.cut = {}, {}, []
        for e in edges:
            (ra, ca), (rb, cb) = P[id(e.a)], P[id(e.b)]
            if ra == rb and cb == ca + 1:
                e.kind = "h"
            elif ca == cb and rb == ra + 1:
                e.kind = "v"
            elif ra == rb:
                e.kind = "row"
            elif ca == cb:
                e.kind = "col"
            else:
                e.kind = "down" if rb > ra else "up"
            if e.kind == "h":
                lab = inline(e.label, MUTED) if e.label else []
                lines = [lab] if lab and len(lab) <= 20 else (
                    wrap(lab, max(10, (len(lab) + 1) // 2 + 1)) if lab else [])
                if len(lines) > 2:
                    lines = [lines[0], cut(lines[1] + [SPACE] + [c for ln in lines[2:] for c in ln + [SPACE]],
                                           len(lines[0]))]
                    self.cut.append(e)
                self.hlab[id(e)] = lines
                hneed[ca] = max(hneed[ca], 6, max([len(ln) for ln in lines] or [0]) + 4)
            elif e.kind in ("row", "down"):
                e.lane, below[ra] = below[ra], below[ra] + 1
            elif e.kind == "up":
                e.lane, below[rb] = below[rb], below[rb] + 1
            elif e.kind == "col":
                e.lane, rlanes[ca] = rlanes[ca], rlanes[ca] + 1
        # a loop beside a column runs right of the labels of that column's down arrows,
        # and its own label right of it
        vl, cl = [0] * nc, [0] * nc
        for e in edges:
            c = P[id(e.a)][1]
            if e.kind == "v" and e.label:
                vl[c] = max(vl[c], min(24, len(inline(e.label))))
            elif e.kind == "col" and e.label:
                cl[c] = max(cl[c], len(inline(e.label)) + 3)
        self.lane_x = [0] * nc
        side = [0] * nc
        for c in range(nc):
            if rlanes[c]:
                off = max(1, colw[c] // 2 + 4 + vl[c] - colw[c])
                self.lane_x[c] = off
                side[c] = off + 2 * rlanes[c] + cl[c]
        colx = [x0]
        for c in range(nc - 1):
            colx.append(colx[-1] + colw[c] + hneed[c] + side[c])
        right = colx[-1] + colw[-1] + side[-1]
        self.width = right - x0
        self.lane_x = [colx[c] + colw[c] + self.lane_x[c] for c in range(nc)]
        users = {}                    # gap below row r -> x of vertical lines crossing it
        for e in edges:
            (ra, ca), (rb, cb) = P[id(e.a)], P[id(e.b)]
            if e.kind == "v":
                users.setdefault(ra, []).append(colx[ca] + colw[ca] // 2)
            elif e.kind in ("row", "down", "up"):
                users.setdefault(ra if e.kind != "up" else ra - 1, []).append(colx[ca])
                users.setdefault(rb if e.kind != "down" else rb - 1, []).append(colx[cb])
            elif e.kind == "col":
                for r in range(min(ra, rb), max(ra, rb)):
                    users.setdefault(r, []).append(self.lane_x[ca] + 2 * e.lane)
        vneed = [1] * nr
        for e in edges:
            if e.kind == "v":
                r, c = P[id(e.a)]
                cx = colx[c] + colw[c] // 2
                limit = min([u - 2 for u in users.get(r, []) if u > cx] + [x0 + width])
                lines = wrap(inline(e.label, MUTED), max(8, limit - cx - 2)) if e.label else []
                self.vlab[id(e)] = lines
                vneed[r] = max(vneed[r], 3, len(lines) + 2)
        rowy = [y0]
        for r in range(nr - 1):
            rowy.append(rowy[-1] + rowh[r] + vneed[r] + below[r] + (1 if below[r] else 0))
        self.bottom = rowy[-1] + rowh[-1] + (below[-1] + 1 if below[-1] else 0)
        self.colx, self.colw, self.rowy, self.rowh, self.vneed = colx, colw, rowy, rowh, vneed
        for n in nodes:
            r, c = P[id(n)]
            n.x, n.y, n.w, n.h = colx[c], rowy[r], colw[c], rowh[r]

    def lane_y(self, r, k):
        return self.rowy[r] + self.rowh[r] + self.vneed[r] + k

    def draw(self, cv, warn):
        for n in self.nodes:
            cv.box(n.x, n.y, n.w, n.h, "", stroke=n.color or CYAN)
            lines = self.body[id(n)]
            top = n.y + 1 + (n.h - 2 - len(lines)) // 2
            for i, ln in enumerate(lines):
                put_line(cv, n.x + (n.w - len(ln)) // 2, top + i, ln)
        used = {}

        def attach(n, side):             # beside the centre, where straight arrows run
            k = used.get((id(n), side), 0)
            used[(id(n), side)] = k + 1
            cx = n.x + n.w // 2
            spots = [p for p in range(n.x + 1, cx - 1, 2)] + [p for p in range(cx + 2, n.x + n.w - 1, 2)]
            spots = spots or [p for p in (n.x + 1, cx + 1) if p < n.x + n.w - 1]
            return spots[k] if k < len(spots) else cx

        routed = []
        for e in self.edges:
            a, b = e.a, e.b
            color = span_color(e.label) or MUTED
            if e.kind == "h":
                yy, x1, x2 = a.y + 1, a.x + a.w, b.x - 1
                cv.joined_path([(x1, yy), (x2, yy)], color)
                for ln, ly in zip(self.hlab[id(e)], (yy - 1, yy + 1)):
                    put_line(cv, x1 + (x2 - x1 + 1 - len(ln)) // 2, ly, ln)
            elif e.kind == "v":
                cx = a.x + a.w // 2
                cv.joined_path([(cx, a.y + a.h), (cx, b.y - 1)], color)
                text_lines(cv, cx + 2, a.y + a.h + 1, self.vlab[id(e)])
            elif e.kind == "col":
                (_, c), k = self.P[id(a)], e.lane
                lx = self.lane_x[c] + 2 * k
                ya, yb = a.y + a.h - 2, b.y + b.h - 2
                seq = cv.joined_path([(a.x + a.w, ya), (lx, ya), (lx, yb), (b.x + b.w, yb)], color)
                routed.append((e, seq, color, (lx + 2, (ya + yb) // 2)))
            else:
                ra, rb = self.P[id(a)][0], self.P[id(b)][0]
                xa, xb = attach(a, "top" if e.kind == "up" else "bottom"), attach(
                    b, "top" if e.kind == "down" else "bottom")
                ly = self.lane_y(rb if e.kind == "up" else ra, e.lane)
                start = (xa, a.y - 1) if e.kind == "up" else (xa, a.y + a.h)
                end = (xb, b.y - 1) if e.kind == "down" else (xb, b.y + b.h)
                seq = cv.joined_path([start, (xa, ly), (xb, ly), end], color)
                routed.append((e, seq, color, None))
        for e, seq, color, spot in routed:
            if not e.label:
                continue
            lab = inline(e.label, MUTED)
            if spot:
                put_line(cv, spot[0], spot[1], lab)
            elif not _label_on_line(cv, seq, lab, color):
                warn(f"the label {plain(lab)!r} does not fit on the line from "
                     f"{e.a.label!r} to {e.b.label!r}", e.line)
        for e in self.cut:
            warn(f"the label {e.label!r} is cut: keep arrow labels under 40 characters", e.line)


def d_flow(cv, b, x, y, width, notes):
    nodes, edges = parse_flow(b)
    for vertical, cap in ((False, 24), (False, 16), (False, 12),
                          (True, 28), (True, 18), (True, 12)):
        lay = FlowLayout(nodes, edges, x, y, width, vertical, cap)
        if lay.width <= width:
            break
    if lay.width > width:
        notes.append((b.line, f"the flow needs {lay.width} columns even top to bottom, the "
                              f"pane has {width}: fewer boxes per line or shorter labels"))
    lay.draw(cv, lambda msg, ln=b.line: notes.append((ln, msg)))
    return lay.bottom


# -- sequences -------------------------------------------------------------------------------
_PART = r"(?:\{[A-Za-z]+:[^}]*\}|[^:{]+?)"
_MSG = re.compile(rf"^(?P<a>{_PART})\s*(?P<arr>-->>|->>|-->|->)\s*(?P<b>{_PART})\s*"
                  rf"(?::\s*(?P<t>.*))?$")
_NOTE = re.compile(rf"^note(?:\s+(?:over\s+)?(?P<p>{_PART}))?\s*:\s*(?P<t>.*)$", re.I)


def d_seq(cv, b, x, y, width, notes):
    parts, steps = [], []

    def part(tok, ln):
        label, _, color = _node(tok, ln)
        for p in parts:
            if p["label"].lower() == label.lower():
                p["color"] = p["color"] or color
                return p
        parts.append({"label": label, "color": color})
        return parts[-1]

    for ln, raw in b.body:
        s = raw.strip()
        if not s:
            continue
        if s.startswith("---"):
            steps.append(("div", s.strip("- "), ln))
            continue
        m = _NOTE.match(s)
        if m:
            steps.append(("note", part(m.group("p"), ln) if m.group("p") else None,
                          m.group("t"), ln))
            continue
        m = _MSG.match(s)
        if not m:
            raise MdError(ln, "a seq line looks like 'a -> b: message', 'b --> a: reply', "
                              "'note a: text' or '--- text'")
        steps.append(("msg", part(m.group("a"), ln), part(m.group("b"), ln),
                      m.group("arr").startswith("--"), m.group("t") or "", ln))
    if not parts:
        raise MdError(b.line, "the seq block has no messages")
    n = len(parts)
    width = min(width, SLOT_W * n)
    slot = width / n
    if slot < 10:
        notes.append((b.line, f"{n} participants leave {slot:.0f} columns each at {width} "
                              f"columns: use fewer"))
    hh = 0
    for i, p in enumerate(parts):
        p["x"] = x + int(slot * i + slot / 2)
        p["lines"] = wrap(inline(p["label"], FG, True), max(4, int(slot) - 6))
        hh = max(hh, len(p["lines"]) + 2)
    for p in parts:
        w = max(len(ln) for ln in p["lines"]) + 4
        bx = p["x"] - w // 2
        cv.box(bx, y, w, hh, "", stroke=p["color"] or CYAN)
        top = y + 1 + (hh - 2 - len(p["lines"])) // 2
        for i, ln in enumerate(p["lines"]):
            put_line(cv, p["x"] - len(ln) // 2, top + i, ln)
        cv.cells[y + hh - 1][p["x"]][0] = "┬"
    y0 = y = y + hh
    y += 1
    text = set()                                   # cells of labels: no lifeline there

    def say(x0, yy, chars):
        put_line(cv, x0, yy, chars)
        text.update((x0 + i, yy) for i in range(len(chars)))

    for st in steps:
        if st[0] == "div":
            label = f" {st[1]} " if st[1] else ""
            lx = x + (width - len(label)) // 2
            for i in range(width):
                if not lx <= x + i < lx + len(label):
                    cv.put(x + i, y, "┄", DIM)
            cv.text(lx, y, label, GREY)
            text.update((x + i, y) for i in range(width))
            y += 1
        elif st[0] == "note":
            _, p, words, ln = st
            nx = p["x"] + 2 if p else x
            w = min(48, x + width - nx)
            lines = wrap(inline(words, FG, False, _warner(notes, ln)), w - 2)
            cv.fill(nx, y, max(len(ln) for ln in lines) + 2, len(lines), PANEL)
            y = text_lines(cv, nx + 1, y, lines)
        else:
            _, pa, pb, dashed, words, ln = st
            color = span_color(words) or MUTED
            lab = inline(words, MUTED, False, _warner(notes, ln)) if words else []
            if pa is pb:
                lines = wrap(lab, max(8, x + width - pa["x"] - 4)) if lab else []
                cv.put(pa["x"] + 1, y, "─", color)
                cv.put(pa["x"] + 2, y, "╮", color)
                cv.put(pa["x"] + 2, y + 1, "╯", color)
                cv.put(pa["x"] + 1, y + 1, "◀", color)
                for i, ln_ in enumerate(lines):
                    say(pa["x"] + 4, y + i, ln_)
                y += max(2, len(lines))
                continue
            lo, hi = sorted((pa["x"], pb["x"]))
            span = hi - lo - 1
            lines = wrap(lab, max(6, span - 2)) if lab else []
            for ln_ in lines:
                say(lo + 1 + (span - len(ln_)) // 2, y, ln_)
                y += 1
            ch = "╌" if dashed else "─"
            right = pb["x"] > pa["x"]
            for xx in range(lo + 1, hi):
                cv.put(xx, y, ("▶" if right else ch) if xx == hi - 1 else
                       ("◀" if not right else ch) if xx == lo + 1 else ch, color)
            y += 1
    for p in parts:                                # lifelines, only where nothing is drawn
        for yy in range(y0, y + 1):
            cv._grow(yy + 1)
            c = cv.cells[yy][p["x"]]
            if c[0] == " " and c[2] == BG and (p["x"], yy) not in text:
                cv.put(p["x"], yy, "│", DIM)
    return y + 1


# -- trees -----------------------------------------------------------------------------------
_KEY = re.compile(r"^([A-Za-z_][\w.-]*):\s+(\S.*)$")
TREE_LAYOUTS = ("auto", "top", "left", "side", "list")
TREE_BOX_ROWS = 40                 # auto keeps boxes only while they stay this short
TREE_GAP = 2                       # columns between sibling boxes
TREE_VGAP = 1                      # rows between the boxes of siblings in a column
TREE_CAPS = (24, 16, 12)           # box text widths the top layout tries, widest first
TREE_GUIDE = GREY                  # connectors


class TreeNode:
    def __init__(self, label, sub, color, key, line):
        self.label, self.sub, self.color, self.key, self.line = label, sub, color, key, line
        self.children = []
        self.dim = label.startswith(("…", "..."))


def parse_tree(b):
    """The root of the tree a tree block describes: one node per line, nested by indent."""
    rows = [(ln, len(raw) - len(raw.lstrip(" ")), raw.strip()) for ln, raw in b.body
            if raw.strip()]
    if not rows:
        raise MdError(b.line, "the tree block is empty")
    root, stack = None, []
    for ln, ind, s in rows:
        if s.startswith("\\"):                       # \word: text is a name, not an edge label
            key, s = None, s[1:].strip()
        else:
            m = _KEY.match(s)
            key, s = (m.group(1), m.group(2)) if m else (None, s)
        if not s:
            raise MdError(ln, "a tree line with no text after the backslash")
        label, sub, color = _node(s, ln)
        node = TreeNode(label, sub, color, key, ln)
        if root is None:
            root, stack = node, [(ind, node)]
            continue
        if ind <= rows[0][1]:
            raise MdError(ln, "a tree has one root: indent this line under its parent"
                              if ind == rows[0][1] else "this line is indented less than the root")
        popped = False
        while stack[-1][0] > ind:
            stack.pop()
            popped = True
        if stack[-1][0] == ind:                    # a sibling of the line above or of an ancestor
            stack.pop()
        elif popped:
            raise MdError(ln, "this indent matches no line above it: line it up with a sibling")
        stack[-1][1].children.append(node)
        stack.append((ind, node))
    return root


def _count(n):
    return sum(1 + _count(c) for c in n.children)


def _fold(n, depth, level=0):
    """Replace everything below `depth` levels with one `… N more` leaf."""
    if level >= depth and n.children:
        n.children = [TreeNode(f"… {_count(n)} more", "", None, None, n.line)]
        return
    for c in n.children:
        _fold(c, depth, level + 1)


def _tree_line(n):
    """One line of text for a node: `key: label (sub)`."""
    out = inline(n.key + ":", MUTED) + [SPACE] if n.key else []
    out += inline(n.label, n.color or (GREY if n.dim else FG), not n.dim)
    return out + [SPACE] + inline(f"({n.sub})", MUTED) if n.sub else out


class ListLayout:
    """One node per line under its parent, with ├── └── │ guides. Always fits: it only grows down."""

    kind = "list"

    def __init__(self, root, width):
        self.rows = []

        def go(n, trail, last, depth):       # trail: does each ancestor have later siblings?
            self.rows.append((n, trail, last, depth))
            below = trail + [not last] if depth else []
            for i, c in enumerate(n.children):
                go(c, below, i == len(n.children) - 1, depth + 1)

        go(root, [], True, 0)
        self.depth = max(r[3] for r in self.rows)
        for self.step in (4, 3, 2):
            if self.step * self.depth + 12 <= width:
                break
        self.need = 2 * self.depth + 12
        self.lines = [wrap(_tree_line(n), max(1, width - self.step * d))
                      for n, _, _, d in self.rows]
        self.height = sum(len(ln) for ln in self.lines)

    def draw(self, cv, x, y):
        step = self.step
        for (n, trail, last, d), lines in zip(self.rows, self.lines):
            guide = "".join(("│" if t else " ") + " " * (step - 1) for t in trail)
            for i, ln in enumerate(lines):
                if d:
                    own = ("└" if last else "├") + "─" * (step - 2) + " " if i == 0 else \
                          ("│" if not last else " ") + " " * (step - 1)
                    for k, ch in enumerate(guide + own):
                        if ch != " ":
                            cv.put(x + k, y, ch, TREE_GUIDE)
                put_line(cv, x + step * d, y, ln)
                y += 1


class SideLayout:
    """Root at the left, children to its right, one row per leaf: app ─┬─ api ─┬─ db."""

    kind = "side"

    def __init__(self, root):
        self.items, self.rows = [], 0
        self.width = self._place(root, 0)[1]
        self.height = self.rows

    def _place(self, n, col):
        text = _tree_line(n)
        end = col + len(text)
        if not n.children:
            row, self.rows = self.rows, self.rows + 1
            self.items.append((col, row, text, []))
            return row, end
        kids, far = [], end
        for c in n.children:
            row, e = self._place(c, end + 5)
            kids.append(row)
            far = max(far, e)
        self.items.append((col, kids[0], text, kids))      # a parent shares its first child's row
        return kids[0], far

    def draw(self, cv, x, y):
        for col, row, text, kids in self.items:
            put_line(cv, x + col, y + row, text)
            if not kids:
                continue
            gx = x + col + len(text) + 2
            cv.put(gx - 1, y + row, "─", TREE_GUIDE)
            cv.put(gx, y + row, "┬" if len(kids) > 1 else "─", TREE_GUIDE)
            cv.put(gx + 1, y + row, "─", TREE_GUIDE)
            for r in range(kids[0] + 1, kids[-1] + 1):
                if r in kids:
                    cv.put(gx, y + r, "└" if r == kids[-1] else "├", TREE_GUIDE)
                    cv.put(gx + 1, y + r, "─", TREE_GUIDE)
                else:
                    cv.put(gx, y + r, "│", TREE_GUIDE)


def _box_lines(n, cap):
    lines = wrap(inline(n.key + ":", MUTED), cap) if n.key else []
    lines += wrap(inline(n.label, GREY if n.dim else FG, not n.dim), cap)
    return lines + (wrap(inline(f"({n.sub})", MUTED), cap) if n.sub else [])


class TopLayout:
    """The root on top, each node's children in a row below it, a bus line between."""

    kind = "top"

    def __init__(self, root, cap):
        self.cap, self.nodes, self.levels = cap, [], []
        self._size(root)
        self._depths(root, 0)
        self._place(root, 0)
        self.width = root.sw
        self.ys = [0]
        for h in self.levels:
            self.ys.append(self.ys[-1] + h + 1)
        self.height = self.ys[-1] - 1

    def _size(self, n):
        n.lines = _box_lines(n, self.cap)
        n.w = max(len(ln) for ln in n.lines) + 4
        n.h = len(n.lines) + 2
        kids = [self._size(c) for c in n.children]
        n.inner = sum(kids) + TREE_GAP * (len(kids) - 1) if kids else 0
        n.sw = max(n.w, n.inner)                           # the columns its subtree needs
        return n.sw

    def _depths(self, n, d):
        n.d = d
        self.nodes.append(n)
        if len(self.levels) <= d:
            self.levels.append(0)
        self.levels[d] = max(self.levels[d], n.h)
        for c in n.children:
            self._depths(c, d + 1)

    def _place(self, n, x0):
        """Children side by side in the span [x0, x0 + sw), the parent centred over them."""
        if not n.children:
            n.x = x0 + (n.sw - n.w) // 2
            return
        cx = x0 + (n.sw - n.inner) // 2
        for c in n.children:
            self._place(c, cx)
            cx += c.sw + TREE_GAP
        a, z = n.children[0], n.children[-1]
        mid = (a.x + a.w // 2 + z.x + z.w // 2) // 2
        m = n.children[len(n.children) // 2]
        if len(n.children) % 2:                            # one straight line to the middle child
            mid = m.x + m.w // 2
        n.x = min(max(mid - n.w // 2, x0), x0 + n.sw - n.w)

    def draw(self, cv, x, y):
        for n in self.nodes:
            bx, by = x + n.x, y + self.ys[n.d]
            cv.box(bx, by, n.w, n.h, "", stroke=n.color or (DIM if n.dim else CYAN))
            for i, ln in enumerate(n.lines):
                put_line(cv, bx + (n.w - len(ln)) // 2, by + 1 + i, ln)
        for n in self.nodes:
            if not n.children:
                continue
            px, top = x + n.x + n.w // 2, y + self.ys[n.d]
            bottom, bus = top + n.h - 1, top + self.levels[n.d]
            edge = cv.cells[bottom][px]                # the border cell the connector leaves from
            stroke = edge[1]
            edge[0] = " "
            for c in n.children:
                cx = x + c.x + c.w // 2
                cv.joined_path([(px, bottom), (px, bus), (cx, bus), (cx, bus + 1)],
                               TREE_GUIDE, head=False)
                cv.cells[bus + 1][cx][0] = "┴"
            edge[0], edge[1] = "┬", stroke


class LeftLayout:
    """The top layout turned: the root at the left, each node's children in a column to its right."""

    kind = "left"

    def __init__(self, root, cap):
        self.nodes, self.cols = [], []
        self._size(root, cap)
        self._depths(root, 0)
        self._place(root, 0)
        self.colx = [0]
        for w in self.cols:
            self.colx.append(self.colx[-1] + w + 3)       # a stub, the bus and a run between
        self.width = self.colx[-1] - 3
        self.height = root.sh

    def _size(self, n, cap):
        n.lines = _box_lines(n, cap)
        n.w = max(len(ln) for ln in n.lines) + 4
        n.h = len(n.lines) + 2
        kids = [self._size(c, cap) for c in n.children]
        n.inner = sum(kids) + TREE_VGAP * (len(kids) - 1) if kids else 0
        n.sh = max(n.h, n.inner)                           # the rows its subtree needs
        return n.sh

    def _depths(self, n, d):
        n.d = d
        self.nodes.append(n)
        if len(self.cols) <= d:
            self.cols.append(0)
        self.cols[d] = max(self.cols[d], n.w)
        for c in n.children:
            self._depths(c, d + 1)

    def _place(self, n, y0):
        """Children stacked in the rows [y0, y0 + sh), the parent centred beside them."""
        if not n.children:
            n.y = y0 + (n.sh - n.h) // 2
            return
        cy = y0 + (n.sh - n.inner) // 2
        for c in n.children:
            self._place(c, cy)
            cy += c.sh + TREE_VGAP
        a, z = n.children[0], n.children[-1]
        mid = (a.y + a.h // 2 + z.y + z.h // 2) // 2
        m = n.children[len(n.children) // 2]
        if len(n.children) % 2:                            # one straight line to the middle child
            mid = m.y + m.h // 2
        n.y = min(max(mid - n.h // 2, y0), y0 + n.sh - n.h)

    def draw(self, cv, x, y):
        for n in self.nodes:
            bx, by = x + self.colx[n.d], y + n.y
            cv.box(bx, by, n.w, n.h, "", stroke=n.color or (DIM if n.dim else CYAN))
            for i, ln in enumerate(n.lines):
                put_line(cv, bx + (n.w - len(ln)) // 2, by + 1 + i, ln)
        for n in self.nodes:
            if not n.children:
                continue
            right, row = x + self.colx[n.d] + n.w - 1, y + n.y + n.h // 2
            bus, left = x + self.colx[n.d + 1] - 2, x + self.colx[n.d + 1]
            edge = cv.cells[row][right]                    # the border cell the connector leaves
            stroke = edge[1]
            edge[0] = " "
            for c in n.children:
                to = y + c.y + c.h // 2
                cv.joined_path([(right, row), (bus, row), (bus, to), (left, to)],
                               TREE_GUIDE, head=False)
                cv.cells[to][left][0] = "┤"
            edge[0], edge[1] = "├", stroke


def choose_tree_layout(root, want, width):
    """The layout to draw `root` in at `width` columns, and the width each one tried needs.

    `auto` takes the first that fits, so a narrower pane only ever moves down this list: boxes
    top down; the same boxes turned, with the root at the left; the turned boxes with tighter
    text, then the upright ones; one line per leaf; an indented list. Turning comes before any
    text is squeezed, and boxes come before any text form. The list always fits.
    """
    names = ("top", "left", "side", "list") if want == "auto" else (want,)
    wide, tight = TREE_CAPS[0], TREE_CAPS[1:]
    tries = [(n, wide) for n in ("top", "left")] + [(n, c) for n in ("left", "top") for c in tight]
    need = {}
    for name, cap in tries:
        if name in names:
            box = (TopLayout if name == "top" else LeftLayout)(root, cap)
            need[name] = box.width
            if box.width <= width and (want != "auto" or box.height <= TREE_BOX_ROWS):
                return box, need
    if "side" in names:
        side = SideLayout(root)
        need["side"] = side.width
        if side.width <= width:
            return side, need
    return ListLayout(root, min(width, TEXT_W)), need


def d_tree(cv, b, x, y, width, notes):
    warn = _warner(notes, b.line)
    try:
        opts = dict(kv.split("=", 1) for kv in shlex.split(b.args))
    except ValueError:
        raise MdError(b.line, "tree options look like: ```tree layout=side depth=3")
    for k in set(opts) - {"layout", "depth"}:
        warn(f"tree option {k!r} is ignored (options: layout, depth)")
    want = opts.get("layout", "auto").lower()
    if want not in TREE_LAYOUTS:
        raise MdError(b.line, f"layout= takes one of: {', '.join(TREE_LAYOUTS)}")
    root = parse_tree(b)
    if "depth" in opts:
        if not opts["depth"].isdigit():
            raise MdError(b.line, "depth= takes a number of levels below the root")
        _fold(root, int(opts["depth"]))
    lay, need = choose_tree_layout(root, want, width)
    if want == "auto":
        cv.degraded += {"top": 0, "left": 0, "side": 1, "list": 2}[lay.kind]
    if lay.kind == "list":
        if want in ("top", "left", "side"):
            warn(f"layout={want} needs {need[want]} columns, the pane has {width}: drawn as a "
                 f"list")
        if lay.need > width:
            warn(f"the tree is {lay.depth} levels deep and needs {lay.need} columns, the pane "
                 f"has {width}: fold it with depth=N")
    lay.draw(cv, x, y)
    return y + lay.height


# -- panels ----------------------------------------------------------------------------------
def _panels_at(b, width, side):
    """Draw the panels' blocks side by side or stacked: (panel width, drawn, notes, degraded)."""
    n = len(b.panels)
    pw = min(PANEL_W, (width - 2 * (n - 1)) // n if side else width)
    drawn, notes, degraded = [], [], 0
    for title, ln, blocks in b.panels:
        sub = Canvas(pw - 4)
        h = draw_blocks(sub, blocks, 0, 0, pw - 4, notes)
        degraded += sub.degraded
        drawn.append((title, sub, h))
    return pw, drawn, notes, degraded


def d_panels(cv, b, x, y, width, notes):
    n = len(b.panels)
    side = n > 1 and (width - 2 * (n - 1)) // n >= 34
    pw, drawn, local, degraded = _panels_at(b, width, side)
    if side and (local or degraded):          # stack them rather than lose a drawing
        alt = _panels_at(b, width, False)
        if (len(set(alt[2])), alt[3]) < (len(set(local)), degraded):
            side = False
            pw, drawn, local, degraded = alt
    notes.extend(local)
    H = max(h for _, _, h in drawn)
    for i, (title, sub, h) in enumerate(drawn):
        px, ph = (x + i * (pw + 2), H) if side else (x, h)
        color = span_color(title) or MUTED
        cv.box(px, y, pw, ph + 4, "", stroke=color, bg=BG)
        head = [SPACE] + cut(inline(title, color, True), pw - 6) + [SPACE]
        for i, (ch, fg, _, bold) in enumerate(head):          # replaces part of the border
            cv.cells[y][px + 2 + i] = [ch, fg, BG, bold]
        for yy in range(min(h, sub.h)):
            for xx in range(sub.w):
                ch, fg, bg, bold = sub.cells[yy][xx]
                if ch != " " or bg != BG:
                    cv.put(px + 2 + xx, y + 2 + yy, ch, fg, bg, bold)
        if not side:
            y += ph + 5
    return y + H + 4 if side else y - 1


DRAW = {"h2": d_h2, "h3": d_h3, "p": d_p, "note": d_note, "li": d_li, "hr": d_hr,
        "code": d_code, "table": d_table, "bars": d_bars, "flow": d_flow, "seq": d_seq,
        "tree": d_tree, "panels": d_panels}


def preview(text, widths):
    """Plain text of every page at each width, with warnings. For show.py --plain."""
    out = []
    for page in pages(text):
        for w in widths:
            cv = render(page, w)
            out.append(f"== {page[0]} · {w} cols · {cv.h} rows")
            out.append(cv.plain())
            out.append("-- warnings: " + ("none" if not cv.notes else str(len(cv.notes))))
            out += [f"   line {ln}: {msg}" for ln, msg in cv.notes]
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(prog="mdview.py", description="Print pages as plain text.")
    ap.add_argument("file", help="a Markdown file, or - for stdin")
    ap.add_argument("--cols", default="100")
    a = ap.parse_args()
    src = sys.stdin.read() if a.file == "-" else open(a.file).read()
    try:
        print(preview(src, [int(c) for c in a.cols.split(",")]))
    except MdError as e:
        print(e, file=sys.stderr)
        sys.exit(5)
