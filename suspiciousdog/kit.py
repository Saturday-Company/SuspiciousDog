"""The kit: everything you added to your agent, with what it weighs, how often it is used, and how often it fails.

Every session records what it loaded into the context (skill and subagent listings, MCP server instructions, deferred
tool names, instruction files, hooks) and what it called. Lined up across sessions, that is a ledger: loaded in 267
sessions, used in 0, about 400 tokens each time.
"""

import json
import os
import sqlite3
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path

from .adapters import ADAPTERS, sessions
from .stats import fisher

SCAN_VERSION = 10      # bump whenever an adapter reads kits differently
MIN_SESSIONS = 20       # below this, "too new to judge"
RARE = 0.05             # used in under 5% of the sessions that load it
CHARS_PER_TOKEN = 4     # an estimate, and always shown as one
KINDS = ("skill", "mcp", "subagent", "instructions", "hook", "plugin", "tool")


def tokens(chars):
    return round(chars / CHARS_PER_TOKEN)


# --- reading, with a cache so the second run is instant ---

def cache_path():
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "suspiciousdog" / "kit.sqlite"


class Cache:
    """One row per session file. Rebuilt whenever the file, its subagents or the scanner change."""

    def __init__(self, path=None, enabled=True):
        self.db = None
        if not enabled or os.environ.get("SDOG_NO_CACHE"):
            return
        try:
            path = Path(path or cache_path())
            path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(path)
            self.db.execute("CREATE TABLE IF NOT EXISTS kits (file TEXT PRIMARY KEY, stamp TEXT, data TEXT)")
        except (OSError, sqlite3.Error):
            self.db = None

    def get(self, file, stamp):
        if not self.db:
            return None
        row = self.db.execute("SELECT stamp, data FROM kits WHERE file = ?", (str(file),)).fetchone()
        return json.loads(row[1]) if row and row[0] == stamp else None

    def put(self, file, stamp, data):
        if self.db:
            try:
                self.db.execute("REPLACE INTO kits VALUES (?, ?, ?)", (str(file), stamp, json.dumps(data)))
            except sqlite3.Error:
                pass

    def close(self):
        if self.db:
            self.db.commit()
            self.db.close()


def _read(job):
    name, f = job
    return ADAPTERS[name].kit(f)


def scan(agent=None, path=None, project=None, cache=True):
    """One kit per session, for every agent whose adapter can read what it loaded."""
    store, kits, todo = Cache(enabled=cache), [], []
    for adapter, f in sessions(agent, path):
        if not hasattr(adapter, "kit"):
            continue
        if project and project not in str(f):
            continue
        try:
            stamp = f"{SCAN_VERSION};{adapter.kit_stamp(f)}"
        except OSError:
            continue
        k = store.get(f, stamp)
        if k is None:
            todo.append((adapter.NAME, f, stamp))
        else:
            kits.extend(k if isinstance(k, list) else [k])       # Aider keeps many chats in one file
    if todo:
        jobs = [(name, f) for name, f, _ in todo]
        try:
            with ProcessPoolExecutor(min(8, os.cpu_count() or 1)) as pool:
                fresh = list(pool.map(_read, jobs, chunksize=4))
        except (OSError, RuntimeError, BrokenProcessPool):
            fresh = [_read(job) for job in jobs]
        for (_, f, stamp), k in zip(todo, fresh):
            store.put(f, stamp, k)
            kits.extend(k if isinstance(k, list) else [k])
    store.close()
    return sorted((k for k in kits if k["start"] and (k["base_tokens"] is not None or k["used"])),
                  key=lambda k: k["start"])


# --- the ledger ---

@dataclass
class Item:
    key: str
    loaded: int = 0                 # sessions that loaded it
    used: int = 0                   # sessions that used it
    calls: int = 0
    errors: int = 0
    retries: int = 0
    denied: int = 0
    chars: int = 0                  # the most it took in one session
    first: str = ""
    last: str = ""
    projects: Counter = field(default_factory=Counter)          # where it was used
    loaded_projects: Counter = field(default_factory=Counter)
    samples: list = field(default_factory=list)                 # [why, error text]
    tools: dict = field(default_factory=dict)                   # tool: [calls, errors], inside a server
    error_kinds: Counter = field(default_factory=Counter)       # why it failed, see failures.py
    origin: dict = field(default_factory=dict)
    verdict: str = ""
    why: str = ""

    @property
    def kind(self):
        return self.key.split(":", 1)[0]

    @property
    def name(self):
        return self.key.split(":", 1)[1]

    @property
    def use_rate(self):
        return self.used / self.loaded if self.loaded else 0.0

    @property
    def error_rate(self):
        return self.errors / self.calls if self.calls else 0.0

    @property
    def weight(self):
        """Estimated tokens it costs in the sessions that load it."""
        return tokens(self.chars)


