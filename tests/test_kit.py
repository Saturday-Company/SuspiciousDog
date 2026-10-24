import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from suspiciousdog import cli, kit
from suspiciousdog.adapters import claude_code

FIXTURE = Path(__file__).parent / "fixtures" / "kit" / "s1.jsonl"


class Reading(unittest.TestCase):
    def setUp(self):
        self.k = claude_code.kit(FIXTURE)

    def test_what_was_loaded(self):
        loaded = self.k["loaded"]
        self.assertEqual(set(k for k in loaded if k.startswith("skill:")), {"skill:tidy", "skill:deploy", "skill:plug:helper"})
        self.assertEqual(loaded["skill:tidy"], len("- tidy: Keep the code tidy.\n  More about tidying.\n"))
        self.assertIn("subagent:reviewer", loaded)
        self.assertIn("instructions:/code/shop/CLAUDE.md", loaded)
        self.assertEqual(self.k["base_tokens"], 25010)
        self.assertEqual(self.k["project"], "/code/shop")

    def test_deferred_tools_listed_twice_count_once(self):
        block = len("## shopdb\nQuery the shop.")
        self.assertEqual(self.k["loaded"]["mcp:shopdb"], block + len("mcp__shopdb__query") + 1)

    def test_what_was_used_and_what_failed(self):
        used = self.k["used"]
        self.assertEqual(used["mcp:shopdb"], 3)            # two in the session, one by a subagent
        self.assertEqual(used["skill:tidy"], 1)
        self.assertEqual(used["skill:deploy"], 1)          # typed as /deploy
        self.assertEqual(used["subagent:reviewer"], 1)
        self.assertNotIn("mcp:claude_ai_Gamma", used)
        self.assertEqual(self.k["errors"]["mcp:shopdb"], 1)
        self.assertEqual(self.k["retries"]["mcp:shopdb"], 1)
        self.assertEqual(self.k["denied"]["tool:Bash"], 1)
        self.assertNotIn("tool:Bash", self.k["errors"])
        self.assertEqual(self.k["errors"]["hook:Stop"], 1)
        self.assertIn("hook:PreToolUse guard.py", used)
        self.assertEqual(self.k["subagent_files"], 1)

    def test_server_names_match_tool_names(self):
        self.assertEqual(claude_code.server("claude.ai Google Drive"), "claude_ai_Google_Drive")
        self.assertEqual(claude_code.server("claude-in-chrome"), "claude-in-chrome")


def session(i, project="/p/a", loaded=None, used=None, errors=None):
    return {"agent": "claude-code", "session": f"s{i}", "project": project, "start": f"2026-10-{1 + i % 28:02d}T09:00",
            "base_tokens": 50000, "loaded": loaded or {}, "used": used or {}, "errors": errors or {},
            "retries": {}, "denied": {}, "samples": {}, "attachments": {}}


class Verdicts(unittest.TestCase):
    def test_each_verdict(self):
        kits = []
        for i in range(40):
            project = ["/p/a", "/p/b", "/p/c"][i % 3]
            loaded = {"mcp:gamma": 2000, "skill:often": 400, "skill:once": 400, "skill:here": 400, "mcp:flaky": 800}
            used = {"skill:often": 1, "mcp:flaky": 5, "tool:Bash": 20}
            errors = {"mcp:flaky": 2, "tool:Bash": 0}
            if i == 7:
                used["skill:once"] = 1
            if project == "/p/a" and i < 12:
                used["skill:here"] = 1
            if i < 5:
                loaded["skill:fresh"] = 100
            kits.append(session(i, project, loaded, used, errors))
        items = kit.ledger(kits)
        verdict = {k: it.verdict for k, it in items.items()}
        self.assertEqual(verdict["mcp:gamma"], "ballast")
        self.assertEqual(verdict["skill:often"], "earns")
        self.assertEqual(verdict["skill:once"], "rare")
        self.assertEqual(verdict["skill:here"], "elsewhere")
        self.assertEqual(verdict["mcp:flaky"], "misused")
        self.assertEqual(verdict["skill:fresh"], "new")
        self.assertEqual(items["mcp:gamma"].weight, 500)
        s = kit.summary(kits, items)
        self.assertEqual(s["ballast_tokens"], 500)
        self.assertEqual(s["sessions"], 40)

    def test_builtins_are_not_ballast(self):
        kits = [session(i, loaded={"skill:code-review": 400}) for i in range(30)]
        items = kit.ledger(kits, {}, claude_code.origin)
        self.assertEqual(items["skill:code-review"].verdict, "fixed")

    def test_plugin_is_the_sum_of_its_parts(self):
        installed = {"plugin:plug": {"source": "plugin plug@market", "remove": "claude plugin disable plug@market"}}
        kits = [session(i, loaded={"skill:plug:a": 400, "skill:plug:b": 800}) for i in range(30)]
        items = kit.ledger(kits, installed, claude_code.origin)
        self.assertEqual(items["plugin:plug"].weight, 300)
        self.assertEqual(items["plugin:plug"].verdict, "ballast")
        self.assertEqual(items["skill:plug:a"].origin["remove"], "claude plugin disable plug@market")


class Cache(unittest.TestCase):
    def test_hit_and_miss(self):
        with tempfile.TemporaryDirectory() as d:
            c = kit.Cache(Path(d) / "k.sqlite")
            c.put("f", "1", {"a": 1})
            self.assertEqual(c.get("f", "1"), {"a": 1})
            self.assertIsNone(c.get("f", "2"))
            c.close()


class Command(unittest.TestCase):
    def test_kit_json_on_the_fixture(self):
        os.environ["SDOG_NO_CACHE"] = "1"
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                cli.main(["kit", "--path", str(FIXTURE.parent), "--json"])
            data = json.loads(out.getvalue())
        finally:
            del os.environ["SDOG_NO_CACHE"]
        self.assertEqual(data["summary"]["sessions"], 1)
        keys = {i["key"]: i for i in data["items"]}
        self.assertEqual(keys["mcp:shopdb"]["calls"], 3)
        self.assertEqual(keys["mcp:claude_ai_Gamma"]["verdict"], "new")


if __name__ == "__main__":
    unittest.main()
