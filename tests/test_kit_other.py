"""0.2.0: the kit for Codex, Gemini CLI and Aider, from fixtures built on their source code (no real sessions)."""

import os
import tempfile
import unittest
from pathlib import Path

from suspiciousdog import kit
from suspiciousdog.adapters import aider, codex, gemini

HERE = Path(__file__).parent / "fixtures" / "kit-other"


class Codex(unittest.TestCase):
    def setUp(self):
        self.k = codex.kit(HERE / "codex-rollout.jsonl")

    def test_loaded(self):
        self.assertEqual(self.k["project"], "/srv/p")
        self.assertIn("skill:omarchy", self.k["loaded"])
        self.assertIn("skill:pdf", self.k["loaded"])
        files = [key for key in self.k["loaded"] if key.startswith("instructions:")]
        self.assertEqual(len(files), 2)                              # the global AGENTS.md and the project's
        self.assertTrue(any(f.endswith("/srv/p/AGENTS.md") for f in files))
        self.assertEqual(self.k["base_tokens"], 12000)
        self.assertEqual(self.k["models"], {"gpt-5.5": 1})

    def test_used_and_failed(self):
        self.assertEqual(self.k["used"]["mcp:github"], 2)
        self.assertEqual(self.k["errors"]["mcp:github"], 1)
        self.assertEqual(self.k["error_kinds"]["mcp:github"], {"auth": 1})
        self.assertEqual(self.k["used"]["skill:omarchy"], 1)        # read with cat
        self.assertEqual(self.k["used"]["skill:pdf"], 1)            # invoked with $pdf
        self.assertNotIn("tool:exec_command", self.k["used"])


class Gemini(unittest.TestCase):
    def setUp(self):
        self.k = gemini.kit(HERE / "gemini-session.jsonl")

    def test_loaded(self):
        self.assertIn("instructions:/srv/p/GEMINI.md", self.k["loaded"])
        self.assertTrue(any("extensions/acme/GEMINI.md" in key for key in self.k["loaded"]))
        self.assertGreater(self.k["loaded"]["mcp:github"], 20)
        self.assertEqual(self.k["base_tokens"], 9000)

    def test_used_and_failed(self):
        self.assertEqual(self.k["used"], {"mcp:github": 1, "skill:omarchy": 1, "tool:read_file": 1})
        self.assertEqual(self.k["error_kinds"]["mcp:github"], {"auth": 1})
        self.assertEqual(self.k["tools"]["mcp:github"], {"list_issues": [1, 1]})


class Aider(unittest.TestCase):
    def test_chats(self):
        kits = aider.kit(HERE / "aider" / ".aider.chat.history.md")
        self.assertEqual(len(kits), 2)
        first, second = kits
        self.assertEqual([k.split("/")[-1] for k in first["loaded"]], ["CONVENTIONS.md"])
        self.assertGreater(list(first["loaded"].values())[0], 20)
        self.assertEqual(first["models"], {"gpt-5": 1})
        self.assertEqual(first["base_tokens"], 4100)
        self.assertEqual(second["base_tokens"], 812)
        self.assertEqual(second["models"], {"claude-sonnet-5-5": 1})


class Scan(unittest.TestCase):
    def test_every_agent_in_one_ledger(self):
        old = os.environ.get("SDOG_NO_CACHE")
        os.environ["SDOG_NO_CACHE"] = "1"
        try:
            kits = kit.scan(path=HERE)
        finally:
            os.environ.pop("SDOG_NO_CACHE") if old is None else os.environ.__setitem__("SDOG_NO_CACHE", old)
        self.assertEqual(sorted({k["agent"] for k in kits}), ["aider", "codex", "gemini"])
        items = kit.ledger(kits)
        self.assertEqual(items["mcp:github"].errors, 2)              # one from Codex, one from Gemini


class Config(unittest.TestCase):
    def test_gemini_config_has_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / ".gemini"
            (home / "extensions" / "acme").mkdir(parents=True)
            (home / "settings.json").write_text('{"mcpServers": {"github": {"command": "gh-mcp"}}}')
            (home / "extensions" / "acme" / "gemini-extension.json").write_text('{"name": "acme", "mcpServers": {"x": {}}}')
            old = os.environ.get("GEMINI_CLI_HOME")
            os.environ["GEMINI_CLI_HOME"] = tmp
            try:
                found = gemini.config()
            finally:
                os.environ.pop("GEMINI_CLI_HOME") if old is None else os.environ.__setitem__("GEMINI_CLI_HOME", old)
        self.assertEqual(found["mcp:github"]["fix"]["undo"], ["mcp", "enable", "github"])
        self.assertEqual(found["plugin:acme"]["fix"]["bin"], "gemini")
        self.assertEqual(found["mcp:x"]["plugin"], "acme")


if __name__ == "__main__":
    unittest.main()
