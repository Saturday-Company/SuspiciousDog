"""Claude Code: ~/.claude/projects/<project>/<session>.jsonl"""

import json
import os
from datetime import datetime
from pathlib import Path

from ..model import ASK, BROWSER, EDIT, OTHER, PLAN, READ, SEARCH, SHELL, SKILL, SUBAGENT, WEB, Event, Turn

NAME = "claude-code"
STATUS = "stable"

CATEGORIES = {
    "Write": EDIT, "Edit": EDIT, "MultiEdit": EDIT, "NotebookEdit": EDIT,
    "Bash": SHELL, "Read": READ, "Grep": SEARCH, "Glob": SEARCH, "LS": SEARCH,
    "WebSearch": WEB, "WebFetch": WEB, "Agent": SUBAGENT, "Task": SUBAGENT,
    "AskUserQuestion": ASK, "ExitPlanMode": PLAN, "EnterPlanMode": PLAN, "Skill": SKILL,
}
BROWSER_PREFIXES = ("mcp__claude-in-chrome", "mcp__chrome-devtools", "mcp__Claude_Browser", "mcp__playwright",
                    "mcp__remote-devices__Claude_Browser")


def default_paths():
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"
    return sorted(root.glob("*/*.jsonl"))


def detect(path):
    """Claude Code lines carry a `message` object with a role; other formats don't."""
    if path.suffix != ".jsonl":
        return False
    try:
        with open(path, errors="replace") as f:
            for _, line in zip(range(20), f):
                d = json.loads(line)
                if isinstance(d, dict) and isinstance(d.get("message"), dict) and "role" in d["message"]:
                    return True
    except (OSError, ValueError):
        return False
    return False


def category(name):
    if name in CATEGORIES:
        return CATEGORIES[name]
    if name.startswith(BROWSER_PREFIXES):
        return BROWSER
    return OTHER


def _user_text(content):
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def _when(stamp):
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
    except (AttributeError, ValueError):
        return None


def turns(path):
    path = Path(path)
    current = None
    with open(path, errors="replace") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("isSidechain"):
                continue
            message = d.get("message") if isinstance(d.get("message"), dict) else {}
            content = message.get("content")
            if d.get("type") == "user" and not d.get("isMeta"):
                text = _user_text(content).strip()
                if text.startswith("[Request interrupted"):
                    if current:
                        current.interrupted = True
                    continue
                if text and not text.startswith("<") and "This session is being continued" not in text:
                    if current:
                        current.reply = text
                        yield current
                    current = Turn(NAME, path.stem, path.parent.name, _when(d.get("timestamp")), text)
                    continue
                for b in content if isinstance(content, list) else []:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and current:
                        current.events.append(Event("result", error=bool(b.get("is_error"))))
            elif d.get("type") == "assistant" and current:
                for b in content or []:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "tool_use":
                        args = b.get("input") or {}
                        detail = args.get("file_path") or args.get("command") or args.get("subagent_type") or ""
                        name = b.get("name", "")
                        current.events.append(Event("call", name, category(name), str(detail)))
                    elif b.get("type") == "text" and b.get("text", "").strip():
                        current.texts.append(b["text"])
    if current:
        yield current
