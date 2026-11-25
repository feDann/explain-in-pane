"""Tests for the tree block: python3 -m unittest discover tests

Parsing and its errors, the three layouts on one small tree, and a check over random trees that
every layout draws every node once, inside the pane, without a layout warning.
"""
import os
import random
import re
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills",
                                "explain-in-pane", "scripts"))
import mdview  # noqa: E402

APP = """\
app
  requests
    urllib3
    certifi
  rich
    pygments
"""


def page(body, opts=""):
    return mdview.pages(f"# t\n\n```tree {opts}\n{body}```\n")[0]


def draw(body, opts="", cols=100):
    cv = mdview.render(page(body, opts), cols)
    return cv, [ln for ln in cv.plain().split("\n")]


def block(lines):
    """The drawing without the page's blank first row and the indent of two columns."""
    rows = [ln[2:] for ln in lines]
    while rows and not rows[0]:
        rows.pop(0)
    while rows and not rows[-1]:
        rows.pop()
    return "\n".join(rows)


class ParseTree(unittest.TestCase):
    def root(self, body):
        return mdview.parse_tree(mdview.parse(page(body)[1])[0])

    def test_nesting_by_indent(self):
        r = self.root(APP)
        self.assertEqual([c.label for c in r.children], ["requests", "rich"])
        self.assertEqual([c.label for c in r.children[0].children], ["urllib3", "certifi"])

    def test_any_consistent_indent_step(self):
        r = self.root("a\n    b\n        c\n    d\n")
        self.assertEqual([c.label for c in r.children], ["b", "d"])
        self.assertEqual(r.children[0].children[0].label, "c")

    def test_key_sub_and_colour(self):
        r = self.root("Assign\n  value: {red: BinOp (+)}\n")
        n = r.children[0]
        self.assertEqual((n.key, n.label, n.sub), ("value", "BinOp", "+"))
        self.assertIsNotNone(n.color)

    def test_a_colon_without_a_space_is_part_of_the_label(self):
        r = self.root("a\n  b:\n  http://x\n")
        self.assertEqual([c.label for c in r.children], ["b:", "http://x"])
        self.assertEqual([c.key for c in r.children], [None, None])

    def test_a_backslash_keeps_a_name_that_looks_like_a_key(self):
        r = self.root("a\n  \\note: x\n  b: c\n")
        self.assertEqual([(c.key, c.label) for c in r.children], [(None, "note: x"), ("b", "c")])
        with self.assertRaises(mdview.MdError):
            self.root("a\n  \\\n")

    def test_depth_folds_what_is_below(self):
        cv, rows = draw(APP, "layout=list depth=1")
        text = "\n".join(rows)
        self.assertIn("… 2 more", text)                  # under requests
        self.assertIn("… 1 more", text)                  # under rich
        self.assertNotIn("urllib3", text)
        self.assertIn("… 5 more", "\n".join(draw(APP, "layout=list depth=0")[1]))

    def test_errors_name_the_line(self):
        cases = {
            "": "empty",
            "a\nb\n": "one root",
            "  a\nb\n": "less than the root",
            "a\n    b\n  c\n": "matches no line",
        }
        for body, word in cases.items():
            with self.assertRaises(mdview.MdError, msg=body) as cm:
                mdview.render(page(body), 80)
            self.assertIn(word, cm.exception.msg)
        with self.assertRaises(mdview.MdError) as cm:
            mdview.render(page("a\nb\n"), 80)
        self.assertEqual(cm.exception.line, 5)            # the file line of `b`

    def test_bad_options(self):
        for opts in ("layout=circle", "depth=x", "layout='top"):
            with self.assertRaises(mdview.MdError, msg=opts):
                mdview.render(page("a\n", opts), 80)


