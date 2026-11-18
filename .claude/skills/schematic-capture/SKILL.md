---
name: schematic-capture
description: Workflow for capturing a schematic from Zener (or any code-to-KiCad flow) in as close to one pass as possible with the least token burn - decisions batched up front, code frozen before placement, a pin-geometry pre-flight, placement by a re-runnable generator script, automatic gates (apply, netlist diff, build, classified ERC), and an independent adversarial review before anything is shown. Includes which agent model does which job. Use when planning or running schematic generation or arrangement for any board or module, or when delegating schematic work to agents.
---

# Schematic capture workflow

Goal: a finished, reviewable schematic in one pass, at the lowest cost. The rules for what it must look like are
in `schematic-style`; how the circuit is designed is in `ee-design`. This skill is the order of work, the gates,
and how to use agents. Every rule here came from rework that cost real tokens.

## Where tokens were burned (and the rule that prevents it)
| Waste | Rule |
|---|---|
| Arranging a sheet, then changing net names, net types, ports or hierarchy, which forces a fresh regeneration and throws the placement away | **Freeze the code before any placement** (phase 1). Placement starts only after the last regeneration. |
| Style questions surfacing one at a time during arrangement (pin-order crossings, label types, rail drawing), each costing a round trip and a redraw | **Batch the decisions up front** (phase 0) and run the **pin-geometry pre-flight** (phase 2) before drawing. |
| Concluding "the toolchain can't do X" from one bad probe (it could: sub-sheets), then building around the false limit | **Verify any "can't" with a second, differently-designed test and the tool's changelog** before reporting it or designing around it. Probe on a fresh generation. Use search patterns that match the real file format. |
| A cheap model doing spatial placement by trial in raw coordinates, producing a partial result and a second pass | **Match the model to the job** (table below). |
| Each agent rebuilding the same helpers (render, netlist diff, ERC triage, placement math) | **Reuse committed tools** (Tooling); add new helpers to them instead of to scratch. |
| Chasing ERC findings that are inherent or expected (KiCad label rules, incomplete board) | **Classify ERC findings** with the table in `schematic-style` before acting. |
| A tool reporting success while silently dropping a label | **Gate on the netlist diff**, not on exit codes. |
| Two agents (or an agent and the main session) writing the same file | **One writer per file at a time**; parallelize only independent files. |
| Notes on the sheet, numbers in spec text and `.zen` comments typed by hand from the report, then left stale after the next design change | **Generate notes from the analysis values file** (Design-value change loop); text elsewhere cites the section or key, not the number |
| An agent that hit a usage limit replaced by a fresh one that redoes the work | **Resume the same agent** (send it a message) and have it check its partial edits first |
| Large outputs (full reports, many renders) pulled into the main context | **Agents return a summary plus paths**; the main session opens only the final renders, at modest resolution, and zooms into specific areas. |

## Phases
0. **Decisions batch (ask once, before any code).** Settle and record (spec or style notes):
   - module and instance names (short instance name; module name states its limits), port names by role, rail
     names with voltage, active-low and pair suffixes
   - net type per port (power paths into reusable sheets are plain nets; rails feeding parts are `Power`)
   - hierarchy: which modules are sub-sheets
   - label convention for board-level nets (local vs global) and accepted ERC exceptions
   - title block fields
   - which engineering notes each sheet carries (the `schematic-style` annotation checklist) and the functional
     groups that get titled boxes; confirm the spec and worst-case report contain every number the notes need
   Anything not decided here becomes a mid-arrangement round trip.
1. **Code freeze.** Implement in Zener; `pcb build -Dwarnings` exit 0. Review names and net types against phase 0.
   Then regenerate fresh once (delete the `.kicad_sch` files, apply twice, second unchanged). No placement yet.
