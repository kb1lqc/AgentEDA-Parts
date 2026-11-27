# Datasheet review record (`review/`)

Written only by `tools/ds_review.py` (run by `tools/verify.py`); enforced by `tests/test_ds_review.py` and `lib.check`.
Committed: `components/<Mfr>/<Value>/review/review.toml` (ledger) and, for a capacitor series, `review/export_check.toml` (`docs/spec/capacitor.md` "Export check"); lib.check FAILs on any other file there. Local only,
git-ignored `.review-cache/<Mfr>/<Value>/`: `evidence.toml` (below), `README.md` (legend, counts, rows to review), `DELTA.md` (human-stamped rows now STALE or PDF_CHANGED, with the TOML diff),
`github-issue.md`, `unmapped.md`, `params/<key>.md`, `evidence/` (row crop `<key>_p<n>.png`; per table `[<sheet>_]head_`/`foot_p<n>_y<a>-<b>_x<c>-<d>.png`; fallbacks `[<sheet>_]page_p<n>.png`, `table_p<n>_y<top>.png`; n = PDF page).

## Images
Only `pdftoppm -gray` renders of the local PDF the cite names (`datasheet_file`, or the sheet in brackets); no pixel
edits. Auto: the one line that is the row (symbol, table_xcheck's match first, else the cite's `row <label>` words) and
its row group (continuation lines that start no new row, <= 16). The table's header band (title to first data row) and
its footnotes (marker on the row or header) are shared images at the row's width (table region + 6 pt) and dpi, shown
above and below it: column roles are read on the header image. Fallback (no text layer, rotated page, page range, no or
several matches, longer group, no unit cell in the group): the `ds_index` table, else the full page; status UNSURE.
150 dpi; 200 when the table's smallest glyph < 7 pt. 4-bit gray PNG, 80 KB budget (listed, not a FAIL); tEXt `Source Title Revision Page Copyright SHA256`, no time.

## Check status (per run; never a verification)
`AGREE_TEXT_CHECK` text-layer min/typ/max/unit equal (`table_xcheck`) · `DISAGREE` · `UNSURE` · `NOT_FOUND` (cite missing, unparseable, sheet missing or page not located). A fallback image forces UNSURE.

## Ledger state (per row; pins change only when a stamp is added or its text changes)
`HUMAN_VERIFIED` `human:` stamp, `hash == stamp_hash`, pins and the stamp's row/PDF hashes match · `MACHINE_CHECKED` any other
stamp, pins match (never a human check) · `STALE` hash or the stamp's row hash differs · `PDF_CHANGED` the PDF differs from
the pin or the stamp · `NEW` never stamped · `UNVERIFIED` stamp removed or malformed `human:` · `REFERENCE` a variants.toml override of a row that does not matter (display only, not a stamp) · `NOT_COVERED` used variants.toml keys that are not overrides, resistor-series values (not reviewed; never claim full coverage). Capacitor-series catalog.csv rows are not ledger rows: the export record covers them (`docs/spec/capacitor.md` "Export check").
Row hash: SHA-256 of `json.dumps(table without verified, sort_keys=True, separators=(",", ":"))`. `pdf_sha256` pins the
PDF when the row first entered the ledger or was (re)stamped. Backfill: a stamp is pinned to the current hash
(`baseline = true`) unless the row's hash at the commit that added the stamp line (git blame) differs: then STALE.
`review.toml` holds only what the committed files and the PDF's SHA-256 decide, so its bytes are the same with and without the local PDF: `[inputs]` datasheet_url/_file/_rev, pdf_sha256,
component_sha256, backfill, sheets (file -> SHA-256); `[row.<key>]` hash, stamp, stamp_hash, pdf_sha256, state, sheet, printed_page, pdf_page (the cite's page; kept when the PDF is absent), stamped_toml, baseline;
`[pinout]` pins state and a `[[pinout.page]]` (sheet, pdf_page) per cited page. A state follows from these alone. `evidence.toml` (local) holds the rest: `[inputs]` tool, poppler, python, dpi, pages, text_layer,
render (`complete` | `NOT_RENDERED`); `[row.<key>]` hash (of the row it describes), status, reason, toml_lines, image, image_sha256, image_bytes, crop_box (PDF pt) or `"full_page"`, crop (`auto` | `fallback`), dpi, render_key, header_/foot_ image, sha256, box, key, text_snippet; `[pinout]` hash, its pages' image fields.

## Runs
Render a cache image only when its `render_key` (PDF SHA, page, box, dpi, tool version; + row hash for auto crops) changed or it is missing; a re-render with an unchanged key is compared with the evidence record's SHA. Mode, printed by ds_review and lib.check: evidence (PDF present: cache images must match evidence.toml, which must describe the ledger's row hashes) or ledger-only (no PDF, as in CI: TOML, row hashes, stamps; ds_review prints `NOT_RENDERED` for a part whose cache holds no evidence). `text_cells` keeps the text-layer cells.
Stamp: `verified = "<who> <YYYY-MM-DD> <method>"`. `tools/stamp.py` writes `human:<github-login> <date> page-image ds_review <pdf12> row <row-hash[:12]>` (login from `gh api user`; it refuses when CLAUDECODE is set, and `.claude/settings.json` denies it to agents). CI checks pull requests (`tools/check_stamps.py`, which scans `component.toml` and `variants.toml`): a new or changed human stamp must name the PR author.
`lib.human_review_needed()` counts a human stamp current only in that format, with its row hash = the row's, its PDF SHA = the ledger's and the local PDF's (ledger only without the PDF), and a ledger row; otherwise it is unverified. Derived capacitor-series catalog rows are not counted (`docs/spec/capacitor.md`). `lib.unverified_inputs()` (the verdict's UNVERIFIED INPUTS) counts rows with no stamp or a broken one, plus STALE and PDF_CHANGED rows; machine stamps still pass it, and human review is reported separately by `lib.human_review_needed()` (today the verdict does not require human stamps; `tools/status.py` reports them).
`lib.check` FAILs on a stale row hash, a stamp differing from `verified`, any file but review.toml and export_check.toml under review/, and (evidence mode) a missing evidence record, one that is older than the ledger, or a missing or changed cache image. `review/export_check.toml` (`lib.check`, `check_export_record`): a catalog, group or tables hash that differs from the committed values is STALE; a group `verified` must be `machine export-check <YYYY-MM-DD> <group_sha256[:12]>` or the legacy `human:<login> <date> export-check group <dielectric>`; the cited export is looked up in docs/datasheets/, docs/vendor/, then the committed docs/exports/ (trimmed subset), and the export check is re-run in every mode (a missing export is an error): the export rows hash and the group hashes must match the record, so a hand-edited machine line or catalog row fails in CI. Limits: a stamp is an accountability record, not proof; a hand-typed stamp passes if it reproduces both hashes; `main` needs branch protection requiring PRs; hardware-key signed commits are the planned stronger control.

## Human view
Rows that matter, per-part status, statements, the review page and the pinout stamp: `docs/spec/review-view.md`.
Variant overrides: a `[variant."X".param.K]` in variants.toml of a row that matters is a ledger row `variant.<V>.<key>` with its own cite and page image; its row hash is that of `merge(base [param.K], override fields)`, so a base edit stales its stamp. `tools/stamp.py <Value>:variant.<V>.<key>` writes `verified` under the quoted header (image from the override's own cite and sheet); `tools/check_stamps.py` checks it. An override of a row that does not matter is `REFERENCE`: display only, no stamp.
