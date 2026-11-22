# Human review view and pinout stamp

The ledger, images and row stamps are in `docs/spec/review.md`.

## Human view (`lib/review_status.py`, `tools/review.py`, READMEs; never shows ledger states)
A tick means "this statement of the row matches the datasheet": values, column, conditions, temperature scope, unit
and how the library uses the row, not only the digits.

**Rows that matter** (computed from this repo only, so READMEs are the same in every checkout):
1. `kind = "abs_max"` or `kind = "mechanical"`;
2. `kind = "thermal"` whose `symbol` contains `JC` (any case): RthJC, ZthJC, theta_JC; or whose `symbol`, upper case
   with non-alphanumerics removed, is `TJMAX` (maximum junction temperature). Other thermal and `rec_op`
   rows matter only through rule 3;
3. used: the key is a value in this part's `calc.py` INPUTS (a `.min`/`.typ`/`.max` suffix is dropped), a quoted
   string in `examples/*.py` (risk_rank's text match; over-marking is the safe direction), or the row has
   `check_pins` or `check_ambient`;
4. the pinout: one row named `pinout` for every part with `[[pin]]` entries (see "Pinout stamp").
`--block` only narrows the page to the rows that block uses; it never changes a part's status.
A used value the ledger does not cover cannot be stamped: a used key in `variants.toml`, `catalog.csv` or resistor
series values, and every `variants.toml` override of a row that matters. It is listed as `not covered` (by file) and is
not counted in k or n. The name `pinout` is reserved: `[param.pinout]` is a lib.check error.

**Status per row:** `checked` (ledger `HUMAN_VERIFIED` and a current human stamp, the rule of
`lib.human_review_needed()`; READMEs read the ledger only) · `needs check` (a row that matters, not checked) ·
`reference` (every other row). **Per part (one directory, family or not):** k = checked rows that matter, n = rows
that matter, M = all rows; released when k == n > 0. A row whose hash changes after its stamp is `needs check` again.

**Part README** line 5: `Released: all <n> rows that matter checked (<M> rows in all).` or
`Checked by a person: <k> of <n> rows that matter (<M> rows in all). Review: python3 tools/review.py <Value>`,
plus `; <c> used values not covered (<files>)` when c > 0. The `Checked` column stays.
**Top README:** a generated table between `<!-- review-status:start -->` and `<!-- review-status:end -->`: Part,
Status (`released` or `k of n`), Review command; one line per component directory, sorted by path.

**Statement card** (each row; built only from committed fields, no model text). Title `<symbol> — <name>`; lines:
`Value` (min/typ/max as the README prints them with min_ref/max_ref; a `sym` row or min = -max prints `±<max>`; no
`unit` prints `unitless`) · `Conditions` (`conditions`, or "none printed") · `Temperature` only for scope `25C` ("at
25 °C only"), `full` ("over the full temperature range"), `partial` ("over part of the range: see conditions") ·
`Used by` (calc.py `function (argument)`, Zener check on pins, examples file). `note` is folded under "How we read
it", shown open with ⚠ when the row has `unchecked` or the note says "read as", "applied as" or "inferred". Display
only, never in the TOML: `degC`→°C, `ohm`/`kohm`/`Mohm`→Ω/kΩ/MΩ, `u`-prefixed units→µ, `+/-`→±. The pinout card is
the pin table (number, name, type, function). A row with no min, typ or max is `Fix first`, no tick box (counts in n).

**Page** (`python3 tools/review.py` = every part; `<Value> ...` or `--block <B>` narrows it): a status line per
part first; then per part, fewest `needs check` rows of the whole part first (released parts folded), three sections: **Limits**
(rules 1-2 except mechanical), **Used by equations** (rule 3 rows not in Limits), **Pins & package** (pinout and
mechanical). Each row: statement, header/row/footnote crops (pinout: every page its pins cite), one tick box. Each
image file has one URL per page, however many rows show it; an image path outside `.review-cache/<Mfr>/<Value>/` is
not served. Rows `tools/stamp.py` would refuse show no tick box.
**Locate** (display only; never evidence, never committed): a row without an `auto` crop shows the full page of the
cited sheet and page (150 dpi gray render, cached like fallback pages) with boxes drawn by the browser over the image
(no pixel edits). Boxes: text-layer lines of that page (`pdftotext -bbox-layout`) holding every min/typ/max number of
the row compared by value (`0.90` = `0.9`; a `sym` row also matches its unsigned max), and when some line prints them adjacent and in
order (`0.9 to 1.4`, `±100`) only such lines are kept; else lines holding the symbol
and a word of the cite's row label; at most 5, ambiguity shown as several boxes; none: "row not located, find it on
the page". Cached in `.review-cache/<Mfr>/<Value>/locate.json` per render_key. The view opens zoomed to the boxes;
a click shows the whole page.

## Pinout stamp
`[pinout]` in component.toml holds `verified = "human:<github-login> <YYYY-MM-DD> page-image pinout <pdf-sha256[:12]>
pins <pins-hash[:12]>"`. Pins hash: SHA-256 of `json.dumps([[pin]] list, sort_keys=True, separators=(",", ":"))`.
review.toml `[pinout]`: hash, stamp, stamp_hash, pdf_sha256, state; then one `[[pinout.page]]` per distinct page any
pin cites, in page order: sheet (only when not the main file), pdf_page, image (`evidence/pinout_p<n>.png`, full page
render), image_sha256, image_bytes, dpi, render_key. Same states and checks as a row (`HUMAN_VERIFIED`, `STALE` when
any pin changes, `PDF_CHANGED`, `NEW`); a STALE or PDF_CHANGED human pinout is listed in DELTA.md and github-issue.md
like a row. `tools/stamp.py <Value>:pinout` writes it; `tools/check_stamps.py` checks it like a row stamp.

## PR comment (`tools/pr_status.py`, `.github/workflows/review-status.yml`)
On a pull request from this repo (not a fork), one comment marked `<!-- review-status -->`, created or updated in
place (never duplicated): one line per component directory the PR changes, `<Value>: released` or `<Value>: <k> of
<n> rows that matter checked`, plus `; <c> used values not covered` when c > 0, then `Review: python3 tools/review.py
<Values>`. Computed like the READMEs (ledger only, committed files, no PDFs); never stamps. No changed component: no
comment (an existing one is deleted). Workflow permissions: contents read, pull-requests write.