2. **Pin-geometry pre-flight (text only, no drawing).** From each symbol's pin table and the intended flow, list:
   which side each pin group must face (rotate 180 vs mirror), rail pins below ground pins, crossings forced by
   pin order (e.g. sense taps vs IN+/IN- order), labels that need wider wire pitch, support parts and their
   pins. For each conflict, state the rule from `schematic-style` that resolves it, or ask the designer. Output a
   placement plan table (part, rotation/mirror, approximate position, neighbours). Cheap to review, prevents
   redraws.
3. **Placement by generator script.** Encode the plan as a re-runnable script that computes every coordinate from
   the symbol pin geometry and writes the `.kicad_sch` (never hand-nudge coordinates by trial). A re-run after a
   correction is cheap; a trial-and-error edit loop is not.
   The script also performs the steps `pcb` cannot express and that a regeneration undoes, e.g. swapping power
   symbols inside reusable sheets for hierarchical labels (`schematic-style`, local rails recipe).
4. **Annotate (required, never skipped).** Add the engineering notes and titled group boxes per `schematic-style`
   ("Engineering notes and grouping boxes" and its annotation checklist): every number copied from the spec or the
   worst-case analysis report with its source recorded in the agent's report, instance values on the parent sheet,
   block notes on the reusable sheet, a boxed DESIGN VALUES summary on the parent. A schematic without these is not
   done. If a needed number is missing from the spec or report, add it there first (from the analysis), never
   type it onto the sheet directly.
5. **Automatic gates (no human or model judgment needed).** All must pass before review:
   - `pcb apply schematic --no-open` twice, second `unchanged`
   - netlist diff vs the phase-1 baseline: identical nets and nodes
   - `pcb build -Dwarnings` exit 0
   - ERC classified: zero dangling wires, unconnected endpoints, hierarchical mismatches; every other finding
     matched to an accepted class
   - text-overlap check (script, see Tooling) reports nothing
   - hand-added notes, boxes and titles all survive apply (count top-level `text` / `rectangle` items)
   - **sync check (mandatory, also before every commit):** the schematic must match the code source of truth.
     `pcb build -Dwarnings` proves connectivity equivalence, but it does NOT see part values, MPNs or other fields
     edited in KiCad; so also run `pcb apply schematic --no-open` on a throwaway copy of the repo and require
     `schematic unchanged`. Wrap both in a board script (e.g. `tools/schematic/check_sync.sh`) and enforce it with a
     versioned pre-commit hook (`git config core.hooksPath tools/git`) that runs when `.zen`, `pcb.toml` or
     `eda/*.kicad_sch` are staged. Humans review in KiCad and may change presentation only; circuit changes go in
     the `.zen`.
6. **Adversarial review (independent, read-only).** A fresh agent that did not draw the sheet reviews the renders
   (full sheet plus zoomed crops) against the `schematic-style` review checklist and the phase-0 decisions, and
   returns defects only: `sheet | location | rule broken | evidence | fix`. It also re-checks any claim the drafter
   made about tool limits, and checks every number in the notes against the spec and the worst-case report. The drafter fixes in one pass; re-review only what changed.
7. **Present** to the designer with the renders, the gate results, the accepted ERC exceptions, and any open
   items. Record new preferences in the board's style notes; promote generic ones to `schematic-style`.

## Design-value change loop (after the schematic exists)
A changed requirement or part changes numbers, not placement. Run, judging by exit code:
1. Edit the analysis inputs and/or the `.zen` configs (never the sheet).
2. Run the analysis: it regenerates the datasheet (Markdown and its PDF), charts and the values file.
3. Run the notes script (board `tools/schematic/update_notes.py` pattern): each note line is found by one regex
   that must match exactly once, or nothing is written. If the WORDING of a note changes (a new quantity, e.g.
   calibrated and uncalibrated error), edit that note's text in the `.kicad_sch` once, keeping its line count so
   the box still fits, then extend the rule; the script maintains it from then on. Run it twice: the second run
   changes nothing.
4. `pcb apply schematic --no-open` twice (second unchanged), netlist diff, `pcb build -Dwarnings`, classified ERC,
   schematic PDF export, sync check (fails on a stale schematic PDF, analysis PDF or passive text stack).
