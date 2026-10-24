"""The brief: what this user's past sessions say, in a few lines an agent can read before it starts.

An agent starts every session from zero. It can't know that its "Shall I go ahead?" gets put off, or that one MCP
server keeps failing for the same reason. The transcripts know. Every line of the brief stands on a count from them,
and the brief is rebuilt from the data, never written by hand.

Under 300 tokens, on purpose: it is read at the start of a session, so it is paid for in every session.
"""

import hashlib
import json
import os
import time
from datetime import datetime
from pathlib import Path

from . import lab
from .kit import tokens
from .signals import ALL_OUTCOMES

MAX_CHARS = 1100            # ~275 tokens
MIN_PROJECT_TURNS = 200     # fewer than this in the project: use every session

# What to do about a habit that goes with a worse answer. {o} is how the answer went, {a}/{b} the two rates.
ADVICE = {
    "ends offering more work": "Ending a turn by offering more work (\"Shall I…?\"): {o} {a} of the time, {b} "
                               "otherwise. Finish what was asked and list the rest as open items.",
    "ends with a question": "Ending with a question: {o} {a} of the time, {b} otherwise. Ask only what you can't "
                            "decide.",
    "claims done without looking": "Saying it's done without checking after the last edit: {o} {a} of the time, {b} "
                                   "otherwise. Run or look at the result first.",
    "long final answer (300+ words)": "Answers of 300+ words: {o} {a} of the time, {b} otherwise. Keep them short.",
    "40+ tool calls": "Turns with 40+ tool calls: {o} {a} of the time, {b} otherwise. Check in before going that long.",
    "3+ tool errors": "Turns with 3+ tool errors: {o} {a} of the time, {b} otherwise. Stop and rethink after two "
                      "failures.",
    "touches 5+ files": "Turns that touch 5+ files: {o} {a} of the time, {b} otherwise. Say what you'll change first.",
    "text only": "Answers with no tool call at all: {o} {a} of the time, {b} otherwise. Look before you answer.",
    "drives a browser": "Browser turns: {o} {a} of the time, {b} otherwise. Check the page state before acting.",
}
SAID = {"complaint": "a complaint", "deferral": "put off", "interruption": "interrupted", "asks again": "asked again"}
# What the agent itself can do about each kind of failure.
DO = {
    "auth": "don't retry, tell the user it needs reconnecting",
    "timeout": "keep calls small and don't repeat one that timed out",
    "server": "retry once, then tell the user",
    "wrong target": "re-read the state (tabs, pages, ids) before acting",
    "bad code": "read the schema or the page before writing queries or scripts",
    "wrong arguments": "check the tool's parameters before calling it",
    "not found": "look ids and paths up instead of guessing them",
    "not loaded": "load the tool before calling it",
    "setup": "do the first step (pick the browser, open a tab) before anything else",
}
AGENT_SIDE = {"wrong target", "bad code", "wrong arguments", "not found", "not loaded", "setup"}
# The outcomes the brief looks at: complaint, not pushback, so that a "no" to an offer isn't counted as a complaint.
OUTCOMES = {name: ALL_OUTCOMES[name] for name in ("complaint", "deferral", "interruption", "asks again", "quick yes")}
GOOD = {
    "checks the result after the last edit": "Checking the result after the last edit: a quick yes {a} of the time, "
                                             "{b} otherwise. Keep doing it.",
    "ends with a question": "Ending with one clear question: a quick yes {a} of the time, {b} otherwise. Questions "
                            "get answered; don't avoid them.",
    "ends offering more work": "Offering the next step at the end: a quick yes {a} of the time, {b} otherwise.",
}


def _pct(x):
    return f"{x:.0%}"


def _habits(turns, outcomes=None):
    tables = lab.sniff(turns, outcomes=outcomes or OUTCOMES)
    bad, good = [], []
    for outcome, rows in tables.items():
        for factor, r in rows:
            if r["p"] >= 0.01 or r["n_with"] < 30:
                continue
            strength = "" if r.get("q", 1) < 0.05 else " (a lead, not proven)"
            if outcome in SAID and r["ratio"] > 1.5 and factor in ADVICE:
                bad.append((r["p"], factor, ADVICE[factor].format(o=SAID[outcome], a=_pct(r["rate_with"]),
                                                                  b=_pct(r["rate_without"])) + strength))
            elif outcome == "quick yes" and r["ratio"] > 1.2 and factor in GOOD:
                good.append((r["p"], factor, GOOD[factor].format(a=_pct(r["rate_with"]),
                                                                 b=_pct(r["rate_without"])) + strength))
    lines, seen = [], set()
    for _, factor, line in sorted(bad) + sorted(good)[:1]:
        if factor not in seen:
            seen.add(factor)
            lines.append(line)
    return lines[:3]


def _tools(items):
    lines = []
    for it in sorted((it for it in items.values() if it.verdict == "misused"), key=lambda it: -it.errors)[:3]:
        kinds = [(w, n) for w, n in it.error_kinds.most_common() if w in DO]
        known = sum(n for _, n in kinds)
        mine = [(w, n) for w, n in kinds if w in AGENT_SIDE and n >= 0.25 * known]
        top = (mine or kinds or [(None, 0)])[0][0]
        name = it.name.replace("claude_ai_", "")
        line = f"{name}: {it.error_rate:.0%} of calls fail ({it.errors} of {it.calls})"
        if top:
            line += f", often {top}: {DO[top]}"
        lines.append(line + ".")
    return lines


def build(turns, items=None, project=None, labels=None):
    """The brief as text, and the numbers behind it. With a classifier's labels, habits are read from those."""
    scoped = [t for t in turns if project and project in t.project]
    used = scoped if sum(1 for t in scoped if t.reply) >= MIN_PROJECT_TURNS else turns
    answered = sum(1 for t in used if t.reply)
    outcomes = None
    if labels:
        from .classify import outcomes as read_by_model
        used = [t for t in used if id(t) in labels]
        answered = len(used)
        outcomes = {k: v for k, v in read_by_model(labels).items() if k != "declines"}   # a no is not a failure
    habits = _habits(used, outcomes) if answered else []
    tools = _tools(items or {})
    if not habits and not tools:
        return "", {"turns": answered, "lines": 0}
    where = "this project" if scoped and set(map(id, used)) <= set(map(id, scoped)) else "all your projects"
    reader = ", replies read by a model" if labels else ""
    out = [f"From {answered:,} answered turns in {where}{reader} (SuspiciousDog, {datetime.now():%Y-%m-%d}). "
           "Counts, not rules:"]
    out += [f"- {line}" for line in habits + tools]
    text = "\n".join(out)
    while len(text) > MAX_CHARS and len(out) > 2:
        out.pop()
        text = "\n".join(out)
    return text, {"turns": answered, "lines": len(out) - 1, "tokens": tokens(len(text)), "scope": where,
                  "reader": "model" if labels else "regular expressions"}


# --- the copy that hooks read: building it takes seconds, reading it must not ---

def cache_dir():
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "suspiciousdog"


def cached_path(project=None):
    name = "brief.json" if not project else f"brief-{hashlib.sha1(project.encode()).hexdigest()[:10]}.json"
    return cache_dir() / name


def save(text, numbers, project=None):
    p = cached_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"at": time.time(), "text": text, "numbers": numbers}))


def cached(project=None, max_age=86400):
    """(text, fresh): the last brief built, and whether it is younger than max_age seconds."""
    try:
        d = json.loads(cached_path(project).read_text())
    except (OSError, ValueError):
        return None, False
    return d.get("text"), time.time() - d.get("at", 0) < max_age