class Layouts(unittest.TestCase):
    LIST = """\
app
├── requests
│   ├── urllib3
│   └── certifi
└── rich
    └── pygments"""

    SIDE = """\
app ─┬─ requests ─┬─ urllib3
     │            └─ certifi
     └─ rich ─── pygments"""

    TOP = """\
          ╭─────╮
          │ app │
          ╰──┬──╯
   ╭─────────┴──────────╮
 ╭─────┴────╮           ╭───┴──╮
 │ requests │           │ rich │
 ╰─────┬────╯           ╰───┬──╯
 ╭─────┴──────╮             │
╭────┴────╮  ╭────┴────╮  ╭─────┴────╮
│ urllib3 │  │ certifi │  │ pygments │
╰─────────╯  ╰─────────╯  ╰──────────╯"""

    LEFT = """\
                         ╭─────────╮
                       ╭─┤ urllib3 │
          ╭──────────╮ │ ╰─────────╯
        ╭─┤ requests ├─┤
        │ ╰──────────╯ │ ╭─────────╮
╭─────╮ │              ╰─┤ certifi │
│ app ├─┤                ╰─────────╯
╰─────╯ │
        │ ╭──────╮       ╭──────────╮
        ╰─┤ rich ├───────┤ pygments │
          ╰──────╯       ╰──────────╯"""

    def test_list(self):
        cv, rows = draw(APP, "layout=list")
        self.assertEqual(block(rows), self.LIST)

    def test_side(self):
        cv, rows = draw(APP, "layout=side")
        self.assertEqual(block(rows), self.SIDE)

    def test_top(self):
        cv, rows = draw(APP, "layout=top")
        got = block(rows).split("\n")
        self.assertEqual(len(got), 11)
        self.assertEqual([r.strip() for r in got][:3], ["╭─────╮", "│ app │", "╰──┬──╯"])
        self.assertEqual(cv.notes, [])

    def test_left(self):
        cv, rows = draw(APP, "layout=left")
        self.assertEqual(block(rows), self.LEFT)
        self.assertEqual(cv.notes, [])

    def test_a_tree_too_wide_for_top_is_turned_before_it_becomes_text(self):
        body = "root\n" + "".join(f"  child{i}\n" for i in range(6))
        _, wide = draw(body, "", 120)
        _, narrow = draw(body, "", 50)
        self.assertNotIn("┤", "\n".join(wide))             # fits as boxes top down
        text = "\n".join(narrow)
        self.assertIn("┤", text)                          # still boxes, turned to the left
        self.assertNotIn("├──", text)                     # not the list
        self.assertNotIn("─┬─", text)                     # not the side text

    def test_long_names_still_get_boxes_when_turned(self):
        body = "root\n" + "".join(f"  a-fairly-long-name-{i}\n" for i in range(5))
        _, rows = draw(body, "", 60)
        self.assertIn("╭", "\n".join(rows))

    def test_auto_takes_the_first_that_fits(self):
        _, wide = draw(APP, "", 100)
        _, narrow = draw(APP, "", 30)
        self.assertIn("╭─────╮", "\n".join(wide))
        self.assertEqual(block(narrow), self.LIST)

    def test_a_layout_that_does_not_fit_is_drawn_as_a_list_and_reported(self):
        cv, rows = draw(APP, "layout=top", 30)
        self.assertEqual(block(rows), self.LIST)
        self.assertEqual(len(cv.notes), 1)
        self.assertIn("layout=top needs", cv.notes[0][1])

    def test_a_straight_line_to_the_middle_child(self):
        _, rows = draw("a\n  b\n  c\n  d\n", "layout=top")
        self.assertIn("┼", "\n".join(rows))
        self.assertNotRegex("\n".join(rows), "┬─+┴|┴─+┬")

    def test_too_deep_for_the_pane_is_reported(self):
        body = "".join("  " * i + f"n{i}\n" for i in range(30))
        cv, _ = draw(body, "", 40)
        self.assertTrue(any("levels deep" in m for _, m in cv.notes))

    def test_a_long_label_wraps_under_its_guides(self):
        cv, rows = draw("a\n  " + "word " * 12 + "\n  b\n", "layout=list", 30)
        self.assertEqual(cv.notes, [])
        self.assertTrue(all(len(r) <= 30 for r in rows))
        wrapped = [r for r in rows if r.startswith("  │ ")]
        self.assertTrue(wrapped)                         # continuation rows keep the guide

    def test_in_panels_and_after_a_flow(self):
        text = ("# t\n\n```flow\na --> b\n```\n\n::: panels\n### one\n```tree layout=top\n"
                "a\n  b\n  c\n```\n### two\n```tree\nx\n  y\n```\n:::\n")
        cv = mdview.render(mdview.pages(text)[0], 100)
        self.assertEqual(cv.notes, [])


