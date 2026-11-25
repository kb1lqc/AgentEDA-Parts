---
name: ee-design
description: Use when designing, sizing, selecting parts for or reviewing any circuit or board: worst-case bounds, BOM minimisation, accuracy and thermal analysis, default design rules, when to ask.
---

# EE design approach

Bound every claim with data, never guess a number, show the trade-off, let the designer make judgment calls. Part data and equations come from the AgentEDA-Parts (`component.toml`, `calc.py`, `lib/`). This skill governs circuit design; library-part extraction uses the library's defaults table instead of questions.

## Principles
- **Worst-case analysis bounds every requirement.** Derive every value over all min/max corners (tolerance, temperature, supply, part-to-part); state requirement, result, margin. Typical-only values are never bounds; curve-read values are labelled estimates.
- **Never guess a number.** Datasheet values come from the library with their cite. A value the datasheet does not bound is an open item with a plan (IBIS, measurement); a placeholder is allowed only as a named DESIGN CHOICE with a comment and an open item.
- **Fewest components.** Add a part only when a requirement or analysis needs it; prefer an IC's internal features.
- **Fewest BOM line items.** Reuse a value already in the design if it meets the worst-case bound. Report the BOM line count and each single-use value with its reason; accuracy-critical parts (shunts, precision dividers) may be unique, say why.
- **Long-term availability over today's stock.** Choose active-lifecycle parts, standard values, several authorized distributors, mainstream packages. Stock is a dated snapshot, never decisive. Rank by worst-case performance, then a stated availability rule. Offline lifecycle, PCN and lead time are open items. `MATCH_FAILED` means "not in that service's sources", not "unobtainable".
- **Every number comes from a script run**, never reasoned out.
- **Prefer narrowing the operating range to adding protection;** record residual risk; ask first.
- **Topology from the rendered datasheet figure, not extracted text.** Re-derive every rating when a return node changes; the verifier re-checks from its own render.

## Default design rules (apply unless the requirement says otherwise)
- Passives larger than 0603 where power, voltage or accuracy needs it (0603 floor: circuit-blocks `tools/check_env.py`).
- 100 nF at every IC power pin, at the pin, plus bulk where the rail or datasheet needs it. Check voltage rating and X7R/X5R DC bias.
- Digital lines with edges that matter (SPI, clocks, fast GPIO): source series termination at every driving end, R_series + R_out(driver) about the trace impedance (typically 50 ohm), controlled-impedance trace after it. SPI: MISO at the peripheral; SCLK, MOSI, CS at the controller. Take worst-case R_out from the datasheet or IBIS; label an estimate as not a datasheet equation.
- Check every input's abs-max against the driver's worst-case high level; choose rail tolerance so it passes, prefer one rail for host and peripherals, record the regulator accuracy needed.
- Open-drain outputs: pull-up from rise time and sink current, DNP-selectable.
- Current sense: Kelvin connection; shunt from ADC full scale at worst-case resistance (tolerance plus TCR) with headroom; shunt power within its derated rating at maximum ambient; record firmware calibration constants.
- Check every abs-max and recommended-operating limit worst case against declared voltages, ambient, derating; call out transients (hot-plug, shorts, kickback).

## Accuracy and thermal analysis (any measured or regulated quantity)
- **Solve self-heating, do not assume it.** A part whose parameters depend on its own dissipation runs at a self-consistent temperature (x = theta x P(T_ambient + x), iterated to a stated residual, worst-case P); evaluate its parameters there, other parts at their own temperature (ambient or own junction). A theta read off a curve is an ESTIMATE, an unstated temperature limit an ASSUMPTION: label both, mark dependent results.
- **Beginning-of-life (BOL) shifts belong in every accuracy result.** Read the performance table in full, including fixed terms (+/-(0.5 % + 0.0005 ohm)); test limits are bounds, an unstated typical shift is unusable. Check BOL terms at part selection. End-of-life drift is the designer's scope decision, an open item when out.
- **Report uncalibrated and calibrated, and say which is judged.** If only calibration meets the requirement, make it a production requirement in the spec; model it: list what it removes (fixed gain terms) and what remains (tempco between operating and cal temperature, drift, reference accuracy, offset, quantisation); compute whether gain or offset calibration helps first.
- **Every accuracy result has an error stack-up** (format: `analysis-report.md` in the circuit-blocks repo). The judged total is the worst case over all corners together, never a linear sum or RSS.
- **Report margin.** Flag a pass that is thin before BOL or calibration effects.
- Assert a known value to prove unit conventions (percent vs fraction).
- **Pushing an operating limit:** sweep it in a scratch script, report the largest value that passes worst case, let the designer pick a round value (a design input with its basis).

## When to stop and ask the designer
- A requirement is missing or ambiguous (range, accuracy, ambient, interface).
- Two rules conflict, or a rule cannot be met.
- A safety or abs-max risk remains after the design choice.
- A choice trades accuracy, cost, part count or margin in a way not yet decided.
Present options with numbers and a recommendation; record the decision.

## Deliverables for any block or board
- Sources of truth are code: `.zen` files, Python analysis, params. Everything else is generated from or quotes them.
- Numbers flow one way: analysis, `values.json`, datasheet and notes. Spec text and `.zen` comments cite a section or key, never a copied number.
- Blocks: `reusable-blocks`; report format `docs/spec/analysis-report.md` (circuit-blocks).
- Schematic per `schematic-style`, annotated, strict build passing, waivers and open items listed.
