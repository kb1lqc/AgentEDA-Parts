"""tools/review.py catalog groups: the page model, the group section, and the stamp path (publish runs lib.catalog
export-check --stamp --groups, not stamp.py). A synthetic library in a temp dir; the commands are fake (no git, no gh)."""

import csv
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

import review as R  # noqa: E402
from lib import catalog as CAT  # noqa: E402

from tests.test_catalog_export import CATALOG, EXPORT_ROWS, TOML, write_catalog, write_export  # noqa: E402


class GroupsTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ)  # stamping is refused under CLAUDECODE: clear it for these tests only
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("CLAUDECODE", None)
        self.root = Path(tempfile.mkdtemp())
        (self.root / "docs" / "datasheets").mkdir(parents=True)
        self.export = self.root / "docs" / "datasheets" / "export.csv"  # the name the test catalog's cite gives
        write_export(self.export, EXPORT_ROWS)
        self.folder = self.root / "components" / "Murata" / "GCM21B"
        self.folder.mkdir(parents=True)
        (self.folder / "component.toml").write_text(
            TOML.replace('catalog = "catalog.csv"', 'catalog = "catalog.csv"\ncatalog_decoder = "murata-gcm"\n'
                         'package_default = "D"\npackage_alternates = ["W"]'))
        write_catalog(self.folder / "catalog.csv", CATALOG)
        self.dirs = [self.folder]

    def tearDown(self):
        shutil.rmtree(self.root)

    def groups(self):
        return R.build_groups(self.root, self.dirs)

    def test_one_entry_per_dielectric_none_tickable(self):
        gs = {g["dielectric"]: g for g in self.groups()}
        self.assertEqual(set(gs), {"C0G", "X7R"})
        self.assertFalse(any(g["tickable"] for g in gs.values()))  # derived rows need no tick
        self.assertEqual(gs["C0G"]["ref"], "GCM21B:group:C0G")
        self.assertEqual(gs["C0G"]["rows"], 3)
        self.assertEqual([r["value"] for r in gs["C0G"]["rows_expected"]],
                         ["GCM21B5C1H183FA16", "GCM21B5C1H183GA16", "GCM21B5C1H203JA16"])  # every part, in value order

    def test_fields_decode_one_part(self):
        fields = {label: (code, meaning) for label, code, meaning in CAT.fields_of("GCM21BR70J106KE22")}
        self.assertEqual(fields["Dielectric"], ("R7", "X7R"))
        self.assertEqual(fields["Voltage"], ("0J", "6.3 V"))
        self.assertEqual(fields["Capacitance"], ("106", "10 µF"))
        self.assertEqual(fields["Tolerance"], ("K", "+/-10%"))
        self.assertEqual(fields["Thickness"], ("B", "1.25 mm"))
        self.assertIsNone(CAT.fields_of("not-a-part"))

    def test_legend_lists_only_codes_in_the_group(self):
        g = next(g for g in self.groups() if g["dielectric"] == "C0G")
        legend = R.legend_html(g["rows_expected"])
        self.assertIn("5C = C0G", legend)
        self.assertNotIn("R7 = X7R", legend)
        self.assertIn("183 = 18 nF", legend)  # 18 x 10^3 pF

    def test_group_html_is_one_line_with_no_tick_box(self):
        g = next(g for g in self.groups() if g["dielectric"] == "X7R")
        html_text = R.group_html(g)
        self.assertIn("No tick needed", html_text)
        self.assertNotIn("<input", html_text)

    def test_stamped_group_is_not_tickable(self):
        CAT.main(["export-check", str(self.export), str(self.folder), "--stamp", "reviewer", "--groups", "C0G"])
        gs = {g["dielectric"]: g for g in self.groups()}
        self.assertIsNotNone(gs["C0G"]["stamp"])
        self.assertFalse(gs["C0G"]["tickable"])
        self.assertFalse(gs["X7R"]["tickable"])  # a machine line was written for the group not stamped
        self.assertNotIn('value="GCM21B:group:C0G"', R.group_html(gs["C0G"]))

    def test_machine_group_is_derived_checked_and_not_tickable(self):
        CAT.main(["export-check", str(self.export), str(self.folder)])
        self.assertEqual(len(self.groups()), 2)
        gs = {g["dielectric"]: g for g in self.groups()}
        for g in gs.values():
            self.assertFalse(g["tickable"])
            text = R.group_html(g)
            self.assertIn("derived, checked", text)
            self.assertNotIn('class="ok"', text)
            self.assertNotIn("Ticked by", text)

    def test_missing_export_is_a_visible_group_not_a_tick(self):
        self.export.unlink()
        gs = self.groups()
        self.assertEqual(gs[0]["result"], "NO EXPORT")
        self.assertFalse(gs[0]["tickable"])
        self.assertIn("export-check record", R.group_html(gs[0]))

    def test_publish_stamps_only_the_ticked_group(self):
        commands = []
        status_calls = {"n": 0}

        def fake_run(cmd):
            commands.append(cmd)
            if cmd[:3] == ["git", "status", "--porcelain"]:
                status_calls["n"] += 1
                return 0, ("" if status_calls["n"] == 1 else
                           " M components/Murata/GCM21B/review/export_check.toml\n")
            if cmd[:3] == ["git", "rev-parse", "--abbrev-ref"]:
                return 0, "main\n"
            if cmd[:2] == ["gh", "api"]:
                return 0, "reviewer\n"
            if cmd[:3] == ["gh", "pr", "create"]:
                return 0, "https://github.com/o/r/pull/9\n"
            return 0, ""

        messages = []
        rc = R.publish(self.root, self.dirs, ["GCM21B:group:X7R"], fake_run, lambda *a: messages.extend(a),
                       today=date(2026, 11, 24), python="python3", groups={g["ref"]: g for g in self.groups()})
        self.assertEqual(rc, 0, messages)
        stamps = [c for c in commands if "lib.catalog" in c]
        self.assertEqual(len(stamps), 1)
        self.assertEqual(stamps[0][-4:], ["--stamp", "reviewer", "--groups", "X7R"])
        self.assertFalse(any("tools/stamp.py" in c for c in commands))
        self.assertTrue(any(c[:2] == ["git", "add"] and "components/Murata/GCM21B/review/export_check.toml" in c
                            for c in commands), commands)


if __name__ == "__main__":
    unittest.main()
