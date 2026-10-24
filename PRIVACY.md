# Privacy

SuspiciousDog runs on your machine and reads files that are already there. It makes no network calls, with one
exception you have to ask for.

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

## What stays on your disk

- `~/.cache/suspiciousdog/kit.sqlite`: what each session loaded and called, so the next run is instant. Delete it
  any time; `--no-cache` skips it.
- `~/.local/share/suspiciousdog/journal.jsonl`: what `sdog prune` changed and what you noted, with how to undo it.
  When a user MCP server is removed, its definition is kept there so `sdog undo` can put it back, and definitions can
  hold tokens: the file is created readable by you only (0600).
- `~/.local/share/suspiciousdog/attic/`: skills and subagents that `prune` put away.
- `~/.local/share/suspiciousdog/report.html`: written by `sdog report`. It holds project names and error messages.
  It loads nothing from the network. Don't post it; `sdog share` is the thing for sharing.

`sdog prune` changes your configuration only after you pick the changes, through `claude plugin disable` and
`claude mcp remove` or by moving a folder. Nothing else in SuspiciousDog writes outside the folders above.

## What we do with shared results

They stay public in the repository's issues. Saturday Company aggregates them and publishes the aggregate tables
in this repository. No accounts, no tracking, no analytics. To remove your contribution, close or delete your issue,
or ask us to and we'll do it.
