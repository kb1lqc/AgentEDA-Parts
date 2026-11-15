"""Series tolerance options: decade value set, (value, tolerance code) pairs, per-value TCR rows, the 4-terminal
wrapper, and the Vishay WSK2512 series directories (docs/SPEC.md, "Series components")."""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from shutil import copytree

from lib import load
from lib.check import check_component
from lib.series import DECADE, E_SERIES, allowed_values, rated_voltage
from lib.zen import generate

ROOT = Path(__file__).parent.parent
FIX = Path(__file__).parent / "fixtures" / "Acme" / "RSER2"
KICAD = Path(__file__).parent / "fixtures" / "Acme" / "RSER1"  # borrowed symbol/footprint (2 passive pins)
VISHAY = ROOT / "components" / "Vishay"
HARNESS = Path(__file__).parent / "zen"


def fixture(tmp, toml=(), calc=()):
    """Copy RSER2 into tmp with RSER1's KiCad files, applying (old, new) replacements to component.toml and calc.py."""
    copy = Path(tmp) / "RSER2"
    copytree(FIX, copy)
    for ext in ("kicad_sym", "kicad_mod"):
        shutil.copy(KICAD / f"RSER1.{ext}", copy / f"RSER2.{ext}")
    for name, pairs in (("component.toml", toml), ("calc.py", calc)):
        text = (copy / name).read_text()
        for old, new in pairs:
            assert old in text, old
            text = text.replace(old, new)
        (copy / name).write_text(text)
    return copy


def messages(folder):
    return [f"{lvl}: {msg}" for lvl, msg in check_component(folder)]


def not_kicad(folder):
    """Check messages other than the missing KiCad/STEP files (the series directories get those later)."""
    return [m for m in messages(folder) if "file not found" not in m]


class TestDecade(unittest.TestCase):
    def test_table(self):
        self.assertEqual(len(DECADE), 90)  # 10..99, two significant digits
        self.assertEqual([DECADE[0], DECADE[1], DECADE[-1]], [1.0, 1.1, 9.9])
        self.assertEqual(DECADE, sorted(set(DECADE)))
        self.assertIs(E_SERIES["VISHAY-DECADE"], DECADE)
        self.assertEqual(len([m for m in DECADE if m == 5.0]), 1)

    def test_allowed_values(self):
        values = allowed_values(["VISHAY-DECADE"], 0.001, 0.0099)
        self.assertEqual((len(values), values[0], values[-1]), (90, 0.001, 0.0099))
        self.assertIn(0.0011, values)  # the float 1.1e-3 gives
        self.assertNotIn(0.00105, values)  # three significant digits
        self.assertEqual(len(allowed_values(["VISHAY-DECADE"], 0.01, 0.2)), 101)  # 0.01 ... 0.19 and 0.2

    def test_rated_voltage_without_limit(self):
        self.assertAlmostEqual(rated_voltage(0.025, 1.0), 0.158113883, places=8)
        self.assertEqual(rated_voltage(0.025, 1.0, 0.1), 0.1)


