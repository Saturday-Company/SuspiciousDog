"""Every factor against every outcome, corrected for the number of tests."""

from .signals import FACTORS, OUTCOMES
from .stats import benjamini_hochberg, compare

MIN_TURNS = 10


def sniff(turns, factors=None, outcomes=None):
    """{outcome: [(factor, result), ...]} for the turns that got an answer, sorted by p-value."""
    answered = [t for t in turns if t.reply]
    factors = factors or FACTORS
    outcomes = outcomes or OUTCOMES
    tables = {}
    for o_name, outcome in outcomes.items():
        rows = [(f_name, compare(answered, factor, outcome)) for f_name, factor in factors.items()]
        tables[o_name] = [(f, r) for f, r in rows if r["n_with"] >= MIN_TURNS and r["n_without"] >= MIN_TURNS]
    benjamini_hochberg([r for rows in tables.values() for _, r in rows])
    for o_name in tables:
        tables[o_name].sort(key=lambda row: row[1]["p"])
    return tables


def base_rate(turns, outcome):
    answered = [t for t in turns if t.reply]
    return sum(1 for t in answered if outcome(t)) / len(answered) if answered else 0.0


def findings(tables):
    """Results that survive the correction for multiple tests."""
    return [(o, f, r) for o, rows in tables.items() for f, r in rows if r.get("q", 1) < 0.05]


def before_after(turns, moment, outcomes=None):
    """Each outcome before and after a moment (a rule added, a plugin installed, a model switched)."""
    answered = [t for t in turns if t.reply and t.when]

    def after(t):
        return t.when >= moment
    rows = [(o, compare(answered, after, fn)) for o, fn in (outcomes or OUTCOMES).items()]
    benjamini_hochberg([r for _, r in rows])
    return rows
