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
from .signals import ALL_OUTCOMES, EXTRA_OUTCOMES, FACTORS, OUTCOMES
from .failures import FIX, SHORT
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
    print("  What you load and never use:  sdog kit")
    print("  Help the pack (counts only, never text):  sdog share\n")


def cmd_test(args):
    turns, per_agent = _load(args)
    expr = args.expression

    def factor(t):
        return bool(eval(expr, {"re": re}, {"t": t}))  # your own hypothesis, on your own machine
    answered = [t for t in turns if t.reply]
    print(f"\n  Hypothesis: {expr}   ({sum(1 for t in answered if factor(t))} of {len(answered)} turns)\n")
    from .stats import benjamini_hochberg
    rows = [(o, compare(answered, factor, fn)) for o, fn in ALL_OUTCOMES.items()]
    benjamini_hochberg([r for _, r in rows])
    for outcome, r in rows:
        print(_row(outcome, r, 16))
    print()


def cmd_show(args):
    turns, _ = _load(args)
    if args.factor not in FACTORS:
        sys.exit(f"Unknown factor. Try one of:\n  " + "\n  ".join(FACTORS))
    factor, outcome = FACTORS[args.factor], ALL_OUTCOMES[args.outcome]
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
    print("\n  outcomes:\n    " + "\n    ".join(OUTCOMES) + "\n    " + "\n    ".join(f"{o}  (0.2, not in sniff)" for o in EXTRA_OUTCOMES) + "\n")


def cmd_provenance(args):
    from . import provenance
    provenance.main(args)


SECTIONS = (
    ("ballast", "BALLAST · loaded, never used"),
    ("rare", "RARE · used in under 5% of the sessions that load it"),
    ("elsewhere", "ELSEWHERE · used in one project, loaded everywhere"),
    ("misused", "MISUSED · fails far more often than your other tools"),
    ("earns", "EARNS ITS PLACE"),
    ("hook", "HOOKS"),
)


def _kit(args):
    from . import kit
    from .adapters import claude_code
    kits = kit.scan(args.agent, args.path, args.project, cache=not args.no_cache)
    if not kits:
        sys.exit("No sessions with a readable kit. For now that means Claude Code (`sdog doctor` says what I can read).")
    items = kit.ledger(kits, claude_code.config(), claude_code.origin)
    return kits, items, kit.summary(kits, items)


def _n(x):
    return f"{x:,}"


def _label(source):
    """The short form of where something comes from: "plugin hyperframes", "claude.ai connector"."""
    for long, short in (("not in your config", ""), ("instruction file", ""), ("hook (", ""), ("built in", "")):
        if source.startswith(long):
            return short
    words = source.replace("@", " ").replace(",", " ").split()
    return " ".join(words[:2])


def _place(project):
    """The last two folders of a project: "witdesk-progetto/witdesk"."""
    return "/".join(project.rstrip("/").split("/")[-2:]) if "/" in project else project[-28:]


def _kit_row(it):
    where = _label(it.origin.get("source", ""))
    name = it.name[-36:] if it.kind == "hook" else it.name[:36]
    if it.verdict == "misused":
        numbers = f"{_n(it.calls):>5} calls {it.error_rate:>5.1%} fail"
        extra = f"{it.retries} retried" + (f", {it.denied} denied" if it.denied else "")
    elif it.verdict == "hook":
        numbers = f"{_n(it.calls):>5} fired {it.errors:>3} blocks"
        extra = f"{it.used} sessions"
    else:
        numbers = f"{it.used:>3} of {it.loaded:<4} sessions"
        extra = f"~{_n(it.weight)} tok"
    return f"    {it.kind:<7} {name:<36} {numbers:<22} {extra:<14} {_c(where, '2')}".rstrip()


