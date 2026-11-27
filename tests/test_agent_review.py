"""Variant overrides as ledger rows, and the agent-review record (docs/spec/agent-review.md). Temp libraries only; the fake datasheet and fixtures are those of tests/test_ds_review.py."""
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
import agent_review as CLI  # noqa: E402  (tools/agent_review.py)
import stamp as S  # noqa: E402
from lib import agent_review as AR  # noqa: E402
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
        for ref, why in ((f"X:{REFKEY}", "reference row, agent-reviewed, nothing to stamp"), ("X:variant.X1.nope", "no override")):
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


class CalcHash(unittest.TestCase):
    def h(self, src):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "calc.py"
            f.write_text(src)
            return AR.calc_ast_hash(f)

    def test_layout_and_comments_keep_the_hash_docstring_and_operator_change_it(self):
        base = '"""Doc."""\n\n\ndef f(a, b):\n    """Sum."""\n    return a + b\n'
        self.assertEqual(self.h(base), self.h(base.replace("a + b", "a  +  b  # why").replace("\n\n\n", "\n\n\n\n\n")))
        self.assertNotEqual(self.h(base), self.h(base.replace("Sum.", "Total.")))
        self.assertNotEqual(self.h(base), self.h(base.replace("a + b", "a - b")))

    def test_old_record_without_hash_version_is_stale_with_a_reason(self):
        import shutil
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copytree(ROOT / "components" / "AnalogDevices" / "LTC4364MS", tmp / "components" / "AnalogDevices" / "LTC4364MS")
        d = tmp / "components" / "AnalogDevices" / "LTC4364MS"
        (d / "review").mkdir(exist_ok=True)
        (d / "review" / "agent_review.toml").unlink(missing_ok=True)
        src = tmp / "r.txt"
        src.write_text("low | a | b | c | d\n")
        AR.record(tmp, "LTC4364MS", "adversarial", "m", 1, 0, 1, src)
        self.assertEqual(AR.status(d, tmp)["state"]["adversarial"], "CURRENT")
        f = d / "review" / "agent_review.toml"
        f.write_text("\n".join(l for l in f.read_text().splitlines() if not l.startswith("hash_version")) + "\n")
        st = AR.status(d, tmp)
        self.assertEqual(st["state"]["adversarial"], "STALE")
        self.assertIn("re-record: the hash algorithm changed", st["reason"]["adversarial"])

    def test_hash_is_the_same_under_python_3_9(self):
        import shutil
        import subprocess
        py = "/opt/homebrew/bin/python3.9"
        if not shutil.which(py):
            self.skipTest("python3.9 absent")
        code = ("import ast, hashlib, re, sys\n"
                "src = open(sys.argv[1]).read()\n"
                "m = src[src.index('_SKIP = '):src.index('def public_functions')]\n"
                "from pathlib import Path\n"
                "def _sha(x):\n    return hashlib.sha256(x.encode()).hexdigest()\n"
                "exec(m)\n"
                "for f in sys.argv[2:]:\n    print(f, calc_ast_hash(f))\n")
        files = sorted((ROOT / "components").glob("*/*/calc.py"))
        r = subprocess.run([py, "-c", code, str(ROOT / "lib" / "agent_review.py")] + [str(f) for f in files],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])
        other = dict(line.rsplit(" ", 1) for line in r.stdout.splitlines())
        self.assertEqual(len(other), len(files))
        for f in files:
            self.assertEqual(other[str(f)], AR.calc_ast_hash(f), str(f))


