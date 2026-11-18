---
name: schematic-style
description: Use when planning or running schematic generation or arrangement, delegating schematic work to agents, or generating, reviewing or critiquing any schematic: flow, grouping, naming, notes, title blocks, review checklist.
---

# Schematic style

The reader must understand and debug the circuit without the designer. No layout work (`agent-roles`). Workflow, gates, agent jobs: `docs/briefs/schematic-capture.md` (give it to delegated agents). Toolchain facts: `docs/spec/pcb-toolchain.md`. Sheet-symbol geometry: `docs/spec/blocks.md` (circuit-blocks).

## Flow and placement
- Left to right in processing order (connector, protection, regulator, load). High-side sense: supply in left through the shunt, out right, sense IC below.
- Rank nets: main power path straight first, then the primary data path; pull-ups, timing, bias and configuration bend, drop below or become labelled stubs.
- Group by function into visible clusters with whitespace: power together, data buses together, status and control (`ALERT_N`, `FAULT_N`, `PGOOD_N`) in their own group. 
- Use one bus order on every sheet (SPI: CS, SCLK, MOSI, MISO; I2C: SDA, SCL); stub or re-pin the symbol when pin order interleaves.
- A net never crosses a group box it does not belong to; a tap feeding another group is a labelled stub in each box.
- Orient parts to the flow; mirror, do not wrap wires.
- Support parts sit at the pin they serve: terminations at the driving pin, pull-ups beside the biased pin, dividers at the feedback pin, crystal loads at the oscillator. A decoupling capacitor may sit in a nearby group if its note names part and pin.
- Dividers are vertical: source top, ground bottom, taps right. A drive chain reads from IC pin to driven part; a support pair for another pin pair (bootstrap) gets its own group.

## Power, wires, labels
- Power symbols up, ground down; never rotate a rail symbol to dodge a pinout (route around; rotate the IC 180, not mirror, to put rail above ground). Power paths through a block are labelled nets; rails that only feed parts are power symbols.
- Every label sits on a wire long enough for it.
- Replace crossings with labelled stubs, no wire between. Junction dot at every T, no four-way junctions.
- No text overlaps a wire, pin, symbol or other text; leave clearance between parallel wires.
- Everything on the 1.27 mm grid; `(paper "USLedger")` on every sheet.

## Names
- Names state role, not pin: `BUS_IN`/`BUS_OUT`, `V3V3`, `SENSE_P`/`SENSE_N`; active-low `_N`; pairs `_P`/`_N`.
- Board-level nets are plain with local labels. Module-internal nets keep the instance prefix (`INA.SENSE_P`), not exposed as ports.
- Module names state limits.

## Hierarchy
- Each reusable module is a sub-sheet, reused unchanged: inputs left, outputs and interfaces right on the parent symbol; no board net names; ports are hierarchical labels.
- Each port appears once in a sheet, in the box owning that function; other uses are local labels wired into the same wire group. A far-apart use may take a second port flag. Re-ordered port lines are labelled stub pairs; never leave a wire end dangling.
- Rails and ground are hierarchical labels inside a reusable sheet; global power symbols only on the top sheet.
- The top sheet is a block diagram (sheet symbols, connectors) in power and signal order, DESIGN VALUES beside each block.

## Component text
R and C value stacks are generated, never typed: `tools/schematic/passive_text.py` (circuit-blocks).

## Notes and group boxes
- One-line, high-impact notes next to the part, setpoints as equations, result last (`R5: V(SCP) = <min>-<max> mV -> I(SC) = <min>-<max> A`). No headings or paragraphs; drop a note that only repeats a label; right-justify notes left of a part. A part setting a quantity states it and its consequence in user units.
- Every number comes from the spec or worst-case report (unit conversions aside); never type one from memory.
- Instance values go in a boxed DESIGN VALUES on the parent (6-10 lines: rating, trip points, timing, worst margin, any FAIL); the reusable sheet carries notes true for every instance.
- Titled dashed rectangles around functional areas (title top-left, bold about 1.524 mm, not `text_box`). Boxes cut through nothing; nets cross edges at right angles; margins and channels >= 2.5 mm. Size from real text extents (about 1.08 mm per character); merge interleaved groups.

Annotation checklist (only what applies):
- Power input: voltage range, polarity, max current, abs-max limit and reason; what it feeds. Power output: rail, load side, max current.
- Rail: nominal, tolerance, decoupling at which pin.
- Regulator: input range, setpoint, accuracy, max load, dissipation.
- Sense: element value and tolerance, full scale, ADC headroom, scaling, worst-case error (full scale, low end), calibration.
- Divider: ratio, range. Interface: impedance, terminations, logic level, placeholders flagged, open-drain notes. Protection: threats, trip levels, residual risk. Parent sheet: DESIGN VALUES.

## Title block
Every sheet: title, revision, date, company, author, repo URL plus short hash of the commit where that sheet last changed, one-line description.

## Procedure
Follow the brief's phases and gates; after every `pcb apply`, diff the netlist, not the exit code. Review every render against the checklist before showing it. Record new preferences in the board repo's `docs/notes/style-notes.md`; promote generic ones here.

## Review checklist
- Can a reader follow each function left to right?
- Is every support part at its pin, every label on a wire?
- Any crossing, rotated rail symbol, floating label, or text touching a wire?
- Do names state role?
- Is each reusable block a sub-sheet with no board net names?