5. grep the `.zen` comments, spec and README for the old numbers; replace copies with cites.
The main session hand-checks the top two or three contributors of any changed result with a back-of-envelope
calculation before presenting it (e.g. TCR x temperature span, drift x temperature span).

## Agents: which model does what
The general, always-on roles and token rules are in `agent-roles`; this table adds the schematic-specific jobs.

| Job | Model | Why |
|---|---|---|
| Orchestration, decisions with the designer, final review of renders, skill updates | main session | owns judgment and context |
| Zener code changes, library data, tests, toolchain probes, file renames, spec text | cheapest (Haiku) | well-specified, checkable by build and tests |
| Pin-geometry pre-flight and the placement generator script | mid (Sonnet) | spatial reasoning; a cheap model produced partial layouts |
| Adversarial review | a fresh agent, cheap or mid, never the drafter | independence matters more than size; checklist-driven |
| Analysis script changes (new error terms, stack-ups, charts) | cheapest (Haiku), with the exact model, inputs and outputs specified | checkable by running it; the main session verifies the top terms by hand |
Brief every agent with absolute paths, the files it may write, the skills to read, the gates that define done,
and the scratch directory; ask for a summary plus artifact paths, not full logs.

## Tooling (reuse, extend, commit)
Committed in the component library repo, `tools/schematic/` (README there). Extend them; do not rebuild in scratch.
Needs KiCad 10 `kicad-cli` and `pdftoppm`; Python scripts are stdlib only.
- `render.sh <root.kicad_sch> <out_dir> [dpi]`: all sheets to PDF and PNG.
- `netcmp.py <baseline.net> <new.net>`: net-by-net netlist diff.
- `erc.sh <root.kicad_sch> [report]`: ERC counts by category. Run it on the ROOT sheet; a child sheet alone reports
  every hierarchical label as `pin_not_connected`.
- `kicad_sexpr.py`: lossless `.kicad_sch` reader/writer (`load`, `dumps`, `save`; byte-exact round trip).
- `place.py`: library for the placement script. `Sheet.load(path, namespace)`, `pin_point(ref, pin)`,
  `place_symbol`, `set_field`, `wire`, `junction`, `no_connect`, `label` / `hlabel` / `global_label` (take the
  direction the text runs), `text`, `group_box`, `power_to_hlabels`, `set_paper(PAPER_TABLOID)`,
  `set_title_block`, `repo_comment`, `snap`, `pin_endpoint`. Deterministic UUIDs; re-emitting a key replaces it.
- `overlap.py [--overlap] [--dangling] sheet.kicad_sch ...`: text boxes vs wires, pins, symbol bodies and other
  text; wire ends, pins, labels and sheet pins that connect to nothing. Exit 1 on any finding. It is the text-overlap
  gate of phase 5.

## Placement generator lessons
Write the generator against these; each came from a rework.
- One parametric script, one source of coordinates: select symbols by reference (never by old coordinates), compute
  every point from `pin_point`, emit with `key`s, start with `clear()`. The INA arrangement took two one-off scripts
  because the first fixed pitches before label widths and support-part positions were known; the second re-edited
  raw coordinates. Size label runs and put support parts at their pins in the plan, then run `overlap.py` in the loop.
- Transform: library pin position, y flipped to screen, rotated CCW, THEN mirrored (`mirror x` flips screen y,
  `mirror y` flips screen x). Verified for all 8 orientations against `kicad-cli` netlists.
- Rotate 180 swaps left/right and up/down of the pin groups; mirror flips one axis only. When a pinout puts the rail
  pin below ground, rotate the IC 180 so rail goes up and ground down; mirror only to put a part's pins on the
  other side (shunt Kelvin pins down).
- A symbol field's stored angle is relative to the symbol rotation: a rotated part with stored 90 reads horizontal.
  Place fields with `set_field` (visual angle) and it sets `do_not_autoplace`.
