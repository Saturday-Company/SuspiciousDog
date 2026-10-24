"""Claude Code: ~/.claude/projects/<project>/<session>.jsonl"""

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from ..failures import classify
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
    current, counted = None, set()
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
                current.ended = _when(d.get("timestamp")) or current.ended
                usage = message.get("usage")
                if isinstance(usage, dict) and message.get("id") not in counted:
                    counted.add(message.get("id"))
                    current.tokens += int(usage.get("output_tokens") or 0)
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


# --- the kit: what each session loaded into the context, and what it used ---

LISTED = re.compile(r"^- (\S+?)(?::\s|:?$)")
MCP_TOOL = re.compile(r"^mcp__(.+?)__")
DENIED = "The user doesn't want to proceed with this tool use"
KNOWN_ATTACHMENTS = {"skill_listing", "mcp_instructions_delta", "agent_listing_delta", "instructions", "nested_memory",
                     "deferred_tools_delta", "hook_success", "hook_blocking_error", "hook_additional_context",
                     "hook_system_message", "hook_non_blocking_error", "invoked_skills"}


def server(name):
    """The key a server has in its tool names: "claude.ai Gamma" -> "claude_ai_Gamma"."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", name)


def _listing(text):
    """{name: characters} from a "- name: description" listing."""
    out, name = {}, None
    for line in (text or "").split("\n"):
        m = LISTED.match(line)
        if m:
            name = m.group(1)
            out[name] = out.get(name, 0) + len(line) + 1
        elif name:
            out[name] += len(line) + 1
    return out


def _home(path):
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def _short(command):
    """A hook's command, short enough to name it: "piano-letture.py", "127.0.0.1:4747/hook"."""
    if command.startswith(("http://", "https://")):
        rest = command.split("://", 1)[1]
        return rest.split("/")[0] + "/" + rest.rstrip("/").split("/")[-1]
    paths = [w for w in command.split() if "/" in w]
    return (paths[-1].rstrip("/").split("/")[-1] if paths else command)[:40]


def _key(name, args):
    if name == "Skill":
        return "skill:" + str(args.get("skill") or args.get("command") or "?").lstrip("/")
    if name in ("Agent", "Task"):
        return "subagent:" + str(args.get("subagent_type") or "general-purpose")
    m = MCP_TOOL.match(name)
    if m:
        return "mcp:" + m.group(1)
    return "tool:" + name


