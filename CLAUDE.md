# Zener hardware repo: agent rules

Diode `pcb`/Zener library repo (`github.com/kb1lqc/zener-library`): reusable component packages built from manufacturer
datasheets, and modules built on them. No boards live here. I review every diff. Correctness beats speed. Never guess.
Recurring judgment calls have written defaults (**Defaults instead of questions**): apply them, log each one, and keep
going. Stop and ask only where that section says, or when evidence is missing and no default covers it.

## Ground truth
- Toolchain is pcb 0.4.x: root `pcb.toml` has `pcb-version = "0.4"` (it accepts major.minor only; "0.4.95" breaks every
  build), and the `pcb` shim updates itself, even on `--help`. `pcb +0.4.95 <cmd>` runs an exact version. Each component
  docstring records the versions it was verified on (`Verified:` line). After a toolchain update, run every component's
  `test/matrix.sh` and add the version; a changed case is a regression until explained. Version notes below
  ("in 0.4.95 ...") were tested on 0.4.95.
- No `pcb doc` and no `pcb search` command exist (0.4.95, 0.4.96). Before using any Zener construct, confirm it in, in
  order: stdlib source (`pcb list -m -json @stdlib` gives the path), `pcb <cmd> --help`, a throwaway build in the
  scratchpad (inside a dir with a `pcb.toml`), then https://docs.pcb.new/llms.txt (may be ahead of the toolchain). If a
  construct is in none of these, do not use it; tell me.
- Use the diodeinc `zener-language` and `librarian` skills (`.claude/skills/`; if missing:
  `npx skills add https://github.com/diodeinc/pcb --skill zener-language --skill librarian -a claude-code -y`). Where
  they conflict with this file, this file wins. I am not logged in to `pcb auth`; do not attempt registry or web search.
- Reads outside the repo are blocked. Datasheets go in `docs/datasheets/`, vendor model downloads in `docs/vendor/<Value>/`.
  Do not look elsewhere. Never copy a PDF into `components/`.
- Work on a branch. Touch only files the task needs. Do not commit unless I ask.
- After every change: `pcb fmt <package dir>`, then `pcb build -Wstyle -Dwarnings <package dir>`. `-Wstyle` promotes style
  advice to warnings. `-Dwarnings` fails the build on any warning. Mid-procedure, report the warnings still open; never
  call the task done until the build passes clean.
- Subagents cannot reach me. The main session owns every stop and the final report; subagents return evidence.

