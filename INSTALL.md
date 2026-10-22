# Install

SuspiciousDog is a Python 3.10+ command with no dependencies. Install it once, then use it from any agent.

```bash
pipx install git+https://github.com/Saturday-Company/SuspiciousDog
# or: pip install --user git+https://github.com/Saturday-Company/SuspiciousDog
sdog agents     # what it found on this machine
```

Without installing: `git clone https://github.com/Saturday-Company/SuspiciousDog && cd SuspiciousDog && python3 -m suspiciousdog`.

## Claude Code

As a plugin (adds `/suspiciousdog:sniff` and a skill Claude uses when you ask whether something helps):

```bash
claude plugin marketplace add Saturday-Company/SuspiciousDog
claude plugin install suspiciousdog@suspiciousdog
```

Inside a session the same is `/plugin marketplace add Saturday-Company/SuspiciousDog` and
`/plugin install suspiciousdog@suspiciousdog`. The plugin carries its own copy of the code, so pipx is optional.

Sessions are read from `~/.claude/projects` (or `$CLAUDE_CONFIG_DIR/projects`).

## Codex CLI

Install with pipx, then copy `AGENTS.md` into your project (or append it to yours) so Codex knows how to run and
read it. To use it as a skill, copy `skills/suspiciousdog/` into your Codex skills folder.

Sessions are read from `~/.codex/sessions` and `~/.codex/archived_sessions` (or `$CODEX_HOME`). Compressed
rollouts (`.jsonl.zst`) are not read yet.

## Gemini CLI

Install with pipx, then add the contents of `AGENTS.md` to your `GEMINI.md`, or copy `skills/suspiciousdog/` into
your Gemini skills folder.

Sessions are read from `~/.gemini/tmp/*/chats/` (or `$GEMINI_CLI_HOME/.gemini`).

## Aider

Install with pipx and run `sdog` inside the repository: it reads `.aider.chat.history.md` from the current folder
and its parents, or `$AIDER_CHAT_HISTORY_FILE`. Aider records no per-message times and no exit codes, so the
night and error factors are rough for it.

## Cursor, OpenCode, Windsurf, Cline, Copilot and the rest

Install with pipx and add `AGENTS.md` to your rules. Their sessions aren't read directly yet: convert them to the
open format (`sdog format` prints it, six kinds of JSON lines) and run `sdog sniff --path your-folder`. Put them in
`~/.suspiciousdog/sessions/` and they're picked up automatically. A reader for your agent is a welcome PR: one file
in `suspiciousdog/adapters/`.
