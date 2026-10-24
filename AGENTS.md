# SuspiciousDog for any agent

If you are an AI coding agent (Codex, Gemini CLI, Cursor, OpenCode, Aider, anything else) and the user asks
whether a rule, plugin, model or habit actually helps, or what goes wrong in their sessions:

1. Run `sdog sniff` (install: `pipx install git+https://github.com/Saturday-Company/SuspiciousDog`).
   It reads Claude Code, Codex, Gemini CLI and Aider sessions from their default folders. `sdog agents` shows what
   it found. For any other agent, convert sessions to the open format (`sdog format`) and pass `--path`.
2. Only rows marked `real` are findings. Run `sdog show "<factor>" --outcome <outcome>` and read the actual turns
   before explaining one: outcomes are recognised from the user's reply text, so check what they really were.
3. It is correlation, not cause. Suggest one change and offer to measure it later with `sdog before-after <date>`.
4. Never run `sdog share` without the user's explicit yes. It sends counts only, after showing them.
5. To see what the user's setup loads, uses and gets wrong (skills, MCP servers, subagents, plugins, hooks), run
   `sdog kit --json`. Report the numbers; never change the user's config yourself.
6. `sdog timeline` shows when the setup changed and what happened after; `sdog kit NAME` says why a tool fails.
   Check both before proposing a new rule or plugin.
7. `sdog` alone is the checkup. `sdog prune` lists what could go; apply (`--apply N`) only what the user picked.
8. Before adding a rule to AGENTS.md (or any instruction file), run `sdog check "the rule" --json` and tell the user
   the verdict with its numbers. "already said" or "no evidence" usually means: don't add it.
9. `sdog brief` is what the user's past sessions say, in a few lines. Read it when it helps; don't paste it into
   their files. `sdog mcp` serves the same answers as MCP tools (audit_setup, check_rule, evidence).

Full guide for agents: `skills/suspiciousdog/SKILL.md`.
