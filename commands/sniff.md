---
description: Sniff your agent sessions for what actually works (SuspiciousDog)
argument-hint: "[checkup|kit [NAME]|timeline|prune|sniff|show FACTOR|before-after DATE|report|doctor] [--project NAME]"
allowed-tools: Bash(PYTHONPATH=* python3 -m suspiciousdog:*)
---

Run SuspiciousDog on the user's sessions and explain what it found.

1. Run: `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m suspiciousdog $ARGUMENTS` (no arguments means the checkup).
2. For each `real` finding, run `show "<factor>" --outcome <outcome>` and read the turns before you explain it.
3. Report briefly: the findings that survived, what the turns show, one change worth trying, and that it can be
   checked later with `before-after`. Say "vibes" for everything else.
4. For `prune`, list the proposals and ask which to apply; run `prune --apply N` only with the user's yes.
5. For `kit`, report the ballast, the misused items and the tokens they cost; give the removal hints but never
   apply them.
6. Mention that `share` sends only counts to the public dataset. Do not run it unless the user says yes.
