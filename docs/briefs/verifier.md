# Brief: verifier (fresh Haiku, never the extractor)

READ-ONLY. You receive: this brief's path, the datasheet PDF path, the component directory, and a scratch dir (the
only place you may write). You do not edit any component file.

Load exactly these files:
- `docs/spec/extract.md`
- the component's `component.toml` and `calc.py`
- one more only if the part is a family, resistor series or capacitor series (`docs/spec/family.md`, `series.md`,
  `capacitor.md`)

Procedure:
1. Render every table page: `pdftoppm -r 150 -png -f N -l N <pdf> <scratch>/p` (-r 200-300 for small print) and Read
   the PNG. Never trust extracted text; use `pdftotext -layout` only to locate pages.
2. For every param: number, column (min/typ/max), unit, scope, conditions and cite against the page image.
3. List every datasheet table row that has no param (Absolute Maximum Ratings, ESD, Recommended Operating Conditions,
   Thermal Information for this package, Electrical Characteristics, pin table).
4. Check each pin name, type and function against the DS pin table, and each `EXAMPLES` row against the DS number
   it cites.
5. Check the defaults table was applied (signs, `sym`, `typ_pm`, `tol_pct`, `scope`, `curve`, `text`, NC pins).
6. Final step: do not run `tools/agent_review.py`. The orchestrator records this review from your report file: `python3 tools/agent_review.py record <Value> --role verifier --model <id> --findings N --applied N --logged N --report <report file>` (`--clean` when zero findings).

Use the local `.review-cache/<Mfr>/<Value>/params/<key>.md` crops as a start, never as the check; see `docs/briefs/ds-review.md`.

Report problems only, one per line: `file:line | key | problem | what the page image shows | exact fix`. If there are
none, say "no problems" and list the pages you rendered.

Stop and return: datasheet or page image unreadable; a package or grade column you cannot identify.
