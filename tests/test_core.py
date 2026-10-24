import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from suspiciousdog import cli, lab, share, synthetic
from suspiciousdog.adapters import ADAPTERS, load
from suspiciousdog.signals import ALL_OUTCOMES, FACTORS, OUTCOMES
from suspiciousdog.stats import benjamini_hochberg, compare, fisher

FIXTURES = Path(__file__).parent / "fixtures"


class Stats(unittest.TestCase):
    def test_fisher_matches_r(self):
        # fisher.test(matrix(c(1, 11, 9, 3), 2)) in R gives p = 0.002759
        self.assertAlmostEqual(fisher(1, 9, 11, 3), 0.002759, places=5)

    def test_fisher_degenerate(self):
        self.assertEqual(fisher(0, 0, 0, 0), 1.0)
        self.assertEqual(fisher(5, 0, 5, 0), 1.0)

    def test_benjamini_hochberg(self):
        rows = [{"p": p} for p in (0.01, 0.04, 0.03, 0.5)]
        benjamini_hochberg(rows)
        self.assertAlmostEqual(rows[0]["q"], 0.04)
        self.assertAlmostEqual(rows[2]["q"], 0.04 * 4 / 3)
        self.assertAlmostEqual(rows[3]["q"], 0.5)

    def test_compare(self):
        r = compare(range(10), lambda x: x < 5, lambda x: x in (0, 1, 7))
        self.assertEqual((r["n_with"], r["hits_with"], r["n_without"], r["hits_without"]), (5, 2, 5, 1))
        self.assertAlmostEqual(r["ratio"], 2.0)


class ClaudeCode(unittest.TestCase):
    def setUp(self):
        self.turns = list(ADAPTERS["claude-code"].turns(FIXTURES / "claude" / "session.jsonl"))

    def test_turns(self):
        self.assertEqual([t.request for t in self.turns],
                         ["fix the login form", "not now, later", "no, that's not what I asked"])
        first, second = self.turns[0], self.turns[1]
        self.assertEqual(first.files_written, {"/code/shop/login.py"})
        self.assertEqual(first.reply, "not now, later")
        self.assertTrue(second.interrupted)
        self.assertEqual(second.errors, 1)
        self.assertNotIn("subagent noise", " ".join(self.turns[2].texts))

    def test_signals(self):
        first, second = self.turns[0], self.turns[1]
        self.assertTrue(FACTORS["ends offering more work"](first))
        self.assertTrue(FACTORS["claims done without looking"](first))
        self.assertTrue(OUTCOMES["deferral"](first))
        self.assertTrue(OUTCOMES["pushback"](second))

    def test_detect_by_content(self):
        self.assertTrue(ADAPTERS["claude-code"].detect(FIXTURES / "claude" / "session.jsonl"))
        self.assertFalse(ADAPTERS["jsonl"].detect(FIXTURES / "claude" / "session.jsonl"))


class Synthetic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = synthetic.write(Path(tempfile.mkdtemp()))
        cls.turns, cls.per_agent = load(path=cls.folder)

    def test_loads_through_the_open_format(self):
        self.assertEqual(self.per_agent, {"jsonl": 300})
        self.assertEqual({t.agent for t in self.turns}, {"claude-code", "codex", "gemini"})

    def test_finds_the_planted_effect(self):
        found = {(o, f) for o, f, _ in lab.findings(lab.sniff(self.turns))}
        self.assertIn(("deferral", "ends offering more work"), found)

    def test_noise_stays_noise(self):
        tables = lab.sniff(self.turns)
        real = {f for o, f, _ in lab.findings(tables) if o == "pushback"}
        self.assertNotIn("claims done without looking", real)

    def test_share_has_no_text(self):
        data = share.payload(lab.sniff(self.turns), self.turns, self.per_agent)
        self.assertTrue(share.validate(data))
        dumped = json.dumps(data)
        typed = {text for t in self.turns for text in (t.request, t.reply, *t.texts) if len(text) > 12}
        self.assertTrue(typed)
        for text in typed:
            self.assertNotIn(text, dumped)
        self.assertNotIn(str(self.folder), dumped)
        self.assertIsNotNone(share.issue_url(data))

    def test_share_rejects_anything_else(self):
        data = share.payload(lab.sniff(self.turns), self.turns, self.per_agent)
        data["results"].append(["fix the login form", "pushback", 1, 1, 1, 1])
        with self.assertRaises(AssertionError):
            share.validate(data)

    def test_before_after(self):
        from datetime import datetime, timezone
        rows = dict(lab.before_after(self.turns, datetime(2026, 9, 20, tzinfo=timezone.utc)))
        self.assertEqual(set(rows), set(ALL_OUTCOMES))
        self.assertGreater(rows["quick yes"]["n_with"], 0)


class Cli(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(list(argv))
        return out.getvalue()

    def test_demo_says_it_is_synthetic(self):
        self.assertIn("SYNTHETIC DATA", self.run_cli("demo"))

    def test_sniff_test_show_on_a_folder(self):
        folder = synthetic.write(Path(tempfile.mkdtemp()), sessions=60)
        self.assertIn("Sniffed", self.run_cli("sniff", "--path", str(folder)))
        self.assertIn("Hypothesis", self.run_cli("test", "t.tool_calls > 40", "--path", str(folder)))
        self.assertIn("turns where", self.run_cli("show", "ends offering more work", "--outcome", "deferral",
                                                   "--path", str(folder)))
        self.assertIn("Change at", self.run_cli("before-after", "2026-09-20", "--path", str(folder)))

    def test_share_save(self):
        folder = synthetic.write(Path(tempfile.mkdtemp()), sessions=60)
        target = Path(tempfile.mkdtemp()) / "out.json"
        self.run_cli("share", "--path", str(folder), "--save", str(target))
        self.assertTrue(share.validate(json.loads(target.read_text())))


if __name__ == "__main__":
    unittest.main()