def _detail(it, changes=()):
    print(f"\n  {_c(it.key, '1')} · {_c(it.verdict, '1;33' if it.verdict in ('ballast', 'misused', 'rare') else '1')}"
          f"   {it.why}\n")
    print(f"    loaded   in {it.loaded} sessions ({it.first} → {it.last}), used in {it.used}")
    if it.kind not in ("tool", "hook"):
        print(f"    weight   ~{_n(it.weight)} tokens each time, ~{_n(it.weight * it.loaded)} in all (characters ÷ 4)")
    if it.calls:
        print(f"    calls    {_n(it.calls)}, {it.errors} failed ({it.error_rate:.1%}), {it.retries} retried right away"
              + (f", {it.denied} denied by you" if it.denied else ""))
    if it.origin.get("source"):
        print(f"    from     {it.origin['source']}")
    if it.origin.get("remove") and it.verdict in ("ballast", "rare", "elsewhere"):
        hint = it.origin["remove"]
        if it.verdict == "elsewhere":
            hint = f"keep it only for {_place(it.origin['home'])}: " + hint
        print(f"    to drop  {hint}")
    if it.projects:
        print("    used in  " + " · ".join(f"{_place(p)} {n}" for p, n in it.projects.most_common(4)))
    failing = sorted(((t, c, e) for t, (c, e) in it.tools.items() if e), key=lambda x: -x[2])
    if failing and len(it.tools) > 1:
        print("    fails in " + " · ".join(f"{t} {e}/{c}" for t, c, e in failing[:4]))
    if it.error_kinds:
        print("    why      " + " · ".join(f"{w} {n}" for w, n in it.error_kinds.most_common(4)))
        top = next((w for w, _ in it.error_kinds.most_common() if w != "other"), "other")
        if FIX.get(top):
            print(f"    so       {FIX[top]}")
    for why, text in it.samples:
        print(f"    failed   [{why}] {text[:130]}")
    if changes:
        print()
        for c in changes:
            print(f"    {c.day}  {c.what[:110]}")
    print()


def cmd_kit(args):
    from . import kit
    kits, items, s = _kit(args)
    rows = sorted(items.values(), key=lambda it: (-(it.chars * it.loaded), -it.calls))
    if args.kind:
        rows = [it for it in rows if it.kind == args.kind]
    if args.json:
        print(json.dumps({"summary": s, "items": [
            {"key": it.key, "kind": it.kind, "name": it.name, "verdict": it.verdict, "why": it.why,
             "loaded_sessions": it.loaded, "used_sessions": it.used, "calls": it.calls, "errors": it.errors,
             "retries": it.retries, "denied": it.denied, "weight_tokens": it.weight, "first": it.first,
             "last": it.last, "source": it.origin.get("source", ""), "remove": it.origin.get("remove", ""),
             "used_in": dict(it.projects.most_common(5)), "failures": it.samples} for it in rows]}, indent=1))
        return
    if args.name:
        needle = args.name.lower()
        found = [it for it in rows if needle in (it.name.lower(), it.key.lower())] or \
                [it for it in rows if needle in it.key.lower()]
        if not found:
            sys.exit(f"Nothing in the kit matches {args.name!r}. `sdog kit --all` lists everything.")
        found.sort(key=lambda it: (needle not in (it.name.lower(), it.key.lower()), -(it.calls + it.loaded)))
        from . import timeline
        from .adapters import claude_code
        mine = [c for c in timeline.changes(kits, claude_code.origin, claude_code.config()) if found[0].key in c.keys]
        _detail(found[0], mine)
        if len(found) > 1:
            print(_c("  Also matching: " + ", ".join(it.key for it in found[1:6]) + ("…" if len(found) > 6 else ""), "2"))
            print()
        return
    agents = ", ".join(f"{a} {n}" for a, n in sorted(s["agents"].items()))
    base = f"{_n(s['base_tokens'])} tokens before you type a word (first call, on average)." if s["base_tokens"] else ""
    print(DOG.format(v=__version__, line=f"Went through the kit of {s['sessions']} sessions ({agents}), "
                     f"{s['first']} → {s['last']}.", extra=base))
    listed = s["listed_tokens"]
    names = {"mcp": "MCP servers", "skill": "skills", "instructions": "instruction files", "subagent": "subagents"}
    parts = [f"{names[k]} ~{_n(v)}" for k, v in sorted(listed.items(), key=lambda kv: -kv[1]) if k in names]
    if parts:
        print(f"  What I can name in each session: {' · '.join(parts)} tokens (estimates).")
    if s["ballast_tokens"]:
        print(f"  {_c('~' + _n(s['ballast_tokens']) + ' tokens a session', '1')} go to things you have never used.")
    print()
    limit = None if args.all else 8
    for verdict, title in SECTIONS:
        part = [it for it in rows if it.verdict == verdict]
        if verdict == "misused":
            part.sort(key=lambda it: -it.errors)
        if verdict in ("earns", "hook"):
            part.sort(key=lambda it: -it.calls)
        if not part:
            continue
        print(f"  {_c(title, '1')}")
        for it in part[:limit]:
            print(_kit_row(it))
        if limit and len(part) > limit:
            more = part[limit:]
            weight = kit.tokens(sum(it.chars * it.loaded for it in more) / s["sessions"])
            print(_c(f"    + {len(more)} more" + (f", ~{_n(weight)} tokens a session" if verdict == "ballast" else "")
                     + f"   (sdog kit --all)", "2"))
        print()
    fixed = [it for it in rows if it.verdict == "fixed" and not it.used]
    new = [it for it in rows if it.verdict == "new"]
    if fixed:
        print(f"  Built in and never used: {len(fixed)} items, ~{_n(sum(it.weight for it in fixed))} tokens. "
              f"Not yours to remove.")
    if new:
        print(f"  Too new to judge: {len(new)} items, loaded in fewer than 20 sessions.")
    from . import timeline
    from .adapters import claude_code
    recent = timeline.changes(kits, claude_code.origin, claude_code.config())[-3:]
    if recent:
        print(f"\n  {_c('LATEST CHANGES', '1')}  (did they help? sdog timeline)")
        for c in reversed(recent):
            print(f"    {c.day}  {c.parts[0][:90]}" + (_c(f"  + {len(c.parts) - 1} more", "2") if len(c.parts) > 1 else ""))
    worst = next((it for verdict in ("ballast", "misused", "rare") for it in rows if it.verdict == verdict), None)
    if worst:
        print(f"\n  Look closer:  sdog kit {worst.name}")
    print("  Nothing here changed anything. I only read your transcripts.\n")


