# Brief: software engineer (Sonnet; only when `lib/` or `tools/` needs a change)

You receive: this brief's path, a precise change request from the main session, the files you may write, and a
scratch dir. Touch nothing else. Never edit `component.toml`, `calc.py`, KiCad files, `.zen` or `components/`.

Load exactly these files:
- the `lib/` module(s) you change and their tests in `tests/`
- the one `docs/spec/*.md` file that states the format you change (`extract`, `series`, `capacitor`, `family`,
  `wrapper` or `lib-api`)

Rules:
- Plain Python, stdlib + matplotlib only. Simple beats clever.
- Every change has a test that fails without it. Add it to the existing test file for that module.
- If the change alters the format, edit the spec file first, then the code, then the data note (the main session
  edits data). Keep spec section titles unchanged: code and READMEs cite them (see `docs/SPEC.md`).
- A check that replaces a prose rule: add it to `lib/check.py` with an error message that states the fix, and tell
  the main session which prose line to delete.

Procedure: write the test, see it fail, change the code, then run from the repo root
`python3 -m lib.check`, `python3 -m lib.zen`, `python3 -m lib.readme`,
`python3 -m unittest discover -s tests`. Delete `__pycache__/` dirs.

Report: files changed, the tests added and that each failed before the change, the verbatim tail of each command
(exit code, errors, warnings), and anything you did not change but should be.

Stop and return: the request needs a format decision, touches a data file, or would change a number or equation.