- Local label: anchor at the wire end, text runs along the wire (angle = direction toward the pin, justify
  `left`/`right` + `bottom`), so it sits on its wire; the wire must be longer than the text. Hierarchical and global
  label: anchor at the wire end, text runs away from the wire. KiCad never draws text upside down: 0 and 90 use
  `left`, 180 and 270 use `right` (text ends at the anchor).
- Crossings forced by pin order: draw both nets as labelled stubs at each end, symmetric, no wire between.
- Wires on the 1.27 mm grid, pin rows on 2.54 mm; dog-leg inside a 2.54 mm pitch (INA SPI fan-out).
- Net prefix: module-internal nets carry the instance prefix on local labels (`INA.SENSE_P`); ports are bare names
  (`BUS_OUT`, `SPI.CLK`). Stamping rewrites the prefix; the generator must not hard-code the instance.
- Reusable child sheets: swap power symbols for hierarchical labels with `power_to_hlabels` (rails text up, ground
  down); the parent keeps global power symbols.
- What `pcb apply` does (verified on INA, 2 applies, second `unchanged`): an existing arranged sheet keeps symbol
  positions, wires, labels, notes, boxes, title block and paper size. A freshly generated sheet has default
  positions, power symbols and no wiring: rerun the generator after every fresh generation (idempotent by UUID).
- Paper: Tabloid (11 x 17 in) is `USLedger`; set it on every sheet; `pcb apply` preserves it.
- Gates in the script's own loop: `overlap.py` exit 0 (text, then dangling), then the Automatic gates. ERC finding
  `label_dangling` on a root label whose net has only a sheet pin, and `isolated_pin_label`, are net-level
  and not geometric; `overlap.py --dangling` reports geometry only.
- `overlap.py` does not check pin number/name text or group-box edges; review those in the render.

### Generators must be idempotent (and proven so before they touch committed sheets)
- KiCad saves items grouped by type (rectangle, text, junction, no_connect, wire, label, hierarchical_label,
  symbol, sheet), each group sorted by uuid, with its own indentation. A generator that appends items in emission
  order produces a different file on every rerun even when the content is identical (thousands of churned lines,
  easily misread as lost content). Canonicalise on save: re-indent new items and sort the generated kinds into
  KiCad's order (circuit-blocks `tools/schematic/canon.py`). Gate: generator on its own output is byte-identical.
- Prove a generator change on COPIES (`--eda <scratch copy>`) before writing to committed sheets. Agent briefs
  forbid `git checkout/restore/stash/reset`; if an agent damages committed files it stops and reports, and the
  main session asks the designer before restoring.

## Reused blocks on a board
A board built from reusable blocks (see `reusable-blocks`) gets one child sheet per instance, generated fresh in the
board's own `eda/`; the block repository's arranged reference sheet is not picked up automatically
(`schematic-style`, toolchain facts). Stamp the reference sheet into the board per instance with the blocks repository's `stamp_block.py`
(`reusable-blocks`, Schematic reuse), then run the normal gates. Arrange only the
board's top-level block diagram by hand; never re-arrange a block's internals on a board (fix them in the block
repository and re-stamp).

## Connectivity comes from the datasheet figure, rendered
Before code freeze, check every support-part connection (where each R and C returns: GND, SRC, VS, OUT) against
the datasheet's application figure **rendered as an image** (`pdftoppm -r 400 -x .. -y .. -W .. -H ..` crop, then
look at it). `pdftotext -layout` places pin names next to unrelated parts: on the TPS48000 switch it put "SRC"
beside the gate-ramp C1, and the block shipped with C1 to SRC although Fig 7-4 draws it to GND (found by the
designer, 2026-11-16). The verifier repeats the check from its own render. A return-node change also changes the
part's voltage stress (C1 to GND sees bus + VGS, not VGS), so re-run the rating checks.

## Before reporting a limitation
State what was tried, on a fresh generation, with what evidence (file snippet, exact error). Check the tool's
changelog for the feature. If still unsure, say "not confirmed" rather than "can't".
