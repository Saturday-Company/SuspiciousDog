"""The optional classifier: a small model reads the user's reply and says what it was. Off unless you run it.

The regular expressions in signals.py are free and local, and they get some replies wrong: "no" to an offer of more
work reads like a complaint, a polite correction reads like nothing. A small model tells them apart better. It costs
tokens and sends text out, so it only runs when asked, says first how much it will send, and keeps every label in a
local cache so nothing is sent twice.

Backends, all without extra dependencies:
- claude: the `claude` command you already use, with Haiku (your subscription or key, your terms);
- anthropic: the API, with ANTHROPIC_API_KEY;
- openai: any OpenAI-compatible endpoint, such as a local model (Ollama: --url http://localhost:11434/v1).

`sdog classify --validate` checks a backend against 80 replies labelled by hand (suspiciousdog/data/labels.jsonl),
next to what the regular expressions get on the same replies.
"""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

from .signals import DEFERRAL, PUSHBACK, QUICK_YES, _declines_offer

LABELS = ("complaint", "declines", "defers", "accepts", "new_request", "other")
BATCH = 40
SYSTEM = (
    "You label replies in a conversation between a user and an AI coding agent. For each item you get the end of "
    "the agent's message and the user's reply. Label the reply with exactly one of: complaint (the work is wrong, "
    "broken, not what was asked, or the agent did something it shouldn't), declines (a no to something the agent "
    "offered), defers (not now, later, put it off), accepts (yes, ok, thanks, approval), new_request (moves on to a "
    "new task), other (questions, comments, anything else). Replies can be in any language. Answer with a JSON array "
    "of labels only, one per item, in order.")
DEFAULT_MODELS = {"claude": "haiku", "anthropic": "claude-haiku-5-5", "openai": "llama3.2"}


def sample():
    path = Path(__file__).parent / "data" / "labels.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _item(agent, reply):
    return {"agent": " ".join(agent.split())[-300:], "reply": " ".join(reply.split())[:300]}


def regex_label(agent, reply):
    """What the free regular expressions say, in the classifier's labels."""
    class T:
        pass
    t = T()
    t.final, t.reply = agent, reply
    if _declines_offer(t):
        return "defers" if DEFERRAL.search(reply[:250]) else "declines"
    if PUSHBACK.search(reply[:300]):
        return "complaint"
    if DEFERRAL.search(reply[:250]):
        return "defers"
    if QUICK_YES.match(reply) and len(reply.split()) <= 8:
        return "accepts"
    return "other"


def estimate(items):
    """Tokens that would be sent and received, roughly."""
    batches = -(-len(items) // BATCH)
    sent = sum(len(json.dumps(i, ensure_ascii=False)) for i in items) // 4 + batches * (len(SYSTEM) // 4 + 30)
    return {"items": len(items), "calls": batches, "tokens_in": sent, "tokens_out": len(items) * 4}


# --- the cache: one label per (reply, backend, model), forever ---

def _db():
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "suspiciousdog"
    root.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / "labels.sqlite")
    db.execute("CREATE TABLE IF NOT EXISTS labels (id TEXT PRIMARY KEY, label TEXT)")
    return db


def key(item, backend, model):
    return hashlib.sha1(json.dumps([item, backend, model], ensure_ascii=False).encode()).hexdigest()


def cached(items, backend, model):
    db = _db()
    out = {}
    for i, item in enumerate(items):
        row = db.execute("SELECT label FROM labels WHERE id = ?", (key(item, backend, model),)).fetchone()
        if row:
            out[i] = row[0]
    db.close()
    return out


def _remember(pairs, backend, model):
    db = _db()
    db.executemany("REPLACE INTO labels VALUES (?, ?)", [(key(i, backend, model), lab) for i, lab in pairs])
    db.commit()
    db.close()


# --- the backends ---

def _parse(text, n):
    m = re.search(r"\[.*\]", text or "", re.S)
    labels = json.loads(m.group(0)) if m else []
    if len(labels) != n:
        raise RuntimeError(f"the model answered {len(labels)} labels for {n} replies")
    return [lab if lab in LABELS else "other" for lab in labels]


