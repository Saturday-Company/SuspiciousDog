"""What leaves your machine when you choose to share: counts, and nothing that was ever typed."""

import json
import re
import urllib.parse

from . import __version__
from .signals import FACTORS, OUTCOMES

REPO = "Saturday-Company/SuspiciousDog"
MAX_URL = 7500


def slug(name):
    name = name.lower().replace("+", " plus").replace("<", "under ")
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


FACTOR_SLUGS = {slug(n) for n in FACTORS}
OUTCOME_SLUGS = {slug(n) for n in OUTCOMES}


def payload(tables, turns, per_agent):
    """Only fixed names from our own vocabulary and integers. No prompts, replies, paths or project names."""
    answered = [t for t in turns if t.reply]
    days = sorted({t.when.date() for t in answered if t.when})
    rows = []
    for outcome, results in tables.items():
        for factor, r in results:
            rows.append([slug(factor), slug(outcome), r["n_with"], r["hits_with"], r["n_without"], r["hits_without"]])
    return {
        "suspiciousdog": __version__,
        "agents": {name: int(n) for name, n in sorted(per_agent.items())},
        "turns": len(answered),
        "days": len(days),
        "results": rows,
    }


def validate(data):
    """Raises if anything outside the vocabulary or a number would be sent."""
    assert set(data) == {"suspiciousdog", "agents", "turns", "days", "results"}
    assert re.fullmatch(r"\d+\.\d+\.\d+((a|b|rc)\d+)?", data["suspiciousdog"])
    from .adapters import ADAPTERS
    for name, n in data["agents"].items():
        assert name in ADAPTERS and isinstance(n, int)
    assert isinstance(data["turns"], int) and isinstance(data["days"], int)
    for row in data["results"]:
        factor, outcome, *counts = row
        assert factor in FACTOR_SLUGS and outcome in OUTCOME_SLUGS
        assert len(counts) == 4 and all(isinstance(c, int) and c >= 0 for c in counts)
    return True


def issue_url(data):
    body = json.dumps(data, separators=(",", ":"))
    query = urllib.parse.urlencode({"template": "share-results.yml", "title": "Sniff results", "results": body})
    url = f"https://github.com/{REPO}/issues/new?{query}"
    return url if len(url) <= MAX_URL else None
