"""The open format: any agent can be sniffed once its sessions are written as these records.

One JSON object per line, in order:

    {"type": "session", "id": "s1", "agent": "my-agent", "project": "shop", "cwd": "/code/shop"}
    {"type": "user", "text": "fix the login page", "ts": "2026-10-20T09:12:00Z"}
    {"type": "tool_call", "name": "run_shell", "category": "shell", "detail": "npm test"}
    {"type": "tool_result", "error": false}
    {"type": "assistant", "text": "Fixed. The form now validates the email."}
    {"type": "interrupt"}

`category` is one of: edit, shell, read, search, web, browser, subagent, ask, plan, skill, other.
Files go in ~/.suspiciousdog/sessions/ (or pass --path).
"""

import json
from datetime import datetime
from pathlib import Path

from ..model import OTHER, Event, Turn

NAME = "jsonl"
STATUS = "stable"
CATEGORIES = {"edit", "shell", "read", "search", "web", "browser", "subagent", "ask", "plan", "skill", "other"}


def default_paths():
    return sorted((Path.home() / ".suspiciousdog" / "sessions").glob("**/*.jsonl"))


def detect(path):
    try:
        with open(path, errors="replace") as f:
            first = json.loads(f.readline())
        return isinstance(first, dict) and first.get("type") == "session"
    except (OSError, ValueError):
        return False


def _when(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def turns(path):
    path = Path(path)
    agent, session, project = NAME, path.stem, path.parent.name
    current = None
    with open(path, errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            kind = r.get("type")
            if kind == "session":
                agent = r.get("agent", agent)
                session = str(r.get("id", session))
                project = r.get("project") or Path(r.get("cwd", "") or project).name
            elif kind == "user" and str(r.get("text", "")).strip():
                if current:
                    current.reply = r["text"].strip()
                    yield current
                current = Turn(agent, session, project, _when(r.get("ts")), r["text"].strip())
            elif current is None:
                continue
            elif kind == "assistant" and str(r.get("text", "")).strip():
                current.texts.append(r["text"])
            elif kind == "tool_call":
                cat = r.get("category") if r.get("category") in CATEGORIES else OTHER
                current.events.append(Event("call", str(r.get("name", "")), cat, str(r.get("detail", ""))))
            elif kind == "tool_result":
                current.events.append(Event("result", error=bool(r.get("error"))))
            elif kind == "interrupt":
                current.interrupted = True
    if current:
        yield current
