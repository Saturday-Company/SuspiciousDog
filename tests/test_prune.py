import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from suspiciousdog import cli, journal, kit, prune, report, timeline
from suspiciousdog.adapters import claude_code

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "kit"


def session(i, loaded, used=None):
    return {"agent": "claude-code", "session": f"s{i}", "project": "/p/a", "start": f"2026-10-{1 + i % 28:02d}T09:00",
            "base_tokens": 30000, "loaded": loaded, "used": used or {}, "errors": {}, "retries": {}, "denied": {},
            "samples": {}, "attachments": {"skill_listing": 1}}


class FakeHome(unittest.TestCase):
    """A Claude Code config in a temporary folder, and a fake `claude` that writes down what it was asked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = root / "claude"
        (self.cfg / "skills" / "lonely").mkdir(parents=True)
        (self.cfg / "skills" / "lonely" / "SKILL.md").write_text("---\nname: lonely\n---\n")
        (self.cfg / "plugins").mkdir()
        (self.cfg / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"plugins": {"plug@market": [{"scope": "user", "installedAt": "2026-09-01T00:00:00Z"}]}}))
        (self.cfg / "settings.json").write_text(json.dumps({"enabledPlugins": {"plug@market": True}}))
        (self.cfg / ".claude.json").write_text(json.dumps({"mcpServers": {"my db": {"type": "stdio", "command": "db"}}}))
        self.log = root / "calls.log"
        fake = root / "claude-fake"
        fake.write_text(f"#!/bin/sh\necho \"$@\" >> {self.log}\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.env = {"CLAUDE_CONFIG_DIR": str(self.cfg), "XDG_DATA_HOME": str(root / "data"),
                    "SDOG_CLAUDE": str(fake), "SDOG_NO_CACHE": "1"}
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        loaded = {"skill:lonely": 400, "skill:plug:a": 800, "mcp:my_db": 200, "skill:code-review": 300}
        kits = [session(i, loaded) for i in range(30)]
        self.items = kit.ledger(kits, claude_code.config(), claude_code.origin)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def test_proposals(self):
        mine, yours = prune.proposals(self.items, 30)
        what = [p.what for p in mine]
        self.assertEqual(what[0], "disable plugin plug")                   # the biggest saving first
        self.assertIn("put skill lonely in the attic", what)
        self.assertIn("remove mcp my_db", what)
        self.assertFalse(any("code-review" in p.key for p in mine + yours))   # built in: not ours to touch
        self.assertFalse(any(p.key == "skill:plug:a" for p in mine))          # its plugin is the switch

    def test_apply_and_undo_a_move(self):
        mine, _ = prune.proposals(self.items, 30)
        p = next(p for p in mine if p.key == "skill:lonely")
        e = prune.apply(p)
        self.assertFalse((self.cfg / "skills" / "lonely").exists())
        self.assertTrue((prune.attic() / "skills" / "lonely" / "SKILL.md").exists())
        self.assertEqual(oct(journal.path().stat().st_mode & 0o777), "0o600")
        prune.undo(e)
        self.assertTrue((self.cfg / "skills" / "lonely" / "SKILL.md").exists())
        with self.assertRaises(RuntimeError):
            prune.undo(e)

    def test_apply_and_undo_through_claude(self):
        mine, _ = prune.proposals(self.items, 30)
        server = next(p for p in mine if p.key == "mcp:my_db")
        e = prune.apply(server)
        prune.undo(e)
        calls = self.log.read_text().splitlines()
        self.assertEqual(calls[0], "mcp remove my db -s user")
        self.assertTrue(calls[1].startswith("mcp add-json my db {\"type\": \"stdio\""))

    def test_cli_prune_apply_note_journal(self):
        out = io.StringIO()
        with redirect_stdout(out):
            cli.main(["prune", "--path", str(FIXTURE_DIR), "--apply", "all"])
            cli.main(["note", "disconnected", "Gamma", "--key", "mcp:claude_ai_Gamma"])
            cli.main(["journal", "--path", str(FIXTURE_DIR)])
        text = out.getvalue()
        self.assertIn("noted", text)
        self.assertIn("disconnected Gamma", text)
        self.assertIn("too early", text)

    def test_checkup_and_report_run(self):
        out = io.StringIO()
        target = Path(self.tmp.name) / "r.html"
        with redirect_stdout(out):
            cli.main(["checkup", "--path", str(FIXTURE_DIR)])
            cli.main(["report", "--path", str(FIXTURE_DIR), "--out", str(target)])
        self.assertIn("sessions", out.getvalue())
        html = target.read_text()
        self.assertIn("<title>SuspiciousDog report</title>", html)
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))   # nothing loaded from anywhere

    def test_report_escapes(self):
        it = self.items["skill:lonely"]
        it.origin = {**it.origin, "source": "<script>alert(1)</script>"}
        html = report.build([], self.items, kit.summary([], self.items), [], [], [], timeline.MIN_AFTER)
        self.assertNotIn("<script>alert", html)


class Picking(unittest.TestCase):
    def test_pick(self):
        self.assertEqual(cli._pick("1, 3,3,9", 4), [1, 3])
        self.assertEqual(cli._pick("all", 3), [1, 2, 3])
        self.assertEqual(cli._pick("", 3), [])


if __name__ == "__main__":
    unittest.main()
