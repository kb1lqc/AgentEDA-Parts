"""verified field: loader, the used/unverified input record, and the lib.check format rule."""

import shutil
import tempfile
import unittest
from pathlib import Path

import lib
from lib import rules
from lib.check import check_component

ROOT = Path(__file__).resolve().parent.parent


class Verified(unittest.TestCase):
    def setUp(self):
        lib.reset_inputs()
        self.addCleanup(lib.reset_inputs)

    def test_loaded_and_recorded(self):
        p = lib.load("TexasInstruments/TPS48000QDGXQ1")
        key = next(k for k, v in p.params.items() if v.verified)
        self.assertRegex(p.param(key).verified, rules.VERIFIED_RE)
        self.assertEqual(lib.used_inputs(), [f"TPS48000QDGXQ1:{key}"])
        self.assertEqual(lib.unverified_inputs(), [])

    def test_unverified_row_is_listed(self):
        p = lib.load("TexasInstruments/TPS48000QDGXQ1")
        key = next(k for k, v in p.params.items() if not v.verified)
        p.param(key)
        self.assertEqual(lib.unverified_inputs(), [f"TPS48000QDGXQ1:{key}"])
        lib.reset_inputs()
        self.assertEqual(lib.unverified_inputs(), [])

    def test_inputs_and_series_record(self):
        w = lib.load("Vishay/WSK2512")
        w.inputs("resistance_worst")  # tcr, aging, aging_abs rows
        used = {"WSK2512:tcr_5m_200m", "WSK2512:perf_load_life", "WSK2512:perf_offset_ohm"}
        self.assertEqual(set(lib.used_inputs()), used)
        self.assertEqual(lib.unverified_inputs(), sorted(k for k in used if not w.params[k.split(":")[1]].verified))
        lib.reset_inputs()
        w.series("no_such_prefix")
        self.assertEqual(lib.used_inputs(), [])

    def test_catalog_rows_stamped_as_export(self):
        c = lib.load("Murata/GCM188")
        row = c.catalog()[0]
        from lib.capacitor import selection_params
        for prm in selection_params(row):
            self.assertRegex(prm.verified, rules.VERIFIED_RE)
            self.assertTrue(prm.verified.startswith("manufacturer-export 2026-11-14 "))
        nodate = row.__class__(**{**row.__dict__, "source": "hand typed"}) if hasattr(row, "__dict__") else None
        if nodate is not None:
            self.assertIsNone(selection_params(nodate)[0].verified)

    def test_verdict_and_section(self):
        p = lib.load("TexasInstruments/TPS48000QDGXQ1")
        self.assertEqual(lib.verdict(False), "FAIL")
        p.param(next(k for k, v in p.params.items() if v.verified))
        self.assertEqual(lib.verdict(True), "PASS")
        self.assertIn("every one carries", "\n".join(lib.inputs_section()))
        bad = next(k for k, v in p.params.items() if not v.verified)
        p.param(bad)
        self.assertEqual(lib.verdict(True), "PASS (UNVERIFIED INPUTS)")
        self.assertIn(f"- `TPS48000QDGXQ1:{bad}`", lib.inputs_section())

    def test_unverified_is_sticky(self):
        p = lib.load("TexasInstruments/TPS48000QDGXQ1")
        key = next(k for k, v in p.params.items() if not v.verified)
        p.param(key)
        import dataclasses
        stamped = dataclasses.replace(p.params[key], verified="x 2026-11-18 test")
        q = dataclasses.replace(p, params={**p.params, key: stamped})
        q.param(key)  # a later verified read of the same key
        self.assertEqual(lib.unverified_inputs(), [f"TPS48000QDGXQ1:{key}"])

    def test_selection_keys_do_not_collide(self):
        c = lib.load("Murata/GCM188")
        rows = c.catalog()
        x7r = next(r for r in rows if r.dielectric == "X7R")
        c0g = next(r for r in rows if r.dielectric == "C0G")
        a = c.select(x7r.capacitance, x7r.rated_voltage, "X7R", x7r.tolerance)
        b = c.select(c0g.capacitance, c0g.rated_voltage, "C0G", c0g.tolerance)
        a.part.param("tc"); b.part.param("tc")
        used = lib.used_inputs()
        for want in (f"GCM188[{x7r.value}]:capacitance", f"GCM188[{x7r.value}]:rated_v", f"GCM188[{x7r.value}]:tc_x7r",
                     f"GCM188[{c0g.value}]:capacitance", f"GCM188[{c0g.value}]:tc_c0g"):
            self.assertIn(want, used)

    def test_format_rule(self):
        good = {"param": {"a": {"verified": "jd 2026-11-20 page image"}}}
        for bad in ("yes", "jd 20261120 page image", "jd 2026-11-20", "jd 2026-13-45 page image"):
            self.assertEqual([f.rule for f in rules.verified_findings({"param": {"a": {"verified": bad}}})],
                             ["verified-format"], bad)
        self.assertEqual(rules.verified_findings(good), [])

    def test_check_flags_a_bad_stamp(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "WSK2512"
            shutil.copytree(ROOT / "components" / "Vishay" / "WSK2512", d)
            toml = d / "component.toml"
            s = toml.read_text()
            i = s.index('verified   = "')
            j = s.index("\n", i)
            toml.write_text(s[:i] + 'verified   = "checked"' + s[j:])
            msgs = [m for _, m in check_component(d)]
            self.assertTrue(any("verified-format" in m for m in msgs), msgs)


if __name__ == "__main__":
    unittest.main()
