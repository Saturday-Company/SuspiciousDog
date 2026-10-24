"""When your kit changed, found in the transcripts, and what happened to your answers before and after.

Nobody writes down "installed a plugin on the 6th". The sessions do: the first one that lists it, the last one that
does, the day a CLAUDE.md came in with different content, the day the subagents started answering from another model.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from statistics import median

from .signals import ALL_OUTCOMES
from .stats import benjamini_hochberg, compare, fisher

WINDOW = 5          # sessions on each side of a change that must agree
STEADY = 0.6        # share of sessions that must load an item for it to count as part of the kit
MIN_AFTER = 100     # answered turns on each side of a change before saying anything about it
MIN_EDIT = 50       # characters: smaller edits to an instruction file are typos
DAYS = 14           # turns compared on each side of a change


@dataclass
class Change:
    when: datetime
    what: str
    kind: str                       # added, removed, edited, model, or several of them on one day
    keys: list = field(default_factory=list)
    parts: list = field(default_factory=list)
    sessions: set | None = None     # only these sessions are affected; None means all
    rows: list = field(default_factory=list)
    before: int = 0
    after: int = 0
    medians: dict = field(default_factory=dict)
    together: list = field(default_factory=list)

    @property
    def day(self):
        return f"{self.when:%Y-%m-%d}"


def _when(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()


def _listed(k):
    return k["attachments"].get("skill_listing") or k["attachments"].get("agent_listing_delta")


def _items(kits, origin, installed):
    """Skills, servers and subagents that joined or left the kit."""
    full = [k for k in kits if _listed(k)]
    n, seen = len(full), {}
    for i, k in enumerate(full):
        for key in k["loaded"]:
            if key.split(":", 1)[0] in ("skill", "mcp", "subagent"):
                seen.setdefault(key, []).append(i)
    last_seen = {}
    for k in kits:
        for key in k["loaded"]:
            last_seen[key] = max(last_seen.get(key, ""), k["start"])
    groups = {}
    for key, idx in seen.items():
        first, last = idx[0], idx[-1]
        source = (origin(key, installed) if origin else {}).get("source", "")
        label = source.split(",")[0].split(" (")[0]
        if first >= WINDOW and len(idx) / (n - first) >= STEADY:
            groups.setdefault(("added", full[first]["start"][:10], label), []).append((key, full[first]["start"]))
        if last <= n - 1 - WINDOW and len(idx) / (last - first + 1) >= STEADY and \
                last_seen[key] < full[last + 1]["start"]:
            groups.setdefault(("removed", full[last + 1]["start"][:10], label), []).append((key, full[last + 1]["start"]))
    changes = []
    for (kind, _, label), members in groups.items():
        keys = sorted(key for key, _ in members)
        if len(keys) == 1:
            what = f"{kind} {keys[0].replace(':', ' ', 1)}"
        else:
            kinds = Counter(key.split(":", 1)[0] for key in keys)
            what = f"{kind} " + ", ".join(f"{n} {k}{'s' if n > 1 else ''}" for k, n in kinds.most_common())
        if label:
            what += f" ({label})"
        changes.append(Change(_when(min(stamp for _, stamp in members)), what, kind, keys))
    return changes


def _edits(kits):
    """Instruction files that came in with different content, and stayed that way."""
    changes, history = [], {}
    for k in kits:
        for key, (digest, chars) in k.get("digests", {}).items():
            history.setdefault(key, []).append((k, digest, chars))
    for key, seq in history.items():
        if "/.claude/projects/" in key:
            continue        # the agent's own automatic memory: it changes every day, on its own
        loaders = {k["session"] for k, _, _ in seq}
        scope = None if len(loaders) >= STEADY * len(kits) else loaders
        for i in range(1, len(seq)):
            (_, old, before), (k, new, after) = seq[i - 1], seq[i]
            if new == old or (i + 1 < len(seq) and seq[i + 1][1] != new):
                continue
            delta = after - before
            if abs(delta) < MIN_EDIT:
                continue
            changes.append(Change(_when(k["start"]), f"edited {key.split(':', 1)[1]} ({delta:+,} chars)", "edited",
                                  [key], sessions=scope))
    return changes


def _model_shift(kits, field_name, label):
    """The one split where a model's share changes most, if it changes a lot."""
    rows = [(k, k.get(field_name) or {}) for k in kits if k.get(field_name)]
    if len(rows) < 2 * WINDOW:
        return []
    models = Counter()
    for _, m in rows:
        models.update(m)
    best = None
    totals = [sum(m.values()) for _, m in rows]
    all_runs = sum(totals)
    for model in models:
        hits = [m.get(model, 0) for _, m in rows]
        all_hits, c, d = sum(hits), 0, 0
        for cut in range(len(rows) - WINDOW + 1):
            if cut:
                c, d = c + hits[cut - 1], d + totals[cut - 1]
            if cut < WINDOW:
                continue
            a, b = all_hits - c, all_runs - d
            share_after, share_before = a / b, c / d
            if share_after - share_before < 0.3 or share_after < 0.5:
                continue
            p = fisher(a, b - a, c, d - c)
            if p < 0.001 and (best is None or p < best[0]):
                best = (p, model, cut, share_before, share_after)
    if not best:
        return []
    _, model, cut, before, after = best
    k = rows[cut][0]
    short = model.replace("claude-", "")
    return [Change(_when(k["start"]), f"{label}: {short} {before:.0%} → {after:.0%} of runs", "model",
                   [f"model:{model}"])]


