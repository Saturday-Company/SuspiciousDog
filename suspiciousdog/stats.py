"""Exact tests, small enough to read."""

import math


def fisher(a, b, c, d):
    """Two-sided Fisher exact test on [[a, b], [c, d]]."""
    n, row, col = a + b + c + d, a + b, a + c
    if n == 0 or row in (0, n) or col in (0, n):
        return 1.0
    total = math.comb(n, row)

    def p(x):
        return math.comb(col, x) * math.comb(n - col, row - x) / total
    observed = p(a)
    return min(1.0, sum(p(x) for x in range(max(0, row + col - n), min(row, col) + 1)
                        if p(x) <= observed * (1 + 1e-9)))


def benjamini_hochberg(results):
    """Adds a q-value to each result: with many tests, some small p-values are just luck."""
    ordered = sorted(results, key=lambda r: r["p"])
    lowest = 1.0
    for k in range(len(ordered), 0, -1):
        lowest = min(lowest, ordered[k - 1]["p"] * len(ordered) / k)
        ordered[k - 1]["q"] = lowest


def compare(turns, factor, outcome):
    """Outcome rate in turns with the factor vs without it."""
    hits_with = n_with = hits_without = n_without = 0
    for t in turns:
        hit = bool(outcome(t))
        if factor(t):
            n_with += 1
            hits_with += hit
        else:
            n_without += 1
            hits_without += hit
    rate_with = hits_with / n_with if n_with else 0.0
    rate_without = hits_without / n_without if n_without else 0.0
    if rate_without:
        ratio = rate_with / rate_without
    else:
        ratio = float("inf") if rate_with else 1.0
    return {"n_with": n_with, "hits_with": hits_with, "n_without": n_without, "hits_without": hits_without,
            "rate_with": rate_with, "rate_without": rate_without, "ratio": ratio,
            "p": fisher(hits_with, n_with - hits_with, hits_without, n_without - hits_without)}
