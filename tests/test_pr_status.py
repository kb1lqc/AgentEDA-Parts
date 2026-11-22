"""tools/pr_status.py: the PR review-status comment (docs/spec/review-view.md "PR comment"), on real git repos."""
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
import pr_status as P  # noqa: E402

G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
TOML = '[part]\nvalue = "X"\n\n[param.a]\nkind = "abs_max"\ncite = "DS p.1"\nvalue = 1\n'


class Repo(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.r = Path(self._t.name)
        subprocess.run(G + ["init", "-q"], cwd=self.r, check=True)

    def tearDown(self):
        self._t.cleanup()

    def commit(self, files):
        for p, t in files.items():
            f = self.r / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(t)
        subprocess.run(G + ["add", "-A"], cwd=self.r, check=True)
        subprocess.run(G + ["commit", "-qm", "c", "--allow-empty"], cwd=self.r, check=True)
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.r, capture_output=True, text=True).stdout.strip()

    def run_p(self, base):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = P.main(["--root", str(self.r), "--base", base])
        return rc, buf.getvalue()


class Comment(Repo):
    def test_changed_component_prints_marker_line_and_command(self):
        base = self.commit({"README.md": "x"})
        self.commit({"components/Acme/X/component.toml": TOML, "components/Acme/Y/component.toml": TOML,
                     "docs/other.md": "y"})
        rc, out = self.run_p(base)
        self.assertEqual(rc, 0, out)
        lines = out.splitlines()
        self.assertEqual(lines[0], "<!-- review-status -->")
        self.assertIn("- X: 0 of 1 rows that matter checked", out)
        self.assertIn("- Y: ", out)
        self.assertEqual(lines[-1], "Review: python3 tools/review.py X Y")

    def test_no_component_change_prints_nothing(self):
        base = self.commit({"components/Acme/X/component.toml": TOML})
        self.commit({"docs/other.md": "y"})
        self.assertEqual(self.run_p(base), (0, ""))

    def test_only_changed_directories(self):
        base = self.commit({"components/Acme/X/component.toml": TOML, "components/Acme/Y/component.toml": TOML})
        self.commit({"components/Acme/Y/notes.txt": "n"})
        rc, out = self.run_p(base)
        self.assertNotIn("- X:", out)
        self.assertIn("- Y:", out)
        self.assertEqual(out.splitlines()[-1], "Review: python3 tools/review.py Y")

    def test_deleted_component_is_skipped(self):
        base = self.commit({"components/Acme/X/component.toml": TOML})
        subprocess.run(G + ["rm", "-rq", "components/Acme/X"], cwd=self.r, check=True)
        subprocess.run(G + ["commit", "-qm", "rm"], cwd=self.r, check=True)
        self.assertEqual(self.run_p(base), (0, ""))

    def test_bad_base_is_an_error(self):
        self.commit({"README.md": "x"})
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = P.main(["--root", str(self.r), "--base", "nosuchref"])
        self.assertEqual(rc, 1)

    def test_line_matches_readme_line_numbers(self):
        from lib import review_status
        base = self.commit({"README.md": "x"})
        self.commit({"components/Acme/X/component.toml": TOML})
        r = review_status.review(self.r / "components/Acme/X", self.r, local_pdf=False)
        want = review_status.summary("X", r)[0] + review_status.not_covered_text(r).split(" (")[0]
        _, out = self.run_p(base)
        self.assertIn("- " + want, out.splitlines())


if __name__ == "__main__":
    unittest.main()
