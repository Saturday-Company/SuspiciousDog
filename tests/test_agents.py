"""0.2.0b2: the brief, the rule check, the MCP server, the hooks and the sentinel."""

import io
import json
import os
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from suspiciousdog import brief, check, cli, hooks, journal, kit, mcp_server, sentinel, service, timeline
from suspiciousdog.model import Event, Turn

START = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)


def turn(i, final, reply, project="-p-a", calls=3):
    t = Turn("claude-code", f"s{i // 4}", project, START + timedelta(hours=i), "fix the thing please now", reply=reply)
    t.texts = [final]
    t.events = [Event("call", "Read", "read", "a.py")] * calls
    return t


def offers_and_deferrals(n=400):
    """Offers of more work get put off; everything else gets a yes. A habit the brief should report."""
    out = []
    for i in range(n):
        if i % 5 == 0:
            out.append(turn(i, "Done. Shall I also add caching?", "not now, later" if i % 10 == 0 else "ok"))
        else:
            out.append(turn(i, "Done, the form works.", "ok"))
    return out


def ledger(errors=30, calls=200, kinds=None):
    k = {"agent": "claude-code", "session": "s1", "project": "/p", "start": "2026-10-01T09:00", "base_tokens": 1000,
         "loaded": {"mcp:claude_ai_Supabase": 800}, "used": {"mcp:claude_ai_Supabase": calls, "tool:Read": 2000},
         "errors": {"mcp:claude_ai_Supabase": errors, "tool:Read": 10}, "retries": {}, "denied": {}, "samples": {},
         "attachments": {"skill_listing": 1}, "error_kinds": {"mcp:claude_ai_Supabase": kinds or {"bad code": errors}}}
    return kit.ledger([dict(k, session=f"s{i}") for i in range(25)])


class Brief(unittest.TestCase):
    def test_habits_and_tools_with_numbers(self):
        text, numbers = brief.build(offers_and_deferrals(), ledger())
        self.assertIn("offering more work", text)
        self.assertIn("put off 50%", text)
        self.assertIn("Supabase", text)
        self.assertIn("bad code", text)
        self.assertLessEqual(len(text), brief.MAX_CHARS)
        self.assertLess(numbers["tokens"], 300)

    def test_nothing_to_say(self):
        text, numbers = brief.build([turn(i, "Done.", "ok") for i in range(100)], {})
        self.assertEqual(text, "")

    def test_project_scope_needs_enough_turns(self):
        turns = offers_and_deferrals() + [turn(i, "x", "ok", project="-q") for i in range(10)]
        _, numbers = brief.build(turns, {}, "-q")
        self.assertEqual(numbers["scope"], "all your projects")     # 10 turns in -q: too few, use everything
        _, numbers = brief.build(turns, {}, "-p-a")
        self.assertEqual(numbers["scope"], "this project")

    def test_auth_is_not_the_agents_job(self):
        text, _ = brief.build([], ledger(kinds={"auth": 30}))
        self.assertIn("tell the user", text)


class Check(unittest.TestCase):
    def test_supported_by_failures(self):
        r = check.check("Before running SQL on Supabase, read the table schema", [], ledger(), {}, 25)
        self.assertEqual(r["verdict"], "supported")
        self.assertEqual(r["tools"][0]["name"], "mcp:claude_ai_Supabase")

    def test_already_said(self):
        loaded = {"mcp:claude_ai_Supabase": "Before making schema changes, inspect the existing tables and columns "
                                            "so you understand the current structure."}
        r = check.check("Inspect the existing tables and columns before schema changes", [], {}, loaded, 25)
        self.assertEqual(r["verdict"], "already said")

    def test_no_evidence(self):
        r = check.check("Never use emoji in commit messages", [turn(i, "Done.", "ok") for i in range(50)], {}, {}, 25)
        self.assertEqual(r["verdict"], "no evidence")
        self.assertIn("50 answered turns", r["advice"])

    def test_corrections(self):
        turns = [turn(i, "Done.", "no, you pushed to main again without asking") for i in range(4)]
        r = check.check("Never push to main without asking", turns, {}, {}, 25)
        self.assertEqual(r["corrections"]["count"], 4)
        self.assertEqual(r["verdict"], "supported")

    def test_builtin_tools_only_by_exact_name(self):
        items = kit.ledger([{"agent": "x", "session": "s", "project": "/p", "start": "2026-10-01", "base_tokens": 1,
                             "loaded": {}, "used": {"tool:Read": 50}, "errors": {"tool:Read": 9}, "retries": {},
                             "denied": {}, "samples": {}, "attachments": {}}])
        self.assertEqual(check.check("read the schema first", [], items, {}, 1)["tools"], [])
        self.assertEqual(len(check.check("Use Read before Edit", [], items, {}, 1)["tools"]), 1)


