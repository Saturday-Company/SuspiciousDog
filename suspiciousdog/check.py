"""Before adding a rule: does the problem it fixes show up in the sessions at all, and is it already said?

A rule in CLAUDE.md is paid for in every session. "Always read the schema before writing SQL" is worth it if the
agent keeps writing SQL against tables it never looked at; it is dead weight if that never happens, and a repeat if
the MCP server's own instructions already say so.
"""

import re
from collections import Counter

from . import rules
from .failures import FIX
from .kit import tokens

GENERIC = {"claude", "plugin", "server", "tools", "tool", "skill", "skills", "code", "best", "practices", "mcp",
           "official", "anthropic", "local", "remote", "agent", "with", "from"}
AGENT_SIDE = {"wrong arguments", "wrong target", "bad code", "not found", "not loaded", "setup"}


def _sentences(text):
    for line in text.splitlines():
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = re.sub(r"[*_`#>|]", "", part).strip(" -")
            if len(part.split()) >= 5:
                yield part


def _names(it):
    return {w for w in re.split(r"[^a-z0-9]+", it.name.lower()) if len(w) >= 4 and w not in GENERIC}


def check(text, turns, items, loaded, sessions=0, weeks=1.0):
    """What the user's own data says about a rule they are about to add. A dict, for people and for agents."""
    words = rules.stems(text)
    said_words = set(re.findall(r"[a-z0-9]+", text.lower()))
    out = {"rule": text, "weight_tokens": tokens(len(text)), "sessions_a_week": round(sessions / max(weeks, 1e-9)),
           "can_see": "instruction files, MCP server instructions and skill descriptions of the latest session; "
                      "not the agent's own system prompt",
           "already_loaded": [], "corrections": {"count": 0, "examples": []}, "tools": [], "projects": {}}
    # Already in the context?
    need = max(3, round(0.5 * len(words)))
    similar = []
    for key, body in loaded.items():
        for sentence in _sentences(body):
            shared = words & rules.stems(sentence)
            if len(shared) >= need:
                similar.append((len(shared), key, sentence))
    for _, key, sentence in sorted(similar, key=lambda x: -x[0])[:3]:
        out["already_loaded"].append({"where": key, "text": sentence[:200]})
    # Do the user's corrections say it?
    want = max(2, round(0.4 * len(words)))
    echoed = [t for t in rules.corrections(turns) if len(words & rules.stems(t.reply)) >= want]
    out["corrections"] = {"count": len(echoed),
                          "examples": [" ".join(t.reply.split())[:140] for t in echoed[-3:]]}
    places = Counter(t.project for t in echoed)
    # Do the tools it names fail, and for a reason a rule can fix?
    exact = set(re.findall(r"[A-Za-z0-9_]+", text))
    for it in sorted(items.values(), key=lambda it: -it.calls):
        if it.kind not in ("mcp", "tool", "skill") or not it.calls:
            continue
        if not (it.name in exact if it.kind == "tool" else _names(it) & said_words):
            continue        # built-in tools only by their exact name: "read the schema" is not the Read tool
        kinds = {k: n for k, n in it.error_kinds.most_common() if k != "other"}
        top = next(iter(kinds), None)
        out["tools"].append({"name": it.key, "calls": it.calls, "fail_rate": round(it.error_rate, 3),
                             "why": kinds, "fix": FIX.get(top, "") if top else "",
                             "verdict": it.verdict})
        places.update({p: n for p, n in it.projects.items()})
        if len(out["tools"]) == 3:
            break
    total = sum(places.values())
    if total:
        home, n = places.most_common(1)[0]
        out["projects"] = {"main": home, "share": round(n / total, 2)}
    out["verdict"], out["advice"] = _verdict(out, sum(1 for t in turns if t.reply))
    return out


def _verdict(r, answered):
    cost = f"~{r['weight_tokens']} tokens in every session"
    tools = [t for t in r["tools"] if t["calls"] >= 20 and t["fail_rate"] >= 0.05 and set(t["why"]) & AGENT_SIDE]
    where = ""
    if r["projects"].get("share", 0) >= 0.8:
        where = f" Most of it is in one project ({r['projects']['main']}): put the rule in that project's file."
    if r["already_loaded"]:
        a = r["already_loaded"][0]
        return "already said", (f"Something close is already loaded ({a['where']}): \"{a['text'][:120]}\". "
                                f"Saying it twice costs {cost}; if it isn't followed, make that line more concrete, "
                                f"or turn it into a hook.")
    if r["corrections"]["count"] >= 3 or tools:
        why = []
        if r["corrections"]["count"]:
            why.append(f"you corrected this {r['corrections']['count']} times")
        for t in tools[:2]:
            kind = next(k for k in t["why"] if k in AGENT_SIDE)
            why.append(f"{t['name']} fails {t['fail_rate']:.0%} of {t['calls']} calls, often {kind}")
        return "supported", (f"The problem is in your sessions: {'; '.join(why)}. Worth {cost}. Once it's in, "
                             f"`sdog timeline` measures it from that day.{where}")
    if r["corrections"]["count"] or r["tools"]:
        return "weak", (f"A little evidence ({r['corrections']['count']} corrections, "
                        f"{len(r['tools'])} related tools that rarely fail). It would cost {cost}. Add it if it "
                        f"matters to you, and check `sdog timeline` in two weeks.{where}")
    return "no evidence", (f"Nothing in {answered:,} answered turns shows this problem. It would cost {cost}. "
                           f"Skip it, or add it and check `sdog timeline` in two weeks.")
