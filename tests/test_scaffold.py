"""Tests for tools/scaffold.py: vendor file selection, fail-closed cases, and that a scaffold is rejected by lib.check."""

import re
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import scaffold as sc  # noqa: E402
from lib import check  # noqa: E402


def write(p, text=""):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def vendor(root, value="P1", mods=("fp.kicad_mod",), syms=("s.kicad_sym",), steps=("m.step",)):
    for n in mods:
        write(root / "docs/vendor" / value / "footprints.pretty" / n, "(footprint " + n + ")")
    for n in syms:
        write(root / "docs/vendor" / value / n, "(kicad_symbol_lib " + n + ")")
    for n in steps:
        write(root / "docs/vendor" / value / n, "step " + n)


class TestScaffold(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, mfr="Acme", value="P1"):
        return sc.scaffold(self.root, mfr, value)

    def dest(self, value="P1"):
        return self.root / "components/Acme" / value

    def test_creates_files_and_copies_vendor(self):
        vendor(self.root)
        rc, lines = self.go()
        self.assertEqual(rc, 0, lines)
        d = self.dest()
        self.assertEqual(sorted(p.name for p in d.iterdir()), ["P1.kicad_mod", "P1.kicad_sym", "P1.step", "component.toml", "pcb.toml"])
        self.assertEqual((d / "pcb.toml").read_text(), "")
        self.assertEqual((d / "P1.kicad_sym").read_text(), "(kicad_symbol_lib s.kicad_sym)")
        self.assertIn("step            = \"P1.step\"", (d / "component.toml").read_text())
        self.assertEqual(lines[-1], "scaffold Acme/P1: 5 OK, 0 UNSURE, 0 FAIL")

    def test_n_density_chosen_among_candidates(self):
        vendor(self.root, mods=("a-L.kicad_mod", "a-M.kicad_mod", "a-N.kicad_mod"))
        self.assertEqual(self.go()[0], 0)
        self.assertIn("a-N", (self.dest() / "P1.kicad_mod").read_text())

    def test_unsuffixed_among_l_m_chosen(self):
        vendor(self.root, mods=("a-L.kicad_mod", "a.kicad_mod", "a-M.kicad_mod"))
        self.assertEqual(self.go()[0], 0)
        self.assertIn("(footprint a.kicad_mod)", (self.dest() / "P1.kicad_mod").read_text())

    def test_ambiguous_footprint_fails(self):
        vendor(self.root, mods=("a.kicad_mod", "b.kicad_mod"))
        rc, lines = self.go()
        self.assertEqual(rc, 1)
        self.assertTrue(any(l.startswith("footprint | FAIL | ambiguous") for l in lines))
        self.assertFalse(self.dest().exists())

    def test_ambiguous_symbol_fails(self):
        vendor(self.root, syms=("a.kicad_sym", "b.kicad_sym"))
        self.assertEqual(self.go()[0], 1)

    def test_ambiguous_step_fails(self):
        vendor(self.root, steps=("a.step", "b.stp"))
        self.assertEqual(self.go()[0], 1)

    def test_missing_symbol_fails(self):
        vendor(self.root, syms=())
        rc, lines = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("symbol | FAIL | missing", "\n".join(lines))

    def test_missing_footprint_fails(self):
        vendor(self.root, mods=())
        write(self.root / "docs/vendor/P1/x.txt")
        self.assertEqual(self.go()[0], 1)

    def test_missing_vendor_dir_fails(self):
        rc, lines = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("vendor | FAIL | missing: docs/vendor/P1/", lines[0])

    def test_missing_step_is_unsure_and_none(self):
        vendor(self.root, steps=())
        rc, lines = self.go()
        self.assertEqual(rc, 0)
        self.assertIn("step | UNSURE", "\n".join(lines))
        self.assertEqual(lines[-1], "scaffold Acme/P1: 4 OK, 1 UNSURE, 0 FAIL")
        self.assertIn('step            = "none"', (self.dest() / "component.toml").read_text())

    def test_existing_dir_fails_and_is_untouched(self):
        vendor(self.root)
        write(self.dest() / "component.toml", "keep")
        rc, lines = self.go()
        self.assertEqual(rc, 1)
        self.assertIn("already exists", lines[0])
        self.assertEqual((self.dest() / "component.toml").read_text(), "keep")

    def test_bad_names_fail(self):
        vendor(self.root)
        for mfr, val in (("", "P1"), ("Acme", ""), ("../x", "P1"), ("Acme", ".."), ("a/b", "P1")):
            self.assertEqual(sc.scaffold(self.root, mfr, val)[0], 1, (mfr, val))

    def test_vendor_unused_dir_is_not_read(self):
        vendor(self.root)
        write(self.root / "docs/vendor/P1_unused/x-L.kicad_mod")
        self.assertEqual(self.go()[0], 0)

    def test_template_is_valid_toml_with_every_part_field_empty(self):
        vendor(self.root)
        self.go()
        data = tomllib.loads((self.dest() / "component.toml").read_text())
        for f in check.PART_FIELDS:
            self.assertIn(f, data["part"])
        empty = [f for f in ("value", "mpn", "manufacturer", "description", "category", "package", "datasheet_url",
                             "datasheet_rev", "datasheet_date") if data["part"][f] == ""]
        self.assertEqual(len(empty), 9)
        self.assertEqual(data["pin"], [{"number": "", "name": "", "type": "", "function": "", "cite": ""}])

    def test_scaffold_is_rejected_by_lib_check(self):
        vendor(self.root)
        self.go()
        errors = [m for lvl, m in check.check_component(self.dest()) if lvl == "ERROR"]
        self.assertTrue(errors)
        self.assertTrue(any("value ''" in m for m in errors))

    def test_filling_only_the_part_table_is_still_rejected(self):
        vendor(self.root)
        self.go()
        f = self.dest() / "component.toml"
        text = re.sub(r'^value( +)= ""', r'value\1= "P1"', f.read_text(), flags=re.M)
        f.write_text(text)
        errors = [m for lvl, m in check.check_component(self.dest()) if lvl == "ERROR"]
        self.assertTrue(any("missing 'name'" in m for m in errors), errors)

    def test_deterministic(self):
        vendor(self.root)
        other = tempfile.TemporaryDirectory()
        try:
            vendor(Path(other.name))
            a = sc.scaffold(self.root, "Acme", "P1")
            b = sc.scaffold(Path(other.name), "Acme", "P1")
            self.assertEqual(a, b)
            for n in ("component.toml", "pcb.toml", "P1.kicad_sym", "P1.kicad_mod", "P1.step"):
                self.assertEqual((self.dest() / n).read_bytes(), (Path(other.name) / "components/Acme/P1" / n).read_bytes())
        finally:
            other.cleanup()


if __name__ == "__main__":
    unittest.main()
