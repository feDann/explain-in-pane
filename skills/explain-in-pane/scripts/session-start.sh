#!/bin/sh
# Session-start hook: inside herdr, tell the agent it can draw explanations in a side pane.
# Wire it to whatever your harness runs at session start and adds to the agent's context.
# Prints nothing outside herdr, so the explain-in-pane skill is not used where it cannot draw.
[ "${HERDR_ENV:-}" = 1 ] && [ -n "${HERDR_PANE_ID:-}" ] || exit 0
cat <<'MSG'
This session runs inside herdr, so the explain-in-pane skill can draw in a pane beside this one. Use it on your own, without being asked, when an answer explains something with several moving parts: a flow between components, a sequence of calls, quantities against a limit, a before and after, or a comparison of options. Load the skill, draw the explanation, and keep the text reply to 2 or 3 sentences. Answer in text only for short answers, code changes and status updates.
MSG
