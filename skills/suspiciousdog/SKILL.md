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

    python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/run.py" <command>

Anywhere else, if installed: `sdog <command>`. Commands:

- `sniff` — every factor against every outcome. `--agent`, `--project`, `--path`, `--outcome`, `--all`.
- `test "EXPR"` — the user's own hypothesis as a Python expression over a turn `t`
  (`t.request`, `t.reply`, `t.final`, `t.tool_calls`, `t.files_written`, `t.errors`, `t.uses("subagent")`, `t.when`).
- `show "FACTOR" --outcome OUTCOME` — the real turns behind a number.
- `before-after DATE|FILE` — outcomes before and after a change (a date, or a file like CLAUDE.md: its last commit).
- `kit [NAME]` — everything the user added to the agent (skills, MCP servers, subagents, plugins, instruction files,
  hooks): tokens it weighs, sessions that load it vs use it, failures, and a verdict (ballast, rare, elsewhere,
  misused, earns, new). `--json` for structured output, `--kind skill|mcp|...`. Claude Code only for now.
- `timeline` — every change to the kit (items added or removed, instruction files edited, model shifts), found in
  the transcripts, with outcomes in the 14 days before and after. `--days N`, `--all`.
- `rules` — beta: rules in instruction files that the user's corrections keep echoing, with examples.
- `doctor` — what can be read, and whether the transcript format looks changed.
- `checkup` (or no command) — one screen: ballast, misused tools, recent changes and their effect, habits.
- `prune` — proposals to disable plugins, remove user MCP servers, move user skills away. Without `--apply` it only
  lists. `undo`, `note "text" [--key ITEM]`, `journal`.
- `report [--out FILE]` — one static HTML page with everything, written to disk.
- `brief [--here] [--json]` — what the user's past sessions say, in a few lines (~250 tokens): habits that go with
  worse answers, tools that keep failing and what to do about it. Every line stands on counts.
- `check "RULE TEXT" [--json]` — before adding a rule: is something like it already loaded, do the user's
  corrections say it, do the tools it names fail for a reason it would fix? Verdict: already said, supported, weak,
  no evidence.
- `hooks [on|off] brief|sentinel` — optional Claude Code hooks, off by default: the brief at the start of each
  session, and the sentinel (one line a week on what a change did). Each is journaled, `undo` reverts it.
- `mcp` — the same answers as an MCP server: `audit_setup`, `check_rule`, `evidence`.
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

## The kit

1. When the user asks what weighs on the context, what they never use, or before they install another plugin, skill
   or MCP server, run `kit --json` and answer with the numbers: weight, sessions loaded vs used, failures.
2. Token weights are estimates (characters ÷ 4). Say so.
3. For ballast and rare items, give the `remove` hint from the output, or show the `prune` proposals. Never remove,
   disable or move anything without the user's pick (see 9).
4. For misused items, run `kit NAME` and read the failure samples before guessing why it fails.
5. Items marked "built in" can't be removed. Don't suggest it.
6. Failures come with a reason (auth, wrong arguments, bad code, not found, wrong target, setup, blocked, timeout,
   server). Auth and server are configuration; the others are usually the agent, and a short rule can fix them.
   Propose the rule; don't write it into the user's files without asking.
7. Before the user adds a rule, run `check "the rule"` (or the `check_rule` tool) and tell them the verdict with
   its numbers: "already said" means make the existing line more concrete instead; "no evidence" means it would
   cost tokens in every session for a problem their sessions don't show. Then `rules` and `timeline`: has a similar
   rule been repeated, or changed nothing?
8. `timeline` says "after", never "because". Changes on the same day can't be told apart. Under 100 turns it says
   "too early": repeat that, don't guess.
9. Run `prune` without `--apply` to show the proposals. Run `prune --apply N` only for the numbers the user picked
   in this conversation, never on your own. Same for `undo`. After the user disconnects something by hand, offer
   `note` so it gets measured.
10. The report holds project names and error messages: never upload or paste it anywhere.
11. Before recommending or installing a plugin, skill or MCP server, look it up with `kit NAME` (or `evidence`): if
    the user already has something similar that is ballast, say so.
12. The brief is evidence about this user, not a rulebook: follow it where it applies, and never paste it into their
    files. Turning the hooks on is the user's choice; say what each costs (the brief ~250 tokens a session).
13. SuspiciousDog shows up in its own kit. If it is ballast for this user, say that too.
