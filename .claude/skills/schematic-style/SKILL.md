---
name: schematic-style
description: House style for drawing and reviewing any circuit schematic (KiCad, generated from Zener with pcb apply schematic, or hand-drawn) - left-to-right signal and power flow, power symbols up and ground down, labels on wires, support parts at their pins, crossings replaced by labelled stubs, reusable blocks as hierarchical sheets, role-based port names, complete title blocks. Use whenever a schematic is generated, arranged, reviewed or critiqued, for any board or module.
---

# Schematic style

A schematic is a document for a reader who must understand, review and debug the circuit without the designer in
the room. Every rule below serves that: the eye should follow function, not hunt for connections. The rules are
general; examples are illustrations, not the scope. Where the toolchain cannot do something, the fallback is given.

Schematic first: do no PCB layout work (no `pcb layout`, no `.kicad_pcb` edits) until the designer says layout has
started.

## Flow and placement
- **Left to right.** Signals and power flow from inputs on the left to outputs on the right, in the order they
  are processed. A reader scanning left to right reads the circuit's story.
  - Examples: connector -> protection -> regulator -> load; sensor -> filter/amplifier -> ADC -> digital interface;
    high-side current sense: supply enters left, passes through the shunt, exits right, with the sense IC below
    the shunt and any input network running down from the shunt taps to the IC.
- **Orient parts to the flow.** Rotate or mirror (`(mirror y)`) a symbol so its inputs face the source and its
  outputs face the destination. Prefer mirroring over long wires that wrap around a part.
