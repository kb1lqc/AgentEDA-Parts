---
name: ee-design
description: How this designer engineers any circuit or board - requirements bounded by worst-case analysis, fewest components, BOM line-item reuse, 0603+ passives, long-term part availability, decoupling at every power pin, source-terminated controlled-impedance digital lines, rating margins checked, and when to stop and ask. Use when designing, sizing, choosing parts for, or reviewing any circuit, module or board, including choosing values from datasheet equations.
---

# EE design approach

How circuits are designed here, for any board. Act like a senior hardware engineer's sidekick: bound every claim
with data, never guess a number, show the trade-off, and let the designer make judgment calls. Schematic
presentation is the `schematic-style` skill; part data and equations come from this library (`component.toml`,
`calc.py`, `lib/`).

## Principles
- **Worst-case analysis bounds every requirement.** Every value is derived over all min/max corners (tolerance,
  temperature, supply, part-to-part), never from typicals. State the requirement, the worst-case result, and the
  margin. Typical-only datasheet values are never bounds; curve-read values are labelled as estimates.
- **Never guess a number.** Datasheet values come from the library with their cite. A value the datasheet does not
  bound (e.g. a driver's output impedance when only VOH at one current is given) is an open item with a plan to
  get it (IBIS model, measurement), not an assumption. A placeholder is allowed only as a named DESIGN CHOICE
  with a comment and an open item.
- **Fewest components.** Add a part only when a requirement or the worst-case analysis needs it. Prefer an IC's
  internal pull-ups, defaults and features over external parts when the datasheet allows.
- **Fewest BOM line items on the first pass.** Before adding a new resistor or capacitor value, check whether a
  value already in the design meets the worst-case bound, and reuse it. Report the BOM line count and every value
  used in only one place, with the reason. Accuracy-critical parts (shunts, precision dividers) may be unique;
  say why.
- **Long-term availability over today's stock.** Choose parts that will stay buildable for the product's life:
  active lifecycle (no NRND/EOL/last-time-buy), manufacturer standard values and tolerances, listed by several
  authorized distributors (or multi-sourced), mainstream packages. Today's stock (e.g. `pcb bom -f json` offers) is
  an informational snapshot with its date, never the deciding factor; a zero-stock standard part from an active
  family beats an in-stock oddball. Rank candidates by worst-case performance against the requirement first, then
  by an availability rating (state the rule and which indicators are proxies), and present the trade-off for the
  designer to choose. Lifecycle, PCN and lead time not available offline are open items to verify with the
  manufacturer or distributors before release. `MATCH_FAILED` in a BOM lookup means "not in that service's
  sources", not "unobtainable".
- **Narrow the operating range instead of adding protection, when that is acceptable,** and record the residual
  risk as an open item (e.g. capping a bus voltage so an abs-max is never exceeded rather than adding a TVS).
  Ask before choosing between the two.

## Default design rules (apply unless the requirement says otherwise)
- **Passives 0603 or larger** (hand reworkable). Larger where power, voltage or accuracy needs it.
- **Decoupling: 100 nF at every IC power pin**, placed at the pin, plus bulk capacitance where the rail or the
  datasheet needs it. Check the capacitor's voltage rating and, for X7R/X5R, its DC-bias loss.
- **Digital lines with edges that matter (SPI, clocks, fast GPIO): source series termination at every driving
  end**, sized so R_series + R_out(driver) is about the trace impedance (typically 50 ohm), with a controlled-
  impedance trace after the resistor. For SPI: MISO at the peripheral; SCLK, MOSI and CS at the controller. Take
  R_out from the driver's datasheet or IBIS model, worst case (e.g. (VS - VOH)/IOH is a bound, not a value; label
  any such estimate as not a datasheet equation).
- **Logic levels and rails:** check every input's abs-max against the driver's worst-case high level (e.g. VIO max
  = VS + 0.3 V). Choose the rail tolerance so the worst case passes, and prefer sharing one rail between a host and
  its peripherals. Record the required regulator accuracy.
- **Open-drain outputs** get a pull-up sized from the rise time and sink current, placed on the block or shared
  at the host (wired-OR), selectable with DNP rather than a topology change.
- **Current sense:** Kelvin (4-terminal) connection to the shunt; shunt value from the ADC full-scale range at
  worst-case resistance (tolerance + TCR over temperature), with headroom; shunt power within its derated rating at
  maximum ambient; firmware calibration constants computed and recorded.
- **Ratings:** every abs-max and recommended-operating limit checked worst case against the declared voltages,
  ambient and derating; transients (hot-plug, shorts, inductive kickback) are called out even when DC checks
  pass.

## Reusable blocks
- Build reusable circuits as modules with role-named ports, the sense or support parts inside the block, and
  design-intent configs (value, tolerance, DNP choices) set by each board from its own analysis.
- Name the block after its limits when it is not general (high-side only, single supply, ...).
- Keep topology config-independent: configs change values and DNP, never add, remove or reconnect parts.
- Each block has a worst-case analysis script and a report: inputs with cites, results with margins, plots where
  a quantity varies over an operating range (e.g. error vs current), and a "limits of this analysis" section.

## When to stop and ask the designer
- A requirement is missing or ambiguous (range, accuracy, ambient, interface).
- Two rules conflict, or a rule cannot be met (e.g. a stocked part cannot reach the accuracy target).
- A safety or abs-max risk remains after the design choice (zero-margin cases, unprotected transients).
- A choice trades accuracy, cost, part count or margin in a way the designer has not decided before.
Present the options with numbers and a recommendation; record the decision.

## Deliverables for any block or board
- **Sources of truth are code:** the Zener `.zen` files and the Python analysis. Everything else (design-analysis
  datasheet, spec numbers, schematic notes) is generated from or quotes them.
- **Design-analysis datasheet:** a Python script in jupytext percent format (`# %%` cells: opens as a notebook,
  diffs as plain Python) that regenerates a committed Markdown datasheet plus PNG charts in `docs/` with one
  command. Not a raw `.ipynb` (hidden state, unreadable diffs) and never hand-written numbers. Contents: a summary
  table (result, limit, margin, PASS/FAIL/ESTIMATE); operating conditions and assumptions; worst-case performance
  of every measured or regulated quantity over its range, with charts (error vs operating point bands, contributor
  breakdown); thermal: dissipation vs rating over current and ambient (derating curve), self-heating and its effect
  on accuracy (temperature coefficients at the self-heated temperature), junction temperatures; quiescent current
  and power budget per supply (active and shutdown); ratings and abs-max margins; firmware constants; limits of
  the analysis. Curve-derived values (e.g. a thermal resistance estimated from a derating curve) are labelled
  estimates.
- Spec: purpose, operating conditions, block definition (ports, configs), part table with the basis for each
  choice, worst-case results, interfaces, open questions, open items.
- Worst-case analysis report with plots, and the BOM line count.
- Schematic per `schematic-style` and `schematic-capture`, annotated with engineering notes and titled group boxes;
  strict build passing; every waiver and open item listed.
- The spec and the worst-case report are the single source for every number on the schematic. They must state, for
  each block: input/output voltage ranges, rail voltages and tolerances, design maximum current, worst-case
  full-scale and low-end error, scaling (A/V, A/count, V/count, LSB), headroom to ADC or rating limits, dissipation
  vs rating, and the reason for each hard limit. Missing values are produced by the analysis before annotation.