class TestToleranceFixture(unittest.TestCase):
    """RSER2: decade values 1..100 ohm; B 10-100, D 2-50, F 1-20 ohm; TCR rows 1-9.9 and 10-100 ohm."""

    def setUp(self):
        self.part = load(str(FIX))

    def test_options_and_counts(self):
        p = self.part
        self.assertEqual(p.tolerances(), ["B", "D", "F"])
        self.assertEqual({c: len(p.values(c)) for c in "BDF"}, {"B": 91, "D": 121, "F": 101})
        self.assertEqual(len(p.values()), 181)  # union: 1.0 ... 9.9, 10 ... 99, 100
        self.assertEqual(len(p.pairs()), 91 + 121 + 101)
        self.assertEqual(p.pairs()[:2], [(1.0, "F"), (1.1, "F")])

    def test_range_edge_per_tolerance(self):
        p = self.part
        for code, inside, outside in (("B", (10.0, 100.0), (9.9, 101.0)), ("D", (2.0, 50.0), (1.9, 51.0)),
                                      ("F", (1.0, 20.0), (0.99, 21.0))):
            for v in inside:
                self.assertTrue(p.mpn(v, code), (code, v))
            for v in outside:
                with self.assertRaises(ValueError) as cm:
                    p.mpn(v, code)
                self.assertIn("not an allowed value", str(cm.exception))

    def test_range_is_clipped_to_the_directory(self):
        row = 'min = 1\nmax = 100\nunit = "ohm"\nconditions = ""\ncite = "DS p.1, Ratings, Resistance range"'
        with tempfile.TemporaryDirectory() as d:
            clipped = load(str(fixture(d, [(row, row.replace("max = 100", "max = 60"))])))
        self.assertEqual(clipped.values("B")[-1], 60.0)  # B is 10-100 ohm in its own row
        self.assertEqual(clipped.values("D")[-1], 50.0)  # D is 2-50: unchanged
        self.assertEqual(clipped.values("F")[-1], 20.0)

    def test_mpn_needs_the_code_when_ambiguous(self):
        p = self.part
        self.assertEqual(p.mpn(4.7, "D"), "RSER2-4.7D")
        self.assertEqual(p.mpn(1.5), "RSER2-1.5F")  # only F allows 1.5 ohm: no code needed
        self.assertEqual(p.mpn(100.0, "B"), "RSER2-100B")
        with self.assertRaises(ValueError) as cm:
            p.mpn(4.7)
        self.assertIn("ambiguous", str(cm.exception))
        self.assertIn("D, F", str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            p.mpn(4.7, "Z")
        self.assertIn("not an option", str(cm.exception))
        with self.assertRaises(ValueError):
            p.mpn(4.75, "D")  # not a decade value

    def test_series_value_uses_the_code_tolerance(self):
        p = self.part.series_value(4.7, "D")
        self.assertAlmostEqual(p.min, 4.7 * 0.995)
        self.assertAlmostEqual(p.max, 4.7 * 1.005)
        self.assertEqual(p.typ, 4.7)
        self.assertAlmostEqual(self.part.series_value(4.7, "F").max, 4.7 * 1.01)
        self.assertAlmostEqual(self.part.series_value(1.5).max, 1.5 * 1.01)  # F only
        with self.assertRaises(ValueError):
            self.part.series_value(4.7)
        self.assertAlmostEqual(self.part.tolerance("B").max, 0.001)

    def test_tcr_by_value(self):
        self.assertAlmostEqual(self.part.tcr(1.0).max, 100e-6)
        self.assertAlmostEqual(self.part.tcr(9.9).max, 100e-6)
        self.assertAlmostEqual(self.part.tcr(10.0).max, 50e-6)
        self.assertAlmostEqual(self.part.tcr(100.0).max, 50e-6)
        with self.assertRaises(ValueError):
            self.part.tcr(0.5)

    def test_plain_series_rejects_a_code(self):
        plain = load(str(ROOT / "tests" / "fixtures" / "Acme" / "RSER1"))
        with self.assertRaises(ValueError):
            plain.values("F")
        self.assertEqual(plain.pairs()[0], (10.0, None))
        self.assertEqual(plain.tolerances(), [])


class TestToleranceCheck(unittest.TestCase):
    def run_edit(self, toml=(), calc=()):
        with tempfile.TemporaryDirectory() as d:
            return "\n".join(messages(fixture(d, toml, calc)))

    def test_fixture_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(messages(fixture(d)), [])

    def test_exclusive_with_series_tol(self):
        self.assertIn("series_tol and series_tolerances are exclusive", self.run_edit(
            [('series_power = "p70"\n', 'series_power = "p70"\nseries_tol = "tol_b"\n')]))

    def test_missing_row(self):
        self.assertIn("'nope' is not a param key", self.run_edit([('tol = "tol_d"', 'tol = "nope"')]))

    def test_option_outside_the_directory_range(self):
        # B is 10-100 ohm; a directory range 1-5 ohm leaves it with no value.
        row = 'min = 1\nmax = 100\nunit = "ohm"\nconditions = ""\ncite = "DS p.1, Ratings, Resistance range"'
        text = self.run_edit([(row, row.replace("max = 100", "max = 5"))])
        self.assertIn("series_tolerances.B: its range 'r_range_b' has no value inside the series range", text)

    def test_tcr_gap_and_overlap(self):
        gap = self.run_edit([('name = "TCR low range"\nkind = "electrical"\nscope = "na"\nmin = 1\nmax = 9.9',
                              'name = "TCR low range"\nkind = "electrical"\nscope = "na"\nmin = 1\nmax = 5')])
        self.assertIn("series_tcr: 0 TCR rows cover 5.1 ohm", gap)
        overlap = self.run_edit([('name = "TCR low range"\nkind = "electrical"\nscope = "na"\nmin = 1\nmax = 9.9',
                                  'name = "TCR low range"\nkind = "electrical"\nscope = "na"\nmin = 1\nmax = 12')])
        self.assertIn("series_tcr: 2 TCR rows cover 10 ohm", overlap)

    def test_mpn_without_the_code_argument(self):
        text = self.run_edit(calc=[("def mpn(r_ohm, tol_code):", "def mpn(r_ohm):")])
        self.assertIn("calc.mpn(1, 'F') raised TypeError", text)

    def test_duplicate_mpn_over_codes(self):
        text = self.run_edit(calc=[('return "RSER2-" + format(r_ohm, "g") + tol_code', 'return "RSER2-" + format(r_ohm, "g")')])
        self.assertIn("calc.mpn gives 'RSER2-10' for both 10, 'B' and 10, 'D' ohm", text)

    def test_bad_table_shapes(self):
        self.assertIn("series_tolerances must map a code", self.run_edit(
            [('B = { tol = "tol_b", range = "r_range_b" }', 'B = { tol = "tol_b" }')]))
        self.assertIn("series_tcr must be a list", self.run_edit(
            [('series_tcr = [{ tcr = "tcr_lo", range = "tcr_lo_range" }, { tcr = "tcr_hi", range = "tcr_hi_range" }]',
              'series_tcr = []')]))
        self.assertIn("series_pins must list two different", self.run_edit(
            [('series_power = "p70"\n', 'series_power = "p70"\nseries_pins = ["1", "9"]\n')]))


class TestToleranceZen(unittest.TestCase):
    def test_fixture_wrapper_text(self):
        with tempfile.TemporaryDirectory() as d:
            text, problems = generate(fixture(d))
        self.assertEqual(problems, [])
        self.assertIn('tolerance = config(str, default="", help="Tolerance code, one of B, D, F;', text)
        self.assertIn('(4700000, "D"): "RSER2-4.7D",  # 4.7 ohm, tolerance D', text)
        self.assertIn('4700000: ["D", "F"],', text)  # the codes that allow 4.7 ohm
        self.assertIn('_MPN_STR = _MPN.get((_KEY, _CODE), "UNORDERABLE")', text)
        self.assertIn("def _rated_voltage(_m, v1, v2, what, r, p, derate):", text)  # no Vlimit
        self.assertNotIn("vlim", text)
        self.assertIn("limit2 = p * r * derate * derate", text)
        self.assertIn('{"v1": P1.voltage, "v2": P2.voltage, "what": "rated_voltage", "r": value.value, "p": 0.1, "derate": derate}', text)
        self.assertEqual(len(re.findall(r'(?m)^    \(\d+, "[BDF]"\): "RSER2-', text)), 91 + 121 + 101)

    def test_series_wrapper_unchanged_without_options(self):
        text, problems = generate(ROOT / "tests" / "fixtures" / "Acme" / "RSER1")
        self.assertEqual(problems, [])
        self.assertNotIn("tolerance", text)
        self.assertIn("vlim", text)


class TestWskSeries(unittest.TestCase):
    """components/Vishay/WSK2512 (0.005-0.2 ohm) and WSK2512-LOW (0.0005-0.0049 ohm), data only."""

    @classmethod
    def setUpClass(cls):
        cls.main, cls.low = load(str(VISHAY / "WSK2512")), load(str(VISHAY / "WSK2512-LOW"))

    def test_counts(self):
        self.assertEqual({c: len(self.main.values(c)) for c in "BDF"}, {"B": 101, "D": 151, "F": 151})
        self.assertEqual(len(self.main.pairs()), 403)
        self.assertEqual(self.low.tolerances(), ["D", "F"])  # B starts at 0.01 ohm: no value here
        self.assertEqual({c: len(self.low.values(c)) for c in "DF"}, {"D": 40, "F": 40})  # sub-1 mohm excluded (no printed value code)
        self.assertEqual(len(self.low.pairs()), 80)
        self.assertEqual((self.main.values()[0], self.main.values()[-1]), (0.005, 0.2))
        self.assertEqual((self.low.values()[0], self.low.values()[-1]), (0.001, 0.0049))

    def test_range_edges_per_tolerance(self):
        m, lo = self.main, self.low
        self.assertEqual((m.values("B")[0], m.values("B")[-1]), (0.01, 0.2))  # B 0.01-0.2, clipped at 0.005 below: none
        self.assertEqual((m.values("D")[0], m.values("F")[0]), (0.005, 0.005))  # D 0.001, F 0.0005 clipped to 0.005
        self.assertEqual((lo.values("D")[0], lo.values("D")[-1]), (0.001, 0.0049))
        self.assertEqual((lo.values("F")[0], lo.values("F")[-1]), (0.001, 0.0049))  # F prints 0.0005, excluded below 1 mohm
        for call in (lambda: m.mpn(0.0099, "B"), lambda: m.mpn(0.0049, "F"), lambda: lo.mpn(0.0005, "D"), lambda: lo.mpn(0.0005, "F"),
                     lambda: lo.mpn(0.005, "F"), lambda: lo.mpn(0.0049, "B")):
            with self.assertRaises(ValueError):
                call()

    def test_mpn_codes(self):
        m, lo = self.main, self.low
        self.assertEqual(m.mpn(0.025, "D"), "WSK2512R0250DEA")  # same part as components/Vishay/WSK2512R0250D
        self.assertEqual(m.mpn(0.01, "B"), "WSK2512R0100BEA")  # DS example R0100 = 0.01 ohm
        self.assertEqual(m.mpn(0.005, "F"), "WSK25125L000FEA")  # DS example 5L000 = 0.005 ohm
        self.assertEqual(m.mpn(0.2, "B"), "WSK2512R2000BEA")
        self.assertEqual(m.mpn(0.0099, "F"), "WSK25129L900FEA")
        self.assertEqual(m.mpn(0.011, "F"), "WSK2512R0110FEA")
        self.assertEqual(lo.mpn(0.001, "D"), "WSK25121L000DEA")
        self.assertEqual(lo.mpn(0.0049, "D"), "WSK25124L900DEA")
        with self.assertRaises(ValueError):
            m.mpn(0.025)  # B, D, F all allow it
        for part in (m, lo):
            mpns = [part.mpn(v, c) for v, c in part.pairs()]
            self.assertEqual(len(set(mpns)), len(mpns))

    def test_same_part_as_the_single_directory(self):
        single = load(str(VISHAY / "WSK2512R0250D"))
        self.assertEqual(single.info["mpn"], self.main.mpn(0.025, "D"))
        self.assertEqual(single.param("tol").max, self.main.tolerance("D").max)  # both a fraction (0.005)

    def test_tcr_per_range(self):
        m, lo = self.main, self.low
        self.assertAlmostEqual(m.tcr(0.005).max, 35e-6)
        self.assertAlmostEqual(m.tcr(0.2).max, 35e-6)
        self.assertAlmostEqual(lo.tcr(0.001).max, 250e-6)
        self.assertAlmostEqual(lo.tcr(0.0029).max, 250e-6)
        self.assertAlmostEqual(lo.tcr(0.003).max, 75e-6)
        self.assertAlmostEqual(lo.tcr(0.0049).max, 75e-6)
        for v in lo.values():
            lo.tcr(v)  # every allowed value has exactly one row

    def test_series_value_and_worst_case(self):
        p = self.main.series_value(0.025, "D")
        self.assertAlmostEqual(p.min, 0.025 * 0.995)
        self.assertAlmostEqual(p.max, 0.025 * 1.005)
        from lib.wca import wca
        r = wca(self.main.calc.resistance_worst, r0=0.025, tol=self.main.tolerance("D"), tcr=self.main.tcr(0.025),
                t_c=__import__("lib").Param(min=-40, max=85), t_ref_c=25.0)
        self.assertAlmostEqual(r.max, 0.025 * 1.005 * (1 + 35e-6 * 65))

    def test_no_voltage_limit_and_pins(self):
        for part in (self.main, self.low):
            self.assertNotIn("series_vlimit", part.info)
            self.assertEqual(part.info["series_pins"], ["I1", "I2"])
            self.assertEqual(len(part.pins), 4)

    def test_check_has_only_missing_kicad_files(self):
        for name in ("WSK2512", "WSK2512-LOW"):
            self.assertEqual(not_kicad(VISHAY / name), [], name)

    def test_wrapper_text(self):
        text, problems = generate(VISHAY / "WSK2512")
        self.assertEqual(problems, [])
        self.assertIn('{"v1": I1.voltage, "v2": I2.voltage, "what": "rated_voltage"', text)
        self.assertIn('(25000, "D"): "WSK2512R0250DEA",  # 0.025 ohm, tolerance D', text)
        self.assertIn("B 0.01 to 0.2 ohm, D 0.005 to 0.2 ohm, F 0.005 to 0.2 ohm", text)
        self.assertEqual(len(re.findall(r'(?m)^    \(\d+, "[BDF]"\): "WSK2512', text)), 403)


# (case name, config overrides, expected: "pass" | "error" | "warning", text that must appear)
FIXTURE_CASES = [
    ("nominal", [], "pass", ""),
    ("tolerance_f", ["tolerance=F"], "pass", ""),
    ("ambiguous_tolerance", ["tolerance="], "error", 'the tolerance codes that allow this value: ["D", "F"] (set tolerance)'),
    ("single_option_needs_no_code", ["value=1.5ohm", "tolerance=", "va=0.3V 1%"], "pass", ""),  # only F allows 1.5 ohm
    ("tolerance_outside_range", ["value=1.5ohm", "tolerance=D"], "error", "value_allowed: 1.5 ohm with tolerance code D is not orderable"),
    ("unknown_code", ["tolerance=Z"], "error", "value_allowed"),
    ("not_decade", ["value=4.75ohm"], "error", "value_allowed"),
    ("power_limited", ["va=0.7V 1%"], "error", "rated_voltage: up to 0.707 V"),  # > sqrt(0.1 x 4.7) = 0.686 V
    ("v_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("ambient_out", ["ta=-60°C to 85°C"], "error", "t_oper_ambient"),
]
WSK_CASES = [
    ("nominal", [], "pass", ""),
    ("ambiguous_tolerance", ["tolerance="], "error", "(set tolerance)"),
    ("b_below_its_range", ["value=0.005ohm", "tolerance=B", "va=0.1V"], "error", "value_allowed"),  # B starts at 0.01 ohm
    ("f_at_the_low_edge", ["value=0.005ohm", "tolerance=F", "va=0.07V"], "pass", ""),  # rated sqrt(0.005) = 0.0707 V
    ("below_the_directory_range", ["value=0.0049ohm", "tolerance=F", "va=0.07V"], "error", "value_allowed"),  # WSK2512-LOW
    ("not_decade", ["value=0.0275ohm", "tolerance=D"], "error", "value_allowed"),
    ("across_current_terminals", ["va=0.17V 1%"], "error", "rated_voltage: up to 0.1717 V"),  # > sqrt(0.025) = 0.158 V
    ("derated", ["derate=0.9"], "error", "rated_voltage"),  # 0.1515 V > 0.9 x 0.158 V
    ("v_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("ambient_out", ["ta=-70°C to 85°C"], "error", "t_oper_ambient"),
]


@unittest.skipUnless(shutil.which("pcb"), "pcb not installed")
class TestBuild(unittest.TestCase):
    """Build tolerance-series wrappers in their own workspace: the RSER2 fixture, and a scratch copy of WSK2512 that
    borrows the symbol and footprint of components/Vishay/WSK2512R0250D until the series has its own."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "pcb.toml").write_text('[workspace]\npcb-version = "0.4"\n')
        cls.fix = fixture(root)
        shutil.copy(KICAD / "RSER1.kicad_mod", cls.fix)  # the symbol's Footprint property names this file
        cls.wsk = root / "WSK2512"
        copytree(VISHAY / "WSK2512", cls.wsk)
        single = VISHAY / "WSK2512R0250D"
        for ext in ("kicad_sym", "kicad_mod"):
            shutil.copy(single / f"WSK2512R0250D.{ext}", cls.wsk / f"WSK2512.{ext}")
        shutil.copy(single / "WSK2512R0250D.kicad_mod", cls.wsk)  # the symbol's Footprint property names this file
        for folder, name, harness in ((cls.fix, "RSER2", "Series2"), (cls.wsk, "WSK2512", "WskSeries")):
            text, problems = generate(folder)
            assert not problems, problems
            (folder / f"{name}.zen").write_text(text)
            (folder / "pcb.toml").write_text("")
            subprocess.run(["pcb", "fmt", str(folder)], check=True, capture_output=True)
            shutil.copy(HARNESS / f"{harness}_harness.zen", folder / "_harness.zen")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, *args):
        r = subprocess.run(["pcb", "build", "-Wstyle", "-Dwarnings", *args], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_wrappers_build_standalone(self):
        for folder, name in ((self.fix, "RSER2"), (self.wsk, "WSK2512")):
            rc, out = self.build(str(folder / f"{name}.zen"))
            self.assertEqual(rc, 0, out)

    def run_cases(self, folder, cases):
        from tests.test_zen import outcome
        for name, overrides, expect, text in cases:
            rc, out = self.build(str(folder / "_harness.zen"), *[f"--config={c}" for c in overrides])
            with self.subTest(case=name):
                self.assertEqual(outcome(rc, out), expect, out)
                self.assertIn(text, out)

    def test_fixture_harness_cases(self):
        self.run_cases(self.fix, FIXTURE_CASES)

    def test_wsk_harness_cases(self):
        self.run_cases(self.wsk, WSK_CASES)


if __name__ == "__main__":
    unittest.main()
