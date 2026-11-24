#!/usr/bin/env python3
"""Show pages in this agent session's explain pane, a herdr pane beside the agent's pane.

Usage:
  show.py <<'EOF'              Markdown pages from stdin, each starting with '# Title' (SKILL.md)
  show.py FILE.md|FILE.py ...  pages from files; a .py file is a textkit diagram (render(cols, rows))
  show.py --plain [--cols N,M] [FILE ...]   print the pages as plain text; herdr not needed

A page whose title is already in the pane replaces it where it is; the first page given is
shown. Once the pane is closed its pages are forgotten: the next call opens a new pane with
only the pages it gives. Prints nothing on success, except layout warnings worth fixing.

The session is the herdr pane this runs from ($HERDR_PANE_ID). Its gallery is
$TMPDIR/explain-in-pane/<pane id>/ and remembers the explain pane by id, so a pane of the
same name elsewhere is never touched. With no explain pane in the agent pane's tab, it splits
the agent pane to the right (half, focus stays) and starts viewer.py there.

Exit: 0 shown | 2 usage | 3 not inside herdr | 5 a page cannot be drawn (nothing shown)
      6 the viewer did not draw within 10 s
"""
import json
import os
import re
import shlex
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mdview  # noqa: E402
import textkit as tk  # noqa: E402

WIDTHS = (80, 120, 200)          # every page is laid out at these widths before it is shown


def slug(title):
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "page"


def collect(args, text):
    """[(name, title, content, page or None, path or None)] in the order given."""
    items = []
    sources = [("<stdin>", text)] if text is not None else []
    for f in args:
        if not os.path.isfile(f):
            raise SystemExit(f"no such file: {f}") from None
        if f.endswith(".py"):
            items.append((os.path.basename(f), None, None, None, f))
        else:
            with open(f) as fh:
                sources.append((f, fh.read()))
    for src, body in sources:
        for page in mdview.pages(body):
            title, lines, n = page
            content = "\n".join([f"# {title}"] + [raw for _, raw in lines]) + "\n"
            items.append((slug(title) + ".md", title, content, page, src))
    return items


def check(items):
    """Lay out every page at WIDTHS. Returns (errors, warnings) as printable lines."""
    errors, warnings = [], []
    for name, title, content, page, path in items:
        try:
            if page is None:
                mod = tk.load(path)
                for w in WIDTHS:
                    cv = mod.render(w, 40)
                    warnings += [f"{name} at {w} columns: {m}" for m in cv.warnings[:5]]
            else:
                seen = {}
                for w in WIDTHS:
                    for ln, msg in mdview.render(page, w).notes:
                        seen.setdefault((ln, msg.replace(f"at {w} columns", "at N columns")),
                                        []).append(w)
                for (ln, msg), ws in sorted(seen.items()):
                    where = "" if len(ws) == len(WIDTHS) else f" (at {', '.join(map(str, ws))} columns)"
                    warnings.append(f"{title!r} line {ln}: {msg}{where}")
        except mdview.MdError as e:
            errors.append(f"{title!r} {e}")
        except Exception:
            errors.append(f"{name} does not render:\n{traceback.format_exc()}")
    return errors, warnings