class FakeState(service.State):
    def __init__(self):
        super().__init__()
        self.__dict__.update(kits=[], items=ledger(), summary={"sessions": 25, "first": "2026-10-01",
                                                                "last": "2026-10-20", "base_tokens": 1000,
                                                                "ballast_tokens": 0},
                             turns=offers_and_deferrals(), changes=([], []))

    def loaded_texts(self, cwd=None):
        return {}


class Mcp(unittest.TestCase):
    def talk(self, *messages):
        server = mcp_server.Server(FakeState())
        out = io.StringIO()
        stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
        for line in stdin:
            reply = server.handle(json.loads(line))
            if reply:
                out.write(json.dumps(reply) + "\n")
        return [json.loads(line) for line in out.getvalue().splitlines()]

    def test_handshake_and_tools(self):
        replies = self.talk({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                             "params": {"protocolVersion": "2025-03-26"}},
                            {"jsonrpc": "2.0", "method": "notifications/initialized"},
                            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(replies), 2)       # no answer to a notification
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual([t["name"] for t in replies[1]["result"]["tools"]], ["audit_setup", "check_rule", "evidence"])

    def test_calls(self):
        replies = self.talk(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
             "params": {"name": "check_rule", "arguments": {"text": "Read the Supabase schema before SQL"}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "evidence",
                                                                           "arguments": {"item": "supabase"}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "audit_setup", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "check_rule", "arguments": {}}})
        data = [json.loads(r["result"]["content"][0]["text"]) for r in replies[:3]]
        self.assertEqual(data[0]["verdict"], "supported")
        self.assertEqual(data[1]["key"], "mcp:claude_ai_Supabase")
        self.assertEqual(data[2]["misused"][0]["fails_mostly"], "bad code")
        self.assertIn("error", replies[3])
        self.assertTrue(replies[4]["result"]["isError"])

    def test_serve_reads_lines(self):
        stdin = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"ping"}\nnot json\n')
        out = io.StringIO()
        mcp_server.serve(stdin, out)
        lines = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual(lines[0], {"jsonrpc": "2.0", "id": 1, "result": {}})
        self.assertEqual(lines[1]["error"]["code"], -32700)


class Hooks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "settings.json").write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command",
                                                                                         "command": "echo hi"}]}]}}))
        self.env = {"CLAUDE_CONFIG_DIR": str(root), "XDG_DATA_HOME": str(root / "data"),
                    "XDG_CACHE_HOME": str(root / "cache")}
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.settings = root / "settings.json"

    def tearDown(self):
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.tmp.cleanup()

    def test_on_off_undo_keep_the_rest(self):
        hooks.on("brief")
        hooks.on("sentinel")
        self.assertEqual(hooks.status(), {"brief": True, "sentinel": True})
        with self.assertRaises(RuntimeError):
            hooks.on("brief")
        with redirect_stdout(io.StringIO()):
            cli.main(["undo"])                  # the sentinel goes
        self.assertEqual(hooks.status(), {"brief": True, "sentinel": False})
        hooks.off("brief")
        d = json.loads(self.settings.read_text())
        self.assertEqual(list(d["hooks"]), ["Stop"])    # only ours are removed
        self.assertEqual([e["action"] for e in journal.read()], ["hook", "hook", "undo", "hook"])
        self.assertTrue(list((journal.home() / "attic").glob("settings.json.*")))

    def test_brief_hook_reads_the_copy(self):
        brief.save("From 400 turns: - something", {"turns": 400})
        out = io.StringIO()
        with redirect_stdout(out), unittest.mock.patch("sys.stdin", io.StringIO('{"cwd": "/nowhere"}')):
            cli.main(["brief", "--hook"])
        d = json.loads(out.getvalue())
        self.assertEqual(d["hookSpecificOutput"]["hookEventName"], "SessionStart")
        self.assertIn("something", d["hookSpecificOutput"]["additionalContext"])

    def test_sentinel_once_a_week(self):
        st = {"announced": [], "last_shown": 0, "pending": "SuspiciousDog: on 01/10 you …", "pending_ids": ["#1"]}
        sentinel._save(st)
        self.assertTrue(sentinel.due(now=10 ** 9))
        self.assertIsNone(sentinel.due(now=10 ** 9 + 60))
        self.assertEqual(sentinel._state()["announced"], ["#1"])

    def test_sentinel_line(self):
        c = timeline.Change(START, "#3 disable plugin hyperframes", "journal")
        c.after = 140
        c.medians = {"before": {"base": 68210}, "after": {"base": 65800}}
        c.rows = [("complaint", {"p": 0.5, "rate_with": 0.02, "rate_without": 0.03})]
        line = sentinel.line(c)
        self.assertIn("you disable plugin hyperframes", line)
        self.assertIn("68,210 → 65,800", line)
        self.assertIn("nothing got worse in 140 turns", line)


if __name__ == "__main__":
    unittest.main()
