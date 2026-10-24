"""The sentinel: reads the sessions again after each one ends, and once a week says what a change of yours did.

"On 24/10 you disabled plugin hyperframes: context at the start 68,210 → 65,800 tokens, nothing got worse in
140 turns." One line, only when there is something measured to say, at most once a week.
"""

import json
import time

from . import brief, service
from .hooks import WEEK

WORSE_UP = {"pushback", "complaint", "interruption", "asks again", "deferral"}


def state_path():
    return brief.cache_dir() / "sentinel.json"


def _state():
    try:
        return json.loads(state_path().read_text())
    except (OSError, ValueError):
        return {"announced": [], "last_shown": 0, "pending": None, "pending_ids": []}


def _save(st):
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st))


def line(c):
    """One sentence about one measured change from the journal."""
    what = c.what.split(" ", 1)[1] if c.what.startswith("#") else c.what
    parts = []
    b, a = c.medians.get("before", {}).get("base"), c.medians.get("after", {}).get("base")
    if b and a:
        parts.append(f"context at the start {round(b):,} → {round(a):,} tokens")
    worse = [(n, r) for n, r in c.rows if r["p"] < 0.05 and
             ((n in WORSE_UP and r["rate_with"] > r["rate_without"]) or
              (n == "quick yes" and r["rate_with"] < r["rate_without"]))]
    better = [(n, r) for n, r in c.rows if r["p"] < 0.05 and (n, r) not in worse]
    for n, r in worse[:1] + better[:1]:
        sure = "" if r.get("q", 1) < 0.05 else " (maybe)"
        parts.append(f"{n} {r['rate_without']:.0%} → {r['rate_with']:.0%}{sure}")
    if not worse:
        parts.append(f"nothing got worse in {c.after} turns")
    return f"SuspiciousDog: on {c.when:%d/%m} you {what[0].lower() + what[1:]}: " + ", ".join(parts) + "."


def refresh(cwd=None):
    """After a session: warm the cache, rebuild the briefs, find what is newly measurable. One at a time."""
    import fcntl
    lock_path = brief.cache_dir() / "sentinel.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return _state()             # another refresh is already running
        return _refresh(cwd)


def _refresh(cwd):
    state = service.State()
    text, numbers = service.brief(state)
    brief.save(text, numbers)
    if cwd:
        text, numbers = service.brief(state, cwd)
        brief.save(text, numbers, service.needle(cwd))
    st = _state()
    _, logged = state.changes
    ready = [c for c in logged if c.rows and c.what.split(" ", 1)[0] not in st["announced"]
             and "(undone)" not in c.what]
    if ready:
        st["pending"] = " ".join(line(c) for c in ready[:2])
        st["pending_ids"] = [c.what.split(" ", 1)[0] for c in ready[:2]]
    _save(st)
    return st


def due(now=None):
    """The line to show at the start of this session, or None. Marks it shown."""
    now = now or time.time()
    st = _state()
    if not st.get("pending") or now - st.get("last_shown", 0) < WEEK:
        return None
    text = st["pending"]
    st["announced"] = st.get("announced", []) + st.get("pending_ids", [])
    st.update(pending=None, pending_ids=[], last_shown=now)
    _save(st)
    return text
