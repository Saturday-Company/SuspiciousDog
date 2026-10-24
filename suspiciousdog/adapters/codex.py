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

from ..failures import classify
from ..model import BROWSER, EDIT, OTHER, READ, SEARCH, SHELL, SUBAGENT, WEB, Event, Turn, blank_kit, home_path

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


def _name(p):
    """The tool's full name: MCP tools carry their server in a namespace, "mcp__github" + "list_issues"."""
    name, ns = p.get("name", ""), p.get("namespace") or ""
    return f"{ns.rstrip('_')}__{name}" if ns else name


def _call(p):
    kind = p.get("type")
    if kind == "function_call":
        name = _name(p)
        try:
            args = json.loads(p.get("arguments") or "{}")
        except ValueError:
            args = {}
        args = args if isinstance(args, dict) else {}
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


# --- the kit: what a session loaded and used ---

SKILL_LINE = re.compile(r"^- ([^:\s]+): .*\(file: ([^)]+)\)\s*$", re.M)
SKILL_TAG = re.compile(r"<skill>\s*<name>([^<]+)</name>")
SKILL_FILE = re.compile(r"/skills/([^/\s]+)/SKILL\.md")


def _agents_md(text, cwd):
    """{key: text} for the AGENTS.md block: the global file and the project's, when both are there."""
    body = text.split("<INSTRUCTIONS>", 1)[-1].rsplit("</INSTRUCTIONS>", 1)[0].strip("\n")
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    parts = body.split("\n\n--- project-doc ---\n\n")
    if len(parts) == 2:
        return {home_path(home / "AGENTS.md"): parts[0], home_path(Path(cwd) / "AGENTS.md"): parts[1]}
    return {home_path(Path(cwd) / "AGENTS.md"): body}


def kit(path):
    """What one rollout loaded and used. Codex doesn't record which MCP servers were available, only the used ones."""
    import hashlib
    path = Path(path)
    k = blank_kit(NAME, path.stem, path.parent.name)
    calls, cwd = {}, ""

    def bump(field, key, n=1):
        k[field][key] = k[field].get(key, 0) + n

    def fail(key, name, text):
        bump("errors", key)
        why = classify(text)
        kinds = k["error_kinds"].setdefault(key, {})
        kinds[why] = kinds.get(why, 0) + 1
        k["tools"].setdefault(key, {}).setdefault(name, [0, 0])[1] += 1
        samples = k["samples"].setdefault(key, [])
        if len(samples) < 5 and (kinds[why] == 1 or len(samples) < 2):
            samples.append([why, " ".join(str(text).split())[:160]])

    with open(path, errors="replace") as f:
        for line in f:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if not isinstance(r, dict):
                continue
            p = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            kind, stamp = r.get("type"), r.get("timestamp")
            if stamp:
                k["start"] = k["start"] or stamp
                k["end"] = stamp
            if kind == "session_meta":
                cwd = p.get("cwd") or cwd
                k["project"] = home_path(cwd) if cwd else k["project"]
                k["session"] = p.get("id") or k["session"]
                k["version"] = p.get("cli_version")
                bump("attachments", "session_meta")
            elif kind == "turn_context" and p.get("model"):
                bump("models", p["model"])
            elif kind == "response_item" and p.get("type") == "message":
                text = _text(p.get("content"))
                if "<skills_instructions>" in text:
                    bump("attachments", "skills_instructions")
                    for m in SKILL_LINE.finditer(text):
                        k["loaded"]["skill:" + m.group(1)] = len(m.group(0)) + 1
                elif text.startswith("# AGENTS.md instructions"):
                    bump("attachments", "agents_md")
                    for file, body in _agents_md(text, cwd).items():
                        key = "instructions:" + file
                        k["loaded"][key] = len(body)
                        k["digests"][key] = [hashlib.sha1(body.encode()).hexdigest()[:12], len(body)]
                elif p.get("role") == "user":
                    for name in SKILL_TAG.findall(text):
                        bump("used", "skill:" + name.strip())
            elif kind == "response_item" and p.get("type") in ("function_call", "custom_tool_call", "local_shell_call"):
                call = _call(p)
                if not call:
                    continue
                if call.tool.startswith("mcp__"):
                    server, _, tool = call.tool[5:].partition("__")
                    key = "mcp:" + server
                elif (p.get("namespace") or "") == "skills":
                    try:
                        args = json.loads(p.get("arguments") or "{}")
                    except ValueError:
                        args = {}
                    args = args if isinstance(args, dict) else {}
                    key, tool = "skill:" + str(args.get("name") or args.get("skill") or "?"), call.tool
                else:
                    m = SKILL_FILE.search(call.detail)
                    key, tool = ("skill:" + m.group(1), call.tool) if m else ("tool:" + call.tool, call.tool)
                calls[p.get("call_id")] = (key, tool)
                bump("used", key)
                k["tools"].setdefault(key, {}).setdefault(tool, [0, 0])[0] += 1
            elif kind == "event_msg" and p.get("type") == "item_completed":
                item = p.get("item") or {}
                if item.get("id") in calls and (item.get("status") == "failed" or
                                                (item.get("result") or {}).get("isError")):
                    key, tool = calls.pop(item["id"])
                    error = item.get("error") or item.get("result") or {}
                    fail(key, tool, error.get("message") if isinstance(error, dict) else error)
            elif kind == "event_msg" and p.get("type") == "mcp_tool_call_end":
                result = p.get("result") or {}
                if p.get("call_id") in calls and "Err" in result:
                    key, tool = calls.pop(p["call_id"])
                    fail(key, tool, result["Err"])
            elif kind == "event_msg" and p.get("type") == "token_count" and k["base_tokens"] is None:
                last = (p.get("info") or {}).get("last_token_usage") or {}
                if last.get("input_tokens"):
                    k["base_tokens"] = int(last["input_tokens"])
    for key in k["used"]:
        if not key.startswith("tool:"):
            k["loaded"].setdefault(key, 0)
    return k


def kit_stamp(path):
    st = Path(path).stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


def config():
    """MCP servers in config.toml, and how to remove each. Read with tomllib where there is one (Python 3.11+)."""
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    try:
        import tomllib
        data = tomllib.loads((home / "config.toml").read_text())
    except (ImportError, OSError, ValueError):
        data = {}
    found = {}
    for root in (home / "skills", Path.home() / ".agents" / "skills"):
        for skill in sorted(root.glob("*/SKILL.md")):
            name = skill.parent.name
            if name.startswith("."):
                continue        # .system: bundled with Codex
            found.setdefault("skill:" + name, {
                "source": f"Codex skill {home_path(skill.parent)}",
                "remove": f"add [[skills.config]] name = \"{name}\" enabled = false to ~/.codex/config.toml"})
    for name, d in (data.get("mcp_servers") or {}).items():
        off = isinstance(d, dict) and d.get("enabled") is False
        found["mcp:" + re.sub(r"[^A-Za-z0-9_-]", "_", name)] = {
            "source": "Codex MCP server (~/.codex/config.toml)" + (", disabled" if off else ""),
            "remove": f"set enabled = false under [mcp_servers.{name}] in ~/.codex/config.toml, or `codex mcp remove {name}`"}
    return found
