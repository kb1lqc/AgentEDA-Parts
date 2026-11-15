---
name: reusable-blocks
description: How to build, package, version and reuse circuit blocks (a current monitor, a high-side switch, a regulator) the way the component library reuses parts - one package per block with its own worst-case analysis parameterised per instance, a bench board, a reference schematic sheet with instance-independent notes, standard role-named ports so blocks chain, and how a larger board pulls blocks in by URL and pinned version and draws them as a block diagram. Use when creating a new block, restructuring a repository of blocks, or using blocks on a board.
---

# Reusable circuit blocks

A block is to a board what a library part is to a block: a versioned, analysed, reviewed unit pulled in by URL
and pinned version, used unchanged. Engineering rules are `ee-design`; drawing rules are `schematic-style`; the
order of work is `schematic-capture`. Mark anything below as "verify first" until a throwaway build confirms it
for the current `pcb` version.

## What a block is
- A Zener module with role-named ports, all its support parts inside (sense element, decoupling, terminations,
  pull-ups selectable by DNP), and design-intent configs (values, tolerances, DNP, `ambient`, `derate`).
- Topology is fixed: configs change values and DNP only. A different topology is a different block.
- Its name states its limits (`INA229HighSideMonitor`, not `INA229Monitor`).
- It owns a worst-case analysis that any board can run with its own instance configs.
- It owns a reference schematic sheet, arranged once, with notes that hold for every instance.

## Standard ports (so blocks chain on a block diagram)
| Role | Name | Net type into the block |
|---|---|---|
| Power path in / out (through a shunt, switch, fuse) | `BUS_IN` / `BUS_OUT` | plain `Net` with declared voltage (drawn as labels; `Power` into a sub-sheet breaks the sheet pin) |
| Logic or supply rail feeding parts | `V3V3`, `V5`, `V12` (voltage in the name) | plain `Net` port, `Power(...)` on the board, local inside the sheet |
| Ground | `GND` | plain `Net` port, cast to `Ground` inside |
| Enable / control in | `EN` (active high) or `<NAME>_N` | `Net` with logic voltage |
| Status out (open drain) | `FAULT_N`, `ALERT_N`, `PGOOD` | `Net` with logic voltage |
| Digital interfaces | stdlib interface (`Spi`, `I2c`, ...) named by role (`SPI`) | interface |
| Analog outputs | role name with what it represents (`IMON`, `VMON`) | `Net` with voltage range |
New blocks reuse these names before inventing new ones; record any new standard name here.

## Repository layout (one workspace of blocks, like the component library)
```
pcb.toml                          [workspace] repository = "github.com/<owner>/<blocks repo>"
blocks/<Block>/                   one package per block (`pcb new package blocks/<Block>`), tagged blocks/<Block>/vX.Y.Z
  pcb.toml                        the block's dependencies on library parts (tool-managed)
  <Block>.zen                     the module (ports, configs, Project(name="<Block>", path=..., layout=False))
  spec.md                         ports, configs and their valid ranges, limits and why, open items
  analysis.py                     parameterised worst-case analysis (see below)
benches/<Block>.zen               bench board: declared nets with voltages, one instance with reference configs
benches/<Block>/eda/              the arranged REFERENCE sheet (stamped onto boards) and bench root sheet
benches/<Block>/docs/             generated datasheet, charts and values.json for the reference configs
analysis/                         shared helpers (library loader, report writer); no block-specific numbers
tools/                            check_sync, update_notes, stamp_block, render, netcmp, erc (shared by all blocks)
```
- A block package must not reach outside its folder with relative paths (`pcb` fails); shared Zener code goes in
  its own package and is imported by URL.
- Bench boards are where the block's gates run: `pcb build -Dwarnings`, sync check, ERC, renders. Several boards
  in one workspace build and apply independently, each with its own `path=` for `eda/` (verified with root-level
  `.zen` files; boards in subdirectories: verify first).
- Never nest another `[workspace]` (library or blocks repo) inside a board repo: keep checkouts as siblings.
- A repository whose name states one part (`ina229`) should be renamed for its new scope BEFORE any board imports
  from it: the repository path is part of every import URL and tag.

## Versioning
- Release each block with a tag `blocks/<Block>/vX.Y.Z` (`pcb publish`, or a manual tag if it needs a TTY).
- A board pins each block with `pcb add github.com/<owner>/<repo>/blocks/<Block>@<version>`; never hand-edit
  versions. The block's analysis is pinned to the SAME tag (below); bump both together.
- Patch: notes, docs, analysis fixes that change no result direction. Minor: new configs with backward-compatible
  defaults, new analysis outputs. Major: any port, topology or default change.

## Analysis per instance
- `analysis.py` exposes a function, e.g. `analyze(params) -> values` (the instance's configs and operating
  conditions in, a dict of results out), plus a report writer that renders one instance's datasheet section and
  charts. Datasheet equations come only from the component library (`calc.py`); the block adds the composition
  (self-heating, stack-ups, calibration) labelled "not a DS equation".
- The bench calls it with the reference configs and writes `benches/<Block>/docs/`.
- A board calls it once per instance (from a pinned checkout of the blocks repo at the block's tag, loaded like the
  library's `_zl.py`), writing one values file and one datasheet section per instance, plus board-level results
  that need more than one block (total dissipation, rail budget, interaction such as a switch's Rds(on) seen by a
  monitor's bus voltage).
- Values files are keyed by instance name, so the notes script fills each instance's notes on the parent sheet.

## Schematic reuse
- `pcb` generates one child sheet per instance in the board's own `eda/`, unarranged; the module's `Project(path=)`
  is not a template (`schematic-style`, toolchain facts). So each board STAMPS the block's reference sheet:
  1. Generate the board fresh once (so the root has the sheet symbols).
  2. For each instance: copy the reference sheet to `eda/<instance>.kicad_sch`, rewrite the instance prefix of
     internal labels (`INA.` -> `<instance>.`), give every item a new UUID, and transplant the root's rail sheet
     pins if missing.
  3. `pcb apply schematic --no-open` twice (second unchanged), netlist diff against a fresh generation, ERC.
  Put this in one committed script (`tools/stamp_block.py`) and test it on the bench before any board uses it;
  until then it is unverified for renamed instances.
- Never re-arrange a block's internals on a board. Fix the reference sheet in the blocks repo, release, re-stamp.
- Reference-sheet notes hold for every instance (limits, reasons, roles). Instance numbers (full scale, error,
  scaling, dissipation) go in the DESIGN VALUES box beside the sheet symbol on the parent, filled from the
  instance's values by the notes script.
- The board's top sheet is a block diagram (`schematic-style`, Hierarchy): blocks left to right along the power
  path, chained through `BUS_IN`/`BUS_OUT` at the same height, interfaces to the right, rails up, ground down.

## Adding a new block (checklist)
1. Spec first: purpose, ports from the standard table, configs and valid ranges, requirements to bound.
2. Library parts exist (or are added to the library and released first).
3. Module + bench board; `pcb build -Dwarnings` exit 0 on the bench.
4. `analysis.py` with `analyze(params)`; bench datasheet generated; every requirement judged with margin.
5. Reference sheet per `schematic-capture` (freeze, pre-flight, generator script, annotate, gates, adversarial
   review).
6. Release the tag; record standard-port additions here.