def _change_rows(c):
    """What moved after a change, in one or two lines."""
    from .timeline import MIN_AFTER
    if not c.rows:
        need = "turns after" if c.after < MIN_AFTER else "turns before"
        return [_c(f"too early: {c.before} turns before, {c.after} after (I need {MIN_AFTER} {need})", "2")]
    moved = [(name, r) for name, r in c.rows if r["p"] < 0.05]
    out = []
    for name, r in moved:
        out.append(f"{name} {_pct(r['rate_without'])} → {_pct(r['rate_with'])}  {_verdict(r)}")
    if not moved:
        out.append(_c(f"nothing moved ({c.before} turns before, {c.after} after)", "2"))
    b, a = c.medians.get("before", {}), c.medians.get("after", {})
    if b.get("tokens") and a.get("tokens"):
        out.append(_c(f"median turn: {_n(round(b['tokens']))} → {_n(round(a['tokens']))} output tokens, "
                      f"{b['minutes']:.1f} → {a['minutes']:.1f} min", "2"))
    return out


def cmd_timeline(args):
    from . import timeline
    from .adapters import claude_code
    kits, _, _ = _kit(args)
    found = timeline.changes(kits, claude_code.origin, claude_code.config())
    if not found:
        print("\n  No changes I can see. Same kit from the first session to the last.\n")
        return
    turns, _ = load(args.agent, args.path, args.project)
    timeline.measure(found, turns, days=args.days)
    print(f"\n  {len(found)} changes to your kit, found in the transcripts and grouped by day. For each: your answers "
          f"in the {args.days} days before and after.")
    print(_c("  After is not because. Several changes close together can't be told apart.\n", "2"))
    shown = found if args.all else found[-12:]
    for c in reversed(shown):
        scope = _c(" (only the sessions that load it)", "2") if c.sessions else ""
        print(f"  {_c(c.day, '1')}  " + "\n              ".join(p[:100] for p in c.parts[:4]) +
              (_c(f"\n              + {len(c.parts) - 4} more", "2") if len(c.parts) > 4 else "") + scope)
        for line in _change_rows(c):
            print(f"              {line}")
        print()
    if len(found) > len(shown):
        print(_c(f"  {len(found) - len(shown)} older changes: sdog timeline --all\n", "2"))


