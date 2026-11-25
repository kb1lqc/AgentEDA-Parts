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
        for prm in selection_params(row, "2026-11-24"):  # the date of the group's human export-check stamp
            self.assertRegex(prm.verified, rules.VERIFIED_RE)
            self.assertTrue(prm.verified.startswith("manufacturer-export 2026-11-24 "))
        for prm in selection_params(row):  # no stamp: unverified, whatever the cite says
            self.assertIsNone(prm.verified)

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


class LedgerStale(unittest.TestCase):
    def setUp(self):
        lib.reset_inputs()
        self.addCleanup(lib.reset_inputs)

    def make(self, d, state):
        copy = Path(d) / "LDO1"
        shutil.copytree(ROOT / "tests" / "fixtures" / "Acme" / "LDO1", copy)
        t = copy / "component.toml"
        t.write_text(t.read_text().replace('cite = "DS p.5, Electrical Characteristics, VREF"',
                                           'cite = "DS p.5, Electrical Characteristics, VREF"\nverified = "bob 2026-01-01 page image"'))
        (copy / "review").mkdir()
        (copy / "review" / "review.toml").write_text(f'[inputs]\npdf_sha256 = "x"\n[row.vref]\nstate = "{state}"\nimage = ""\nimage_sha256 = ""\n')
        return copy

    def test_stale_and_pdf_changed_count_unverified(self):
        for state, bad in (("STALE", True), ("PDF_CHANGED", True), ("MACHINE_CHECKED", False)):
            lib.reset_inputs()
            with tempfile.TemporaryDirectory() as d:
                lib.load(str(self.make(d, state))).param("vref")
            self.assertEqual(lib.unverified_inputs(), ["LDO1:vref"] if bad else [], state)

    def test_no_ledger_no_effect(self):
        with tempfile.TemporaryDirectory() as d:
            copy = self.make(d, "STALE")
            shutil.rmtree(copy / "review")
            lib.load(str(copy)).param("vref")
        self.assertEqual(lib.unverified_inputs(), [])


