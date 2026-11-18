# Capacitor series (the part is picked from a catalog)

A capacitor series is a directory for one package whose orderable values are the rows of a committed catalog file.
Murata GCM MLCCs: one directory per Murata size+thickness code (`GCM155`, `GCM188`, `GCM21B`, ...), each with one
symbol, footprint and STEP (the height differs per thickness code), holding every C0G and X7R value. It is an ordinary
component directory plus `catalog.csv` and these `[part]` keys (no `mpn`, no `variants.toml`, exactly 2 pins):

```toml
[part]
value              = "GCM155"            # directory name
series             = "capacitor"
catalog            = "catalog.csv"       # file in this directory
tc_param           = { X7R = "tc_x7r" }  # dielectric -> param row with its temperature characteristic
package_default    = "D"                 # package letter appended to the catalog value: MPN = value + letter
package_alternates = ["W", "J", "V"]     # other letters: the same part in other packaging
```

**catalog.csv** (UTF-8, header row, one row per orderable value; comma separated, quote cells that contain a comma):

| Column | Meaning |
|---|---|
| `value` | MPN without the package letter (`GCM155R71H104KE02`); unique in the file |
| `dielectric` | name as printed by the source (`X7R`, `C0G`) |
| `capacitance` | as printed (`0.1μF`, `6,800pF`, `1.5pF`); units pF, nF, uF (Greek mu or u) |
| `tolerance` | as printed, symmetric (`±10%`, `±0.25pF`); an absolute pF tolerance is divided by C where a fraction is needed |
| `rated_voltage` | as printed (`50Vdc`, `1,000Vdc`) |
| `thickness` | as printed (`0.5mm ±0.05mm`); informational |
| `source` | the cite of the row |

- **The export is the source.** A manufacturer product-list export is a cited source for per-part values. The cite is
  `Murata product list export <file name>, row <part number>` (the part number exactly as the export prints it, with
  the `#` package placeholder). It is not a datasheet table and says so in every Param `note`; per-dielectric and
  per-size rows still cite the reference sheet (`DS p.`).
  The catalog Params (capacitance, tolerance, rated_v) carry `verified = "manufacturer-export <export date> ..."`:
  machine-readable data parsed by tested code, not transcribed; a source without a date leaves them unverified.
- **Generating the catalog.** `python3 -m lib.catalog murata-gcm <vendor csv> <component dir> [--dielectrics X7R,C0G]`
  keeps the export rows whose part number carries the directory's size+thickness code (`GCM155` -> `155`) and whose
  `Temperature characteristics` column is an allowed dielectric (default: the keys of `[part] tc_param`, so a dielectric
  with no temperature-characteristic row is never written), In Production only, and writes `catalog.csv` sorted by
  value. Before writing, every kept row is decoded from its part number and compared with the export's own columns:
  size (length and width), thickness code, dielectric code (`5C` = C0G, `R7` = X7R), rated-voltage code (`1H` = 50 V,
  `2A` = 100 V, ...), the 3-digit capacitance code (two digits and a power of ten in pF; `R` is the decimal point:
  `1R5` = 1.5 pF), the tolerance letter, and the operating temperature (-55 to 125 degC, the range of the shared
  `op_temp_*` rows). Any mismatch, a part number of another form or a repeated part number is an error: the row is not
  written and the command exits 1.
- **The decode tables are a cross-check only ("Not a DS rule").** They live in `lib/catalog.py`, each with its source; a row passing the decode proves the export agrees with itself and the tables, not that the tables are Murata's rules.
- **Restricting rows.** In a capacitor series a param row may carry `dielectric = "X7R"` (applies to every catalog part
  of that dielectric: the temperature characteristic, shared test limits) or `parts = ["GCM155R71H104KE02"]` (applies to
  those catalog values only: per-part rows from a reference sheet, such as thickness T, IR limits, stress-test limits).
  Rows with neither apply to every part. Row keys are unique, so a dielectric-specific quantity has one key per
  dielectric (`tc_x7r`, `tc_c0g`).