def cmd_rules(args):
    from . import rules
    kits, _, _ = _kit(args)
    loaded_by = {}
    for k in kits:
        for key in k["loaded"]:
            if key.startswith("instructions:") and "/.claude/projects/" not in key:
                loaded_by.setdefault(key.split(":", 1)[1], set()).add(k["session"])
    found = rules.read_rules(sorted(loaded_by))
    turns, _ = load(args.agent, args.path, args.project)
    said = rules.corrections(turns)
    echoed = rules.echoes(found, turns, loaded_by)
    files = len({r.file for r in found})
    print(f"\n  {len(found)} rules in {files} instruction files. {len(said)} short corrections or reminders from you.")
    print(_c("  Beta: a rule is echoed when its distinctive words come back in a correction, in a session that had it "
             "loaded. Read the examples.\n", "2"))
    if not echoed:
        print("  None of your corrections repeats a rule. The rules are followed, or never come up:")
        print("  either way, your corrections are about something else. (`sdog show` has the turns.)\n")
        return
    for r in echoed[:args.limit]:
        print(f"  {_c(str(len(r.echoes)) + '×', '1;33')}  {r.text[:150]}")
        print(_c(f"      {r.file}", "2"))
        for t in r.echoes[:2]:
            when = f"{t.when:%Y-%m-%d}" if t.when else ""
            print(f"      {when}  “{' '.join(t.reply.split())[:120]}”")
        print()
    print("  A rule you keep repeating isn't working as written: make it shorter, more concrete, or a hook.\n")


def _journal_changes():
    from . import journal, timeline
    gone = journal.undone()
    out = []
    for e in journal.read():
        if e.get("action") in ("prune", "note"):
            c = timeline.Change(journal.when(e), f"#{e['id']} {e['what']}" + (" (undone)" if e["id"] in gone else ""),
                                "journal", [e.get("key", "")])
            c.parts = [c.what]
            out.append(c)
    return out


def _short_result(c):
    from .timeline import MIN_AFTER
    if not c.rows:
        return _c(f"too early ({c.after} turns after, I need {MIN_AFTER})" if c.after < MIN_AFTER else
                  f"too few turns before ({c.before})", "2")
    moved = [(n, r) for n, r in c.rows if r["p"] < 0.05]
    if not moved:
        return _c("nothing moved", "2")
    return " · ".join(f"{n} {_pct(r['rate_without'])} → {_pct(r['rate_with'])} {_verdict(r)}" for n, r in moved[:2])


def cmd_checkup(args):
    """The one screen: what weighs, what fails, what changed and whether it helped, what the agent keeps doing."""
    from . import prune, timeline
    from .adapters import claude_code
    from . import kit
    from .failures import SHORT
    kits = kit.scan(args.agent, args.path, args.project, cache=not args.no_cache)
    turns, per_agent = load(args.agent, args.path, args.project)
    if not kits and not turns:
        sys.exit("Nothing to sniff. No sessions found. Try `sdog demo`, or `sdog doctor` to see where I look.")
    items = kit.ledger(kits, claude_code.config(), claude_code.origin) if kits else {}
    s = kit.summary(kits, items)
    answered = sum(1 for t in turns if t.reply)
    agents = ", ".join(f"{a} {n}" for a, n in sorted(per_agent.items()))
    base = f" · {_n(s['base_tokens'])} tokens before you type" if s["base_tokens"] else ""
    line = f"{s['sessions']} sessions · {s['first']} → {s['last']}{base}" if kits else \
        "The kit (what you load, use and break) is Claude Code only for now."
    print(DOG.format(v=__version__, line=line, extra=f"{_n(answered)} answered turns · {agents}"))
    rows = sorted(items.values(), key=lambda it: -(it.chars * it.loaded))
    pad = " " * 14

    def head(label, text):
        print(f"  {_c(f'{label:<11}', '1')} {text}")

    ballast = [it for it in rows if it.verdict == "ballast"]
    if ballast:
        head("BALLAST", f"~{_n(s['ballast_tokens'])} tokens a session on {len(ballast)} things you never use")
        for it in ballast[:3]:
            print(f"{pad}{it.kind} {it.name[:34]:<34} 0 of {it.loaded} sessions  ~{_n(it.weight)} tok")
        mine, _ = prune.proposals(items, s["sessions"])
        print(_c(f"{pad}→ sdog prune" + (f"  ({len(mine)} I can do for you, with undo)" if mine else ""), "2"))
    rare = [it for it in rows if it.verdict in ("rare", "elsewhere")]
    if rare:
        head("RARE", f"{len(rare)} things used in under 5% of the sessions that load them, or in one project only")
    misused = sorted((it for it in rows if it.verdict == "misused"), key=lambda it: -it.errors)
    for i, it in enumerate(misused[:3]):
        top = next((w for w, _ in it.error_kinds.most_common() if w != "other"), "")
        why = f" · mostly {top}: {SHORT[top]}" if top else ""
        line = f"{it.kind} {it.name[:28]:<28} {it.error_rate:5.1%} fail{why}"
        if i:
            print(f"{pad}{line}")
        else:
            head("MISUSED", line)
    if misused:
        print(_c(f"{pad}→ sdog kit {misused[0].name}", "2"))
    found = timeline.changes(kits, claude_code.origin, claude_code.config())
    logged = _journal_changes()
    timeline.measure(found + logged, turns)
    for i, c in enumerate(reversed(found[-3:])):
        line = f"{c.day}  {c.parts[0][:62]}" + (_c(f" +{len(c.parts) - 1} more", "2") if len(c.parts) > 1 else "")
        print(f"{pad}{line}") if i else head("CHANGED", line)
        print(f"{pad}            {_short_result(c)}")
    if found:
        print(_c(f"{pad}→ sdog timeline", "2"))
    for i, c in enumerate(reversed(logged[-3:])):
        line = f"{c.day}  {c.what[:62]}"
        print(f"{pad}{line}") if i else head("JOURNAL", line)
        print(f"{pad}            {_short_result(c)}")
    tables = lab.sniff(turns)
    real = lab.findings(tables)
    leads, seen = [], set()
    for o, f, r in sorted(((o, f, r) for o, rs in tables.items() for f, r in rs if r["p"] < 0.01 and r["ratio"] > 1),
                          key=lambda x: x[2]["p"]):
        if f not in seen:
            seen.add(f)
            leads.append((o, f, r))
    for i, (o, f, r) in enumerate((real or leads)[:2]):
        line = f"{f} → {o} {_pct(r['rate_with'])} vs {_pct(r['rate_without'])} · {_verdict(r)}"
        print(f"{pad}{line}") if i else head("HABITS", line)
    if real or leads:
        o, f, _ = (real or leads)[0]
        print(_c(f'{pad}→ sdog show "{f}" --outcome {o}', "2"))
    if not kits and not (real or leads):
        print("  Too few turns for anything to stand out yet. `sdog sniff --all` shows every row.")
    print(f"\n  Nothing here changed anything. `sdog prune` asks before it does; `sdog report` draws it all.\n")


