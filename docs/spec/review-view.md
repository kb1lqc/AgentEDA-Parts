# Human review view and pinout stamp

The ledger, images and row stamps are in `docs/spec/review.md`.

## Human view (`lib/review_status.py`, `tools/review.py`, READMEs; never shows ledger states)
A tick means "this statement of the row matches the datasheet": values, column, conditions, temperature scope, unit
and how the library uses the row, not only the digits.

**Rows that matter** (computed from this repo only, so READMEs are the same in every checkout):
1. `kind = "abs_max"`, or `kind = "mechanical"` unless the key starts with `beam_load`, `solderability`, `mass` or
   `weight` (assembly and test acceptance criteria and mass are no package dimension or land row; they matter only
   through rule 3). The suffix after the prefix (`_c0g`, `_682_c0g`) is a variant of the row;
2. `kind = "thermal"` whose `symbol` contains `JC` (any case): RthJC, ZthJC, theta_JC; or whose `symbol`, upper case
   with non-alphanumerics removed, is `TJMAX` (maximum junction temperature). Other thermal and `rec_op`
   rows matter only through rule 3;
3. used: the key is a value in this part's `calc.py` INPUTS (a `.min`/`.typ`/`.max` suffix is dropped; the capacitor
   selection alias `tc` stands for every row `[part] tc_param` names, so `tc_x7r` and `tc_c0g` are used, see
   `docs/spec/capacitor.md`), a quoted
   string in `examples/*.py` (risk_rank's text match; over-marking is the safe direction), or the row has
   `check_pins` or `check_ambient`;
4. the pinout: one row named `pinout` for every part with `[[pin]]` entries (see "Pinout stamp").
An override (`[variant."X".param.K]` in variants.toml) is a row that matters when its base row matters or its key is in calc INPUTS (rule 3); it is listed as `variant.<V>.<key>`.
`--block` only narrows the page to the rows that block uses; it never changes a part's status.
A used value the ledger does not cover cannot be stamped: a used key in `variants.toml` that is not an
override, or resistor series values. It is listed as `not covered` (by file) and is not counted in k or n. Overrides are
never listed here: an override that matters is a row that matters (counted in k and n); one that does not is `REFERENCE`. Capacitor-series catalog values are covered by the export record (`docs/spec/capacitor.md`), not by rows here, and are not listed. The name `pinout` is reserved: `[param.pinout]` is a lib.check error.

**Status per row:** `checked` (ledger `HUMAN_VERIFIED` and a current human stamp, the rule of
`lib.human_review_needed()`; READMEs read the ledger only) · `needs check` (a row that matters, not checked) ·
`reference` (every other row). **Per part (one directory, family or not):** k = checked rows that matter, n = rows
that matter (each override that matters counts, no dedupe), M = all rows; released when k == n > 0. A row whose hash changes after its stamp is `needs check` again.

**Part README** line 5: `Released: all <n> rows that matter checked (<M> rows in all).` or
`Checked by a person: <k> of <n> rows that matter (<M> rows in all). Review: python3 tools/review.py <Value>`,
plus `; <c> used values not covered (<files>)` when c > 0. `released` is unchanged (human rows only). The `Checked` column stays.
**Top README:** a generated table between `<!-- review-status:start -->` and `<!-- review-status:end -->`: Part,
Status (`released` or `k of n`), Review command; one line per component directory, sorted by path.

**Statement card** (one per row; built only from committed fields, no model text). Title: `<symbol> — <name>`.
- **Value:** min, typ, max as the README prints them, with `min_ref` / `max_ref`. A `sym` row, or min = -max, prints `±<max>`. No `unit` prints `unitless`.
- **Conditions:** the `conditions` field, or "none printed".
- **Temperature** (only for scope `25C`, `full`, `partial`): "at 25 °C only", "over the full temperature range", or "over part of the range: see conditions".
- **Used by:** calc.py `function (argument)`, the Zener check on pins, the examples file.
- **Datasheet columns:** when `note` says "magnitude order" (or "magnitude-order") and quotes printed columns ("MIN column -10", "typ printed -290"), one line per quoted column: `printed <MIN|TYP|MAX> <value> = stored <max|typ|min> <value>`, so the reviewer ticks each printed column against the page image. A note that quotes no column number gets no line.
- **How we read it:** `note`, shown open with ⚠ when the row has `unchecked` or the note says "read as", "applied as" or "inferred". Display only, never in the TOML: `degC`→°C, `ohm`/`kohm`/`Mohm`→Ω/kΩ/MΩ, `u`-prefixed units→µ, `+/-`→±.

The pinout card is the pin table (number, name, type, function). A row with no min, typ or max is `Fix first`, with no tick box (it counts in n).

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
