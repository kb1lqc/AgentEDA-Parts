#!/usr/bin/env python3
"""The whole after-change chain for zener-library as one command. Exit 0 = PASS, 1 = any FAIL.

Usage (repo root): python3 tools/verify.py [--all | DIR ...] [--regen] [--log-dir D] [--root R]

Steps, in order, each judged by exit code:
  1. pcb --version: major.minor must equal pcb-version in the root pcb.toml
  2. python3 -m lib.check           (0 components, 0 errors or warnings = FAIL; see lib.check)
  3. python3 -m lib.zen             (writes wrappers)
  4. python3 -m lib.readme          (writes component READMEs)
  5. pcb build -Wstyle -Dwarnings D for each component dir D: the dirs given, else all with --all, else every
     components/<Mfr>/<Value> with a change in `git status` (none found = FAIL: nothing was built)
  6. python3 -m unittest discover -s tests   ("Ran 0 tests" or no "Ran N tests" line = FAIL)
lib.zen and lib.readme must leave components/** and README.md byte-identical (content hashes before and after). A
difference is a FAIL unless --regen is given; then the changed files are listed and the run still passes.
Output: one PASS line with counts, or the first 5 failures as `file:line message` (`step: line` when the tool prints no
location). Full logs: --log-dir (default: a new $TMPDIR/zl-verify-* per run), one file per step; the log path is printed last.
__pycache__ directories are removed afterwards. Nothing is committed or restored.
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

MAX_FAILURES = 5
LOC_RE = re.compile(r"^(\S+?\.\w+):(\d+)(?::\d+)?:?\s+(.*\S)")
BAD_RE = re.compile(r"\berror\b|\bwarning\b|\bwarn\b|\bfail|✗|Traceback|\bERROR\b|\bFAIL", re.I)
SKIP_DIRS = {".git", ".pcb", "__pycache__"}


def run_cmd(cmd, cwd, env=None):
    """Run a command; return (rc, combined output). A command that cannot start is rc 127, never a pass."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=env)
    except OSError as e:
        return 127, f"cannot start {cmd[0]}: {e}"
    return p.returncode, p.stdout + p.stderr


def failure_lines(step, out, limit=MAX_FAILURES):
    """Up to `limit` failure lines of a step's output as `file:line message` (or `step: line`)."""
    found = []
    for line in out.splitlines():
        line = line.strip()
        if not line or not BAD_RE.search(line):
            continue
        m = LOC_RE.match(line)
        found.append(f"{m.group(1)}:{m.group(2)} {m.group(3)}" if m else f"{step}: {line}")
        if len(found) == limit:
            break
    return found or [f"{step}: failed with no diagnostic line (see log)"]


def tree_hashes(root):
    """sha256 of every file under components/ and of README.md, keyed by relative path (no .pcb, no __pycache__)."""
    out = {}
    root = Path(root)
    readme = root / "README.md"
    if readme.is_file():
        out["README.md"] = hashlib.sha256(readme.read_bytes()).hexdigest()
    for base, dirs, files in os.walk(root / "components"):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for f in sorted(files):
            p = Path(base) / f
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def diff_hashes(before, after):
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def changed_component_dirs(root, runner=run_cmd):
    """components/<Mfr>/<Value> dirs with any change in `git status --porcelain` (None if git cannot answer)."""
    rc, out = runner(["git", "status", "--porcelain", "--untracked-files=all", "--", "components"], root)
    if rc:
        return None
    dirs = set()
    for line in out.splitlines():
        parts = line[3:].split(" -> ")[-1].strip().strip('"').split("/")
        if len(parts) >= 4 and parts[0] == "components":
            dirs.add("/".join(parts[:3]))
    return sorted(dirs)


def all_component_dirs(root):
    return sorted(str(p.parent.relative_to(root)) for p in Path(root).glob("components/*/*/pcb.toml"))


def pcb_major_minor(text):
    m = re.search(r"(\d+)\.(\d+)\.\d+", text)
    return f"{m.group(1)}.{m.group(2)}" if m else None