def cmd_prune(args):
    from . import prune
    kits, items, s = _kit(args)
    mine, yours = prune.proposals(items, s["sessions"])
    if args.name:
        needle = args.name.lower()
        mine = [p for p in mine if needle in p.key.lower()]
        yours = [p for p in yours if needle in p.key.lower()]
    if not mine and not yours:
        print("\n  Nothing to prune. Everything you load, you use. Good dog.\n")
        return
    total = sum(p.saves for p in mine)
    if mine:
        print(f"\n  {_c('I can do these', '1')}, each with an undo. Together: ~{_n(total)} tokens a session.")
        print(_c("  The attic is ~/.local/share/suspiciousdog/attic: `sdog undo` brings things back.\n", "2"))
        for i, p in enumerate(mine, 1):
            print(f"  {i:>2}. {p.what}")
            print(_c(f"      {p.why} · ~{_n(p.saves)} tokens a session", "2"))
            print(_c(f"      {prune.describe(p.fix)}", "2"))
    if yours:
        print(f"\n  {_c('Only you can do these', '1')} (then `sdog note \"what you did\"`, so I can measure it):\n")
        for p in yours[:args.limit]:
            print(f"      {p.what:<44} ~{_n(p.saves):>5} tok  {_c(p.hint, '2')}")
        if len(yours) > args.limit:
            print(_c(f"      + {len(yours) - args.limit} more (--limit)", "2"))
    if not mine:
        print()
        return
    choice = args.apply
    if choice is None:
        if not sys.stdin.isatty():
            print("\n  Nothing applied. Pick with --apply 1,3 (or --apply all).\n")
            return
        choice = input("\n  Apply which? numbers like 1,3 · all · nothing [nothing]: ").strip()
    picked = _pick(choice, len(mine))
    if not picked:
        print("  Nothing applied.\n")
        return
    print()
    for i in picked:
        p = mine[i - 1]
        try:
            e = prune.apply(p)
            print(f"  ✓ #{e['id']} {p.what}")
        except RuntimeError as err:
            print(f"  ✗ {p.what}: {err}")
    print("\n  Written in the journal. `sdog undo` reverts the last one; in two weeks `sdog journal` says if it hurt.")
    print("  Changes apply to new sessions.\n")