AST = """\
Assign
  target: Name x
  value: BinOp (+)
    left: Constant 2
    right: BinOp (*)
      left: Name y
      right: Constant 3
"""


class InPanels(unittest.TestCase):
    """Panels stack before a drawing inside them turns into text."""

    def panels(self, cols):
        text = ("# t\n\n::: panels\n### input\n```text\n" + AST + "```\n### drawn\n```tree\n"
                + AST + "```\n:::\n")
        cv = mdview.render(mdview.pages(text)[0], cols)
        rows = cv.plain().split("\n")
        return cv, rows, any("╭─ input" in r and "╭─ drawn" in r for r in rows)

    def test_the_tree_stays_boxes_while_the_panels_can_stack(self):
        for cols in range(160, 79, -1):
            cv, rows, _ = self.panels(cols)
            self.assertIn("│ Assign │", "\n".join(rows), f"{cols} columns")
            self.assertEqual(cv.notes, [])

    def test_side_by_side_when_both_fit_and_stacked_when_the_drawing_needs_room(self):
        self.assertTrue(self.panels(160)[2])
        self.assertFalse(self.panels(100)[2])

    def test_a_table_is_kept_as_a_table_by_stacking(self):
        text = ("# t\n\n::: panels\n### one\n| Name | Value | Notes |\n|---|---|---|\n"
                "| alpha-long-name | 1234567 | a longer explanatory note |\n### two\n- x\n:::\n")
        rows = mdview.render(mdview.pages(text)[0], 80).plain().split("\n")
        self.assertTrue(any("Name" in r and "Value" in r and "Notes" in r for r in rows))
        self.assertFalse(any("╭─ one" in r and "╭─ two" in r for r in rows))

    def test_two_plain_panels_stay_side_by_side(self):
        text = "# t\n\n::: panels\n### a\n- x\n### b\n- y\n:::\n"
        rows = mdview.render(mdview.pages(text)[0], 80).plain().split("\n")
        self.assertTrue(any("╭─ a" in r and "╭─ b" in r for r in rows))


def random_tree(rng, size):
    """`size` lines n0, n1, ... nested at random, up to 8 levels deep."""
    depth = [0]                                        # level of each line written so far
    lines = ["n0"]
    for i in range(1, size):
        d = rng.randint(1, min(8, depth[-1] + 1))
        depth.append(d)
        lines.append("  " * d + (f"k{i}: " if rng.random() < .3 else "") + f"n{i}"
                     + (" (sub)" if rng.random() < .2 else ""))
    return "\n".join(lines) + "\n"


class Random(unittest.TestCase):
    def test_a_narrower_pane_never_goes_back_to_boxes_from_text(self):
        form = {"top": 0, "left": 0, "side": 1, "list": 2}
        rng = random.Random(3)
        for case in range(40):
            body = random_tree(rng, rng.choice([3, 8, 13, 21, 34]))
            root = mdview.parse_tree(mdview.parse(page(body)[1])[0])
            kinds = [mdview.choose_tree_layout(root, "auto", w)[0].kind
                     for w in range(200, 20, -1)]
            self.assertEqual([form[k] for k in kinds], sorted(form[k] for k in kinds), body)
            flips = sum(a != b for a, b in zip(kinds, kinds[1:]) if {a, b} <= {"top", "left"})
            self.assertLessEqual(flips, 2, f"{kinds}\n{body}")

    def test_every_node_once_inside_the_pane(self):
        rng = random.Random(7)
        for case in range(60):
            size = rng.choice([1, 2, 3, 5, 8, 13, 21, 34, 60])
            body = random_tree(rng, size)
            for layout in ("auto", "list", "side", "top", "left"):
                for cols in (40, 60, 80, 120, 200):
                    cv = mdview.render(page(body, f"layout={layout}"), cols)
                    where = f"layout={layout} cols={cols}\n{body}"
                    notes = [m for _, m in cv.notes if "drawn as a list" not in m]
                    self.assertEqual(notes, [], where)
                    rows = cv.plain().split("\n")
                    self.assertTrue(all(len(r) <= cols for r in rows), where)
                    text = "\n".join(rows)
                    for i in range(size):
                        self.assertEqual(len(re.findall(rf"\bn{i}\b", text)), 1,
                                         f"n{i} in {where}")


if __name__ == "__main__":
    unittest.main()
