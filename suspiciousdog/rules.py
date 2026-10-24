"""Rules you keep repeating. A line in CLAUDE.md that your corrections echo is a line that isn't working as written.

Beta. Each rule's distinctive words are matched against your corrections and reminders. A match says where to look,
not that the rule was broken: read the examples.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .signals import PUSHBACK

REMINDER = re.compile(
    r"(ricorda|ricordati|ti (avevo|ho) (già |gia' )?detto|come (ti )?(ho|avevo) detto|te l'ho|non dimenticare|"
    r"remember|i told you|as i said|don't forget|di nuovo|\bagain\b)", re.I)
# A line reads as a rule when it tells the agent what to do or not to do.
RULE = re.compile(
    r"\b(non|mai|sempre|prima di|chiedo|chiedi|evita|usa|uso|deve|devi|va (fatto|messo|scritto)|solo|"
    r"never|always|don't|do not|must|only|avoid|use|ask|before)\b", re.I)
SHORT = 60          # words: longer replies are new requests, and share words with everything
STOP = set("""
about after again all also always and any are because been before being both but can could did does doing done each
even every from have here into just like make many more most much must need never not now only other over same should
some such than that their them then there these they this those through very want were what when where which while
will with without would your yours
alla alle allo agli anche ancora avere come cosa cose della delle dello degli dalla dalle dagli dopo dove essere fare
fatto fatti già hanno lavoro loro molto nella nelle nello negli niente ogni oppure perché però piu più poi prima
proprio qualcosa quale quali quando quello quella quelle quelli questo questa queste questi sempre senza solo sono
stato stata sulla sulle sugli tutto tutta tutte tutti uguale usare viene volta mai così cosi deve devi puoi può
""".split())


def stems(text):
    return {w[:6] for w in re.findall(r"[a-zà-ù]{4,}", text.lower()) if w not in STOP}


@dataclass
class Rule:
    file: str
    text: str
    stems: set
    echoes: list = field(default_factory=list)      # turns whose reply echoes the rule


def read_rules(files):
    rules = []
    for name in files:
        path = Path(name).expanduser()
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        fence, items = False, []
        for line in lines + [""]:
            if line.strip().startswith("```"):
                fence = not fence
                continue
            if fence:
                continue
            bullet = re.match(r"^\s*([-*+]|\d+[.)])\s+", line)
            if not line.strip() or bullet or line.lstrip().startswith(("#", "|", ">", "<")):
                items.append([])     # a blank line, a heading or a new bullet ends the item before it
            if line.strip() and not line.lstrip().startswith(("#", "|", ">", "<")):
                if not items:
                    items.append([])
                items[-1].append(line[bullet.end():] if bullet else line.strip())
        for item in items:
            text = re.sub(r"[*_`]", "", " ".join(item)).strip()
            if len(text.split()) >= 6 and RULE.search(text):
                rules.append(Rule(name, text, stems(text)))
    df = Counter(s for r in rules for s in r.stems)
    common = {s for s, n in df.items() if n > max(5, len(rules) // 10)}
    for r in rules:
        r.stems -= common
    return [r for r in rules if len(r.stems) >= 2]


def corrections(turns):
    """Turns whose short reply corrects or reminds the agent of something."""
    return [t for t in turns if t.reply and len(t.reply.split()) <= SHORT and
            (PUSHBACK.search(t.reply[:300]) or REMINDER.search(t.reply))]


def echoes(rules, turns, loaded_by=None):
    """Rules whose distinctive words come back in a correction, in a session that had the rule loaded."""
    said = [(t, stems(t.reply)) for t in corrections(turns)]
    for r in rules:
        sessions = (loaded_by or {}).get(r.file)
        need = max(3, round(0.4 * len(r.stems)))
        r.echoes = [t for t, words in said if len(r.stems & words) >= need and
                    len(r.stems & words) >= 0.2 * len(words) and (sessions is None or t.session in sessions)]
    return sorted((r for r in rules if r.echoes), key=lambda r: -len(r.echoes))
