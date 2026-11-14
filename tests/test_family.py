"""Families and variants, typ_ref, tol_pct, series, and the new README limits line."""

import tempfile
import unittest
from pathlib import Path
from shutil import copytree

from lib import Param, load, readme, wca
from lib.check import check_component
from lib.component import to_param
from lib.zen import generate, wrappers

FIX = Path(__file__).parent / "fixtures" / "Acme"


def messages(folder):
    return [f"{lvl}: {msg}" for lvl, msg in check_component(folder)]


def edited_family(tmp, toml=(), variants=(), calc=()):
    """Copy FAM1 into tmp, applying (old, new) replacements to component.toml, variants.toml and calc.py."""
    copy = Path(tmp) / "FAM1"
    copytree(FIX / "FAM1", copy)
    for name, pairs in (("component.toml", toml), ("variants.toml", variants), ("calc.py", calc)):
        text = (copy / name).read_text()
        for old, new in pairs:
            assert old in text, old
            text = text.replace(old, new)
        (copy / name).write_text(text)
    return copy


class TestLoadFamily(unittest.TestCase):
    def test_load_by_family_and_variant(self):
        a = load(str(FIX / "FAM1"), variant="FAM1-A")
        b = load(str(FIX / "FAM1"), variant="FAM1-B")
        self.assertEqual((a.variant, a.info["value"], a.info["mpn"]), ("FAM1-A", "FAM1-A", "FAM1-A#R"))
        self.assertEqual(a.family_path, FIX / "FAM1")
        self.assertEqual(b.info["mpn"], "FAM1-B#R")
        self.assertEqual(a.info["alternates"], ["FAM1-A#T"])
        self.assertEqual(a.calc.vout(1.0, 10e3, 10e3), 2.0)

    def test_restricted_and_override_rows(self):
        a = load(str(FIX / "FAM1"), variant="FAM1-A")
        b = load(str(FIX / "FAM1"), variant="FAM1-B")
        self.assertNotIn("vhi_only", a.params)
        self.assertAlmostEqual(b.param("vhi_only").max, 5.0)
        self.assertAlmostEqual(a.param("vref").min, 0.98)  # overridden
        self.assertAlmostEqual(b.param("vref").min, 0.99)  # shared
        self.assertEqual(list(a.params)[:3], ["vin_abs", "vref", "vref_c"])  # override keeps its position

    def test_load_by_variant_value(self):
        part = load(str(FIX / "FAM1-B"))  # not a directory: found by scanning the siblings' variants.toml
        self.assertEqual((part.variant, part.info["value"]), ("FAM1-B", "FAM1-B"))
        with tempfile.TemporaryDirectory() as d:  # same through root= and 'Mfr/Value'
            copytree(FIX / "FAM1", Path(d) / "components" / "Acme" / "FAM1")
            self.assertEqual(load("Acme/FAM1-A", root=Path(d)).variant, "FAM1-A")
        with self.assertRaises(FileNotFoundError):
            load(str(FIX / "NOPE-9"))

    def test_load_errors(self):
        with self.assertRaises(ValueError) as cm:
            load(str(FIX / "FAM1"))
        self.assertIn("FAM1-A, FAM1-B", str(cm.exception))
        with self.assertRaises(ValueError):
            load(str(FIX / "FAM1"), variant="FAM1-Z")
        with self.assertRaises(ValueError):
            load(str(FIX / "LDO1"), variant="X")
        self.assertIsNone(load(str(FIX / "LDO1")).variant)
        self.assertIsNone(load(str(FIX / "LDO1")).family_path)