def kit(path):
    """What one session loaded (characters per item), used (calls), and got wrong. Subagents' calls count too."""
    path = Path(path)
    k = {"agent": NAME, "session": path.stem, "project": path.parent.name, "start": None, "end": None,
         "version": None, "base_tokens": None, "models": {}, "loaded": {}, "used": {}, "errors": {},
         "retries": {}, "denied": {}, "samples": {}, "attachments": {}, "subagent_files": 0,
         "digests": {}, "subagent_models": {}, "tools": {}, "error_kinds": {}}

    def load(key, chars):
        k["loaded"][key] = max(k["loaded"].get(key, 0), chars)

    def bump(field, key, n=1):
        k[field][key] = k[field].get(key, 0) + n

    def instructions(file, text):
        key = "instructions:" + _home(file)
        load(key, len(text))
        k["digests"][key] = [hashlib.sha1(text.encode()).hexdigest()[:12], len(text)]

    deferred = {}   # MCP tool names are listed again after every reconnect: count each once

    def read(file, main):
        ids, failed, model_seen = {}, None, main
        with open(file, errors="replace") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                if main and d.get("timestamp"):
                    k["start"] = k["start"] or d["timestamp"]
                    k["end"] = d["timestamp"]
                if main and d.get("version"):
                    k["version"] = d["version"]
                if main and d.get("cwd") and k["project"] == path.parent.name:
                    k["project"] = _home(d["cwd"])
                kind = d.get("type")
                if kind == "attachment" and main:
                    a = d.get("attachment") if isinstance(d.get("attachment"), dict) else {}
                    t = a.get("type")
                    bump("attachments", str(t))
                    if t == "skill_listing":
                        for name, chars in _listing(a.get("content")).items():
                            load("skill:" + name, chars)
                    elif t == "agent_listing_delta":
                        listed = _listing("\n".join(a.get("addedLines") or []))
                        for name in a.get("addedTypes") or []:
                            load("subagent:" + name, listed.get(name, 0))
                    elif t == "mcp_instructions_delta":
                        for name, block in zip(a.get("addedNames") or [], a.get("addedBlocks") or []):
                            load("mcp:" + server(name), len(str(block)))
                    elif t == "deferred_tools_delta":
                        for name in a.get("addedNames") or []:
                            m = MCP_TOOL.match(name)
                            if m:
                                deferred.setdefault("mcp:" + m.group(1), set()).add(name)
                    elif t == "instructions":
                        for fl in a.get("files") or []:
                            if isinstance(fl, dict) and fl.get("path"):
                                instructions(fl["path"], str(fl.get("content") or ""))
                    elif t == "nested_memory" and a.get("path"):
                        content = a.get("content")
                        text = content.get("content") if isinstance(content, dict) else content
                        instructions(a["path"], str(text or ""))
                    elif str(t).startswith("hook_"):
                        command = a.get("command")
                        key = "hook:" + (f"{a.get('hookEvent') or '?'} {_short(str(command))}" if command
                                         else str(a.get("hookName") or a.get("hookEvent") or "?"))
                        load(key, len(str(a.get("content") or "")))
                        bump("used", key)
                        if t == "hook_blocking_error":
                            bump("errors", key)
                    continue
                message = d.get("message") if isinstance(d.get("message"), dict) else {}
                content = message.get("content")
                if kind == "assistant":
                    if main and k["base_tokens"] is None and isinstance(message.get("usage"), dict):
                        u = message["usage"]
                        k["base_tokens"] = sum(int(u.get(f) or 0) for f in
                                               ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
                    model = message.get("model")
                    if main and model and not str(model).startswith("<"):
                        bump("models", model)
                    if not model_seen and model and not str(model).startswith("<"):
                        bump("subagent_models", model)
                        model_seen = True
                    for b in content if isinstance(content, list) else []:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            name = b.get("name", "")
                            key = _key(name, b.get("input") if isinstance(b.get("input"), dict) else {})
                            ids[b.get("id")] = key, name
                            bump("used", key)
                            k["tools"].setdefault(key, {}).setdefault(name.split("__")[-1], [0, 0])[0] += 1
                            if failed == name:
                                bump("retries", key)
                            failed = None
                elif kind == "user":
                    if main and isinstance(content, str):
                        for name in re.findall(r"<command-name>/?([^<\s]+)</command-name>", content):
                            if "skill:" + name in k["loaded"]:
                                bump("used", "skill:" + name)
                    for b in content if isinstance(content, list) else []:
                        if not (isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in ids):
                            continue
                        key, name = ids[b["tool_use_id"]]
                        text = b.get("content")
                        text = text if isinstance(text, str) else " ".join(
                            x.get("text", "") for x in text or [] if isinstance(x, dict))
                        if DENIED in text:
                            bump("denied", key)
                        elif b.get("is_error"):
                            bump("errors", key)
                            failed = name
                            k["tools"].setdefault(key, {}).setdefault(name.split("__")[-1], [0, 0])[1] += 1
                            why = classify(text)
                            kinds = k["error_kinds"].setdefault(key, {})
                            kinds[why] = kinds.get(why, 0) + 1
                            samples = k["samples"].setdefault(key, [])
                            if len(samples) < 5 and (kinds[why] == 1 or len(samples) < 2):
                                samples.append([why, " ".join(text.split())[:160]])

    read(path, True)
    for sub in sorted(path.with_suffix("").glob("subagents/*.jsonl")):
        k["subagent_files"] += 1
        try:
            read(sub, False)
        except OSError:
            pass
    for key, names in deferred.items():
        k["loaded"][key] = k["loaded"].get(key, 0) + sum(len(n) + 1 for n in names)
    for key in k["used"]:
        if not key.startswith("tool:"):
            k["loaded"].setdefault(key, 0)
    return k


def kit_stamp(path):
    """Changes whenever the session or one of its subagents does: the cache key."""
    path = Path(path)
    parts = [path] + sorted(path.with_suffix("").glob("subagents/*.jsonl"))
    return ";".join(f"{p.stat().st_mtime_ns}:{p.stat().st_size}" for p in parts)


def config():
    """What is installed on disk, and how each thing would be removed. {key: (source, how to remove)}."""
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    found = {}

    def read_json(p):
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return {}
    plugins = read_json(root / "plugins" / "installed_plugins.json").get("plugins") or {}
    enabled = read_json(root / "settings.json").get("enabledPlugins") or {}
    for full, installs in plugins.items():
        plugin = full.split("@")[0]
        when = min((i.get("installedAt", "") for i in installs if isinstance(i, dict)), default="")
        on = enabled.get(full, True)
        user = any(isinstance(i, dict) and i.get("scope", "user") == "user" for i in installs)
        found["plugin:" + plugin] = {"source": f"plugin {full}, installed {when[:10]}" + ("" if on else ", disabled"),
                                     "remove": f"claude plugin disable {full}", "installed": when}
        if on and user:
            found["plugin:" + plugin]["fix"] = {"type": "run", "argv": ["plugin", "disable", full, "-s", "user"],
                                                "undo": ["plugin", "enable", full, "-s", "user"]}
    for p in sorted((root / "skills").glob("*/SKILL.md")):
        found["skill:" + p.parent.name] = {"source": f"user skill {_home(str(p.parent))}",
                                          "remove": f"move {_home(str(p.parent))} into the project that uses it",
                                          "fix": {"type": "move", "path": str(p.parent), "what": "skills"}}
    for p in sorted((root / "agents").glob("*.md")):
        found["subagent:" + p.stem] = {"source": f"user subagent {_home(str(p))}", "remove": f"remove {_home(str(p))}",
                                       "fix": {"type": "move", "path": str(p), "what": "agents"}}
    claude_json = read_json(Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home())) / ".claude.json")
    for name, definition in (claude_json.get("mcpServers") or {}).items():
        found["mcp:" + server(name)] = {"source": "user MCP server (~/.claude.json)",
                                        "remove": f"claude mcp remove {name} -s user",
                                        "fix": {"type": "run", "argv": ["mcp", "remove", name, "-s", "user"],
                                                "undo": ["mcp", "add-json", name, json.dumps(definition), "-s", "user"]}}
    for project, settings in (claude_json.get("projects") or {}).items():
        for name in (settings or {}).get("mcpServers") or {}:
            found.setdefault("mcp:" + server(name), {"source": f"MCP server of {_home(project)}",
                                                     "remove": f"claude mcp remove {name} (in {_home(project)})"})
        where = Path(project)
        for name in read_json(where / ".mcp.json").get("mcpServers") or {}:
            found.setdefault("mcp:" + server(name), {"source": f"{_home(project)}/.mcp.json",
                                                     "remove": f"remove it from {_home(project)}/.mcp.json"})
        for p in sorted((where / ".claude" / "skills").glob("*/SKILL.md")):
            found.setdefault("skill:" + p.parent.name, {"source": f"project skill {_home(str(p.parent))}",
                                                        "remove": f"remove {_home(str(p.parent))}"})
        for p in sorted((where / ".claude" / "agents").glob("*.md")):
            found.setdefault("subagent:" + p.stem, {"source": f"project subagent {_home(str(p))}",
                                                    "remove": f"remove {_home(str(p))}"})
    return found


