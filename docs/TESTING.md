# Component check testing

How every component's electrical checks are proven (CLAUDE.md step 7). A check you have not seen fail is unverified.
Reference implementation: `components/TexasInstruments/INA821IDGK/test/`.

## Files per component
| File | Role |
|---|---|
| `test/harness.zen` | Instantiates the component once. Every input is a `config()` whose default is the nominal passing case, so `pcb build <package>` stays green. The string `"unset"` leaves a value off. |
| `test/matrix.sh` | Start from `docs/templates/matrix.sh.template` (worked example; it exits 2 until edited). Self-checking case list. Builds the harness once per case with `--config` overrides and compares the outcome with the expectation. Exits 1 on any difference. |
| `test/README.md` | One row per case: what it sets and what it proves. |

## Running
```
components/<Mfr>/<Value>/test/matrix.sh            # current toolchain
components/<Mfr>/<Value>/test/matrix.sh 0.4.95     # exact toolchain (pcb +0.4.95)
```
Output is one `ok`/`FAIL` line per case and `N/N cases as expected`. A `FAIL` line prints the expected and observed result
and the build's diagnostics. Run it after every component change and after every toolchain update.

## How a case is judged
Every build runs `pcb build -Wstyle -Dwarnings`. `-Dwarnings` turns any warning into a failed build, so the result is
classified from the exit code and the diagnostics:

| Result | Meaning |
|---|---|
| `pass` | exit 0 (advice-level diagnostics, such as waived checks, do not fail the build) |
| `error` | non-zero exit with an `Error` diagnostic (other than "Build failed") |
| `warning` | non-zero exit with only `Warning` diagnostics |

The case also names a text that must appear in the output, normally the check's own message with its numbers
(`"35.0 to 36.1 V outside 4.5 to 36.0 V"`). Matching on the message proves the intended check fired, not some other
one, and that it computed the expected worst case. Never judge on the presence of `✗` alone: a build that fails to
start (bad `pcb.toml`, parse error) prints no `✗` and would look like a pass.

## Case types (each check gets all that apply)
| Type | Purpose | Construction |
|---|---|---|
| nominal | the harness defaults pass clean | no overrides |
| boundary | the exact limit passes | a range whose worst-case edge lands exactly on the limit, e.g. `vinp=39V to 40V` for a 40 V max. Give the range a width so the tolerance check does not fire |
| just outside | the check fails, at its intended severity | move the worst-case edge just past the limit (0.05-0.1 V, 1 °C). Expect `error` for abs max and rec-op, `warning` for special regions |
| waived | a waiver drops a warning to advice | the failing input plus `waive_<check>="<rationale>"`; expect `pass` |
| unset | a missing value never passes silently | `<input>=unset`; expect `warning` with `UNVERIFIED <check>` |
| tolerance | a net with min == max warns | a point value such as `vp=15V`; exactly 0 V (GND) is exempt and has its own `pass` case |
| guard | config validation | e.g. `derate=0`, `derate=1.5` must error |
| mutation | code paths no config can reach | the script patches a temp copy of the package (e.g. adds a waiver to an error-level check) and expects the refusal; the patch is checked to have applied |
| package_root | the package built alone stays green | `pcb build <package>`: with no nets attached, UNVERIFIED drops to advice |

Skip cases for the implicit `io(Power(voltage=))` documentation range (CLAUDE.md).

## Worst case and isolation
- Checks compare ranges at their worst edge. A pin limit stated against another pin uses `v.min - ref.max` and
  `v.max - ref.min`. A window between two rails uses `(lo rail).max + offset` and `(hi rail).min - offset`. So boundary
  values come from the rail tolerance: with V+ = 15 V 5%, V+ min = 14.25 V, and a (V+)-2 V limit is 12.25 V.
- One case should fire one check. When two checks share an input, isolate the one under test:
  - Use `derate` to pull an abs-max limit inside a rec-op limit (abs_span at derate 0.8 = 32 V, below op_span 36 V).
  - Waive the overlapping warning-level check (`waive_vcm=test` while testing the ±40 V abs max).
  - Where isolation is impossible, a stricter check shadows a looser one. Record the looser row as `UNCHECKED: covered
    by <check>` instead of registering a check that can never be seen failing alone.
  - Where only one edge is shadowed (LTC4364 abs_VCC: its -40 V edge sits below op_VCC's 4 V), keep the check: its
    other edge fails alone. Test the shadowed edge as a combined case and name the edge in a comment beside the
    checks and in `test/README.md`.
- The expected text pins the isolated check: an `error` case must match that check's message, not merely any error.

## Adding a case
1. Add a `t <name> <pass|error|warning> "<text>" KEY=VALUE ...` line to `matrix.sh` under its check. Quote values with
   spaces: `"vp=15V 5%"`.
2. Put a comment line directly above it: the scenario, the worst-case arithmetic from the values it sets and the
   harness defaults (`span max = 16.1 - (-16) = 32.1 V, 0.1 V over 32 V`), and which checks fire (`only abs_span
   fails`, or `abs_VCC fails; op_VCC also fires, the text pins abs_VCC`). Confirm every "also fires" claim from a
   real build's output, never by reasoning alone.
3. Add a row to `test/README.md`; its Proves column must agree with the comment.
4. Run the script. Prove a new case can fail: flip its expectation once and confirm `FAIL` and exit 1.

## Toolchain updates
`pcb-version = "0.4"` in the root `pcb.toml` takes the latest 0.4.x, and the `pcb` shim updates itself. After an update,
run every component's `test/matrix.sh`, then add the version to the `Verified:` line in the component docstring. If a
case changes, treat it as a regression until explained.
