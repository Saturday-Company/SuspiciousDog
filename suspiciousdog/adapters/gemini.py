"""Google Gemini CLI: ~/.gemini/tmp/<project>/chats/session-*.jsonl (and the older session-*.json)

The JSONL is append-only: a message is written again in full whenever it changes, `{"$rewindTo": id}` drops a
message and everything after it, `{"$patch": {...}}` edits in place. We replay it the same way the CLI does.
Tool results come back as synthetic `user` messages made of functionResponse parts; those are not the human.
"""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from ..failures import classify
from ..model import EDIT, OTHER, READ, SEARCH, SHELL, SKILL, SUBAGENT, WEB, Event, Turn, blank_kit, home_path

NAME = "gemini"
STATUS = "beta"

CATEGORIES = {
    "run_shell_command": SHELL, "replace": EDIT, "write_file": EDIT, "edit": EDIT,
    "read_file": READ, "read_many_files": READ, "glob": SEARCH, "search_file_content": SEARCH, "grep": SEARCH,
    "list_directory": SEARCH, "web_fetch": WEB, "google_web_search": WEB, "delegate_to_agent": SUBAGENT,
    "grep_search": SEARCH, "invoke_agent": SUBAGENT, "activate_skill": SKILL,
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


# --- the kit: what a session loaded and used ---

CONTEXT = re.compile(r"--- Context from: (.+?) ---\n(.*?)\n--- End of Context from: \1 ---", re.S)
SERVER_NOTE = re.compile(r"The following are instructions provided by the tool server '([^']+)':")
DISPLAY = re.compile(r"^(.+?) \((.+?) MCP Server\)$")


def _key(call):
    """kit key and tool name for one tool call."""
    name, args = call.get("name", ""), call.get("args") or {}
    m = DISPLAY.match(str(call.get("displayName") or ""))
    if m:
        return "mcp:" + m.group(2), m.group(1)
    if name.startswith("mcp_"):
        server, _, tool = name[4:].partition("_")        # ambiguous if the server has an underscore
        return "mcp:" + server, tool
    if name == "activate_skill":
        return "skill:" + str(args.get("name") or "?"), name
    if name in ("invoke_agent", "delegate_to_agent"):
        return "subagent:" + str(args.get("agent_name") or args.get("name") or "?"), name
    return "tool:" + name, name


def _error_text(call):
    for part in call.get("result") or []:
        response = (part.get("functionResponse") or {}).get("response") if isinstance(part, dict) else None
        if isinstance(response, dict) and response.get("error"):
            return str(response["error"])
    return str(call.get("resultDisplay") or "")


def kit(path):
    """What one chat loaded (GEMINI.md files, MCP server instructions) and used. Skills and servers that were
    available but never used aren't recorded."""
    path = Path(path)
    meta, messages = _messages(path)
    k = blank_kit(NAME, meta.get("sessionId", path.stem), _project(meta, path))
    k["start"] = meta.get("startTime")
    k["end"] = meta.get("lastUpdated") or k["start"]

    def bump(field, key, n=1):
        k[field][key] = k[field].get(key, 0) + n

    for m in messages:
        kind = m.get("type")
        if kind == "user":
            text = _human_text(m.get("content")) or ""
            if "<session_context>" not in text:
                continue
            bump("attachments", "session_context")
            for file, body in CONTEXT.findall(text):
                key = "instructions:" + home_path(file)
                k["loaded"][key] = len(body)
                k["digests"][key] = [hashlib.sha1(body.encode()).hexdigest()[:12], len(body)]
            notes = list(SERVER_NOTE.finditer(text))
            for i, note in enumerate(notes):
                end = notes[i + 1].start() if i + 1 < len(notes) else text.find("</project_context>", note.end())
                k["loaded"]["mcp:" + note.group(1)] = (end if end > 0 else len(text)) - note.start()
        elif kind == "gemini":
            if m.get("model"):
                bump("models", m["model"])
            tokens = m.get("tokens") or {}
            if k["base_tokens"] is None and tokens.get("input"):
                k["base_tokens"] = int(tokens["input"])
            for call in m.get("toolCalls") or []:
                key, tool = _key(call)
                bump("used", key)
                k["tools"].setdefault(key, {}).setdefault(tool, [0, 0])[0] += 1
                if call.get("status") == "error":
                    bump("errors", key)
                    k["tools"][key][tool][1] += 1
                    text = _error_text(call)
                    why = classify(text)
                    kinds = k["error_kinds"].setdefault(key, {})
                    kinds[why] = kinds.get(why, 0) + 1
                    samples = k["samples"].setdefault(key, [])
                    if len(samples) < 5 and (kinds[why] == 1 or len(samples) < 2):
                        samples.append([why, " ".join(text.split())[:160]])
    for key in k["used"]:
        if not key.startswith("tool:"):
            k["loaded"].setdefault(key, 0)
    return k


def kit_stamp(path):
    st = Path(path).stat()
    return f"{st.st_mtime_ns}:{st.st_size}"


def config():
    """MCP servers and extensions on disk, and the commands that switch them off (both have an undo)."""
    home = _home()
    found = {}

    def read(p):
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return {}
    for name in (read(home / "settings.json").get("mcpServers") or {}):
        found["mcp:" + name] = {"source": "Gemini CLI MCP server (~/.gemini/settings.json)",
                                "remove": f"gemini mcp disable {name}",
                                "fix": {"type": "run", "bin": "gemini", "argv": ["mcp", "disable", name],
                                        "undo": ["mcp", "enable", name]}}
    for root in (home / "skills", Path.home() / ".agents" / "skills"):
        for skill in sorted(root.glob("*/SKILL.md")):
            name = skill.parent.name
            found.setdefault("skill:" + name, {"source": f"Gemini CLI skill {home_path(skill.parent)}",
                                               "remove": f"gemini skills disable {name}",
                                               "fix": {"type": "run", "bin": "gemini", "argv": ["skills", "disable", name],
                                                       "undo": ["skills", "enable", name]}})
    for manifest in sorted((home / "extensions").glob("*/gemini-extension.json")):
        ext = read(manifest).get("name") or manifest.parent.name
        found["plugin:" + ext] = {"source": f"Gemini CLI extension {ext}", "remove": f"gemini extensions disable {ext}",
                                  "fix": {"type": "run", "bin": "gemini", "argv": ["extensions", "disable", ext],
                                          "undo": ["extensions", "enable", ext]}}
        for name in read(manifest).get("mcpServers") or {}:
            found.setdefault("mcp:" + name, {"source": f"Gemini CLI extension {ext}",
                                             "remove": f"gemini extensions disable {ext}", "plugin": ext})
    return found
