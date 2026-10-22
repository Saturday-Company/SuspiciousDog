"""Draws the dog. `python scripts/logo.py` writes assets/logo.svg and assets/logo-dark.svg (then PNGs if rsvg-convert exists).

A short-haired hound in three-quarter view: snout to the left, one heavy-lidded eye looking back at you,
a floppy ear, a red collar with a tag. Ink lines, roughened by an SVG filter.
"""

import random
import shutil
import subprocess
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
COLLAR, BUCKLE = "#d1352b", "#d4a72c"


def dog(ink, paper):
    rng = random.Random(11)
    specks = []
    for _ in range(60):
        x, y = rng.uniform(30, 570), rng.uniform(30, 580)
        if 90 < x < 560 and 120 < y < 600:
            continue
        r = rng.choice((1.6, 2.2, 3, 4.2))
        specks.append(f'<ellipse cx="{x:.0f}" cy="{y:.0f}" rx="{r}" ry="{r * rng.uniform(.6, 1.3):.1f}"/>')
    whiskers = []
    for _ in range(14):
        x, y = rng.uniform(178, 246), rng.uniform(308, 338)
        whiskers.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{rng.choice((2, 2.5, 3))}"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600" width="600" height="600">
  <title>SuspiciousDog</title>
  <defs>
    <filter id="ink" x="-5%" y="-5%" width="110%" height="110%">
      <feTurbulence type="fractalNoise" baseFrequency="0.045" numOctaves="2" seed="4"/>
      <feDisplacementMap in="SourceGraphic" scale="6" xChannelSelector="R" yChannelSelector="G"/>
    </filter>
  </defs>
  <g filter="url(#ink)" stroke="{ink}" stroke-linecap="round" stroke-linejoin="round">
    <path d="M300 470 C292 520 296 560 304 598 M478 440 C500 490 508 540 510 598" fill="none" stroke-width="13"/>
    <path d="M118 318 C120 296 140 284 170 280 C215 272 245 252 266 220 C282 186 316 140 370 134 C424 128 466 162 474 214
             C480 260 472 304 456 342 C445 370 455 400 474 432 L300 462 C296 425 282 398 255 382 C220 368 175 362 150 356
             C128 350 116 338 118 318 Z" fill="{paper}" stroke-width="13"/>
    <path d="M104 312 C106 292 138 286 156 298 C168 310 160 336 140 340 C120 344 102 332 104 312 Z" fill="{ink}"/>
    <path d="M158 345 C190 351 224 353 252 347" fill="none" stroke-width="8"/>
    <path d="M262 236 C280 262 330 266 350 226 C320 216 284 220 262 236 Z" fill="#ffffff" stroke-width="6"/>
    <path d="M326 228 C320 236 320 252 330 257 C342 254 348 240 347 228 Z" fill="#111111" stroke="none"/>
    <path d="M254 238 C280 218 324 210 356 224" fill="none" stroke-width="15"/>
    <path d="M286 198 C306 188 330 188 348 197" fill="none" stroke-width="6"/>
    <path d="M268 280 C284 284 302 283 316 276" fill="none" stroke-width="5"/>
    <path d="M408 140 C462 120 530 146 548 214 C562 270 550 330 516 360 C496 334 484 300 472 268 C458 232 436 190 408 140 Z"
          fill="{ink}"/>
    <path d="M294 450 C350 474 430 460 478 424 L488 452 C436 490 350 504 290 478 Z" fill="{COLLAR}" stroke-width="7"/>
    <rect x="384" y="461" width="36" height="26" rx="4" fill="{BUCKLE}" stroke-width="6" transform="rotate(-12 402 474)"/>
    <circle cx="338" cy="492" r="7" fill="none" stroke-width="5"/>
    <circle cx="338" cy="524" r="19" fill="{ink}"/>
  </g>
  <g fill="{ink}" filter="url(#ink)">
    {' '.join(whiskers)}
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
