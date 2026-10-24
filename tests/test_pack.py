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


def issue(body, n, labels=("results",)):
    return json.dumps({"number": n, "body": body, "labels": [{"name": x} for x in labels]})


def block(data):
    return f"### Counts\n\n```json\n{json.dumps(data)}\n```\n\n### Notes\n\n<script>alert(1)</script>"


class Pack(unittest.TestCase):
    def test_only_valid_shares_count(self):
        other = dict(GOOD, turns=301)
        evil = json.loads(json.dumps(GOOD))
        evil["results"][0][0] = "<img src=x onerror=alert(1)>"
        private = json.loads(json.dumps(GOOD))
        private["kit"]["items"].append(["skill:preventivo-saturday", 1, 0, 0, 0, 50])
        lines = [issue(block(GOOD), 1), issue(block(GOOD), 2),            # the same share twice: once
                 issue(block(other), 3), issue(block(evil), 4), issue(block(private), 5),
                 issue(block(other), 6, labels=("results", "invalid")), issue("no json here", 7), "not json"]
        found = pack.shares(lines)
        self.assertEqual(len(found), 2)

    def test_page(self):
        found = pack.shares([issue(block(GOOD), 1), issue(block(dict(GOOD, turns=301)), 2)])
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


if __name__ == "__main__":
    unittest.main()
