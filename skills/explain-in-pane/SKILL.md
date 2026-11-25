---
name: explain-in-pane
description: Draws an explanation in a herdr pane beside the agent from short Markdown with flow, sequence, bar and tree blocks. The layout fits the pane's width and redraws on resize, and its pages stay browsable with nvim keys until the pane is closed. Use it on your own, without being asked, when the session runs inside herdr and an answer explains something with several moving parts, such as a flow between components, a sequence of calls, a tree (dependencies, an AST, a call tree), quantities against a limit, a before and after, or options compared. Also use it when the user asks to explain, draw or diagram something "in the pane" / "nel pane".
---

# Explain in pane

Write the explanation as Markdown and pipe it to `show.py` in one shell command. The layout is automatic, so don't compute positions or read the scripts first. This page has the whole format.

## When to use it on your own

The pane exists only inside herdr, where `$HERDR_ENV` is `1`. Some harnesses add a session note that says so. If there is none, check the variable once. Draw when the answer has a structure that prose hides:

- a flow between components, or calls between services
- a hierarchy: a dependency tree, an AST, a call tree, a directory layout
- quantities against a limit, such as memory, a quota or a latency budget
- a before and after, or options compared with a verdict

Answer in text only for short answers, code changes, status updates, and when the user asks for text.

## Quick start

`<skill-dir>` is this skill's base directory: the folder that holds this file.

````bash
<skill-dir>/scripts/show.py <<'EOF'
# Retry flow

## 1. A failed delivery goes back through the queue

```flow
client -->|POST /pay| api -->|enqueue| queue -->|deliver| worker
worker -->|{red: 503, retry}| queue
```

The worker answers {red: 503} while the gateway is down, and the message returns after a delay.
EOF
````

## The format

| Write | Draws |
|---|---|
| `# Title` | Starts a page. The title is in the pane's footer. Put several pages in one call: the first is shown. |
| `## 1. Section` | A section heading. |
| text, `- item`, `1. item` | Paragraphs and lists, wrapped to the pane. |
| `> text` | A grey footnote. |
| `\| a \| b \|` rows, `\|---\|` under the header | A table. It turns into one record per row when the pane is narrow. |
| `---` | A rule. |
| ```` ```flow ```` | Boxes and arrows. |
| ```` ```seq ```` | A sequence diagram. |
| ```` ```tree ```` | A tree from indented lines. |
| ```` ```bars cap=1024 unit=MiB ```` | Horizontal bars, with a red limit line at `cap`. |
| `::: panels`, `### title` per panel, `:::` | Panels side by side, stacked when the pane is narrow or when stacking keeps a drawing (a tree, a table) that side by side would turn into text. Panels hold any blocks. |
| any other fence | Code, drawn as written. |

Inline: `{red: text}` colours text, `**bold**`, `` `code` ``. Colours: red, green, orange, yellow, cyan, blue, purple, lime, teal, pink, grey.

**flow**

```text
kafka (topic: webhooks) -->|poll 500| consumer (1 pod) -->|insert| postgres
consumer -->|rebalance| {orange: old batch (not committed)}
```

- Each line is a chain drawn left to right. `name (sub)` adds a second line in the box. A name used again is the same box.
- A line that starts from a box already drawn branches down from it. An arrow back to an earlier box is drawn as a loop.
- `{red: name}` colours a box, and `-->|{red: 503}|` colours an arrow.
- In a narrow pane the flow runs top to bottom.

**seq**

```text
client -> api: POST /pay
api -> {red: gateway}: authorize
gateway --> api: {red: 401}
note api: no mapping for 401
--- retried after 30 s ---
api -> api: back off
```

- `->` is a call and `-->` a reply. `a -> a` is a self call, `note a: text` a note beside a, `--- text` a divider.
- Participants appear in the order first used. Six fit in 80 columns.

**bars**

```text
steady: heap 420, batch 260, meta 140
rebalance: heap 420, batch 260, old batch 260 orange, meta 140
```

- A row is `label: name value, name value` (stacked) or `label: 136`. A colour after a value sets it. Equal names share a colour, and two or more names add a legend.
- Options after `bars`: `cap=`, `unit=`, `max=` (the axis end), `caplabel="..."`.

