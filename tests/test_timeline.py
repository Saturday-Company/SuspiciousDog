import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from suspiciousdog import failures, kit, rules, timeline
from suspiciousdog.adapters import claude_code
from suspiciousdog.model import Turn
from suspiciousdog.signals import ALL_OUTCOMES, EXTRA_OUTCOMES, OUTCOMES

START = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "kit" / "s1.jsonl"


def day(i):
    return (START + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ")


def session(i, loaded=(), digests=None, subagent_models=None):
    return {"agent": "claude-code", "session": f"s{i}", "project": "/p", "start": day(i), "base_tokens": 1000,
            "loaded": {key: 400 for key in loaded}, "used": {}, "errors": {}, "retries": {}, "denied": {},
            "samples": {}, "attachments": {"skill_listing": 1}, "digests": digests or {},
            "subagent_models": subagent_models or {}, "models": {}}


class Changes(unittest.TestCase):
    def setUp(self):
        kits = []
        for i in range(30):
            loaded = ["skill:old"] if i < 20 else []
            loaded += ["mcp:new"] if i >= 10 else []
            text = "v1" if i < 15 else "v2"
            digests = {"instructions:~/.claude/CLAUDE.md": [text, 1000 if i < 15 else 1400]}
            models = {"claude-opus-5-5": 3} if i < 22 else {"claude-sonnet-5-5": 3}
            kits.append(session(i, loaded, digests, models))
        self.kits = kits
        self.found = timeline.changes(kits)

    def test_added_removed_edited_and_model(self):
        what = {c.day: c.what for c in self.found}
        self.assertIn("added mcp new", what["2026-09-11"])
        self.assertIn("removed skill old", what["2026-09-21"])
        self.assertIn("edited ~/.claude/CLAUDE.md (+400 chars)", what["2026-09-16"])
        self.assertIn("subagents: sonnet-5-5 0% → 100% of runs", what["2026-09-23"])

    def test_nothing_at_the_edges(self):
        self.assertFalse(any(c.day == "2026-09-01" for c in self.found))

    def test_measure_waits_for_enough_turns(self):
        turns = [Turn("claude-code", f"s{i}", "/p", START + timedelta(days=i, hours=1), "do it", reply="ok")
                 for i in range(30)]
        timeline.measure(self.found, turns)
        self.assertTrue(all(not c.rows for c in self.found))

    def test_measure_finds_a_shift(self):
        turns = []
        for i in range(30):
            for j in range(20):
                bad = i >= 15 and j < 8
                turns.append(Turn("claude-code", f"s{i}", "/p", START + timedelta(days=i, minutes=j), "do it",
                                  reply="no, that's wrong" if bad else "ok thanks"))
        timeline.measure(self.found, turns, days=10)
        edit = next(c for c in self.found if c.day == "2026-09-16")
        rows = dict(edit.rows)
        self.assertLess(rows["pushback"]["q"], 0.05)
        self.assertGreater(rows["pushback"]["rate_with"], rows["pushback"]["rate_without"])


class Failures(unittest.TestCase):
    def test_kinds(self):
        cases = {
            "Vercel API request failed (403 Forbidden)": "auth",
            "Input validation error: Invalid arguments for tool x": "wrong arguments",
            'ERROR: 42P01: relation "public.membro" does not exist': "bad code",
            "This session's tab group no longer exists (tabs were closed).": "wrong target",
            "Multiple Chrome browsers are connected and none has been selected": "setup",
            "Permission for this action was denied by the Claude Code auto mode classifier": "blocked",
            "The operation timed out.": "timeout",
            "something odd": "other",
        }
        for text, kind in cases.items():
            self.assertEqual(failures.classify(text), kind, text)

    def test_fixture_failure_is_classified(self):
        k = claude_code.kit(FIXTURE)
        self.assertEqual(k["error_kinds"]["mcp:shopdb"], {"bad code": 1})
        self.assertEqual(k["tools"]["mcp:shopdb"]["query"], [3, 1])
        self.assertIn("instructions:/code/shop/CLAUDE.md", k["digests"])


class Outcomes(unittest.TestCase):
    def turn(self, final, reply, request="add the export button"):
        t = Turn("x", "s", "p", None, request, reply=reply)
        t.texts = [final]
        return t

    def test_declining_an_offer_is_not_a_complaint(self):
        declined = self.turn("Done. Shall I also add tests?", "no, later")
        self.assertTrue(OUTCOMES["pushback"](declined))
        self.assertFalse(EXTRA_OUTCOMES["complaint"](declined))
        angry = self.turn("Done.", "no, that's not what I asked")
        self.assertTrue(EXTRA_OUTCOMES["complaint"](angry))

    def test_asks_again(self):
        t = self.turn("Here it is.", "add the export button to the orders page", "add the export button to orders page")
        self.assertTrue(ALL_OUTCOMES["asks again"](t))
        self.assertFalse(ALL_OUTCOMES["asks again"](self.turn("Here.", "great, now the invoices")))

    def test_sniff_keeps_its_four_outcomes(self):
        self.assertEqual(list(OUTCOMES), ["pushback", "deferral", "interruption", "quick yes"])

    def test_turn_tokens_and_time(self):
        first = next(claude_code.turns(FIXTURE))
        self.assertEqual(first.tokens, 5)


class Rules(unittest.TestCase):
    def test_an_echoed_rule(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "CLAUDE.md"
            path.write_text("# Rules\n\n- Never push to the main branch without running\n  the integration tests first.\n"
                            "- Write commit messages in English, always.\n")
            found = rules.read_rules([str(path)])
            self.assertEqual(len(found), 2)
            self.assertIn("integration tests first", found[0].text)
            turns = [Turn("x", "s1", "p", None, "ship it", reply="no! you pushed to main again without the integration tests"),
                     Turn("x", "s2", "p", None, "ship it", reply="ok")]
            echoed = rules.echoes(found, turns, {str(path): {"s1", "s2"}})
            self.assertEqual([len(r.echoes) for r in echoed], [1])
            self.assertEqual(rules.echoes(found, turns, {str(path): {"s2"}}), [])


if __name__ == "__main__":
    unittest.main()
