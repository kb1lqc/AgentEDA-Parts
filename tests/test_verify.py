"""Tests for tools/verify.py with a fake command runner (no real lib.check, pcb or unittest is run)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import verify as v  # noqa: E402


def write(p, text=""):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


class Fake:
    """Scripted runner: `replies` maps a command key to (rc, output); `effects` maps a key to a callable run first."""

    def __init__(self, root, **over):
        self.root = Path(root)
        self.calls = []
        self.replies = {
            "pcb --version": (0, "pcbc 0.4.102\n"),
            "-m lib.check": (0, "3 components, 0 errors, 0 warnings, 0 tolerated (datasheets absent), 0 allowlisted findings, 0 abstained\n"),
            "-m lib.zen": (0, ""),
            "-m lib.readme": (0, ""),
            "pcb build": (0, "ok\n"),
            "-m unittest": (0, "Ran 12 tests in 0.1s\n\nOK\n"),
            "git status": (0, ""),
            "git ls-files": (0, ""),
            "tools/ds_review.py": (0, "summary: 1 component(s), 0 render(s), 0 file(s) changed\n"),
        }
        self.replies.update(over)
        self.effects = {}

    def __call__(self, cmd, cwd, env=None):
        key = next((k for k in self.replies if k in " ".join(cmd)), None)
        self.calls.append(" ".join(cmd))
        if key in self.effects:
            self.effects[key]()
        return self.replies[key] if key else (127, f"unscripted {cmd}")


def mkroot(tmp, version="0.4"):
    root = Path(tmp)
    write(root / "pcb.toml", f'[workspace]\nrepository = "x"\npcb-version = "{version}"\n')
    write(root / "components/A/B/pcb.toml")
    write(root / "components/A/B/component.toml", "x")
    write(root / "README.md", "r")
    return root


class TestVerify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = mkroot(self.tmp.name)
        self.logs = Path(self.tmp.name) / "logs"

    def tearDown(self):
        self.tmp.cleanup()

    def run_v(self, fake, **kw):
        kw.setdefault("all_dirs", True)
        return v.verify(self.root, log_dir=self.logs, runner=fake, **kw)

    def test_default_log_dir_is_fresh_per_run(self):
        # two runs at once must not share a log directory (AgentEDA-Parts #19)
        import shutil
        dirs = []
        for _ in range(2):
            rc, lines = v.verify(self.root, runner=Fake(self.root), all_dirs=True)
            logs = [l for l in lines if l.startswith("logs:")]
            self.assertEqual(len(logs), 1, lines)
            dirs.append(Path(logs[0].split(":", 1)[1].strip()))
        self.addCleanup(lambda: [shutil.rmtree(d, ignore_errors=True) for d in dirs])
        self.assertNotEqual(dirs[0], dirs[1])
        self.assertTrue(all(d.is_dir() and d.name.startswith("zl-verify-") for d in dirs))

    def test_pass_line_has_counts(self):
        rc, lines = self.run_v(Fake(self.root))
        self.assertEqual(rc, 0)
        self.assertEqual(lines[0], "PASS: pcb 0.4, components 3, built 1/1, tests 12")
        self.assertTrue(lines[-1].startswith("logs: "))
        self.assertTrue((self.logs / "00-pcb-version.log").read_text().startswith("exit 0"))

    def test_pcb_version_mismatch_fails(self):
        rc, lines = self.run_v(Fake(self.root, **{"pcb --version": (0, "pcbc 0.5.1\n")}))
        self.assertEqual(rc, 1)
        self.assertIn("pcb-version 0.4 but installed pcb is 0.5", lines[1])

    def test_pcb_cannot_start_fails(self):
        rc, lines = self.run_v(Fake(self.root, **{"pcb --version": (127, "cannot start pcb")}))
        self.assertEqual(rc, 1)

    def test_missing_root_pcb_toml_version_fails(self):
        (self.root / "pcb.toml").write_text("[workspace]\n")
        rc, lines = self.run_v(Fake(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("pcb-version", lines[1])

    def test_zero_components_fails(self):
        out = "0 components, 0 errors, 0 warnings, 0 tolerated (datasheets absent), 0 allowlisted findings, 0 abstained\n"
        rc, lines = self.run_v(Fake(self.root, **{"-m lib.check": (0, out)}))
        self.assertEqual(rc, 1)
        self.assertIn("zero components", lines[1])

    def test_check_without_summary_fails(self):
        rc, _ = self.run_v(Fake(self.root, **{"-m lib.check": (0, "")}))
        self.assertEqual(rc, 1)

    def test_check_failure_shows_first_five_only(self):
        out = "".join(f"A/B: ERROR: problem {i}\n" for i in range(8)) + "1 components, 8 errors, 0 warnings\n"
        rc, lines = self.run_v(Fake(self.root, **{"-m lib.check": (1, out)}))
        self.assertEqual(rc, 1)
        self.assertEqual(len([l for l in lines if "problem" in l]), 5)
        self.assertIn("lib.check: A/B: ERROR: problem 0", lines[1])
        self.assertNotIn("problem 5", "\n".join(lines))

    def test_missing_evidence_cache_is_rebuilt_then_checked_again(self):
        ok = "1 components, 0 errors, 0 warnings, 0 tolerated (datasheets absent), 0 allowlisted findings, 0 abstained\n"
        bad = ("A/B: ERROR: .review-cache/A/B/evidence.toml has no evidence of x (PDF present): "
               "rerun python3 tools/ds_review.py components/A/B\n1 components, 1 errors, 0 warnings\n")

        class Healing(Fake):
            n = 0

            def __call__(self, cmd, cwd, env=None):
                if "-m lib.check" in " ".join(cmd):
                    Healing.n += 1
                    self.calls.append(" ".join(cmd))
                    return (1, bad) if Healing.n == 1 else (0, ok)
                return super().__call__(cmd, cwd, env)

        fake = Healing(self.root)
        rc, lines = self.run_v(fake)
        self.assertEqual(rc, 0, lines)
        self.assertEqual(sum("-m lib.check" in c for c in fake.calls), 2)
        self.assertTrue(any(c.endswith("tools/ds_review.py components/A/B") for c in fake.calls))
        self.assertIn("rebuilt the local evidence cache of 1 part(s): B", "\n".join(lines))

    def test_failure_line_gets_file_and_line(self):
        out = "components/A/B/B.zen:12:4 error: bad net\n"
        rc, lines = self.run_v(Fake(self.root, **{"pcb build": (1, out)}))
        self.assertEqual(rc, 1)
        self.assertEqual(lines[1], "components/A/B/B.zen:12 error: bad net")

    def test_build_failure_without_diagnostic_still_fails(self):
        rc, lines = self.run_v(Fake(self.root, **{"pcb build": (1, "")}))
        self.assertEqual(rc, 1)
        self.assertIn("no diagnostic", lines[1])

    def test_generator_changing_files_fails_unless_regen(self):
        fake = Fake(self.root)
        fake.effects["-m lib.zen"] = lambda: write(self.root / "components/A/B/B.zen", "new")
        rc, lines = self.run_v(fake)
        self.assertEqual(rc, 1)
        self.assertIn("components/A/B/B.zen:1 changed by lib.zen/lib.readme", lines[1])
        (self.root / "components/A/B/B.zen").unlink()
        rc, lines = self.run_v(fake, regen=True)
        self.assertEqual(rc, 0)
        self.assertIn("regenerated 1 file(s): components/A/B/B.zen", lines[0])

    def test_generator_rewriting_identical_bytes_passes(self):
        fake = Fake(self.root)
        fake.effects["-m lib.readme"] = lambda: write(self.root / "README.md", "r")
        self.assertEqual(self.run_v(fake)[0], 0)

    def test_readme_change_is_detected(self):
        fake = Fake(self.root)
        fake.effects["-m lib.readme"] = lambda: write(self.root / "README.md", "changed")
        rc, lines = self.run_v(fake)
        self.assertEqual(rc, 1)
        self.assertIn("README.md:1", lines[1])

    def test_no_changed_dirs_fails_closed(self):
        rc, lines = self.run_v(Fake(self.root), all_dirs=False)
        self.assertEqual(rc, 1)
        self.assertIn("no component dirs to build", lines[1])

    def test_changed_dirs_from_git_status(self):
        fake = Fake(self.root, **{"git status": (0, " M components/A/B/component.toml\n?? components/C/D/new.txt\n M lib/x.py\n")})
        write(self.root / "components/C/D/new.txt")
        rc, lines = self.run_v(fake, all_dirs=False)
        self.assertEqual(rc, 0)
        self.assertIn("built 2/2", lines[0])
        self.assertEqual([c for c in fake.calls if c.startswith("pcb build")],
                         ["pcb build -Wstyle -Dwarnings components/A/B", "pcb build -Wstyle -Dwarnings components/C/D"])

    def test_explicit_dirs_are_built(self):
        fake = Fake(self.root)
        rc, lines = self.run_v(fake, dirs=["components/A/B"], all_dirs=False)
        self.assertEqual(rc, 0)
        self.assertIn("built 1/1", lines[0])

    def test_missing_dir_fails(self):
        rc, lines = self.run_v(Fake(self.root), dirs=["components/X/Y"], all_dirs=False)
        self.assertEqual(rc, 1)
        self.assertIn("components/X/Y:1 not a directory", lines[1])

    def test_zero_tests_fails(self):
        for out in ("Ran 0 tests in 0.0s\n\nNO TESTS RAN\n", "boom\n"):
            rc, lines = self.run_v(Fake(self.root, **{"-m unittest": (0, out)}))
            self.assertEqual(rc, 1, out)
            self.assertIn("no tests ran", lines[1])

    def test_failing_tests_fail(self):
        rc, lines = self.run_v(Fake(self.root, **{"-m unittest": (1, "FAIL: test_x (tests.test_a.A)\nRan 3 tests\n")}))
        self.assertEqual(rc, 1)
        self.assertIn("FAIL: test_x", lines[1])

    def test_unrunnable_command_is_127(self):
        rc, out = v.run_cmd(["/nonexistent/binary-xyz"], self.tmp.name)
        self.assertEqual(rc, 127)

    def test_deterministic_output(self):
        a = self.run_v(Fake(self.root))
        b = self.run_v(Fake(self.root))
        self.assertEqual(a, b)

    def test_clean_pycache(self):
        write(self.root / "lib/__pycache__/x.pyc")
        write(self.root / "components/A/__pycache__/x.pyc")
        v.clean_pycache(self.root)
        self.assertFalse(list(self.root.rglob("__pycache__")))

    def test_pcb_major_minor(self):
        self.assertEqual(v.pcb_major_minor("pcbc 0.4.102"), "0.4")
        self.assertIsNone(v.pcb_major_minor("nothing"))

    # ds_review step and PDF guard (docs/spec/review.md)
    def test_tracked_pdf_fails(self):
        rc, lines = self.run_v(Fake(self.root, **{"git ls-files": (0, "docs/x.pdf\n")}))
        self.assertEqual(rc, 1)
        self.assertIn("docs/x.pdf:1 PDF is tracked", lines[1])

    def test_pdf_under_components_fails(self):
        write(self.root / "components/A/B/review/copy.pdf", "%PDF")
        rc, lines = self.run_v(Fake(self.root))
        self.assertEqual(rc, 1)
        self.assertIn("components/A/B/review/copy.pdf:1", lines[1])

    def test_ds_review_runs_before_lib_check_with_scope(self):
        fake = Fake(self.root)
        self.run_v(fake, all_dirs=False, dirs=["components/A/B"])
        i = next(n for n, c in enumerate(fake.calls) if "tools/ds_review.py" in c)
        self.assertTrue(fake.calls[i].endswith("tools/ds_review.py components/A/B"))
        self.assertGreater(next(n for n, c in enumerate(fake.calls) if "-m lib.check" in c), i)  # checks fresh records
        fake = Fake(self.root)
        self.run_v(fake)
        self.assertTrue(any(c.endswith("tools/ds_review.py --all") for c in fake.calls))

    def test_review_mode_lines_reach_the_pass_line(self):
        fake = Fake(self.root, **{
            "tools/ds_review.py": (0, "summary: 1 component(s)\nreview: ledger-only mode (no local PDF) in 1 part(s): B\n"),
            "-m lib.check": (0, "review: ledger-only mode (no local PDF) in 1 part(s): B\n3 components, 0 errors, 0 warnings, "
                                "0 tolerated (datasheets absent), 0 allowlisted findings, 0 abstained\n")})
        rc, lines = self.run_v(fake)
        self.assertEqual(rc, 0, lines)
        self.assertIn("; review: ledger-only mode (no local PDF) in 1 part(s): B", lines[0])
        self.assertIn("; lib.check review: ledger-only mode", lines[0])

    def test_ds_review_failure_fails(self):
        rc, lines = self.run_v(Fake(self.root, **{"tools/ds_review.py": (1, "FAIL: poppler not found (pdftoppm)\n")}))
        self.assertEqual(rc, 1)
        self.assertIn("poppler not found", lines[1])

    def test_stale_review_record_fails_without_regen(self):
        # a PR that changes a part but not its review.toml must not pass by ds_review regenerating it in the runner
        fake = Fake(self.root)
        fake.effects["tools/ds_review.py"] = lambda: write(self.root / "components/A/B/review/review.toml", "d")
        rc, lines = self.run_v(fake)
        self.assertEqual(rc, 1, lines)
        self.assertIn("components/A/B/review/review.toml:1 changed by ds_review", lines[1])
        self.assertIn("--regen", lines[1])

    def test_review_changes_are_listed_with_regen(self):
        fake = Fake(self.root)
        fake.effects["tools/ds_review.py"] = lambda: write(self.root / "components/A/B/review/review.toml", "d")
        rc, lines = self.run_v(fake, regen=True)
        self.assertEqual(rc, 0, lines)
        self.assertIn("review: 1 file(s) changed in 1 part(s): A/B", lines[0])
        self.assertNotIn("SHOW THE HUMAN", lines[0])  # no part reported a delta
        fake.replies["tools/ds_review.py"] = (0, "components/A/B: UNSURE=3 | STALE=3 | fallback 0 | renders 0 | changed 1"
                                                 " | delta 3\nsummary: 1 component(s)\n")
        rc, lines = self.run_v(fake, regen=True)
        self.assertIn("SHOW THE HUMAN .review-cache/A/B/DELTA.md (3 row(s) need review)", lines[0])


if __name__ == "__main__":
    unittest.main()
