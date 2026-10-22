---
description: Sniff your agent sessions for what actually works (SuspiciousDog)
argument-hint: "[sniff|test EXPR|show FACTOR|before-after DATE|demo] [--project NAME]"
allowed-tools: Bash(PYTHONPATH=* python3 -m suspiciousdog:*)
---

Run SuspiciousDog on the user's sessions and explain what it found.

1. Run: `PYTHONPATH="${CLAUDE_PLUGIN_ROOT}" python3 -m suspiciousdog $ARGUMENTS` (no arguments means `sniff`).
2. For each `real` finding, run `show "<factor>" --outcome <outcome>` and read the turns before you explain it.
3. Report briefly: the findings that survived, what the turns show, one change worth trying, and that it can be
   checked later with `before-after`. Say "vibes" for everything else.
4. Mention that `share` sends only counts to the public dataset. Do not run it unless the user says yes.
