"""Tests for tools/risk_rank.py on a fixture repo (components, a blocks dir with analysis.py, examples)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "risk_rank.py"
sys.path.insert(0, str(TOOL.parent))
import risk_rank as rr  # noqa: E402

TOML = '''[part]
value = "X"

[[pin]]
number = "2"
name = "B"

[[pin]]
number = "1"
name = "A"

[param.land_pad_w]
kind = "mechanical"

[param.vos_25c]
kind = "electrical"

[param.vin_abs]
kind = "abs_max"
check_pins = ["A"]

[param.ta_abs]
kind = "abs_max"
check_ambient = true

[param.gain_err_25c]
kind = "electrical"

[param.noise_typ]
kind = "electrical"

[param.unused_row]
kind = "electrical"
'''
CALC = 'INPUTS = {"gain_actual": {"gain_err": "gain_err_25c.typ"}, "other_fn": {"x": "noise_typ"}}\n'


def write(p, text=""):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class TestRiskRank(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.root, self.blocks = t / "zl", t / "cb"
        write(self.root / "components/A/X/component.toml", TOML)
        write(self.root / "components/A/X/calc.py", CALC)
        write(self.blocks / "blocks/B/analysis.py", 'x = part.param("vos_25c")\ny = part.inputs("gain_actual")\n')
        write(self.root / "examples/e.py", 'z = ("unrelated_key")\n')

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        res, problems = rr.rank_all(self.root, self.blocks)
        self.assertEqual(problems, [])
        return {r["key"]: r for r in res["components"][0]["rows"]}

    def test_ranks(self):
        r = self.rows()
        self.assertEqual({k: v["rank"] for k, v in r.items()},
                         {"pin:1": 0, "pin:2": 0, "land_pad_w": 0, "vos_25c": 1, "vin_abs": 1, "ta_abs": 1,
                          "gain_err_25c": 1, "noise_typ": 2, "unused_row": 2})

    def test_reasons(self):
        r = self.rows()
        self.assertEqual(r["vos_25c"]["reasons"], ["analysis-or-example"])
        self.assertEqual(r["gain_err_25c"]["reasons"], ["inputs-of-used-function"])
        self.assertEqual(r["vin_abs"]["reasons"], ["zener-check"])
        self.assertEqual(r["land_pad_w"]["reasons"], ["mechanical"])

    def test_unused_function_inputs_do_not_count(self):
        self.assertEqual(self.rows()["noise_typ"]["rank"], 2)

    def test_sorted_by_rank_then_key(self):
        res, _ = rr.rank_all(self.root, self.blocks)
        keys = [(r["rank"], r["key"]) for r in res["components"][0]["rows"]]
        self.assertEqual(keys, sorted(keys))

    def test_example_literal_marks_row_used(self):
        write(self.root / "examples/e.py", 'z = ("unused_row")\n')
        self.assertEqual(self.rows()["unused_row"]["rank"], 1)

    def test_missing_blocks_dir_fails(self):
        res, problems = rr.rank_all(self.root, self.blocks / "nope")
        self.assertIsNone(res)
        self.assertIn("blocks dir not found", problems[0])

    def test_no_analysis_fails(self):
        (self.blocks / "blocks/B/analysis.py").unlink()
        res, problems = rr.rank_all(self.root, self.blocks)
        self.assertIsNone(res)
        self.assertIn("no blocks/*/analysis.py", problems[0])

    def test_zero_components_fails(self):
        (self.root / "components/A/X/component.toml").unlink()
        res, problems = rr.rank_all(self.root, self.blocks)
        self.assertIsNone(res)

    def test_non_literal_inputs_is_unsure_not_silent(self):
        write(self.root / "components/A/X/calc.py", "INPUTS = dict(a=1)\n")
        res, _ = rr.rank_all(self.root, self.blocks)
        self.assertEqual(res["components"][0]["status"], "UNSURE")
        self.assertEqual(res["components"][0]["reason"], "INPUTS is not a literal")

    def test_bad_toml_is_fail_and_exit_1(self):
        write(self.root / "components/A/X/component.toml", "[part\n")
        res, problems = rr.rank_all(self.root, self.blocks)
        self.assertEqual(res["components"][0]["status"], "FAIL")
        self.assertTrue(problems)

    def test_cli_deterministic_and_exit_codes(self):
        cmd = [sys.executable, "-B", str(TOOL), "--root", str(self.root), "--blocks", str(self.blocks)]
        a = subprocess.run(cmd, capture_output=True, text=True)
        b = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(a.returncode, 0)
        self.assertEqual((a.stdout, a.stderr), (b.stdout, b.stderr))
        data = json.loads(a.stdout)
        self.assertEqual(data["blocks_dir"], str(self.blocks.resolve()))
        self.assertIn("1 OK, 0 UNSURE, 0 FAIL", a.stderr)
        bad = subprocess.run(cmd[:-1] + [str(self.blocks / "x")], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()
