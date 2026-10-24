"""The pack page: every share, added up. Run by .github/workflows/pack.yml; locally:

    gh api --paginate "repos/Saturday-Company/SuspiciousDog/issues?labels=results&state=open&per_page=100" \
        --jq '.[]' > issues.jsonl
    python scripts/pack.py issues.jsonl site

Issues are written by anyone, so they are data: a share counts only if `share.validate` accepts it (our own
vocabulary, public names, integers), and nothing from an issue reaches the page except those names and numbers.
"""

import json
import os
import re
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from suspiciousdog import share                             # noqa: E402
from suspiciousdog.report import CSS                        # noqa: E402
from suspiciousdog.stats import benjamini_hochberg, fisher  # noqa: E402

MIN_SHARES_FOR_ITEM = 2     # a public item shows up once two people have it: one share is one person's kit


def shares(lines):
    """Valid payloads from the open issues: the latest one per GitHub account, so one person counts once."""
    latest = {}
    for line in lines:
        try:
            issue = json.loads(line)
        except ValueError:
            continue
        if not isinstance(issue, dict) or issue.get("pull_request") or issue.get("state", "open") != "open":
            continue
        if any(label.get("name") in ("invalid", "spam") for label in issue.get("labels") or []):
            continue
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", issue.get("body") or "", re.S)
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
            share.validate(data)
        except (ValueError, AssertionError, TypeError, KeyError, AttributeError):
            continue
        who = str((issue.get("user") or {}).get("login") or f"issue-{issue.get('number')}")
        if who not in latest or issue.get("number", 0) > latest[who][0]:
            latest[who] = (issue.get("number", 0), data)
    return [data for _, data in latest.values()]


