# How parts get into this library

A short guide to the import workflow. The format contract is [SPEC.md](SPEC.md), the KiCad rules are
[KICAD.md](KICAD.md), and the full procedure with defaults and stop rules is [../CLAUDE.md](../CLAUDE.md).

## Two layers
| Layer | Files | Edited by |
|---|---|---|
| Data + math (source of truth) | `component.toml`, `calc.py`, `catalog.csv` (MLCC series) | People and AI, verified against the datasheet |
| Circuit capture (generated) | `<Value>.zen`, `pcb.toml` | Nobody: `python3 -m lib.zen` |

Every datasheet number has min/typ/max, unit, conditions, scope and a page cite. Which rows become Zener checks is
set in the TOML (`check_pins`, `check_ambient`, or an `unchecked` reason).

## Part types
| Type | When | Example |
|---|---|---|
| Single part | One orderable | `TexasInstruments/TPS48000QDGXQ1` |
| Family (`variants.toml`) | Same package, different grade or option | `AnalogDevices/LTC4364MS`, `TexasInstruments/INA241DGK` |
| Value series | The datasheet prints the part-number rule and a regular value set | `Panasonic/ERJ-3EKF`, `Panasonic/ERA-3AEB` |
| Value series with tolerance options | Several tolerances, each with its own range | `Vishay/WSK2512` |
| Catalog series | Irregular availability; values from a manufacturer export, cross-checked by decoding each part number | `Murata/GCM188` |

## What to supply (into `temporary/`)
1. The datasheet PDF. Name the package and grade if there are several.
2. Vendor CAD (symbol, footprint, STEP), one subfolder or zip per part. Ultra Librarian N density is fine.
   Altium-only files are converted with `kicad-cli` (see KICAD.md).
3. Optional: errata sheets, value/decade tables, land-pattern guides.
4. Catalog series: the product-list export (CSV), one reference sheet per size x dielectric and per thickness code,
   one STEP per thickness code, one symbol + footprint per case size.

Check that every download is for the datasheet's part and package before using it.

## Steps
1. **Pre-flight and intake:** revision, part-number decode, package/grade choice; family or separate directory.
2. **KiCad:** edit the vendor files: datasheet pin names and types, pads equal the datasheet land pattern,
   courtyard 0.25 mm beyond the larger of pads and body, pin-1 marker. Never draw from scratch.
3. **Extract:** every ratings, operating, thermal and electrical row. Extract text locally (`pdftotext -layout`) and
   confirm key tables, pinouts, land patterns and curves on page images.
4. **Equations:** one function per datasheet equation; `EXAMPLES` reproduce the datasheet's numbers;
   non-datasheet helpers say `Not a DS equation:`.
5. **Zener:** check fields on every abs-max and rec-op row, generate the wrapper, write a harness and `CASES`
   (nominal pass, each limit failing, waiver, unset net, ambient). Flip one case to prove the tests are live.
6. **Verify:** a fresh independent verifier, then an adversarial review. Apply findings that cite the datasheet,
   log the rest, and re-review scripted bulk fixes.
7. **Run, in order:** `python3 -m lib.check` -> `python3 -m lib.zen` -> `python3 -m lib.readme` ->
   `pcb build -Wstyle -Dwarnings components/<Mfr>/<Value>` -> `python3 -m unittest discover -s tests`.
   All must pass with 0 errors and 0 warnings.
8. **Report and commit:** evidence, decision log, open items; add the part to the README parts table.

## Standing rules
- Never guess a number. A value the datasheet doesn't print (including a part-number code) is excluded and logged.
- Curve readings are `curve = true` and never pass/fail bounds.
- Conflicting reference sheets in one series: the newest-format sheet wins, and the older values are logged.
- `scope = "partial"` marks rows that apply only under a condition the checker can't see (waivable warning).
- Derating policy is deferred to a dedicated NASA EEE-INST-002 effort.
