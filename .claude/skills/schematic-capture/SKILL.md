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
6. **Adversarial review (independent, read-only).** A fresh agent that did not draw the sheet reviews the renders
   (full sheet plus zoomed crops) against the `schematic-style` review checklist and the phase-0 decisions, and
   returns defects only: `sheet | location | rule broken | evidence | fix`. It also re-checks any claim the drafter
   made about tool limits, and checks every number in the notes against the spec and the worst-case report. The drafter fixes in one pass; re-review only what changed.
7. **Present** to the designer with the renders, the gate results, the accepted ERC exceptions, and any open
   items. Record new preferences in the board's style notes; promote generic ones to `schematic-style`.

## Agents: which model does what
| Job | Model | Why |
|---|---|---|
| Orchestration, decisions with the designer, final review of renders, skill updates | main session | owns judgment and context |
| Zener code changes, library data, tests, toolchain probes, file renames, spec text | cheapest (Haiku) | well-specified, checkable by build and tests |
| Pin-geometry pre-flight and the placement generator script | mid (Sonnet) | spatial reasoning; a cheap model produced partial layouts |
| Adversarial review | a fresh agent, cheap or mid, never the drafter | independence matters more than size; checklist-driven |
Brief every agent with absolute paths, the files it may write, the skills to read, the gates that define done,
and the scratch directory; ask for a summary plus artifact paths, not full logs.

## Tooling (reuse, extend, commit)
Keep these as committed helpers (e.g. in the library's `lib/` or a `tools/` folder) rather than rebuilding them in
scratch each time:
- `render`: export all sheets to PDF and PNG (`kicad-cli sch export pdf` + `pdftoppm`), with crop/zoom options.
- `netcmp`: export the netlist and compare net-by-net against a baseline (names and node sets).
- `erc`: run `kicad-cli sch erc` and summarize by category, marking accepted classes.
- `overlap`: compute text bounding boxes (labels, hierarchical labels, sheet pins, fields) and report any that
  intersect a wire, pin, symbol body or other text. This turns the most common visual review finding into an
  automatic gate.
- `place`: helpers for the placement script: pin endpoint for a symbol at (x, y, rotation, mirror), grid snap,
  wire/label emitters with correct label anchor, angle and justify.

## Before reporting a limitation
State what was tried, on a fresh generation, with what evidence (file snippet, exact error). Check the tool's
changelog for the feature. If still unsure, say "not confirmed" rather than "can't".
