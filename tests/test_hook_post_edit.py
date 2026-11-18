"""Tests for tools/hook_post_edit.py (fake runner, plus one real pcb fmt in a temp dir)."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parent.parent / "tools" / "hook_post_edit.py"
sys.path.insert(0, str(TOOL.parent))
import hook_post_edit as h  # noqa: E402


def write(p, text=""):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


class TestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.calls = []
        self.reply = (0, "")

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, cmd, cwd):
        self.calls.append(cmd)
        return self.reply

    def go(self, path):
        return h.handle({"tool_input": {"file_path": str(path)}}, self.root, self.runner)

    def test_zen_runs_pcb_fmt_on_that_file_only(self):
        f = write(self.root / "components/A/B/B.zen")
        self.assertEqual(self.go(f), (0, ""))
        self.assertEqual(self.calls, [["pcb", "fmt", str(f)]])

    def test_zen_fmt_failure_is_exit_2(self):
        f = write(self.root / "x.zen")
        self.reply = (1, "syntax error line 3\n")
        rc, msg = self.go(f)
        self.assertEqual(rc, 2)
        self.assertIn("syntax error line 3", msg)

    def test_zen_command_cannot_start_is_not_silent(self):
        self.reply = (127, "cannot run pcb")
        self.assertEqual(self.go(write(self.root / "x.zen"))[0], 2)

    def test_component_toml_runs_scoped_check(self):
        f = write(self.root / "components/A/B/component.toml")
        self.assertEqual(self.go(f), (0, ""))
        self.assertEqual(self.calls, [[sys.executable, "-m", "lib.check", "components/A/B"]])

    def test_calc_and_variants_are_checked_too(self):
        for n in ("calc.py", "variants.toml"):
            self.calls.clear()
            self.go(write(self.root / "components/A/B" / n))
            self.assertEqual(len(self.calls), 1, n)

    def test_check_failure_prints_only_failures(self):
        f = write(self.root / "components/A/B/component.toml")
        self.reply = (1, "A/B: ERROR: pin 1: missing 'cite'\nA/B: WARN: datasheet_file not found: x\nABSTAIN: noise\n"
                         "1 components, 1 errors, 0 warnings, 1 tolerated\n")
        rc, msg = self.go(f)
        self.assertEqual(rc, 2)
        self.assertIn("pin 1: missing 'cite'", msg)
        self.assertNotIn("datasheet_file", msg)
        self.assertNotIn("ABSTAIN", msg)

    def test_check_failure_with_no_error_line_still_reports(self):
        f = write(self.root / "components/A/B/component.toml")
        self.reply = (1, "Traceback (most recent call last):\nValueError: x\n")
        rc, msg = self.go(f)
        self.assertEqual(rc, 2)
        self.assertIn("ValueError: x", msg)

    def test_ignored_files(self):
        for p in (write(self.root / "README.md"), write(self.root / "components/A/B/README.md"),
                  write(self.root / "components/A/component.toml"), self.root / "gone.zen",
                  write(self.root / ".pcb/x.zen"), Path("/etc/hosts"), write(self.root / "lib/calc.py")):
            self.assertEqual(self.go(p), (0, ""), p)
        self.assertEqual(self.calls, [])
        self.assertEqual(h.handle({}, self.root, self.runner), (0, ""))
        self.assertEqual(h.handle({"tool_input": {}}, self.root, self.runner), (0, ""))

    def test_non_json_stdin_fails(self):
        p = subprocess.run([sys.executable, "-B", str(TOOL), "--root", str(self.root)], input="nope", capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_real_pcb_fmt_formats_only_the_edited_zen(self):
        f = write(self.root / "a.zen", 'x   =   1\n')
        other = write(self.root / "b.zen", 'y   =   2\n')
        p = subprocess.run([sys.executable, "-B", str(TOOL), "--root", str(self.root)],
                           input=json.dumps({"tool_input": {"file_path": str(f)}}), capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(f.read_text(), "x = 1\n")
        self.assertEqual(other.read_text(), "y   =   2\n")


if __name__ == "__main__":
    unittest.main()
