"""lib.catalog.export_check: a committed catalog.csv against the manufacturer export it cites (docs/spec/capacitor.md
"Export check"). Tiny synthetic export and catalog, so the tests run offline."""

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from lib import catalog as C

HEADER = ["Operating Temperature", "Part Number", "Product Status", "Length", "Width", "Thickness",
          "Temperature characteristics", "Capacitance", "Tolerance of capacitance", "Rated Voltage DC"]
OPTEMP = "-55～125℃"
EXPORT_ROWS = [
    # part number, status, C0G/X7R, capacitance, tolerance, rated voltage
    ("GCM21B5C1H183FA16#", "In Production", "C0G", "18,000pF", "±1%", "50Vdc"),
    ("GCM21B5C1H183GA16#", "In Production", "C0G", "18,000pF", "±2%", "50Vdc"),
    ("GCM21B5C1H203JA16#", "In Production", "C0G", "20,000pF", "±5%", "50Vdc"),
    ("GCM21B5C1H223JA16#", "Discontinued", "C0G", "22,000pF", "±5%", "50Vdc"),  # not In Production: not expected
    ("GCM21BR71H104KA37#", "In Production", "X7R", "0.1μF", "±10%", "50Vdc"),
]
CATALOG = [  # what the generator writes from EXPORT_ROWS (In Production, C0G and X7R, size 21 thickness B)
    ("GCM21B5C1H183FA16", "C0G", "18,000pF", "±1%", "50Vdc", "1.25mm ±0.15mm"),
    ("GCM21B5C1H183GA16", "C0G", "18,000pF", "±2%", "50Vdc", "1.25mm ±0.15mm"),
    ("GCM21B5C1H203JA16", "C0G", "20,000pF", "±5%", "50Vdc", "1.25mm ±0.15mm"),
    ("GCM21BR71H104KA37", "X7R", "0.1μF", "±10%", "50Vdc", "1.25mm ±0.15mm"),
]
TOML = """[part]
value = "GCM21B"
catalog = "catalog.csv"
tc_param = { X7R = "tc_x7r", C0G = "tc_c0g" }
"""


def write_export(path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["Part Number", "Product Status", "Length", "Width", "Thickness", "Temperature characteristics",
                    "Operating Temperature", "Capacitance", "Tolerance of capacitance", "Rated Voltage DC"])
        for number, status, diel, cap, tol, volt in rows:
            w.writerow([number, status, "2mm ±0.15mm", "1.25mm ±0.15mm", "1.25mm ±0.15mm", diel,
                        OPTEMP, cap, tol, volt])


def write_catalog(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(C.CATALOG_COLUMNS)
        for value, diel, cap, tol, volt, thick in rows:
            w.writerow([value, diel, cap, tol, volt, thick, f"Murata product list export export.csv, row {value}#"])


class ExportCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.folder = self.tmp / "GCM21B"
        self.folder.mkdir()
        (self.folder / "component.toml").write_text(TOML)
        self.export = self.tmp / "export.csv"
        write_export(self.export, EXPORT_ROWS)
        write_catalog(self.folder / "catalog.csv", CATALOG)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def check(self):
        return C.export_check(self.folder, self.export)

    def test_match(self):
        r = self.check()
        self.assertEqual(r["result"], "MATCH", r)
        self.assertEqual(r["rows"], 4)
        self.assertEqual(r["groups"]["C0G"]["rows"], 3)
        self.assertEqual(r["groups"]["X7R"]["rows"], 1)
        self.assertEqual(r["differences"], [])
        self.assertEqual(r["errors"], [])

    def test_changed_field_is_a_difference(self):
        rows = list(CATALOG)
        rows[0] = ("GCM21B5C1H183FA16", "C0G", "18,000pF", "±2%", "50Vdc", "1.25mm ±0.15mm")  # tolerance
        write_catalog(self.folder / "catalog.csv", rows)
        r = self.check()
        self.assertEqual(r["result"], "MISMATCH")
        self.assertTrue(any("GCM21B5C1H183FA16: tolerance" in d for d in r["differences"]), r["differences"])

    def test_missing_catalog_row(self):
        write_catalog(self.folder / "catalog.csv", CATALOG[1:])
        r = self.check()
        self.assertEqual(r["result"], "MISMATCH")
        self.assertIn("GCM21B5C1H183FA16: in the export, missing from catalog.csv", r["differences"])

    def test_extra_catalog_row(self):
        extra = CATALOG + [("GCM21B5C1H223JA16", "C0G", "22,000pF", "±5%", "50Vdc", "1.25mm ±0.15mm")]
        write_catalog(self.folder / "catalog.csv", extra)
        r = self.check()
        self.assertEqual(r["result"], "MISMATCH")
        self.assertTrue(any("GCM21B5C1H223JA16: in catalog.csv" in d for d in r["differences"]), r["differences"])

    def test_discontinued_export_row_must_not_be_in_catalog(self):
        # the discontinued 22 nF part is in the export but not expected: a catalog that has it is a mismatch (checked
        # above); a catalog without it matches, which is the rule the generator applies
        r = self.check()
        self.assertNotIn("GCM21B5C1H223JA16", " ".join(r["differences"]))

    def test_decode_error_is_a_mismatch(self):
        rows = list(EXPORT_ROWS)
        rows[0] = ("GCM21B5C1H183FA16#", "In Production", "C0G", "18,000pF", "±1%", "63Vdc")  # 1H is 50 V
        write_export(self.export, rows)
        r = self.check()
        self.assertEqual(r["result"], "MISMATCH")
        self.assertTrue(r["errors"], r)

    def test_group_hash_changes_with_a_row(self):
        before = self.check()["groups"]["C0G"]["sha256"]
        rows = list(CATALOG)
        rows[1] = ("GCM21B5C1H183GA16", "C0G", "18,000pF", "±2%", "50Vdc", "1.25mm ±1.5mm")  # thickness text
        write_catalog(self.folder / "catalog.csv", rows)
        self.assertNotEqual(before, self.check()["groups"]["C0G"]["sha256"])
        self.assertEqual(self.check()["result"], "MISMATCH")

    def test_group_hash_is_order_independent(self):
        a = C.group_hash([{"value": "A", "x": 1}, {"value": "B", "x": 2}], [])
        b = C.group_hash([{"value": "B", "x": 2}, {"value": "A", "x": 1}], [])
        self.assertEqual(a, b)

    def test_group_hash_covers_the_export_side_too(self):
        a = C.group_hash([{"value": "A", "x": 1}], [{"value": "A", "x": 1}])
        b = C.group_hash([{"value": "A", "x": 2}], [{"value": "A", "x": 1}])
        self.assertNotEqual(a, b)

    def test_cli_exit_codes(self):
        self.assertEqual(C.main(["export-check", str(self.export), str(self.folder)]), 0)
        write_catalog(self.folder / "catalog.csv", CATALOG[1:])
        self.assertEqual(C.main(["export-check", str(self.export), str(self.folder)]), 1)


if __name__ == "__main__":
    unittest.main()
