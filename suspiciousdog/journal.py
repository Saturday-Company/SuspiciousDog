"""The journal: every change made through SuspiciousDog, or noted by you, with how to undo it.

One JSON object per line in ~/.local/share/suspiciousdog/journal.jsonl. Weeks later each entry is a before/after:
the moment is exact, nobody has to remember it.
"""

import json
import os
from datetime import datetime
from pathlib import Path


def home():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "suspiciousdog"


def path():
    return home() / "journal.jsonl"


def read():
    try:
        lines = path().read_text().splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def write(action, what, key="", undo=None, **extra):
    """Append an entry. The file is private: an MCP server's definition can carry a token."""
    entries = read()
    entry = {"id": max((e.get("id", 0) for e in entries), default=0) + 1,
             "at": datetime.now().astimezone().isoformat(timespec="seconds"),
             "action": action, "what": what, "key": key, "undo": undo, **extra}
    path().parent.mkdir(parents=True, exist_ok=True)
    with open(path(), "a") as f:
        f.write(json.dumps(entry) + "\n")
    os.chmod(path(), 0o600)
    return entry


def undone():
    """Ids of entries that have been undone."""
    return {e.get("undoes") for e in read() if e.get("action") == "undo"}


def when(entry):
    return datetime.fromisoformat(entry["at"])
