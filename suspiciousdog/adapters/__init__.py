"""Readers for each agent's transcripts. Every adapter exposes NAME, STATUS, default_paths(), detect(path), turns(path)."""

from pathlib import Path

from . import aider, claude_code, codex, gemini, generic

ADAPTERS = {a.NAME: a for a in (claude_code, codex, gemini, aider, generic)}


def sessions(agent=None, path=None):
    """(adapter, file) pairs: from --path if given, otherwise from every agent's default folders."""
    chosen = [ADAPTERS[agent]] if agent else list(ADAPTERS.values())
    if path:
        root = Path(path).expanduser()
        files = sorted(p for p in root.rglob("*") if p.is_file()) if root.is_dir() else [root]
        for f in files:
            for adapter in chosen:
                if adapter.detect(f):
                    yield adapter, f
                    break
        return
    for adapter in chosen:
        for f in adapter.default_paths():
            yield adapter, f


def load(agent=None, path=None, project=None):
    """All turns, plus how many sessions each agent contributed."""
    turns, per_agent = [], {}
    for adapter, f in sessions(agent, path):
        if project and project not in str(f):
            continue
        try:
            found = list(adapter.turns(f))
        except (OSError, UnicodeDecodeError):
            continue
        if found:
            per_agent[adapter.NAME] = per_agent.get(adapter.NAME, 0) + 1
            turns.extend(found)
    return turns, per_agent