def origin(key, installed):
    """Where an item comes from, when the disk doesn't say it directly."""
    if key in installed:
        return installed[key]
    kind, _, name = key.partition(":")
    if kind == "mcp" and name.startswith("claude_ai_"):
        return {"source": "claude.ai connector", "remove": "disconnect it at claude.ai/settings/connectors"}
    if kind == "skill" and name.startswith("anthropic-skills:"):
        return {"source": "claude.ai skill", "remove": "turn it off at claude.ai/settings/capabilities"}
    plugin = None
    if kind == "skill" and ":" in name:
        plugin = name.split(":")[0]
    elif kind == "mcp" and name.startswith("plugin_"):
        plugin = next((p[7:] for p in installed if p.startswith("plugin:") and name.startswith(f"plugin_{p[7:]}_")),
                      name.split("_")[1])
    if plugin:
        found = installed.get("plugin:" + plugin) or {
            "source": f"plugin {plugin} (not on disk: synced or managed)", "remove": f"claude plugin disable {plugin}"}
        return {**found, "plugin": plugin}
    if kind == "instructions":
        return {"source": "instruction file", "remove": ""}
    if kind == "hook":
        return {"source": "hook (settings.json or a plugin)", "remove": ""}
    if kind == "mcp":
        return {"source": "not in your config files (an extension, a plugin or a project)", "remove": ""}
    return {"source": "built in", "remove": "", "builtin": True}
