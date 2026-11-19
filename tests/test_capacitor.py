"""Capacitor series: printed-value parsing, catalog reading, part selection, restrictions, lib.check, the decode
cross-check, the catalog generator, capacitance_worst_pct / _ppm, the Zener wrapper text and README."""

import contextlib
import csv
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from shutil import copytree

from lib import Param, load, readme, wca
from lib import capacitor, catalog
from lib.check import check_component
from lib.zen import generate

FIX = Path(__file__).parent / "fixtures" / "Acme" / "CSER1"
EXPORT = Path(__file__).parent / "fixtures" / "murata_gcm_sample.csv"


def edited(tmp, toml=(), calc=(), cat=()):
    """Copy CSER1 into tmp, applying (old, new) replacements to component.toml, calc.py and catalog.csv."""
    copy = Path(tmp) / "CSER1"
    copytree(FIX, copy)
    for name, pairs in (("component.toml", toml), ("calc.py", calc), ("catalog.csv", cat)):
        text = (copy / name).read_text(encoding="utf-8")
        for old, new in pairs:
            assert old in text, old
            text = text.replace(old, new)
        (copy / name).write_text(text, encoding="utf-8")
    return copy


def messages(folder):
    return [f"{lvl}: {msg}" for lvl, msg in check_component(folder)]