- **Loading.** `load(dir)` returns a Part holding only the unrestricted rows (`part.hidden` maps the other keys to
  their restriction; `part.param("tc_x7r")` then says which restriction hides it). `part.catalog()` returns the
  `lib.capacitor.CatalogRow` list, `part.dielectrics()` the dielectrics in it.
- **Selecting a part.** `sel = part.select(capacitance, rated_voltage, dielectric, tolerance=None)`; capacitance in F
  and rated voltage in V (or printed text, `"0.1uF"`, `"50Vdc"`), dielectric as in the catalog, tolerance as printed
  (`"+/-10%"` or `"±10%"`) and only needed when the catalog lists several for that value. It returns a `Selection`
  with `value`, `mpn` (value + `package_default`), `alternates` (value + each `package_alternates`), `dielectric`,
  `tolerance`, `thickness`, `capacitance` (Param, F: typ = printed value, min/max from the tolerance),
  `rated_voltage` (Param, V: min = -rating, max = rating, non-polarized) and `part`, a Part of the rows that apply
  to this part (dielectric rows of its dielectric, `parts` rows naming its value) plus the selection keys
  `capacitance`, `tolerance` (fraction), `rated_v` and `tc` (the row `tc_param` names for its dielectric, an alias).
  No match raises `ValueError` ("no catalog part for ...", with the voltages or tolerances that do exist); several
  matches (two tolerances and none given; two values with the same tolerance) raise `ValueError` "ambiguous: ..."
  listing the values. Capacitance and rated voltage match to 1e-9 relative.
- **calc.** Two functions, one per temperature-characteristic kind, so a coefficient can never be read as a fraction.
  `capacitance_worst_pct(c0, tol, tc)` is `C0 x (1 + tol) x (1 + tc)` for percent-change classes (X7R: `tc` a fraction,
  -15 to 15 % over the whole range). `capacitance_worst_ppm(c0, tol, tc, dt)` is `C0 x (1 + tol) x (1 + tc x dt)` for
  ppm classes (C0G: `tc` in 1/degC, 0 +/-30 ppm/degC); `dt` (T - 25 degC) is required, and `ValueError` is raised for
  `dt` below 0 or above 100, because the coefficient is printed for 25 to 125 degC only (below 25 degC the Table A drift
  rows apply, and their docstring says so). Each raises `ValueError` if `tc` has the other kind's magnitude. Each has
  its own `INPUTS` (`c0` -> `capacitance.typ`, `tol` -> `tolerance`, `tc` -> `tc`, the dielectric's row, never
  hard-coded) and its own `EXAMPLES` from printed numbers. Neither includes DC-bias or aging capacitance loss (the
  reference sheets print no number; for X7R these can dominate), and the docstrings say so:
  `wca(sel.part.calc.capacitance_worst_pct, **sel.part.inputs("capacitance_worst_pct"))`, or for C0G
  `wca(sel.part.calc.capacitance_worst_ppm, dt=Param(min=0, max=100), **sel.part.inputs("capacitance_worst_ppm"))`.
  The tolerance and tc rows are bound-only, so the result has no typ unless the caller states one.
- **Re-decoding the catalog.** `[part] catalog_decoder = "murata-gcm"` makes `lib.check` decode every committed row again
  with the offline half of the `lib.catalog` decode (`value + "#"` against the part-number form, then dielectric, rated
  voltage, capacitance code, tolerance letter and thickness code against the row's columns, and the size+thickness
  code against the directory name; length, width and operating temperature exist only in the export and are skipped).
  A hand edit of a column is an ERROR. Same tables as the generator, same "Not a DS rule" status.
- **Suffix convention.** A row key ending in `_c0g` / `_x7r` (the dielectric name, lower case) is about that dielectric.
- Rating rows still need `check_pins`, `check_ambient` or `unchecked`; in a capacitor series only `check_ambient` (one per catalog dielectric) and `unchecked` are possible. Row keys `capacitance`, `tolerance`, `rated_v`, `tc` are reserved for the selection (`INPUTS` may name them).
- `lib.readme` adds a "Series" section (catalog count, MPN rule, selection, wrapper, a table per dielectric) and shows
  "Applies to: dielectric X7R." / "Applies to: parts ..." in the Conditions of restricted rows.
- Zener: see "Capacitor wrapper".
