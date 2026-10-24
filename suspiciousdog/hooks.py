"""Two optional hooks for Claude Code, off until you turn them on, each written in the journal with its undo.

- brief: at the start of a session the agent reads the brief (~250 tokens, in every session that starts).
- sentinel: when a session ends the data is read again in the background; at most once a week, when a change you
  made has enough turns after it, the next session opens with one line saying what happened. The line is shown to
  you as a hook message; Claude Code may pass it to the model too, ~30 tokens, once a week.

Both only read from the hook: building the brief takes seconds, so the hook reads the copy made after the last
session and never makes the session wait.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import journal

FEATURES = {
    "brief": [("SessionStart", "startup", "brief --hook")],
    "sentinel": [("SessionEnd", None, "sentinel --hook end"), ("SessionStart", "startup", "sentinel --hook start")],
}
WEEK = 7 * 86400


def settings_path():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "settings.json"


def command():
    """How a hook calls sdog: the installed command, or this very Python with the package on its path."""
    found = shutil.which("sdog")
    if found:
        return shlex.quote(found)
    root = Path(__file__).resolve().parent.parent
    return f"PYTHONPATH={shlex.quote(str(root))} {shlex.quote(sys.executable)} -m suspiciousdog"


def _read():
    p = settings_path()
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        raise RuntimeError(f"{p} is not valid JSON; not touching it")


def _write(settings):
    p = settings_path()
    if p.exists():
        backup = journal.home() / "attic" / f"settings.json.{int(time.time())}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, backup)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.sdog")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(p)


def _ours(hook, tail):
    cmd = str(hook.get("command", "")) if isinstance(hook, dict) else ""
    return cmd.endswith(tail) and ("sdog" in cmd or "suspiciousdog" in cmd)


def status():
    """{feature: on?}"""
    hooks = _read().get("hooks") or {}
    out = {}
    for feature, parts in FEATURES.items():
        out[feature] = all(any(_ours(h, tail) for group in hooks.get(event) or [] for h in group.get("hooks") or [])
                           for event, _, tail in parts)
    return out


def on(feature, record=True):
    if feature not in FEATURES:
        raise RuntimeError(f"no hook called {feature}; there are {', '.join(FEATURES)}")
    if status()[feature]:
        raise RuntimeError(f"{feature} is already on")
    settings = _read()
    hooks = settings.setdefault("hooks", {})
    for event, matcher, tail in FEATURES[feature]:
        group = {"hooks": [{"type": "command", "command": f"{command()} {tail}", "timeout": 10}]}
        if matcher:
            group = {"matcher": matcher, **group}
        hooks.setdefault(event, []).append(group)
    _write(settings)
    if record:
        return journal.write("hook", f"turned on the {feature} hook", f"hook:sdog {feature}",
                             {"type": "hooks", "off": feature})


def off(feature, record=True):
    settings = _read()
    hooks = settings.get("hooks") or {}
    removed = 0
    for event, _, tail in FEATURES.get(feature, []):
        groups = []
        for group in hooks.get(event) or []:
            kept = [h for h in group.get("hooks") or [] if not _ours(h, tail)]
            removed += len(group.get("hooks") or []) - len(kept)
            if kept:
                groups.append({**group, "hooks": kept})
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if not removed:
        raise RuntimeError(f"{feature} is not on")
    if not hooks:
        settings.pop("hooks", None)
    _write(settings)
    if record:
        return journal.write("hook", f"turned off the {feature} hook", f"hook:sdog {feature}",
                             {"type": "hooks", "on": feature})


def detach(*args):
    """Run sdog in the background and return at once: a hook must never make the session wait."""
    cmd = shlex.split(command()) + list(args)
    env = dict(os.environ)
    if cmd and cmd[0].startswith("PYTHONPATH="):
        env["PYTHONPATH"] = cmd.pop(0).split("=", 1)[1]
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True, env=env)
    except OSError:
        pass
