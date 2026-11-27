"""lib.catalog.export_check: a committed catalog.csv against the manufacturer export it cites (docs/spec/capacitor.md
"Export check"). Tiny synthetic export and catalog, so the tests run offline."""

import csv
import os
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from lib import catalog as C
from lib import check as K

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


# Printed forms of the export's "Tolerance of capacitance" column for each letter of C.TOLERANCE (a small inline fixture).
PRINTED_TOLERANCE = {"W": ["±0.05pF", "+/-0.05pF", "± 0.05 pF"], "B": ["±0.1pF"], "C": ["±0.25pF"], "D": ["±0.5pF"],
                     "F": ["±1%"], "G": ["±2%", "+/-2 %"], "J": ["±5%"], "K": ["±10%"], "M": ["±20%"], "R": ["±2.5%"]}


class ToleranceLetterTests(unittest.TestCase):
    def test_fixture_covers_every_letter_in_the_table(self):
        self.assertEqual(set(PRINTED_TOLERANCE), set(C.TOLERANCE), "add the printed forms of a new letter here")

    def test_every_letter_decodes_every_printed_form(self):
        for letter, forms in PRINTED_TOLERANCE.items():
            for printed in forms:
                row = {"Part Number": f"GCM21B5C1H183{letter}A16#", "Temperature characteristics": "C0G",
                       "Capacitance": "18,000pF", "Tolerance of capacitance": printed, "Rated Voltage DC": "50Vdc",
                       "Thickness": "1.25mm ±0.15mm"}
                self.assertEqual(C.decode(row, offline=True), [], f"{letter} {printed}")

    def test_wrong_and_one_sided_printed_forms_are_reported(self):
        base = {"Part Number": "GCM21B5C1H183KA16#", "Temperature characteristics": "C0G", "Capacitance": "18,000pF",
                "Tolerance of capacitance": "±5%", "Rated Voltage DC": "50Vdc", "Thickness": "1.25mm ±0.15mm"}
        self.assertTrue(C.decode(base, offline=True))  # K is +/-10 %, the export says +/-5 %
        one_sided = dict(base, **{"Part Number": "GCM21B5C1H183ZA16#", "Tolerance of capacitance": "+80%/-20%"})
        self.assertTrue(C.decode(one_sided, offline=True))  # a one-sided letter not in the table is never silently accepted


