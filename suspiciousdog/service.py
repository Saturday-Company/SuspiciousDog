"""The answers, as data: shared by the command line, the MCP server and the hooks.

Everything is read lazily and once: the MCP server keeps one State for its whole life.
"""

import os
import re
from functools import cached_property
from pathlib import Path

from . import kit, lab, prune, timeline
from .adapters import claude_code, load
from .failures import FIX


def origin():
    """Where things come from, knowing what sdog itself took out (otherwise a skill in the attic looks built in)."""
    gone = prune.pruned()

    def find(key, installed):
        if key in gone and key not in installed:
            e = gone[key]
            return {"source": f"taken out with sdog on {e['at'][:10]} (journal #{e['id']})", "remove": "",
                    "pruned": True}
        found = claude_code.origin(key, installed)
        return {**found, "pruned": True} if key in gone or f"plugin:{found.get('plugin')}" in gone else found
    return find


def journal_changes():
    """The journal's entries as changes, so they get the same before/after as the ones found in the transcripts."""
    from . import journal
    gone = journal.undone()
    out = []
    for e in journal.read():
        if e.get("action") in ("prune", "note", "hook"):
            c = timeline.Change(journal.when(e), f"#{e['id']} {e['what']}" + (" (undone)" if e["id"] in gone else ""),
                                "journal", [e.get("key", "")])
            c.parts = [c.what]
            out.append(c)
    return out


