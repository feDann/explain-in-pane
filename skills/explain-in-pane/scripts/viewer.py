#!/usr/bin/env python3
"""The explain pane: shows the pages sent since it opened, redrawn whenever the pane resizes.

Usage: viewer.py GALLERY_DIR      (show.py starts it inside a herdr pane)

GALLERY_DIR holds the pages (<name>.md, one Markdown page each, or <name>.py, a textkit
diagram) and:
  order        one file name per line, oldest first (show.py appends)
  focus        "<name> <token>": show.py asks for <name>; a new token means a new request
  shown        "<token> ok" or "<token> error <message>", written once the request is drawn
  viewer.pid   this process while it runs

Keys (nvim style): h/l previous/next page, [N]gt go to page N, gt/gT next/previous,
j/k or Ctrl-e/Ctrl-y one line, Ctrl-d/Ctrl-u half a page, Ctrl-f/Ctrl-b a page,
gg/G top/bottom, [N]G line N, a count before a motion repeats it, q quits (the pane closes).
Mouse: click the arrows in the footer; the wheel scrolls.
"""
import os
import select
import signal
import sys
import termios
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mdview  # noqa: E402
import textkit as tk  # noqa: E402

POLL = 0.1           # seconds between looks at the gallery
FOOT_BG, FOOT_FG, FOOT_DIM, FOOT_KEY = "#2a2c35", tk.FG, "#8a8f99", tk.CYAN


def sgr(fg, bg, bold=False):
    f, b = tk.rgb(fg), tk.rgb(bg)
    return f"\x1b[{'1' if bold else '22'};38;2;{f[0]};{f[1]};{f[2]};48;2;{b[0]};{b[1]};{b[2]}m"