class RecordTests(unittest.TestCase):
    """review/export_check.toml, its human stamps, and the lib.check rules (docs/spec/capacitor.md "Export check")."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.folder = self.tmp / "GCM21B"
        self.folder.mkdir()
        (self.folder / "component.toml").write_text(TOML)
        self.export = self.tmp / "export.csv"
        write_export(self.export, EXPORT_ROWS)
        write_catalog(self.folder / "catalog.csv", CATALOG)
        self.record = self.folder / "review" / "export_check.toml"
        env = mock.patch.dict(os.environ)  # stamping is refused under CLAUDECODE: clear it for these tests only
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_cmd(self, *args):
        return C.main(["export-check", *args, str(self.export), str(self.folder)])

    def test_match_writes_machine_record_without_login(self):
        self.assertEqual(self.run_cmd(), 0)
        text = self.record.read_text()
        self.assertIn('[group.C0G]', text)
        rec = tomllib.loads(text)
        self.assertEqual(rec["tables_sha256"], C.tables_sha256())
        for d, g in rec["group"].items():
            self.assertRegex(g["verified"], rf"^machine export-check \d{{4}}-\d{{2}}-\d{{2}} {g['group_sha256'][:12]}$")
            self.assertNotIn("spot_check", g)
        self.assertNotIn("human:", text)
        self.assertEqual(K.check_export_record(self.folder), [])

    def test_stamp_writes_human_line_per_group(self):
        self.assertEqual(self.run_cmd("--stamp", "reviewer-1"), 0)
        text = self.record.read_text()
        self.assertIn('verified = "human:reviewer-1 ', text)
        self.assertIn("export-check group C0G", text)
        self.assertIn("export-check group X7R", text)

    def test_mismatch_writes_nothing(self):
        write_catalog(self.folder / "catalog.csv", CATALOG[1:])
        self.assertEqual(self.run_cmd(), 1)
        self.assertFalse(self.record.exists())

    def test_agents_cannot_stamp(self):
        os.environ["CLAUDECODE"] = "1"  # restored by the patch.dict in setUp
        self.assertEqual(self.run_cmd("--stamp", "reviewer-1"), 1)
        self.assertFalse(self.record.exists())

    def test_bad_login_refused(self):
        self.assertEqual(self.run_cmd("--stamp", "-bad"), 2)

    def test_groups_stamp_only_their_own_and_keep_the_rest(self):
        self.assertEqual(self.run_cmd("--stamp", "reviewer-1", "--groups", "C0G"), 0)
        text = self.record.read_text()
        self.assertIn("export-check group C0G", text)
        self.assertNotIn("export-check group X7R", text)
        self.assertEqual(self.run_cmd("--stamp", "reviewer-2", "--groups", "X7R"), 0)
        text = self.record.read_text()
        self.assertIn("human:reviewer-1 ", text)  # C0G's stamp kept
        self.assertIn("human:reviewer-2 ", text)
        self.assertEqual(self.run_cmd(), 0)  # a machine-only rerun keeps both stamps
        self.assertEqual(self.record.read_text().count('verified = "human:'), 2)

    def test_changed_catalog_drops_stamps(self):
        self.run_cmd("--stamp", "reviewer-1")
        extra_export = EXPORT_ROWS + [("GCM21B5C1H223FA16#", "In Production", "C0G", "22,000pF", "±1%", "50Vdc")]
        write_export(self.export, extra_export)
        write_catalog(self.folder / "catalog.csv", CATALOG + [
            ("GCM21B5C1H223FA16", "C0G", "22,000pF", "±1%", "50Vdc", "1.25mm ±0.15mm")])
        self.assertEqual(self.run_cmd(), 0)  # a new, matching catalog and export: new hashes
        text = self.record.read_text()
        self.assertIn("GCM21B5C1H223FA16", self.folder.joinpath("catalog.csv").read_text())
        rec = tomllib.loads(text)
        self.assertTrue(rec["group"]["C0G"]["verified"].startswith("machine export-check "))  # changed group: no human line
        self.assertTrue(rec["group"]["X7R"]["verified"].startswith("human:reviewer-1 "))  # unchanged group keeps its line

    def test_groups_must_exist(self):
        self.assertEqual(self.run_cmd("--stamp", "reviewer-1", "--groups", "NP0"), 2)
        self.assertFalse(self.record.exists())

    def test_stamp_date_feeds_verified_only_when_stamped_and_current(self):
        from lib.capacitor import export_stamp_date
        catalog_path = self.folder / "catalog.csv"
        self.assertIsNone(export_stamp_date(self.folder, catalog_path, "C0G"))  # no record
        self.run_cmd()
        self.assertRegex(export_stamp_date(self.folder, catalog_path, "C0G"), r"^\d{4}-\d{2}-\d{2}$")  # machine line
        self.run_cmd("--stamp", "reviewer-1")
        day = export_stamp_date(self.folder, catalog_path, "C0G")
        self.assertRegex(day, r"^\d{4}-\d{2}-\d{2}$")
        self.assertIsNone(export_stamp_date(self.folder, catalog_path, "NP0"))  # no such group
        rows = list(CATALOG)
        rows[0] = ("GCM21B5C1H183FA16", "C0G", "18,000pF", "±2%", "50Vdc", "1.25mm ±0.15mm")
        write_catalog(catalog_path, rows)
        self.assertIsNone(export_stamp_date(self.folder, catalog_path, "C0G"))  # catalog changed: stale

    def test_lib_check_accepts_fresh_record(self):
        self.run_cmd("--stamp", "reviewer-1")
        self.assertEqual(K.check_export_record(self.folder), [])

    def test_lib_check_flags_stale_catalog(self):
        self.run_cmd("--stamp", "reviewer-1")
        rows = list(CATALOG)
        rows[0] = ("GCM21B5C1H183FA16", "C0G", "18,000pF", "±2%", "50Vdc", "1.25mm ±0.15mm")
        write_catalog(self.folder / "catalog.csv", rows)
        out = K.check_export_record(self.folder)
        self.assertTrue(any("STALE" in m for _, m in out), out)

    def test_lib_check_flags_bad_stamp(self):
        self.run_cmd("--stamp", "reviewer-1")
        text = self.record.read_text().replace("export-check group C0G", "export-check group X7R", 1)
        self.record.write_text(text)
        out = K.check_export_record(self.folder)
        self.assertTrue(any("verified is not a human or machine export-check line" in m for _, m in out), out)

    def machine_lines(self):
        return {d: g["verified"] for d, g in tomllib.loads(self.record.read_text())["group"].items()}

    def test_tampered_group_hash_is_flagged(self):
        self.run_cmd()
        rec = tomllib.loads(self.record.read_text())
        old = rec["group"]["C0G"]["group_sha256"]
        self.record.write_text(self.record.read_text().replace(old, "0" * 64))
        out = K.check_export_record(self.folder)
        self.assertTrue(any("is not the group's group_sha256" in m for _, m in out), out)

    def test_malformed_machine_line_is_flagged(self):
        self.run_cmd()
        text = self.record.read_text().replace("machine export-check", "machine export-chek", 1)
        self.record.write_text(text)
        out = K.check_export_record(self.folder)
        self.assertTrue(any("verified is not a human or machine" in m for _, m in out), out)

    def test_stale_catalog_hash_flagged_for_machine_record(self):
        self.run_cmd()
        rows = list(CATALOG)
        rows[0] = ("GCM21B5C1H183FA16", "C0G", "18,000pF", "±2%", "50Vdc", "1.25mm ±0.15mm")
        write_catalog(self.folder / "catalog.csv", rows)
        out = K.check_export_record(self.folder)
        self.assertTrue(any("STALE" in m and "catalog.csv changed" in m for _, m in out), out)
        from lib.capacitor import current_groups
        self.assertEqual(current_groups(self.folder, self.folder / "catalog.csv"), {})

    def test_stale_tables_hash_is_flagged_and_not_current(self):
        from lib.capacitor import current_groups
        self.run_cmd()
        self.assertEqual(set(current_groups(self.folder, self.folder / "catalog.csv")), {"C0G", "X7R"})
        with mock.patch.dict(C.TOLERANCE, {"Z": "+/-99%"}):  # a table edit changes the tables hash
            out = K.check_export_record(self.folder)
            self.assertTrue(any("STALE" in m and "decode tables" in m for _, m in out), out)
            self.assertEqual(current_groups(self.folder, self.folder / "catalog.csv"), {})
            self.assertEqual(self.run_cmd(), 0)  # a rerun records the new tables hash
            self.assertEqual(K.check_export_record(self.folder), [])

    def test_mixed_record_works(self):
        from lib.capacitor import current_groups
        self.run_cmd("--stamp", "reviewer-1", "--groups", "C0G")
        lines = self.machine_lines()
        self.assertTrue(lines["C0G"].startswith("human:reviewer-1 "))
        self.assertTrue(lines["X7R"].startswith("machine export-check "))
        self.assertEqual(K.check_export_record(self.folder), [])
        got = current_groups(self.folder, self.folder / "catalog.csv")
        self.assertEqual((got["C0G"]["kind"], got["X7R"]["kind"]), ("human", "machine"))

    def test_human_line_kept_when_group_unchanged_dropped_when_changed(self):
        self.run_cmd("--stamp", "reviewer-1")
        write_export(self.export, EXPORT_ROWS + [("GCM21B5C1H223FA16#", "In Production", "C0G", "22,000pF", "±1%", "50Vdc")])
        write_catalog(self.folder / "catalog.csv", CATALOG + [
            ("GCM21B5C1H223FA16", "C0G", "22,000pF", "±1%", "50Vdc", "1.25mm ±0.15mm")])
        self.run_cmd()
        lines = self.machine_lines()
        self.assertTrue(lines["X7R"].startswith("human:reviewer-1 "))  # still valid: kept, not turned into a machine line
        self.assertTrue(lines["C0G"].startswith("machine export-check "))
        self.assertFalse(any(v.startswith("human:") for d, v in lines.items() if d == "C0G"))

    def test_human_only_record_passes_with_changed_tables_hash(self):
        self.run_cmd("--stamp", "reviewer-1")
        text = self.record.read_text()
        text = "\n".join(l for l in text.splitlines() if not l.startswith("tables_sha256")) + "\n"
        self.record.write_text(text.replace("[export]", 'tables_sha256 = "' + "0" * 64 + '"\n\n[export]', 1))
        self.assertEqual(K.check_export_record(self.folder), [])  # human lines ignore the tables hash

    def test_group_rows_must_equal_catalog_count(self):
        self.run_cmd()
        text = self.record.read_text().replace("rows = 3", "rows = 4", 1)
        self.record.write_text(text)
        out = K.check_export_record(self.folder)
        self.assertTrue(any("rows = 4 but catalog.csv has 3 C0G rows" in m for _, m in out), out)

    def test_group_must_be_a_catalog_dielectric(self):
        self.run_cmd()
        self.record.write_text(self.record.read_text() + '\n[group.NP0]\nrows = 1\ngroup_sha256 = "' + "0" * 64 + '"\n')
        out = K.check_export_record(self.folder)
        self.assertTrue(any("group NP0: no row of catalog.csv has dielectric NP0" in m for _, m in out), out)

    def test_stray_review_file_is_flagged_but_record_is_not(self):
        self.run_cmd()
        (self.folder / "review" / "notes.txt").write_text("x")
        flagged = [m for _, m in K.stray_review_files(self.folder)]
        self.assertEqual(len(flagged), 1)
        self.assertIn("notes.txt", flagged[0])


if __name__ == "__main__":
    unittest.main()