- **Support parts at the pin they serve.** Decoupling capacitors next to the power pin they bypass; series
  terminations next to the driving pin; pull-ups/pull-downs next to the pin they bias (with a junction on that
  pin's wire); feedback dividers next to the feedback pin; crystals and load capacitors next to the oscillator
  pins. The schematic then shows which part belongs to which pin, and the layout engineer inherits that intent.
- **Group by function.** Each functional group (input protection, regulation, sensing, interface) is a visible
  cluster with whitespace between groups.

## Power and ground
- **Power symbols up, ground down.** Rails feeding parts are power symbols pointing up at the top of the part;
  ground symbols point down at the bottom. No rail wires running across the sheet.
- **Never rotate a rail symbol to dodge a pinout.** If a pinout puts a rail pin below a ground pin (or otherwise
  forces the rail and ground wires to cross), route the rail wire around so the symbols keep pointing up and down.
- **Power paths through a block are nets, not rail symbols.** A path that carries load power through a block (a
  bus through a shunt, a switch, a fuse or an eFuse) is a labelled net entering on the left and leaving on the
  right, so the reader sees the path. Rails that only feed parts stay power symbols.
- **Rail names carry the intended voltage** (`V3V3`, `V5`, `VBAT`, `V12_IN`): the reader knows the level without
  looking it up. Identifiers cannot start with a digit, so `V3V3`, not `3V3`.

## Wires, labels and crossings
- **Every label sits on a wire**, and the wire is long enough that the label fits along it. No label floats at a
  bare pin end; a label on a pin is easy to misread as unconnected.
- **No crossings where a reroute or a label avoids them.** When two connections would cross, draw both nets as
  labelled wire stubs at each end, symmetrically, with no wire between. Never rely on a four-way junction.
- **Junction dots** at every T; no four-way junctions.
- **No text overlaps a wire, pin, symbol or other text** - including the text of net labels, hierarchical labels
  (ports), global labels, sheet pins, power-symbol names, references, values and fields. A label's text runs
  along its own wire, never across another one; leave clearance between parallel wires so neighbouring labels do
  not touch. Reference and value sit beside their symbol.
- **Grid:** everything on the 1.27 mm (50 mil) grid so wires land exactly on pins.

## Names
- **Net and port names state role, not part pin names.** `BUS_IN` / `BUS_OUT` for a power path, `V3V3` for a
  rail, `SENSE_P` / `SENSE_N` for a differential pair; not `I_IN`, `VS`, `PIN6`.
- **Active-low signals end in `_N`** (`ALERT_N`, `RESET_N`, `CS_N` where the name is ours to choose).
- **Differential pairs end in `_P` / `_N`** (KiCad pairs nets by these suffixes).
- **Board-level nets are plain** (`SPI_MISO`, `V3V3`) and drawn as **local labels**, not global labels. Nets internal to a reusable module keep the instance
  prefix the tool adds (`INA.SENSE_P`), using a short instance name; do not expose internal nets as ports just to
  shorten labels.
- **Module names state their limits** when the block is not general (`...HighSideMonitor`, `...3V3Only`), so a
  reuser cannot misapply it.

## Hierarchy
- **Each reusable module is its own hierarchical sub-sheet**, reused unchanged on every board. The parent shows
  the sheet symbol with the module's ports: inputs on the left edge, outputs and interfaces on the right edge.
- **Power paths flow through the sheet symbol.** A block's power-path ports sit at the same height on opposite
  edges (e.g. `BUS_IN` left, `BUS_OUT` right), so the path reads as one straight wire through the block. Interface
  pins group above or below it on the right edge; rails on the top edge, ground on the bottom edge.
- **The reusable sheet carries no board net names.** Ports appear inside as hierarchical labels named after the
  module's ports; the parent maps board nets to them.
- **Rails and ground are local inside a reusable sheet.** Inside the block, V3V3 / GND (and any rail) are
  hierarchical labels connected through sheet pins; global power symbols appear only on the top-level sheet, where
  the board rails are defined. The block then makes no assumption about which rail it sits on. Power symbols
  pointing up/down still apply on the top level and on non-reusable sheets.
- **Interfaces as harnesses** (a bus group carrying SPI, I2C, ...) are preferred where the toolchain keeps them;
  otherwise one sheet pin per member, grouped together on the sheet edge.

## Engineering notes and grouping boxes
- **Minimal, high-impact notes** at the power path input and output, at each rail and at key parts: expected
  voltage range, rail voltage and tolerance, design maximum current, worst-case full-scale error, scaling (A per V,
  A per count, LSB), key limits and why (e.g. a cap set by an abs max). Short lines with units, no prose. Drop any
  note that only repeats a label, unless the designer asks to keep it.
- **Every number comes from the spec or the worst-case analysis report**; only unit conversions are derived (say
  so). Never type a value from memory.
- **Instance values on the parent, block notes on the reusable sheet.** The parent sheet carries this board's
  numbers next to the block (with a boxed design-values summary); the reusable sheet carries notes about the block
  itself and only the values its configs set.
- **Group with titled boxes.** Draw rectangles (one stroke style per meaning, e.g. dashed = functional group) around
  functional areas and note groups, each with a short title at the top-left inside the edge (e.g. POWER PATH /
  CURRENT SENSE, LOGIC SUPPLY, SPI / ALERT, DESIGN VALUES). Boxes never cut through symbols or text; a net leaving a
  group crosses the edge at a right angle. Even margins (>= 2.54 mm) between edge and contents.
  - Plan box edges from the real text extents (pin names and numbers, rotated label text, reference/value,
    symbol body), not from pin and wire geometry: keep >= 2.5 mm clearance. Estimate text at about 1.08 mm per
    character for 1.27 mm font, then confirm in a render.
  - Groups whose parts interleave (one group's symbol above another's stubs) cannot each get a clean rectangle
    without moving parts: merge them into one box and let a note name the sub-function.
  - Adjacent boxes need a channel of >= 2.5 mm between them.
  - Use a dashed rectangle plus a separate bold title (about 1.524 mm) and plain text rather than a KiCad
    `text_box`, so one stroke style keeps one meaning and titles can be larger than notes.
- Notes sit on the free side of what they describe, never touching a wire, pin, symbol, label or other text.
  Plain `text` with embedded line breaks gives clean multi-line notes; right-justify notes placed left of a part.

### Annotation checklist (what each kind of circuit should state)
Show only the items that apply; every value from the spec or the worst-case report.
| Where | Note content |
|---|---|
| Power input | voltage range (min-max, AC/DC), polarity or side (high/low), max current, transient or abs-max limit and its reason |
| Power output / load side | what it feeds, max current, what is measured or switched there |
| Each rail | nominal and tolerance, accepted range of the parts on it, decoupling at which pin |
| Regulator / converter | input range, output setpoint and worst-case accuracy, max load, efficiency or dissipation if it drives thermal design |
| Current / voltage sense | sense element value and tolerance, full-scale value, headroom to the ADC range, scaling (A/V, A/count, V/count, LSB), worst-case error at full scale and at the low end, calibration constants |
| Divider / feedback | ratio, worst-case output range, what sets it |
| Digital interface | bus and line impedance, where terminations are and their values (placeholders flagged), logic level, active-low and open-drain notes |
| Protection | what it protects against, clamp/trip levels, and any residual risk |
| Parent sheet | a boxed DESIGN VALUES summary of the block instance: operating conditions, key part choices, scaling, worst-case results, dissipation |

## Title block (every sheet)
Title, revision, date, company, author, the repo URL plus git short hash, and a one-line description of what the
sheet contains. A printed sheet must identify itself.

## Toolchain facts: Zener / pcb 0.4.102 with KiCad 10
- **Sub-sheets:** a module becomes its own KiCad sub-sheet when it declares
  `Project(name="<Module>", path="<anything>", layout=False)` (stdlib `properties.zen`). `path` is required; without
  it the module is flattened. The parent gets a sheet symbol named after the instance with one sheet pin per port;
  the child file is `<instance>.kicad_sch` next to the root. A second `Project()` at the root writes a full copy
  of the design, not a sub-sheet.
- **Net types decide the drawing:** `Power` and `Ground` nets become power symbols; plain `Net`s become labels, and
  inside a sub-sheet a plain-`Net` port becomes a hierarchical label. A `Power` net passed into a sub-sheet shows
  up inside as a global power symbol named after the board net, and KiCad ERC reports that sheet pin unmatched:
  declare power paths into reusable sheets as `Net(voltage=...)` (voltage checks still run).
- **Local rails in a sub-sheet (verified recipe):** library wrappers type supply pins as `Power` (cast at the
  pin) and ground pins as `Ground`, so inside a block those nets are always drawn as global power symbols. To make
  them local: declare the module ports as plain nets (`V3V3 = io(Net)`, `GND = io(Net)` then
  `_GND = Ground(GND)` and connect library ground pins to `_GND`); the board keeps `V3V3 = Power(..., voltage=...)`
  so voltage checks still run. The root gets V3V3/GND sheet pins. Then replace each V3V3/GND power symbol in the
  child with a `hierarchical_label` of the same name at the symbol's pin point (angle 90 for a rail, 270 for
  ground). `pcb apply` keeps it, the netlist is unchanged and ERC finds every sheet pin matched. A fresh
  regeneration brings the power symbols back, so this swap is a scripted step re-run after any regeneration.
  - On an already-arranged sheet, an incremental `pcb apply` does NOT add the new V3V3/GND sheet pins or root
    power symbols after the port-type change, and still reports success while the rails are split into
    `/INA/V3V3` and `/INA/GND` (only the netlist diff shows it). Generate a throwaway fresh copy, transplant the
    root's new sheet pins, power symbols and their `lib_symbols` entries by script, then place them by hand.
  - For a ground label pointing down (angle 270) use `justify right`; `justify left` folds the text back over the
    wire.