def ledger(kits, installed=None, origin=None):
    """{key: Item}, every item with its verdict."""
    items = {}

    def item(key):
        if key not in items:
            items[key] = Item(key)
        return items[key]
    for k in kits:
        day = (k["start"] or "")[:10]
        for key, chars in k["loaded"].items():
            it = item(key)
            it.loaded += 1
            it.chars = max(it.chars, chars)
            it.first = min(it.first or day, day)
            it.last = max(it.last, day)
            it.loaded_projects[k["project"]] += 1
        for key, n in k["used"].items():
            it = item(key)
            it.used += 1
            it.calls += n
            it.projects[k["project"]] += 1
            if key.startswith("tool:"):
                it.loaded += 1
                it.first = min(it.first or day, day)
                it.last = max(it.last, day)
        for field_name in ("errors", "retries", "denied"):
            for key, n in k[field_name].items():
                setattr(item(key), field_name, getattr(item(key), field_name) + n)
        for key, texts in k["samples"].items():
            it = item(key)
            for why, text in (t if isinstance(t, list) else ["other", t] for t in texts):
                known = {w for w, _ in it.samples}
                if len(it.samples) < 6 and (why not in known or len(it.samples) < 2):
                    it.samples.append([why, text])
        for key, tools in k.get("tools", {}).items():
            it = item(key)
            for tool, (calls, errors) in tools.items():
                total = it.tools.setdefault(tool, [0, 0])
                total[0] += calls
                total[1] += errors
        for key, kinds in k.get("error_kinds", {}).items():
            item(key).error_kinds.update(kinds)
    for key, it in items.items():
        it.origin = origin(key, installed or {}) if origin else {}
    _plugins(items)
    for key, it in items.items():
        if key.startswith("plugin:") and origin:
            o = origin(key, installed or {})
            if not o.get("builtin"):
                it.origin = {**it.origin, **o}
    judge(items)
    return items


def _plugins(items):
    """A plugin is the sum of what it brings: its skills and its servers."""
    groups = {}
    for it in list(items.values()):
        plugin = it.origin.get("plugin")
        if plugin:
            groups.setdefault(plugin, []).append(it)
    for plugin, parts in groups.items():
        p = items.setdefault("plugin:" + plugin, Item("plugin:" + plugin))
        p.origin = {k: v for k, v in parts[0].origin.items() if k != "plugin"}
        p.loaded = max(x.loaded for x in parts)
        p.used = max(x.used for x in parts)
        p.calls = sum(x.calls for x in parts)
        p.errors = sum(x.errors for x in parts)
        p.chars = sum(x.chars for x in parts)
        p.first = min(x.first for x in parts if x.first) if any(x.first for x in parts) else ""
        p.last = max(x.last for x in parts)
        for x in parts:
            p.projects.update(x.projects)


def judge(items):
    """ballast, rare, elsewhere, misused, earns, new; fixed for what is built in; pruned for what sdog took out;
    weight and hook for the rest."""
    calls = sum(it.calls for it in items.values() if it.kind in ("tool", "mcp"))
    errors = sum(it.errors for it in items.values() if it.kind in ("tool", "mcp"))
    for it in items.values():
        others_calls, others_errors = calls - it.calls, errors - it.errors
        base = others_errors / others_calls if others_calls else 0.0
        if it.kind == "mcp" and it.calls >= 20 and it.error_rate >= max(2 * base, 0.05) and \
                fisher(it.errors, it.calls - it.errors, others_errors, others_calls - others_errors) < 0.01:
            it.verdict, it.why = "misused", f"fails {it.error_rate:.1%} of the time, your other tools {base:.1%}"
        elif it.origin.get("pruned"):
            it.verdict, it.why = "pruned", "taken out with sdog: the journal measures what happened after"
        elif it.kind == "instructions":
            it.verdict, it.why = "weight", "loaded as written; whether it is followed comes in 0.2.0a2"
        elif it.kind == "tool":
            it.verdict, it.why = "builtin", ""
        elif it.kind == "hook":
            it.verdict = "hook"
            it.why = f"fired {it.calls} times" + (f", blocked {it.errors}" if it.errors else "")
        elif it.origin.get("builtin") and it.kind != "mcp":
            it.verdict = "fixed"
            it.why = f"built in, used in {it.used} of {it.loaded} sessions: not yours to remove"
        elif it.loaded < MIN_SESSIONS:
            it.verdict, it.why = "new", f"loaded in {it.loaded} sessions, I need {MIN_SESSIONS}"
        elif it.used == 0:
            it.verdict, it.why = "ballast", f"loaded in {it.loaded} sessions, never used"
        elif _elsewhere(it):
            home, n = it.projects.most_common(1)[0]
            it.verdict = "elsewhere"
            it.why = f"used only in {home} ({n} sessions), loaded in {len(it.loaded_projects)} projects"
            it.origin = {**it.origin, "home": home}
        elif it.use_rate < RARE:
            it.verdict, it.why = "rare", f"used in {it.used} of {it.loaded} sessions ({it.use_rate:.0%})"
        else:
            it.verdict, it.why = "earns", f"used in {it.used} of {it.loaded} sessions ({it.use_rate:.0%})"


def _elsewhere(it):
    if len(it.projects) != 1 or it.used < 3 or len(it.loaded_projects) < 3:
        return False
    home = next(iter(it.projects))
    return it.loaded - it.loaded_projects[home] >= MIN_SESSIONS


def summary(kits, items):
    """The numbers for the top of the report."""
    base = [k["base_tokens"] for k in kits if k["base_tokens"]]
    days = sorted(k["start"][:10] for k in kits)
    per_kind = Counter()
    for it in items.values():
        if it.kind in ("skill", "mcp", "subagent", "instructions") and it.loaded:
            per_kind[it.kind] += it.chars * it.loaded
    n = len(kits) or 1
    ballast = sum(it.chars * it.loaded for it in items.values() if it.verdict == "ballast")
    return {"sessions": len(kits), "first": days[0] if days else "", "last": days[-1] if days else "",
            "base_tokens": round(sum(base) / len(base)) if base else None,
            "listed_tokens": {kind: tokens(c / n) for kind, c in per_kind.items()},
            "ballast_tokens": tokens(ballast / n),
            "agents": dict(Counter(k["agent"] for k in kits))}