def needle(cwd):
    """How a folder shows up in session paths: Claude Code writes /srv/x as -srv-x."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd)) if cwd else None


class State:
    def __init__(self, agent=None, path=None, project=None, cache=True):
        self.agent, self.path, self.project, self.cache = agent, path, project, cache

    @cached_property
    def kits(self):
        return kit.scan(self.agent, self.path, self.project, cache=self.cache)

    @cached_property
    def items(self):
        return kit.ledger(self.kits, claude_code.config(), origin()) if self.kits else {}

    @cached_property
    def summary(self):
        return kit.summary(self.kits, self.items)

    @cached_property
    def turns(self):
        return load(self.agent, self.path, self.project)[0]

    @cached_property
    def changes(self):
        """(changes found in the transcripts, changes in the journal), both measured."""
        found = timeline.changes(self.kits, claude_code.origin, claude_code.config()) if self.kits else []
        logged = journal_changes()
        timeline.measure(found + logged, self.turns, kits=self.kits)
        return found, logged

    @property
    def weeks(self):
        s = self.summary
        if not s["first"]:
            return 1.0
        from datetime import date
        days = (date.fromisoformat(s["last"]) - date.fromisoformat(s["first"])).days + 1
        return max(days / 7, 1.0)

    def loaded_texts(self, cwd=None):
        """What the latest session (in this folder, if it has one) loaded, as text."""
        files = claude_code.default_paths()
        mine = [f for f in files if cwd and needle(cwd) == f.parent.name]
        pool = mine or files
        if not pool:
            return {}
        latest = max(pool, key=lambda f: f.stat().st_mtime)
        try:
            return claude_code.texts(latest)
        except OSError:
            return {}


def _result(c):
    if not c.rows:
        return {"measured": False, "turns_before": c.before, "turns_after": c.after,
                "note": f"too early: needs {timeline.MIN_AFTER} turns on each side"}
    moved = {n: {"before": round(r["rate_without"], 3), "after": round(r["rate_with"], 3), "p": round(r["p"], 4),
                 "q": round(r.get("q", 1), 4)} for n, r in c.rows if r["p"] < 0.05}
    b, a = c.medians.get("before", {}), c.medians.get("after", {})
    return {"measured": True, "turns_before": c.before, "turns_after": c.after, "moved": moved,
            "context_tokens": [b.get("base"), a.get("base")] if b.get("base") and a.get("base") else None}


def _row(it, sessions):
    top = next((w for w, _ in it.error_kinds.most_common() if w != "other"), None)
    row = {"key": it.key, "verdict": it.verdict, "why": it.why, "loaded_sessions": it.loaded,
           "used_sessions": it.used, "weight_tokens": it.weight,
           "tokens_a_session": prune._saves(it, sessions), "remove": it.origin.get("remove", "")}
    if it.calls:
        row.update(calls=it.calls, fail_rate=round(it.error_rate, 3), retries=it.retries)
    if top:
        row.update(fails_mostly=top, fix=FIX.get(top, ""))
    return row


def audit(state, limit=8):
    """The checkup, as data."""
    items, s = state.items, state.summary
    rows = sorted(items.values(), key=lambda it: -(it.chars * it.loaded))
    found, logged = state.changes
    tables = lab.sniff(state.turns)
    habits = sorted(((o, f, r) for o, rs in tables.items() for f, r in rs if r["p"] < 0.01 and r["ratio"] > 1),
                    key=lambda x: x[2]["p"])
    mine, yours = prune.proposals(items, s["sessions"]) if items else ([], [])
    me = [it for it in rows if "suspiciousdog" in it.key.lower() or it.key == "skill:sniff"]
    return {
        "sessions": s["sessions"], "from": s["first"], "to": s["last"],
        "context_tokens_at_start": s["base_tokens"], "ballast_tokens_a_session": s["ballast_tokens"],
        "ballast": [_row(it, s["sessions"]) for it in rows if it.verdict == "ballast"][:limit],
        "rare": [_row(it, s["sessions"]) for it in rows if it.verdict in ("rare", "elsewhere")][:limit],
        "misused": [_row(it, s["sessions"]) for it in sorted(rows, key=lambda it: -it.errors)
                    if it.verdict == "misused"][:limit],
        "changes": [{"day": c.day, "what": c.parts, **_result(c)} for c in found[-5:]],
        "journal": [{"day": c.day, "what": c.what, **_result(c)} for c in logged[-5:]],
        "habits": [{"factor": f, "outcome": o, "with": round(r["rate_with"], 3), "without": round(r["rate_without"], 3),
                    "turns": r["n_with"], "q": round(r.get("q", 1), 4)} for o, f, r in habits[:5]],
        "prune": {"sdog_can_do": len(mine), "only_the_user_can_do": len(yours),
                  "note": "list with `sdog prune`; apply only the numbers the user picks"},
        "suspiciousdog_itself": [_row(it, s["sessions"]) for it in me[:3]],
        "how_to_read": "after is not because; weights are characters / 4; verdicts need 20+ sessions",
    }


def find(items, name):
    needle_ = name.lower()
    rows = sorted(items.values(), key=lambda it: -(it.calls + it.loaded))
    exact = [it for it in rows if needle_ in (it.name.lower(), it.key.lower())]
    return exact or [it for it in rows if needle_ in it.key.lower()]


def evidence(state, name):
    """Everything about one item: weight, use, failures and what happened when it came or went."""
    found = find(state.items, name)
    if not found:
        return {"error": f"nothing in the kit matches {name!r}", "hint": "call audit_setup for the list"}
    it, s = found[0], state.summary
    changes = [c for c in state.changes[0] if it.key in c.keys]
    out = _row(it, s["sessions"])
    out.update(first=it.first, last=it.last, source=it.origin.get("source", ""),
               used_in={p: n for p, n in it.projects.most_common(4)},
               failing_tools={t: {"calls": c, "errors": e} for t, (c, e) in it.tools.items() if e},
               why_it_fails=dict(it.error_kinds.most_common()),
               failure_samples=[f"[{w}] {t[:140]}" for w, t in it.samples[:4]],
               changes=[{"day": c.day, "what": c.parts, **_result(c)} for c in changes],
               also_matching=[x.key for x in found[1:6]])
    return out


def check_rule(state, text, cwd=None):
    from .check import check
    return check(text, state.turns, state.items, state.loaded_texts(cwd), state.summary["sessions"], state.weeks)


def brief(state, cwd=None):
    from . import brief as b
    from .classify import labels_for
    return b.build(state.turns, state.items, needle(cwd), labels_for(state.turns))


def here():
    return os.environ.get("CLAUDE_PROJECT_DIR") or str(Path.cwd())
