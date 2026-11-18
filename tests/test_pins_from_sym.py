import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import phase3b_pdf as fx  # noqa: E402
import pins_from_sym as P  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "pins_from_sym"


def cli(*args):
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "pins_from_sym.py"), *map(str, args)],
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def by_number(pins):
    return {p["number"]: p for p in pins}


class TestPinsFromSym(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        pdf = cls.tmp / "ds.pdf"
        pdf.write_bytes(fx.build_pdf(fx.datasheet_pages()))
        subprocess.run([sys.executable, str(ROOT / "tools" / "ds_index.py"), str(pdf), "--out", str(cls.tmp / "idx"),
                        "--no-crops"], capture_output=True)
        cls.index = cls.tmp / "idx" / "index.json"

    @classmethod
    def tearDownClass(cls):
        __import__("shutil").rmtree(cls.tmp, ignore_errors=True)

    def test_good_with_datasheet_all_ok_and_toml_form(self):
        rc, out = cli(FIX / "good.kicad_sym", "--datasheet-index", self.index)
        self.assertEqual(rc, 0)
        self.assertIn('[[pin]]\nnumber   = "1"\nname     = "OUT"\ntype     = "output"\n', out)
        self.assertIn("# summary: pins=3 OK=3 UNSURE=0 FAIL=0", out)
        self.assertIn("`function` and `cite` are NOT generated", out)
        self.assertNotIn("\nfunction", out)
        self.assertNotIn("\ncite", out)

    def test_without_datasheet_no_pin_is_ok(self):
        rc, out = cli(FIX / "good.kicad_sym")
        self.assertEqual(rc, 0)
        self.assertIn("OK=0 UNSURE=3", out)

    def test_wrong_name_vs_datasheet_is_unsure(self):
        pins, head, fatal = P.run(str(FIX / "good.kicad_sym"), str(self.index))
        self.assertTrue(all(p["status"] == "OK" for p in pins))
        f = self.tmp / "renamed.kicad_sym"
        f.write_text((FIX / "good.kicad_sym").read_text().replace('"VCC"', '"VDD"'))
        pins, head, fatal = P.run(str(f), str(self.index))
        self.assertEqual(by_number(pins)["2"]["status"], "UNSURE")
        self.assertEqual(by_number(pins)["1"]["status"], "OK")

    def test_wrong_pin_count_extra_pin_is_unsure(self):
        txt = (FIX / "good.kicad_sym").read_text().replace(
            "    )\n  )\n)\n", '      (pin input line (at 0 -7.62 0) (length 7.62)\n        (name "EXTRA" (effects))\n'
            '        (number "4" (effects))\n      )\n    )\n  )\n)\n')
        f = self.tmp / "four.kicad_sym"
        f.write_text(txt)
        pins, head, fatal = P.run(str(f), str(self.index))
        self.assertEqual(len(pins), 4)
        self.assertEqual(by_number(pins)["4"]["status"], "UNSURE")

    def test_pin_diagram_label_does_not_confirm_a_name(self):
        # the fixture's pin DIAGRAM (above the Pin Functions title) prints "7 Vs"; the table has no pin 7
        txt = (FIX / "good.kicad_sym").read_text().replace('(name "GND"', '(name "Vs"').replace('(number "3"', '(number "7"')
        f = self.tmp / "diagram.kicad_sym"
        f.write_text(txt)
        st = by_number(P.run(str(f), str(self.index))[0])
        self.assertEqual(st["7"]["status"], "UNSURE")

    def test_duplicate_numbers_fail(self):
        rc, out = cli(FIX / "dup_numbers.kicad_sym", "--datasheet-index", self.index)
        self.assertEqual(rc, 1)
        self.assertIn("FAIL=2", out)

    def test_duplicate_names_unsure(self):
        pins, _, fatal = P.run(str(FIX / "dup_names.kicad_sym"), str(self.index))
        st = by_number(pins)
        self.assertEqual((st["2"]["status"], st["3"]["status"], st["1"]["status"]), ("UNSURE", "UNSURE", "OK"))

    def test_odd_names_unsure(self):
        pins, _, fatal = P.run(str(FIX / "odd_names.kicad_sym"), str(self.index))
        self.assertEqual({p["status"] for p in pins}, {"UNSURE"})
        reasons = " ".join(p["reason"] for p in pins)
        self.assertIn("overbar", reasons)
        self.assertIn("alternate", reasons)

    def test_hidden_and_stacked_unsure(self):
        pins, _, fatal = P.run(str(FIX / "hidden_stacked.kicad_sym"), str(self.index))
        st = by_number(pins)
        self.assertEqual(st["2"]["status"], "UNSURE")
        self.assertIn("hidden", st["2"]["reason"])
        self.assertIn("stacked", st["3"]["reason"])

    def test_pin_name_equal_to_number_and_nc_unsure(self):
        f = self.tmp / "nc.kicad_sym"
        f.write_text((FIX / "good.kicad_sym").read_text().replace('(name "OUT"', '(name "1"').replace('(name "GND"', '(name "NC"'))
        st = by_number(P.run(str(f), str(self.index))[0])
        self.assertEqual((st["1"]["status"], st["3"]["status"]), ("UNSURE", "UNSURE"))

    def test_fail_closed_inputs(self):
        for name in ("zero_pins", "truncated", "empty"):
            rc, out = cli(FIX / (name + ".kicad_sym"))
            self.assertEqual(rc, 1, name)
            self.assertIn("FAIL=1", out, name)
        rc, out = cli(FIX / "does_not_exist.kicad_sym")
        self.assertEqual(rc, 1)
        rc, out = cli(FIX / "two_symbols.kicad_sym")
        self.assertEqual(rc, 1)
        self.assertIn("exactly one symbol", out)

    def test_missing_index_pins_unsure_not_ok(self):
        rc, out = cli(FIX / "good.kicad_sym", "--datasheet-index", self.tmp / "nope.json")
        self.assertEqual(rc, 0)
        self.assertIn("OK=0", out)

    def test_deterministic(self):
        a = cli(FIX / "good.kicad_sym", "--datasheet-index", self.index)
        b = cli(FIX / "good.kicad_sym", "--datasheet-index", self.index)
        self.assertEqual(a, b)

    def test_natural_pin_order(self):
        self.assertEqual(sorted(["10", "2", "1", "A1", "B2"], key=P.natural), ["1", "2", "10", "A1", "B2"])


if __name__ == "__main__":
    unittest.main()
