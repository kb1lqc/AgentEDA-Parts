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

## Verify parameters (the human check)

### Where the list comes from

- **For a part in this repo:** run `python3 tools/verify.py components/<Mfr>/<Value>`, then open
  `.review-cache/<Mfr>/<Value>/README.md` (local only; needs the PDF). It has a table of rows to review, and `DELTA.md`
  next to it lists human-stamped rows that changed since their stamp. Only `review/review.toml` is committed.
- **For circuit blocks:** the `human-review-packet` artifact from the circuit-blocks CI run. It has one HTML page per
  block. See the circuit-blocks `CONTRIBUTING.md`.

### Read one item

For each row, open `.review-cache/<Mfr>/<Value>/params/<key>.md`. It is local only: page images are vendor excerpts and
are never committed. `python3 tools/verify.py` (or `python3 tools/ds_review.py components/<Mfr>/<Value>`) builds it
when the datasheet PDF is in `docs/datasheets/`. It shows:

- the TOML lines as committed,
- the evidence image (the table row, cut from the PDF page),
- the source page (printed page and PDF page).

The ledger, `review/review.toml`, records each row's state: `HUMAN_VERIFIED` (a current human stamp),
`MACHINE_CHECKED` (a machine stamp, not a human check), `NEW`, `STALE`, `PDF_CHANGED`, `UNVERIFIED` or `NOT_COVERED`.

In the circuit-blocks packet, each row sits in one tier. A **row crop** is the image of one table row cut from the
datasheet page. The **text check** (`AGREE_TEXT_CHECK`) compares the TOML numbers with the PDF's text layer only. It is
not a human check. The tier tells you how much to trust the row crop:

| Tier | Meaning | What to do |
|---|---|---|
| Fix first | DISAGREE, NOT_FOUND, or an old record | Fix the cite or the TOML first. Do not stamp. |
| Tier 1 | Automatic row crop, and the text check agrees | Check the image against the TOML. |
| Tier 2 | Automatic row crop, text check unsure | Read the image closely. |
| Tier 3 | Table or page image, not a single row | Read the table header and footnotes too. |
| Page lookup | No usable image | Open the PDF page yourself. |
| No review record | The row has no record yet | Ask the maintainer, or run `tools/verify.py` in the zener-library checkout for that part. Do not stamp. |

### What to compare

Check each of these against the page:

- value, and sign (a minus sign matters)
- unit
- min, typ and max columns, in the right column
- conditions (temperature, voltage, load, package)
- footnotes that change the value
- the cite: right table, right page, right row name

### Three outcomes

- **Matches:** stamp the row (below).
- **Wrong:** fix the TOML with the correct number and cite. Run `tools/verify.py --regen` and commit `review.toml` too.
  Never stamp a wrong row.
- **Unclear:** leave the row alone. Open an issue. The issue text can use `.review-cache/<Mfr>/<Value>/github-issue.md` if it exists.

### Stamp the row

Stamp only the rows you looked at, on the page image, in the PDF. Never stamp a row you did not look at.

```sh
python3 tools/stamp.py INA229AIDGS:vin_diff_abs
```

Refer to a row as `<Value>:<key>`. Several rows at once: put one `<Value>:<key>` per line in a file outside the repo,
and run `python3 tools/stamp.py --from <file>` (`# comments` allowed).

Your GitHub login is read from `gh` (`gh api user --jq .login`). To use another login, add `--who <github-login>`.

It writes one line in the row, with a placeholder for each value:

```toml
verified   = "human:<github-login> <YYYY-MM-DD> page-image ds_review <pdf-sha256 first 12> row <row-hash first 12>"
```

- The login is the person who checked.
- The date is the day of the check.
- The PDF hash ties the stamp to the exact datasheet file.
- The row hash ties the stamp to the exact numbers.

If you later edit the row, or the PDF changes, the stamp stops matching. The row goes back to `STALE` (the stamp no
longer matches the row) or `PDF_CHANGED` (the PDF file differs). You must check the row again and stamp it again.
Stamping is not automatic.

Then run the check again with `--regen` (it records your stamp in `review.toml`), and commit both files:

```sh
python3 tools/verify.py --regen components/<Mfr>/<Value>
```

Expected output from `tools/stamp.py` (one line per row, then a `next:` line):

```
INA229AIDGS:vin_diff_abs: (no stamp) -> human:<github-login> <date> page-image ds_review <pdf12> row <row12>
next: python3 tools/verify.py --regen components/TexasInstruments/INA229AIDGS
```

CI runs `tools/check_stamps.py` on every pull request. It fails the PR if an added human stamp names anyone
other than the PR author. Stamp only as your own GitHub login, and never stamp another person's check.

What a stamp is: an accountability record (who says they checked, against which file and numbers), not proof. Agents
are blocked from `tools/stamp.py` (it refuses when `CLAUDECODE` is set, and `.claude/settings.json` denies it), but a
stamp typed by hand passes if it reproduces both hashes. The stamp check runs only on pull requests, so `main` needs
branch protection that requires a PR. Signed commits with a hardware key are the planned stronger control.

Open the PR with the stamps and the TOML fixes together, or in separate PRs. Name the rows you checked in the PR text.

## Troubleshooting: `tools/stamp.py` refusals

Stamping is all or nothing. If one row is refused, no row is written.

- `is not a GitHub login`: `--who` must be a GitHub login (1 to 39 letters, digits, or single hyphens between letters or digits).
- `gh is not installed`, or `gh api user timed out`: install `gh`, or pass `--who <github-login>`.
- `gh api user failed`: run `gh auth login`, or pass `--who <github-login>`.
- `no <Value>:<key> given`: you passed no rows.
- `expected <Value>:<key>`: write the row as `Value:key`, with one colon.
- `no component directory`: use the folder name, not a variant name.
- `component.toml is not valid TOML`: fix the file first.
- `no [param.<key>] in component.toml`: the key is wrong. Check the spelling.
- `no readable review/review.toml (no review record)`, or `no review record for this row`: run `python3 tools/verify.py` for the folder.
- `review record is older than the committed row`: run `python3 tools/verify.py`, then stamp again.
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
