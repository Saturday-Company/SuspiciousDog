# Privacy

SuspiciousDog runs on your machine and reads files that are already there. It makes no network calls, with two
exceptions you have to ask for: `sdog share` and `sdog classify`.

## `sdog share`

1. It builds the payload from your results: the SuspiciousDog version, which agents and how many sessions each,
   how many answered turns, over how many distinct days, and for each factor × outcome four integers (turns with
   the factor, how many had the outcome, turns without, how many had the outcome).
2. Factor and outcome names come from SuspiciousDog's own vocabulary. `share.validate()` rejects any payload with
   a key, string or value outside it, and `tests/test_core.py` checks that no prompt, reply, agent message or path
   from the sessions appears in it.
3. It prints the payload and asks. Nothing happens unless you answer yes.
4. It opens a pre-filled GitHub issue in your browser. You submit it yourself, under your GitHub account, in public.
   `sdog share --save file.json` writes the payload to a file instead.

Custom hypotheses from `sdog test` are never included.

Format 2 (0.2.0) adds counts about the kit: for each item with a public name, sessions that loaded it, sessions that
used it, calls, failures and its weight in tokens. Public means on the fixed lists in `suspiciousdog/public.py`:
built-in tools and subagents, MCP servers from public directories, plugins from Anthropic's public marketplaces
(checked by the repository they were added from, not by their name), skills that ship with Claude Code or
claude.ai. Your own skills, private plugins, connectors you named yourself, instruction
files, hooks and paths never leave; they are counted as one number, `private_items`. `share.validate()` rejects any
other name, and `tests/test_kit_other.py` checks it with private names that must not come out.

## `sdog classify`

Off unless you run it. It sends, for each reply it labels, the last 300 characters of the agent's message and the
first 300 of your reply to the model you choose: through your own `claude` command (Haiku by default, under your
account's terms; it runs with `--restricted` in an empty folder, so your settings, hooks and CLAUDE.md files stay
out, and Claude Code itself adds your account email as context), to the Anthropic API with your key, or to an
OpenAI-compatible endpoint such as a local model. It
says how many replies and roughly how many tokens before it sends anything, and asks. Labels are kept in
`~/.cache/suspiciousdog/labels.sqlite` so nothing is sent twice. `--validate` sends only the 80 made-up replies in
`suspiciousdog/data/labels.jsonl`.

## What stays on your disk

- `~/.cache/suspiciousdog/kit.sqlite`: what each session loaded and called, so the next run is instant. Delete it
  any time; `--no-cache` skips it.
- `~/.local/share/suspiciousdog/journal.jsonl`: what `sdog prune` changed and what you noted, with how to undo it.
  When a user MCP server is removed, its definition is kept there so `sdog undo` can put it back, and definitions can
  hold tokens: the file is created readable by you only (0600).
- `~/.local/share/suspiciousdog/attic/`: skills and subagents that `prune` put away.
- `~/.cache/suspiciousdog/brief*.json`, `sentinel.json`, `labels.sqlite`: the last brief, the sentinel's state, the
  classifier's labels.
- `~/.local/share/suspiciousdog/attic/settings.json.*`: a copy of `~/.claude/settings.json` from before each
  `sdog hooks on|off`, readable by you only, since settings can hold tokens. Delete them when you like.
- `~/.local/share/suspiciousdog/report.html`: written by `sdog report`. It holds project names and error messages.
  It loads nothing from the network. Don't post it; `sdog share` is the thing for sharing.

`sdog prune` changes your configuration only after you pick the changes, through the agent's own commands
(`claude plugin disable`, `claude mcp remove`, `gemini mcp disable`…) or by moving a folder. `sdog hooks on|off`
adds or removes its own two hooks in `~/.claude/settings.json`, after copying the file to the attic. Nothing else in
SuspiciousDog writes outside the folders above. `sdog mcp` only reads.

## What we do with shared results

They stay public in the repository's issues. A GitHub Action in this repository (`.github/workflows/pack.yml`)
adds up the valid ones and publishes the pack page on GitHub Pages; an issue only counts if `share.validate()`
accepts it, and only the latest open share of each GitHub account counts. No accounts, no tracking, no analytics. To remove your contribution, close or delete your issue,
or ask us to and we'll do it.