class HumanReview(unittest.TestCase):
    """lib.human_review_needed: a row is human-checked only with a `human:` stamp and a ledger state that is not bad."""

    def setUp(self):
        lib.reset_inputs()
        self.addCleanup(lib.reset_inputs)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name) / "LDO1"
        shutil.copytree(ROOT / "tests" / "fixtures" / "Acme" / "LDO1", self.d, ignore=shutil.ignore_patterns("__pycache__"))

    def stamp(self, key_cite, stamp):
        t = self.d / "component.toml"
        t.write_text(t.read_text().replace(key_cite, f'{key_cite}\nverified = "{stamp}"', 1))

    def ledger(self, **states):
        (self.d / "review").mkdir(exist_ok=True)
        rows = "".join(f'[row.{k}]\nstate = "{v}"\nimage = ""\nimage_sha256 = ""\n' for k, v in states.items())
        (self.d / "review" / "review.toml").write_text('[inputs]\npdf_sha256 = "x"\n' + rows)

    def test_reasons(self):
        self.stamp('cite = "DS p.5, Electrical Characteristics, VREF"', "human:bob 2026-11-20 page-image ds_review abc")
        self.stamp('cite = "DS p.5, Electrical Characteristics, VOS"', "sonnet-audit 2026-11-18 blind reading")
        self.stamp('cite = "DS p.4, Absolute Maximum Ratings, VIN"', "bob 2026-11-20 page-image ds_review abc")
        p = lib.load(str(self.d))
        for k in ("vref", "vos", "vin_abs", "gain_err"):
            p.param(k)
        got = {e["key"]: e["reason"] for e in lib.human_review_needed()}
        # vref: human prefix without the row-hash binding -> malformed; a who without the prefix is a machine stamp
        self.assertEqual(got, {"vref": "human stamp: malformed", "vos": "machine stamp", "vin_abs": "machine stamp",
                               "gain_err": "no stamp"})
        e = next(e for e in lib.human_review_needed() if e["key"] == "gain_err")
        self.assertEqual((e["input"], e["value"], e["dir"], e["ref"], e["review_key"], e["state"]),
                         ("LDO1:gain_err", "LDO1", str(self.d), "LDO1:gain_err", "gain_err", None))
        self.assertTrue(e["cite"].startswith("DS p."))
        lib.reset_inputs()
        self.assertEqual(lib.human_review_needed(), [])

    def test_bad_ledger_state_overrides_human_stamp(self):
        self.stamp('cite = "DS p.5, Electrical Characteristics, VREF"', "human:bob 2026-11-20 page-image ds_review abc")
        for state, want in (("STALE", "STALE"), ("PDF_CHANGED", "PDF_CHANGED"), ("HUMAN_VERIFIED", "human stamp: malformed")):
            lib.reset_inputs()
            self.ledger(vref=state)
            lib.load(str(self.d)).param("vref")
            self.assertEqual([e["reason"] for e in lib.human_review_needed()], [want], state)

    def test_sticky(self):
        p = lib.load(str(self.d))
        p.param("vref")
        import dataclasses
        q = dataclasses.replace(p, params={**p.params, "vref": dataclasses.replace(p.params["vref"], verified="human:x 2026-11-20 y")})
        q.param("vref")
        self.assertEqual([e["reason"] for e in lib.human_review_needed()], ["no stamp"])

    def test_family_series_and_selection_rows(self):
        # This test reads real components, whose rows people stamp over time. It checks how a row read maps to its
        # review record (review_key, ref), not which rows are still unreviewed: so every `human:` stamp is read as
        # absent here, and a newly human-checked row cannot make the test fail.
        from unittest import mock
        import lib.component as comp
        real = comp._review

        def unstamped(path, review_key, stamp, *a, **k):
            return real(path, review_key, None if str(stamp).startswith("human:") else stamp, *a, **k)

        patcher = mock.patch.object(comp, "_review", unstamped)
        patcher.start()
        self.addCleanup(patcher.stop)
        f = lib.load("AnalogDevices/LTC4364MS", variant="LTC4364CMS-1")
        f.param("dvsns_0c125c")  # variants.toml override: its own review row, not the shared one
        f.param("abs_vcc")
        c = lib.load("Murata/GCM188")
        x7r = next(r for r in c.catalog() if r.dielectric == "X7R")
        sel = c.select(x7r.capacitance, x7r.rated_voltage, "X7R", x7r.tolerance)
        sel.part.param("tc")
        sel.part.param("tolerance")
        lib.load("Vishay/WSK2512").tcr(10e-3)
        rows = {r["input"]: r for r in lib.human_review_needed()}
        ov = rows["LTC4364CMS-1:dvsns_0c125c"]
        self.assertEqual((ov["review_key"], ov["ref"]), ("variant.LTC4364CMS-1.dvsns_0c125c", None))
        self.assertEqual(rows["LTC4364CMS-1:abs_vcc"]["ref"], "LTC4364MS:abs_vcc")
        cap = rows[f"GCM188[{x7r.value}]:capacitance"]
        self.assertEqual((cap["review_key"], cap["ref"], cap["reason"]), (None, None, "no stamp"))  # no export-check stamp yet
        self.assertEqual(rows[f"GCM188[{x7r.value}]:tc_x7r"]["ref"], "GCM188:tc_x7r")
        self.assertEqual(rows[f"GCM188[{x7r.value}]:tolerance"]["review_key"], None)  # catalog row, not a TOML row
        self.assertEqual(rows["WSK2512:tcr_5m_200m"]["ref"], "WSK2512:tcr_5m_200m")
        self.assertEqual(set(rows) - set(lib.used_inputs()), set())


if __name__ == "__main__":
    unittest.main()
