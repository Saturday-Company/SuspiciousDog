"""OpenAI Codex CLI: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl

Two layouts exist. "legacy" rollouts log user and agent messages as `event_msg` user_message / agent_message;
"paginated" ones (the current default) log them as `event_msg` item_completed with a UserMessage / AgentMessage
item. Both keep the model-facing `response_item` lines, which is where tool calls and their output live.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

from ..model import BROWSER, EDIT, OTHER, READ, SEARCH, SHELL, SUBAGENT, WEB, Event, Turn

NAME = "codex"
STATUS = "beta"

CATEGORIES = {
    "exec_command": SHELL, "shell": SHELL, "shell_command": SHELL, "local_shell": SHELL, "write_stdin": SHELL,
    "apply_patch": EDIT, "view_image": READ, "web_search": WEB, "tool_search": SEARCH, "spawn_agent": SUBAGENT,
}
EXIT_CODE = re.compile(r"(?:Process exited with code|Exit code:)\s*(-?\d+)")
PATCHED_FILE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.M)


def default_paths():
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    return sorted([*(home / "sessions").glob("**/rollout-*.jsonl"), *(home / "archived_sessions").glob("**/rollout-*.jsonl")])


def detect(path):
    if path.suffix != ".jsonl":
        return False
    try:
        with open(path, errors="replace") as f:
            first = json.loads(f.readline())
        return isinstance(first, dict) and first.get("type") == "session_meta" and "payload" in first
    except (OSError, ValueError):
        return False


def category(name):
    if name in CATEGORIES:
        return CATEGORIES[name]
    if re.search(r"browser|playwright|chrome", name, re.I):
        return BROWSER
    return OTHER


def _when(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _text(content):
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content or [] if isinstance(c, dict))


def _user_message(record, events_mode):
    """The human prompt in this line, if there is one."""
    p = record.get("payload") or {}
    if record.get("type") == "event_msg":
        if p.get("type") == "user_message":
            return p.get("message", "")
        item = p.get("item") or {}
        if p.get("type") == "item_completed" and item.get("type") == "UserMessage":
            return _text(item.get("content"))
    elif not events_mode and record.get("type") == "response_item":
        if p.get("type") == "message" and p.get("role") == "user":
            text = _text(p.get("content"))
            return "" if text.lstrip().startswith("<") else text
    return None


def _call(p):
    kind = p.get("type")
    if kind == "function_call":
        name = p.get("name", "")
        try:
            args = json.loads(p.get("arguments") or "{}")
        except ValueError:
            args = {}
        command = args.get("cmd") or args.get("command") or ""
        if isinstance(command, list):
            command = " ".join(command)
        return Event("call", name, category(name), str(command or args.get("path", "")))
    if kind == "custom_tool_call":
        name = p.get("name", "")
        files = PATCHED_FILE.findall(p.get("input", "") or "")
        return Event("call", name, category(name), files[0] if files else "")
    if kind == "local_shell_call":
        command = (p.get("action") or {}).get("command") or []
        return Event("call", "local_shell", SHELL, " ".join(command) if isinstance(command, list) else str(command))
    if kind == "web_search_call":
        return Event("call", "web_search", WEB, "")
    return None


def _failed(output):
    text = output if isinstance(output, str) else _text(output)
    m = EXIT_CODE.search(text)
    if m:
        return m.group(1) != "0"
    return bool(re.match(r"\s*(error|failed|apply_patch verification failed)", text, re.I))


def turns(path):
    path = Path(path)
    with open(path, errors="replace") as f:
        records = []
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):
                records.append(r)
    events_mode = any(_user_message(r, True) is not None for r in records)
    project, session = path.parent.name, path.stem
    current = None
    for r in records:
        p = r.get("payload") or {}
        if r.get("type") == "session_meta":
            project = Path(p.get("cwd") or project).name
            session = p.get("id") or session
            continue
        prompt = _user_message(r, events_mode)
        if prompt is not None:
            if not prompt.strip():
                continue
            if current:
                current.reply = prompt.strip()
                yield current
            current = Turn(NAME, session, project, _when(r.get("timestamp")), prompt.strip())
            continue
        if current is None:
            continue
        if r.get("type") == "event_msg" and p.get("type") == "turn_aborted" and p.get("reason") == "interrupted":
            current.interrupted = True
        elif r.get("type") == "response_item":
            if p.get("type") == "message" and p.get("role") == "assistant":
                text = _text(p.get("content"))
                if text.strip():
                    current.texts.append(text)
            elif p.get("type") in ("function_call_output", "custom_tool_call_output"):
                current.events.append(Event("result", error=_failed(p.get("output", ""))))
            else:
                call = _call(p)
                if call:
                    current.events.append(call)
    if current:
        yield current
