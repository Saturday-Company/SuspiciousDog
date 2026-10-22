import unittest
from pathlib import Path

from suspiciousdog.adapters import ADAPTERS, load
from suspiciousdog.model import EDIT, SHELL
from suspiciousdog.signals import FACTORS, OUTCOMES

FIXTURES = Path(__file__).parent / "fixtures"


def turns(agent, *parts):
    return list(ADAPTERS[agent].turns(FIXTURES.joinpath(*parts)))


class Detection(unittest.TestCase):
    def test_each_fixture_is_claimed_by_exactly_its_adapter(self):
        cases = {
            "claude-code": FIXTURES / "claude" / "session.jsonl",
            "codex": FIXTURES / "codex" / "legacy.jsonl",
            "gemini": FIXTURES / "gemini" / "session.jsonl",
            "aider": FIXTURES / "aider" / ".aider.chat.history.md",
        }
        for agent, path in cases.items():
            claimed = [name for name, a in ADAPTERS.items() if a.detect(path)]
            self.assertEqual(claimed, [agent], path)

    def test_load_a_mixed_folder(self):
        found, per_agent = load(path=FIXTURES)
        self.assertEqual(per_agent, {"claude-code": 1, "codex": 2, "gemini": 1, "aider": 1})
        self.assertTrue(all(t.request for t in found))


class Codex(unittest.TestCase):
    def test_legacy(self):
        first, second = turns("codex", "codex", "legacy.jsonl")
        self.assertEqual(first.request, "fix the failing test in hello.py")
        self.assertEqual(first.reply, "great, thanks")
        self.assertEqual([e.category for e in first.calls], [SHELL, EDIT])
        self.assertEqual(first.files_written, {"hello.py"})
        self.assertEqual(first.errors, 1)
        self.assertEqual(first.final, "Fixed the typo in hello.py; tests pass.")
        self.assertTrue(OUTCOMES["quick yes"](first))

    def test_paginated_ignores_injected_context(self):
        first, second, third = turns("codex", "codex", "paginated.jsonl")
        self.assertEqual([first.request, second.request, third.request], ["run the tests", "not now, later", "ok go ahead"])
        self.assertTrue(FACTORS["ends offering more work"](first))
        self.assertTrue(OUTCOMES["deferral"](first))
        self.assertTrue(second.interrupted)


class Gemini(unittest.TestCase):
    def test_replay(self):
        first, second = turns("gemini", "gemini", "session.jsonl")
        self.assertEqual(first.request, "fix the failing test in hello.py")
        self.assertEqual(first.reply, "no, it still fails")
        self.assertEqual([e.category for e in first.calls], [SHELL, EDIT])
        self.assertEqual(first.errors, 1)
        self.assertEqual(first.final, "Fixed the typo.")
        self.assertTrue(OUTCOMES["pushback"](first))
        self.assertTrue(second.interrupted)


class Aider(unittest.TestCase):
    def test_markdown(self):
        first, second = turns("aider", "aider", ".aider.chat.history.md")
        self.assertEqual(first.request, "fix the typo in hello()")
        self.assertEqual(first.reply, "run the tests and show me the result")
        self.assertEqual(first.files_written, {"hello.py"})
        self.assertEqual([e.detail for e in second.calls], ["pytest -q"])
        self.assertEqual(first.when.year, 2026)


if __name__ == "__main__":
    unittest.main()