class TestCheckFamily(unittest.TestCase):
    def test_good_family(self):
        self.assertEqual(messages(FIX / "FAM1"), [])

    def test_unknown_variant_in_row(self):
        with tempfile.TemporaryDirectory() as d:
            text = "\n".join(messages(edited_family(d, toml=[('["FAM1-B"]', '["FAM1-B", "FAM1-Q"]')])))
        self.assertIn("param vhi_only: variants names unknown variant 'FAM1-Q'", text)

    def test_inputs_key_missing_in_one_variant(self):
        with tempfile.TemporaryDirectory() as d:
            text = "\n".join(messages(edited_family(d, calc=[('{"vref": "vref"}', '{"vref": "vhi_only.max"}')])))
        self.assertIn("variant FAM1-A: INPUTS: vout.vref -> unknown param key 'vhi_only'", text)
        self.assertNotIn("variant FAM1-B", text)

    def test_override_row_is_checked(self):
        with tempfile.TemporaryDirectory() as d:
            text = "\n".join(messages(edited_family(d, variants=[("min = 980", "min = 1100")])))
        self.assertIn("ERROR: variant FAM1-A: param vref: min <= typ <= max violated", text)

    def test_variant_part_field_missing(self):
        with tempfile.TemporaryDirectory() as d:
            text = "\n".join(messages(edited_family(d, variants=[('mpn = "FAM1-B#R"\n', "")])))
        self.assertIn("ERROR: variant FAM1-B: [part] missing field 'mpn'", text)
        self.assertNotIn("variant FAM1-A: [part]", text)


class TestReadmeFamily(unittest.TestCase):
    def test_family_readme(self):
        text = readme.build(FIX / "FAM1")
        self.assertIn("| Value | mpn | alternates | temp_grade | step |", text)
        self.assertIn("| FAM1-A | FAM1-A#R | FAM1-A#T | 0 to 70 degC | none |", text)
        self.assertIn("| FAM1-B | FAM1-B#R |  | -40 to 125 degC | none |", text)
        self.assertIn("Variants: FAM1-B.", text)
        self.assertIn("## Variant-specific parameters: FAM1-A", text)
        self.assertIn("| Reference voltage |  | 980 | 1000 | 1020 | mV | TA = 25 degC, A grade |", text)
        self.assertNotIn("Variant-specific parameters: FAM1-B", text)
        self.assertIn("`vref` -> `vref`", text)


