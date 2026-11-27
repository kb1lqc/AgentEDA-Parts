"""tools/stamp.py (person-run human stamp) on temp copies with real ds_review records (docs/spec/review.md "Runs")."""
import datetime
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import stamp as S  # noqa: E402
import lib  # noqa: E402
from lib import component as lib_component  # noqa: E402
from test_ds_review import BODY, COMP, Base, PinBase  # noqa: E402

DAY = datetime.date(2026, 11, 20)


def no_agent(test):
    """These tests play the person: clear CLAUDECODE (set when an agent runs the suite) for the test's duration."""
    import os
    from unittest import mock
    patcher = mock.patch.dict(os.environ)
    patcher.start()
    test.addCleanup(patcher.stop)
    os.environ.pop("CLAUDECODE", None)


class Stamp(Base):
    def setUp(self):
        no_agent(self)
        super().setUp()
        rc, out = self.run_r()
        self.assertEqual(rc, 0, out)
        self.sha = self.ledger()["inputs"]["pdf_sha256"][:12]

    def toml(self):
        return (self.root / COMP / "component.toml").read_text()

    def stamp(self, *refs, who="alice"):
        return S.stamp(self.root, who, list(refs), today=DAY)

    def refused(self, *refs, who="alice", why=""):
        before = self.toml()
        rc, out = self.stamp(*refs, who=who)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.toml(), before, "a refusal must write nothing")
        self.assertIn(why, "\n".join(out))
        return out

    def test_writes_human_stamp_replacing_machine_and_repins(self):
        before = tomllib.loads(self.toml())
        rc, out = self.stamp("X:vos", "X:iq")
        self.assertEqual(rc, 0, out)
        hashes = {k: r["hash"][:12] for k, r in self.rows().items() if isinstance(r, dict) and r.get("hash")}
        want_of = {k: f"human:alice 2026-11-20 page-image ds_review {self.sha} row {hashes[k]}" for k in ("vos", "iq")}
        after = tomllib.loads(self.toml())
        self.assertEqual(after["param"]["vos"]["verified"], want_of["vos"])  # machine stamp replaced
        self.assertEqual(after["param"]["iq"]["verified"], want_of["iq"])    # inserted after cite
        self.assertRegex(want_of["iq"], lib_component.HUMAN_RE)
        for k in ("vos", "iq"):
            before["param"][k]["verified"] = want_of[k]
        self.assertEqual(after, before, "only the two stamps change")
        self.assertIn("X:vos: tester 2026-11-20 page-image ds_review abc -> " + want_of["vos"], out)
        self.assertIn("X:iq: (no stamp) -> " + want_of["iq"], out)
        self.assertEqual(self.run_r()[0], 0)
        rows = self.rows()
        self.assertEqual((rows["vos"]["state"], rows["iq"]["state"]), ("HUMAN_VERIFIED", "HUMAN_VERIFIED"))

    def test_disagree_and_not_found_refused(self):
        self.assertEqual(self.rows()["vos_bad"]["status"], "DISAGREE")
        self.refused("X:vos_bad", why="status DISAGREE")
        self.refused("X:nocite", why="status NOT_FOUND")

    def test_all_or_nothing(self):
        out = self.refused("X:vos", "X:vos_bad")
        self.assertEqual(out[-1], "nothing written")

    def test_unknown_key_value_and_bad_refs(self):
        self.refused("X:nope", why="no [param.nope]")
        self.refused("Y:vos", why="no component directory")
        self.refused("vos", why="expected <Value>:<key>")
        self.refused(why="no <Value>:<key>")

    def test_refused_inside_claude_code(self):
        import os
        os.environ["CLAUDECODE"] = "1"
        out = self.refused("X:iq", why="CLAUDECODE is set")
        self.assertEqual(out, [S.AGENT])
        rc, out = self.gh('echo octo-cat')  # main refuses before asking gh
        self.assertEqual((rc, out.strip()), (1, S.AGENT))

    def test_who_must_be_one_word(self):
        self.refused("X:iq", who="Alice Smith", why="--who")
        self.refused("X:iq", who="alice_s", why="not a GitHub login")
        self.refused("X:iq", who="", why="--who")

    def test_pdf_changed_or_missing_refused(self):
        pdf = self.root / "docs/datasheets/x.pdf"
        pdf.write_bytes(pdf.read_bytes() + b"\n% changed\n")
        self.refused("X:iq", why="differs from the PDF")
        pdf.unlink()
        self.refused("X:iq", why="missing")

    def test_row_changed_since_review_refused(self):
        self.edit("max = 2", "max = 3")  # iq row edited after the ledger was written
        self.refused("X:iq", why="older than the committed row")

    def test_no_review_record_refused(self):
        img = self.cdir / self.rows()["iq"]["image"]
        img.unlink()
        self.refused("X:iq", why="no local evidence image")
        import shutil
        shutil.rmtree(self.rdir)
        self.refused("X:iq", why="no readable review/review.toml")

    def test_no_evidence_record_or_one_of_another_row_refused(self):
        ev = self.cdir / "evidence.toml"
        text = ev.read_text()
        ev.write_text(text.replace(self.rows()["iq"]["hash"], "0" * 64))  # the record describes another version of the row
        self.refused("X:iq", why="no local evidence of the current row")
        ev.unlink()  # a clean clone: committed ledger, no cache
        self.refused("X:iq", why="no local evidence of the current row")
        ev.write_text(text)
        self.assertEqual(self.stamp("X:iq")[0], 0)

    def test_from_file(self):
        f = self.root / "refs.txt"
        f.write_text("# checked\nX:iq\n\nX:vos  # comment\n")
        self.assertEqual(S.read_refs(["X:aol"], f), ["X:aol", "X:iq", "X:vos"])

    def test_set_stamp_guards(self):
        t = self.toml()
        with self.assertRaises(ValueError):
            S.set_stamp(t, "nope", "human:a 2026-11-20 x")
        bad = t.replace('[param.iq]\n', '[param.iq]\n[param.iq.sub]\n', 1)  # stamp would land in another table
        with self.assertRaises(Exception):
            S.set_stamp(bad, "iq", "human:a 2026-11-20 x")

    def gh(self, script):
        """Run S.main with a fake `gh` first on PATH (script = its sh body; None = no gh at all)."""
        import contextlib, io, os
        bindir = self.root / "bin"
        bindir.mkdir(exist_ok=True)
        if script is not None:
            (bindir / "gh").write_text("#!/bin/sh\n" + script + "\n")
            (bindir / "gh").chmod(0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = str(bindir) if script is None else f"{bindir}{os.pathsep}{old}"
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = S.main(["--root", str(self.root), "X:iq"])
        finally:
            os.environ["PATH"] = old
        return rc, buf.getvalue()

    def test_who_defaults_to_github_login(self):
        rc, out = self.gh('[ "$*" = "api user --jq .login" ] && echo octo-cat')
        self.assertEqual(rc, 0, out)
        self.assertIn('-> human:octo-cat ', out)
        self.assertRegex(tomllib.loads(self.toml())["param"]["iq"]["verified"], lib_component.HUMAN_RE)

    def test_gh_missing_or_signed_out_refused(self):
        before = self.toml()
        rc, out = self.gh(None)
        self.assertEqual(rc, 1)
        self.assertIn("gh is not installed", out)
        self.assertIn("gh auth login", out)
        rc, out = self.gh('echo "You are not logged into any GitHub hosts." >&2; exit 4')
        self.assertEqual(rc, 1)
        self.assertIn("not logged into", out)
        self.assertIn("--who <github-login>", out)
        rc, out = self.gh("echo 'bad login!'")  # gh output is validated like --who
        self.assertEqual(rc, 1)
        self.assertEqual(self.toml(), before)

    def test_github_login_rules(self):
        for ok in ("a", "octo-cat", "A1-b2-c3", "x" * 39):
            self.assertRegex(ok, S.WHO_RE)
            self.assertRegex(f"human:{ok} 2026-11-20 page-image ds_review 0123456789ab row 0123456789ab",
                             lib_component.HUMAN_RE)
        self.assertIsNone(S.WHO_RE.match("alice\n"))  # \\Z, not $: a trailing newline is not a login
        self.assertIsNone(lib_component.HUMAN_RE.match(
            "human:alice 2026-11-20 page-image ds_review 0123456789ab row 0123456789ab\n"))
        for bad in ("", "-a", "a-", "a--b", "a_b", "a.b", "x" * 40, "a b"):
            self.assertNotRegex(bad, S.WHO_RE)
            self.assertNotRegex(f"human:{bad} 2026-11-20 page-image ds_review 0123456789ab row 0123456789ab",
                                lib_component.HUMAN_RE)

    def test_crlf_comment_and_mode_kept(self):
        f = self.root / COMP / "component.toml"
        t = self.toml().replace('verified = "%s"' % "tester 2026-11-20 page-image ds_review abc",
                                'verified = "tester 2026-11-20 page-image ds_review abc"  # keep me')
        f.write_bytes(t.replace("\n", "\r\n").encode())
        f.chmod(0o644)
        self.assertEqual(self.run_r()[0], 0)  # ledger hashes are line-ending independent
        rc, out = self.stamp("X:vos", "X:iq")
        self.assertEqual(rc, 0, out)
        b = f.read_bytes()
        self.assertEqual(b.count(b"\n"), b.count(b"\r\n"), "every line keeps CRLF")
        self.assertRegex(b.decode(), r'verified = "human:alice [^"]+"  # keep me\r\n')
        self.assertEqual(f.stat().st_mode & 0o777, 0o644)
        self.assertEqual([p.name for p in f.parent.iterdir() if p.name.startswith(".component")], [])

    def test_bad_toml_and_changed_image_refused(self):
        img = self.cdir / self.rows()["iq"]["image"]
        img.write_bytes(img.read_bytes() + b"x")
        self.refused("X:iq", why="image_sha256")
        f = self.root / COMP / "component.toml"
        f.write_text(self.toml() + "\n[param.broken\n")
        self.refused("X:vos", why="not valid TOML")


class StampPinout(PinBase):
    """`<Value>:pinout` (docs/spec/review-view.md "Pinout stamp"): same refusals as a row."""

    def setUp(self):
        no_agent(self)
        super().setUp()
        self.assertEqual(self.run_r()[0], 0)
        self.sha = self.ledger()["inputs"]["pdf_sha256"][:12]

    def toml(self):
        return (self.root / COMP / "component.toml").read_text()

    def stamp(self, *refs, who="alice"):
        return S.stamp(self.root, who, list(refs), today=DAY)

    def refused(self, *refs, why=""):
        before = self.toml()
        rc, out = self.stamp(*refs)
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.toml(), before, "a refusal must write nothing")
        self.assertIn(why, "\n".join(out))

    def test_writes_the_exact_pinout_stamp_and_repins(self):
        before = tomllib.loads(self.toml())
        rc, out = self.stamp("X:pinout", "X:iq")
        self.assertEqual(rc, 0, out)
        want = f"human:alice 2026-11-20 page-image pinout {self.sha} pins {self.pins_hash()[:12]}"
        after = tomllib.loads(self.toml())
        self.assertEqual(after["pinout"], {"verified": want})
        self.assertRegex(want, lib_component.PINOUT_RE)
        del after["pinout"]
        after["param"]["iq"].pop("verified")
        self.assertEqual(after, before, "only the two stamps change")
        self.assertIn("X:pinout: (no stamp) -> " + want, out)
        self.assertEqual(self.run_r()[0], 0)
        self.assertEqual(self.ledger()["pinout"]["state"], "HUMAN_VERIFIED")
        rc, out = self.stamp("X:pinout")  # again: the old stamp is replaced, one [pinout] table
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.toml().count("[pinout]"), 1)
        self.assertIn("X:pinout: " + want + " -> " + want, out)

    def test_machine_stamp_is_replaced_in_place(self):
        p = self.root / COMP / "component.toml"
        p.write_text(self.toml() + '\n[pinout]\n# note\nverified = "sonnet-audit 2026-11-18 pins"  # keep\n')
        self.assertEqual(self.stamp("X:pinout")[0], 0)
        self.assertRegex(self.toml(), r'\[pinout\]\n# note\nverified = "human:alice [^"]+"  # keep\n')

    def test_refusals_write_nothing(self):
        pdf = self.root / "docs/datasheets/x.pdf"
        self.edit('function = "Input"', 'function = "In"')  # pins edited after the record
        self.refused("X:pinout", why="older than the committed pins")
        self.run_r()
        img = self.cdir / self.ledger()["pinout"]["page"][0]["image"]
        img.write_bytes(img.read_bytes() + b"x")
        self.refused("X:pinout", why="evidence image differs")
        img.unlink()
        self.refused("X:pinout", why="no local evidence image")
        self.run_r()
        pdf.write_bytes(pdf.read_bytes() + b"\n% changed\n")
        self.refused("X:pinout", why="differs from the PDF")
        pdf.unlink()
        self.refused("X:pinout", why="missing")
        import shutil
        shutil.rmtree(self.rdir)
        self.refused("X:pinout", why="no readable review/review.toml")

    def test_every_pinout_page_image_is_checked(self):
        self.edit('function = "Output"\ncite = "DS p.4, Pin Functions"', 'function = "Output"\ncite = "DS p.1, Pin Functions"')
        self.run_r()
        first, second = (self.cdir / g["image"] for g in self.ledger()["pinout"]["page"])
        self.assertNotEqual(first, second)
        good = second.read_bytes()
        second.write_bytes(good + b"x")  # the second page only: a check of the first image alone would pass
        self.refused("X:pinout", why="evidence image differs")
        second.unlink()
        self.refused("X:pinout", why="no local evidence image")
        second.write_bytes(good)
        self.assertEqual(self.stamp("X:pinout")[0], 0)

    def test_no_pins_and_all_or_nothing_and_agent(self):
        import os
        self.refused("X:pinout", "X:vos_bad", why="status DISAGREE")
        self.make(BODY)
        self.run_r()
        self.refused("X:pinout", why="no [[pin]]")
        os.environ["CLAUDECODE"] = "1"
        self.assertEqual(self.stamp("X:pinout"), (1, [S.AGENT]))


