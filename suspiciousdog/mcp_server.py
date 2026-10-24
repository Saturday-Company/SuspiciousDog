"""`sdog mcp`: the evidence as an MCP server, over stdio, with the standard library only.

Three tools, because every tool an agent can see is weight in its context:
- audit_setup: the checkup, as data;
- check_rule: before adding a rule, does the problem show up at all, and is it already said?
- evidence: everything about one plugin, skill, MCP server, subagent or tool.

It only reads. Nothing here changes the user's configuration or sends anything anywhere.
"""

import json
import sys
import traceback

from . import __version__, service

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
INSTRUCTIONS = ("Counts from this user's own past sessions. Before adding a rule to CLAUDE.md/AGENTS.md, call "
                "check_rule; before recommending or installing a plugin, skill or MCP server, call evidence; to "
                "review the setup, audit_setup. Read-only.")
TOOLS = [
    {"name": "audit_setup",
     "description": "What the user's agent setup costs and does: context at start, ballast (loaded, never used), "
                    "misused tools and why they fail, recent changes with before/after, habits that go with "
                    "worse answers.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "check_rule",
     "description": "Before adding a rule to CLAUDE.md or AGENTS.md: is something like it already loaded, do the "
                    "user's corrections say it, do the tools it names fail for a reason it would fix? Returns a "
                    "verdict (already said, supported, weak, no evidence) and the numbers.",
     "inputSchema": {"type": "object", "properties": {
         "text": {"type": "string", "description": "the rule, as it would be written"},
         "cwd": {"type": "string", "description": "the project folder, if the rule is for one project"}},
         "required": ["text"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "evidence",
     "description": "One item of the setup (plugin, skill, MCP server, subagent, tool, hook): weight in tokens, "
                    "sessions loaded vs used, failure rate and reasons, and what changed when it came or went.",
     "inputSchema": {"type": "object", "properties": {
         "item": {"type": "string", "description": "a name like gamma, supabase, code-review, or a key like "
                                                   "mcp:claude_ai_Gamma"}},
         "required": ["item"], "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
]


class Server:
    def __init__(self, state=None):
        self.state = state or service.State()

    def call(self, name, args):
        if name == "audit_setup":
            return service.audit(self.state)
        if name == "check_rule":
            text = str(args.get("text") or "").strip()
            if not text:
                raise ValueError("text is required")
            return service.check_rule(self.state, text, args.get("cwd") or service.here())
        if name == "evidence":
            return service.evidence(self.state, str(args.get("item") or ""))
        raise KeyError(name)

    def handle(self, msg):
        """One JSON-RPC message in, one out (None for notifications)."""
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            return None
        params = msg.get("params") or {}
        if method == "initialize":
            asked = params.get("protocolVersion")
            return self._ok(mid, {"protocolVersion": asked if asked in PROTOCOLS else PROTOCOLS[0],
                                  "capabilities": {"tools": {"listChanged": False}},
                                  "serverInfo": {"name": "suspiciousdog", "version": __version__},
                                  "instructions": INSTRUCTIONS})
        if method == "ping":
            return self._ok(mid, {})
        if method == "tools/list":
            return self._ok(mid, {"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name")
            if name not in {t["name"] for t in TOOLS}:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
            try:
                data = self.call(name, params.get("arguments") or {})
            except Exception as e:      # a tool error is an answer, not a crash
                if not isinstance(e, ValueError):
                    traceback.print_exc(file=sys.stderr)
                return self._ok(mid, {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                                      "isError": True})
            return self._ok(mid, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                                  "isError": bool(isinstance(data, dict) and data.get("error"))})
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}

    @staticmethod
    def _ok(mid, result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(stdin=None, stdout=None):
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    server = Server()
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            batch = msg if isinstance(msg, list) else [msg]
            replies = [r for r in (server.handle(m) for m in batch if isinstance(m, dict)) if r]
            reply = replies if isinstance(msg, list) else (replies[0] if replies else None)
        if reply:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