def export_rows():
    with open(EXPORT, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def export_row(number):
    return next(dict(r) for r in export_rows() if r["Part Number"] == number)


class TestParse(unittest.TestCase):
    def test_capacitance(self):
        self.assertEqual(capacitor.parse_capacitance("100pF"), 100e-12)
        self.assertEqual(capacitor.parse_capacitance("0.1μF"), 1e-7)  # Greek mu, as the export prints it
        self.assertEqual(capacitor.parse_capacitance("0.1uF"), 1e-7)
        self.assertEqual(capacitor.parse_capacitance("6,800pF"), 6.8e-9)
        self.assertEqual(capacitor.parse_capacitance("1.5pF"), 1.5e-12)
        self.assertEqual(capacitor.parse_capacitance("1,000,000pF"), 1e-6)
        for bad in ("1,2,3pF", "1,23pF", ",800pF", "6,80pF", "6800,pF"):
            with self.assertRaises(ValueError, msg=bad):
                capacitor.parse_capacitance(bad)
        with self.assertRaises(ValueError):
            capacitor.parse_capacitance("10 ohm")

    def test_voltage(self):
        self.assertEqual(capacitor.parse_voltage("50Vdc"), 50.0)
        self.assertEqual(capacitor.parse_voltage("1,000Vdc"), 1000.0)
        self.assertEqual(capacitor.parse_voltage("6.3Vdc"), 6.3)
        self.assertEqual(capacitor.parse_voltage("50V"), 50.0)
        with self.assertRaises(ValueError):
            capacitor.parse_voltage("50")

    def test_tolerance(self):
        self.assertEqual(capacitor.parse_tolerance("±10%"), ("rel", 0.1))
        self.assertEqual(capacitor.parse_tolerance("+/-2.5%"), ("rel", 0.025))
        self.assertEqual(capacitor.parse_tolerance("±0.25pF"), ("abs", 0.25e-12))
        with self.assertRaises(ValueError):
            capacitor.parse_tolerance("+80/-20%")

    def test_keys_agree_between_python_and_text(self):
        self.assertEqual(capacitor.zen_key(1e-7, 50.0), (100000000, 50000))
        self.assertEqual(capacitor.zen_key(6.8e-9, 1000.0), (6800000, 1000000))
        self.assertEqual(capacitor.zen_key(1.5e-12, 6.3), (1500, 6300))
        self.assertEqual(capacitor.tol_key("±0.25pF"), capacitor.tol_key("+/- 0.25 pF"))


class TestCatalog(unittest.TestCase):
    def test_fixture_catalog(self):
        rows = load(str(FIX)).catalog()
        self.assertEqual(len(rows), 6)
        self.assertEqual(load(str(FIX)).dielectrics(), ["C0G", "X7R"])
        row = next(r for r in rows if r.value == "CSER1-X682K")
        self.assertEqual((row.c, row.v, row.tol_kind, row.tol), (6.8e-9, 1000.0, "rel", 0.1))

    def test_bad_catalog_lists_every_problem(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, cat=[("0.1μF,±10%,16Vdc", "banana,±10%,16Vdc"),
                                  ("CSER1-X104M,X7R,0.1μF,±20%,50Vdc", "CSER1-X104K,X7R,0.1μF,±20%,50Vdc")])
            with self.assertRaises(ValueError) as cm:
                capacitor.read_catalog(copy / "catalog.csv")
            text = str(cm.exception)
            self.assertIn("capacitance 'banana'", text)
            self.assertIn("value appears more than once", text)

    def test_wrong_columns(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, cat=[("value,dielectric", "value,diel")])
            with self.assertRaises(ValueError):
                capacitor.read_catalog(copy / "catalog.csv")


class TestSelect(unittest.TestCase):
    def setUp(self):
        self.part = load(str(FIX))

    def test_match(self):
        sel = self.part.select(0.1e-6, 16, "X7R")
        self.assertEqual((sel.value, sel.mpn, sel.alternates), ("CSER1-X104K16", "CSER1-X104K16T", ["CSER1-X104K16R"]))
        self.assertEqual((sel.dielectric, sel.tolerance), ("X7R", "±10%"))
        self.assertEqual(sel.rated_voltage.max, 16.0)
        self.assertEqual(sel.rated_voltage.min, -16.0)  # non-polarized
        self.assertAlmostEqual(sel.capacitance.min, 0.09e-6)
        self.assertEqual(sel.capacitance.typ, 0.1e-6)
        self.assertAlmostEqual(sel.capacitance.max, 0.11e-6)
        self.assertIn("CSER1-X104K16", sel.capacitance.cite)

    def test_printed_text_and_tolerance(self):
        sel = self.part.select("0.1uF", "50Vdc", "X7R", tolerance="+/-20%")
        self.assertEqual(sel.value, "CSER1-X104M")
        self.assertAlmostEqual(sel.capacitance.max, 0.12e-6)
        self.assertEqual(self.part.select(6.8e-9, 1000, "X7R").value, "CSER1-X682K")  # printed "6,800pF", "1,000Vdc"

    def test_absolute_tolerance(self):
        sel = self.part.select(1.5e-12, 50, "C0G")
        self.assertAlmostEqual(sel.capacitance.min, 1.25e-12)
        self.assertAlmostEqual(sel.capacitance.max, 1.75e-12)
        self.assertAlmostEqual(sel.part.param("tolerance").max, 0.25 / 1.5)  # as a fraction of C

    def test_no_match(self):
        for args, text in (((0.2e-6, 50, "X7R"), "no X7R part with that capacitance"),
                           ((0.1e-6, 25, "X7R"), "rated voltages for that capacitance: 16Vdc, 50Vdc"),
                           ((0.1e-6, 50, "X7R", "+/-5%"), "tolerances for that capacitance and voltage: ±10%, ±20%"),
                           ((0.1e-6, 50, "Y5V"), "dielectric 'Y5V' is not in the catalog (C0G, X7R)")):
            with self.assertRaises(ValueError) as cm:
                self.part.select(*args)
            self.assertIn("no catalog part for", str(cm.exception))
            self.assertIn(text, str(cm.exception))

    def test_ambiguous_tolerance(self):
        with self.assertRaises(ValueError) as cm:
            self.part.select(0.1e-6, 50, "X7R")  # +/-10 % and +/-20 % both listed
        self.assertIn("ambiguous: 2 catalog parts", str(cm.exception))
        self.assertIn("pass tolerance= one of", str(cm.exception))

    def test_ambiguous_same_tolerance(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, cat=[("CSER1-X104M,X7R,0.1μF,±20%", "CSER1-X104K2,X7R,0.1μF,±10%")])
            with self.assertRaises(ValueError) as cm:
                load(str(copy)).select(0.1e-6, 50, "X7R", tolerance="+/-10%")
            self.assertIn("ambiguous", str(cm.exception))
            self.assertIn("CSER1-X104K, CSER1-X104K2", str(cm.exception))

    def test_select_on_other_series_fails(self):
        with self.assertRaises(ValueError):
            load(str(FIX.parent / "RSER1")).select(1e-7, 50, "X7R")


class TestRestrictions(unittest.TestCase):
    def setUp(self):
        self.part = load(str(FIX))

    def test_plain_load_has_only_unrestricted_rows(self):
        self.assertEqual(list(self.part.params), [])  # every fixture row is restricted
        self.assertEqual(set(self.part.hidden), {"tc_x7r", "tc_c0g", "op_temp_x7r", "op_temp_c0g", "thickness", "self_heating"})
        with self.assertRaises(KeyError) as cm:
            self.part.param("tc_x7r")
        self.assertIn("restricted to dielectric X7R", str(cm.exception))

    def test_dielectric_rows(self):
        x7r = self.part.select(0.1e-6, 16, "X7R").part
        c0g = self.part.select(100e-12, 100, "C0G").part
        self.assertIn("tc_x7r", x7r.params)
        self.assertNotIn("tc_c0g", x7r.params)
        self.assertIn("tc_c0g", c0g.params)
        self.assertEqual(x7r.param("tc").max, 0.15)  # alias of the dielectric's row, % -> fraction
        self.assertEqual(c0g.param("tc").max, 30e-6)  # ppm/degC -> 1/degC
        self.assertEqual(c0g.param("op_temp_c0g").max, 150)

    def test_part_rows(self):
        k = self.part.select(0.1e-6, 50, "X7R", "+/-10%").part
        m = self.part.select(0.1e-6, 50, "X7R", "+/-20%").part
        self.assertIn("thickness", k.params)
        self.assertNotIn("thickness", m.params)
        self.assertNotIn("self_heating", self.part.select(100e-12, 100, "C0G").part.params)

    def test_selection_keys(self):
        p = self.part.select(0.1e-6, 50, "X7R", "+/-10%").part
        for key in capacitor.SELECTION_KEYS:
            self.assertIn(key, p.params)
        self.assertEqual(p.param("rated_v").max, 50.0)

    def test_dielectric_row_in_toml_is_not_a_part_row(self):
        copy = tempfile.TemporaryDirectory()
        self.addCleanup(copy.cleanup)
        d = edited(copy.name, toml=[('[param.thickness]\nparts = ["CSER1-X104K"]', '[param.thickness]\nparts = ["CSER1-X104K"]\ndielectric = "X7R"')])
        self.assertIn("a row has dielectric or parts, not both", "\n".join(messages(d)))


class TestCapacitanceWorst(unittest.TestCase):
    def test_x7r_corners(self):
        sel = load(str(FIX)).select(0.1e-6, 50, "X7R", "+/-10%")
        cap = wca(sel.part.calc.capacitance_worst_pct, **sel.part.inputs("capacitance_worst_pct"))
        self.assertAlmostEqual(cap.min, 0.1e-6 * 0.90 * 0.85)  # tolerance -10 %, X7R -15 %
        self.assertAlmostEqual(cap.max, 0.1e-6 * 1.10 * 1.15)
        self.assertIsNone(cap.typ)  # the tolerance and tc rows are bound-only: no typ (state it with with_typ in code)

    def test_c0g_needs_dt(self):
        sel = load(str(FIX)).select(100e-12, 100, "C0G")
        cap = wca(sel.part.calc.capacitance_worst_ppm, dt=Param(min=0, max=100), **sel.part.inputs("capacitance_worst_ppm"))
        self.assertAlmostEqual(cap.min, 100e-12 * 0.95 * (1 - 30e-6 * 100))
        self.assertAlmostEqual(cap.max, 100e-12 * 1.05 * (1 + 30e-6 * 100))

    def test_ppm_function_requires_dt_and_range(self):
        calc = load(str(FIX)).calc
        with self.assertRaises(TypeError):
            calc.capacitance_worst_ppm(100e-12, 0.05, 30e-6)  # dt has no default
        for dt in (-1, 100.5):
            with self.assertRaises(ValueError):
                calc.capacitance_worst_ppm(100e-12, 0.05, 30e-6, dt)
        self.assertAlmostEqual(calc.capacitance_worst_ppm(100e-12, 0, 30e-6, 0), 100e-12)

    def test_wrong_kind_of_tc_is_refused(self):
        """The bug being prevented: a 1/degC coefficient read as a fraction understates C0G badly."""
        calc = load(str(FIX)).calc
        with self.assertRaises(ValueError):
            calc.capacitance_worst_pct(100e-12, 0.05, 30e-6)
        with self.assertRaises(ValueError):
            calc.capacitance_worst_ppm(100e-12, 0.05, 0.15, 100)
        c0g = load(str(FIX)).select(100e-12, 100, "C0G")
        with self.assertRaises(ValueError):
            wca(c0g.part.calc.capacitance_worst_pct, **c0g.part.inputs("capacitance_worst_pct"))

    def test_real_c0g(self):
        for name, tol, low in (("Murata/GCM155", "+/-1%", 98.703e-12), ("Murata/GCM188", "+/-2%", 97.706e-12)):
            sel = load(name).select(100e-12, 50, "C0G", tol)
            cap = wca(sel.part.calc.capacitance_worst_ppm, dt=Param(min=0, max=100), **sel.part.inputs("capacitance_worst_ppm"))
            self.assertAlmostEqual(cap.min, low, places=18)

    def test_tc_is_read_from_the_dielectric_row(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, toml=[("min = -15\nmax = 15", "min = -22\nmax = 56")])
            sel = load(str(copy)).select(0.1e-6, 50, "X7R", "+/-10%")
            cap = wca(sel.part.calc.capacitance_worst_pct, **sel.part.inputs("capacitance_worst_pct"))
            self.assertAlmostEqual(cap.min, 0.1e-6 * 0.90 * (1 - 0.22))
            self.assertAlmostEqual(cap.max, 0.1e-6 * 1.10 * 1.56)

    def test_real_murata_directories(self):
        for name, value in (("Murata/GCM155", "GCM155R71H104KE02"), ("Murata/GCM188", "GCM188R71H104KA57")):
            sel = load(name).select(0.1e-6, 50, "X7R", "+/-10%")
            self.assertEqual((sel.value, sel.mpn), (value, value + "D"))
            cap = wca(sel.part.calc.capacitance_worst_pct, **sel.part.inputs("capacitance_worst_pct"))
            self.assertAlmostEqual(cap.min, 0.0765e-6, places=12)
            self.assertIn("DS p.2", sel.part.param("tc").cite)
            self.assertIn("thickness_t", sel.part.params)  # the per-part rows of the reference sheet are kept


class TestCheck(unittest.TestCase):
    def run_edit(self, toml=(), calc=(), cat=()):
        with tempfile.TemporaryDirectory() as d:
            return "\n".join(messages(edited(d, toml, calc, cat)))

    def test_fixture_passes(self):
        self.assertEqual(messages(FIX), [])

    def test_dielectric_without_tc_row_is_refused(self):
        text = self.run_edit(toml=[('tc_param = { X7R = "tc_x7r", C0G = "tc_c0g" }', 'tc_param = { X7R = "tc_x7r" }')])
        self.assertIn("ERROR: catalog dielectric 'C0G' has no [part] tc_param entry", text)

    def test_tc_row_problems(self):
        self.assertIn("is not a param key", self.run_edit(toml=[('C0G = "tc_c0g"', 'C0G = "nope"')]))
        self.assertIn('must have dielectric = "C0G"', self.run_edit(toml=[('C0G = "tc_c0g"', 'C0G = "tc_x7r"')]))
        self.assertIn("needs min, max and unit % or ppm/degC", self.run_edit(toml=[('unit = "ppm/degC"', 'unit = "degC"')]))

    def test_restriction_problems(self):
        self.assertIn("dielectric 'Y5V' is not in the catalog",
                      self.run_edit(toml=[('dielectric = "C0G"\nname = "Operating', 'dielectric = "Y5V"\nname = "Operating')]))
        self.assertIn("parts names 'NOPE', which is not a catalog value",
                      self.run_edit(toml=[('parts = ["CSER1-X104K"]\nname = "Thickness"', 'parts = ["NOPE"]\nname = "Thickness"')]))
        self.assertIn("parts must be a non-empty list",
                      self.run_edit(toml=[('parts = ["CSER1-X104K"]\nname = "Thickness"', 'parts = []\nname = "Thickness"')]))

    def test_ambient_row_per_dielectric(self):
        text = self.run_edit(toml=[('name = "Operating temperature, C0G"\nkind = "rec_op"', 'name = "Operating temperature, C0G"\nkind = "rec_op"\nunchecked = "x"'),
                                   ("check_ambient = true\n\n[param.thickness]", "\n[param.thickness]")])
        self.assertIn("dielectric C0G: needs exactly one check_ambient row", text)

    def test_part_fields_and_pins(self):
        self.assertIn("[part] series needs 'catalog'", self.run_edit(toml=[('catalog = "catalog.csv"\n', "")]))
        self.assertIn("[part] mpn must be absent", self.run_edit(toml=[('series = "capacitor"', 'series = "capacitor"\nmpn = "X"')]))
        self.assertIn("single capital letters", self.run_edit(toml=[('package_alternates = ["R"]', 'package_alternates = ["T"]')]))
        self.assertIn("catalog not found", self.run_edit(toml=[('catalog = "catalog.csv"', 'catalog = "nope.csv"')]))

    def test_reserved_key_and_check_pins(self):
        self.assertIn("key is reserved for the part selection", self.run_edit(toml=[("[param.thickness]", "[param.tolerance]")]))
        self.assertIn("check_pins is not supported", self.run_edit(toml=[('unchecked = "depends on AC current; owner: module"', 'check_pins = ["1"]')]))

    def test_bad_catalog_value(self):
        self.assertIn("ERROR: catalog.csv line 2", self.run_edit(cat=[("50Vdc,0.5mm ±0.05mm,\"Acme test list, row CSER1-X104K\"", "50V dc,0.5mm ±0.05mm,\"Acme test list, row CSER1-X104K\"")]))

    def test_inputs_may_use_selection_keys(self):
        self.assertIn("unknown param key 'nope'", self.run_edit(calc=[('"tc": "tc"', '"tc": "nope"')]))


GOOD = "GCM155R71H104KE02#"


class TestCommittedCatalogDecode(unittest.TestCase):
    """lib.check re-decodes every committed catalog row, so a hand edit of any column is an error."""

    def mutated(self, value, column, new):
        with tempfile.TemporaryDirectory() as d:
            work = Path(d) / "GCM155"
            copytree(Path(__file__).parent.parent / "components" / "Murata" / "GCM155", work)
            path = work / "catalog.csv"
            with open(path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            row = next(r for r in rows if r["value"] == value)
            row[column] = new
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=capacitor.CATALOG_COLUMNS, lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
            return "\n".join(m for m in messages(work) if m.startswith("ERROR"))

    def test_unedited_catalogs_pass(self):
        # The git-ignored datasheet PDFs may be absent (CI, a release checkout): lib.check tolerates that warning, and
        # so does this test. Any other message still fails.
        from lib.check import TOLERATED
        for name in ("GCM155", "GCM188"):
            msgs = messages(Path(__file__).parent.parent / "components" / "Murata" / name)
            self.assertEqual([m for m in msgs if TOLERATED not in m], [])

    def test_each_column_edit_is_an_error(self):
        v = "GCM1555C1H101FA16"  # C0G, 100 pF, +/-1 %, 50 V, thickness 0.5 mm
        for column, new, text in (("capacitance", "220pF", "capacitance code 101 gives 100 pF"),
                                  ("rated_voltage", "500Vdc", "rated-voltage code 1H gives 50 V"),
                                  ("tolerance", "\u00b120%", "tolerance letter F gives +/-1%"),
                                  ("dielectric", "X7R", "dielectric code 5C gives C0G"),
                                  ("thickness", "0.8mm \u00b10.1mm", "thickness code 5 gives 0.5 mm")):
            with self.subTest(column=column):
                out = self.mutated(v, column, new)
                self.assertIn(f"catalog row {v}: {text}", out)

    def test_value_edit_is_an_error(self):
        self.assertIn("size+thickness code 188 differs", self.mutated("GCM1555C1H101FA16", "value", "GCM1885C1H101FA16"))
        self.assertIn("does not have the form", self.mutated("GCM1555C1H101FA16", "value", "GCM1555C1H101F"))


class TestSuffixConvention(unittest.TestCase):
    def run_edit(self, toml):
        with tempfile.TemporaryDirectory() as d:
            return "\n".join(messages(edited(d, toml=toml)))

    def test_parts_row_of_the_other_dielectric_warns(self):
        text = self.run_edit([('[param.thickness]\nparts = ["CSER1-X104K"]', '[param.thickness_c0g]\nparts = ["CSER1-X104K"]')])
        self.assertIn("WARN: param thickness_c0g: key ends in _c0g but parts names CSER1-X104K of another dielectric", text)

    def test_dielectric_row_with_the_wrong_suffix_warns(self):
        text = self.run_edit([("[param.op_temp_c0g]", "[param.op_temp_x7r2]"), ("[param.op_temp_x7r]\ndielectric = \"X7R\"", "[param.op_temp_c0g]\ndielectric = \"X7R\"")])
        self.assertIn("key ends in _c0g but dielectric = 'X7R'", text)

    def test_matching_suffix_is_quiet(self):
        text = self.run_edit([('[param.thickness]\nparts = ["CSER1-X104K"]', '[param.thickness_x7r]\nparts = ["CSER1-X104K"]')])
        self.assertNotIn("WARN", text)


class TestDecode(unittest.TestCase):
    def test_good_rows(self):
        for number in ("GCM155R71H104KE02#", "GCM1555C1H100FA16#", "GCM188R71H104KA57#", "GCM1555C1H1R0BA16#", "GCM21BR70J106KE22#"):
            self.assertEqual(catalog.decode(export_row(number)), [], number)

    def mismatch(self, **changes):
        row = export_row(GOOD)
        row.update(changes)
        return " | ".join(catalog.decode(row))

    def test_size_code(self):
        self.assertIn("size 15 gives length 1 mm", self.mismatch(Length="1.6mm ±0.1mm"))
        self.assertIn("size 15 gives width 0.5 mm", self.mismatch(Width="0.8mm ±0.1mm"))
        self.assertIn("size code 99 is not in the decode table", self.mismatch(**{"Part Number": "GCM995R71H104KE02#"}))

    def test_thickness_code(self):
        self.assertIn("thickness code 5 gives 0.5 mm", self.mismatch(Thickness="0.8mm ±0.1mm"))
        self.assertIn("thickness code Z is not in the decode table", self.mismatch(**{"Part Number": "GCM15ZR71H104KE02#"}))

    def test_dielectric_code(self):
        self.assertIn("dielectric code R7 gives X7R, export says 'C0G'", self.mismatch(**{"Temperature characteristics": "C0G"}))
        self.assertIn("dielectric code R9 is not in the decode table", self.mismatch(**{"Part Number": "GCM155R91H104KE02#"}))

    def test_voltage_code(self):
        self.assertIn("rated-voltage code 1H gives 50 V, export says '25Vdc'", self.mismatch(**{"Rated Voltage DC": "25Vdc"}))
        self.assertIn("rated-voltage code 9Z is not in the decode table", self.mismatch(**{"Part Number": "GCM155R79Z104KE02#"}))

    def test_capacitance_code(self):
        self.assertIn("capacitance code 104 gives 100000 pF", self.mismatch(Capacitance="0.22μF"))
        self.assertIn("capacitance code 1R0 gives 1.0 pF", " | ".join(catalog.decode({**export_row("GCM1555C1H1R0BA16#"), "Capacitance": "2pF"})))
        self.assertIn("is not 3 digits or R-decimal", self.mismatch(**{"Part Number": "GCM155R71HABCKE02#"}))

    def test_tolerance_letter(self):
        self.assertIn("tolerance letter K gives +/-10%, export says '±5%'", self.mismatch(**{"Tolerance of capacitance": "±5%"}))
        self.assertIn("tolerance letter Z is not in the decode table", self.mismatch(**{"Part Number": "GCM155R71H104ZE02#"}))

    def test_operating_temperature(self):
        self.assertIn("operating temperature", self.mismatch(**{"Operating Temperature": "-55～150℃"}))

    def test_malformed_number(self):
        self.assertIn("does not have the form", self.mismatch(**{"Part Number": "GCM155R71H104KE02"}))  # no package placeholder


def quiet_main(args):
    """catalog.main with its progress and error text swallowed."""
    with contextlib.redirect_stdout(io.StringIO()):
        return catalog.main(args)


class TestGenerator(unittest.TestCase):
    def build(self, rows, code="155", dielectrics=("X7R", "C0G")):
        return catalog.build_rows(rows, code, set(dielectrics), "sample.csv")

    def test_filters_and_cites(self):
        rows, errors, skipped = self.build(export_rows())
        self.assertEqual(errors, [])
        self.assertEqual([r["value"] for r in rows],
                         ["GCM1555C1H100FA16", "GCM1555C1H1R0BA16", "GCM155R71H104KE02", "GCM155R71H104ME02"])
        self.assertEqual(skipped, {"other size/thickness": 2, "other dielectric": 0, "not In Production": 0})
        r = next(r for r in rows if r["value"] == "GCM155R71H104KE02")
        self.assertEqual((r["dielectric"], r["capacitance"], r["tolerance"], r["rated_voltage"], r["thickness"]),
                         ("X7R", "0.1μF", "±10%", "50Vdc", "0.5mm ±0.05mm"))
        self.assertEqual(r["source"], "Murata product list export sample.csv, row GCM155R71H104KE02#")

    def test_dielectric_filter(self):
        rows, _, skipped = self.build(export_rows(), dielectrics=("X7R",))
        self.assertEqual([r["dielectric"] for r in rows], ["X7R", "X7R"])
        self.assertEqual(skipped["other dielectric"], 2)

    def test_status_filter(self):
        data = export_rows()
        data[1]["Product Status"] = "Not recommended"
        rows, _, skipped = self.build(data)
        self.assertEqual(skipped["not In Production"], 1)
        self.assertEqual(len(rows), 3)

    def test_mismatch_row_is_an_error_and_not_written(self):
        data = export_rows()
        for r in data:
            if r["Part Number"] == "GCM155R71H104ME02#":
                r["Tolerance of capacitance"] = "±5%"
        rows, errors, _ = self.build(data)
        self.assertEqual(len(rows), 3)
        self.assertNotIn("GCM155R71H104ME02", [r["value"] for r in rows])
        self.assertEqual(len(errors), 1)
        self.assertIn("GCM155R71H104ME02#: tolerance letter M gives +/-20%", errors[0])

    def test_duplicate_part_number(self):
        data = export_rows()
        data.append(dict(data[1]))
        _, errors, _ = self.build(data)
        self.assertTrue(any("appears more than once" in e for e in errors), errors)

    def test_main_writes_a_catalog_that_loads(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "GCM155"
            folder.mkdir()
            (folder / "component.toml").write_text('[part]\ntc_param = { X7R = "a" }\n')
            self.assertEqual(quiet_main(["murata-gcm", str(EXPORT), str(folder)]), 0)  # dielectrics from tc_param
            rows = capacitor.read_catalog(folder / "catalog.csv")
            self.assertEqual([r.value for r in rows], ["GCM155R71H104KE02", "GCM155R71H104ME02"])
            self.assertEqual(capacitor.read_catalog(folder / "catalog.csv")[0].v, 50.0)
            text = (folder / "catalog.csv").read_text(encoding="utf-8")
            self.assertTrue(text.startswith("value,dielectric,capacitance,tolerance,rated_voltage,thickness,source\n"))
            self.assertFalse(text.startswith("﻿"))  # no byte order mark

    def test_main_refuses_a_bad_directory_name_and_no_dielectric(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / "CSER1"
            folder.mkdir()
            self.assertEqual(quiet_main(["murata-gcm", str(EXPORT), str(folder)]), 1)
            folder = Path(d) / "GCM155"
            folder.mkdir()
            (folder / "component.toml").write_text("[part]\n")
            self.assertEqual(quiet_main(["murata-gcm", str(EXPORT), str(folder)]), 1)  # no tc_param, no --dielectrics

    def test_main_exit_code_on_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            data = export_rows()
            data[1]["Capacitance"] = "0.22μF"
            bad = Path(d) / "bad.csv"
            with open(bad, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=list(data[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(data)
            folder = Path(d) / "GCM155"
            folder.mkdir()
            (folder / "component.toml").write_text('[part]\ntc_param = { X7R = "a", C0G = "b" }\n')
            (folder / "catalog.csv").write_text("previous good catalog\n")
            self.assertEqual(quiet_main(["murata-gcm", str(bad), str(folder)]), 1)
            # on any decode error nothing is written: the previous catalog is left untouched
            self.assertEqual((folder / "catalog.csv").read_text(), "previous good catalog\n")


class TestCommittedCatalogs(unittest.TestCase):
    """The two Murata catalogs decode and list X7R and C0G rows (both dielectrics have a temperature-characteristic row)."""

    def test_murata_catalogs(self):
        for name, count in (("Murata/GCM155", 697), ("Murata/GCM188", 633)):
            part = load(name)
            rows = part.catalog()
            self.assertEqual((len(rows), part.dielectrics()), (count, ["C0G", "X7R"]), name)
            for r in rows:
                self.assertTrue(r.value.startswith(name.split("/")[1]) and r.source.endswith(r.value + "#"), r.value)


class TestZenAndReadme(unittest.TestCase):
    def test_wrapper_text(self):
        text, problems = generate(FIX)
        self.assertEqual(problems, [])
        self.assertIn('load("@stdlib/units.zen", "Capacitance", "Temperature", "Voltage")', text)
        self.assertIn("value = config(Capacitance,", text)
        self.assertIn("rated_v = config(Voltage,", text)
        self.assertIn("dielectric = config(str,", text)
        self.assertIn("tolerance = config(", text)
        self.assertIn('default=""', text)
        self.assertIn('("X7R", 100000000, 50000, "+/-10%"): "CSER1-X104K",  # 0.1uF 50Vdc +/-10%', text)
        self.assertIn('("X7R", 6800000, 1000000, "+/-10%"): "CSER1-X682K"', text)  # "6,800pF", "1,000Vdc"
        self.assertIn('("C0G", 1500, 50000, "+/-0.25pF"): "CSER1-C1R5C"', text)
        self.assertIn('("X7R", 100000000, 50000): ["+/-10%", "+/-20%"],', text)  # tolerances per value, for the message
        self.assertIn('_VALUE_STR = _VALUE.get(_FULL, "UNORDERABLE")', text)
        self.assertIn('_MPN_STR = _VALUE_STR + "T" if _FULL in _VALUE else "UNORDERABLE"', text)
        self.assertIn('properties={"alternatives": [_VALUE_STR + l for l in ["R"]] if _FULL in _VALUE else []}', text)
        self.assertIn('"X7R": (218.15, 398.15),  # op_temp_x7r', text)
        self.assertIn('"C0G": (218.15, 423.15),  # op_temp_c0g', text)
        self.assertIn("part_orderable", text)
        self.assertIn('"vr": rated_v.value, "derate": derate}, "error")', text)
        self.assertIn("# UNCHECKED: self_heating [parts CSER1-X104K]", text)
        self.assertNotIn("# UNCHECKED: op_temp", text)  # ambient rows are checks

    def test_duplicate_wrapper_key_is_a_problem(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, cat=[("CSER1-X104M,X7R,0.1μF,±20%", "CSER1-X104N,X7R,0.1μF,±10%")])
            self.assertTrue(any("share" in p for p in generate(copy)[1]))

    def test_ambient_waiver_is_a_problem(self):
        with tempfile.TemporaryDirectory() as d:
            copy = edited(d, toml=[('name = "Operating temperature, X7R"\nkind = "rec_op"\nscope = "na"', 'name = "Operating temperature, X7R"\nkind = "rec_op"\nscope = "25C"')])
            self.assertTrue(any("must be an error-severity" in p for p in generate(copy)[1]))

    def test_readme_section(self):
        text = readme.build(FIX)
        self.assertIn("## Series", text)
        self.assertIn("- **Catalog**: `catalog.csv`, 6 orderable values", text)
        self.assertIn("default `T`, alternates `R`", text)
        self.assertIn("| C0G | 2 | 1.5 pF to 100 pF | 50 V, 100 V |", text)
        self.assertIn("Applies to: dielectric X7R.", text)
        self.assertIn("Applies to: parts CSER1-X104K.", text)
        self.assertIn("from the catalog part selection", text)  # INPUTS keys supplied by the selection


# (case name, config overrides, expected: "pass" | "error" | "warning", text that must appear)
CASES = [
    ("nominal", [], "pass", ""),
    ("rated_out", ["va=17V"], "error", "rated_voltage: up to 17.0 V"),
    ("derated_out", ["va=12V", "derate=0.7"], "error", "rated_voltage"),  # 12 V > 0.7 x 16 V
    ("reversed_out", ["va=0V", "vb=17V"], "error", "rated_voltage"),
    ("tolerance_needed", ["rated=50V"], "error", "part_orderable"),  # +/-10 % and +/-20 % are both listed
    ("tolerance_given", ["rated=50V", "tolerance=+/-20%", "va=5V"], "pass", ""),
    ("absolute_tolerance", ["value=1.5pF", "rated=50V", "dielectric=C0G", "va=5V"], "pass", ""),  # +/-0.25 pF
    ("printed_voltage", ["value=6.8nF", "rated=1000V", "va=900V"], "pass", ""),  # "6,800pF", "1,000Vdc"
    ("not_listed", ["value=0.11uF"], "error", "part_orderable"),
    ("c0g_not_listed_at_that_value", ["dielectric=C0G"], "error", "part_orderable"),
    ("p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("x7r_ambient_out", ["ta=-40°C to 140°C"], "error", "ambient_range"),  # X7R limit 125 degC
    ("c0g_ambient_ok", ["value=100pF", "rated=100V", "dielectric=C0G", "va=5V", "ta=-40°C to 140°C"], "pass", ""),  # C0G limit 150
    ("c0g_ambient_out", ["value=100pF", "rated=100V", "dielectric=C0G", "va=5V", "ta=-40°C to 160°C"], "error", "ambient_range"),
    ("ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ambient_range"),
]


@unittest.skipUnless(shutil.which("pcb"), "pcb not installed")
class TestBuild(unittest.TestCase):
    """Build the fixture wrapper in its own workspace (the fixture is not under components/)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / "pcb.toml").write_text('[workspace]\npcb-version = "0.4"\n')
        cls.dir = root / "CSER1"
        copytree(FIX, cls.dir)
        text, problems = generate(cls.dir)
        assert not problems, problems
        (cls.dir / "CSER1.zen").write_text(text)
        (cls.dir / "pcb.toml").write_text("")
        subprocess.run(["pcb", "fmt", str(cls.dir)], check=True, capture_output=True)
        shutil.copy(Path(__file__).parent / "zen" / "Capacitor_harness.zen", cls.dir / "_harness.zen")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def build(self, *args):
        r = subprocess.run(["pcb", "build", "-Wstyle", "-Dwarnings", *args], capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_wrapper_builds_standalone(self):
        rc, out = self.build(str(self.dir / "CSER1.zen"))
        self.assertEqual(rc, 0, out)

    def test_harness_cases(self):
        from tests.test_zen import outcome
        for name, overrides, expect, text in CASES:
            rc, out = self.build(str(self.dir / "_harness.zen"), *[f"--config={c}" for c in overrides])
            with self.subTest(case=name):
                self.assertEqual(outcome(rc, out), expect, out)
                self.assertIn(text, out)


if __name__ == "__main__":
    unittest.main()