Terms: **MPN** = exact orderable number with `#` suffixes (LT6015IS5#TRMPBF). **BasePart** = family (LT6015).
**Value** = BasePart + package + grade, no reel suffix (LT6015IS5). It also names the package directory, so two
packages of one BasePart never collide. **MfrDir** = current manufacturer name without spaces (AnalogDevices).
**Cite** = `DS p.<printed page>, <table or figure title>, <row>` against the revision in the docstring. Use printed page
numbers, not the PDF index; table titles survive renumbering. Pages with no printed number (package addenda) are cited
`DS PDF p.<n>, <drawing number and revision>`.

## Component procedure (one Value per directory)
At the start of a component task, read `docs/COMPONENT_CHECKLIST.md` (sections A-F, cited per step), the four
`docs/templates/*.template` files and `docs/TESTING.md`. Reference packages: `components/TexasInstruments/INA821IDGK/`
(no ground pin, `_GND`) and `components/AnalogDevices/LTC4364HMS-1/` (ground pin, `_G = GND.voltage`, looped rows).
GATE = show the evidence and the Decision Log (every default applied: case | default | severity | open item), then
continue. Wait for me only on a **Stop** condition. My final review of the diff replaces mid-run approvals.

0. **Pre-flight (checklist A).** Check `docs/datasheets/`, `docs/vendor/<Value>/` (KiCad symbol + footprint, STEP),
   `.claude/skills/`, root `pcb.toml`, `expect` on PATH. If anything I must supply is missing, send ONE message listing all
   of it with exact paths, then do everything that does not need it. I supply only what Claude cannot fetch.
   Datasheet missing: send the message and end the turn. STEP missing: continue, state "no STEP", open item. Also check
   `pdftoppm` and `python3` on PATH.
1. **Intake (checklist A).** Datasheet revision and date, MPN decode from Ordering Information / package addendum
   (package, grade, finish, packaging, MSL), lifecycle. No web access: revision currency, errata, PCN and lifecycle are
   open items ("not checked"), not questions. Several packages or grades and the task does not name one: **Stop**.
2. **Extract (checklist B, C, D).** Pin table, footprint table, limits table, each with cites. Render table pages to PNG
   (`pdftoppm -r 110 -png -f N -l N`) and read them; text extraction scrambles columns. Apply the defaults for datasheet
   contradictions. **Stop** only on the conditions in the Defaults section.
3. **Vendor model.** Ultra Librarian ships L/N/M densities: keep N (nominal) in `docs/vendor/<Value>/footprints.pretty/`,
   move the others to `docs/vendor/<Value>_unused/` before import (the importer takes what it finds). Delete any PDF in
   the vendor folder. Run `scripts/pinmap.py` on the vendor files and compare pad numbers, positions and winding with
   step 2 (checklist D). Pass numeric EP/tab pad numbers as extra arguments. Exit 2 ("WINDING NOT CHECKED": BGA/LGA
   names, collinear pads) means compare pad 1 / A1 and the row and column direction with the DS top view by hand and log
   it in Done item 2. Same dimensions do not rule out a mirrored footprint. **Stop** on a mirrored or rotated pattern,
   a pad count, pitch or pin-1 corner mismatch, or a missing land pattern in the DS. Plain pad-size differences are fixed
   in step 5 by default. Never hand-draw a symbol or footprint. No STEP: say so; never substitute another part's model.
4. **Import (scripted).** From the repo root:
   `expect scripts/import_component.exp docs/vendor/<Value> <Value> <MfrDir>` (exit 0 = ok, 3 timeout, 4 early exit).
   It answers the importer's MPN and Manufacturer prompts; output lands in `components/<MfrDir>/<Value>/`. `pcb new
   component` needs a TTY: piped stdin and `script` fail. If `expect` is missing, **Stop** and give me that command.
   Exit 3 or 4: read the printed importer output, fix the cause (bad vendor path; an existing target dir: report it, do
   not delete it), re-run once; otherwise **Stop**. An unexpected extra prompt shows up as exit 3.
   The importer writes the MPN and Manufacturer answers verbatim into the symbol, renames files to `<Value>.*`, upgrades
   them to the current KiCad format, embeds the STEP (`kicad-embed://<Value>.step`), writes an empty `pcb.toml` and a stub
   `.zen` in which same-name pins collapse into one io (RG, RG became one net). Replace the stub from the template.
5. **Fixups.** Importer output is never final. Every time, one layer at a time, `pcb fmt` + build after each:
   - Symbol properties: `Manufacturer_Part_Number` = MPN, `Manufacturer_Name` = current name with spaces (Texas
     Instruments), `Datasheet` = manufacturer URL, `Value` = Value, `ki_fp_filters` = Value, `Description` filled. Add
     `Part(mpn=, manufacturer=, datasheet=)` with the same strings. Delete any PDF or `docs/` the importer created.
   - Pin electrical types from the datasheet function, not the vendor (checklist C). Vendor "passive"/"unspecified" on
     a supply disables the power-pin warnings the V- cast relies on.
   - Keep datasheet pin names verbatim in the symbol (`+IN`, `-VS`; they work as `pins={}` keys). Rename only same-name
     pins that are separate nodes (RG -> RG1/RG2). io names are uppercase functions (`IN_P`, `V_NEG`). Type them:
     `Power`/`Ground` for supplies, a stdlib interface only where the grouping is real (two sensor legs are not a
     `DiffPair`), `Net` otherwise.
   - Symbol `-Wstyle`: origin centred on the body AND every pin on the 2.54 grid; a 4-pins-per-side body cannot centre
     exactly, so shift by the centre rounded to 2.54 (the check tolerates ~1.27 off; INA821 used (-20.32, +2.54)).
     Shift EVERY `(at x y)`, including pins sitting at (0 0); only hidden properties stay at (0 0). Pin-name offset
     0.508-1.27 mm (use 0.762).
   - Footprint: set pads to the DS land pattern exactly (size, position, corner radius as `roundrect_rratio` =
     r / short side, max 0.5). Courtyard on F.CrtYd, 0.05 line: 0.25 mm beyond the outer pad edges and the max body
     or lead-tip extent, whichever is larger, rounded to 0.01 (BGA 0.25; connectors 0.5 unless the DS says
     otherwise). Delete duplicated vendor texts (often a locked and an unlocked copy of the pin-1 `*`) and move any Fab
     pin-1 marker outside the body. Set footprint `Value`
     = Value, `Datasheet`, and `Description` = package, drawing number and revision, "DS land pattern".
   - After every symbol or footprint edit run both, show the output, never re-check by eye:
     `python3 -I scripts/symgeom.py <sym>` (per unit: pin positions; flags off-grid pins, pins inside the body,
     off-centre body, bad name offset; exit 0/1/2 = ok/flagged/usage) and
     `python3 -I scripts/pinmap.py <sym> <mod> [EP pad numbers]` (pin/pad sets, pad x/y, winding; exit 1 on mismatch or
     mirroring, 2 = winding not checked, see step 3). Pad 1's corner is a hand check against the DS top-view diagram.
   - STEP: `python3 -I scripts/stepbox.py <step> <mod>` prints the vertex box in mm. Compare it with the DS drawing and
     say which matched: a one-solid model gives body + leads (lead span E/D, height A); an assembly model (TI) gives the
     body only, untransformed. A box matching neither, or an unknown unit (exit 2), is a **Stop**. File names are not
     evidence (TI's DGK0008A model is named MUA08A). Pin-1 orientation in the KiCad 3D viewer stays an open item for me.
6. **Limits and checks.** Copy `component.zen.template` and `limits.zen.template`. Numbers live in
   `<basepart lowercase>_limits.zen` (INA821 -> `ina821_limits.zen`, checklist F); checks live in `<Value>.zen`.
   Follow the rules below. Show the limits table, each row mapped to one check or one `UNCHECKED:` line, then write the checks.
7. **Verify.** Copy `harness.zen.template` to `test/harness.zen` and `matrix.sh.template` to `test/matrix.sh`, per
   `docs/TESTING.md`. Harness defaults are the nominal passing case, so `pcb build <package dir>` stays green. For each
   check cover nominal, each boundary, just outside each boundary (it must fail at the intended severity), input unset
   (UNVERIFIED warning) for every input including rails, and with a waiver set (for waivable checks). Add a
   `test/README.md` row per case, mirroring the INA821IDGK `test/README.md` header and Case | Overrides | Expect |
   Proves columns. `grep -rn '@@\|^#T' <package dir>` must print nothing (placeholders in comments do not fail a build).
   `test/matrix.sh` must exit 0 on the installed toolchain and on `pcb +<last verified>` (newest version in the
   reference packages' `Verified:` lines; if it cannot be fetched, installed version only, open item). Prove each new case
   can fail by flipping its expectation once. Skip cases for the implicit `io(Power(voltage=))` range.
8. **Review and report.** The main session (subagents cannot spawn agents) starts three fresh adversarial Sonnet
   reviewers in parallel, read-only on the repo, each with a scratch dir for builds: software (every `.zen`, template
   conformance, matrix coverage), hardware (limits vs DS, severities, pin types, defaults applied), KiCad (symbol,
   footprint, STEP, script output). Each prompt names the package path, this file, the checklist and the DS path, and
   asks for numbered findings: severity | file:line | problem | exact fix. Apply the findings that cite DS or rule text,
   log the rest as open items. One round; re-review only if a limit or check changed. Re-run step 7, then report
   everything in Done. Anything missing means the task is not done.

## Defaults instead of questions
Apply the default, add a Decision Log row, add the open item, continue. A default is void, and you **Stop**, if it would
be unsafe, if two defaults conflict, or if the "Stop if" column applies.

| Case | Default | Stop if |
|---|---|---|
| Abs-max row with no stated reference pin (INA821 ±40 V inputs) | Check against the part's own ground pin net (`_rel`, ref `<GND pin>.voltage`); the constant `_GND = Voltage("0V")` only for parts with no ground pin (op amp, in-amp), commented "reference unstated; system 0 V assumed". Error, derated, open item. Record the row's supply condition; if it holds only with supplies applied (INA821 Fig 63), add the docstring line "valid with supplies in rec-op; unpowered drive: owner module". Never invent a rail-relative bound. Rows named for a pin pair (VDS, VGS, VCE, VR, VBST-VSW, VCC-VEE) are not this case: use the named pin | The DS states a reference (use it); several grounds (isolated, GND1/GND2); no ground pin and the part is not an amplifier-type part |
| Rail-relative abs max on a pin the part drives (OUT) | `UNCHECKED ...; owner: module`: outputs rarely carry a declared voltage, so a check would be UNVERIFIED in every instance. Exception, not a stop: if the output is the part's function (regulator VOUT, driver rail), check it against its stated reference, error, derated; a VIN-to-VOUT (reverse, back-feed) row is a `_rel` check | Never |
| Abs-max row shadowed by a stricter error check (abs TA vs grade) | `UNCHECKED ...; covered by <check>`; never register a check that cannot be seen failing alone | The covering check is warning-level or waivable |
| Limit guaranteed only at 25 °C (VCM range, REF range) | Warning-level check, waivable (`waive_<x>`), in a "25°C only" block of the limits file. Open item. An Absolute Maximum row stated only at 25 °C (MOSFET ID) stays an unwaivable error with the 25 °C value, open item | Never |
| Typical-only value (clamp current, ISC, bandwidth) | Never a bound. Comment or `UNCHECKED ...; owner: module` (the module rules enforce series R or clamps) | Never |
| "Specified by characterization" row | Treat as guaranteed; comment "characterized, not production tested (DS note N)" | Never |
| DS contradicts itself (pin I/O column says +IN is "O") | Priority: pin function text > pin diagram > I/O column. Record the error as an open item | Pin number, position or count disagree between diagram and table, or the function text conflicts |
| NC / DNC / EP | DS wording only, quoted. NC: omitted (auto NotConnected). DNC: must float, no pour. EP "must/should connect to X": shares X's symbol pin name (one node). EP "internally connected to X; connect to X or leave floating": connect to X, open item. EP "may float": omit. Never an independent io a module could tie to the wrong rail | EP or NC wording missing or ambiguous (a vendor `no_connect` type is not evidence) |
| External-component pins (RG, COMP, SS, RT, ILIM, PROG) | Symbol type passive, io `Net`, separate nodes renamed apart, DS equation in the limits file | The DS lists the pin as a voltage input with its own abs max (FB, CS, SENSE): input type and a check |
| Abs max on a pin whose voltage the part or an external passive network sets (SW, BOOT, COMP, SS, RT, ILIM, VCC bypass) | `UNCHECKED ...; owner: module\|layout`, equation in the limits file: the net never carries a declared voltage | The pin is a voltage input (FB, CS+/-, EN, PG pull-up rail): check it |
| Abs-max row qualified by time, pulse or duty (SW -5 V < 10 ns, ID pulsed) | DC checks use the continuous row only; the qualified row is `UNCHECKED ...; DC checks exclude transients; owner: layout\|module` | Only a pulsed value exists, no continuous one |
| Power-dissipating part (LDO, FET, load switch, driver) | Limits file exports `tj_rise(p)` from θJA ("JEDEC board, convection") and Tj max; component row `UNCHECKED ...; owner: module (must call tj_rise)`. SOA and ID-vs-T curves: UNCHECKED, owner module | Never |
| Input current, clamp, unpowered behaviour without DS data | `UNCHECKED ...; owner: module` plus docstring note; module adds series R or clamps | Never |
| Lead finish / MSL | From the package addendum. Pure Sn or "NIPDAU \| SN" = tin-whisker open item. Missing MSL = "no data in DS" | Never |
| Revision currency, errata, PCN, lifecycle | Open item "not checked (no web access)"; status from the addendum with its date | I named a different revision |
| Vendor footprint differs from the DS land pattern in pad size only | Nominal density, pads edited to the DS pattern exactly (step 5), DS vs footprint per dimension in Done | Mirror, rotation, pad count, pitch or pin-1 mismatch; no DS land pattern |
| Category not in checklist B | Derive the set (checklist B rule), open item "category set derived, not user-approved" | The part switches power or connects off-board (buck, hot-swap, gate driver, isolator) and the derived set lacks Tj, a current limit or a fault-pin rating |
| Alternatives | Same part, other reel/tube suffix, or a wider grade whose every checked limit is equal or tighter in its DS | Never |
| Limits layout | Separate `<value>_limits.zen` (checklist F) | Never |
| Toolchain | Float `"0.4"`; run `test/matrix.sh` on the installed version and on `pcb +<last verified>` (step 7) | A case differs between versions |

## Limit and check rules
- Limits are guaranteed datasheet min/max only, from the full-temperature row for the chosen grade, with test conditions
  recorded. A typical value or a curve is never a check bound (checklist B). Abs-max and rec-op tables usually apply
  "over operating free-air temperature range" (record the header).
- Scope: every Absolute Maximum Ratings row, rec-op, and the category minimum set in checklist B. Nothing else.
- Give both ends of every range their unit: `Voltage("-0.3V to 76V")`, `Temperature("-40°C to 85°C")`. In 0.4.95,
  `"-40 to 85°C"` parses as -313.15 to 85 °C (tested).
- Every abs-max row gets exactly one of: a check (name + severity), or
  `# UNCHECKED: <row> (<cite>); <reason>; owner: module|board|layout|assembly`, one line per row (ESD HBM and CDM are
  two rows). Signal pins count, not only supplies.
- Store raw datasheet limits. Never bake a derated number into a component. Derating comes in through the `derate` config
  (a factor in (0, 1] that shrinks abs-max magnitudes; the template rejects >1), set at project level, passed down.
- Severity: abs max or rec-op violated = error. Special region (Over-The-Top, below rec-op load, 25 °C-only rec-op) =
  warning. Input unset = UNVERIFIED warning. A rail or signal net feeding a check without tolerance (min == max) =
  warning, because worst case is not assessed (exactly 0 V is exempt). Every docstring states that the checks are DC
  steady-state and do not cover transients, overshoot, hot-plug ringing or load dump.
- Limits stated against another pin (input vs V-, VGS, IN to OUT) use `_rel` with that reference pin: worst case
  `v.min - ref.max` and `v.max - ref.min`. A window between two rails ((V-)+2 V to (V+)-2 V) uses `_band`. For negative
  quantities (P-FET VGS, sink current), state the sign convention in the comment.
- Register every check through the template's `_limit()` (code below). It never lets an unset input pass, and it handles
  waivers. Inside a check function, fail with `check()` or `error()`.
- Do not put `warn()` or a top-level `check()` on connection-dependent conditions. `Module()` evaluates the file once with
  unconnected inputs before the real pass, so they false-fire. Electrical checks run after evaluation, on real nets.
- `io(Power(voltage=...))` adds an implicit check, but only at warning severity. It documents the rail; it does not
  enforce a limit.
- A rail that may be a negative supply or GND (op-amp V-): `io(Net)`, then cast `Power(net, voltage=net.voltage)` at
  the pin. `io(Power)` rejects `Ground`, `io(Ground)` rejects a -15V `Power`, and `io(Power|Ground)` is not allowed.
  Cover the lost type check with `_rel` span checks.
- Temperature: the component holds the grade's TA range and checks it against the `ambient` config (unset = UNVERIFIED).
  An alternate may have a wider grade than the primary (I primary, H alternate), never a narrower one.
- `alternatives` holds only form-fit-function-identical variants (reel/tube, wider grade). Pin-compatible second
  sources go in open items until someone verifies them electrically.
- The `_limit` helpers are copied per component, verbatim. A shared `lib/` package was tested and rejected for now:
  it needs `pcb sync` dependencies, `_ROOT` passed in, and breaks the matrix mutation case. Revisit at 3+ components.

## Waivers (intentional warning-level conditions under -Dwarnings)
0.4.95 has no per-check acknowledgement. `# suppress:` comments and `-S` match by kind or severity, and
`add_electrical_check` has no kind, so they would hide every warning on a line or in the build. They also do not reach
a child module's checks from the instance line (tested). Convention:
- Each waivable check gets `waive_<check> = config(str, default="")`. A non-empty value is the rationale with a cite;
  `_limit()` then drops that check to advice. Only warning-level checks are waivable; `_limit()` refuses to waive an error.
- Set the waiver at the instance: `waive_ott="Input intentionally above V+, DS p.10 Over-The-Top"`. Empty = not waived.
- Never suppress with `# suppress:`, `-S`, or by deleting a check. List every waiver in the report:
  `grep -rn 'waive_[a-z_]*=' --include='*.zen' . | grep -v '/.pcb/'` (harness pass-throughs of empty defaults are not
  waivers).

## Template core (verbatim from the build-verified template)
```zen
_ROOT = len(builtin.current_module_path()) == 0  # built standalone, not instantiated


def _limit(name, fn, inputs, severity, waiver=""):
    # Unset input: UNVERIFIED warning, never a silent pass. Waiver drops a warning to advice.
    if waiver and severity != "warning":
        error("only warning-level checks can be waived: " + name)
    unset = [k for k, v in inputs.items() if v == None]
    if unset:

        def _unverified(_m):
            error("UNVERIFIED " + name + ": no value for " + ", ".join(unset))

        builtin.add_electrical_check(name=name, check_fn=_unverified, severity="advice" if _ROOT else "warning")
    else:
        builtin.add_electrical_check(name=name, check_fn=fn, inputs=inputs, severity="advice" if waiver else severity)
```
Usage (signal pins get abs-max coverage too, looped against their reference): see the check block at the end of
`docs/templates/component.zen.template` and `components/TexasInstruments/INA821IDGK/INA821IDGK.zen`.
`_ROOT` drops UNVERIFIED to advice only when the component itself is built (no nets attached), so the package build stays
green. In any real instance, an unset input warns and fails `-Dwarnings`.

## Zener facts (tested; each cost a failed build once)
- Units: `.min`/`.max` return floats in SI units (Temperature in kelvin). A ratio of physical values is a unitless
  `PhysicalValue`; use `.value` before float math (`gain()` returns `.value`).
- Harness: an unnamed `Net()` is an error. `None` cannot be passed to a typed `config()`, so omit an unset optional
  input with `**({} if x == "unset" else {"ambient": x})`, which must be the LAST argument.
- Judge a build by its exit code, never by the absence of `✗`: a build that cannot start prints no `✗`.
- `Component()` needs no `footprint=` when the symbol's `Footprint` property names the package footprint.
- Every `.zen` beside a `pcb.toml` is a package entrypoint; a limits library builds as "(0 components)", which is fine.
- Workspace: packages load each other by full URL, `load("github.com/kb1lqc/zener-library/components/<MfrDir>/<Value>/
  <value>_limits.zen", ...)` and `Module(".../<Value>.zen")`, then `pcb sync`. Relative paths that leave a package fail
  ("escapes beyond package root"). Never hand-edit resolved versions.
- expect: a braced pattern list must span lines; on one line Tcl reads it as one literal pattern and the script hangs.

## Done: evidence to show
1. Pin table (checklist C columns), `scripts/symgeom.py` and `scripts/pinmap.py` output from after the last symbol edit,
   both exit 0 (pinmap exit 2: the hand check of pad 1 / A1 and row direction, written out).
2. Footprint table: IPC-7351 Z/G/X/Y/C, DS value vs footprint value, cite; pad-position check; courtyard; pin-1 marker;
   EP paste split; STEP model status with `scripts/stepbox.py` output.
3. Limits table: parameter | min/typ/max + unit | test conditions | cite | check name + severity, or UNCHECKED + owner.
4. Check test matrix: the `test/README.md` table, plus the verbatim `test/matrix.sh` summary line
   (`N/N cases as expected`) for each toolchain version run.
5. Verbatim tail of `pcb fmt` and `pcb build -Wstyle -Dwarnings <package dir>`, showing zero warnings.
6. Waivers: the grep output, or "none".
7. Decision Log: every default applied, with its open item.
8. Open items: datasheet ambiguities, 25 °C-only limits, revision/errata/PCN status, lead finish, lifecycle, radiation
   ("no data in DS" if so), unverified second sources, 3D-viewer pin-1 check, and any Zener syntax not confirmed in
   stdlib source or a test build.

## Modules (hierarchical, reusable circuits)
- Build from components. Expose design intent via `config()` (gain, Vout, current limit), not raw component values.
- Load datasheet numbers and equations from the component's `_limits.zen`; never retype them.
- Pass `derate`, `ambient` and any waiver down to each component. Never hard-code them in a module.
- Implement datasheet equations in named functions with cites. Snap results with the E-series helpers in
  `@stdlib/utils.zen` (`e24`, `e96`, ...) and `check()` the resulting tolerance against the requirement.
- A module that can drive an input while the part is unpowered must check the clamp-current limit or add a series R.
- Keep topology stable: configs change values and `dnp`, never add, remove, or reconnect instances.
