"""Lighten the kit: proposals from the ledger, applied only on an explicit yes, each one undoable.

What it can do itself, through Claude Code's own commands or by moving a folder:
- disable a plugin installed for the user (`claude plugin disable`, undone with `enable`);
- remove a user MCP server (`claude mcp remove`, undone with `add-json` and the saved definition);
- move a user skill or subagent out of the way, into SuspiciousDog's attic, or into the one project that uses it.

What it can't (claude.ai connectors and skills, managed plugins, project files) it tells you how to do, and
`sdog note` puts it in the journal so the before/after still happens.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import journal
from .kit import tokens

VERDICTS = ("ballast", "rare", "elsewhere")
CHEAP = 100         # tokens a session: something you do use, now and then, that costs less than this is worth keeping


@dataclass
class Proposal:
    key: str
    what: str           # what would happen, in words
    why: str
    saves: int          # estimated tokens a session, averaged over every session
    fix: dict | None    # None: you do it, here is how
    hint: str = ""


def claude():
    return os.environ.get("SDOG_CLAUDE", "claude")


def attic():
    return journal.home() / "attic"


def pruned():
    """{key: journal entry} for what sdog took out and nobody put back."""
    gone = journal.undone()
    return {e["key"]: e for e in journal.read() if e.get("action") == "prune" and e["id"] not in gone and e.get("key")}


def _saves(it, sessions):
    return tokens(it.chars * it.loaded / max(sessions, 1))


def cheap(items, sessions):
    """Rarely used, but used, and light: a skill you reach for once a month is worth its line in the listing."""
    return sorted((it for it in items.values() if it.verdict == "rare" and not it.origin.get("builtin")
                   and _saves(it, sessions) < CHEAP), key=lambda it: -_saves(it, sessions))


def proposals(items, sessions):
    """(proposals sdog can apply, things only you can do), biggest saving first."""
    mine, yours = [], []
    light = {it.key for it in cheap(items, sessions)}
    for it in items.values():
        if it.verdict not in VERDICTS or it.origin.get("builtin") or it.key in light or it.origin.get("pruned"):
            continue
        if it.origin.get("source", "").endswith(", disabled"):
            continue
        if it.origin.get("plugin") and f"plugin:{it.origin['plugin']}" in items:
            continue        # its plugin is the thing to switch off
        saves = _saves(it, sessions)
        fix = it.origin.get("fix")
        why = it.why
        if fix and fix["type"] == "move":
            src = Path(fix["path"])
            if it.verdict == "elsewhere" and it.origin.get("home"):
                project = Path(os.path.expanduser(it.origin["home"]))
                dest = project / ".claude" / fix["what"] / src.name
                what = f"move {it.kind} {it.name} into {it.origin['home']}, the only project that uses it"
                fix = {"type": "move", "from": str(src), "to": str(dest)}
            else:
                what = f"put {it.kind} {it.name} in the attic"
                fix = {"type": "move", "from": str(src), "to": str(attic() / fix["what"] / src.name)}
            mine.append(Proposal(it.key, what, why, saves, fix))
        elif fix and fix["type"] == "run" and it.verdict != "elsewhere":
            verb = "disable" if it.kind == "plugin" else "remove"
            mine.append(Proposal(it.key, f"{verb} {it.kind} {it.name}", why, saves, fix))
        elif it.origin.get("remove"):
            yours.append(Proposal(it.key, f"{it.kind} {it.name}", why, saves, None, it.origin["remove"]))
    mine.sort(key=lambda p: -p.saves)
    yours.sort(key=lambda p: -p.saves)
    return mine, yours


def describe(fix):
    """The exact command or move, for the user to read before saying yes."""
    if fix["type"] == "run":
        return "$ " + " ".join([claude(), *fix["argv"]])[:160]
    home = str(Path.home())
    return "mv " + " → ".join(p.replace(home, "~", 1) for p in (fix["from"], fix["to"]))


def _run(argv):
    try:
        done = subprocess.run([claude(), *argv], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"couldn't run {claude()}: {e}")
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout or f"exit {done.returncode}").strip()[:300])


def _move(src, dest):
    src, dest = Path(src), Path(dest)
    if not src.exists():
        raise RuntimeError(f"{src} is not there any more")
    if dest.exists():
        raise RuntimeError(f"{dest} already exists; not overwriting it")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))


def apply(p):
    """Do it, then write it down with its undo."""
    fix = p.fix
    if fix["type"] == "run":
        _run(fix["argv"])
        undo = {"type": "run", "argv": fix["undo"]}
    else:
        _move(fix["from"], fix["to"])
        undo = {"type": "move", "from": fix["to"], "to": fix["from"]}
    return journal.write("prune", p.what, p.key, undo, saves=p.saves)


def undo(entry):
    u = entry.get("undo")
    if not u:
        raise RuntimeError("nothing to undo for this entry (a note, or already undone)")
    if entry["id"] in journal.undone():
        raise RuntimeError(f"entry {entry['id']} was already undone")
    if u["type"] == "run":
        _run(u["argv"])
    elif u["type"] == "hooks":
        from . import hooks
        hooks.off(u["off"], record=False) if u.get("off") else hooks.on(u["on"], record=False)
    else:
        _move(u["from"], u["to"])
    return journal.write("undo", f"undid #{entry['id']}: {entry['what']}", entry.get("key", ""), None,
                         undoes=entry["id"])
