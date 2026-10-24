"""Readers for each agent's transcripts. Every adapter exposes NAME, STATUS, default_paths(), detect(path), turns(path)."""

import os
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

from . import aider, claude_code, codex, gemini, generic

ADAPTERS = {a.NAME: a for a in (claude_code, codex, gemini, aider, generic)}


def sessions(agent=None, path=None):
    """(adapter, file) pairs: from --path if given, otherwise from every agent's default folders."""
    chosen = [ADAPTERS[agent]] if agent else list(ADAPTERS.values())
    if path:
        root = Path(path).expanduser()
        files = sorted(p for p in root.rglob("*") if p.is_file() and p.parent.name != "subagents") \
            if root.is_dir() else [root]
        for f in files:
            for adapter in chosen:
                if adapter.detect(f):
                    yield adapter, f
                    break
        return
    for adapter in chosen:
        for f in adapter.default_paths():
            yield adapter, f


def _turns(job):
    name, f = job
    try:
        return list(ADAPTERS[name].turns(f))
    except (OSError, UnicodeDecodeError):
        return []


def load(agent=None, path=None, project=None):
    """All turns, plus how many sessions each agent contributed. Many files are read in parallel."""
    jobs = [(adapter.NAME, f) for adapter, f in sessions(agent, path) if not project or project in str(f)]
    found = None
    if len(jobs) > 20:
        try:
            with ProcessPoolExecutor(min(8, os.cpu_count() or 1)) as pool:
                found = list(pool.map(_turns, jobs, chunksize=8))
        except (OSError, RuntimeError, BrokenProcessPool):
            found = None
    if found is None:
        found = [_turns(job) for job in jobs]
    turns, per_agent = [], {}
    for (name, _), these in zip(jobs, found):
        if these:
            per_agent[name] = per_agent.get(name, 0) + 1
            turns.extend(these)
    return turns, per_agent
