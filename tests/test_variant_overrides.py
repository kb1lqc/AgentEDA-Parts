"""Variant overrides as ledger rows (docs/spec/review.md "Variant overrides"). Temp libraries only; the fake datasheet and fixtures are those of tests/test_ds_review.py."""
import contextlib
import io
import os
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
import stamp as S  # noqa: E402
from lib import check, review_status  # noqa: E402
from test_check_stamps import AL, BOB, Repo  # noqa: E402
from test_ds_review import BODY, COMP, Base  # noqa: E402

OVERRIDES = '''[variant."X1"]
mpn = "X1"

[variant."X1".param.vos]
name = "n vos"
symbol = "VOS"
kind = "electrical"
scope = "25C"
unit = "uV"
conditions = ""
cite = "DS p.2, 6.5 Electrical Characteristics, x"
typ = 10
max = 35

[variant."X1".param.iq]
name = "n iq"
symbol = "IQ"
kind = "electrical"
scope = "25C"
unit = "mA"
conditions = ""
cite = "DS p.2, 6.5 Electrical Characteristics, x"
typ = 1.2
max = 2
'''
CALC = '"""calc."""\nINPUTS = {"f": {"v": "vos"}}\n\n\ndef f(v):\n    """Double v."""\n    return 2 * v\n\n\ndef _h():\n    return 1\n'
KEY, REFKEY = "variant.X1.vos", "variant.X1.iq"
DAY = __import__("datetime").date(2026, 11, 27)


def no_agent(test):
    patcher = mock.patch.dict(os.environ)
    patcher.start()
    test.addCleanup(patcher.stop)
    os.environ.pop("CLAUDECODE", None)


class Family(Base):
    """X is a family part: variants.toml overrides vos (used by an example, so it matters) and iq (does not)."""

    def setUp(self):
        super().setUp()
        (self.root / COMP / "variants.toml").write_text(OVERRIDES)
        (self.root / "examples").mkdir()
        (self.root / "examples" / "use.py").write_text('# X\nrow = "vos"\n')
        rc, out = self.run_r()
        self.assertEqual(rc, 0, out)
        self.d = self.root / COMP

    def vtext(self):
        return (self.d / "variants.toml").read_text()


