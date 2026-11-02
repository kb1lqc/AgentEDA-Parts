# Component checklist

Read at the start of every component task. CLAUDE.md gives the procedure. This file lists what to extract and check at
each step. Every item ends in a table row, a check, an `UNCHECKED:` line, a Decision Log row, or an open item. Nothing
gets skipped silently. Reference package: `components/TexasInstruments/INA821IDGK/`.

## A. Pre-flight and intake (steps 0, 1)
- [ ] Pre-flight: one message, sent once, listing everything missing that only I can supply, with exact paths:
      datasheet PDF -> `docs/datasheets/<basepart>.pdf`; manufacturer KiCad export (Ultra Librarian/SnapEDA) unzipped ->
      `docs/vendor/<Value>/`, no PDF inside; package STEP -> `docs/vendor/<Value>/<package>.stp`, or "none exists".
      Claude handles skills, root `pcb.toml`, vendor folder cleanup and the import itself.
- [ ] Datasheet revision letter and date. Currency, errata and PCN: "not checked (no web access)" unless I said otherwise.
- [ ] MPN decoded from the Ordering Information table: base, package code, temp grade, lead finish, packaging. Show it.
- [ ] Lead finish recorded. Pure Sn gets flagged as a tin-whisker open item.
- [ ] Lifecycle status and MSL from the package option addendum, with its date (addenda are often newer than the DS).
- [ ] Radiation (TID/SEL/SEE): give the DS value, or write "radiation: no data in DS". Never take numbers from similar parts.

## B. Limits (step 2). Guaranteed values only.
- [ ] Read limit tables from rendered page images, not text extraction: columns (min/typ/max, 25 °C vs full-temp rows)
      scramble in text.
- [ ] Each limit is a datasheet min or max, never a typical value or a curve. A typical-only value goes in as
      `typ` with "(typical, not guaranteed)", or is left out. It is never a check bound.
- [ ] Use the full-temperature row for the chosen grade: ADI/LT "●" rows, TI "full range" rows. If only a 25 °C
      limit exists, it becomes an open item and a warning-level, waivable check (CLAUDE.md Defaults).
- [ ] Each limit records its test conditions (VS, TA, load, frequency). If the conditions don't cover the
      application, it becomes an open item.
- [ ] A limit stated relative to another pin is recorded with its reference pin. Sign convention is stated for
      negative quantities (P-FET VGS, sink current); compare magnitudes explicitly.
- [ ] Every Absolute Maximum Ratings row is in the limits table. That includes supply, each input/output pin,
      pin-to-pin differentials, input current, output short-circuit duration, Tj, storage.
- [ ] Category minimum set, plus rec-op:
  - Op amp: ICMR, output swing vs load, Isc, IB/IOS, VOS, GBW, slew, max C-load, IQ.
  - LDO/switcher: VIN, VOUT range, ILIM, dropout vs load, IQ, COUT/ESR range, UVLO/EN thresholds.
  - MOSFET: VDS, VGS, ID vs temperature, RDS(on) at the VGS used, SOA.
  - Instrumentation amp: supply span, VCM range vs rails, REF range, output swing vs load, gain equation and range,
    VOSI/VOSO, IB/IOS, CMRR min, gain error, gain drift, IQ, input overvoltage and clamp current.
  - TVS/ESD diode: VRWM, VBR min, IR at VRWM, clamp voltage at IPP (max), capacitance, IEC 61000-4-2/-4-5 ratings.
  - Interface/ADC/reference: VIH/VIL vs supply rail, bus-pin abs max vs fault range, input range vs VREF, REF range,
    output drive. IEC ESD/surge and bus-fault ratings: UNCHECKED, owner board.
  - Any other category: derive the set from the DS Electrical Characteristics headings. Keep rows with a guaranteed
    min/max that bound a module decision (input range, output range, offset/bias, supply current, threshold, timing,
    drive limit); typical-only rows are comments. Do not wait: log "category set derived, not user-approved".
  - All: Tj max, θJC/θJB, θJA (flagged "JEDEC board, convection"), ESD HBM/CDM, latch-up.
  - Leave out: typical curves, application-circuit values, other MPNs' ordering info, marking.
- [ ] Each input-capable pin: clamp diodes to which rails, abs-max input current, behaviour unpowered (V+ = 0 or
      high-Z). If a module can drive the pin while the part is off, it must check this or require a series R.

## C. Pins (steps 2 and 5)
- [ ] Pin table columns: unit, pin number, DS name, symbol name, vendor type, corrected type, io name/type, DS page.
- [ ] Corrected KiCad type comes from the datasheet function: supply power_in, regulator output power_out,
      open-drain open_collector, signal input/output/bidirectional. Never keep "passive" on an IC pin by default;
      external-component pins (gain resistor, compensation, soft-start) are passive. The DS I/O column loses to the
      pin's function text (INA821 lists +IN as "O"): record the error as an open item.
- [ ] Each EP/thermal pad gets its own row quoting the datasheet's exact wording ("must connect to V-", "may float").
      Never assume EP = GND. The io type follows the wording.
