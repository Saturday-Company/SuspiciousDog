"""Made-up sessions for the demo and the tests. Nobody typed these. They say so on every line."""

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

AGENTS = ("claude-code", "codex", "gemini")
REQUESTS = [
    "fix the login form, it accepts empty emails",
    "add pagination to the orders table",
    "why is the build failing on CI?",
    "rename the invoices module to billing",
    "make the dashboard load faster",
    "write tests for the cart total",
    "You are a senior engineer. Review the payment flow end to end and fix what you find, keeping the public API "
    "stable, adding tests where coverage is thin, and documenting anything surprising in the README so the next "
    "person does not have to rediscover it. Do not touch the database schema without asking first, and keep the "
    "commits small.",
]
OFFERS = ["Done. I could also add caching to the API. Shall I?", "Fixed. Want me to refactor the helpers too?"]
DONE = ["Fixed, the form now rejects empty emails.", "Done: pagination works with 20 rows per page."]
QUESTIONS = ["Which date format should the invoices use?"]
REPLIES_YES = ["ok", "go ahead", "perfect, thanks", "yes"]
REPLIES_LATER = ["not now, put it on the backlog", "later, maybe", "leave it for now"]
REPLIES_PUSHBACK = ["no, it still doesn't work", "that's not what I asked", "still broken on mobile"]
REPLIES_OTHER = ["now look at the settings page", "how much would this cost per month?", "next: the export button"]


def _turn_records(rng, when):
    request = rng.choice(REQUESTS)
    records = [{"type": "user", "text": request, "ts": when.isoformat()}]
    edits = rng.random() < 0.55
    calls = rng.randint(1, 60) if edits else rng.randint(0, 6)
    for i in range(calls):
        if edits and i == calls // 2:
            records.append({"type": "tool_call", "name": "edit_file", "category": "edit", "detail": "src/app.py"})
        else:
            cat = rng.choice(("read", "search", "shell", "read"))
            records.append({"type": "tool_call", "name": cat, "category": cat,
                            "detail": "npm test" if cat == "shell" else "src/app.py"})
        records.append({"type": "tool_result", "error": rng.random() < 0.04})
    if rng.random() < 0.06:
        records.append({"type": "tool_call", "name": "spawn_agent", "category": "subagent", "detail": ""})
        records.append({"type": "tool_result", "error": False})
    style = rng.random()
    if style < 0.06:
        final, offer = rng.choice(OFFERS), True
    elif style < 0.15:
        final, offer = rng.choice(QUESTIONS), False
    else:
        final, offer = rng.choice(DONE), False
    records.append({"type": "assistant", "text": final})
    if calls > 40 and rng.random() < 0.03:
        records.append({"type": "interrupt"})
    # The planted effect: offering more work gets deferred far more often. Everything else is noise.
    roll = rng.random()
    if offer:
        reply = (REPLIES_LATER if roll < 0.12 else REPLIES_YES if roll < 0.5 else REPLIES_OTHER)
    else:
        reply = (REPLIES_LATER if roll < 0.013 else REPLIES_PUSHBACK if roll < 0.045 else
                 REPLIES_YES if roll < 0.17 else REPLIES_OTHER)
    return records, rng.choice(reply)


def write(folder, sessions=300, seed=7):
    """Writes synthetic sessions in the open JSONL format and returns the folder."""
    rng = random.Random(seed)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    for s in range(sessions):
        agent = AGENTS[s % len(AGENTS)]
        when = start + timedelta(hours=rng.randint(0, 24 * 50))
        lines = [{"type": "session", "id": f"synthetic-{s:04d}", "agent": agent, "project": "synthetic-demo",
                  "synthetic": True}]
        pending = None
        for _ in range(rng.randint(2, 5)):
            records, reply = _turn_records(rng, when)
            if pending:
                records[0]["text"] = pending
            lines.extend(records)
            pending = reply
            when += timedelta(minutes=rng.randint(2, 40))
        lines.append({"type": "user", "text": pending, "ts": when.isoformat()})
        with open(folder / f"synthetic-{s:04d}.jsonl", "w") as f:
            f.write("\n".join(json.dumps(r) for r in lines) + "\n")
    return folder
