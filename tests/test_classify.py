"""The optional classifier, with a fake `claude` so nothing leaves the machine."""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from suspiciousdog import classify


class Classify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.calls = root / "calls"
        fake = root / "claude"
        # Answers "accepts" for every item it gets, and writes down each call.
        self.argv = root / "argv"
        fake.write_text("#!/usr/bin/env python3\nimport json, os, sys\nitems = json.loads(sys.stdin.read())\n"
                        f"open({str(self.calls)!r}, 'a').write('x')\n"
                        f"open({str(self.argv)!r}, 'w').write(json.dumps([sys.argv[1:], os.getcwd()]))\n"
                        "print(json.dumps({'result': json.dumps(['accepts'] * len(items))}))\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.env = {"SDOG_CLAUDE": str(fake), "XDG_CACHE_HOME": str(root / "cache")}
        self.old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.tmp.cleanup()

    def test_sample_is_labelled(self):
        rows = classify.sample()
        self.assertEqual(len(rows), 80)
        self.assertTrue({r["label"] for r in rows} <= set(classify.LABELS))

    def test_regex_baseline(self):
        self.assertEqual(classify.regex_label("Done. Shall I also add caching?", "no"), "declines")
        self.assertEqual(classify.regex_label("Done. Shall I also add caching?", "not now, later"), "defers")
        self.assertEqual(classify.regex_label("Fixed.", "still broken"), "complaint")
        self.assertEqual(classify.regex_label("Fixed.", "perfetto"), "accepts")

    def test_label_caches(self):
        items = [classify._item("Fixed.", f"reply {i}") for i in range(50)]
        self.assertEqual(classify.label(items), ["accepts"] * 50)
        self.assertEqual(self.calls.read_text(), "xx")             # 50 items, batches of 40
        classify.label(items)
        self.assertEqual(self.calls.read_text(), "xx")             # the second time, all from the cache

    def test_claude_runs_restricted_in_an_empty_folder(self):
        classify.label([classify._item("Fixed.", "argv check")])
        argv, cwd = json.loads(self.argv.read_text())
        self.assertIn("--restricted", argv)
        self.assertIn("sdog-classify-", cwd)

    def test_miscount_splits_the_batch(self):
        answers = iter(['["accepts"]', '["complaint"]', '["accepts", "accepts", "accepts"]'])
        classify.BACKENDS["fake"] = lambda batch, model, url: next(answers) if len(batch) == 1 else '["accepts"]'
        classify.DEFAULT_MODELS["fake"] = "m"
        try:
            got = classify.label([classify._item("a", "b"), classify._item("a", "c")], backend="fake")
        finally:
            del classify.BACKENDS["fake"], classify.DEFAULT_MODELS["fake"]
        self.assertEqual(got, ["accepts", "complaint"])

    def test_estimate_and_agreement(self):
        e = classify.estimate([classify._item("x" * 400, "y" * 400)] * 80)
        self.assertEqual(e["calls"], 2)
        acc, per = classify.agreement(["complaint", "accepts"], ["complaint", "other"])
        self.assertEqual(acc, 0.5)
        self.assertEqual(per["complaint"]["precision"], 1.0)


if __name__ == "__main__":
    unittest.main()
