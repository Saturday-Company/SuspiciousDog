"""Aider: .aider.chat.history.md in each repository.

Markdown, append-only. `#### ` lines are the user, `> ` lines are Aider's own output, everything else is the
model. Edits are SEARCH/REPLACE blocks inside the model's text. There are no per-message times (only the
`# aider chat started at` header) and no exit codes, so errors are recognised from Aider's messages.
"""

import os
import re
from datetime import datetime
from pathlib import Path

from ..model import EDIT, SHELL, Event, Turn

NAME = "aider"
STATUS = "beta"
FILENAME = ".aider.chat.history.md"

STARTED = re.compile(r"^# aider chat started at (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*$")
ERROR_LINE = re.compile(r"error|traceback|failed|unable to|can't|cannot|did not match|exception", re.I)
FENCE = re.compile(r"^```(\w*)\s*$")


def default_paths():
    found = []
    env = os.environ.get("AIDER_CHAT_HISTORY_FILE")
    if env and Path(env).is_file():
        found.append(Path(env))
    here = Path.cwd()
    for folder in (here, *here.parents):
        if (folder / FILENAME).is_file():
            found.append(folder / FILENAME)
    return sorted(set(found))


def detect(path):
    if path.name.endswith(".chat.history.md"):
        return True
    if path.suffix != ".md":
        return False
    try:
        with open(path, errors="replace") as f:
            return any(STARTED.match(line) for _, line in zip(range(30), f))
    except OSError:
        return False


def _model_text(lines):
    """Turns the model's raw reply into edit events and its prose. Shell runs come from `> Running` lines."""
    events, prose, fence, last_plain = [], [], None, ""
    for line in lines:
        m = FENCE.match(line.strip())
        if m and fence is None:
            fence = m.group(1) or "text"
            continue
        if m and fence is not None:
            fence = None
            continue
        if fence is not None:
            if line.startswith("<<<<<<< SEARCH"):
                events.append(Event("call", "edit_block", EDIT, last_plain.strip()))
            continue
        if line.strip():
            last_plain = line
            prose.append(line)
    return events, "\n".join(prose).strip()


def turns(path):
    path = Path(path)
    project = path.parent.name
    started, session_no = None, 0
    current, user_lines, model_lines = None, [], []

    def close_model():
        nonlocal model_lines
        if current and model_lines:
            events, prose = _model_text(model_lines)
            current.events.extend(events)
            if prose:
                current.texts.append(prose)
        model_lines = []

    def open_turn():
        nonlocal current, user_lines
        text = " ".join(user_lines).strip()
        user_lines = []
        if not text or text.startswith("/"):
            return None
        finished = current
        if finished:
            finished.reply = text
        current = Turn(NAME, f"{path.stem}-{session_no}", project, started, text)
        return finished

    with open(path, errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = STARTED.match(line)
            if m:
                close_model()
                if user_lines:
                    done = open_turn()
                    if done:
                        yield done
                if current:
                    yield current
                current = None
                session_no += 1
                started = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
                continue
            if line.startswith("#### "):
                close_model()
                user_lines.append(line[5:].rstrip())
                continue
            if user_lines:
                done = open_turn()
                if done:
                    yield done
            if line.startswith("> "):
                close_model()
                note = line[2:].strip()
                if current is None:
                    continue
                if note.startswith("Applied edit to"):
                    current.events.append(Event("result"))
                elif note.startswith("Running "):
                    current.events.append(Event("call", "shell", SHELL, note[8:]))
                elif note.startswith("^C") or "KeyboardInterrupt" in note:
                    current.interrupted = True
                elif ERROR_LINE.search(note) and not note.startswith(("Tokens:", "Commit ")):
                    current.events.append(Event("result", error=True))
                continue
            if current is not None:
                model_lines.append(line)
    close_model()
    if user_lines:
        done = open_turn()
        if done:
            yield done
    if current:
        yield current
