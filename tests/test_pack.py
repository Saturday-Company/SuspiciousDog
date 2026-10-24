"""The pack page: shares from issues, added up, and nothing from an issue but names and numbers."""

import importlib.util
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("pack", Path(__file__).parent.parent / "scripts" / "pack.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)

GOOD = {"suspiciousdog": "0.2.0", "agents": {"claude-code": 40}, "turns": 300, "days": 20,
        "results": [["ends_offering_more_work", "deferral", 50, 6, 250, 3], ["writes_files", "pushback", 120, 10, 180, 9]],
        "format": 2, "kit": {"sessions": 40, "context_tokens": 52000, "ballast_tokens": 900, "private_items": 12,
                             "items": [["mcp:gamma", 38, 0, 0, 0, 600], ["tool:Bash", 40, 40, 900, 30, 0]]}}


def issue(body, n, labels=("results",), user=None, state="open"):
    return json.dumps({"number": n, "body": body, "labels": [{"name": x} for x in labels], "state": state,
                       "user": {"login": user or f"u{n}"}})


def block(data):
    return f"### Counts\n\n```json\n{json.dumps(data)}\n```\n\n### Notes\n\n<script>alert(1)</script>"


class Pack(unittest.TestCase):
    def test_only_valid_shares_count(self):
        other = dict(GOOD, turns=301)
        evil = json.loads(json.dumps(GOOD))
        evil["results"][0][0] = "<img src=x onerror=alert(1)>"
        private = json.loads(json.dumps(GOOD))
        private["kit"]["items"].append(["skill:preventivo-saturday", 1, 0, 0, 0, 50])
        impossible = json.loads(json.dumps(GOOD))
        impossible["results"][0] = ["ends_offering_more_work", "deferral", 10, 50, 10, 1]   # 50 hits in 10 turns
        huge = json.loads(json.dumps(GOOD))
        huge["results"][0] = ["ends_offering_more_work", "deferral", 10 ** 9, 1, 10, 1]
        boolean = dict(GOOD, turns=True)
        lines = [issue(block(GOOD), 1, user="ann"), issue(block(other), 2, user="ann"),   # one person: once, the latest
                 issue(block(other), 3, user="bob"), issue(block(evil), 4), issue(block(private), 5),
                 issue(block(impossible), 6), issue(block(huge), 7), issue(block(boolean), 8),
                 issue(block(other), 9, labels=("results", "invalid")), issue(block(GOOD), 10, state="closed"),
                 issue("no json here", 11), "not json"]
        found = pack.shares(lines)
        self.assertEqual(len(found), 2)
        self.assertEqual({d["turns"] for d in found}, {301})

    def test_page(self):
        found = pack.shares([issue(block(GOOD), 1), issue(block(dict(GOOD, turns=301)), 2)])
        self.assertEqual(len(found), 2)
        p = pack.add_up(found)
        self.assertEqual(p["shares"], 2)
        self.assertEqual(p["turns"], 601)
        self.assertEqual([it["name"] for it in p["items"]], ["tool:Bash", "mcp:gamma"])
        row = next(r for r in p["results"] if r["factor"] == "ends_offering_more_work")
        self.assertEqual((row["turns"], row["same_way"], row["shares"]), (100, 2, 2))
        html = pack.page(p)
        self.assertIn("What the pack found", html)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("preventivo", html)


    def test_empty_page(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "issues.jsonl"
            src.write_text("")
            pack.main(src, Path(tmp) / "site")
            self.assertIn("No shares right now", (Path(tmp) / "site" / "index.html").read_text())


if __name__ == "__main__":
    unittest.main()