class Record(Family):
    def setUp(self):
        super().setUp()
        (self.d / "calc.py").write_text(CALC)
        self.report = self.root / "report.txt"
        self.report.write_text("high | a.py:1 | p | e | fix\nlow | b.py:2 | p | e | fix\n")
        self.report2 = self.root / "report2.txt"
        self.report2.write_text("medium | c.py:3 | p | e | fix\nlow | d.py:4 | p | e | fix\n")
        self.rec(role="verifier")
        self.rec(role="adversarial", report=self.report2)

    def rec(self, role="verifier", findings=2, applied=1, logged=1, clean=False, report=None, rows_checked=None):
        rc = 0 if role == "verifier" and rows_checked is None else rows_checked
        return AR.record(self.root, "X", role, "claude-haiku", findings, applied, logged, report or self.report, clean=clean,
                         today=DAY, rows_checked=rc)

    def st(self):
        return AR.status(self.d, self.root)["state"]

    def test_record_written_and_current(self):
        e = tomllib.loads((self.d / "review" / "agent_review.toml").read_text())
        for role in AR.ROLES:
            self.assertEqual(e[role]["findings"], 2)
            self.assertEqual(e[role]["report_lines"], 2)
            self.assertEqual(len(e[role]["report_sha256"]), 64)
            self.assertEqual(len(e[role]["datasheet_pdf_sha256"]), 64)
            self.assertEqual(e[role]["functions"], ["f"])  # public names only
            self.assertIn(REFKEY, e[role]["reference_overrides"])
            self.assertIn("iq", e[role]["reference_rows"])
            self.assertIn(KEY, e[role]["matters"])
            self.assertEqual(set(e[role]["input_sha256"]), {"component.toml", "variants.toml", "calc.py", "examples/use.py"})
        self.assertEqual(self.st(), {"verifier": "CURRENT", "adversarial": "CURRENT"})
        self.assertEqual(AR.clause(AR.status(self.d, self.root)), "; agent review: verifier+adversarial current 2026-11-27")
        self.assertEqual([m for lvl, m in check.check_agent_review(self.d)], [])

    def test_stray_rule_allows_the_record_and_still_rejects_others(self):
        self.assertEqual(check.stray_review_files(self.d), [])
        (self.d / "review" / "notes.md").write_text("x")
        self.assertEqual(len(check.stray_review_files(self.d)), 1)

    def test_param_value_edit_is_stale_and_an_error(self):
        self.edit("typ = 1.2", "typ = 1.3")
        self.assertEqual(set(self.st().values()), {"STALE"})
        self.assertEqual(AR.clause(AR.status(self.d, self.root)), "; agent review: stale")
        msgs = check.check_agent_review(self.d)
        self.assertEqual({lvl for lvl, _ in msgs}, {"ERROR"})
        self.assertIn("STALE", msgs[0][1])

    def test_human_stamp_readme_and_zen_changes_stay_current(self):
        no_agent(self)
        self.assertEqual(S.stamp(self.root, "alice", [f"X:{KEY}", "X:vos"], today=DAY)[0], 0)
        self.assertEqual(set(self.st().values()), {"CURRENT"})  # verified lines are not inputs
        (self.d / "README.md").write_text("changed")
        (self.d / "X.zen").write_text("changed")
        (self.d / "pcb.toml").write_text("")
        (self.d / "review" / "review.toml").write_text("# regenerated\n")
        self.assertEqual(set(self.st().values()), {"CURRENT"})

    def test_calc_docstring_edit_is_stale_but_a_comment_is_not(self):
        calc = self.d / "calc.py"
        calc.write_text(CALC + "# a comment\n")
        self.assertEqual(set(self.st().values()), {"CURRENT"})
        calc.write_text(CALC.replace("Double v.", "Twice v."))
        self.assertEqual(set(self.st().values()), {"STALE"})

    def test_example_file_edit_is_stale(self):
        (self.root / "examples" / "use.py").write_text('# X\nrow = "vos"\nmore = 1\n')
        self.assertEqual(set(self.st().values()), {"STALE"})
        (self.root / "examples" / "other.py").write_text("unrelated = 1\n")  # names no part of this family
        (self.root / "examples" / "use.py").write_text('# X\nrow = "vos"\n')
        self.assertEqual(set(self.st().values()), {"CURRENT"})

    def test_matters_key_list_change_is_stale(self):
        # an example that names no part of this family is not an input, but it makes `iq` a row that matters
        (self.root / "examples" / "other.py").write_text('row = "iq"\n')
        self.assertIn("iq", review_status.matters(self.d, self.root))
        self.assertEqual(set(self.st().values()), {"STALE"})

    def test_one_role_missing_is_pending_and_a_counted_warn(self):
        (self.d / "review" / "agent_review.toml").unlink()
        self.rec(role="verifier")
        self.assertEqual(self.st(), {"verifier": "CURRENT", "adversarial": "MISSING"})
        self.assertEqual(AR.clause(AR.status(self.d, self.root)), "; agent review: pending (adversarial)")
        msgs = check.check_agent_review(self.d)
        self.assertEqual([lvl for lvl, _ in msgs], ["WARN"])
        self.assertIn(check.AGENT_PENDING, msgs[0][1])

    def test_missing_warn_does_not_fail_main(self):
        (self.d / "review" / "agent_review.toml").unlink()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            check.main([str(self.d)])
        self.assertIn("1 agent review pending", buf.getvalue())
        self.assertNotIn("agent review MISSING", buf.getvalue())  # counted, not printed per part

    def test_malformed_file_is_an_error(self):
        f = self.d / "review" / "agent_review.toml"
        f.write_text("[verifier\nbroken")
        msgs = check.check_agent_review(self.d)
        self.assertTrue(msgs and all(lvl == "ERROR" for lvl, _ in msgs), msgs)
        f.write_text('[verifier]\ndate = "2026-11-27"\n')  # fields missing
        msgs = check.check_agent_review(self.d)
        self.assertTrue(any("verifier" in m and "missing" in m for _, m in msgs), msgs)

    def test_scope_naming_a_missing_row_is_an_error(self):
        f = self.d / "review" / "agent_review.toml"
        f.write_text(f.read_text().replace('"iq"', '"ghost"', 1))
        msgs = [m for lvl, m in check.check_agent_review(self.d) if lvl == "ERROR"]
        self.assertTrue(any("ghost" in m for m in msgs), msgs)

    def test_clean_and_report_rules(self):
        empty = self.root / "empty.txt"
        empty.write_text("\n")
        said = self.root / "said.txt"
        said.write_text("no findings: checked 12 numbers\n")
        for kw in (dict(findings=0, applied=0, logged=0, report=said),                      # zero findings needs --clean
                   dict(findings=2, applied=1, logged=1, report=empty),                     # findings, empty report
                   dict(findings=2, applied=1, logged=1, clean=True, report=said),          # clean with findings
                   dict(findings=1, applied=1, logged=1),                                   # applied + logged > findings
                   dict(findings=1, applied=0, logged=0, report=self.root / "nope.txt")):  # unreadable report
            with self.assertRaises(ValueError, msg=str(kw)):
                self.rec(**kw)
        self.rec(findings=0, applied=0, logged=0, clean=True, report=said)
        with self.assertRaises(ValueError):
            self.rec(findings=0, applied=0, logged=0, clean=True, report=empty)  # --clean needs a report that says something
        with self.assertRaises(ValueError):
            self.rec(role="verifier", report=self.report2)  # the other role's report
        with self.assertRaises(ValueError):
            self.rec(findings=3, applied=0, logged=0)  # 3 findings, 2 report lines
        with self.assertRaises(ValueError):
            AR.record(self.root, "X", "reviewer", "m", 1, 0, 0, self.report)  # unknown role
        with self.assertRaises(ValueError):
            AR.record(self.root, "Nope", "verifier", "m", 1, 0, 0, self.report)  # unknown part

    def test_rows_checked_rules_and_backward_compatibility(self):
        with self.assertRaises(ValueError):  # required for the verifier
            AR.record(self.root, "X", "verifier", "m", 2, 1, 1, self.report)
        with self.assertRaises(ValueError):  # forbidden for the adversarial role
            AR.record(self.root, "X", "adversarial", "m", 2, 1, 1, self.report2, rows_checked=1)
        total = len(AR.current(self.d, self.root)["reference_rows"]) + len(AR.current(self.d, self.root)["reference_overrides"])
        for bad in (total + 1, -1):
            with self.assertRaises(ValueError):
                self.rec(role="verifier", rows_checked=bad)
        self.rec(role="verifier", rows_checked=total)
        e = tomllib.loads((self.d / "review" / "agent_review.toml").read_text())
        self.assertEqual((e["verifier"]["rows_checked"], e["verifier"]["rows_total"]), (total, total))
        self.assertNotIn("rows_checked", e["adversarial"])
        f = self.d / "review" / "agent_review.toml"  # an old record without the fields still parses
        f.write_text("\n".join(l for l in f.read_text().splitlines() if not l.startswith("rows_")) + "\n")
        self.assertEqual(set(self.st().values()), {"CURRENT"})
        self.edit("typ = 1.2", "typ = 1.3")
        self.assertEqual(set(self.st().values()), {"STALE"})

    def test_swapping_the_datasheet_stales_the_record(self):
        self.assertEqual(set(self.st().values()), {"CURRENT"})
        (self.root / "docs/datasheets/x.pdf").write_bytes(self.PDF + b"\n% changed\n")
        self.assertEqual(set(self.st().values()), {"STALE"})

    def test_example_scope_is_whole_word_and_recursive(self):
        ex = self.root / "examples"
        (ex / "sub").mkdir()
        (ex / "sub" / "deep.py").write_text("# X\n")
        (ex / "other.py").write_text("# XY and aXb\n")  # contains X only inside other words
        names = {f.relative_to(ex).as_posix() for f in AR.example_files_of(self.d, self.root)}
        self.assertEqual(names, {"use.py", "sub/deep.py"})
        self.assertIn("examples/sub/deep.py", AR.current(self.d, self.root)["input_sha256"])

    def test_capacitor_series_hashes_the_decode_tables(self):
        t = (self.d / "component.toml").read_text()
        (self.d / "component.toml").write_text(t.replace('[part]\n', '[part]\ncatalog_decoder = "murata-gcm"\n', 1))
        self.assertIn("catalog_tables", AR.current(self.d, self.root)["input_sha256"])

    def test_cli_refuses_and_writes(self):
        args = ["--role", "verifier", "--rows-checked", "0", "--model", "m", "--findings", "2", "--applied", "1", "--logged", "1",
                "--report", str(self.report), "--root", str(self.root)]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(CLI.main(["record", "X"] + args), 0)
            self.assertEqual(CLI.main(["record", "Nope"] + args), 1)
            self.assertEqual(CLI.main(["record", "X"] + ["--role", "boss"] + args[4:]), 1)
        self.assertEqual(buf.getvalue().count("refused"), 2)

    def test_readme_line_carries_the_clause(self):
        r = review_status.review(self.d, self.root, local_pdf=False)
        self.assertIn("; agent review: verifier+adversarial current 2026-11-27", review_status.readme_line("X", r))


if __name__ == "__main__":
    unittest.main()
