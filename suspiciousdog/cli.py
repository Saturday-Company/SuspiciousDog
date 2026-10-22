"""sdog: sniff your agent sessions for what actually works."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path

from . import __version__, lab, share, synthetic
from .adapters import ADAPTERS, load
from .signals import FACTORS, OUTCOMES
from .stats import compare

DOG = r"""
     /^-----^\
    ( ◔    ◔ )     SuspiciousDog v{v}
     \  ▼  /       {line}
      `---'        {extra}
"""


def _plain():
    return not sys.stdout.isatty() or os.environ.get("NO_COLOR")


def _c(text, code):
    return text if _plain() else f"\033[{code}m{text}\033[0m"


def _pct(x):
    return f"{x:.1%}"


def _ratio(r):
    return "∞" if r == float("inf") else f"{r:.1f}×"


def _verdict(r):
    if r.get("q", 1) < 0.05:
        return _c("real", "1;32")
    if r["p"] < 0.05:
        return _c("maybe", "33")
    return _c("vibes", "2")


def _row(name, r, width=40):
    return (f"    {name[:width]:<{width}} {r['n_with']:>5} turns  {_pct(r['rate_with']):>6} vs {_pct(r['rate_without']):>6}"
            f"  {_ratio(r['ratio']):>6}  {_verdict(r)}")


def _header(turns, per_agent, line=None):
    answered = sum(1 for t in turns if t.reply)
    sessions = sum(per_agent.values())
    agents = ", ".join(f"{a} {n}" for a, n in sorted(per_agent.items())) or "none"
    print(DOG.format(v=__version__, line=f"Sniffed {answered} turns from {sessions} sessions ({agents}).",
                     extra=line or ""))


def _load(args):
    turns, per_agent = load(args.agent, args.path, args.project)
    if not turns:
        where = args.path or ", ".join(ADAPTERS)
        sys.exit(f"Nothing to sniff. No sessions found ({where}). Try `sdog demo`, or `sdog agents` to see where I look.")
    return turns, per_agent


def cmd_sniff(args, turns=None, per_agent=None):
    if turns is None:
        turns, per_agent = _load(args)
        _header(turns, per_agent)
    tables = lab.sniff(turns)
    tests = sum(len(rows) for rows in tables.values())
    for outcome, rows in tables.items():
        if args.outcome and outcome != args.outcome:
            continue
        print(f"  {_c(outcome, '1')} · {_pct(lab.base_rate(turns, OUTCOMES[outcome]))} of turns")
        shown = rows if args.all else [r for r in rows if r[1]["p"] < 0.05][:6] or rows[:3]
        for name, r in shown:
            print(_row(name, r))
        print()
    found = lab.findings(tables)
    print(f"  real = survives the correction for {tests} tests (q < 0.05). maybe = p < 0.05 alone. vibes = vibes.")
    if found:
        print(f"\n  {len(found)} finding{'s' if len(found) != 1 else ''}. Everything else is vibes.")
        outcome, factor, _ = found[0]
        print(f"  Look before you believe:  sdog show \"{factor}\" --outcome {outcome}")
    else:
        print("\n  No findings. Your agent is fine, or you need more sessions. Either way: no new plugins today.")
    print("  Help the pack (counts only, never text):  sdog share\n")


def cmd_test(args):
    turns, per_agent = _load(args)
    expr = args.expression

    def factor(t):
        return bool(eval(expr, {"re": re}, {"t": t}))  # your own hypothesis, on your own machine
    answered = [t for t in turns if t.reply]
    print(f"\n  Hypothesis: {expr}   ({sum(1 for t in answered if factor(t))} of {len(answered)} turns)\n")
    from .stats import benjamini_hochberg
    rows = [(o, compare(answered, factor, fn)) for o, fn in OUTCOMES.items()]
    benjamini_hochberg([r for _, r in rows])
    for outcome, r in rows:
        print(_row(outcome, r, 16))
    print()


def cmd_show(args):
    turns, _ = _load(args)
    if args.factor not in FACTORS:
        sys.exit(f"Unknown factor. Try one of:\n  " + "\n  ".join(FACTORS))
    factor, outcome = FACTORS[args.factor], OUTCOMES[args.outcome]
    hits = [t for t in turns if t.reply and factor(t) and outcome(t)]
    print(f"\n  {len(hits)} turns where the agent did \"{args.factor}\" and the answer was {args.outcome}.\n")
    for t in hits[:args.limit]:
        when = f"{t.when:%Y-%m-%d %H:%M}" if t.when else ""
        print(f"  · {t.agent} · {t.project[-30:]} · {when}")
        print(f"    asked:   {' '.join(t.request.split())[:150]}")
        print(f"    agent:   …{' '.join(t.final.split())[-150:]}")
        print(f"    reply:   {' '.join(t.reply.split())[:150]}\n")


def _change_date(target):
    p = Path(target).expanduser()
    if not p.exists():
        return datetime.fromisoformat(target).astimezone()
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cI", "--", p.name], cwd=p.parent,
                             capture_output=True, text=True, timeout=10).stdout.strip()
        if out:
            return datetime.fromisoformat(out).astimezone()
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return datetime.fromtimestamp(p.stat().st_mtime).astimezone()


def cmd_before_after(args):
    turns, per_agent = _load(args)
    moment = _change_date(args.when)
    rows = lab.before_after(turns, moment)
    before = sum(1 for t in turns if t.reply and t.when and t.when < moment)
    after = sum(1 for t in turns if t.reply and t.when and t.when >= moment)
    print(f"\n  Change at {moment:%Y-%m-%d %H:%M}. {before} turns before, {after} after.\n")
    print(f"    {'outcome':<16} {'after':>6} vs {'before':>6}")
    for outcome, r in rows:
        print(f"    {outcome:<16} {_pct(r['rate_with']):>6} vs {_pct(r['rate_without']):>6}  {_ratio(r['ratio']):>6}  {_verdict(r)}")
    if after < 100:
        print(f"\n  Only {after} turns since the change. Keep working; ask me again in a week.")
    print()


def cmd_share(args):
    turns, per_agent = _load(args)
    data = share.payload(lab.sniff(turns), turns, per_agent)
    share.validate(data)
    if args.save:
        Path(args.save).write_text(json.dumps(data, indent=1) + "\n")
        print(f"  Saved {args.save}. Nothing left your machine.")
        return
    print("\n  This is everything that would be shared. Counts and our own factor names. No prompts, no replies,")
    print("  no paths, no project names. It goes to a public GitHub issue, under your account.\n")
    print(json.dumps(data, indent=1))
    if not args.yes:
        if input("\n  Open the issue? [y/N] ").strip().lower() not in ("y", "yes"):
            print("  Fine. Nothing left your machine.")
            return
    url = share.issue_url(data)
    if url:
        print(f"\n  Opening: {url[:90]}…")
        webbrowser.open(url)
        print("  Press 'Create' on GitHub. Thanks. The pack gets a little less gullible.")
    else:
        out = Path("suspiciousdog-share.json")
        out.write_text(json.dumps(data))
        print(f"\n  Too big for a link. Saved {out}. Open https://github.com/{share.REPO}/issues/new?template=share-results.yml")
        print("  and paste it in.")


def cmd_demo(args):
    folder = synthetic.write(Path(tempfile.mkdtemp(prefix="sdog-demo-")))
    turns, per_agent = load("jsonl", folder)
    _header(turns, per_agent, _c("SYNTHETIC DATA. Made up for the demo. Nobody typed this.", "1;35"))
    cmd_sniff(args, turns, per_agent)


def cmd_agents(args):
    print()
    for name, a in ADAPTERS.items():
        paths = a.default_paths()
        print(f"  {name:<12} {a.STATUS:<7} {len(paths):>5} session files")
    print("\n  Anything else: convert it to the open format (see `sdog format`) and pass --path.\n")


def cmd_format(args):
    from .adapters import generic
    print(generic.__doc__)


def cmd_factors(args):
    print("\n  factors:\n    " + "\n    ".join(FACTORS))
    print("\n  outcomes:\n    " + "\n    ".join(OUTCOMES) + "\n")


def cmd_provenance(args):
    from . import provenance
    provenance.main(args)


def main(argv=None):
    p = argparse.ArgumentParser(prog="sdog", description="Sniff your AI agent sessions for what actually works.")
    p.add_argument("--version", action="version", version=f"suspiciousdog {__version__}")
    sub = p.add_subparsers(dest="command")

    def add(name, fn, help_text, sessions=True):
        s = sub.add_parser(name, help=help_text)
        s.set_defaults(fn=fn)
        if sessions:
            s.add_argument("--agent", choices=list(ADAPTERS), help="only this agent")
            s.add_argument("--path", help="a file or folder of sessions instead of the default places")
            s.add_argument("--project", help="only sessions whose path contains this")
        return s

    s = add("sniff", cmd_sniff, "every factor against every outcome")
    s.add_argument("--outcome", choices=list(OUTCOMES))
    s.add_argument("--all", action="store_true", help="show every row, vibes included")
    s = add("test", cmd_test, "your own hypothesis, as a Python expression over the turn `t`")
    s.add_argument("expression", help='e.g. "t.tool_calls > 40" or "\'sorry\' in t.final.lower()"')
    s = add("show", cmd_show, "the actual turns behind a number")
    s.add_argument("factor")
    s.add_argument("--outcome", choices=list(OUTCOMES), default="pushback")
    s.add_argument("--limit", type=int, default=12)
    s = add("before-after", cmd_before_after, "did a change help? a date, or a file like CLAUDE.md / AGENTS.md")
    s.add_argument("when", help="YYYY-MM-DD, or a path: its last commit (or modification) is the moment")
    s = add("share", cmd_share, "send the counts (never text) to the public dataset")
    s.add_argument("--yes", action="store_true", help="don't ask")
    s.add_argument("--save", metavar="FILE", help="write the counts to a file instead of opening an issue")
    s = add("demo", cmd_demo, "sniff synthetic sessions, to see what it looks like", sessions=False)
    s.add_argument("--outcome", choices=list(OUTCOMES))
    s.add_argument("--all", action="store_true")
    add("agents", cmd_agents, "which agents I can read, and where", sessions=False)
    add("format", cmd_format, "the open session format, for any other agent", sessions=False)
    add("factors", cmd_factors, "list factors and outcomes", sessions=False)
    s = sub.add_parser("provenance", help="experiment 1: names written from memory (Claude Code only)")
    s.set_defaults(fn=cmd_provenance)
    s.add_argument("session", nargs="?", help="a session file; default: your latest")
    s.add_argument("--history", action="store_true", help="every session: do names from memory fail more?")
    s.add_argument("--world", action="store_true", help="also search repos, dependencies and man pages (slow)")

    args = p.parse_args(argv)
    if not getattr(args, "fn", None):
        args = p.parse_args(["sniff", *(argv or sys.argv[1:])])
    args.fn(args)
