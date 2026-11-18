# SPEC rationale and history (humans only; agents do not load this)

## Goal (was SPEC.md top)
A person or an AI can pick a part, read its datasheet numbers, and compute how a circuit built from it performs:
nominal, worst case (min/max), as tables and plots. Everything must be checkable against the datasheet by a human
with the PDF open.

## Example: Vishay WSK2512 series (was SPEC "Series components")
`components/Vishay/WSK2512` (0.005 to 0.2 ohm, decade values, B/D/F) and `WSK2512-LOW` (0.0005 to 0.0049 ohm, D/F):
the datasheet prints one table for the whole model, split into two directories where the solder pad dimensions
change. MPN = `WSK2512` + 5-character value code + tolerance code + `EA`: value code `R0250` (0.025 ohm: `R` is the
decimal point, four digits of ohm), `5L000` (0.005 ohm: below 0.01 ohm the value is in mohm with `L`), `L5000`
(0.0005 ohm, inferred: no printed sub-1 mohm example); `0.025 D -> WSK2512R0250DEA`. The single part
`WSK2512R0250D` stays a separate directory and is also reachable as `WSK2512` 0.025 ohm code D.

## Capacitor catalog decode tables (was SPEC "Capacitor series")
The Murata reference sheets decode just their own example part number (DS p.2). Only `15`/`5`, `18`/`8`, `R7`, `1H`,
`104`, `K` and the package letters are printed there; the other codes come from Murata's published part-number system
and are consistent with every row of the export (one printed value per code). A row passing the decode proves the
export agrees with itself and with the tables, not that the tables are Murata's rules.

## Wrapper history (was SPEC "Zener wrapper")
- Series wrapper: resistance `.value` is a float in ohm (confirmed with a scratch build).
- Capacitor wrapper: tuple dict keys, a `Voltage` config and `.value` floats were confirmed with a scratch build
  (pcb 0.4.102). Two catalog values with the same key are a generator problem. The generated module grows with the
  catalog: about 140 rows is 23 kB (GCM155); a catalog of hundreds of rows builds in well under a second.

## Deleted as enforced by code (was SPEC "Validation", README limits)
`lib/check.py` is the validation list. `lib/readme.py` writes the README "Limits of this data" line (row counts per
scope, curve rows, text rows, and a TJ reminder when a junction-temperature row exists with no `check_ambient` row).
