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

    def test_one_entry_per_dielectric_all_tickable_before_stamping(self):
        gs = {g["dielectric"]: g for g in self.groups()}
        self.assertEqual(set(gs), {"C0G", "X7R"})
        self.assertTrue(all(g["tickable"] for g in gs.values()))
        self.assertEqual(gs["C0G"]["ref"], "GCM21B:group:C0G")
        self.assertEqual(gs["C0G"]["rows"], 3)
        self.assertEqual(sum(c[3] for c in gs["C0G"]["combos"]), 3)  # every part is in a combination

    def test_group_html_has_one_tick_box_with_the_group_ref(self):
        g = next(g for g in self.groups() if g["dielectric"] == "X7R")
        html_text = R.group_html(g)
        self.assertIn('value="GCM21B:group:X7R"', html_text)
        self.assertIn("GCM21BR71H104KA37", html_text)  # the example part of the group

    def test_stamped_group_is_not_tickable(self):
        CAT.main(["export-check", str(self.export), str(self.folder), "--stamp", "reviewer", "--groups", "C0G"])
        gs = {g["dielectric"]: g for g in self.groups()}
        self.assertIsNotNone(gs["C0G"]["stamp"])
        self.assertFalse(gs["C0G"]["tickable"])
        self.assertTrue(gs["X7R"]["tickable"])
        self.assertNotIn('value="GCM21B:group:C0G"', R.group_html(gs["C0G"]))
        self.assertIn("Ticked by reviewer", R.group_html(gs["C0G"]))

    def test_missing_export_is_a_visible_group_not_a_tick(self):
        self.export.unlink()
        gs = self.groups()
        self.assertEqual(gs[0]["result"], "NO EXPORT")
        self.assertFalse(gs[0]["tickable"])
        self.assertIn("no export file", R.group_html(gs[0]))

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
