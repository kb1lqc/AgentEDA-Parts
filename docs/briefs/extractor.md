# Brief: extractor (electrical engineer, one Haiku per part)

You receive: this brief, the datasheet, the component dir, a scratch dir and the vendor symbol path. Write ONLY `component.toml` and `calc.py` in the component dir. Run no git command.

Load exactly these files:
- `docs/spec/extract.md` (format, defaults, calc.py rules, cites)
- `docs/KICAD.md` (symbol pin names and types, so `[[pin]]` matches the symbol)
- one more only if the part is a family (`docs/spec/family.md`), a resistor series (`docs/spec/series.md`) or a
  capacitor series (`docs/spec/capacitor.md`)

Procedure:
1. Locate tables with `pdftotext -layout`; read each as an image:
   `pdftoppm -r 150 -png -f N -l N <pdf> <scratch>/p` (-r 200-300 for small print), then Read the PNG.
2. `component.toml`: every row of Absolute Maximum Ratings, ESD, Recommended Operating Conditions, Thermal
   Information (this package's column) and Electrical Characteristics, as separate `_25c` / `_full` keys where both
   exist; mechanical rows in mm; `[[pin]]` as in the symbol. Apply the Defaults table; do not ask.
3. `check_pins` / `check_ambient` / `unchecked` on every `abs_max` and `rec_op` row.
4. `calc.py`: one function per DS equation, `EXAMPLES` from numbers the DS prints, `INPUTS`, one
   combined function for the part's main quantity (temperature recipe).
5. Run `python3 -m lib.check`; fix your errors.
6. Intake: datasheet revision and date, MPN decode (package, grade, finish, packaging, MSL), lifecycle as printed.
   Compare land pattern vs footprint pads; courtyard, pin-1 marker, STEP status.

Review records: `docs/briefs/ds-review.md` (never write `verified`; never edit `review/`).

Report: params per kind, pin table with cites, equations with cites, EXAMPLES results, the check selection, every
judgement call and DS ambiguity, land-pattern comparison, open items.

Stop and return: datasheet missing; several packages, grades or options and the task names none;
pin number, position or count disagree between diagram and table; NC or exposed-pad wording missing; footprint
mirrored, rotated or with pad count, pitch or pin-1 corner disagreeing with the DS.