def add_up(found):
    agents, turns = {}, 0
    cells = {}
    for d in found:
        turns += d["turns"]
        for a, n in d["agents"].items():
            agents[a] = agents.get(a, 0) + n
        for f, o, nw, hw, nwo, hwo in d["results"]:
            c = cells.setdefault((f, o), [0, 0, 0, 0, 0, 0])
            c[0] += nw
            c[1] += hw
            c[2] += nwo
            c[3] += hwo
            if nw and nwo:
                c[4] += 1
                c[5] += (hw / nw) > (hwo / nwo)
    rows = []
    for (f, o), (nw, hw, nwo, hwo, n, up) in cells.items():
        if nw >= 10 and nwo >= 10:
            try:
                p = fisher(hw, nw - hw, hwo, nwo - hwo)
            except (ValueError, OverflowError):
                continue
            rows.append({"factor": f, "outcome": o, "with": hw / nw, "without": hwo / nwo, "turns": nw,
                         "p": p, "shares": n, "same_way": up})
    benjamini_hochberg(rows)
    rows.sort(key=lambda r: r["p"])
    items = {}
    kits = [d["kit"] for d in found if "kit" in d]
    for k in kits:
        for name, loaded, used, calls, errors, weight in k["items"]:
            it = items.setdefault(name, {"name": name, "shares": 0, "loaded": 0, "used": 0, "calls": 0, "errors": 0,
                                         "weights": []})
            it["shares"] += 1
            it["loaded"] += loaded
            it["used"] += used
            it["calls"] += calls
            it["errors"] += errors
            it["weights"].append(weight)
    table = []
    for it in items.values():
        if it["shares"] < MIN_SHARES_FOR_ITEM:
            continue
        w = sorted(it.pop("weights"))
        it["weight"] = w[len(w) // 2]
        table.append(it)
    table.sort(key=lambda it: -it["loaded"])
    context = sorted(k["context_tokens"] for k in kits if k["context_tokens"])
    return {"shares": len(found), "agents": agents, "turns": turns, "kits": len(kits),
            "context_tokens": context[len(context) // 2] if context else None,
            "results": rows, "items": table}


def page(pack):
    e = escape
    tiles = [(pack["shares"], "shares"), (f"{pack['turns']:,}", "answered turns"),
             (f"{pack['context_tokens']:,}" if pack["context_tokens"] else "–", "tokens before the first word (median)"),
             (", ".join(f"{a} {n}" for a, n in sorted(pack["agents"].items())), "sessions per agent")]
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
           f"content='width=device-width,initial-scale=1'><title>The pack</title><style>{CSS}</style></head><body><main>"
           "<h1>What the pack found</h1><div class='mute'>Every <code>sdog share</code>, added up. Counts only: no "
           "prompts, no replies, no paths, no private names. Updated by a GitHub Action from the shared issues.</div>"
           "<div class='tiles'>" + "".join(f"<div class='tile'><b>{e(str(v))}</b><span>{e(t)}</span></div>"
                                          for v, t in tiles) + "</div>"]
    out.append("<h2>Habits and answers</h2><div class='mute'>Every factor against every outcome, all shares pooled, "
               "with the Benjamini-Hochberg correction. \"Same way\" counts the shares where the factor went with "
               "more of the outcome: a pooled result that only one heavy user drives shows up here.</div>"
               "<div class='wrap'><table><thead><tr><th>factor</th><th>outcome</th><th class='n'>turns</th>"
               "<th class='n'>with</th><th class='n'>without</th><th class='n'>same way</th><th>verdict</th></tr>"
               "</thead><tbody>")
    for r in pack["results"][:40]:
        verdict = "real" if r["q"] < 0.05 else "maybe" if r["p"] < 0.05 else "vibes"
        out.append(f"<tr><td>{e(r['factor'].replace('_', ' '))}</td><td>{e(r['outcome'].replace('_', ' '))}</td>"
                   f"<td class='n'>{r['turns']:,}</td><td class='n'>{r['with']:.1%}</td>"
                   f"<td class='n'>{r['without']:.1%}</td><td class='n'>{r['same_way']} of {r['shares']}</td>"
                   f"<td class='v v-{'earns' if verdict == 'real' else 'rare' if verdict == 'maybe' else 'new'}'>"
                   f"{verdict}</td></tr>")
    out.append("</tbody></table></div>")
    if pack["items"]:
        out.append(f"<h2>Public plugins, servers and tools</h2><div class='mute'>From {pack['kits']} shared kits. An "
                   f"item shows up once {MIN_SHARES_FOR_ITEM} shares have it. Used = sessions that used it ÷ sessions "
                   "that loaded it.</div><div class='wrap'><table><thead><tr><th>name</th><th class='n'>shares</th>"
                   "<th class='n'>sessions</th><th class='n'>used</th><th class='n'>~tokens</th><th class='n'>calls"
                   "</th><th class='n'>fail</th></tr></thead><tbody>")
        for it in pack["items"]:
            use = it["used"] / it["loaded"] if it["loaded"] else 0
            fail = f"{it['errors'] / it['calls']:.1%}" if it["calls"] else ""
            out.append(f"<tr><td class='name'>{e(it['name'])}</td><td class='n'>{it['shares']}</td>"
                       f"<td class='n'>{it['loaded']:,}</td><td class='n'>{use:.0%}</td><td class='n'>{it['weight']}"
                       f"</td><td class='n'>{it['calls']:,}</td><td class='n'>{fail}</td></tr>")
        out.append("</tbody></table></div>")
    out.append("<footer>Add yours: <code>pipx install git+https://github.com/Saturday-Company/SuspiciousDog</code>, "
               "then <code>sdog share</code>. It shows you everything before it sends anything. "
               "github.com/Saturday-Company/SuspiciousDog</footer></main></body></html>")
    return "".join(out)


EMPTY = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
         f"content='width=device-width,initial-scale=1'><title>The pack</title><style>{CSS}</style></head><body><main>"
         "<h1>What the pack found</h1><p class='mute'>No shares right now. <code>sdog share</code> adds yours.</p>"
         "</main></body></html>")


def main(source, target):
    found = shares(Path(source).read_text().splitlines())
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"shares={len(found)}\n")
    print(f"{len(found)} valid shares")
    out = Path(target)
    out.mkdir(parents=True, exist_ok=True)
    if not found:           # written, but deployed only if the page was already up (see pack.yml)
        (out / "index.html").write_text(EMPTY)
        return
    pack = add_up(found)
    (out / "index.html").write_text(page(pack))
    (out / "pack.json").write_text(json.dumps(pack, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:3])
