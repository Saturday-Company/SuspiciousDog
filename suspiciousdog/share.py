"""What leaves your machine when you choose to share: counts, and nothing that was ever typed."""

import json
import re
import urllib.parse

from . import __version__
from .signals import FACTORS, OUTCOMES

REPO = "Saturday-Company/SuspiciousDog"
MAX_URL = 7500
CAP = 10 ** 7       # no honest share counts more turns, sessions or calls than this


def slug(name):
    name = name.lower().replace("+", " plus").replace("<", "under ")
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


FACTOR_SLUGS = {slug(n) for n in FACTORS}
OUTCOME_SLUGS = {slug(n) for n in OUTCOMES}


def kit_counts(items, summary):
    """Format 2: the kit, for items with public names only (see public.py). Everything else is one number."""
    from . import public
    rows, private = {}, 0
    for it in items.values():
        if it.kind in ("hook", "instructions") or it.verdict == "pruned":
            continue
        name = public.key(it)
        if not name:
            private += 1
            continue
        row = rows.setdefault(name, [name, 0, 0, 0, 0, 0])      # loaded, used, calls, errors, weight
        row[1] += it.loaded
        row[2] += it.used
        row[3] += it.calls
        row[4] += it.errors
        row[5] = max(row[5], it.weight)
    return {"sessions": int(summary["sessions"]), "context_tokens": int(summary["base_tokens"] or 0),
            "ballast_tokens": int(summary["ballast_tokens"]), "private_items": private,
            "items": sorted(rows.values())}


def payload(tables, turns, per_agent, items=None, summary=None):
    """Only fixed names from our own vocabulary and integers. No prompts, replies, paths or project names."""
    answered = [t for t in turns if t.reply]
    days = sorted({t.when.date() for t in answered if t.when})
    rows = []
    for outcome, results in tables.items():
        for factor, r in results:
            rows.append([slug(factor), slug(outcome), r["n_with"], r["hits_with"], r["n_without"], r["hits_without"]])
    data = {
        "suspiciousdog": __version__,
        "agents": {name: int(n) for name, n in sorted(per_agent.items())},
        "turns": len(answered),
        "days": len(days),
        "results": rows,
    }
    if items and summary and summary.get("sessions"):
        data["format"] = 2
        data["kit"] = kit_counts(items, summary)
    return data


def validate(data):
    """Raises if anything outside the vocabulary or a number would be sent."""
    from . import public
    assert set(data) in ({"suspiciousdog", "agents", "turns", "days", "results"},
                         {"suspiciousdog", "agents", "turns", "days", "results", "format", "kit"})
    assert re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?", data["suspiciousdog"])
    if "kit" in data:
        kit = data["kit"]
        assert data["format"] == 2
        assert set(kit) == {"sessions", "context_tokens", "ballast_tokens", "private_items", "items"}
        assert all(_count(kit[k]) for k in kit if k != "items")
        for row in kit["items"]:
            name, *counts = row
            assert isinstance(name, str) and public.allowed(name), name
            assert len(counts) == 5 and all(_count(c) for c in counts)
            loaded, used, calls, errors, _ = counts
            assert used <= loaded and errors <= calls
    from .adapters import ADAPTERS
    for name, n in data["agents"].items():
        assert name in ADAPTERS and _count(n)
    assert _count(data["turns"]) and _count(data["days"])
    for row in data["results"]:
        factor, outcome, *counts = row
        assert factor in FACTOR_SLUGS and outcome in OUTCOME_SLUGS
        assert len(counts) == 4 and all(_count(c) for c in counts)
        n_with, hits_with, n_without, hits_without = counts
        assert hits_with <= n_with and hits_without <= n_without
    return True


def _count(x):
    return isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= CAP


def issue_url(data):
    body = json.dumps(data, separators=(",", ":"))
    query = urllib.parse.urlencode({"template": "share-results.yml", "title": "Sniff results", "results": body})
    url = f"https://github.com/{REPO}/issues/new?{query}"
    return url if len(url) <= MAX_URL else None