class Overrides(Family):
    def test_matter_override_is_a_full_row_and_other_is_reference(self):
        r = self.rows()
        self.assertEqual(r[KEY]["state"], "NEW")
        self.assertTrue(r[KEY]["image"].startswith("evidence/variant.X1.vos_p"), r[KEY]["image"])  # its own cite's page image
        self.assertEqual(r[KEY]["pdf_page"], 2)
        self.assertEqual(r[REFKEY]["state"], "REFERENCE")
        self.assertNotIn("image", r[REFKEY])
        self.assertIn(KEY, review_status.matters(self.d, self.root))
        self.assertNotIn(REFKEY, review_status.matters(self.d, self.root))
        self.assertEqual(review_status.not_covered(self.d), {})  # no override is listed as not covered
        self.assertEqual([m for lvl, m in check.check_ledger(self.d) if lvl == "ERROR"], [])

    def test_stamp_writes_verified_under_the_quoted_header_and_counts(self):
        no_agent(self)
        rc, out = S.stamp(self.root, "alice", [f"X:{KEY}"], today=DAY)
        self.assertEqual(rc, 0, out)
        v = tomllib.loads(self.vtext())["variant"]["X1"]["param"]["vos"]["verified"]
        self.assertRegex(v, r"^human:alice 2026-11-27 page-image ds_review [0-9a-f]{12} row [0-9a-f]{12}$")
        self.assertNotIn("verified", tomllib.loads(self.vtext())["variant"]["X1"]["param"]["iq"])
        self.assertTrue(tomllib.loads((self.d / "component.toml").read_text())["param"]["vos"]["verified"].startswith("tester"))
        self.run_r()
        self.assertEqual(self.rows()[KEY]["state"], "HUMAN_VERIFIED")
        self.assertEqual(review_status.checked_rows(self.d, local_pdf=False)[KEY], ("alice", "2026-11-27"))
        r = review_status.review(self.d, self.root, local_pdf=False)
        self.assertIn(KEY, r["matters"])
        self.assertEqual(r["status"][KEY], "checked")
        self.assertEqual(r["status"][REFKEY], "reference")
        self.assertEqual([m for lvl, m in check.check_ledger(self.d) if lvl == "ERROR"], [])

    def test_base_edit_stales_the_override_stamp(self):
        no_agent(self)
        self.assertEqual(S.stamp(self.root, "alice", [f"X:{KEY}"], today=DAY)[0], 0)
        self.run_r()
        self.assertEqual(self.rows()[KEY]["state"], "HUMAN_VERIFIED")
        self.edit('symbol = "VOS"\nkind', 'symbol = "VOS"\nnote = "base only"\nkind')  # a base field the override does not set
        self.run_r()
        self.assertEqual(self.rows()[KEY]["state"], "STALE")
        self.assertNotIn(KEY, review_status.checked_rows(self.d, local_pdf=False))

    def test_stamp_refuses_inside_claude_code(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}):
            rc, out = S.stamp(self.root, "alice", [f"X:{KEY}"], today=DAY)
        self.assertEqual(rc, 1)
        self.assertIn("CLAUDECODE", "\n".join(out))
        self.assertNotIn("verified", self.vtext())

    def test_stamp_refuses_a_reference_override_and_an_unknown_one(self):
        no_agent(self)
        for ref, why in ((f"X:{REFKEY}", "reference row, nothing to stamp"), ("X:variant.X1.nope", "no override")):
            rc, out = S.stamp(self.root, "alice", [ref], today=DAY)
            self.assertEqual(rc, 1, out)
            self.assertIn(why, "\n".join(out))
        self.assertNotIn("verified", self.vtext())

    def test_lib_check_rejects_a_verified_line_on_a_reference_override(self):
        self.d.joinpath("variants.toml").write_text(self.vtext().replace(
            'cite = "DS p.2, 6.5 Electrical Characteristics, x"\ntyp = 1.2', 'cite = "DS p.2, 6.5 Electrical Characteristics, x"\n'
            'verified = "sonnet-audit 2026-11-27 x"\ntyp = 1.2', 1))
        msgs = [m for lvl, m in check.check_ledger(self.d) if lvl == "ERROR"]
        self.assertTrue(any(REFKEY in m and "reference override" in m for m in msgs), msgs)

    def test_set_stamp_with_dotted_and_quoted_variant_names(self):
        self.assertEqual(S.override_ref("variant.A.1.gain"), ("A.1", "gain"))
        text = '[variant."A.1".param.gain]\ncite = "DS p.1"\ntyp = 1\n'
        out = S.set_stamp(text, "variant.A.1.gain", "human:a x")
        self.assertEqual(tomllib.loads(out)["variant"]["A.1"]["param"]["gain"]["verified"], "human:a x")
        with self.assertRaises(ValueError):  # a quote in a variant name has no plain header: refused, not guessed
            S.set_stamp('[variant."A\\"B".param.gain]\ncite = "x"\n', 'variant.A"B.gain', "human:a x")

    def test_lib_check_catches_a_wrong_override_stamp_and_state(self):
        self.d.joinpath("variants.toml").write_text(self.vtext().replace(
            'cite = "DS p.2, 6.5 Electrical Characteristics, x"\ntyp = 10', 'cite = "DS p.2, 6.5 Electrical Characteristics, x"\n'
            'verified = "sonnet-audit 2026-11-27 x"\ntyp = 10', 1))
        msgs = [m for lvl, m in check.check_ledger(self.d) if lvl == "ERROR"]
        self.assertTrue(any(f"row {KEY}: stamp differs" in m for m in msgs), msgs)

    def test_human_review_needed_names_a_stampable_ref_for_an_override(self):
        from lib import component
        component.reset_inputs()
        p = component.load(self.d, variant="X1")
        p.param("vos")
        need = {n["key"]: n for n in component.human_review_needed()}
        self.assertEqual(need["vos"]["review_key"], KEY)
        self.assertEqual(need["vos"]["ref"], f"X:{KEY}")
        component.reset_inputs()


class OverrideStampsInPrs(Repo):
    def test_a_foreign_login_in_variants_toml_is_caught(self):
        v = "components/Acme/X/variants.toml"
        base = '[variant."X1".param.vos]\ncite = "DS p.1"\n'
        self.flagged({v: base}, {v: base + f'verified = "{BOB}"\n'})
        self.fresh()
        self.assertEqual(self.run_c({v: base}, {v: base + f'verified = "{AL}"\n'})[0], 0)


class SeveralOverrides(Family):
    def test_k_and_n_count_every_override_of_one_key(self):
        block = OVERRIDES.split('[variant."X1".param.vos]')[1].split('[variant."X1".param.iq]')[0]
        self.d.joinpath("variants.toml").write_text(OVERRIDES + '\n[variant."X2"]\nmpn = "X2"\n\n[variant."X2".param.vos]' + block)
        self.run_r()
        r = review_status.review(self.d, self.root, local_pdf=False)
        self.assertEqual({k for k in r["matters"] if k.rsplit(".", 1)[-1] == "vos"}, {"vos", "variant.X1.vos", "variant.X2.vos"})
        self.assertEqual((r["k"], r["n"]), (0, 3))

