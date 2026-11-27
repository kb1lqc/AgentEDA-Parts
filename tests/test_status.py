import json
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from tools import status

ROOT = Path(__file__).resolve().parent.parent


def run(*args):
    out = StringIO()
    with redirect_stdout(out):
        code = status.main(list(args))
    return code, out.getvalue()


class Status(unittest.TestCase):
    def pick(self, released):
        for s in json.loads(run("--all", "--json")[1]):
            if s["released"] == released and (released or s["needs_check"]):
                return s["value"]
        self.skipTest("no such part in the library")

    def test_released_part_exits_0(self):
        v = self.pick(True)
        code, out = run(v)
        self.assertEqual(code, 0)
        self.assertIn(f"{v}: RELEASED", out)

    def test_unreleased_part_names_rows_and_exits_1(self):
        v = self.pick(False)
        code, out = run(v)
        self.assertEqual(code, 1)
        self.assertIn("NOT RELEASED", out)
        self.assertIn("needs a check:", out)
        self.assertIn(f"python3 tools/review.py {v}", out)

    def test_json_fields(self):
        v = self.pick(False)
        s = json.loads(run(v, "--json")[1])[0]
        self.assertEqual(s["value"], v)
        self.assertEqual(sorted(s), ["checked", "derived", "dir", "matters", "needs_check", "not_covered", "released",
                                     "rows", "value"])

    def test_unknown_part_exits_2(self):
        self.assertEqual(run("NoSuchPart")[0], 2)

    def test_all_lists_every_part(self):
        code, out = run("--all", "--json")
        self.assertEqual(len(json.loads(out)), len(list(ROOT.glob("components/*/*/component.toml"))))


if __name__ == "__main__":
    unittest.main()