def _pick(choice, n):
    choice = (choice or "").strip().lower()
    if choice in ("all", "a"):
        return list(range(1, n + 1))
    picked = []
    for part in choice.replace(" ", ",").split(","):
        if part.isdigit() and 1 <= int(part) <= n and int(part) not in picked:
            picked.append(int(part))
    return picked


def cmd_note(args):
    from . import journal
    e = journal.write("note", " ".join(args.text), args.key or "")
    print(f"\n  #{e['id']} noted at {e['at'][:16].replace('T', ' ')}. In two weeks `sdog journal` will say what changed.\n")


def cmd_journal(args):
    from . import journal, timeline
    entries = journal.read()
    if not entries:
        print(f"\n  The journal is empty. `sdog prune` and `sdog note` write to it ({journal.path()}).\n")
        return
    logged = _journal_changes()
    turns, _ = load(args.agent, args.path, args.project)
    timeline.measure(logged, turns, days=args.days)
    by_id = {c.what.split(" ", 1)[0]: c for c in logged}
    print()
    for e in entries:
        at = e["at"][:16].replace("T", " ")
        if e["action"] == "undo":
            print(_c(f"  #{e['id']:<3} {at}  {e['what']}", "2"))
            continue
        c = by_id.get(f"#{e['id']}")
        print(f"  #{e['id']:<3} {at}  {c.what[len(str(e['id'])) + 2:] if c else e['what']}")
        if c:
            for line in _change_rows(c):
                print(f"              {line}")
    print()


def cmd_undo(args):
    from . import journal, prune
    entries = [e for e in journal.read() if e.get("undo") and e["id"] not in journal.undone()]
    if args.id:
        entries = [e for e in entries if e["id"] == args.id]
    if not entries:
        print("\n  Nothing to undo.\n")
        return
    e = entries[-1]
    try:
        done = prune.undo(e)
    except RuntimeError as err:
        sys.exit(f"  Couldn't undo #{e['id']}: {err}")
    print(f"\n  ✓ #{done['id']} {done['what']}. New sessions get it back.\n")


def cmd_report(args):
    from . import journal, report, timeline
    from .adapters import claude_code
    kits, items, s = _kit(args)
    turns, _ = load(args.agent, args.path, args.project)
    found = timeline.changes(kits, claude_code.origin, claude_code.config())
    logged = _journal_changes()
    timeline.measure(found + logged, turns)
    tables = lab.sniff(turns)
    habits = sorted(((o, f, r) for o, rs in tables.items() for f, r in rs if r["p"] < 0.05 and r["ratio"] > 1),
                    key=lambda x: x[2]["p"])
    out = Path(args.out).expanduser() if args.out else journal.home() / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.build(kits, items, s, found, logged, habits, timeline.MIN_AFTER))
    print(f"\n  Wrote {out}  ({out.stat().st_size // 1024} KB, nothing sent anywhere)")
    print("  It holds project names and error messages: keep it to yourself; `sdog share` is for sharing.\n")
    if args.open:
        webbrowser.open(out.as_uri())


