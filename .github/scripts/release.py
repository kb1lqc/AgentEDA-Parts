#!/usr/bin/env python3
"""Create the release tags `pcb publish --check` proposes, exactly as printed (annotated, name and message), on HEAD.
Usage: release.py <plan.json> [--version vX.Y.Z --label <repo name>] [--push]
Only package paths under components/ or blocks/ are tagged; the root package wave (it would rewrite the root pcb.toml)
is never tagged here (circuit-blocks #9). --version adds the repo release tag "<label> vX.Y.Z" on the same commit.
Without --push it only prints the plan. Prints a Markdown table for the job summary; exits 1 on any problem."""
import json
import re
import subprocess
import sys


def git(*a):
    return subprocess.run(["git", *a], check=True, capture_output=True, text=True).stdout.strip()


def main(argv):
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    push = "--push" in argv
    version = argv[argv.index("--version") + 1] if "--version" in argv else ""
    label = argv[argv.index("--label") + 1] if "--label" in argv else ""
    plan = json.load(open(argv[0]))
    tags = [(p["tag"], p["message"]) for p in plan.get("packages", [])
            if p.get("path", "").startswith(("components/", "blocks/"))]
    skipped = [p["tag"] for p in plan.get("packages", []) if not p.get("path", "").startswith(("components/", "blocks/"))]
    if version:
        if not re.fullmatch(r"v\d+\.\d+\.\d+", version) or not label:
            print(f"❌ --version must look like v1.2.3 and needs --label (got {version!r}, {label!r})")
            return 1
        tags.append((version, f"{label} {version}"))
    existing = set(git("tag").split())
    clash = [t for t, _ in tags if t in existing]
    head = git("rev-parse", "--short", "HEAD")
    print(f"## {'🚀 Released' if push else '📋 Release plan (dry run)'}: {len(tags)} tag(s) on `{head}`", "")
    if not tags:
        print("Nothing to release: every package is already tagged at its current content.")
        return 0
    print("| Tag | Message |", "|---|---|", *[f"| `{t}` | {m} |" for t, m in tags], sep="\n")
    if skipped:
        print("", f"Not tagged on purpose (root package wave, circuit-blocks #9): {', '.join(f'`{t}`' for t in skipped)}")
    if clash:
        print("", f"❌ Already exist: {', '.join(clash)}")
        return 1
    if push:
        for t, m in tags:
            git("tag", "-a", t, "HEAD", "-m", m)
        git("push", "origin", *[t for t, _ in tags])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
