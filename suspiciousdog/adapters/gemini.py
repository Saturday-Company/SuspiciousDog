"""Google Gemini CLI: ~/.gemini/tmp/<project>/chats/session-*.jsonl (and the older session-*.json)

The JSONL is append-only: a message is written again in full whenever it changes, `{"$rewindTo": id}` drops a
message and everything after it, `{"$patch": {...}}` edits in place. We replay it the same way the CLI does.
Tool results come back as synthetic `user` messages made of functionResponse parts; those are not the human.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from ..model import EDIT, OTHER, READ, SEARCH, SHELL, SUBAGENT, WEB, Event, Turn

NAME = "gemini"
STATUS = "beta"

CATEGORIES = {
    "run_shell_command": SHELL, "replace": EDIT, "write_file": EDIT, "edit": EDIT,
    "read_file": READ, "read_many_files": READ, "glob": SEARCH, "search_file_content": SEARCH, "grep": SEARCH,
    "list_directory": SEARCH, "web_fetch": WEB, "google_web_search": WEB, "delegate_to_agent": SUBAGENT,
}
NOT_HUMAN = ("/", "?", "<session_context>", "<hook_context>")


def _home():
    return Path(os.environ.get("GEMINI_CLI_HOME", Path.home())) / ".gemini"


def default_paths():
    chats = (_home() / "tmp").glob("*/chats")
    return sorted(p for c in chats for p in [*c.glob("session-*.jsonl"), *c.glob("session-*.json")])


def detect(path):
    if path.suffix not in (".jsonl", ".json"):
        return False
    try:
        with open(path, errors="replace") as f:
            first = json.loads(f.readline() if path.suffix == ".jsonl" else f.read())
        return isinstance(first, dict) and "sessionId" in first and "projectHash" in first
    except (OSError, ValueError):
        return False


def _when(stamp):
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def _messages(path):
    """The conversation as the CLI would rebuild it."""
    with open(path, errors="replace") as f:
        if path.suffix == ".json":
            data = json.load(f)
            return data, list(data.get("messages") or [])
        meta, messages = {}, {}
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            if "sessionId" in r and "projectHash" in r:
                meta = r
            elif "$rewindTo" in r:
                ids = list(messages)
                if r["$rewindTo"] in ids:
                    for gone in ids[ids.index(r["$rewindTo"]):]:
                        del messages[gone]
            elif "$patch" in r:
                patch = r["$patch"] or {}
                for gone in patch.get("removeIds") or []:
                    messages.pop(gone, None)
                if patch.get("id") in messages:
                    messages[patch["id"]].update({k: v for k, v in patch.items() if k in ("content", "toolCalls")})
                if patch.get("orderIds"):
                    order = [i for i in patch["orderIds"] if i in messages]
                    messages = {i: messages[i] for i in order + [i for i in messages if i not in order]}
            elif "id" in r and "type" in r:
                messages[r["id"]] = r
        return meta, list(messages.values())


def _human_text(content):
    """The typed text of a user message, or None when it only carries tool responses."""
    if isinstance(content, str):
        return content
    parts = [p for p in content or [] if isinstance(p, dict)]
    if parts and all("functionResponse" in p for p in parts):
        return None
    return " ".join(p.get("text", "") for p in parts if "text" in p)


def _project(meta, path):
    root = path.parent.parent / ".project_root"
    try:
        return Path(root.read_text().strip()).name
    except OSError:
        return path.parent.parent.name or str(meta.get("projectHash", ""))[:8]


def turns(path):
    path = Path(path)
    meta, messages = _messages(path)
    session, project = meta.get("sessionId", path.stem), _project(meta, path)
    current = None
    for m in messages:
        kind = m.get("type")
        if kind == "user":
            text = _human_text(m.get("content"))
            if text is None or not text.strip() or text.lstrip().startswith(NOT_HUMAN):
                continue
            if current:
                current.reply = text.strip()
                yield current
            current = Turn(NAME, session, project, _when(m.get("timestamp")), text.strip())
        elif kind == "info" and current and "cancel" in str(m.get("content", "")).lower():
            current.interrupted = True
        elif kind == "gemini" and current:
            for call in m.get("toolCalls") or []:
                name = call.get("name", "")
                args = call.get("args") or {}
                detail = args.get("file_path") or args.get("command") or args.get("path") or ""
                current.events.append(Event("call", name, CATEGORIES.get(name, OTHER), str(detail)))
                if call.get("status") == "cancelled":
                    current.interrupted = True
                elif call.get("status") in ("success", "error"):
                    current.events.append(Event("result", error=call.get("status") == "error"))
            content = m.get("content")
            text = content if isinstance(content, str) else _human_text(content) or ""
            if text.strip():
                current.texts.append(text)
    if current:
        yield current