class HumanCurrent(Base):
    """lib.human_review_needed against real ledgers: a human stamp is bound to the row hash and the PDF SHA."""

    def setUp(self):
        no_agent(self)
        super().setUp()
        self.assertEqual(self.run_r()[0], 0)
        rc, out = S.stamp(self.root, "alice", ["X:iq"], today=DAY)
        self.assertEqual(rc, 0, out)
        lib.reset_inputs()
        self.addCleanup(lib.reset_inputs)

    def toml(self):
        return (self.root / COMP / "component.toml").read_text()

    def reasons(self):
        lib.reset_inputs()
        lib.load(str(self.root / COMP)).param("iq")
        return [e["reason"] for e in lib.human_review_needed()]

    def test_fresh_stamp_is_current_before_and_after_repin(self):
        self.assertEqual(self.reasons(), [])
        self.assertEqual(self.run_r()[0], 0)
        self.assertEqual(self.rows()["iq"]["state"], "HUMAN_VERIFIED")
        self.assertEqual(self.reasons(), [])

    def test_edit_after_stamp_flags_with_or_without_verify(self):
        self.edit("max = 2", "max = 3")
        self.assertEqual(self.reasons(), ["human stamp: row changed"])  # no verify run: ledger still says NEW
        self.assertEqual(self.run_r()[0], 0)  # ds_review re-pins to the current hash, but the stamp's row hash differs:
        self.assertEqual(self.rows()["iq"]["state"], "STALE")  # the ledger says STALE too
        self.assertEqual(self.reasons(), ["STALE"])

    def test_broken_human_stamp_is_unverified(self):
        lib.reset_inputs()
        lib.load(str(self.root / COMP)).param("iq")
        self.assertEqual((lib.unverified_inputs(), lib.verdict(True)), ([], "PASS"))
        self.edit("max = 2", "max = 3")
        lib.reset_inputs()
        lib.load(str(self.root / COMP)).param("iq")
        self.assertEqual(lib.unverified_inputs(), ["X:iq"])
        self.assertEqual(lib.verdict(True), "PASS (UNVERIFIED INPUTS)")

    def test_repo_root(self):
        self.assertEqual(lib_component._repo_root(self.root / COMP), self.root.resolve())
        self.assertIsNone(lib_component._repo_root(self.root / "elsewhere" / "X"))

    def test_delta_lists_only_changed_human_stamped_rows(self):
        delta = self.root / ".review-cache/Acme/X/DELTA.md"
        self.assertEqual(self.run_r()[0], 0)
        self.assertEqual(delta.read_text(), "no human-stamped row changed since its stamp\n")  # NEW/machine rows: not a delta
        self.edit("typ = 1.2\nmax = 2", "typ = 1.2\nmax = 3")
        rc, out = self.run_r()
        self.assertIn("| delta 1", out)
        t = delta.read_text()
        self.assertIn("1 row(s) need review", t)
        self.assertIn("## [iq](params/iq.md): STALE", t)
        self.assertIn("-max = 2", t)
        self.assertIn("+max = 3", t)
        self.assertNotIn("## [vos]", t)  # machine-stamped
        self.edit("typ = 1.2\nmax = 3", "typ = 1.2\nmax = 2")
        led = self.rdir / "review.toml"
        led.write_text(led.read_text().replace(self.ledger()["inputs"]["pdf_sha256"], "0" * 64))  # the PDF moved on
        self.run_r()
        self.assertEqual(self.rows()["iq"]["state"], "PDF_CHANGED")
        self.assertIn("## [iq](params/iq.md): PDF_CHANGED", delta.read_text())

    def test_pdf_changed_flags(self):
        pdf = self.root / "docs/datasheets/x.pdf"
        pdf.write_bytes(pdf.read_bytes() + b"\n% changed\n")
        self.assertEqual(self.reasons(), ["human stamp: PDF changed"])  # on disk, ledger not rerun
        pdf.unlink()
        led = self.rdir / "review.toml"
        sha = self.ledger()["inputs"]["pdf_sha256"]
        led.write_text(led.read_text().replace(sha, "0" * 64))
        self.assertEqual(self.reasons(), ["human stamp: PDF changed"])  # ledger SHA differs, PDF absent

    def test_malformed_and_no_record(self):
        t = self.toml()
        stamp = tomllib.loads(t)["param"]["iq"]["verified"]
        for bad in ("human:", "human:alice 2026-11-20 page-image ds_review " + self.ledger()["inputs"]["pdf_sha256"][:12],
                    stamp + " extra"):
            (self.root / COMP / "component.toml").write_text(t.replace(stamp, bad))
            self.assertEqual(self.reasons(), ["human stamp: malformed"], bad)
        (self.root / COMP / "component.toml").write_text(t)
        import shutil
        shutil.rmtree(self.rdir)
        self.assertEqual(self.reasons(), ["no review record"])

    def test_row_hash_is_the_ledgers(self):
        params = tomllib.loads(self.toml())["param"]
        for k, r in self.rows().items():
            if isinstance(r, dict) and r.get("hash") and k in params:
                self.assertEqual(lib_component.row_hash(params[k]), r["hash"], k)


if __name__ == "__main__":
    unittest.main()