def root_pcb_version(root):
    try:
        return tomllib.loads((Path(root) / "pcb.toml").read_text())["workspace"]["pcb-version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return None


def verify(root, dirs=None, all_dirs=False, regen=False, log_dir=None, runner=run_cmd):
    """Run the chain. Returns (exit code, summary text lines). `runner(cmd, cwd)` -> (rc, output) is injectable."""
    root = Path(root)
    # a fresh directory per run, so two runs at once never share logs (zener-library #19)
    log_dir = Path(log_dir) if log_dir else Path(tempfile.mkdtemp(prefix="zl-verify-"))
    log_dir.mkdir(parents=True, exist_ok=True)
    fails, counts, notes = [], {}, []
    logs = []

    def step(name, cmd):
        rc, out = runner(cmd, root)
        (log_dir / f"{len(logs) + 1:02d}-{name}.log").write_text(f"$ {' '.join(cmd)}\nexit {rc}\n{out}")
        logs.append(name)
        if rc:
            fails.extend(failure_lines(name, out))
        return rc, out

    def finish():
        lines = fails[:MAX_FAILURES]
        if fails:
            lines = [f"FAIL: {len(fails)} failure line(s), first {len(lines)}"] + lines
        else:
            lines = ["PASS: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + (f"; {'; '.join(notes)}" if notes else "")]
        lines.append(f"logs: {log_dir}")
        return (1 if fails else 0), lines

    # 1. pcb version
    want = root_pcb_version(root)
    rc, out = runner(["pcb", "--version"], root)
    (log_dir / "00-pcb-version.log").write_text(f"exit {rc}\n{out}")
    have = pcb_major_minor(out) if rc == 0 else None
    if want is None:
        fails.append("pcb.toml:1 missing or unreadable pcb-version in the root pcb.toml")
    elif have is None:
        fails.append(f"pcb --version: cannot read a version (exit {rc})")
    elif have != want:
        fails.append(f"pcb.toml:1 pcb-version {want} but installed pcb is {have}")
    if fails:
        return finish()
    counts["pcb"] = f"{have}"

    # 2. lib.check
    rc, out = step("lib.check", [sys.executable, "-m", "lib.check"])
    m = re.search(r"^(\d+) components, (\d+) errors, (\d+) warnings", out, re.M)
    if not m:
        fails.append("lib.check: no summary line printed")
    elif int(m.group(1)) == 0:
        fails.append("lib.check: zero components checked")
    else:
        counts["components"] = m.group(1)
    if fails:
        return finish()

    # 3-4. generators must leave the committed files alone
    before = tree_hashes(root)
    rz, _ = step("lib.zen", [sys.executable, "-m", "lib.zen"])
    rr, _ = step("lib.readme", [sys.executable, "-m", "lib.readme"])
    changed = diff_hashes(before, tree_hashes(root))
    if changed and not regen:
        fails.extend(f"{c}:1 changed by lib.zen/lib.readme (committed file is stale; rerun with --regen)"
                     for c in changed)
    elif changed:
        notes.append(f"regenerated {len(changed)} file(s): " + ", ".join(changed[:10]) + (" ..." if len(changed) > 10 else ""))
    if rz or rr:
        return finish()

    # 5. builds
    if dirs:
        todo = [str(d) for d in dirs]
    elif all_dirs:
        todo = all_component_dirs(root)
    else:
        todo = changed_component_dirs(root, runner)
        if todo is None:
            fails.append("git status: cannot list changed components (use --all or give dirs)")
            return finish()
    if not todo:
        fails.append("build: no component dirs to build (none changed; use --all or give dirs)")
        return finish()
    built = 0
    for d in todo:
        if not (root / d).is_dir():
            fails.append(f"{d}:1 not a directory")
            continue
        rc, _ = step("build-" + d.replace("/", "_"), ["pcb", "build", "-Wstyle", "-Dwarnings", d])
        built += rc == 0
    counts["built"] = f"{built}/{len(todo)}"
    if fails:
        return finish()

    # 6. unit tests
    rc, out = step("unittest", [sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    m = re.search(r"^Ran (\d+) tests?", out, re.M)
    if not m or int(m.group(1)) == 0:
        fails.append("unittest: no tests ran")
    else:
        counts["tests"] = m.group(1)
    return finish()


def clean_pycache(root):
    for base, dirs, _ in os.walk(root):
        dirs[:] = [d for d in dirs if d not in {".git", ".pcb"}]
        for d in [d for d in dirs if d == "__pycache__"]:
            shutil.rmtree(Path(base) / d, ignore_errors=True)
            dirs.remove(d)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dirs", nargs="*", help="component dirs to build (components/<Mfr>/<Value>)")
    ap.add_argument("--all", action="store_true", help="build every component")
    ap.add_argument("--regen", action="store_true", help="allow lib.zen/lib.readme to change files; report them")
    ap.add_argument("--log-dir")
    ap.add_argument("--root", default=Path(__file__).resolve().parent.parent)
    a = ap.parse_args(argv)
    root = Path(a.root).resolve()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        rc, lines = verify(root, a.dirs, a.all, a.regen, a.log_dir)
    finally:
        clean_pycache(root)
    print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main())