- **Internal net names** are always `<instance>.<net>`, even for an explicitly named `Net()`. A `Net("X")` assigned
  to a variable `X` only triggers a `style.redundant_name` advice; write `X = Net(...)`.
- **Interfaces** (stdlib `Spi`, `I2c`, ...) become one hierarchical label and sheet pin per member (`SPI.CS`, ...).
  A hand-drawn KiCad bus group does not persist: `pcb apply` accepts it only with breakouts named as group members,
  then rewrites it into separate pins and leaves the breakouts dangling (ERC errors that `pcb build` does not
  catch). Keep members as separate pins until pcb supports buses.
- **`pcb apply` is incremental.** It keeps hand-moved symbols, wires, labels, text, graphics and the title block,
  and refuses any edit that changes connectivity ("not netlist-equivalent"): use that as the safety check for hand
  edits. Net-name, net-type and new-sheet changes often only appear on a fresh generation (delete the `.kicad_sch`
  files, apply again), which loses hand placement. **Finish the Zener code first, regenerate once, then arrange.**
- **Editing S-expressions by hand:** schematic Y grows downward; pin positions in `lib_symbols` are relative to
  the symbol origin and transformed by the instance rotation and mirror (rot 0: sheet = (at.x + x, at.y - y)).
  Move a symbol's Reference and Value `(at ...)` with it. KiCad 10 writes `(sheet` followed by a newline, so
  search with `\(sheet($|\s)`.
  - Read each symbol's real pin geometry from `lib_symbols`; do not assume symmetry (e.g. a resistor symbol with
    pin 1 at +7.62 and pin 2 at -5.08). A wrong guess leaves a pin unconnected or shorts two nets.
  - Field text angles on rotated symbols behaved differently in two passes (absolute in one, relative to the
    symbol rotation in another): set `do_not_autoplace` on hand-placed fields and confirm the angle in a render.
  - Hierarchical-label flags draw on one side of the anchor depending on the angle (0: text to the right, 180:
    to the left); put the flag at the far end of its wire so the text points away from the wire.
  - Rotating an IC 180 degrees (not mirroring) reverses its pin order top to bottom; it can put a rail pin above
    a ground pin so both run straight up and down.
  - Local-label text sits about 0.3-0.5 mm above its wire; at 2.54 mm pin pitch neighbouring label text nearly
    touches the wire above. Fan stacked label wires out to 5.08 mm pitch with nested jogs (the lower pin's jog
    closer to the IC).
  - Plan room for a pull-up's vertical drop and its rail symbol before routing a stacked pin group: a pull-up on a
    middle pin forces the pins above it to jog around it.
  - `pcb apply` refuses a hand edit that shorts or splits nets ("not netlist-equivalent: nets ... are shorted"),
    which catches bad coordinates before they are written.