- [ ] Each non-function pin is classified with a cite: NC (no internal connection), DNC (internal node, must float), or
      reserved/must-tie. A vendor `no_connect` type is not evidence. Omitted no_connect pins auto-wire to
      `NotConnected()`, so confirm each one may float and may be poured over.
- [ ] Multi-unit parts: supply pins are in their own unit or marked shared. The docstring cites the datasheet's
      handling for an unused unit.
- [ ] Same-name pins merge only if the datasheet says they are one node. 0.4.95 connects every symbol pin that shares
      a name to one net (tested), so rename separate nodes (VIN1/VIN2, PGND/AGND) in the symbol.
- [ ] Mode-dependent pins (MODE/SYNC, straps, EN with hysteresis): name by primary function, list every mode with a
      cite, and record the strap sample time and pull value.

## D. Footprint (steps 3 and 5)
- [ ] Package code matches the drawing, height included. LT "S5" is TSOT-23, not SOT-23-5. Vendor footprint names are
      not evidence (Ultra Librarian called the INA821 VSSOP "SOIC_21IDGKR_TEX").
- [ ] Vendor densities: keep nominal (N), move L/M to `docs/vendor/<Value>_unused/` before import.
- [ ] Land pattern in IPC-7351 terms: Z (toe-to-toe), G (heel-to-heel), X, Y, C (pitch), plus density level or
      "vendor recommended". Give DS value vs footprint value, and state pad size as x by y. Default: pads set to the
      DS land pattern exactly. If the DS has no land pattern, Stop before deriving one from package min/max.
- [ ] Pad positions: each pad number sits where the top-view pin diagram puts it. Note whether the package drawing
      is a bottom view. Check for mirroring and rotation using the `scripts/pinmap.py` PAD x/y output
      (KiCad: top view, +y down).
- [ ] Pad number set == symbol pin number set, EP included, and pad numbering runs CCW in top view
      (`scripts/pinmap.py` exits 1 otherwise; pass every numeric EP/tab pad number as an extra argument). Exit 2:
      BGA/LGA or collinear pads are not winding-checked, and zig-zag connector numbering is not JEDEC CCW: compare with
      the DS top view by hand and record it.
- [ ] Pad 1 sits in the corner the DS top-view pin diagram shows. The script cannot check this.
- [ ] Courtyard present, 0.25 mm beyond pads and max body. Pin-1 marker on silk/fab sits outside the body outline.
      No duplicated vendor texts (`grep -c 'fp_text user "\*"'` = one per intended marker).
- [ ] Symbol geometry: `scripts/symgeom.py` exits 0 (pins on 2.54 grid, none inside the body, body centred, name
      offset 0.508-1.27). `pinmap.py` does not look at symbol coordinates.
- [ ] EP paste is split into windows covering 50-80% of the pad, unless the DS says otherwise.
- [ ] STEP model is for the exact package, or "no STEP" is stated. Never another part's model. `scripts/stepbox.py`
      body size and unit match the DS drawing; pin-1 orientation in the 3D viewer is an open item for me.

## E. Checks (steps 6 and 7)
- [ ] Each limits-table row maps to one check (name, severity) or to `UNCHECKED: <reason>; owner: module|board|layout`.
- [ ] Checks use `.min`/`.max` worst case. Every rail and signal net feeding a check has a tolerance check (warning).
- [ ] Every abs-max row is covered, including Tj, storage and lead temperature (usually UNCHECKED with an owner).
- [ ] Derated limits use the `derate` config, never a number baked into the component.
- [ ] The harness covers, per check: nominal, each boundary, just outside each boundary, input unset (rails too).
      Every error/warning check has been seen to fail. Waivable checks have also been seen to pass with a waiver.
      All of it is encoded in `test/matrix.sh` (docs/TESTING.md), which exits 0.
- [ ] No test case exists for the implicit `io(Power(voltage=))` documentation range.

## F. Limits library (step 6). `<basepart lowercase>_limits.zen`, the `ina821_limits.zen` pattern
- [ ] Holds raw guaranteed values only, never derated, each cited `DS p.<n>, <table>, <row>`, and the reference pin for
      relative limits ("reference unstated, taken to GND" when the DS gives none).
- [ ] Temperature scope is explicit: abs max / rec-op (record the table header), full-temp maxima for module error
      budgets, and a separate "25°C only" block with its test conditions. Typical values are comments only.
- [ ] Datasheet equations are named functions with the equation number, returning plain floats (`.value`), with the DS
      range `check()`ed (e.g. `rg_for_gain(g)`: 1 < g <= 10000). Inverse helpers say "snap with e96() in the module and
      re-check"; DS application tables are rounded and are not data.
- [ ] Contains no `io()`, `config()`, `Component()`, `Module()`, `add_electrical_check`, derate or ambient logic, and no
      values from other grades, packages or MPNs.
- [ ] The component `load()`s its limits from here; modules load it by full package URL (CLAUDE.md Zener facts).
