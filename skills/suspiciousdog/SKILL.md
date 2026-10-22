---
name: suspiciousdog
description: Test ideas about how the agent works against the user's real transcripts. Use when the user asks whether a rule, plugin, skill, hook, model or habit actually helps, wants to know what goes wrong in their agent sessions, says "sniff", or before adding a rule to CLAUDE.md or AGENTS.md. Runs locally; nothing leaves the machine unless the user explicitly runs `share`.
---

# SuspiciousDog

Every rule or plugin for an agent is a hypothesis: "if the agent does X, the work goes better". The user's
transcripts already contain the experiment. SuspiciousDog splits them into turns (user message → what the agent
did → the user's next message), marks factors (what the agent did) and outcomes (pushback, deferral,
interruption, quick yes), and compares turns with and without each factor with Fisher's exact test and a
Benjamini-Hochberg correction.

## Running it

Inside the Claude Code plugin:

    PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m suspiciousdog <command>

Anywhere else, if installed: `sdog <command>`. Commands:

- `sniff` — every factor against every outcome. `--agent`, `--project`, `--path`, `--outcome`, `--all`.
- `test "EXPR"` — the user's own hypothesis as a Python expression over a turn `t`
  (`t.request`, `t.reply`, `t.final`, `t.tool_calls`, `t.files_written`, `t.errors`, `t.uses("subagent")`, `t.when`).
- `show "FACTOR" --outcome OUTCOME` — the real turns behind a number.
- `before-after DATE|FILE` — outcomes before and after a change (a date, or a file like CLAUDE.md: its last commit).
- `demo` — synthetic data, clearly labelled.
- `share` — sends counts only, after showing them. Never run it without the user's explicit yes in this conversation.

## Reading the results

1. Only `real` rows (q < 0.05) are findings. `maybe` is a lead, `vibes` is nothing. Say so plainly.
2. Before believing any finding, run `show` on it and read the turns. Outcomes are recognised from the text of the
   user's reply, so a "no" to an offer counts as pushback. Tell the user what the turns actually show.
3. It is correlation. Present it as "where to look", never as cause.
4. Propose at most one concrete change per finding, and offer to measure it later with `before-after`.
5. When the user wants to add a rule or install a plugin, check first whether the problem it solves appears in
   their data at all. "This happened 3 times in 1,000 turns" is a useful answer.
6. Never paste the user's transcripts anywhere. Quote only short excerpts back to the user.
