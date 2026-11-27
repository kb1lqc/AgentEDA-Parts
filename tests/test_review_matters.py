"""Rows that matter (docs/spec/review-view.md rules 1 and 3) on the committed parts: capacitor selection aliases and
mechanical rows."""

import unittest
from pathlib import Path

from lib import review_status as RS
from lib.component import _read_toml

ROOT = Path(__file__).resolve().parent.parent
PARTS = sorted(d for d in (ROOT / "components").glob("*/*") if (d / "component.toml").is_file())


class CapacitorAliases(unittest.TestCase):
    def test_tc_rows_matter_for_every_dielectric(self):
        mat = RS.matters(ROOT / "components/Murata/GCM188", ROOT)
        for key in ("tc_x7r", "tc_c0g"):
            self.assertIn(key, mat)
            self.assertIn("calc.py INPUTS", mat[key])

    def test_used_by_names_the_function(self):
        self.assertIn("capacitance_worst_pct(tc)", RS.used_by(ROOT / "components/Murata/GCM188", "tc_x7r", ROOT))

    def test_tc_is_not_an_uncovered_value(self):
        self.assertNotIn("tc", sum(RS.not_covered(ROOT / "components/Murata/GCM155").values(), []))

    def test_no_input_alias_stays_unresolved(self):
        for d in PARTS:
            part = (_read_toml(d / "component.toml") or {}).get("part") or {}
            if part.get("series") != "capacitor":
                continue
            params = (_read_toml(d / "component.toml") or {}).get("param") or {}
            rows = set((part.get("tc_param") or {}).values())
            self.assertTrue(rows <= set(params), f"{d.name}: tc_param names a missing row")
            self.assertTrue(rows <= RS.matters(d, ROOT).keys(), f"{d.name}: a tc row does not matter")
            left = RS.not_covered(d).get("series", []) + RS.not_covered(d).get("unknown", [])
            self.assertEqual(left, [], f"{d.name}: unresolved INPUTS {left}")


class MechanicalRows(unittest.TestCase):
    def test_assembly_and_mass_rows_are_reference(self):
        mat = RS.matters(ROOT / "components/Murata/GCM188", ROOT)
        for key in ("beam_load", "beam_load_c0g", "solderability", "solderability_c0g"):
            self.assertNotIn(key, mat)
        self.assertNotIn("mass", RS.matters(ROOT / "components/Panasonic/ERA-2AEB", ROOT))
        self.assertNotIn("weight", RS.matters(ROOT / "components/Vishay/WSK2512", ROOT))

    def test_dimension_and_land_rows_still_matter(self):
        for part, keys in (("Murata/GCM188", ("land_a", "length", "dim_g", "thickness_t")),
                           ("Panasonic/ERA-2AEB", ("dim_l", "land_a")), ("Vishay/WSK2512", ("dim_l", "pad_a")),
                           ("STMicroelectronics/STM32H723ZET6", ("mech_a", "mech_n", "mech_theta"))):
            mat = RS.matters(ROOT / "components" / part, ROOT)
            for key in keys:
                self.assertEqual(mat.get(key), ["mechanical"], f"{part}: {key}")

    def test_no_dimension_row_is_dropped_anywhere(self):
        for d in PARTS:
            params = (_read_toml(d / "component.toml") or {}).get("param") or {}
            mat = RS.matters(d, ROOT)
            for key, t in params.items():
                if t.get("kind") == "mechanical" and key not in mat:
                    self.assertTrue(key.startswith(RS.NOT_DIMENSION), f"{d.name}: {key}")


if __name__ == "__main__":
    unittest.main()
