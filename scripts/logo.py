"""Draws the dog. `python scripts/logo.py` writes assets/logo.svg and assets/logo-dark.svg (then PNGs if rsvg-convert exists)."""

import random
import shutil
import subprocess
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"


def dog(ink, paper):
    rng = random.Random(11)
    specks = []
    for _ in range(46):
        x, y = rng.uniform(40, 560), rng.uniform(30, 580)
        if 150 < x < 450 and 140 < y < 480:
            continue
        r = rng.choice((1.6, 2.2, 3, 4.2))
        specks.append(f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{r}" ry="{r * rng.uniform(.6, 1.3):.1f}"/>')
    stubble = []
    for _ in range(26):
        x, y = rng.uniform(232, 368), rng.uniform(372, 440)
        if 268 < x < 332 and y < 400:
            continue
        stubble.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rng.choice((2, 2.6, 3.2))}"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="600" height="600">
  <title>SuspiciousDog</title>
  <defs>
    <filter id="ink" x="-5%" y="-5%" width="110%" height="110%">
      <feTurbulence type="fractalNoise" baseFrequency="0.045" numOctaves="2" seed="4"/>
      <feDisplacementMap in="SourceGraphic" scale="7" xChannelSelector="R" yChannelSelector="G"/>
    </filter>
  </defs>
  <g filter="url(#ink)" stroke="{ink}" stroke-linecap="round" stroke-linejoin="round">
    <path d="M300 124 C384 122 446 180 452 270 C456 330 440 372 430 404 C414 460 364 504 300 506 C236 504 186 460 170 404 C160 372 144 330 148 270 C154 180 216 126 300 124 Z"
          fill="{paper}" stroke-width="15"/>
    <path d="M214 150 C158 132 104 160 86 236 C72 300 88 356 120 372 C142 338 150 282 162 236 C170 204 186 176 214 150 Z" fill="{ink}"/>
    <path d="M386 150 C442 132 496 160 514 236 C528 300 512 356 480 372 C458 338 450 282 438 236 C430 204 414 176 386 150 Z" fill="{ink}"/>
    <path d="M186 238 C214 246 246 252 274 256" fill="none" stroke-width="14"/>
    <path d="M330 236 C352 214 388 212 414 226" fill="none" stroke-width="14"/>
    <path d="M194 284 L276 279 C274 306 254 318 236 318 C214 318 196 306 194 284 Z" fill="{paper}" stroke-width="10"/>
    <path d="M326 281 L408 276 C406 303 386 315 368 315 C346 315 328 303 326 281 Z" fill="{paper}" stroke-width="10"/>
    <circle cx="261" cy="296" r="11" fill="{ink}" stroke="none"/>
    <circle cx="393" cy="293" r="11" fill="{ink}" stroke="none"/>
    <path d="M226 352 C230 412 268 448 300 448 C334 448 370 412 374 352" fill="none" stroke-width="9"/>
    <path d="M270 344 C278 330 322 330 330 344 C334 358 314 372 300 372 C286 372 266 358 270 344 Z" fill="{ink}"/>
    <path d="M300 372 L300 396" fill="none" stroke-width="8"/>
    <path d="M266 408 C284 404 318 404 336 407" fill="none" stroke-width="9"/>
  </g>
  <g fill="{ink}" filter="url(#ink)">
    {' '.join(stubble)}
    {' '.join(specks)}
  </g>
</svg>
"""


def main():
    ASSETS.mkdir(exist_ok=True)
    for name, ink, paper in (("logo", "#111111", "#ffffff"), ("logo-dark", "#f2f2f2", "#0d1117")):
        svg = ASSETS / f"{name}.svg"
        svg.write_text(dog(ink, paper))
        if shutil.which("rsvg-convert"):
            subprocess.run(["rsvg-convert", "-w", "600", "-o", str(ASSETS / f"{name}.png"), str(svg)], check=True)


if __name__ == "__main__":
    main()