def _prompt(batch):
    return json.dumps([{"n": i + 1, **item} for i, item in enumerate(batch)], ensure_ascii=False)


def _claude(batch, model, url=None):
    cmd = [os.environ.get("SDOG_CLAUDE", "claude"), "-p", "--model", model, "--system-prompt", SYSTEM, "--tools", "",
           "--strict-mcp-config", "--no-session-persistence", "--output-format", "json"]
    done = subprocess.run(cmd, input=_prompt(batch), capture_output=True, text=True, timeout=300)
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout).strip()[:300])
    return json.loads(done.stdout).get("result", "")


def _post(url, body, headers):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"content-type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def _anthropic(batch, model, url=None):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    d = _post(url or "https://api.anthropic.com/v1/messages",
              {"model": model, "max_tokens": 1024, "system": SYSTEM,
               "messages": [{"role": "user", "content": _prompt(batch)}]},
              {"x-api-key": api_key, "anthropic-version": "2023-06-01"})
    return "".join(b.get("text", "") for b in d.get("content", []))


def _openai(batch, model, url=None):
    base = (url or "http://localhost:11434/v1").rstrip("/")
    headers = {"authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"} if os.environ.get("OPENAI_API_KEY") else {}
    d = _post(base + "/chat/completions", {"model": model, "temperature": 0, "messages": [
        {"role": "system", "content": SYSTEM}, {"role": "user", "content": _prompt(batch)}]}, headers)
    return d["choices"][0]["message"]["content"]


BACKENDS = {"claude": _claude, "anthropic": _anthropic, "openai": _openai}


def label(items, backend="claude", model=None, url=None, progress=None):
    """Labels for every item, from the cache or the model. Items are {"agent", "reply"}."""
    model = model or DEFAULT_MODELS[backend]
    known = cached(items, backend, model)
    todo = [i for i in range(len(items)) if i not in known]
    def ask(batch):
        try:
            return _parse(BACKENDS[backend](batch, model, url), len(batch))
        except RuntimeError:
            if len(batch) == 1:
                raise
            half = len(batch) // 2        # a miscounted answer: ask again in two halves
            return ask(batch[:half]) + ask(batch[half:])
    for start in range(0, len(todo), BATCH):
        idx = todo[start:start + BATCH]
        batch = [items[i] for i in idx]
        labels = ask(batch)
        _remember(zip(batch, labels), backend, model)
        known.update(zip(idx, labels))
        if progress:
            progress(min(start + BATCH, len(todo)), len(todo))
    if len(items) > 100:
        _last_path().write_text(json.dumps({"backend": backend, "model": model}))
    return [known[i] for i in range(len(items))]


def _last_path():
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "suspiciousdog" / "classifier.json"


def labels_for(turns, coverage=0.9):
    """{id(turn): label} from the cache of the last classifier run, if it covers most turns; otherwise None."""
    try:
        last = json.loads(_last_path().read_text())
    except (OSError, ValueError):
        return None
    answered, items = items_for(turns)
    known = cached(items, last["backend"], last["model"])
    if not answered or len(known) < coverage * len(answered):
        return None
    return {id(answered[i]): lab for i, lab in known.items()}


def items_for(turns):
    """The turns worth labelling (the ones with a reply), and their items."""
    answered = [t for t in turns if t.reply]
    return answered, [_item(t.final, t.reply) for t in answered]


def agreement(truth, guess):
    hits = sum(1 for a, b in zip(truth, guess) if a == b)
    per = {}
    for lab in LABELS:
        tp = sum(1 for a, b in zip(truth, guess) if a == b == lab)
        fp = sum(1 for a, b in zip(truth, guess) if b == lab and a != lab)
        fn = sum(1 for a, b in zip(truth, guess) if a == lab and b != lab)
        per[lab] = {"precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None}
    return hits / len(truth) if truth else 0.0, per


# Outcomes from the labels, for `sniff --classifier`: same names as the regular ones, read by a model.
def outcomes(labels_by_turn):
    def is_(*wanted):
        return lambda t: labels_by_turn.get(id(t)) in wanted
    return {"complaint": is_("complaint"), "deferral": is_("defers"), "declines": is_("declines"),
            "quick yes": is_("accepts")}
