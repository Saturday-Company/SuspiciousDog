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


class ShareV2(unittest.TestCase):
    """Format 2 carries kit counts, and never a private name."""

    def test_private_names_stay_home(self):
        from suspiciousdog import share
        loaded = {"skill:preventivo-saturday": 300, "mcp:claude_ai_AcmeCRM": 500, "mcp:my_secret_db": 200,
                  "plugin:secret": 100, "instructions:/home/u/acme/CLAUDE.md": 900, "subagent:acme-reviewer": 50,
                  "mcp:claude_ai_Gamma": 600, "skill:anthropic-skills:pdf": 100, "skill:anthropic-skills:mine": 90,
                  "skill:simplify": 40}
        used = {"tool:Bash": 10, "tool:acme_internal_tool": 3, "mcp:claude_ai_Gamma": 1}
        kits = [{"agent": "claude-code", "session": f"s{i}", "project": "/home/u/acme", "start": "2026-10-01",
                 "base_tokens": 1000, "loaded": loaded, "used": used, "errors": {}, "retries": {}, "denied": {},
                 "samples": {}, "attachments": {}} for i in range(25)]

        def origin(key, installed):
            if key == "plugin:secret":
                return {"source": "plugin secret@acme-market, installed 2026-09-01"}
            return {"builtin": True} if key == "skill:simplify" else {}
        items = kit.ledger(kits, {}, origin)
        data = share.payload({}, [], {"claude-code": 25}, items, kit.summary(kits, items))
        self.assertTrue(share.validate(data))
        names = {row[0] for row in data["kit"]["items"]}
        self.assertEqual(names, {"mcp:gamma", "skill:anthropic-skills:pdf", "skill:simplify", "tool:Bash"})
        text = str(data).lower()
        for secret in ("preventivo", "acme", "secret", "claude.md", "/home", "mine"):
            self.assertNotIn(secret, text)
        self.assertGreaterEqual(data["kit"]["private_items"], 6)

    def test_validate_rejects_a_private_name(self):
        from suspiciousdog import share
        data = {"suspiciousdog": "0.2.0", "agents": {}, "turns": 0, "days": 0, "results": [], "format": 2,
                "kit": {"sessions": 1, "context_tokens": 1, "ballast_tokens": 0, "private_items": 0,
                        "items": [["skill:preventivo-saturday", 1, 0, 0, 0, 10]]}}
        with self.assertRaises(AssertionError):
            share.validate(data)
        data["kit"]["items"] = [["plugin:secret@acme-market", 1, 0, 0, 0, 10]]
        with self.assertRaises(AssertionError):
            share.validate(data)
