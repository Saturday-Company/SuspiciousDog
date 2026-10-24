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

For the kit (what the agent loaded, used and broke), three optional additions:

    {"type": "loaded", "key": "skill:pdf", "chars": 240}
    {"type": "tool_call", "name": "list_issues", "item": "mcp:github"}
    {"type": "tool_result", "error": true, "text": "401 Unauthorized"}
    {"type": "usage", "input_tokens": 41000}

`key` and `item` are a kind and a name: skill, mcp, subagent, plugin, instructions (a file path), hook. A call
without `item` counts as the tool `name`. `usage` is the context at the first call, before the user typed anything.
"""

import json
from datetime import datetime
from pathlib import Path

from ..failures import classify
from ..model import OTHER, Event, Turn, blank_kit

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


def kit(path):
    path = Path(path)
    k = blank_kit(NAME, path.stem, path.parent.name)
    last = None

    def bump(field, key, n=1):
        k[field][key] = k[field].get(key, 0) + n
    with open(path, errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            kind = r.get("type")
            if r.get("ts"):
                k["start"] = k["start"] or r["ts"]
                k["end"] = r["ts"]
            if kind == "session":
                k["agent"] = r.get("agent", k["agent"])
                k["session"] = str(r.get("id", k["session"]))
                k["project"] = r.get("cwd") or r.get("project") or k["project"]
            elif kind == "loaded" and ":" in str(r.get("key", "")):
                k["loaded"][r["key"]] = max(k["loaded"].get(r["key"], 0), int(r.get("chars") or 0))
            elif kind == "usage" and k["base_tokens"] is None and r.get("input_tokens"):
                k["base_tokens"] = int(r["input_tokens"])
            elif kind == "tool_call":
                name = str(r.get("name", ""))
                last = (str(r.get("item") or "tool:" + name), name)
                bump("used", last[0])
                k["tools"].setdefault(last[0], {}).setdefault(name, [0, 0])[0] += 1
            elif kind == "tool_result" and r.get("error") and last:
                key, name = last
                bump("errors", key)
                k["tools"][key][name][1] += 1
                why = classify(str(r.get("text", "")))
                kinds = k["error_kinds"].setdefault(key, {})
                kinds[why] = kinds.get(why, 0) + 1
    for key in k["used"]:
        if not key.startswith("tool:"):
            k["loaded"].setdefault(key, 0)
    return k


def kit_stamp(path):
    st = Path(path).stat()
    return f"{st.st_mtime_ns}:{st.st_size}"
