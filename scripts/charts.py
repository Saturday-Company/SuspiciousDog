"""Builds the README images from real counts. `python scripts/charts.py`"""

import json
import re
import subprocess
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
ASSETS = ROOT / "assets"
GREY, DEAD, REAL, BAR_OFF = "#8b949e", "#cf222e", "#2da44e", "#8b949e"
FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def _row(data, factor, outcome):
    for f, o, nw, hw, nwo, hwo in data["results"]:
        if f == factor and o == outcome:
            return hw / nw, hwo / nwo, nw
    raise KeyError(factor, outcome)


def hypotheses():
    data = json.loads((RESULTS / "saturday-2026-10-23.json").read_text())
    prov = json.loads((RESULTS / "saturday-2026-10-23-provenance.json").read_text())
    red = prov["red"]["then_failed"] / prov["red"]["names"]
    green = prov["green"]["then_failed"] / prov["green"]["names"]
    blind_with, blind_without, blind_n = _row(data, "claims_done_without_looking", "pushback")
    offer_with, offer_without, offer_n = _row(data, "ends_offering_more_work", "pushback")
    cards = [
        ("Names written from memory", "tool calls that then failed", f"{prov['red']['names']:,} names",
         ("from memory", red), ("seen first", green), "DEAD", DEAD),
        ("“Done”, without looking", "turns the user pushed back on", f"{blind_n} turns",
         ("claims done blind", blind_with), ("every other turn", blind_without), "DEAD", DEAD),
        ("“Shall I also…?”", "turns the user pushed back on", f"{offer_n} turns",
         ("offers more work", offer_with), ("every other turn", offer_without), "REAL", REAL),
    ]
    w, h, top = 860, 150 + 120 * len(cards), 70
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" font-family="{FONT}">',
           "<title>Three ideas about AI agents, tested on real sessions: two died</title>",
           f'<text x="{w / 2}" y="28" font-size="16" font-weight="600" fill="{GREY}" text-anchor="middle">'
           f'Three ideas, tested on {data["turns"]} real turns. Two died.</text>',
           f'<text x="{w / 2}" y="50" font-size="12" fill="{GREY}" text-anchor="middle">'
           f'{data["agents"].get("claude-code", 0)} Claude Code sessions over {data["days"]} days · reproduce on yours: sdog sniff</text>']
    for i, (title, metric, n, (la, va), (lb, vb), verdict, colour) in enumerate(cards):
        y = top + 20 + i * 120
        scale = 430 / max(va, vb)
        out += [f'<text x="40" y="{y}" font-size="15" font-weight="600" fill="{GREY}">{escape(title)}</text>',
                f'<text x="40" y="{y + 18}" font-size="12" fill="{GREY}">{escape(metric)} · {escape(n)}</text>',
                f'<rect x="{w - 130}" y="{y - 16}" width="88" height="26" rx="4" fill="none" stroke="{colour}" stroke-width="2"/>',
                f'<text x="{w - 86}" y="{y + 2}" font-size="13" font-weight="700" fill="{colour}" text-anchor="middle" '
                f'letter-spacing="1.5">{verdict}</text>']
        for j, (label, value, fill) in enumerate(((la, va, colour), (lb, vb, BAR_OFF))):
            by = y + 32 + j * 26
            digits = 2 if value < 0.01 else 1
            out += [f'<text x="190" y="{by + 14}" font-size="12" fill="{GREY}" text-anchor="end">{escape(label)}</text>',
                    f'<rect x="200" y="{by}" width="{max(2, value * scale):.1f}" height="18" rx="2" fill="{fill}" '
                    f'fill-opacity="{1 if j == 0 else 0.45}"/>',
                    f'<text x="{208 + value * scale:.1f}" y="{by + 14}" font-size="12" font-weight="600" fill="{GREY}">'
                    f'{value:.{digits}%}</text>']
    out += [f'<text x="{w / 2}" y="{h - 22}" font-size="11" fill="{GREY}" text-anchor="middle">'
            "Bars are scaled per idea. REAL survives the Benjamini-Hochberg correction across every test (q &lt; 0.05).</text>",
            "</svg>"]
    (ASSETS / "hypotheses.svg").write_text("\n".join(out) + "\n")


def terminal(name, command, title):
    """A screenshot-like SVG of real command output."""
    env = {"NO_COLOR": "1", "PATH": "/usr/bin:/bin"}
    text = subprocess.run([sys.executable, "-m", "suspiciousdog", *command], cwd=ROOT, capture_output=True,
                          text=True, env=env).stdout.rstrip("\n").splitlines()
    lh, w = 19, 900
    h = 60 + lh * len(text)
    out = [f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg">', f"<title>{escape(title)}</title>",
           f'<rect width="{w}" height="{h}" rx="10" fill="#0d1117"/>',
           '<circle cx="22" cy="20" r="6" fill="#ff5f56"/><circle cx="42" cy="20" r="6" fill="#ffbd2e"/>'
           '<circle cx="62" cy="20" r="6" fill="#27c93f"/>',
           f'<text x="{w / 2}" y="24" font-family="{FONT}" font-size="12" fill="#8b949e" text-anchor="middle">'
           f'$ sdog {escape(" ".join(command))}</text>']
    for i, line in enumerate(text):
        y = 54 + i * lh
        tspans = []
        for part in re.split(r"(\breal\b|\bmaybe\b|\bvibes\b|SYNTHETIC DATA\.[^\n]*)", line):
            colour = {"real": REAL, "maybe": "#d29922", "vibes": "#6e7681"}.get(part, "#c9d1d9")
            if part.startswith("SYNTHETIC"):
                colour = "#d2a8ff"
            if part:
                tspans.append(f'<tspan fill="{colour}">{escape(part)}</tspan>')
        out.append(f'<text x="18" y="{y}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" '
                   f'font-size="13" xml:space="preserve">{"".join(tspans)}</text>')
    out.append("</svg>")
    (ASSETS / name).write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    hypotheses()
    terminal("demo.svg", ["demo"], "sdog demo, on synthetic sessions")
    print("assets/hypotheses.svg, assets/demo.svg")
