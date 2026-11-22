# Contributing to the component library

## What this library is

- It holds electronic parts as data: every pin, rating and electrical number from the datasheet, with its page cite.
- Each part also has a short Python file of datasheet equations, and a generated Zener (`.zen`) file, the input
  format of the circuit-design tool.
- Other people's circuit blocks import these parts, so a wrong number here reaches every design that uses it.

## Why a person must check the numbers

Worst-case analysis uses these numbers as limits. A typo or a misread table can pass a bad design.

- A person opens the datasheet page and compares each number with the file.
- Machine checks do not count as this check. A machine stamp (a `verified` value such as `sonnet-audit ...`), or a
  text-layer match, is a machine result. It is not a human check.
- A stamp is the `verified` line that records a person's check (see Stamp the row). Only a person runs
  `tools/stamp.py`, and only after checking the row. Agents never stamp.

## Setup

What you need:

- Python 3.11 or newer, with matplotlib: `python3 -m pip install matplotlib`
- poppler, for page images: `brew install poppler` (macOS) or `sudo apt-get install poppler-utils` (Debian/Ubuntu)
- pcb 0.4.x, the Zener toolchain. Install it from https://docs.pcb.new. This repo pins `pcb-version = "0.4"` in
  `pcb.toml`. Check with `pcb --version`. Expected: a 0.4.x version.
- GitHub CLI, signed in: `brew install gh`, then `gh auth login`
- KiCad conversion tools only if a vendor file is Altium-only. See `docs/KICAD.md`.

Get the code and check the tools:

```sh
git clone https://github.com/kb1lqc/zener-library.git
cd zener-library
python3 tools/verify.py --help
python3 -c "import matplotlib; print(matplotlib.__version__)"
```

Expected: the verify help text, then a matplotlib version number.

Work on a branch, never on `main`:

```sh
git switch -c add/<Value>
```

## Add a component

Read `docs/notes/workflow.md` first. It shows the part types (single part, family, value series, catalog series).

1. **Check the part.** Note the datasheet revision and date. Note the package and grade. If the datasheet covers
   several packages or grades and you do not know which one you need, ask the maintainer before you go on.
2. **Put the files in place.**
   - Datasheet PDF: `docs/datasheets/` (git-ignored, never committed)
   - Vendor symbol (the schematic picture), footprint (the board land pattern) and STEP (the 3D model):
     `docs/vendor/<Value>/` (git-ignored)
3. **Make the part folder.** Use the scaffold. The `--datasheet-url` value is required. It is recorded, not fetched.

   ```sh
   python3 tools/scaffold.py <Mfr> <Value> --datasheet-url <https link to the PDF>
   ```

   This creates `components/<Mfr>/<Value>/` with a `component.toml` template.
4. **Fill `component.toml`.** Every number gets a row with min, typ, max, unit, conditions, scope and a `cite` that
   names the page. Format: `docs/SPEC.md` (index) and `docs/spec/`. Defaults for judgement calls: `docs/spec/extract.md`.
   Do not copy a number from memory or from another part.
5. **Write `calc.py`.** One function per datasheet equation, each citing its page. Format: `docs/spec/lib-api.md`.
6. **Fix the symbol and footprint.** Rules: `docs/KICAD.md`.
7. **Generate the files.** Do not edit these by hand. They are rebuilt from the data.

   ```sh
   python3 -m lib.zen
   python3 -m lib.readme
   ```

8. **Run the full check.**

   ```sh
   python3 tools/verify.py
   ```

   With no folder names, it checks the parts you changed. Expected: one line that starts with `PASS`. If it fails,
   it prints the first 5 problems and a log path. Fix them and run it again. If you changed no part, it fails with
   `nothing was built`: pass the folder, e.g. `python3 tools/verify.py components/<Mfr>/<Value>`.
   If it says a `review.toml` is stale (expected after you change a part, or for a new part), run it again with
   `--regen` and commit the updated `review.toml`. CI fails a PR whose `review.toml` is stale.
9. **Open a pull request.** Push the branch and open the PR with `gh pr create`. CI runs `tools/verify.py --all`.
   The review record (see below) lists rows that still need a human check. Those rows do not fail CI.
   A bot comment on the PR (`tools/pr_status.py`, workflow `review-status`) shows `<k> of <n> rows that matter checked` for each part the PR changes, with the `tools/review.py` command.

## Verify parameters (the human check)

### One command, tick, click

In your own terminal (not an agent's), from the library root, with the datasheet PDFs in `docs/datasheets/`:

```sh
python3 tools/review.py                                 # every part
python3 tools/review.py INA229AIDGS                     # or one or more parts
python3 tools/review.py --block INA229HighSideMonitor   # or only the rows a circuit block reads
```

`--block` reads the block's `library-inputs.json` from the circuit-blocks checkout next to this one (`../ina229`, else
`../circuit-blocks`; or `--blocks-repo <path>`); it narrows the page, never a part's status. A page opens in your
browser:

- First a status line per part, in the form `<Value>: <k> of <n> rows that matter checked` (k checked, n rows that
  matter; the numbers change as rows are stamped, so none are quoted here). The rows that matter are
  the absolute maximums, mechanical rows, junction-to-case and maximum junction temperature, every value the library
  uses (calc.py, examples, Zener checks) and the pinout. A part is released when all of them are checked.
- Then, per part (fewest rows to check first; released parts folded away), three sections: Limits, Used by equations,
  Pins & package. Each row shows its statement (values, column, conditions, scope, unit, where the library uses it),
  the datasheet crops (table header, the row, footnotes; for the pinout every page its pins cite) and one tick box. Each
  image is loaded once however many rows show it.