class TestZenFamily(unittest.TestCase):
    def test_one_wrapper_per_variant(self):
        self.assertEqual([(d.name, v) for d, v in wrappers([str(FIX / "FAM1")])], [("FAM1", "FAM1-A"), ("FAM1", "FAM1-B")])
        self.assertEqual([v for _, v in wrappers([str(FIX / "LDO1")])], [None])
        a, pa = generate(FIX / "FAM1", "FAM1-A")
        b, pb = generate(FIX / "FAM1", "FAM1-B")
        self.assertEqual((pa, pb), ([], []))
        self.assertIn('name="FAM1-A"', a)
        self.assertIn('mpn="FAM1-A#R"', a)
        self.assertIn('"alternatives": ["FAM1-A#T"]', a)
        self.assertIn('name="FAM1-B"', b)
        self.assertNotIn("alternatives", b)

    def test_tol_pct_row_checked_with_loaded_limits(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited_family(d, toml=[('tol_pct = [-1, 2]\nunit = "mV"', 'tol_pct = [-1, 2]\nunit = "V"\ncheck_pins = ["OUT"]')])
            text, problems = generate(copy, "FAM1-A")
        self.assertEqual(problems, [])
        self.assertIn('"lo": 990.0, "hi": 1020.0', text)  # typ 1000 V, -1 % / +2 %: limits come from tol_pct
        self.assertIn("tol_pct -1 % / +2 %", text)


class TestTolPctTypRef(unittest.TestCase):
    def test_tol_pct_loaded(self):
        p = to_param({"typ": 10, "tol_pct": [-10, 10], "unit": "V"})
        self.assertAlmostEqual(p.min, 9.0)
        self.assertAlmostEqual(p.max, 11.0)
        p = to_param({"typ": -10, "tol_pct": [-10, 10], "unit": "V"})  # sorted for a negative typ
        self.assertEqual((p.min, p.typ, p.max), (-11.0, -10.0, -9.0))
        with self.assertRaises(ValueError):
            to_param({"typ": 1, "min": 0, "tol_pct": [-1, 1], "unit": "V"})

    def test_tol_pct_wca(self):
        p = load(str(FIX / "FAM1"), variant="FAM1-A").param("vref_c")
        r = wca(lambda v: 2 * v, v=p)
        self.assertAlmostEqual(r.min, 1.98)
        self.assertAlmostEqual(r.max, 2.04)

    def test_tol_pct_check(self):
        with tempfile.TemporaryDirectory() as d:
            text = "\n".join(messages(edited_family(d, toml=[("tol_pct = [-1, 2]", "tol_pct = [3, 2]")])))
            self.assertIn("param vref_c: tol_pct lo 3 > hi 2", text)
        with tempfile.TemporaryDirectory() as d:
            text = "\n".join(messages(edited_family(d, toml=[("tol_pct = [-1, 2]", "tol_pct = [-1, 2]\nmax = 5")])))
            self.assertIn("param vref_c: tol_pct needs typ and no min/max", text)

    def test_tol_pct_readme(self):
        text = readme.build(FIX / "FAM1")
        self.assertIn("| Reference voltage, 1 mA |  | -1 % | 1000 | +2 % | mV |", text)

    def test_typ_ref_resolve(self):
        part = load(str(FIX / "LDO1"))
        part.params["vt"] = Param(min=5.0, typ=11.0, max=20.0, unit="V", typ_ref="IN")
        self.assertEqual(part.resolve("vt", {"IN": 15.0}).typ, 26.0)
        self.assertEqual(part.resolve("vt", {"IN": 15.0}).min, 5.0)
        rail = Param(min=14.0, max=16.0)  # no typ
        self.assertIsNone(part.resolve("vt", {"IN": rail}).typ)
        self.assertEqual(part.resolve("vt", {"IN": Param(min=14, typ=15, max=16)}).typ, 26.0)
        with self.assertRaises(ValueError):
            part.resolve("vt", {})

    def test_typ_ref_check_and_readme(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited_family(d, toml=[('unit = "mV"\nconditions = "TA', 'unit = "mV"\ntyp_ref = "IN"\nconditions = "TA')])
            self.assertEqual(messages(copy), [])  # ordering check skipped, ref is a pin
            self.assertIn("| Reference voltage |  | 990 | 1000 (rel. IN) | 1010 |", readme.build(copy))
        with tempfile.TemporaryDirectory() as d:
            copy = edited_family(d, toml=[('unit = "mV"\nconditions = "TA', 'unit = "mV"\ntyp_ref = "VSS"\nconditions = "TA')])
            self.assertIn("typ_ref 'VSS' is not a [[pin]] name", "\n".join(messages(copy)))


class TestSeries(unittest.TestCase):
    def test_series_sorted_by_number(self):
        part = load(str(FIX / "FAM1"), variant="FAM1-A")
        s = part.series("vovc_thr")
        self.assertEqual(list(s), [2, 16])  # numeric order, not string order
        self.assertAlmostEqual(s[16].typ, 1.6)
        self.assertEqual(part.series("nothing"), {})

    def test_suffix_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            text = "\n".join(messages(edited_family(d, toml=[('symbol = "VTH_16"', 'symbol = "VTH_10"')])))
        self.assertIn("param vovc_thr_16: key suffix 16 != symbol suffix 10", text)


class TestLimitsLine(unittest.TestCase):
    def test_limits_present(self):
        text = readme.build(FIX / "LDO1")
        self.assertIn("## Limits of this data", text)
        self.assertIn("Rows by scope: 25C 1, full 4, na 1, partial 1 (25C rows hold only at 25 degC). "
                      "Curve (graph) rows: 0. Text rows: 1.", text)
        self.assertNotIn("junction", text)

    def test_junction_only(self):
        tables = [{"kind": "rec_op", "unit": "degC", "symbol": "TJ", "name": "Junction temperature", "scope": "na"}]
        self.assertIn("Temperatures are junction (TJ)", readme.limits_line(tables))
        tables[0]["check_ambient"] = True
        self.assertNotIn("junction (TJ)", readme.limits_line(tables))


if __name__ == "__main__":
    unittest.main()


class TestVariantMpn(unittest.TestCase):
    def test_variant_must_set_own_mpn(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = "\n".join(messages(edited_family(tmp, variants=[('mpn = "FAM1-B#R"\n', "")])))
        self.assertIn("variant FAM1-B: must set its own mpn", text)

    def test_variant_must_set_own_temp_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = (FIX / "FAM1" / "variants.toml").read_text()
            line = next(ln for ln in src.splitlines(keepends=True) if ln.startswith("temp_grade"))
            text = "\n".join(messages(edited_family(tmp, variants=[(line, "")])))
        self.assertIn("must set its own temp_grade", text)
