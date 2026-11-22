# Brief: datasheet review records (`tools/ds_review.py`; contract `docs/spec/review.md`)

- Trigger: `python3 tools/verify.py` runs it on changed parts and on every part with no `review/`; `--all` on all.
  A new part comes from `python3 tools/scaffold.py <Mfr> <Value> --datasheet-url <vendor URL>`.
- Read `.review-cache/<Mfr>/<Value>/DELTA.md` first (human-stamped rows now STALE or PDF_CHANGED, with the TOML diff),
  then that folder's `README.md` (every row that is not HUMAN_VERIFIED). Only `review/review.toml` is committed.
- Status (text layer, per run): AGREE_TEXT_CHECK, DISAGREE, UNSURE, NOT_FOUND. **AGREE_TEXT_CHECK is not verified.**
- State (ledger): HUMAN_VERIFIED, MACHINE_CHECKED (not human), STALE, PDF_CHANGED, NEW, UNVERIFIED, NOT_COVERED.
- STALE and PDF_CHANGED rows make analyses report `PASS (UNVERIFIED INPUTS)`.
- Agents never write or edit `verified` (a row's, or `[pinout]`'s); only a person does, with `tools/stamp.py <Value>:<key>`
  or `<Value>:pinout`, or the one-button `tools/review.py`, after the image (`params/<key>.md`, `evidence/pinout_p<n>.png`).
- Agents never edit `review/`; rerun the tool. Report the DELTA.md rows (key, state, status) to the human.
- A DISAGREE is a question for the page image, never a value to copy into the TOML.
- Optional local hook: `cp tools/pre-commit .git/hooks/pre-commit` (runs verify.py before each commit).
- Optional model second opinion: `docs/briefs/ds-review-model-prompt.md`; its output never changes data or states.
