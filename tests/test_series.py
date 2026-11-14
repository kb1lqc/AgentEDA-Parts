"""Series components: E-series tables, Part.values/mpn/series_value, lib.check, Zener wrapper, README."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from shutil import copytree

from lib import load, readme
from lib.check import check_component
from lib.series import E24, E96, allowed_values, rated_voltage
from lib.zen import generate, io_name

FIX = Path(__file__).parent / "fixtures" / "Acme" / "RSER1"
HARNESS = Path(__file__).parent / "zen" / "Series_harness.zen"


def edited(tmp, toml=(), calc=()):
    """Copy RSER1 into tmp, applying (old, new) replacements to component.toml and calc.py."""
    copy = Path(tmp) / "RSER1"
    copytree(FIX, copy)
    for name, pairs in (("component.toml", toml), ("calc.py", calc)):
        text = (copy / name).read_text()
        for old, new in pairs:
            assert old in text, old
            text = text.replace(old, new)
        (copy / name).write_text(text)
    return copy


def messages(folder):
    return [f"{lvl}: {msg}" for lvl, msg in check_component(folder)]


class TestTables(unittest.TestCase):
    def test_counts_and_known_values(self):
        self.assertEqual((len(E24), len(E96)), (24, 96))
        for table in (E24, E96):
            self.assertEqual(table, sorted(set(table)))
        self.assertIn(4.7, E24)
        self.assertIn(9.1, E24)
        self.assertEqual([E96[0], E96[40], E96[-1]], [1.00, 2.61, 9.76])  # 2.61 is the 41st E96 value
        self.assertEqual(E96[24], 1.78)

    def test_allowed_values(self):
        self.assertEqual(len(allowed_values(["E24"], 10, 91)), 24)  # one decade, end values included
        self.assertEqual(len(allowed_values(["E96"], 1e3, 9.76e3)), 96)
        values = allowed_values(["E24", "E96"], 100, 1e3)
        self.assertEqual(values, sorted(set(values)))
        self.assertIn(2610.0, allowed_values(["E96"], 10, 1e6))  # the float 2.61e3 gives
        self.assertIn(2700.0, allowed_values(["E24", "E96"], 10, 1e6))  # E24 value that E96 lacks (2.74)

    def test_rated_voltage(self):
        self.assertAlmostEqual(rated_voltage(1e3, 0.1, 50), 10.0)
        self.assertEqual(rated_voltage(1e6, 0.1, 50), 50)  # voltage limit wins


class TestPart(unittest.TestCase):
    def setUp(self):
        self.part = load(str(FIX))

    def test_values_and_mpn(self):
        values = self.part.values()
        self.assertEqual((len(values), values[0], values[-1]), (49, 10.0, 1000.0))  # E24, 10 ohm to 1 kohm
        self.assertEqual(self.part.mpn(240.0), "RSER1-240R")

    def test_values_one_decade(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, [("max = 1000\nunit", "max = 91\nunit")])
            self.assertEqual(len(load(str(copy)).values()), 24)

    def test_series_value(self):
        p = self.part.series_value(240.0)
        self.assertEqual(p.typ, 240.0)
        self.assertAlmostEqual(p.min, 240.0 * 0.99)
        self.assertAlmostEqual(p.max, 240.0 * 1.01)
        self.assertEqual(p.unit, "ohm")

    def test_not_allowed(self):
        for call in (self.part.series_value, self.part.mpn):
            with self.assertRaises(ValueError) as cm:
                call(237.0)
            self.assertIn("not an allowed value", str(cm.exception))

    def test_plain_part_has_no_values(self):
        with self.assertRaises(ValueError):
            load(str(FIX.parent / "LDO1")).values()


class TestCheck(unittest.TestCase):
    def test_fixture_passes(self):
        # p70 (rec_op) and v_max (abs_max) carry no check_pins/unchecked: the series reads them, so no warning.
        self.assertEqual(messages(FIX), [])

    def run_edit(self, toml=(), calc=()):
        with tempfile.TemporaryDirectory() as d:
            return "\n".join(messages(edited(d, toml, calc)))

    def test_missing_mpn_function(self):
        text = self.run_edit(calc=[("def mpn(", "def not_mpn(")])
        self.assertIn("ERROR: calc.py of a series must define mpn(value)", text)

    def test_duplicate_mpn(self):
        text = self.run_edit(calc=[('return "RSER1-" + format(r_ohm, "g") + "R"', 'return "RSER1"')])
        self.assertIn("ERROR: calc.mpn gives 'RSER1' for both 10 and 11 ohm", text)

    def test_mpn_raises(self):
        text = self.run_edit(calc=[('return "RSER1-"', 'raise ValueError("no such value")\n    return "RSER1-"')])
        self.assertIn("ERROR: calc.mpn(10) raised ValueError: no such value", text)

    def test_field_errors(self):
        self.assertIn("[part] series needs 'e_series'", self.run_edit([('e_series = ["E24"]\n', "")]))
        self.assertIn("e_series must list names from", self.run_edit([('["E24"]', '["E12"]')]))
        self.assertIn("series_tol = 'nope' is not a param key", self.run_edit([('series_tol = "tol"', 'series_tol = "nope"')]))
        self.assertIn("[part] mpn must be absent", self.run_edit([('series = "resistor"', 'series = "resistor"\nmpn = "X"')]))
        self.assertIn("only 'resistor' and 'capacitor' are supported", self.run_edit([('series = "resistor"', 'series = "cap"')]))


# RSER1 with E24 + E96 where E96 starts at 100 ohm (47.5 ohm is E96 only; 47 ohm is E24).
E96_MIN = [('e_series = ["E24"]', 'e_series = ["E24", "E96"]\nseries_eseries_min = { E96 = 100 }')]


class TestEseriesMin(unittest.TestCase):
    def test_allowed_values_function(self):
        values = allowed_values(["E24", "E96"], 10, 1e3, {"E96": 100})
        self.assertNotIn(47.5, values)  # E96 only, below the E96 minimum
        self.assertNotIn(97.6, values)  # just below 100
        self.assertIn(47.0, values)  # E24, stays allowed below the E96 minimum
        self.assertIn(100.0, values)  # the minimum itself
        self.assertIn(102.0, values)  # just above, E96
        self.assertIn(110.0, values)  # E24 and E96
        self.assertEqual(allowed_values(["E24", "E96"], 10, 1e3), allowed_values(["E24", "E96"], 10, 1e3, {}))
        self.assertIn(47.5, allowed_values(["E24", "E96"], 10, 1e3))

    def test_part_values_mpn_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, E96_MIN)
            self.assertEqual(messages(copy), [])
            part = load(str(copy))
            values = part.values()
            for ok in (47.0, 100.0, 102.0, 1000.0):
                self.assertIn(ok, values)
                self.assertTrue(part.mpn(ok))
            for bad in (47.5, 97.6):
                self.assertNotIn(bad, values)
                for call in (part.mpn, part.series_value):
                    with self.assertRaises(ValueError) as cm:
                        call(bad)
                    self.assertIn("not an allowed value", str(cm.exception))

    def test_check_rejects_bad_field(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, [('e_series = ["E24"]', 'e_series = ["E24"]\nseries_eseries_min = { E96 = 100 }')])
            self.assertIn("series_eseries_min must map names from e_series", "\n".join(messages(copy)))

    def test_wrapper_table_excludes_value(self):
        with tempfile.TemporaryDirectory() as d:
            text, problems = generate(edited(d, E96_MIN))
        self.assertEqual(problems, [])
        self.assertIn("47000000: ", text)  # 47 ohm (E24)
        self.assertNotIn("47500000: ", text)  # 47.5 ohm (E96 below minimum)
        self.assertIn("(E96 only from 100 ohm)", text)  # in the value_allowed message

    def test_new_panasonic_directories_have_an_mpn_for_every_value(self):
        root = Path(__file__).parent.parent / "components" / "Panasonic"
        for name in ("ERA-2AEB", "ERA-3AEB", "ERA-6AEB", "ERJ-6ENF", "ERJ-8ENF"):
            with self.subTest(part=name):
                part = load(str(root / name))
                values = part.values()
                self.assertTrue(values)
                mpns = [part.mpn(v) for v in values]  # raises ValueError for a value without a printed code
                self.assertEqual(len(set(mpns)), len(mpns))
                if name.startswith("ERA"):
                    self.assertNotIn(47.5, values)
                    self.assertIn(47.0, values)
                    self.assertIn(102.0, values)


class TestZen(unittest.TestCase):
    def test_io_names_numeric_pins(self):
        self.assertEqual([io_name("1"), io_name("2")], ["P1", "P2"])

    def test_wrapper_text(self):
        text, problems = generate(FIX)
        self.assertEqual(problems, [])
        self.assertIn("P1 = io(Net)", text)
        self.assertIn("P2 = io(Net)", text)
        self.assertIn('"1": P1,', text)
        self.assertIn("value = config(Resistance,", text)
        self.assertIn('240000000: "RSER1-240R",  # 240 ohm', text)  # MPN table, micro-ohm keys
        self.assertEqual(text.count('"RSER1-'), 49)
        self.assertIn("_MPN_STR = _MPN.get(_KEY,", text)
        self.assertIn('part=Part(mpn=_MPN_STR, manufacturer="Acme"', text)
        self.assertIn("value_allowed", text)
        self.assertIn('"r": value.value, "p": 0.1, "vlim": 50.0, "derate": derate}, "error")', text)  # derated rating
        self.assertIn("limit2 = min(p * r, vlim * vlim) * derate * derate", text)
        self.assertIn("# UNCHECKED: power derating above 70 degC", text)
        self.assertNotIn("# UNCHECKED: p70", text)  # read by the series check, not an unchecked rating
        self.assertIn('load("@stdlib/units.zen", "Resistance", "Temperature")', text)
        self.assertIn("t_oper_ambient", text)  # the normal ambient check

    def test_duplicate_mpn_is_a_problem(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, calc=[('return "RSER1-" + format(r_ohm, "g") + "R"', 'return "RSER1"')])
            self.assertTrue(any("gives 'RSER1' for both" in p for p in generate(copy)[1]))


class TestReadme(unittest.TestCase):
    def test_series_section(self):
        text = readme.build(FIX)
        self.assertIn("## Series", text)
        self.assertIn("- **Value range**: 10 ohm to 1 kohm (`res_range`)", text)
        self.assertIn("- **E-series**: E24 (49 values in range)", text)
        self.assertIn("examples: 10 ohm -> `RSER1-10R`, 100 ohm -> `RSER1-100R`, 1 kohm -> `RSER1-1000R`", text)
        self.assertIn("min(sqrt(P70 x R), Vlimit), P70 = 100 mW (`p70`), Vlimit = 50 V (`v_max`)", text)
        self.assertIn("| 100 ohm | 3.162 V |", text)
        self.assertIn("computed from `p70`, `v_max`", text)
        self.assertNotIn("**mpn**", text)


# (case name, config overrides, expected: "pass" | "error" | "warning", text that must appear)
CASES = [
    ("nominal", [], "pass", ""),
    ("not_e_series", ["value=237ohm"], "error", "value_allowed: 237.0 ohm is not an allowed value"),
    ("above_range", ["value=1.2kohm"], "error", "value_allowed"),
    ("power_limited", ["va=5V 5%"], "error", "rated_voltage: up to 5.25 V"),  # 5.25 V > sqrt(0.1 x 240) = 4.9 V
    ("derated", ["derate=0.9"], "error", "rated_voltage"),  # 4.545 V > 0.9 x 4.9 V
    ("high_value_passes", ["value=1kohm", "va=9V 1%"], "pass", ""),  # rated 10 V
    ("voltage_limited", ["value=1kohm", "va=11V"], "error", "rated_voltage"),  # > sqrt(0.1 x 1000) = 10 V
    ("reverse_polarity", ["va=0V", "vb=4.5V 1%"], "pass", ""),  # magnitude across the part
    ("v_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("ambient_out", ["ta=-60°C to 85°C"], "error", "t_oper_ambient"),
]


@unittest.skipUnless(shutil.which("pcb"), "pcb not installed")
class TestBuild(unittest.TestCase):
    """Build the fixture wrapper in its own workspace (the fixture is not under components/)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "pcb.toml").write_text('[workspace]\npcb-version = "0.4"\n')
        cls.dir = root / "RSER1"
        copytree(FIX, cls.dir)
        text, problems = generate(cls.dir)
        assert not problems, problems
        (cls.dir / "RSER1.zen").write_text(text)
        (cls.dir / "pcb.toml").write_text("")
        subprocess.run(["pcb", "fmt", str(cls.dir)], check=True, capture_output=True)
        shutil.copy(HARNESS, cls.dir / "_harness.zen")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, *args):
        r = subprocess.run(["pcb", "build", "-Wstyle", "-Dwarnings", *args], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_wrapper_builds_standalone(self):
        rc, out = self.build(str(self.dir / "RSER1.zen"))
        self.assertEqual(rc, 0, out)

    def test_excluded_e96_value_refused(self):
        """A wrapper generated with E96 from 100 ohm refuses 47.5 ohm and accepts 47 ohm (E24) and 102 ohm."""
        from tests.test_zen import outcome
        work = Path(self.tmp.name) / "RSER1E96"
        work.mkdir()
        copy = edited(work, E96_MIN)
        text, problems = generate(copy)
        assert not problems, problems
        (copy / "RSER1.zen").write_text(text)
        (copy / "pcb.toml").write_text("")
        subprocess.run(["pcb", "fmt", str(copy)], check=True, capture_output=True)
        shutil.copy(HARNESS, copy / "_harness.zen")
        for value, expect in (("47ohm", "pass"), ("102ohm", "pass"), ("47.5ohm", "error"), ("97.6ohm", "error")):
            rc, out = self.build(str(copy / "_harness.zen"), f"--config=value={value}", "--config=va=1V 1%")
            with self.subTest(value=value):
                self.assertEqual(outcome(rc, out), expect, out)
                if expect == "error":
                    self.assertIn("not an allowed value", out)

    def test_harness_cases(self):
        from tests.test_zen import outcome
        for name, overrides, expect, text in CASES:
            rc, out = self.build(str(self.dir / "_harness.zen"), *[f"--config={c}" for c in overrides])
            with self.subTest(case=name):
                self.assertEqual(outcome(rc, out), expect, out)
                self.assertIn(text, out)


if __name__ == "__main__":
    unittest.main()


class TestErjRatedVoltageAgrees(unittest.TestCase):
    """The rated-voltage formula exists in lib.series and in each ERJ calc.py: they must agree."""

    def test_lib_and_calc_agree(self):
        from lib import load
        from lib.series import rated_voltage
        for name in ("Panasonic/ERJ-2RKF", "Panasonic/ERJ-3EKF"):
            part = load(name)
            p, vlim = part.param("p70").max, part.param("v_limit").max
            for r in (10.0, 49.9, 1e3, 25e3, 1e6):
                self.assertAlmostEqual(rated_voltage(r, p, vlim), part.calc.rated_voltage(r, p, vlim), places=12)