def cmd_doctor(args):
    from . import kit
    from .adapters import claude_code
    print()
    for name, a in ADAPTERS.items():
        paths = a.default_paths()
        reads = "turns + kit" if hasattr(a, "kit") else "turns"
        print(f"  {_c(name, '1'):<12} {a.STATUS:<7} {len(paths):>5} session files   reads: {reads}")
    kits = kit.scan("claude-code", cache=not args.no_cache)
    if kits:
        def coverage(group):
            n = len(group) or 1
            have = {"skill listing": "skill_listing", "MCP instructions": "mcp_instructions_delta",
                    "subagent listing": "agent_listing_delta", "instruction files": "instructions"}
            parts = [f"{label} {sum(1 for k in group if k['attachments'].get(t)) / n:.0%}" for label, t in have.items()]
            parts.append(f"token usage {sum(1 for k in group if k['base_tokens']) / n:.0%}")
            return " · ".join(parts)
        versions = sorted({k["version"] for k in kits if k["version"]},
                          key=lambda v: [int(x) if x.isdigit() else 0 for x in v.split(".")])
        lean = [k for k in kits if not any(k["attachments"].get(t) for t in ("skill_listing", "agent_listing_delta"))]
        full = [k for k in kits if k not in lean]
        print(f"\n  Claude Code, {len(kits)} sessions with activity, "
              f"{sum(k['subagent_files'] for k in kits)} subagent files folded in")
        print(f"    all sessions      {coverage(full)}")
        print(f"    last 20 sessions  {coverage(full[-20:])}")
        if lean:
            tok = sorted(k["base_tokens"] or 0 for k in lean)[len(lean) // 2]
            print(f"    {len(lean)} sessions listed no skills or subagents at all (scripted runs?), ~{_n(tok)} tokens each")
        if versions:
            print(f"    versions          {versions[0]} → {versions[-1]}")
        print("    If a share drops in the last 20 sessions, Claude Code changed its format: please open an issue.")
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    files = [root / "settings.json", root / "plugins" / "installed_plugins.json",
             Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home())) / ".claude.json"]
    print("\n  config  " + "  ".join(f"{p.name} {'ok' if p.exists() else 'missing'}" for p in files))
    print(f"  plugins, skills and servers found on disk: {len(claude_code.config())}")
    c = kit.cache_path()
    print(f"  cache   {c} " + (f"{c.stat().st_size / 1e6:.1f} MB" if c.exists() else "(none yet)"))
    print()


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
    s.add_argument("--outcome", choices=list(ALL_OUTCOMES), default="pushback")
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
    s = add("kit", cmd_kit, "what you added to your agent: what it weighs, what you use, what fails")
    s.add_argument("name", nargs="?", help="one item, in detail (e.g. gamma, supabase, code-review)")
    s.add_argument("--kind", choices=["skill", "mcp", "subagent", "instructions", "hook", "plugin", "tool"])
    s.add_argument("--all", action="store_true", help="every row of every section")
    s.add_argument("--json", action="store_true", help="for agents and scripts")
    s.add_argument("--no-cache", action="store_true", help="read every session again")
    s = add("timeline", cmd_timeline, "when your kit changed, and your answers before and after each change")
    s.add_argument("--days", type=int, default=14, help="turns compared on each side of a change (default 14)")
    s.add_argument("--all", action="store_true", help="every change, not just the last 12")
    s.add_argument("--no-cache", action="store_true")
    s = add("rules", cmd_rules, "beta: rules in your CLAUDE.md / AGENTS.md that your corrections keep repeating")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--no-cache", action="store_true")
    s = add("checkup", cmd_checkup, "the one screen: what weighs, what fails, what changed, what the agent keeps doing")
    s.add_argument("--no-cache", action="store_true")
    s = add("prune", cmd_prune, "lighten the kit: proposals, applied only on your yes, each with an undo")
    s.add_argument("name", nargs="?", help="only items whose name contains this")
    s.add_argument("--apply", metavar="WHICH", help="1,3 or all, without asking")
    s.add_argument("--limit", type=int, default=12)
    s.add_argument("--no-cache", action="store_true")
    s = sub.add_parser("note", help="write a change you made yourself into the journal, so it gets measured")
    s.set_defaults(fn=cmd_note)
    s.add_argument("text", nargs="+")
    s.add_argument("--key", help="the item, as `sdog kit` names it (e.g. mcp:claude_ai_Gamma)")
    s = add("journal", cmd_journal, "every change made or noted, and what happened after")
    s.add_argument("--days", type=int, default=14)
    s = sub.add_parser("undo", help="revert the last change made by prune (or --id N)")
    s.set_defaults(fn=cmd_undo)
    s.add_argument("--id", type=int)
    s = add("report", cmd_report, "everything on one static HTML page, written to your disk")
    s.add_argument("--out", help="where to write it (default ~/.local/share/suspiciousdog/report.html)")
    s.add_argument("--open", action="store_true", help="open it in the browser")
    s.add_argument("--no-cache", action="store_true")
    s = add("doctor", cmd_doctor, "what I can read, for each agent and format version", sessions=False)
    s.add_argument("--no-cache", action="store_true")
    s = sub.add_parser("provenance", help="experiment 1: names written from memory (Claude Code only)")
    s.set_defaults(fn=cmd_provenance)
    s.add_argument("session", nargs="?", help="a session file; default: your latest")
    s.add_argument("--history", action="store_true", help="every session: do names from memory fail more?")
    s.add_argument("--world", action="store_true", help="also search repos, dependencies and man pages (slow)")

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or (argv[0] not in sub.choices and argv[0] not in ("-h", "--help", "--version")):
        argv = ["checkup", *argv]           # `sdog`, `sdog --project x`: the checkup
    args = p.parse_args(argv)
    args.fn(args)
