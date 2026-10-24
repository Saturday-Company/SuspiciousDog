"""`sdog report`: one static HTML page with everything, written to disk. No server, no network, no external files."""

from collections import defaultdict
from html import escape
from statistics import median

from . import __version__
from .failures import SHORT

VERDICT_NOTE = {
    "ballast": "loaded, never used", "rare": "used in under 5% of the sessions that load it",
    "elsewhere": "used in one project only", "misused": "fails far more often than your other tools",
    "earns": "earns its place", "new": "too new to judge", "fixed": "built in", "weight": "instruction file",
    "hook": "hook", "builtin": "built-in tool",
}

CSS = """
:root{--bg:#fbfaf7;--fg:#1d1b18;--mute:#6f6a62;--line:#e6e1d8;--card:#ffffff;--accent:#c2410c;--good:#2f7d4a;
--warn:#b45309;--bad:#b42318;--bar:#d6cfc2;--chip:#f1ede6}
@media (prefers-color-scheme:dark){:root{--bg:#141311;--fg:#ece8e1;--mute:#a19a8f;--line:#2c2a26;--card:#1c1b18;
--accent:#fb923c;--good:#6fcf97;--warn:#f5b453;--bad:#f87171;--bar:#4a453d;--chip:#26241f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,
"Segoe UI",sans-serif}main{max-width:1080px;margin:0 auto;padding:28px 16px 64px}h1{font-size:26px;margin:0 0 4px}
h2{font-size:18px;margin:36px 0 10px}.mute{color:var(--mute)}.note{font-size:13px;color:var(--mute);
border-left:3px solid var(--accent);padding:6px 10px;margin:14px 0;background:var(--card)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:18px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}.tile b{display:block;
font-size:22px;font-variant-numeric:tabular-nums}.tile span{font-size:12px;color:var(--mute)}
svg{max-width:100%;height:auto;display:block}.chart rect.b{fill:var(--bar)}.chart rect.b:hover{fill:var(--accent)}
.chart text{fill:var(--mute);font-size:11px}.chart line{stroke:var(--line)}
.change{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}
.change .d{font-weight:600;font-variant-numeric:tabular-nums}.change ul{margin:4px 0 4px 18px;padding:0}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.chip{border:1px solid var(--line);background:var(--chip);
color:var(--fg);border-radius:999px;padding:3px 10px;font-size:13px;cursor:pointer}.chip.on{background:var(--fg);
color:var(--bg)}input[type=search]{width:100%;max-width:320px;padding:7px 10px;border:1px solid var(--line);
border-radius:8px;background:var(--card);color:var(--fg);font:inherit}.wrap{overflow-x:auto;border:1px solid
var(--line);border-radius:10px;background:var(--card)}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:7px 9px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}th{cursor:pointer;
position:sticky;top:0;background:var(--card);user-select:none}td.n,th.n{text-align:right;
font-variant-numeric:tabular-nums}td.name{white-space:normal;word-break:break-all;min-width:160px}
.v{font-weight:600}.v-ballast,.v-misused{color:var(--bad)}.v-rare,.v-elsewhere{color:var(--warn)}
.v-earns{color:var(--good)}.v-new,.v-fixed,.v-weight,.v-hook,.v-builtin{color:var(--mute);font-weight:400}
.fail{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:8px 0}
.fail code{font-size:12px;color:var(--mute);display:block;white-space:pre-wrap;word-break:break-word;margin-top:3px}
footer{margin-top:40px;font-size:12px;color:var(--mute)}
"""

JS = """
const rows=[...document.querySelectorAll('#ledger tbody tr')];let verdict='all';
function show(){const q=document.getElementById('q').value.toLowerCase();for(const r of rows){
r.hidden=!((verdict==='all'||r.dataset.v===verdict)&&r.textContent.toLowerCase().includes(q))}}
document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{document.querySelectorAll('.chip').forEach(x=>
x.classList.remove('on'));c.classList.add('on');verdict=c.dataset.v;show()});
document.getElementById('q').oninput=show;
document.querySelectorAll('#ledger th').forEach((th,i)=>th.onclick=()=>{const num=th.classList.contains('n');
const dir=th.dataset.dir=th.dataset.dir==='asc'?'desc':'asc';const tb=th.closest('table').tBodies[0];
[...tb.rows].sort((a,b)=>{let x=a.cells[i].dataset.s??a.cells[i].textContent,y=b.cells[i].dataset.s??b.cells[i].textContent;
if(num){x=+x;y=+y}return (x>y?1:x<y?-1:0)*(dir==='asc'?1:-1)}).forEach(r=>tb.appendChild(r))});
"""


