#!/usr/bin/env python3
"""Print the PR review-status comment (docs/spec/review-view.md "PR comment"); never stamps anything.

Usage (repo root, CI on pull requests):
  python3 tools/pr_status.py --base SHA [--head HEAD] [--root R]
Lists the component directories (components/<Mfr>/<Value>/) that `git diff --name-only BASE...HEAD` touches and that
still have a component.toml, then prints the comment markdown: the `<!-- review-status -->` marker, one line per
directory (`- <Value>: released` or `- <Value>: <k> of <n> rows that matter checked`, plus `; <c> used values not
covered`), and `Review: python3 tools/review.py <Values>`. Numbers come from lib.review_status (ledger only, no PDFs),
the same as line 5 of the part README. Prints nothing when no component changed. Exit 0 = ok, 1 = error.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import review_status  # noqa: E402

MARKER = "<!-- review-status -->"


def changed_dirs(root, base, head):
    """Sorted component directories (relative to root) changed between the merge base of BASE and HEAD, and HEAD."""
    r = subprocess.run(["git", "-C", str(root), "diff", "--name-only", "-z", "--no-renames", f"{base}...{head}"],
                       capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git diff failed: {r.stderr.decode(errors='replace').strip()}")
    dirs = set()
    for name in r.stdout.decode().split("\0"):
        parts = name.split("/")
        if len(parts) > 3 and parts[0] == "components":
            dirs.add("/".join(parts[:3]))
    return sorted(d for d in dirs if (Path(root) / d / "component.toml").is_file())


def comment(root, dirs):
    """The comment markdown for the component directories dirs ('' when there are none)."""
    if not dirs:
        return ""
    lines, values = [MARKER, ""], []
    for d in dirs:
        value = Path(d).name
        r = review_status.review(Path(root) / d, root, local_pdf=False)
        c = sum(len(v) for v in r["not_covered"].values())
        head = f"{value}: released" if r["released"] else review_status.summary(value, r)[0]
        lines.append(f"- {head}" + (f"; {c} used values not covered" if c else ""))
        values.append(value)
    lines += ["", f"Review: python3 tools/review.py {' '.join(values)}"]
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    try:
        out = comment(a.root, changed_dirs(a.root, a.base, a.head))
    except Exception as e:  # any failure: no comment text, exit 1
        print(f"pr_status: {e}", file=sys.stderr)
        return 1
    print(out, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