- The pinout is one row: tick it when the pin table (number, name, type, function) matches the pin table pages.
- A row with no tick box (shown with the reason) cannot be stamped yet: fix the row or its cite (a row with no
  min, typ or max shows `Fix first` and still counts as a row to check), or run `python3 tools/verify.py`.

Compare each statement with its image, tick the rows that match, and press **Stamp N rows and open PR**. The tool then
shows each command as it runs it: it needs a clean working tree (untracked files are fine), fetches `origin`, makes a
branch `review/<parts>-<login>-<date>` from `origin/main`, runs `tools/stamp.py` on the ticked rows, runs
`tools/verify.py --regen` on those parts, commits their `component.toml`, `review/review.toml` and `README.md`,
pushes and opens the PR with `gh`. If `stamp.py` refuses, it goes back to your branch and deletes the new one. If
`verify` fails, it stops and leaves the branch for you, uncommitted. `--dry-run` is for a person trying the
page: it shows the commands and runs none. Agents don't run `review.py` (`.claude/settings.json` denies it; its
`CLAUDECODE` refusal lets only `--dry-run` through, for the tests).

### What to compare

- value, and sign (a minus sign matters)
- unit
- min, typ and max, in the right column (read the table header image)
- conditions (temperature, voltage, load, package)
- footnotes that change the value
- the cite: right table, right page, right row name

### Three outcomes

- **Matches:** tick it.
- **Wrong:** leave it unticked. Fix the TOML with the correct number and cite, run `tools/verify.py --regen`, and
  commit `review.toml` too. Never stamp a wrong row.
- **Unclear:** leave it unticked and open an issue (`.review-cache/<Mfr>/<Value>/github-issue.md` has the text).

### What a stamp is

Each stamped row gets one line, bound to the datasheet file and the row's numbers:

```toml
verified   = "human:<github-login> <YYYY-MM-DD> page-image ds_review <pdf-sha256 first 12> row <row-hash first 12>"
```

The pinout has its own table in `component.toml`, bound to the pin list and the PDF:

```toml
[pinout]
verified = "human:<github-login> <YYYY-MM-DD> page-image pinout <pdf-sha256 first 12> pins <pins-hash first 12>"
```

If the row (or any pin) or the PDF changes later, the stamp stops matching and the row needs a check again. A stamp is an
accountability record (who says they checked, against which file and numbers), not proof. CI (`tools/check_stamps.py`)
fails a PR whose added human stamp names anyone other than the PR author, so stamp only as yourself. Agents are blocked
from `tools/stamp.py` and `tools/review.py` (both refuse when `CLAUDECODE` is set, and `.claude/settings.json` denies
them), but a stamp typed by hand passes if it reproduces both hashes; `main` needs branch protection that requires a PR.

### Fallback: stamp by hand

The evidence for one part is in `.review-cache/<Mfr>/<Value>/` (local only; `python3 tools/verify.py
components/<Mfr>/<Value>` builds it): `README.md` lists the rows, `params/<key>.md` shows each row's TOML, crop and
page. Then:

```sh
python3 tools/stamp.py INA229AIDGS:vin_diff_abs INA229AIDGS:pinout   # or --from <file>, one <Value>:<key> per line
python3 tools/verify.py --regen components/TexasInstruments/INA229AIDGS
```

Commit `component.toml`, `review/review.toml` and `README.md`, and name the rows in the PR text. `--who
<github-login>` overrides the login read from `gh api user`.

## Troubleshooting: `tools/stamp.py` refusals

Stamping is all or nothing. If one row is refused, no row is written.

- `is not a GitHub login`: `--who` must be a GitHub login (1 to 39 letters, digits, or single hyphens between letters or digits).
- `gh is not installed`, or `gh api user timed out`: install `gh`, or pass `--who <github-login>`.
- `gh api user failed`: run `gh auth login`, or pass `--who <github-login>`.
- `no <Value>:<key> given`: you passed no rows.
- `expected <Value>:<key>`: write the row as `Value:key`, with one colon.
- `no component directory`: use the folder name, not a variant name.
- `component.toml is not valid TOML`: fix the file first.
- `no [param.<key>] in component.toml`: the key is wrong. Check the spelling. `no [[pin]]`: `<Value>:pinout` needs pins.
- `no readable review/review.toml (no review record)`, or `no review record for this row`: run `python3 tools/verify.py` for the folder.
- `review record is older than the committed row` (or `pins`): run `python3 tools/verify.py`, then stamp again.
- `status DISAGREE` or `status NOT_FOUND`: fix the row or its cite first. Do not stamp.
- `running inside Claude Code (CLAUDECODE is set)`: run `tools/stamp.py` yourself, in your own terminal.
- `no local evidence image for this row`: run `python3 tools/verify.py` (needs the PDF in `docs/datasheets/`).
- `evidence image differs from the ledger`: run `python3 tools/verify.py`.
- `ledger names no PDF SHA-256 for this row's sheet`: run `python3 tools/verify.py` for the folder.
- `local PDF docs/datasheets/<file> missing`: put the datasheet in `docs/datasheets/`.
- `differs from the PDF the evidence was rendered from`: the PDF on your disk is not the one the check used. Get the
  right file, then run `python3 tools/verify.py`.
- `verified line is not a one-line string`: the stamp line was edited by hand. Put it back on one line.
- `edit would change more than the stamp`: something else in the row changed. Ask the maintainer.
- `nothing written`: none of the rows were stamped. Fix the first refusal and run again.