def changes(kits, origin=None, installed=None):
    """One change per day (and per scope): what happens on the same day can't be told apart."""
    single = _items(kits, origin, installed) + _edits(kits)
    single += _model_shift(kits, "models", "main model") + _model_shift(kits, "subagent_models", "subagents")
    days = {}
    for c in sorted(single, key=lambda c: c.when):
        scope = frozenset(c.sessions) if c.sessions else None
        days.setdefault((c.day, scope), []).append(c)
    found = []
    for (_, scope), group in days.items():
        kinds = {c.kind for c in group}
        found.append(Change(group[0].when, "; ".join(c.what for c in group), kinds.pop() if len(kinds) == 1 else "mixed",
                            [k for c in group for k in c.keys], sessions=set(scope) if scope else None,
                            parts=[c.what for c in group]))
    found.sort(key=lambda c: c.when)
    for c in found:
        c.together = [o.what for o in found if o is not c and o.sessions is None
                      and abs((o.when - c.when).total_seconds()) < 3 * 86400]
    return found


def measure(found, turns, days=DAYS, outcomes=None, kits=()):
    """Before/after on the turns around each change, corrected across every change and outcome at once.

    With the kits, also the context each session started with: the real weight of what came in or went out.
    """
    outcomes = outcomes or ALL_OUTCOMES
    answered = [t for t in turns if t.reply and t.when]
    starts = [(_when(k["start"]), k["session"], k["base_tokens"]) for k in kits if k.get("base_tokens")]
    every = []
    for c in found:
        lo, hi = c.when - timedelta(days=days), c.when + timedelta(days=days)
        base = {"before": [b for w, s, b in starts if lo <= w < c.when and (c.sessions is None or s in c.sessions)],
                "after": [b for w, s, b in starts if c.when <= w < hi and (c.sessions is None or s in c.sessions)]}
        near = [t for t in answered if lo <= t.when < hi and (c.sessions is None or t.session in c.sessions)]
        after = [t for t in near if t.when >= c.when]
        c.before, c.after = len(near) - len(after), len(after)
        for side, group in (("before", [t for t in near if t.when < c.when]), ("after", after)):
            tokens = [t.tokens for t in group if t.tokens]
            seconds = [t.seconds for t in group if t.seconds is not None]
            c.medians[side] = {"tokens": median(tokens) if tokens else None,
                               "minutes": median(seconds) / 60 if seconds else None,
                               "base": median(base[side]) if len(base[side]) >= 3 else None}
        c.rows = []
        if c.after >= MIN_AFTER and c.before >= MIN_AFTER:
            c.rows = [(name, compare(near, lambda t, m=c.when: t.when >= m, fn)) for name, fn in outcomes.items()]
            every.extend(r for _, r in c.rows)
    benjamini_hochberg(every)
    return found
