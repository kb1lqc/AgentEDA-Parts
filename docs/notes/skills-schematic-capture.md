# History and rationale: the retired schematic-capture skill (humans only)

Merged into `schematic-style` plus `docs/briefs/schematic-capture.md` in the context diet (2026-11-17). Every rule came from rework that cost real tokens.

## Where tokens were burned (and the rule that prevents it)
| Waste | Rule |
|---|---|
| Arranging a sheet, then changing net names, net types, ports or hierarchy, forcing a fresh regeneration that throws the placement away | Freeze the code before any placement. |
| Style questions surfacing one at a time during arrangement (pin-order crossings, label types, rail drawing), each a round trip and a redraw | Batch the decisions up front and run the pin-geometry pre-flight before drawing. |
| Concluding "the toolchain can't do X" from one bad probe (it could: sub-sheets), then building around the false limit | Verify any "can't" with a second, differently designed test and the tool's changelog; probe on a fresh generation; use search patterns that match the real file format. |
| A cheap model doing spatial placement by trial in raw coordinates, producing a partial result and a second pass | Match the model to the job (Sonnet for pre-flight and generator). |
| Each agent rebuilding the same helpers (render, netlist diff, ERC triage, placement math) | Reuse committed tools; add helpers to them, not to scratch. |
| Chasing ERC findings that are inherent or expected | Classify ERC findings first. |
| A tool reporting success while silently dropping a label | Gate on the netlist diff, not exit codes. |
| Two writers on one file | One writer per file. |
| Notes and spec text typed by hand from the report, stale after the next design change | Generate notes from the values file; text elsewhere cites the key. |
| An agent that hit a usage limit replaced by a fresh one that redoes the work | Resume the same agent and have it check its partial edits first. |
| Large outputs pulled into the main context | Agents return a summary plus paths. |

## Generator lessons (each from a rework)
- The INA arrangement took two one-off scripts: the first fixed pitches before label widths and support-part positions were known; the second re-edited raw coordinates. Size label runs and put support parts at their pins in the plan, then run `overlap.py` in the loop.
- The transform was verified for all 8 orientations against `kicad-cli` netlists.
- Idempotence: KiCad saves items grouped by type (rectangle, text, junction, no_connect, wire, label, hierarchical_label, symbol, sheet), each group sorted by uuid, with its own indentation. A generator that appends in emission order produces a different file on every rerun (thousands of churned lines, easily misread as lost content). Canonicalise on save (circuit-blocks `tools/schematic/canon.py`).
- `pcb apply` keeping arranged sheets was verified on INA (two applies, second `unchanged`).
- Agents were forbidden `git checkout/restore/stash/reset` after damage to committed files; the main session asks the designer before restoring.

## Connectivity from the rendered figure
`pdftotext -layout` placed pin names next to unrelated parts: on the TPS48000 switch it put "SRC" beside the gate-ramp C1, and the block shipped with C1 to SRC although Fig 7-4 draws it to GND (found by the designer, 2026-11-16). Crop with `pdftoppm -r 400 -x .. -y .. -W .. -H ..` and look. A return-node change also changes the part's voltage stress (C1 to GND sees bus + VGS, not VGS): re-run the rating checks.

## Design-value change loop (now scripted)
Edit analysis inputs or `.zen` configs, never the sheet; run the analysis; run the notes script (each note line found by one regex that must match exactly once; a changed note wording is edited once in the `.kicad_sch`, keeping its line count); apply twice, netlist diff, build, ERC, PDF export, sync check; grep `.zen` comments, spec and README for the old numbers and replace copies with cites. The main session hand-checks the top two or three contributors (TCR x span, drift x span) before presenting. Phase 3 scripts this as `verify.py values`.

## Toolchain list and removed duplicates
The tooling list (`render.sh`, `netcmp.py`, `erc.sh`, `kicad_sexpr.py`, `place.py` API, `overlap.py`) is in `tools/schematic/README.md` and each tool's `--help`. The sync-check wrapper (`check_sync.sh`) plus the pre-commit hook (`git config core.hooksPath tools/git`) enforce schematic = code; `pcb build` does not see values, MPNs or fields edited in KiCad, so apply on a throwaway copy must report `schematic unchanged`.