def herdr(*args):
    r = subprocess.run(["herdr", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"herdr {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    try:
        return json.loads(r.stdout)["result"]
    except (ValueError, KeyError, TypeError):
        return None


def tab_of(pane):
    try:
        return herdr("pane", "get", pane)["pane"]["tab_id"]
    except (RuntimeError, KeyError, TypeError, ValueError):
        return None


def write(path, content):
    tmp = os.path.join(os.path.dirname(path), "." + os.path.basename(path) + ".tmp")
    with open(tmp, "w") as f:
        f.write(content)
    os.replace(tmp, path)


def viewer_alive(g):
    try:
        with open(os.path.join(g, "viewer.pid")) as f:
            pid = f.read().strip()
        r = subprocess.run(["ps", "-p", pid, "-o", "command="], capture_output=True, text=True)
        return f"viewer.py {g}" in r.stdout
    except (FileNotFoundError, ValueError):
        return False


def clear(g):
    """Forget the pages of earlier explanations, so a new viewer shows only the new ones."""
    for name in os.listdir(g):
        if name == "order" or name.endswith((".md", ".py")):
            os.remove(os.path.join(g, name))


def show(items):
    me = os.environ["HERDR_PANE_ID"]
    g = os.path.join(os.environ.get("TMPDIR", "/tmp").rstrip("/") or "/tmp", "explain-in-pane",
                     re.sub(r"[^A-Za-z0-9_-]", "_", me))
    os.makedirs(g, exist_ok=True)

    my_tab = tab_of(me)
    try:
        with open(os.path.join(g, "pane")) as f:
            pane = f.read().strip()
    except FileNotFoundError:
        pane = ""
    if pane and (my_tab is None or tab_of(pane) != my_tab):
        pane = ""
    if not pane or not viewer_alive(g):     # the pane was closed: start from these pages only
        clear(g)

    try:
        with open(os.path.join(g, "order")) as f:
            order = f.read().split()
    except FileNotFoundError:
        order = []
    for name, title, content, page, path in items:
        if page is None:
            with open(path) as f:
                content = f.read()
        write(os.path.join(g, name), content)
        if name not in order:
            order.append(name)
    write(os.path.join(g, "order"), "\n".join(order) + "\n")

    if not pane:
        pane = herdr("pane", "split", me, "--direction", "right", "--ratio", "0.5",
                     "--no-focus")["pane"]["pane_id"]
        try:
            herdr("pane", "rename", pane, "explain")
        except RuntimeError:
            pass
        write(os.path.join(g, "pane"), pane + "\n")
        try:
            os.remove(os.path.join(g, "viewer.pid"))
        except FileNotFoundError:
            pass

    token = f"{os.getpid()}-{time.time_ns()}"
    write(os.path.join(g, "focus"), f"{items[0][0]} {token}\n")
    if not viewer_alive(g):
        herdr("pane", "run", pane, f"exec python3 {shlex.quote(os.path.join(HERE, 'viewer.py'))} "
                                   f"{shlex.quote(g)}")
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with open(os.path.join(g, "shown")) as f:
                status = f.read().strip()
        except FileNotFoundError:
            status = ""
        if status.startswith(token + " "):
            status = status[len(token) + 1:]
            if status == "ok":
                return 0
            print(f"viewer: {status}", file=sys.stderr)
            return 5
        time.sleep(0.03)
    print(f"the viewer in pane {pane} did not draw {items[0][0]} within 10 s", file=sys.stderr)
    return 6


def main(argv):
    plain, widths, files = False, [100], []
    it = iter(argv)
    for a in it:
        if a == "--plain":
            plain = True
        elif a == "--cols":
            widths = [int(c) for c in next(it, "100").split(",")]
        elif a in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        elif a.startswith("-") and a != "-":
            print(f"unknown option {a}\n\n{__doc__.strip()}", file=sys.stderr)
            return 2
        else:
            files.append(a)
    text = None
    if not files or "-" in files:
        if sys.stdin.isatty():
            print(__doc__.strip(), file=sys.stderr)
            return 2
        text = sys.stdin.read()
        files = [f for f in files if f != "-"]
    try:
        items = collect(files, text)
    except mdview.MdError as e:
        print(e, file=sys.stderr)
        return 5
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2
    if plain:
        for name, title, content, page, path in items:
            if page is None:
                mod = tk.load(path)
                for w in widths:
                    cv = mod.render(w, 40)
                    print(f"== {tk.title_of(mod, path)} · {w} cols\n{cv.plain()}")
            else:
                print(mdview.preview(content, widths))
        return 0
    errors, warnings = check(items)
    if errors:
        print("nothing shown:\n" + "\n".join(errors), file=sys.stderr)
        return 5
    if os.environ.get("HERDR_ENV") != "1" or not os.environ.get("HERDR_PANE_ID"):
        print("not inside herdr: answer in text, or print the drawing with show.py --plain",
              file=sys.stderr)
        return 3
    titles = [t for _, t, *_ in items if t]
    dup = sorted({t for t in titles if titles.count(t) > 1})
    warnings += [f"two pages are titled {t!r}: the last one is kept" for t in dup]
    code = show(items)
    if warnings and code == 0:
        print("shown, with layout warnings:\n" + "\n".join("  " + w for w in warnings),
              file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
