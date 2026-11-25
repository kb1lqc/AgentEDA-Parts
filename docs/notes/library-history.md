# Library workflow history (humans only; agents do not load this)

The old docs/WORKFLOW.md (later docs/notes/workflow.md, removed: its part types are in CONTRIBUTING.md) conflicted with
CLAUDE.md (it said to extract text with `pdftotext -layout`, to commit at the end, and to supply files into `temporary/`);
CLAUDE.md and docs/spec/ win.

## Derating policy
Deferred to a dedicated NASA EEE-INST-002 effort. The `derate` wrapper config now exists (`lib/zen.py`).

## Part types (from the old WORKFLOW)
Single part (`TexasInstruments/TPS48000QDGXQ1`); family (`AnalogDevices/LTC4364MS`, `TexasInstruments/INA241DGK`);
value series (`Panasonic/ERJ-3EKF`, `Panasonic/ERA-3AEB`); value series with tolerance options (`Vishay/WSK2512`);
catalog series (`Murata/GCM188`).

## Schematic tools
`tools/schematic/` Python tools are stdlib only; tests are `tests/test_schematic_tools.py`. Text sizes in
`overlap.py` are estimates calibrated on KiCad 10 renders (pin number/name text and group-box edges are not checked).

## Removed librarian skill
The registry-generic `librarian` skill was deleted: it referenced skills and trees that do not exist here
(`kicad-symbol`, `modules/`, registry search) and contradicted generated wrappers.