def _n(x):
    return f"{x:,}"


def _chart(kits):
    """Tokens before the first word, median per day."""
    days = defaultdict(list)
    for k in kits:
        if k["base_tokens"]:
            days[k["start"][:10]].append(k["base_tokens"])
    if not days:
        return ""
    keys = sorted(days)
    values = [median(days[d]) for d in keys]
    top = max(values) or 1
    w, h, pad = 1000, 220, 30
    step = (w - pad) / len(keys)
    bars = []
    for i, (d, v) in enumerate(zip(keys, values)):
        bh = (h - 40) * v / top
        x = pad + i * step
        bars.append(f'<rect class="b" x="{x:.1f}" y="{h - 20 - bh:.1f}" width="{max(step - 2, 1):.1f}" height="{bh:.1f}">'
                    f'<title>{d}: {_n(round(v))} tokens ({len(days[d])} sessions)</title></rect>')
    labels = [f'<text x="{pad + i * step:.1f}" y="{h - 4}">{keys[i][5:]}</text>'
              for i in range(0, len(keys), max(1, len(keys) // 8))]
    return (f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" aria-label="Tokens loaded before the first word, '
            f'median per day"><line x1="{pad}" x2="{w}" y1="{h - 20}" y2="{h - 20}"/>'
            f'<text x="0" y="14">{_n(round(top))}</text>{"".join(bars)}{"".join(labels)}</svg>')


def _result(c, min_after):
    if not c.rows:
        return f"too early: {c.before} turns before, {c.after} after (needs {min_after} on each side)"
    moved = [(name, r) for name, r in c.rows if r["p"] < 0.05]
    if not moved:
        return f"nothing moved ({c.before} turns before, {c.after} after)"
    return " · ".join(f"{name} {r['rate_without']:.1%} → {r['rate_with']:.1%} "
                      f"({'real' if r.get('q', 1) < 0.05 else 'maybe'})" for name, r in moved)


def build(kits, items, summary, changes, journal_changes, habits, min_after):
    e = escape
    rows = sorted(items.values(), key=lambda it: (-(it.chars * it.loaded), -it.calls))
    verdicts = [v for v in ("ballast", "rare", "elsewhere", "misused", "earns", "new", "fixed", "weight", "hook")
                if any(it.verdict == v for it in rows)]
    used = sum(1 for it in rows if it.used and it.kind not in ("tool", "instructions"))
    listed = sum(1 for it in rows if it.kind not in ("tool", "instructions"))
    tiles = [(summary["sessions"], "sessions"), (f"{summary['first'][5:]} → {summary['last'][5:]}", "period"),
             (_n(summary["base_tokens"] or 0), "tokens before your first word (average)"),
             (_n(summary["ballast_tokens"]), "tokens a session on things never used"),
             (f"{used} / {listed}", "things used / things loaded")]
    out = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
           f"content='width=device-width,initial-scale=1'><title>SuspiciousDog report</title><style>{CSS}</style>"
           f"</head><body><main><h1>SuspiciousDog report</h1><div class='mute'>v{__version__} · "
           f"{', '.join(f'{a} {n}' for a, n in summary['agents'].items())}</div>",
           "<div class='note'>This page holds project names and error messages from your sessions. It lives on your "
           "disk and nothing was sent anywhere. Don't share it as it is: <code>sdog share</code> sends counts only."
           "</div><div class='tiles'>" +
           "".join(f"<div class='tile'><b>{e(str(v))}</b><span>{e(t)}</span></div>" for v, t in tiles) + "</div>",
           "<h2>Context before your first word</h2><div class='mute'>Median per day, from the first API call of each "
           "session.</div>" + _chart(kits)]
    if journal_changes:
        out.append("<h2>Journal</h2>")
        for c in reversed(journal_changes):
            out.append(f"<div class='change'><span class='d'>{c.day}</span> {e(c.what)}<div class='mute'>"
                       f"{e(_result(c, min_after))}</div></div>")
    if changes:
        out.append("<h2>When the kit changed</h2><div class='mute'>Found in the transcripts, grouped by day, with your "
                   "answers in the days before and after. After is not because.</div>")
        for c in reversed(changes):
            parts = "".join(f"<li>{e(p)}</li>" for p in c.parts)
            scope = " <span class='mute'>(only the sessions that load it)</span>" if c.sessions else ""
            out.append(f"<div class='change'><span class='d'>{c.day}</span>{scope}<ul>{parts}</ul>"
                       f"<div class='mute'>{e(_result(c, min_after))}</div></div>")
    out.append("<h2>The kit</h2><div class='chips'>" +
               "<button class='chip on' data-v='all'>all</button>" +
               "".join(f"<button class='chip' data-v='{v}'>{v} ({sum(1 for it in rows if it.verdict == v)})</button>"
                       for v in verdicts) +
               "</div><input id='q' type='search' placeholder='filter by name…' aria-label='filter'>"
               "<div class='wrap' style='margin-top:8px;max-height:640px'><table id='ledger'><thead><tr>"
               "<th>kind</th><th>name</th><th>verdict</th><th class='n'>loaded</th><th class='n'>used</th>"
               "<th class='n'>~tokens</th><th class='n'>calls</th><th class='n'>fail</th><th>mostly</th>"
               "<th>from</th></tr></thead><tbody>")
    for it in rows:
        if it.kind == "tool":
            continue
        top = next((w for w, _ in it.error_kinds.most_common() if w != "other"), "")
        out.append(f"<tr data-v='{it.verdict}'><td>{it.kind}</td><td class='name'>{e(it.name)}</td>"
                   f"<td class='v v-{it.verdict}' title='{e(VERDICT_NOTE.get(it.verdict, ''))}'>{it.verdict}</td>"
                   f"<td class='n'>{it.loaded}</td><td class='n'>{it.used}</td><td class='n'>{it.weight}</td>"
                   f"<td class='n'>{it.calls}</td><td class='n' data-s='{it.error_rate:.4f}'>"
                   f"{f'{it.error_rate:.1%}' if it.calls else ''}</td><td>{e(top)}</td>"
                   f"<td>{e(it.origin.get('source', ''))}</td></tr>")
    out.append("</tbody></table></div>")
    misused = sorted((it for it in rows if it.verdict == "misused"), key=lambda it: -it.errors)
    if misused:
        out.append("<h2>Why it fails</h2>")
        for it in misused:
            tools = sorted(((t, c, f) for t, (c, f) in it.tools.items() if f), key=lambda x: -x[2])[:5]
            kinds = " · ".join(f"{w} {n}" for w, n in it.error_kinds.most_common(5))
            samples = "".join(f"<code>[{e(w)}] {e(t)}</code>" for w, t in it.samples[:4])
            top = next((w for w, _ in it.error_kinds.most_common() if w != "other"), "")
            out.append(f"<div class='fail'><b>{e(it.name)}</b> · {it.errors} of {_n(it.calls)} calls failed "
                       f"({it.error_rate:.1%})<div class='mute'>{e(kinds)}"
                       f"{(' → ' + e(SHORT[top])) if top else ''}</div>"
                       f"<div class='mute'>{' · '.join(e(f'{t} {f}/{c}') for t, c, f in tools)}</div>{samples}</div>")
    if habits:
        out.append("<h2>What the agent keeps doing</h2><div class='wrap'><table><thead><tr><th>factor</th><th>outcome"
                   "</th><th class='n'>turns</th><th class='n'>with</th><th class='n'>without</th><th>verdict</th>"
                   "</tr></thead><tbody>")
        for o, f, r in habits:
            out.append(f"<tr><td>{e(f)}</td><td>{e(o)}</td><td class='n'>{r['n_with']}</td>"
                       f"<td class='n'>{r['rate_with']:.1%}</td><td class='n'>{r['rate_without']:.1%}</td>"
                       f"<td>{'real' if r.get('q', 1) < 0.05 else 'maybe'}</td></tr>")
        out.append("</tbody></table></div>")
    out.append("<footer>Token weights are estimates (characters ÷ 4). Correlation, not cause: the numbers say where to "
               "look, <code>sdog show</code> and <code>sdog kit NAME</code> show what happened. "
               "github.com/Saturday-Company/SuspiciousDog</footer></main>"
               f"<script>{JS}</script></body></html>")
    return "".join(out)
