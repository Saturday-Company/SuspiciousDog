"""The one shape every agent's transcript is turned into."""

import re
from dataclasses import dataclass, field
from datetime import datetime

# Tool categories shared by every adapter, so factors work the same for any agent.
EDIT, SHELL, READ, SEARCH, WEB, BROWSER, SUBAGENT, ASK, PLAN, SKILL, OTHER = (
    "edit", "shell", "read", "search", "web", "browser", "subagent", "ask", "plan", "skill", "other")

TRIVIAL_SHELL = (
    r"^\s*(cd [^&;]+(&&|;)\s*)?(git (add|commit|push|status|diff|log|checkout|branch|stash|fetch|pull)|ls|cat|echo|"
    r"mkdir|cp|mv|rm|sed -i|head|tail|wc|grep|rg|find|pwd|which)\b")


@dataclass
class Event:
    kind: str                  # "call" or "result"
    tool: str = ""             # the agent's own tool name
    category: str = OTHER      # one of the categories above
    detail: str = ""           # file path or shell command, when there is one
    error: bool = False        # for results: did the tool fail


@dataclass
class Turn:
    """From one user message to the next: what the agent did, and how the user answered."""
    agent: str
    session: str
    project: str
    when: datetime | None
    request: str
    events: list = field(default_factory=list)
    texts: list = field(default_factory=list)
    reply: str = ""
    interrupted: bool = False

    @property
    def calls(self):
        return [e for e in self.events if e.kind == "call"]

    @property
    def tool_calls(self):
        return len(self.calls)

    @property
    def files_written(self):
        return {e.detail for e in self.calls if e.category == EDIT}

    @property
    def errors(self):
        return sum(1 for e in self.events if e.kind == "result" and e.error)

    @property
    def final(self):
        return self.texts[-1] if self.texts else ""

    def uses(self, *categories):
        return any(e.category in categories for e in self.calls)

    def looked_after_last_edit(self):
        """None if nothing was edited; otherwise whether the agent ran, rendered or viewed anything afterwards."""
        calls = self.calls
        edits = [i for i, e in enumerate(calls) if e.category == EDIT]
        if not edits:
            return None
        for e in calls[edits[-1] + 1:]:
            if e.category == SHELL and not re.search(TRIVIAL_SHELL, e.detail):
                return True
            if e.category == BROWSER:
                return True
            if e.category == READ and re.search(r"\.(png|jpe?g|webp|gif|pdf)$", e.detail, re.I):
                return True
        return False