**tree**

```text
app (python 3.12)
  requests 2.31
    urllib3 2.0
    certifi
  {red: pygments 2.16}
  urllib3 2.0 (*)
```

- One node per line, nested by indent (any step, as long as it is consistent), with a single root. Siblings are drawn in the order written, so write them in reading order.
- `name (sub)` and `{red: name}` work as in flow. `key: node` marks the node's role under its parent, such as an AST field, and is drawn with the node: `left: Name (x)`. A name that really starts with `word: ` takes a backslash: `\note: x`.
- `depth=N` folds everything below N levels into `… N more`. `layout=top`, `left`, `side` or `list` after `tree` pins a layout.

Writing a tree:

- Use `tree` when every node has one parent. A node that is exactly the same under two parents is two lines: mark the second `(*)` and leave its children out. The same name with another version is another node: write both in full. Cycles, or one node drawn once with two parents, are a `flow`.
- One root. When the data has none (a config, a list of packages), add one named for it. What belongs to a node goes in its `(sub)`, one fact each: a version, a value (`connect (2s)`), or the constraint on its edge (`urllib3 (1.26.16, needs <1.27)`).
- In an AST, the kind is the name, its value is the `(sub)` and the field is the key: `value: BinOp (+)`. Draw the nodes the answer is about and leave out wrappers such as `Module` and `ctx`.
- Leave the layout to the pane. It keeps boxes while they fit, turns them to run left to right when that fits, and only then draws text, so don't pin a layout unless you are comparing layouts. Never draw a tree by hand with `├──` in a text fence: that is drawn as written and cannot adapt.
- A big tree: fold it with `depth=2` or `3`. Colour only the nodes the answer is about, such as `{red: urllib3 1.26}`, and nothing when the question is just how it nests.
- To show the source beside its tree, use `::: panels` with a text fence and a tree. The panels stack by themselves when the pane is narrow.
- A warning `drawn as a list` means the pinned layout did not fit: drop `layout=`. A warning `levels deep` means the tree is too deep for the pane: fold it with `depth=`.

## What a page holds

- Numbered sections, one idea each, such as `## 1. A batch is one commit for all its records`. The heading states the point.
- At most one caption per section: one sentence of 25 words or fewer that says what to notice, coloured. Leave it out when the heading and the drawing already say it.
- Table cells and list items are fragments, not sentences.
- A `>` footnote only for a caveat that changes the conclusion.
- The real names, numbers and identifiers from the conversation.
- At most 3 sections per page. For more, write more pages in the same call, with the page that answers the question first.

## Workflow

1. Write the Markdown inside the shell command, in a quoted heredoc (`<<'EOF'`). No file is needed.
2. Read the result. No output means the page is shown. `shown, with layout warnings` names the lines to fix: fix the ones that matter, such as a cut label, and run again. The same `# Title` replaces the page where it is.
3. Reply in 2 or 3 sentences: the answer, and what to notice in the pane. Don't retell the pages: with several pages, say how many and which to read first. The first time in a session, add `In the pane: h/l switch pages, j/k scroll, q closes it.` Leave out file paths.

Follow-ups:

- "Fix it" or "that's wrong": send the page again with the same `# Title`.
- "More detail" on a section: a new page with its own title.
- "Next", "previous" or "scroll" said to you rather than typed in the pane: `herdr pane send-keys <pane> l`. The pane id command is in the reference.
- To see what the pane shows: `herdr pane read <pane> --source visible`.

## When show.py fails

| Exit | Meaning | Do |
|---|---|---|
| 2 | usage | Fix the call. |
| 3 | not inside herdr | Answer in text. For the drawing in a code block, pipe the same Markdown to `show.py --plain --cols 100`. |
| 5 | nothing was shown: the message names the page and line | Fix that line and run again. |
| 6 | the viewer did not draw within 10 s | `herdr pane read <pane> --source visible`. If the pane shows a shell, the viewer did not start: run again. |

For shapes Markdown cannot express, such as bands between columns, a page can be a Python drawing: see [references/textkit.md](references/textkit.md).