- **KiCad ERC label rule:** a LOCAL label on a sheet with no component pin, on a net with more than one pin inside a
  sub-sheet, is reported as `label_dangling` (KiCad `ercCheckLabels`). It is not a wiring fault. A global label
  clears it but changes the net name (no leading `/`). House convention: keep local labels for board-level nets
  and accept these until the board's connectors or host exist.
- **KiCad 10 symbols** (format 20251024+) are required by `pcb apply`; `python3 -m lib.check` enforces it for
  library parts.
- **Close KiCad** (no `*.lck` next to the schematic) before running `pcb apply`, or a KiCad save can overwrite it.
  `kicad-cli` run on files inside the project folder can leave stale `.lck` files too: run it on copies.

## Procedure
1. Finish the circuit in code; `pcb build -Dwarnings <board>.zen` exits 0.
2. Regenerate fresh: back up and delete the `.kicad_sch` files, run `pcb apply schematic --no-open <board>.zen`
   twice (the second must report `schematic unchanged`).
3. Arrange in small steps per the rules above. After each step: `pcb apply schematic --no-open` (exit 0; if not
   netlist-equivalent, restore the last backup), then render and look:
   `kicad-cli sch export pdf --output <scratch>/s.pdf <root>.kicad_sch && pdftoppm -r 110 -png <scratch>/s.pdf <scratch>/s`
   (all sheets export; on macOS `kicad-cli` is `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`).
4. Fill every sheet's title block.
5. Finish: apply twice (second unchanged), `pcb build -Dwarnings` exit 0, and `kicad-cli sch erc` with zero
   dangling labels, dangling wires and hierarchical-label mismatches. Expected while the board is incomplete,
   and to be re-checked once it is: `isolated_pin_label` (a net reaching only one real pin because its connector
   or host is not drawn yet), `pin_not_driven` (inputs whose driver is off-sheet or not drawn yet) and
   `power_pin_not_driven` (no regulator, input connector or PWR_FLAG on the rail yet). `lib_symbol_issues` means
   KiCad's ERC has no symbol library table for the parts: a project-configuration notice, not a circuit error.
   Review each render against every rule before showing it.
6. **Count your hand-added items after every apply** (top-level `(text`, `(text_box`, `(rectangle`): an item
   inserted inside a `lib_symbols` entry (e.g. found by searching for a nested `(embedded_fonts`) is silently
   dropped by `pcb apply` with exit 0. Insert top-level items before the file's final `)`.
7. **Diff the netlist after every apply**, not just its exit code: `pcb apply` has been seen to drop a hand-placed
   label silently (net gone, still "updated", exit 0). Export with
   `kicad-cli sch export netlist --output <scratch>/n.net <root>.kicad_sch` before and after, and compare nets.

## Review checklist
- Can a reader follow each function left to right without hunting?
- Is every support part at the pin it serves, and is every label on a wire?
- Any crossing, rotated rail symbol, floating label, or any text (labels, ports, sheet pins, fields) touching a wire?
- Do names state role (ports, rails with voltage, `_N`, `_P`/`_N`)?
- Is each reusable block a sub-sheet with no board net names inside?
- Is every title block complete?

## Open style questions (ask when they come up; record the answer here)
- Value text shown on parts (MPN, or value such as "100nF 50V X7R") and reference designator style.
- Sheet size, text sizes.
