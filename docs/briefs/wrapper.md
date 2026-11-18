# Brief: wrapper (Haiku; generate, test and wire the Zener wrapper)

You receive: this brief's path, the component directory, a scratch dir, and the files you may write:
`tests/zen/<Value>_harness.zen` and rows in `tests/test_zen.py` `CASES`. You never edit `<Value>.zen` by hand and
never edit `component.toml` (report a TOML fix instead).

Load exactly these files:
- `docs/spec/wrapper.md` (what the generator emits, so you can predict the file)
- `.claude/skills/zener-wrapper/SKILL.md` (generate chain, harness rules, CASES, module use)
- `.claude/skills/zener-language/SKILL.md`
- the component's `component.toml`

Procedure:
1. `python3 -m lib.zen components/<Mfr>/<Value>`; read the wrapper top to bottom against the TOML: `# UNCHECKED:`
   list, pins, configs, one `_limit(...)` per checked pin.
2. If `lib.zen` prints `ERROR:`, report the TOML fix; do not edit `lib/zen.py`.
3. Write the harness and `CASES` rows per the skill: nominal pass; each check just outside its limit failing at its
   severity; one waiver for a warning-level check; one unset net (UNVERIFIED); ambient out of range and unset.
4. Prove one new case can fail by flipping its expectation once, then restore it.
5. `pcb build -Wstyle -Dwarnings components/<Mfr>/<Value>` (one directory per call), then
   `python3 -m unittest tests.test_zen -v`. Judge by exit code. Delete `__pycache__/` dirs.

Report: the check table (key, pins, severity, or the unchecked reason), the cases added, the flip proof, the verbatim
tail of the build and the unittest summary, and any TOML or generator problem found.

Stop and return: the generator needs a Zener construct it does not already emit (the main session decides; confirm
it first in stdlib source or a scratchpad build), or a datasheet number would have to be typed into Zener.