class Viewer:
    def __init__(self, gallery):
        self.g = gallery
        self.names, self.idx = [], 0
        self.top = {}                 # name -> first visible row
        self.cache = {}               # name -> (mtime, cols, rows, title, ansi rows, error)
        self.request = None           # last focus line handled
        self.answer = None            # (token, status) to write once drawn
        self.count, self.pending = "", ""
        self.buttons = []             # (x0, x1, action) on the footer row, 1-based columns
        self.size = (0, 0)
        self.drawn = None

    # -- gallery ---------------------------------------------------------------------------
    def p(self, name):
        return os.path.join(self.g, name)

    def poll(self):
        try:
            with open(self.p("order")) as f:
                names = [n for n in f.read().split() if os.path.isfile(self.p(n))]
        except FileNotFoundError:
            names = []
        if names != self.names:
            cur = self.current()
            self.names = names
            self.idx = names.index(cur) if cur in names else min(self.idx, max(0, len(names) - 1))
        try:
            with open(self.p("focus")) as f:
                line = f.read().strip()
        except FileNotFoundError:
            line = ""
        if line and line != self.request:
            self.request = line
            name, _, token = line.partition(" ")
            if name in self.names:
                self.idx = self.names.index(name)
                self.top[name] = 0
            self.answer = (token, name)

    def current(self):
        return self.names[self.idx] if self.names else None

    # -- drawing -----------------------------------------------------------------------
    def render(self, name, cols, rows):
        path = self.p(name)
        mtime = os.path.getmtime(path)
        hit = self.cache.get(name)
        if hit and hit[:3] == (mtime, cols, rows):
            return hit[3:]
        title, body, err = os.path.splitext(name)[0], [], None
        try:
            if name.endswith(".md"):
                with open(path) as f:
                    page = mdview.pages(f.read())[0]
                title = page[0]
                cv = mdview.render(page, cols)
            else:
                mod = tk.load(path)
                title = tk.title_of(mod, path)
                cv = mod.render(cols, rows)
            body = cv.ansi_rows()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            cv = tk.Canvas(cols)
            y = cv.text(2, 1, f"{name} failed to draw", tk.RED, bold=True) + 1
            for line in traceback.format_exc().splitlines():
                y = cv.para(2, y, line, cols - 4, tk.MUTED)
            body = cv.ansi_rows()
        self.cache[name] = (mtime, cols, rows, title, body, err)
        return title, body, err

    def frame(self):
        cols, rows = os.get_terminal_size(sys.stdout.fileno())
        self.size = (cols, rows)
        view = max(1, rows - 1)
        name = self.current()
        blank = sgr(tk.FG, tk.BG) + " " * cols + "\x1b[0m"
        if name is None:
            title, body, err = "", [], None
            msg = "No diagrams yet."
            body = [blank, sgr(tk.MUTED, tk.BG) + ("  " + msg).ljust(cols) + "\x1b[0m"]
        else:
            title, body, err = self.render(name, cols, view)
        top = max(0, min(self.top.get(name, 0), len(body) - view))
        self.top[name] = top
        shown = body[top:top + view]
        shown += [blank] * (view - len(shown))
        out = ["\x1b[?25l"]
        for i, row in enumerate(shown):
            out.append(f"\x1b[{i + 1};1H{row}")
        out.append(f"\x1b[{rows};1H" + self.footer(cols, title, top, len(body), view))
        sys.stdout.write("".join(out))
        sys.stdout.flush()
        if self.answer and self.answer[1] == name:
            self.reply(self.answer[0], "ok" if err is None else f"error {err}")
            self.answer = None
        elif self.answer and self.answer[1] not in self.names:
            self.reply(self.answer[0], f"error {self.answer[1]} is not in the gallery")
            self.answer = None

    def reply(self, token, status):
        tmp = self.p(".shown.tmp")
        with open(tmp, "w") as f:
            f.write(f"{token} {status}\n")
        os.replace(tmp, self.p("shown"))

    def footer(self, cols, title, top, total, view):
        n = len(self.names)
        pos = f"{self.idx + 1}/{n}" if n else "0/0"
        if total <= view:
            where = "all"
        elif top == 0:
            where = "top"
        elif top + view >= total:
            where = "bot"
        else:
            where = f"{100 * top // max(1, total - view)}%"
        hint = "h/l page · j/k scroll · q quit"
        right = f"  {hint}   {where} " if cols >= 70 else f"  {where} "
        left = [(" ◀ ", "prev", FOOT_KEY, True), (f" {pos} ", None, FOOT_FG, False),
                (" ▶ ", "next", FOOT_KEY, True), ("  ", None, FOOT_FG, False)]
        room = max(0, cols - sum(len(t) for t, *_ in left) - len(right))
        name = (title[:max(0, room - 1)] + "…") if len(title) > room else title
        parts = left + [(name.ljust(room), None, FOOT_FG, True), (right, None, FOOT_DIM, False)]
        self.buttons, x, out = [], 1, []
        for text, action, color, bold in parts:      # cut at the pane's right edge
            text = text[:max(0, cols - x + 1)]
            if action and text:
                self.buttons.append((x, x + len(text) - 1, action))
            out.append(sgr(color, FOOT_BG, bold) + text)
            x += len(text)
        return "".join(out) + "\x1b[0m"

    # -- input -------------------------------------------------------------------------
    def scroll(self, d):
        name = self.current()
        if name:
            self.top[name] = max(0, self.top.get(name, 0) + d)

    def go(self, i):
        if self.names:
            self.idx = max(0, min(len(self.names) - 1, i))

    def key(self, ch):
        """One key, vim style. Returns False to quit."""
        view = max(1, self.size[1] - 1)
        if ch.isdigit() and (ch != "0" or self.count):
            self.count += ch
            return True
        n, counted, self.count = int(self.count or 1), bool(self.count), ""
        if self.pending == "g":
            self.pending = ""
            if ch == "g":
                self.top[self.current()] = (n - 1) if counted else 0
            elif ch == "t":
                self.go(n - 1 if counted else self.idx + 1)
            elif ch == "T":
                self.go(self.idx - n)
            return True
        if ch == "g":
            self.pending, self.count = "g", (str(n) if counted else "")
        elif ch in ("j", "\x05", "DOWN"):
            self.scroll(n)
        elif ch in ("k", "\x19", "UP"):
            self.scroll(-n)
        elif ch == "\x04":
            self.scroll(n * (view // 2))
        elif ch == "\x15":
            self.scroll(-n * (view // 2))
        elif ch in ("\x06", "PGDN"):
            self.scroll(n * view)
        elif ch in ("\x02", "PGUP"):
            self.scroll(-n * view)
        elif ch == "G":
            self.top[self.current()] = (n - 1) if counted else 10 ** 9
        elif ch in ("l", "RIGHT"):
            self.go(self.idx + n)
        elif ch in ("h", "LEFT"):
            self.go(self.idx - n)
        elif ch == "HOME":
            self.top[self.current()] = 0
        elif ch == "END":
            self.top[self.current()] = 10 ** 9
        elif ch == "q":
            return False
        return True

    def mouse(self, b, x, y, press):
        if not press:
            return
        if b == 64:
            self.scroll(-3)
        elif b == 65:
            self.scroll(3)
        elif b == 0 and y == self.size[1]:
            for x0, x1, action in self.buttons:
                if x0 <= x <= x1:
                    self.go(self.idx + (1 if action == "next" else -1))

    def feed(self, data):
        """Parse keys and SGR mouse reports. Returns False to quit."""
        s, i = data.decode("utf-8", "replace"), 0
        seqs = {"[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT", "[5~": "PGUP",
                "[6~": "PGDN", "[H": "HOME", "[F": "END", "[1~": "HOME", "[4~": "END"}
        while i < len(s):
            if s.startswith("\x1b[<", i):
                j = i + 3
                while j < len(s) and s[j] not in "Mm":
                    j += 1
                try:
                    b, x, y = (int(v) for v in s[i + 3:j].split(";"))
                    self.mouse(b, x, y, s[j:j + 1] == "M")
                except ValueError:
                    pass
                i = j + 1
                continue
            if s[i] == "\x1b":
                for seq, name in seqs.items():
                    if s.startswith(seq, i + 1):
                        if not self.key(name):
                            return False
                        i += 1 + len(seq)
                        break
                else:
                    self.count, self.pending = "", ""   # a lone Escape cancels a count or g
                    i += 1
                continue
            if not self.key(s[i]):
                return False
            i += 1
        return True


def main():
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    v = Viewer(os.path.abspath(sys.argv[1]))
    pidfile = v.p("viewer.pid")
    with open(pidfile, "w") as f:
        f.write(f"{os.getpid()}\n")

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[3] &= ~(termios.ECHO | termios.ICANON)      # keys one at a time, not echoed
    new[0] &= ~termios.IXON                          # Ctrl-s/Ctrl-q are keys too
    new[6][termios.VMIN], new[6][termios.VTIME] = 1, 0
    termios.tcsetattr(fd, termios.TCSANOW, new)

    wake_r, wake_w = os.pipe()
    os.set_blocking(wake_w, False)
    signal.set_wakeup_fd(wake_w)
    signal.signal(signal.SIGWINCH, lambda *_: None)
    def stop(*_):
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)

    # alternate screen, no wrap, hidden cursor, mouse buttons in SGR form
    sys.stdout.write("\x1b[?1049h\x1b[?7l\x1b[?25l\x1b[?1000h\x1b[?1006h\x1b[2J")
    try:
        v.poll()
        v.frame()
        while True:
            ready, _, _ = select.select([fd, wake_r], [], [], POLL)
            redraw = False
            if wake_r in ready:
                os.read(wake_r, 512)
                redraw = True
            if fd in ready:
                data = os.read(fd, 1024)
                if not data or not v.feed(data):
                    break
                redraw = True
            before = (list(v.names), v.idx, v.request)
            v.poll()
            cur = v.current()
            try:
                stale = cur is not None and v.cache.get(cur, (None,))[0] != os.path.getmtime(v.p(cur))
            except FileNotFoundError:
                stale = True
            if redraw or stale or before != (v.names, v.idx, v.request):
                v.frame()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            sys.stdout.write("\x1b[?1006l\x1b[?1000l\x1b[?25h\x1b[?7h\x1b[0m\x1b[?1049l")
            sys.stdout.flush()
            termios.tcsetattr(fd, termios.TCSANOW, old)
        except OSError:
            pass                                     # the pane is already gone
        try:
            with open(pidfile) as f:
                mine = f.read().strip() == str(os.getpid())
            if mine:                                 # a newer viewer may own the file now
                os.remove(pidfile)
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
